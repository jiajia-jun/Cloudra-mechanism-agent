"""Cloudra HTTP API。

API 是应用服务层的 HTTP 适配器。默认仅监听本机；如需局域网访问，请设置
``CLOUDRA_API_TOKEN`` 并显式指定 ``CLOUDRA_API_HOST=0.0.0.0``。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cloudra import __version__
from cloudra.config import get_config
from cloudra.service import CloudraService
from cloudra.skill_class import skill_loader


class SessionCreate(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "denied"]
    denial_reason: str = Field(default="", max_length=2_000)


def _allowed_origins() -> list[str]:
    raw = os.getenv(
        "CLOUDRA_API_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


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
        allow_headers=["Authorization", "Content-Type"],
    )

    artifacts_dir = Path(get_config().data_dir) / "artifacts"
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # 只读环境仍应能导入 API；此时仅禁用产物下载路由。
        pass
    if artifacts_dir.is_dir():
        app.mount("/artifacts", StaticFiles(directory=artifacts_dir), name="artifacts")

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
            _, record = service.submit_session(request.query, conversation_id)
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
            while True:
                events = service.session_runner.events(conversation_id, session_id, cursor)
                for event in events:
                    cursor = event["id"]
                    yield f"id: {cursor}\nevent: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                record = service.session_runner.get(conversation_id, session_id)
                if record is None or record.state in {
                    "completed", "sleeping", "failed", "cancelled", "killed", "interrupted"
                }:
                    break
                await asyncio.sleep(1)

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
            record = service.session_runner.cancel(conversation_id, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Session 不存在")
        return record.to_dict()

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

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


app = create_app()


def main() -> None:
    """启动开发服务器。默认只允许本机访问。"""
    import uvicorn

    host = os.getenv("CLOUDRA_API_HOST", "127.0.0.1")
    port = int(os.getenv("CLOUDRA_API_PORT", "8000"))
    if host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("CLOUDRA_API_TOKEN"):
        raise RuntimeError("对外监听 API 前必须设置 CLOUDRA_API_TOKEN")
    uvicorn.run("cloudra.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
