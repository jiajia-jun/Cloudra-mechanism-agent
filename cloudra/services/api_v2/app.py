"""Thin FastAPI v2 routing over RuntimeCore + CommandBus.

This module knows HTTP concerns only.  Every write is submitted as a Command;
handlers live in runtime_v2.commands.  No business logic is allowed here.
"""

from __future__ import annotations

import asyncio
import logging
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

logger = logging.getLogger(__name__)

# 服务关闭的有界时间（停止语义契约 3）：推理/收尾任务的取消+回收总额。
_SHUTDOWN_GRACE_SECONDS = 15.0


def _daemon_watchdog_interval() -> float:
    """巡检间隔秒数（CLOUDRA_DAEMON_WATCHDOG_SECONDS，缺省 30；非法值回落缺省）。"""
    raw = os.environ.get("CLOUDRA_DAEMON_WATCHDOG_SECONDS", "").strip()
    try:
        return float(raw) if raw else 30.0
    except ValueError:
        return 30.0


async def _daemon_watchdog_loop(interval: float) -> None:
    """周期 ensure 守护进程（scheduler/kg_vec）：守护崩溃退出后由本循环重拉起。

    首轮延迟一个间隔——web_launcher 启动时已 ensure 过一次，避免重复探测。
    ensure_daemons 自身只记日志不外抛，这里的 except 是兜底中的兜底。
    """
    await asyncio.sleep(interval)
    while True:
        try:
            from cloudra.services.daemon_supervisor import ensure_daemons

            await asyncio.to_thread(ensure_daemons)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("daemon watchdog tick failed", exc_info=True)
        await asyncio.sleep(interval)


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
        # 应用启动即显式启动：清除 `cloudra stop` 留下的关停标志/marker，
        # 守护自愈与拉起从新一轮生命周期重新开始。
        from cloudra.services.daemon_supervisor import clear_daemons_shutdown

        clear_daemons_shutdown()
        await core.reminders.rearm_all()
        await core.email_listener.start()
        await compute_notify.start()
        # 事件驱动督导的恢复接线（Task 3 挂点，Task 4 补测试矩阵）：
        # 项目装载后扫描持久化督导待办并补通知（覆盖"落库后通知前崩溃"
        # 窗口），含 legacy_auto 待办的一次性 Coordinator 提示。只在
        # dag_guided 项目上做；standard/dag_record 不消费督导信箱。
        # 只安排通知——恢复路径绝不执行 LLM 之外的副作用扩展。
        from cloudra.runtime_v2.schemas import OrchestrationMode
        from cloudra.runtime_v2.supervision import reconcile_supervision

        for project in list(core.projects.values()):
            if project.settings.orchestration_mode is not OrchestrationMode.DAG_GUIDED:
                # 继承模型下项目字段只是默认值：agent 显式覆盖仍可处在
                # guided（spawn settings / settings_update 显式钉），其持久
                # 督导待办同样需要补通知。
                if not any(
                    agent.project_id == project.id
                    and agent.settings.orchestration_mode is OrchestrationMode.DAG_GUIDED
                    for agent in core.agents.values()
                ):
                    continue
            try:
                await reconcile_supervision(core, project.id)
            except Exception:
                logger.warning(
                    "supervision reconcile failed for project %s", project.id,
                    exc_info=True,
                )
        # 计算认领只由独立守护进程（cloudra scheduler）承担，与 API 分家；
        # web 启动时无活实例会自动 detach 拉起（web_launcher），之后由下面的
        # 自愈巡检兜底重拉起（CLOUDRA_DAEMON_WATCHDOG=off 关闭，测试默认关）。
        watchdog_task: asyncio.Task | None = None
        if os.environ.get("CLOUDRA_DAEMON_WATCHDOG", "").strip().lower() not in {"off", "0", "false"}:
            watchdog_task = asyncio.create_task(
                _daemon_watchdog_loop(_daemon_watchdog_interval()), name="daemon-watchdog"
            )
        try:
            yield
        finally:
            # 停止语义契约 3 的固定顺序：
            # 1) 停止新任务准入与守护自愈拉起：取消 watchdog 任务（本进程
            #    不再有 ensure 调用方）。正常关停不置全局关停标志——守护
            #    进程刻意长存，不随 API 退出；显式全停（POST
            #    /api/v2/runtime/shutdown / cloudra stop）才置标志落 marker。
            if watchdog_task is not None:
                watchdog_task.cancel()
                await asyncio.gather(watchdog_task, return_exceptions=True)
            # 2) 取消并 await 所有注册推理/收尾任务（runner/finalize，含
            #    停止准入 `_accepting=False`），回收本服务拥有的 JS host——
            #    有界时间，超时记录后继续关停。
            try:
                await asyncio.wait_for(core.aclose(), timeout=_SHUTDOWN_GRACE_SECONDS)
            except asyncio.TimeoutError:
                logger.error(
                    "core.aclose() exceeded %.0fs shutdown grace; continuing teardown",
                    _SHUTDOWN_GRACE_SECONDS,
                )
            except Exception:
                logger.exception("core.aclose() failed during shutdown")
            # 3) 关闭 broker/客户端/流与持久化收尾。
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
    stages = default_stages(core)
    executor = LegacyToolExecutor(core)
    from cloudra.runtime_v2.invocation import InvocationService

    invocations = InvocationService(
        event_writer=core.event_writer, stages=stages, tools=executor, agents=core.agents
    )
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=LegacyLLMProvider(),
        tools=executor,
        prompt_provider=LegacyPromptProvider(),
        event_hub=core.event_hub,
        notices=core.notices,
        invocations=invocations,
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
