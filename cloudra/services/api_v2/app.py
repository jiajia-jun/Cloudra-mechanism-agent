"""Thin FastAPI v2 routing over RuntimeCore + CommandBus.

This module knows HTTP concerns only.  Every write is submitted as a Command;
handlers live in runtime_v2.commands.  No business logic is allowed here.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import weakref
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from cloudra import __version__
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import CommandRejected
from cloudra.services.api_token import resolve_api_token

from .context import ApiContext
from .routers import build_routers

logger = logging.getLogger(__name__)

# 服务关闭的有界时间（停止语义契约 3）：推理/收尾任务的取消+回收总额。
_SHUTDOWN_GRACE_SECONDS = 15.0

# Host 校验白名单：本地 API 只接受回环地址与 TestClient 的 testserver；
# 其它 Host（DNS rebinding 的域名）一律 400，挡掉浏览器跨域页面重绑定访问。
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}
_LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}

# web_launcher 显式绑定的地址（uvicorn 子进程 env 传入 `cloudra web --host`）。
_BIND_HOST_ENV = "CLOUDRA_API_BIND_HOST"
# 通配绑定：客户端实际使用的名字（IP/主机名/别名）无法枚举。
_WILDCARD_BIND_HOSTS = {"0.0.0.0", "::", "*"}


def _host_allowlist() -> set[str] | None:
    """token=off 时的 Host 白名单；``None`` 表示关闭校验。

    有 token 时不走这里（只验 token）。off 时默认回环 + testserver；
    通配绑定关闭校验，具体非回环地址把该地址加进白名单。
    """
    bind_host = os.environ.get(_BIND_HOST_ENV, "").strip()
    if not bind_host or bind_host in _ALLOWED_HOSTS:
        return _ALLOWED_HOSTS
    if bind_host in _WILDCARD_BIND_HOSTS:
        return None
    return _ALLOWED_HOSTS | {bind_host}


class _HostCheckMiddleware:
    """纯 ASGI Host 校验：hostname 不在白名单 → 400（不进入路由）。

    ``allowed_hosts=None`` 关闭校验（显式绑到通配地址，见 ``_host_allowlist``）。
    """

    def __init__(self, app: Any, allowed_hosts: set[str] | None) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and self.allowed_hosts is not None:
            host = ""
            for name, value in scope.get("headers") or []:
                if name == b"host":
                    host = value.decode("latin-1").strip()
                    break
            if host.startswith("[") and "]" in host:
                hostname = host[1:host.index("]")]
            else:
                hostname = host.split(":", 1)[0]
            # IPv6 字面量在 scope 里不带方括号，白名单里两种写法都认。
            if hostname not in self.allowed_hosts and f"[{hostname}]" not in self.allowed_hosts:
                response = JSONResponse({"detail": "invalid host"}, status_code=400)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


# 请求体读取预算。ASGI 层没有 body 读超时：一个声明了 Content-Length 却慢慢发字节的连接
# 会一直挂在协议解析状态上——实测「声明 8MB、只发 20 字节」45s 内无响应、不关连接、也不
# 超时。进入应用前把 body 读完（有大小上限与时长预算），下游 receive 从缓冲重放；无 body
# 的请求（GET、SSE）完全不走这条路径，行为逐字节不变。
_BODY_READ_TIMEOUT_SECONDS = 30.0
_MAX_REQUEST_BYTES = 32 * 1024 * 1024
# 未带有效 token 时只允许缓冲这么多——避免鉴权前被 32MiB×30s 拖垮。
_MAX_UNAUTH_REQUEST_BYTES = 8 * 1024


class _BodyTooLargeError(Exception):
    """请求体超过允许上限。"""


def _request_body_declared(scope: dict) -> bool:
    """请求是否声明了 body：非零 Content-Length 或 chunked 传输。"""
    for name, value in scope.get("headers") or []:
        if name == b"content-length":
            try:
                return int(value) > 0
            except ValueError:
                return True
        if name == b"transfer-encoding" and b"chunked" in value.lower():
            return True
    return False


def _presented_api_token(scope: dict) -> str | None:
    """从 Authorization: Bearer 或 ?token= 取出调用方出示的 token（无则 None）。"""
    for name, value in scope.get("headers") or []:
        if name == b"authorization":
            raw = value.decode("latin-1")
            if raw.startswith("Bearer "):
                return raw[len("Bearer ") :]
            return None
    qs = scope.get("query_string") or b""
    for part in qs.split(b"&"):
        if part.startswith(b"token="):
            return unquote(part[len(b"token=") :].decode("latin-1"))
    return None


async def _reject_request(scope: dict, receive: Any, send: Any, status_code: int, detail: str) -> None:
    """拒绝请求并让服务器关连接（此时 body 可能还没读完）。"""
    response = JSONResponse({"detail": detail}, status_code=status_code, headers={"connection": "close"})
    await response(scope, receive, send)


class _BodyGuardMiddleware:
    """请求体大小上限与读取超时（Host 校验之后、路由/Depends 鉴权之前）。

    - 声明的 ``Content-Length`` 超限 → 413，且**不读** body；
    - 分块传输累计超限 → 413；
    - 整个 body 在 ``_BODY_READ_TIMEOUT_SECONDS`` 内没读完 → 408；
    - 配置了 API token 且请求未出示有效 token 时，缓冲上限降为
      ``_MAX_UNAUTH_REQUEST_BYTES``；声明就更大 → **401 且不读 body**
      （避免未认证客户端先吃满 32MiB 再被路由拒）。

    读到的分片按序重放给下游，与未经本中间件时语义一致。
    """

    def __init__(self, app: Any, *, expected_token: str | None = None) -> None:
        self.app = app
        self.expected_token = expected_token

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not _request_body_declared(scope):
            await self.app(scope, receive, send)
            return

        authed = self.expected_token is None
        if not authed:
            presented = _presented_api_token(scope)
            authed = presented is not None and hmac.compare_digest(presented, self.expected_token)
        max_bytes = _MAX_REQUEST_BYTES if authed else _MAX_UNAUTH_REQUEST_BYTES

        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    await _reject_request(scope, receive, send, 400, "invalid Content-Length")
                    return
                if declared > _MAX_REQUEST_BYTES:
                    await _reject_request(scope, receive, send, 413, "request body exceeds the size limit")
                    return
                if not authed and declared > _MAX_UNAUTH_REQUEST_BYTES:
                    await _reject_request(scope, receive, send, 401, "invalid token")
                    return
                break

        buffered: list[dict] = []
        total = 0
        try:
            async with asyncio.timeout(_BODY_READ_TIMEOUT_SECONDS):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        buffered.append(message)
                        break
                    total += len(message.get("body", b""))
                    if total > max_bytes:
                        raise _BodyTooLargeError
                    buffered.append(message)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await _reject_request(scope, receive, send, 408, "timed out reading the request body")
            return
        except _BodyTooLargeError:
            # 未认证路径触顶用 401（与「没 token」一致）；已认证触顶才是真超限 413。
            if authed:
                await _reject_request(scope, receive, send, 413, "request body exceeds the size limit")
            else:
                await _reject_request(scope, receive, send, 401, "invalid token")
            return

        pending = list(buffered)

        async def replay() -> dict:
            if pending:
                return pending.pop(0)
            return await receive()

        await self.app(scope, replay, send)


def _ensure_fd_limit(min_limit: int = 10240) -> None:
    """在 POSIX/macOS 上提升文件描述符软限制，防止高并发或长驻服务耗尽 fd。"""
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft < min_limit:
            target = min(min_limit, hard) if hard != resource.RLIM_INFINITY else min_limit
            if target > soft:
                resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except Exception:
        pass


def create_v2_app(
    core: RuntimeCore | None = None,
    pipeline: Any = None,
    store_path: str | None = None,
    legacy_service: Any = None,
) -> FastAPI:
    _ensure_fd_limit()
    from cloudra.services.api_token import require_token_for_bind

    require_token_for_bind(os.environ.get(_BIND_HOST_ENV, ""))
    core = core or RuntimeCore()
    if pipeline is not None:
        from cloudra.runtime_v2.agent_runner import AgentRunner

        core.runner = AgentRunner(core, pipeline)
    if store_path is not None:
        from cloudra.runtime_v2.persistence import RuntimeStore

        core.store = RuntimeStore(store_path)

    bus = CommandBus(core)
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker

    compute_notify = ComputeNotifyBroker(core)
    # Hosted benchmark batch service (GH #32)：题目跑在 live core 上，
    # 启动/停止/状态/历史 + SSE 由 routers/benchmark.py 暴露。
    from cloudra.benchmark.batch import BenchmarkService

    benchmark_service = BenchmarkService(core, bus)

    @asynccontextmanager
    async def runtime_lifespan(_app: FastAPI):
        try:
            await core.reminders.rearm_all()
            await core.email_listener.start()
            await compute_notify.start()
            if getattr(core, "task_describer", None) is not None:
                core.task_describer.start()
            # 事件驱动督导的恢复接线（Task 3 挂点，Task 4 补测试矩阵）：
            # 项目装载后扫描持久化督导待办并补通知（覆盖"落库后通知前崩溃"
            # 窗口），含 legacy_auto 待办的一次性 Coordinator 提示。只在
            # dag_guided 项目上做；standard/dag_record 不消费督导信箱。
            # auto_wake=False：只驻留信箱/pin，不 spawn、不把休眠督导或协调者
            # 打进 LLM（issue #35）。显式 resume / 在线切回 guided 才开跑。
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
                    await reconcile_supervision(core, project.id, auto_wake=False)
                except Exception:
                    logger.warning(
                        "supervision reconcile failed for project %s", project.id,
                        exc_info=True,
                    )
            yield
        finally:
            # 1) 取消并 await 所有注册推理/收尾任务（runner/finalize，含
            #    停止准入 `_accepting=False`），回收本服务拥有的 JS host——
            #    有界时间，超时记录后继续关停。benchmark 批次先优雅终止
            #    （级联取消题目 agent，不碰计算），core.aclose() 兜底。
            try:
                await benchmark_service.shutdown()
            except Exception:
                logger.exception("benchmark batch shutdown failed")
            try:
                await asyncio.wait_for(core.aclose(), timeout=_SHUTDOWN_GRACE_SECONDS)
            except asyncio.TimeoutError:
                logger.error(
                    "core.aclose() exceeded %.0fs shutdown grace; continuing teardown",
                    _SHUTDOWN_GRACE_SECONDS,
                )
            except Exception:
                logger.exception("core.aclose() failed during shutdown")
            # 2) 关闭 broker/客户端/流与持久化收尾。
            # 快照是缓存不是权威（事件表才是），但关机前补一次让下次 restore
            # 的增量尾巴尽量短；失败不阻断关停。
            try:
                await bus.flush_snapshot()
            except Exception:
                logger.exception("runtime snapshot failed during shutdown")
            for close in (compute_notify.close, core.email_listener.close, core.reminders.close):
                try:
                    await close()
                except Exception:
                    logger.exception("%s failed during shutdown", close.__qualname__)

    @asynccontextmanager
    async def lifespan(application):
        from cloudra.infra.config import get_config
        from cloudra.tools import use_tool_entries
        from cloudra.tools.mcp import MCPToolManager

        manager = MCPToolManager(get_config().mcp_servers)
        async with manager.lifespan(core.external_tools):
            with use_tool_entries(core.external_tools):
                async with runtime_lifespan(application) as state:
                    yield state

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
    # CLOUDRA_API_TOKEN=off 显式关闭认证；未设环境变量时回退到
    # data_dir/.api_token（首次启动自动生成，0600）。None 表示全放行。
    api_token = resolve_api_token()
    # 请求体上限/读取超时：Host 之后、路由 Depends 鉴权之前。传入 expected_token，
    # 未认证大 body 在缓冲前拒掉（见 _BodyGuardMiddleware）。
    app.add_middleware(_BodyGuardMiddleware, expected_token=api_token)
    # 有 token：只验 token（远程/反代/公网域名靠它，Host 不拦）。
    # token=off：回环白名单挡 DNS rebinding。
    # 最后添加的中间件最先执行：Host 校验先于 body guard / CORS / 路由。
    app.add_middleware(
        _HostCheckMiddleware,
        allowed_hosts=None if api_token is not None else _host_allowlist(),
    )

    async def authorize(
        request: Request,
        authorization: Optional[str] = Header(default=None),
        token: Optional[str] = Query(default=None),
    ) -> None:
        if api_token is None:
            # token=off 只给回环客户端。工厂路径不设 BIND_HOST 时，
            # Host: 127.0.0.1 能骗过白名单，但 ASGI client 仍是对端地址。
            client_host = request.client.host if request.client else ""
            if client_host not in _LOOPBACK_CLIENTS:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
                )
            return
        # 头和 ?token= 等价：EventSource / <img> / 下载无法带 Authorization。
        header_ok = authorization is not None and hmac.compare_digest(
            authorization, f"Bearer {api_token}"
        )
        query_ok = token is not None and hmac.compare_digest(token, api_token)
        if header_ok or query_ok:
            return
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

    ctx = ApiContext(core=core, bus=bus, protected=protected, benchmark=benchmark_service)
    for router in build_routers(ctx):
        app.include_router(router)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):  # noqa: ARG001
        response = await call_next(request)
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    return app


def create_default_v2_app(*, store_path: str | None = None) -> FastAPI:
    """Create one authoritative API runtime per durable database."""
    from cloudra.infra.flocks import try_acquire_lock
    from cloudra.persistence.paths import runtime_api_lock_path

    store_path = store_path or os.environ.get("CLOUDRA_RUNTIME_STORE") or None
    if store_path is None:
        return _build_default_v2_app(store_path=None)
    lock_path = runtime_api_lock_path(store_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = try_acquire_lock(str(lock_path))
    if fd is None:
        raise RuntimeError(
            "This runtime database is already in use by another Cloudra service. "
            "Close that service or use a different data directory."
        )
    try:
        app = _build_default_v2_app(store_path=store_path)
    except BaseException:
        os.close(fd)
        raise
    release = weakref.finalize(app, os.close, fd)
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def owned_lifespan(application):
        if not release.alive:
            raise RuntimeError("This Cloudra runtime is already closed; create a fresh application to restart.")
        try:
            async with original_lifespan(application) as state:
                yield state
        finally:
            await asyncio.to_thread(release)

    app.router.lifespan_context = owned_lifespan
    return app


def _build_default_v2_app(*, store_path: str | None) -> FastAPI:
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
