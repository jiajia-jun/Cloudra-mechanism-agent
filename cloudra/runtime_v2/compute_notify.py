"""v2-native compute job notifications: IPC task_finished -> agent.message."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from cloudra.infra import events
from cloudra.persistence import paths
from cloudra.persistence.database import ConversationDB
from cloudra.runtime.compute_notify import build_compute_finish_content, resolve_submission_info
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.schemas import Command

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

logger = logging.getLogger("runtime_v2.compute_notify")


class ComputeNotifyBroker:
    """Subscribe to compute ``task_finished`` IPC and deliver via CommandBus."""

    def __init__(self, core: "RuntimeCore") -> None:
        self.core = core
        self._listeners: dict[str, asyncio.Task] = {}
        self._maintain_task: asyncio.Task | None = None
        self._delivered: set[tuple[str, int, str]] = set()

    async def start(self) -> None:
        if self._maintain_task is not None:
            return
        self._maintain_task = asyncio.create_task(self._maintain_listeners(), name="compute-notify")

    async def close(self) -> None:
        task, self._maintain_task = self._maintain_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        listeners = list(self._listeners.values())
        self._listeners.clear()
        for listener in listeners:
            listener.cancel()
        if listeners:
            await asyncio.gather(*listeners, return_exceptions=True)

    async def ensure_project(self, project_id: str) -> None:
        if project_id in self._listeners:
            return
        queue = await events.subscribe_async(project_id, "task_finished")
        self._listeners[project_id] = asyncio.create_task(
            self._listen(project_id, queue),
            name=f"compute-notify:{project_id}",
        )

    async def _maintain_listeners(self) -> None:
        while True:
            try:
                project_ids = set(self.core.projects.keys())
                root = paths.conversations_dir()
                if root.is_dir():
                    project_ids.update(
                        child.name for child in root.iterdir() if child.is_dir()
                    )
                for project_id in project_ids:
                    await self.ensure_project(project_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("compute notify listener maintenance failed")
            await asyncio.sleep(5.0)

    async def _listen(self, project_id: str, queue: asyncio.Queue) -> None:
        while True:
            message = await queue.get()
            if not isinstance(message, dict):
                continue
            if message.get("kind") != "task_finished":
                continue
            if message.get("task_kind") != "compute":
                continue
            try:
                await self._deliver(project_id, message)
            except Exception:
                logger.exception("compute notify delivery failed for %s", project_id)

    async def _deliver(self, project_id: str, payload: dict[str, Any]) -> None:
        if project_id not in self.core.projects:
            return
        task_id = int(payload.get("task_id") or 0)
        state = str(payload.get("state") or "")
        if not task_id or not state:
            return
        key = (project_id, task_id, state)
        if key in self._delivered:
            return
        self._delivered.add(key)

        content = str(payload.get("content") or "").strip()
        if not content:
            content = await self._fallback_content(project_id, task_id, state)

        session_id = payload.get("session_id")
        delivered: set[str] = set()
        if isinstance(session_id, str) and session_id in self.core.agents:
            await self._send_message(session_id, content)
            delivered.add(session_id)

        if payload.get("notify_coordinator", True):
            coordinator = self._coordinator_for(project_id)
            if coordinator is not None and coordinator.id not in delivered:
                await self._send_message(coordinator.id, content)

    async def _fallback_content(self, project_id: str, task_id: int, state: str) -> str:
        db = ConversationDB(project_id)
        info = await resolve_submission_info(db, task_id)
        fail_reason = ""
        try:
            async with db.aconnect() as con:
                cur = await con.execute(
                    "SELECT path, last_error FROM compute_jobs WHERE id=?",
                    (task_id,),
                )
                row = await cur.fetchone()
            if row:
                info["path"] = row[0] or info.get("path") or ""
                fail_reason = row[1] or ""
        except Exception:
            pass
        return build_compute_finish_content(
            task_id=task_id,
            state=state,
            input_path=str(info.get("path") or ""),
            fail_reason=fail_reason,
        )

    def _coordinator_for(self, project_id: str):
        return next(
            (
                agent
                for agent in self.core.list_project_agents(project_id)
                if agent.role_id == "coordinator"
            ),
            None,
        )

    async def _send_message(self, session_id: str, content: str) -> None:
        body = content if content.startswith("[Compute job]") else f"[Compute job]\n{content}"
        await CommandBus(self.core).execute(
            Command(
                type="agent.message",
                target={"session_id": session_id},
                payload={"content": body},
                actor="system",
            )
        )
