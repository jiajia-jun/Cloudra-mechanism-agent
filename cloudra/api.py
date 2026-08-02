"""Cloudra HTTP API。

API 是应用服务层的 HTTP 适配器。默认仅监听本机；如需局域网访问，请设置
``CLOUDRA_API_TOKEN`` 并显式指定 ``CLOUDRA_API_HOST=0.0.0.0``。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cloudra import __version__, events, paths
from cloudra.config import get_config, set_config_value
from cloudra.database import ConversationDB
from cloudra.service import CloudraService, validate_conversation_id
from cloudra.skill_class import skill_loader


class SessionCreate(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    working_directory: str | None = Field(default=None, max_length=4_096)
    # 按 Session 启用 YOLO 全自动审批（等价 CLI 的 --yolo，但只作用于本会话）
    yolo: bool = False


class ConfigSet(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    value: str = Field(default="", max_length=4_096)


def _validate_working_directory(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("工作目录必须使用绝对路径")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("工作目录不存在或无法访问") from exc
    if not resolved.is_dir():
        raise ValueError("工作目录必须指向一个文件夹")
    return str(resolved)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "denied"]
    denial_reason: str = Field(default="", max_length=2_000)


class SessionMessageAppend(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    working_directory: str | None = Field(default=None, max_length=4_096)


def _allowed_origins() -> list[str]:
    raw = os.getenv(
        "CLOUDRA_API_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,"
        "tauri://localhost,http://tauri.localhost,https://tauri.localhost",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _registry_revision(names: list[str]) -> str:
    payload = json.dumps(sorted(names), ensure_ascii=False, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def create_app(service: CloudraService | None = None) -> FastAPI:
    """创建应用；工厂函数让测试可以注入假的 service。"""
    service = service or CloudraService()
    api_token = os.getenv("CLOUDRA_API_TOKEN", "").strip()

    app = FastAPI(
        title="Cloudra API",
        description="Cloudra 前端与自动化客户端使用的 Conversation/Session API",
        version=__version__,
    )
    app.state.cloudra_service = service
    if hasattr(service.session_runner, "recover_stale_sessions"):
        app.router.add_event_handler("startup", service.session_runner.recover_stale_sessions)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Cloudra-Client-Version",
            "X-Cloudra-Download-Token",
            "X-Cloudra-Protocol-Version",
        ],
    )

    async def authorize(authorization: str | None = Header(default=None)) -> None:
        # 本机开发时可以不设 token；对外监听时启动函数会强制要求 token。
        if not api_token:
            return
        if authorization != f"Bearer {api_token}":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少或无效的 API Token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    protected = [Depends(authorize)]

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/operations/status", dependencies=protected)
    async def operations_status() -> dict:
        """Low-cardinality operational counters; never returns prompts or tokens."""
        from cloudra.operations import operational_status

        minimum = int(os.getenv("CLOUDRA_MIN_FREE_BYTES", str(1024**3)))
        return operational_status(Path(get_config().data_dir), min_free_bytes=minimum)

    @app.get("/api/runtime/diagnostics", dependencies=protected)
    async def runtime_diagnostics() -> dict:
        """返回当前进程实际加载的静态能力，不暴露配置凭据。"""
        from cloudra.runtime_profile import filter_tools_for_runtime, is_mobile_runtime
        from cloudra.subagents import Subagent_hash
        from cloudra.tools import get_tool_load_errors, get_tools_lst

        tool_entries = filter_tools_for_runtime(get_tools_lst())
        tool_names = sorted(entry.tool_name for entry in tool_entries)
        subagent_ids = sorted(Subagent_hash().subagents_dict)
        return {
            "server_version": __version__,
            "runtime_profile": "android" if is_mobile_runtime() else "server",
            "tools": {
                "revision": _registry_revision(tool_names),
                "names": tool_names,
                "load_errors": get_tool_load_errors(),
            },
            "subagents": {
                "revision": _registry_revision(subagent_ids),
                "agent_ids": subagent_ids,
            },
        }

    @app.post("/api/conversations", status_code=status.HTTP_201_CREATED, dependencies=protected)
    async def create_conversation() -> dict:
        conversation = service.create_conversation()
        return {"id": conversation.id, "state": conversation.state}

    @app.post(
        "/api/conversations/{conversation_id}/sessions",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=protected,
    )
    async def create_session(conversation_id: str, request: SessionCreate) -> dict:
        try:
            working_directory = _validate_working_directory(request.working_directory)
            if working_directory is None:
                _, record = service.submit_session(request.query, conversation_id, yolo=request.yolo)
            else:
                _, record = service.submit_session(
                    request.query,
                    conversation_id,
                    working_directory=working_directory,
                    yolo=request.yolo,
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return record.to_dict()

    @app.get(
        "/api/conversations/{conversation_id}/sessions/{session_id}/events",
        dependencies=protected,
    )
    async def get_session_events(
        conversation_id: str,
        session_id: str,
        after_id: int = 0,
    ) -> list[dict]:
        try:
            return service.session_runner.events(conversation_id, session_id, after_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get(
        "/api/conversations/{conversation_id}/sessions/{session_id}/diagnostics",
        dependencies=protected,
    )
    async def get_session_diagnostics(
        conversation_id: str,
        session_id: str,
    ) -> dict:
        """读取该 Session 最近一次实际 LLM 请求的 prompt/tool 诊断。"""
        try:
            session = service.session_runner.get(conversation_id, session_id)
            session_events = service.session_runner.events(conversation_id, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="Session 不存在")
        requests = [
            event
            for event in session_events
            if event.get("event_type") == "llm_request_diagnostics"
        ]
        return {
            "server_version": __version__,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "latest_request": requests[-1]["data"] if requests else None,
        }

    @app.get(
        "/api/conversations/{conversation_id}/sessions/{session_id}/events/stream",
        dependencies=protected,
    )
    async def stream_session_events(
        conversation_id: str,
        session_id: str,
        after_id: int = 0,
    ) -> StreamingResponse:
        async def generate():
            cursor = after_id
            db = ConversationDB(conversation_id)
            if not Path(db.path).is_file():
                # 数据库尚未创建（会话从未启动）：保持原有行为，直接结束空流
                return

            await events.ensure_listener(conversation_id)
            queue = await events.subscribe_async(conversation_id, "session_event")

            terminal_event_types = {"completed", "failed", "cancelled", "killed", "interrupted"}
            keepalive_interval = 15.0

            with db.connect() as conn:
                # 先补拉订阅前已经落库的事件
                buffered = service.session_runner.events(conversation_id, session_id, cursor, conn=conn)
                for event in buffered:
                    cursor = event["id"]
                    yield f"id: {cursor}\nevent: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if any(event["event_type"] in terminal_event_types for event in buffered):
                    return

                while True:
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=keepalive_interval)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue

                    # 只转发目标 session 的事件
                    if msg.get("session_id") != session_id:
                        continue

                    # 可能有多个事件在同一 IPC 消息里（不会，但保险起见做 catch-up）
                    fresh = service.session_runner.events(conversation_id, session_id, cursor, conn=conn)
                    for event in fresh:
                        cursor = event["id"]
                        yield f"id: {cursor}\nevent: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if any(event["event_type"] in terminal_event_types for event in fresh):
                        return

                    record = service.session_runner.get(conversation_id, session_id, conn=conn)
                    if record is None or record.state in terminal_event_types | {"sleeping"}:
                        return

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/api/conversations/{conversation_id}/sessions", dependencies=protected)
    async def list_sessions(conversation_id: str) -> list[dict]:
        try:
            return [record.to_dict() for record in service.session_runner.list(conversation_id)]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/conversations/{conversation_id}/sessions/{session_id}", dependencies=protected)
    async def get_session(conversation_id: str, session_id: str) -> dict:
        try:
            record = service.session_runner.get(conversation_id, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Session 不存在")
        return record.to_dict()

    @app.post(
        "/api/conversations/{conversation_id}/sessions/{session_id}/cancel",
        dependencies=protected,
    )
    async def cancel_session(conversation_id: str, session_id: str) -> dict:
        try:
            record = await service.session_runner.cancel(conversation_id, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Session 不存在")
        return record.to_dict()

    @app.get(
        "/api/conversations/{conversation_id}/sessions/{session_id}/children",
        dependencies=protected,
    )
    async def list_session_children(conversation_id: str, session_id: str) -> list[dict]:
        try:
            return [
                record.to_dict()
                for record in service.session_runner.list_children(conversation_id, session_id)
            ]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/conversations/{conversation_id}/sessions/{session_id}/messages",
        dependencies=protected,
    )
    async def append_session_message(
        conversation_id: str,
        session_id: str,
        request: SessionMessageAppend,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        command_id = idempotency_key or f"api-msg-{uuid.uuid4().hex}"
        try:
            working_directory = _validate_working_directory(request.working_directory)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            command, record = await service.append_session_message_command(
                command_id=command_id,
                conversation_id=conversation_id,
                session_id=session_id,
                content=request.content,
                working_directory=working_directory,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "command_id": command.command_id,
            "state": command.state,
            "session": record.to_dict(),
        }

    @app.get("/api/conversations", dependencies=protected)
    async def list_conversations() -> list[dict]:
        return service.list_conversations()

    @app.delete("/api/conversations", dependencies=protected)
    async def delete_all_conversations() -> dict:
        count = service.delete_all_conversations()
        return {"deleted": count}

    @app.get("/api/conversations/{conversation_id}/messages", dependencies=protected)
    async def get_messages(conversation_id: str) -> list[dict]:
        try:
            return service.get_conversation_messages(conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="无法读取会话消息") from exc

    @app.get("/api/approvals", dependencies=protected)
    async def list_approvals() -> list[dict]:
        return await service.list_pending_approvals()

    @app.post(
        "/api/conversations/{conversation_id}/approvals/{approval_id}/decision",
        dependencies=protected,
    )
    async def decide_approval(
        conversation_id: str,
        approval_id: int,
        request: ApprovalDecision,
    ) -> dict:
        try:
            changed = await service.decide_approval(
                conversation_id,
                approval_id,
                request.decision,
                request.denial_reason,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not changed:
            raise HTTPException(status_code=404, detail="待审批记录不存在")
        return {"id": approval_id, "conversation_id": conversation_id, "state": request.decision}

    @app.get("/api/skills", dependencies=protected)
    async def get_skills():
        return skill_loader().skill_datas_get()

    @app.get("/api/config", dependencies=protected)
    async def get_config_display() -> dict:
        """当前生效配置（敏感字段脱敏），等价 `cloudra config show`。"""
        return get_config().to_display_dict()

    @app.post("/api/config/set", dependencies=protected)
    async def set_config(request: ConfigSet) -> dict:
        """设置单个配置项，等价 `cloudra config set <key> <value>`。"""
        try:
            set_config_value(request.key, request.value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return get_config().to_display_dict()

    _LOG_CONTENT_CAP = 256 * 1024

    @app.get("/api/conversations/{conversation_id}/logs", dependencies=protected)
    async def get_conversation_logs(conversation_id: str) -> list[dict]:
        """读取对话日志目录下的所有日志文件，等价 `cloudra logs <conv_id>`。"""
        try:
            validate_conversation_id(conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        log_dir = paths.logs_dir(conversation_id)
        if not log_dir.is_dir():
            return []
        results = []
        for entry in sorted(log_dir.iterdir()):
            if not entry.is_file():
                continue
            try:
                raw = entry.read_bytes()[: _LOG_CONTENT_CAP + 1]
                truncated = len(raw) > _LOG_CONTENT_CAP
                results.append({
                    "name": entry.name,
                    "size": entry.stat().st_size,
                    "content": raw[:_LOG_CONTENT_CAP].decode("utf-8", errors="replace"),
                    "truncated": truncated,
                })
            except OSError:
                continue
        return results

    @app.get("/api/sessions", dependencies=protected)
    async def list_all_sessions(state: str | None = None) -> list[dict]:
        """跨会话聚合所有 Session，替代 CLI `sessions` 读取的遗留全局表。"""
        rows = []
        for conversation in service.list_conversations():
            conversation_id = conversation.get("id", "")
            try:
                validate_conversation_id(conversation_id)
            except ValueError:
                continue
            for record in service.session_runner.list(conversation_id):
                row = record.to_dict()
                row["conversation_id"] = conversation_id
                rows.append(row)
        if state:
            rows = [row for row in rows if row["state"] == state]
        rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return rows[:100]

    # Android/remote clients use only the stable, versioned control surface.
    from cloudra.api_v1 import create_v1_router

    app.include_router(create_v1_router(service, authorize))
    return app


def main() -> None:
    """启动开发服务器。默认只允许本机访问。"""
    import uvicorn

    host = os.getenv("CLOUDRA_API_HOST", "127.0.0.1")
    port = int(os.getenv("CLOUDRA_API_PORT", "8000"))
    if host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("CLOUDRA_API_TOKEN"):
        raise RuntimeError("对外监听 API 前必须设置 CLOUDRA_API_TOKEN")
    uvicorn.run("cloudra.api:create_app", host=host, port=port, reload=False, factory=True)


if __name__ == "__main__":
    main()
