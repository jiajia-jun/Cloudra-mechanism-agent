"""Web frontend launcher used by the `cloudra` command.

Keeps Node/npm knowledge out of the CLI module.  The launcher works for source
checkouts and editable installs; packaged wheels can point CLOUDRA_FRONTEND_DIR
at an unpacked frontend directory.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from cloudra.infra.flocks import is_lock_held
from cloudra.persistence.paths import runtime_api_lock_path
from cloudra.services.daemon_supervisor import ensure_daemons
from cloudra.services.runtime_ownership import (
    describe_store_conflict,
    find_store_owner,
)

# 常驻 SSE 不会自己结束（SPA 一打开就挂着 EventSource，见 frontend/src/api.ts），
# 而 uvicorn 默认（None）会**无限等待活跃连接**：`cloudra stop` 因此报「API: 已停止」
# 却关不死进程（GH #38）。给一个有界上界，超时后由 uvicorn 取消这些连接——流生成器
# 的 finally 照常退订。取值与本文件的 _terminate_runtime(grace=20) 对齐。
_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS = 20

# 默认只绑回环。`--host` 可显式改绑（局域网/SSH 远程访问场景）；绑定地址经
# CLOUDRA_API_BIND_HOST 传进 uvicorn 子进程，api_v2 的 Host 白名单据此放开
# （见 app.py::_host_allowlist）。
_DEFAULT_BIND_HOST = "127.0.0.1"
_LOOPBACK_BIND_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
_WILDCARD_BIND_HOSTS = {"0.0.0.0", "::", "*"}

logger = logging.getLogger(__name__)


def _frontend_dir() -> Path:
    override = os.environ.get("CLOUDRA_FRONTEND_DIR", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override))
    # cloudra/web_launcher.py -> cloudra/.. == repository root (source checkout)
    candidates.append(Path(__file__).resolve().parents[1] / "frontend")
    candidates.append(Path.cwd() / "frontend")
    for candidate in candidates:
        if (candidate / "package.json").is_file():
            return candidate.resolve()
    raise RuntimeError(
        "frontend directory not found; set CLOUDRA_FRONTEND_DIR to the "
        "directory containing frontend/package.json"
    )


def _check_node(frontend: Path) -> None:
    npm = shutil.which("npm")
    node = shutil.which("node")
    if npm is None or node is None:
        raise RuntimeError(
            "Node.js >= 22.12 and npm are required for the Cloudra web frontend. "
            f"Frontend found at {frontend}. Install from https://nodejs.org/"
        )


def _npm_argv() -> list[str]:
    """npm as an invokable argv prefix (fully resolved executable)."""
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError(
            "npm not found on PATH; install Node.js >= 22.12 or run with --skip-build"
        )
    return [npm]


def _frontend_source_newer_than_dist(frontend: Path) -> bool:
    dist_index = frontend / "dist" / "index.html"
    if not dist_index.is_file():
        return True
    dist_mtime = dist_index.stat().st_mtime
    for root in (frontend / "src", frontend / "public"):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.stat().st_mtime > dist_mtime:
                return True
    for name in ("index.html", "vite.config.ts", "package.json"):
        path = frontend / name
        if path.is_file() and path.stat().st_mtime > dist_mtime:
            return True
    return False


def _ensure_frontend(frontend: Path, *, rebuild: bool = False, skip_build: bool = False) -> None:
    dist = frontend / "dist"
    if skip_build:
        if not (dist / "index.html").is_file():
            raise RuntimeError("--skip-build was requested but frontend/dist is missing")
        return
    _check_node(frontend)
    if not (frontend / "node_modules").is_dir():
        print("[cloudra] installing frontend dependencies...", flush=True)
        subprocess.run(_npm_argv() + ["install", "--no-audit", "--no-fund"], cwd=frontend, check=True)
    stale = _frontend_source_newer_than_dist(frontend)
    if rebuild or not (dist / "index.html").is_file() or stale:
        if stale and not rebuild and (dist / "index.html").is_file():
            print("[cloudra] frontend source changed — rebuilding...", flush=True)
        else:
            print("[cloudra] building frontend...", flush=True)
        subprocess.run(_npm_argv() + ["run", "build"], cwd=frontend, check=True)


def _probe_host(bind_host: str) -> str:
    """本机侧探测/访问用的地址。

    通配绑定（0.0.0.0/::）在回环上同样可达，用回环探测；绑具体网卡地址时
    回环上根本没有监听，必须用该地址本身。IPv6 字面量加方括号才能拼进 URL。
    """
    if bind_host in _WILDCARD_BIND_HOSTS:
        return "127.0.0.1"
    if ":" in bind_host:
        return f"[{bind_host}]"
    return bind_host


def _is_loopback_bind(bind_host: str) -> bool:
    return bind_host in _LOOPBACK_BIND_HOSTS


def _may_reuse_runtime(bind_host: str) -> bool:
    """能否复用已在跑的实例。

    通配绑定不能：探测走回环，而回环探测分辨不出对端绑的是 127.0.0.1 还是
    0.0.0.0——复用会让 `--host 0.0.0.0` 静默失效（用户以为已对外可访问，
    实际只绑在回环上）。回环/具体地址的探测地址就是绑定地址本身，判定可信。
    """
    return bind_host not in _WILDCARD_BIND_HOSTS


def _port_is_bindable(bind_host: str, preferred: int) -> bool:
    family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((bind_host, preferred))
        except OSError:
            return False
        return True


def _find_api_port(preferred: int, bind_host: str) -> int:
    """Choose a free port; a healthy foreign runtime is still occupied."""
    for port in range(preferred, preferred + 100):
        if _port_is_bindable(bind_host, port):
            return port
    raise RuntimeError(f"no free port near {preferred}; set CLOUDRA_API_PORT explicitly")


def _owned_runtime_port(
    store_path: str, *, bind_host: str, probe_host: str, requested_port: int | None,
) -> int | None:
    """Reuse only the requested database's owner, or explain its conflict."""
    lock_path = runtime_api_lock_path(store_path)
    # 持锁者必然创建过锁文件；文件不在（含 data_dir 尚未建立）就是没人持锁，
    # 不能顺手把 data_dir 建出来。
    if not lock_path.is_file() or not is_lock_held(str(lock_path)):
        return None
    owner = find_store_owner(store_path, probe_host=probe_host)
    if (
        owner is not None and owner.port is not None
        and owner.serves_spa and _may_reuse_runtime(bind_host)
    ):
        if requested_port is not None and requested_port != owner.port:
            raise RuntimeError(
                f"Requested port {requested_port} differs from this runtime database's port {owner.port}.\n"
                + describe_store_conflict(store_path, owner)
            )
        return owner.port
    raise RuntimeError(
        describe_store_conflict(
            store_path, owner, reuse_allowed=_may_reuse_runtime(bind_host)
        )
    )


def _wait_healthy(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if 200 <= resp.status < 300:
                    return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"runtime did not become healthy at {url}")


def _terminate_runtime(runtime: subprocess.Popen, *, grace: float = 20.0) -> None:
    """SIGTERM → 有界等待 → SIGKILL 升级 → reap。

    SIGTERM 让 uvicorn 走优雅关停（lifespan 收尾：停准入 → 取消推理/收尾
    任务 → 关流/客户端 → 回收 JS host）；不许只发信号假定已回收（停止
    语义契约 6）。
    """
    if runtime.poll() is not None:
        return
    runtime.terminate()
    try:
        runtime.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        logger.warning("web runtime did not exit within %.0fs of SIGTERM; killing", grace)
    runtime.kill()
    try:
        runtime.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.error("web runtime still alive after SIGKILL")


def _primary_address() -> str | None:
    """本机对外的首选 IPv4；取不到（无默认路由）返回 ``None``。

    UDP connect 只让内核选出口网卡，不实际发包；不解析 `ifconfig` 文本。
    仅用于把「别的机器能访问的地址」打印给用户——通配绑定下控制台里的
    回环 URL 复制到另一台机器上没有意义。
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # 192.0.2.0/24 是 TEST-NET-1，永不路由到真实主机。
            sock.connect(("192.0.2.1", 1))
            return sock.getsockname()[0]
    except OSError:
        return None


def _ui_url(url_host: str, api_port: int, token: str | None) -> str:
    """访问 URL；认证开启时把 token 放 fragment 里（fragment 不进 HTTP 请求，
    前端启动时读入 sessionStorage 后从地址栏抹掉）。"""
    url = f"http://{url_host}:{api_port}"
    return f"{url}/#token={token}" if token is not None else url


def _uvicorn_argv(api_port: int, bind_host: str) -> list[str]:
    """uvicorn 子进程命令行；关停上界见 ``_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS``。"""
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "cloudra.services.api_v2:create_default_v2_app",
        "--factory",
        "--host",
        bind_host,
        "--port",
        str(api_port),
        "--timeout-graceful-shutdown",
        str(_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS),
        "--log-level",
        "warning",
    ]


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


def launch_browser(
    frontend: Path,
    *,
    rebuild: bool,
    skip_build: bool,
    host: str | None = None,
    port: int | None = None,
) -> int:
    _ensure_fd_limit()
    bind_host = (host or "").strip() or _DEFAULT_BIND_HOST
    from cloudra.services.api_token import require_token_for_bind

    require_token_for_bind(bind_host)
    probe_host = _probe_host(bind_host)
    from cloudra.persistence import paths

    store_path = str(
        Path(os.environ.get("CLOUDRA_RUNTIME_STORE") or paths.runtime_db_path()).expanduser().resolve()
    )
    requested_port = port if port is not None else (
        int(os.environ["CLOUDRA_API_PORT"]) if os.environ.get("CLOUDRA_API_PORT") else None
    )
    owned_port = _owned_runtime_port(
        store_path, bind_host=bind_host, probe_host=probe_host, requested_port=requested_port,
    )
    reused_runtime = owned_port is not None
    if owned_port is not None:
        api_port = owned_port
    elif requested_port is not None:
        if not _port_is_bindable(bind_host, requested_port):
            raise RuntimeError(f"Requested port {requested_port} is already in use by another service.")
        api_port = requested_port
    else:
        api_port = _find_api_port(8000, bind_host)
    if not _is_loopback_bind(bind_host):
        print(
            f"[cloudra] warning: binding to non-loopback address {bind_host} — the API is "
            "reachable from the network and the bearer token is the only access control",
            flush=True,
        )
    _ensure_frontend(frontend, rebuild=rebuild, skip_build=skip_build)
    # 显式启动清除 `cloudra stop` 的持久关停 marker，否则 ensure 拒绝拉起。
    from cloudra.services.daemon_supervisor import clear_daemons_shutdown

    clear_daemons_shutdown()
    ensure_daemons()
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    repo_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = f"{repo_root}:{existing_pythonpath}" if existing_pythonpath else repo_root
    env["CLOUDRA_RUNTIME_STORE"] = store_path
    env["CLOUDRA_FRONTEND_SERVE_DIR"] = str(frontend / "dist")
    # 绑定地址传给 app（Host 校验白名单据此放开；绑回环时保持原白名单）。
    env["CLOUDRA_API_BIND_HOST"] = bind_host
    runtime = None
    if reused_runtime:
        print(f"[cloudra] reusing existing Cloudra runtime on port {api_port}", flush=True)
    else:
        print(f"[cloudra] starting web server on {bind_host}:{api_port}...", flush=True)
        runtime = subprocess.Popen(
            _uvicorn_argv(api_port, bind_host),
            env=env,
            # 固定子进程 cwd：`python -m` 会把 cwd 放到 sys.path 最前面，
            # cwd 下一个无 __init__.py 的 `cloudra` 目录会把已安装包遮蔽成
            # namespace 包（__version__ 缺失、子模块却能被 editable finder
            # 加载，报 "unknown location"）。frontend 目录已校验存在且不
            # 含 cloudra 子目录，是确定无遮蔽的工作目录。
            cwd=frontend,
        )
    try:
        _wait_healthy(f"http://{probe_host}:{api_port}/api/v2/runtime/health")
        from cloudra.services.api_token import resolve_api_token

        token = resolve_api_token()
        shown_url = _ui_url(probe_host, api_port, token)
        print(f"[cloudra] web UI: {shown_url}", flush=True)
        if bind_host in _WILDCARD_BIND_HOSTS:
            # 通配绑定常常是「服务在远端、浏览器在别处」（SSH/局域网）：
            # 控制台里的回环 URL 在那台机器上打不开，把对外地址一并给出。
            reachable = _primary_address()
            if reachable:
                print(
                    f"[cloudra] reachable from other machines: "
                    f"{_ui_url(reachable, api_port, token)}",
                    flush=True,
                )
        if os.environ.get("CLOUDRA_NO_BROWSER", "").strip().lower() not in {"1", "true", "yes"}:
            webbrowser.open(shown_url)
        if runtime is None:
            return 0
        return runtime.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if runtime is not None:
            _terminate_runtime(runtime)
