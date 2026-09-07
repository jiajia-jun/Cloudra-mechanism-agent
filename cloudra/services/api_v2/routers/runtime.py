"""Runtime health/capabilities and global LLM config routes."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Any

from fastapi import APIRouter

from cloudra import __version__

from ..context import ApiContext
from ..models import GlobalConfigPatch


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/runtime/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @router.post("/api/v2/runtime/shutdown", dependencies=ctx.protected)
    async def runtime_shutdown() -> dict[str, str]:
        """显式全停入口（`cloudra stop` 调用）：进程内停准入（守护自愈
        失效），延迟一拍后 SIGTERM 本进程——uvicorn 走优雅 lifespan 关停
        （取消并 await 推理/收尾任务、关流/客户端、回收 JS host）。
        计算进程（scheduler/guard/QM）不受此入口影响（执行面铁律）。
        """
        from cloudra.services.daemon_supervisor import request_daemons_shutdown

        request_daemons_shutdown()
        # 先让响应发出去再关停本进程。
        asyncio.get_running_loop().call_later(
            0.5, os.kill, os.getpid(), signal.SIGTERM
        )
        return {"status": "shutting_down"}

    @router.get("/api/v2/runtime/capabilities", dependencies=ctx.protected)
    async def runtime_capabilities() -> dict[str, Any]:
        roles = [role.model_dump(mode="json") for role in ctx.core.roles.list()]
        return {
            "version": __version__,
            "roles": roles,
            "platform": "desktop",
            "strict_events": ctx.core.event_log.strict,
        }

    @router.get("/api/v2/runtime/config", dependencies=ctx.protected)
    async def runtime_config() -> dict[str, Any]:
        """Global LLM config: the fallback behind empty per-agent settings."""
        from cloudra.infra.config import get_config

        cfg = get_config()

        def slot(role) -> dict[str, Any]:
            return {
                "model": role.model,
                "url": role.url,
                "key_set": bool(role.key),
                "context_window": role.context_window,
                "timeout": role.timeout,
                "reasoning_effort": role.reasoning_effort,
            }

        return {
            "config_file": str(cfg.config_file),
            "coordinator": slot(cfg.coordinator),
            "follower": slot(cfg.follower),
        }

    @router.patch("/api/v2/runtime/config", dependencies=ctx.protected)
    async def patch_runtime_config(body: GlobalConfigPatch) -> dict[str, Any]:
        """Update one global LLM slot and persist it to the YAML config.

        Writes go through ``mutate_config``: the disk YAML is the source of
        truth, and the in-memory singleton (what empty per-agent settings
        fall back to via adapters.legacy_default_settings) is refreshed from
        disk in the same critical section, so the change is live on the next
        LLM request.  ``key=""`` clears the stored key; keys are write-only
        and never returned by the GET endpoint.
        """
        from cloudra.infra.config import mutate_config

        slot = body.slot
        changes = body.changes.model_dump(exclude_unset=True)

        def _apply(work) -> None:
            target = work.coordinator if slot == "coordinator" else work.follower
            for field, value in changes.items():
                setattr(target, field, value)

        await asyncio.to_thread(mutate_config, _apply)
        return await runtime_config()

    return router
