"""TUI 控制面：同进程 CloudraService，或经本机 HTTP 委托给隔离 runtime。"""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import MISSING, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from cloudra.services import control_store
from cloudra.services.service import CloudraService, SessionRecord


def runtime_url_from_env() -> str | None:
    raw = (os.environ.get("CLOUDRA_TUI_RUNTIME_URL") or "").strip()
    return raw or None


def create_tui_service() -> CloudraService:
    """TUI 用服务入口。设置了 ``CLOUDRA_TUI_RUNTIME_URL`` 时走隔离控制。"""
    from cloudra.tui.new.runtime_proc import inline_mode

    url = runtime_url_from_env()
    if url and not inline_mode():
        return IsolatedControlService(url)
    return CloudraService()


def session_record_from_dict(payload: dict) -> SessionRecord:
    """把 API JSON 还原为 SessionRecord。"""
    kwargs: dict[str, Any] = {}
    for field in fields(SessionRecord):
        if field.name in payload:
            kwargs[field.name] = payload[field.name]
            continue
        if field.default is not MISSING:
            continue
        if field.default_factory is not MISSING:  # type: ignore[comparison-overlap]
            continue
        kwargs[field.name] = None
    return SessionRecord(**kwargs)


_CANCELABLE_STATES = frozenset(
    {
        "queued",
        "running",
        "waiting",
        "waiting_for_user",
        "waiting_for_approval",
        "waiting_for_device",
    }
)


class _IsolatedSessionRunner:
    """读本地 SQLite；取消先本地打标/IPC，再尽力通知 runtime 取消协程。"""

    def __init__(self, service: "IsolatedControlService") -> None:
        self._service = service
        self._local = service._local_runner

    def list(self, *args, **kwargs):
        return self._local.list(*args, **kwargs)

    def list_children(self, *args, **kwargs):
        return self._local.list_children(*args, **kwargs)

    def events(self, *args, **kwargs):
        return self._local.events(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._local.get(*args, **kwargs)

    def recover_stale_sessions(self, *args, **kwargs):
        return self._local.recover_stale_sessions(*args, **kwargs)

    def submit(self, *args, **kwargs):
        raise RuntimeError("隔离 TUI 不能在本进程 submit；请经 HTTP runtime")

    async def submit_async(self, *args, **kwargs):
        raise RuntimeError("隔离 TUI 不能在本进程 submit_async；请经 HTTP runtime")

    async def cancel(self, conversation_id: str, session_id: str) -> SessionRecord | None:
        """取消隔离模式下的 Session。

        不能只走 HTTP：runtime 与 Agent 共用一个 asyncio 循环时，同步重活会
        饿死 uvicorn，Esc 的 cancel POST 一直排不上队。本地
        ``update_session_fields(cancel_requested)`` 会经 IPC 广播，Agent 的
        ``_cancel_consumer`` 在循环恢复后即可打断。

        也不调用本进程 ``SessionRunner.cancel`` 全文：其 ``record.pid`` 分支会
        SIGTERM 掉整个 runtime 进程。
        """
        record = await asyncio.to_thread(self._local.get, conversation_id, session_id)
        if record is None:
            return None
        if record.state in _CANCELABLE_STATES:
            await asyncio.to_thread(
                self._local._update,
                conversation_id,
                session_id,
                state="cancel_requested",
            )
        # 尽力让 runtime 取消协程；循环卡死时快速放弃，信号已在上面发出。
        try:
            payload = await asyncio.wait_for(
                self._service._request_json(
                    "POST",
                    f"/api/conversations/{conversation_id}/sessions/{session_id}/cancel",
                ),
                timeout=2.0,
            )
            if payload is not None:
                return session_record_from_dict(payload)
        except Exception:
            pass
        return await asyncio.to_thread(self._local.get, conversation_id, session_id)

    async def force_cancel(
        self, conversation_id: str, session_id: str
    ) -> SessionRecord | None:
        """强制终止：本地落 killed + 杀子进程，并尽力通知 runtime。

        不 SIGTERM Coordinator 的 ``record.pid``（那是 runtime 进程本身）。
        """
        from cloudra.infra.config import get_config
        from cloudra.tui.new.runtime_proc import read_runtime_pid

        record = await asyncio.to_thread(self._local.get, conversation_id, session_id)
        if record is None:
            return None
        if record.state in _CANCELABLE_STATES:
            await asyncio.to_thread(
                self._local._update,
                conversation_id,
                session_id,
                state="cancel_requested",
            )
        await asyncio.to_thread(
            self._local._cancel_descendants, conversation_id, session_id
        )
        runtime_pid = read_runtime_pid(Path(get_config().data_dir))
        if (
            record.pid
            and record.pid != os.getpid()
            and record.pid != runtime_pid
            and record.pid > 0
        ):
            try:
                os.kill(record.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        finished = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(
            self._local._update,
            conversation_id,
            session_id,
            state="killed",
            finished_at=finished,
        )
        await asyncio.to_thread(
            self._local._emit, conversation_id, session_id, "killed", {}
        )
        try:
            client = self._service._client_or_create()
            response = await asyncio.wait_for(
                client.post(
                    f"/api/conversations/{conversation_id}/sessions/{session_id}/cancel",
                    params={"force": "true"},
                ),
                timeout=2.0,
            )
            if response.status_code < 400 and response.content:
                return session_record_from_dict(response.json())
        except Exception:
            pass
        return await asyncio.to_thread(self._local.get, conversation_id, session_id)


class IsolatedControlService(CloudraService):
    """SQLite 只读/审批/交互仍可本进程；启动与取消任务走本机 HTTP runtime。"""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._local_runner = self.session_runner
        self.session_runner = _IsolatedSessionRunner(self)  # type: ignore[assignment]
        self._client: httpx.AsyncClient | None = None

    def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(60.0, connect=5.0),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        allow_404: bool = True,
    ) -> dict | None:
        client = self._client_or_create()
        response = await client.request(method, path, json=json)
        if allow_404 and response.status_code == 404:
            return None
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def submit_session_async(
        self,
        query: str,
        conversation_id: str | None = None,
        working_directory: str | None = None,
        yolo: bool = False,
        orchestration_mode: str | Any = "standard",
        orchestration_config: dict | None = None,
    ) -> tuple[str, SessionRecord]:
        del orchestration_config  # runtime 按 mode 派生
        if conversation_id is None:
            conversation = await asyncio.to_thread(self.create_conversation)
            conversation_id = conversation.id
        mode = getattr(orchestration_mode, "value", orchestration_mode)
        body: dict[str, Any] = {
            "query": query,
            "yolo": bool(yolo),
            "orchestration_mode": mode,
        }
        if working_directory:
            body["working_directory"] = working_directory
        payload = await self._request_json(
            "POST",
            f"/api/conversations/{conversation_id}/sessions",
            json=body,
            allow_404=False,
        )
        assert payload is not None
        return conversation_id, session_record_from_dict(payload)

    async def append_session_message_command(
        self,
        *,
        command_id: str,
        conversation_id: str,
        session_id: str,
        content: str,
        working_directory: str | None = None,
    ):
        del working_directory
        body: dict[str, Any] = {"content": content}
        headers = {"Idempotency-Key": command_id}
        client = self._client_or_create()
        response = await client.post(
            f"/api/conversations/{conversation_id}/sessions/{session_id}/messages",
            json=body,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        session = data.get("session") or data
        record = session_record_from_dict(session)
        command = control_store.ClientCommand(
            command_id=str(data.get("command_id") or command_id),
            conversation_id=conversation_id,
            session_id=session_id,
            command_type="session.message.append",
            payload={"content": content},
            state=str(data.get("state") or "applied"),
            result={"session_id": record.session_id},
            error=None,
            created_at="",
            applied_at=None,
        )
        return command, record

    async def dag_request_replan(self, conversation_id: str, note: str = ""):
        return await self._request_json(
            "POST",
            f"/api/conversations/{conversation_id}/dag/replan",
            json={"note": note},
            allow_404=True,
        )
