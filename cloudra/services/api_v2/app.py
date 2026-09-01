"""Thin FastAPI v2 routing over RuntimeCore + CommandBus.

This module knows HTTP concerns only.  Every write is submitted as a Command;
handlers live in runtime_v2.commands.  No business logic is allowed here.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from cloudra import __version__
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import CommandRejected

from .context import ApiContext
from .routers import build_routers


def create_v2_app(
    core: RuntimeCore | None = None,
    pipeline: Any = None,
    store_path: str | None = None,
    legacy_service: Any = None,
) -> FastAPI:
    core = core or RuntimeCore()
    if pipeline is not None:
        from cloudra.runtime_v2.agent_runner import AgentRunner

        core.runner = AgentRunner(core, pipeline)
    if store_path is not None:
        from cloudra.runtime_v2.persistence import RuntimeStore

        core.store = RuntimeStore(store_path)

        async def persist_event(envelope) -> None:
            # llm.chunk deltas are transient hub-only events: no replay value,
            # and persisting them would flood the event table.
            if envelope.type == "llm.chunk":
                return
            await asyncio.to_thread(core.store.append_event, envelope)

        core.event_hub.subscribe(persist_event)
    bus = CommandBus(core)
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker

    compute_notify = ComputeNotifyBroker(core)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await core.reminders.rearm_all()
        await core.email_listener.start()
        await compute_notify.start()
        # 计算认领只由独立守护进程（cloudra scheduler）承担，与 API 分家；
        # web 启动时无活实例会自动 detach 拉起（web_launcher）。
        try:
            yield
        finally:
            # 快照是缓存不是权威（事件表才是），但关机前补一次让下次 restore
            # 的增量尾巴尽量短；失败不阻断关停。
            await bus.flush_snapshot()
            await compute_notify.close()
            await core.email_listener.close()
            await core.reminders.close()

    app = FastAPI(title="Cloudra API v2", version=__version__, lifespan=lifespan)
    app.state.runtime_core = core
    app.state.legacy_service = legacy_service
    # Local SPA origins (browser dev/build servers) are
    # cross-origin to this runtime.  No credentials are allowed, so wildcard
    # CORS is safe for the local single-user trust model.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_token = os.getenv("CLOUDRA_API_TOKEN", "").strip()

    async def authorize(authorization: Optional[str] = Header(default=None)) -> None:
        if not api_token:
            return
        if authorization != f"Bearer {api_token}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    protected = [Depends(authorize)]

    @app.exception_handler(CommandRejected)
    async def handle_command_rejected(request: Request, exc: CommandRejected) -> JSONResponse:
        http_code = {
            "not_found": status.HTTP_404_NOT_FOUND,
            "state_conflict": status.HTTP_409_CONFLICT,
        }.get(exc.code, status.HTTP_400_BAD_REQUEST)
        return JSONResponse(
            status_code=http_code,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )

    ctx = ApiContext(core=core, bus=bus, protected=protected)
    for router in build_routers(ctx):
        app.include_router(router)

    return app


def create_default_v2_app(*, store_path: str | None = None) -> FastAPI:
    """Production wiring: legacy LLM/tool bridges + policy stages + durability."""
    from cloudra.infra.logging_setup import setup_logging
    from cloudra.persistence import paths

    # web 进程内所有 cloudra.* 日志（knowledge plugin 告警、runtime_v2 诊断等）
    # 落盘到 data_dir/logs/api.log；幂等，--factory 重建/测试多次建 app 不叠加。
    setup_logging("cloudra", log_file=paths.logs_dir() / "api.log")
    store_path = store_path or os.environ.get("CLOUDRA_RUNTIME_STORE") or None
    from cloudra.runtime_v2.adapters import (
        LegacyLLMProvider,
        LegacyPromptProvider,
        LegacyToolExecutor,
        legacy_default_runtime_settings,
    )
    from cloudra.runtime_v2.persistence import restore_core
    from cloudra.runtime_v2.plugins import attach_plugins, load_plugins_from_config
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    # 通用插件面（GraphRAG 图书馆、事件观察者等，plugins 配置声明）：
    # 加载即注册，attach 把 on_event 挂进事件总线、setup 拿到 core。
    # 失败只记日志。无自演化——核心不回写，插件自维护存储。
    load_plugins_from_config()

    core = RuntimeCore(strict_events=True)
    core.runtime_defaults = legacy_default_runtime_settings()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=LegacyLLMProvider(),
        tools=LegacyToolExecutor(core),
        prompt_provider=LegacyPromptProvider(),
        event_hub=core.event_hub,
        notices=core.notices,
    )
    app = create_v2_app(core, pipeline=pipeline, store_path=store_path)
    # Attach after the hub/store exist: setup(core) hooks get a fully wired
    # core, on_event hooks start receiving from this point (backfill events
    # from restore are intentionally not replayed to plugins).
    attach_plugins(core)
    if core.store is not None:
        restore_core(core, core.store)
    # Optional single-port browser mode: serve the built SPA from the same
    # uvicorn process.  Static mount is added last so /api/* routes win.
    serve_dir = os.environ.get("CLOUDRA_FRONTEND_SERVE_DIR", "").strip()
    if serve_dir and Path(serve_dir, "index.html").is_file():
        app.mount("/", StaticFiles(directory=serve_dir, html=True), name="frontend")
    return app
