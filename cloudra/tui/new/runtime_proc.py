"""本机 TUI 配套的 Agent runtime（FastAPI）进程管理。

默认拓扑：
- runtime：``cloudra.services.api``，跑 SessionRunner / Coordinator
- TUI：只负责渲染与控制命令，经 ``CLOUDRA_TUI_RUNTIME_URL`` 访问 runtime

``CLOUDRA_TUI_INLINE=1`` 时不拉起 runtime（与旧版同进程）。
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


def runtime_url_path(data_dir: Path) -> Path:
    return data_dir / "runtime.url"


def runtime_pid_path(data_dir: Path) -> Path:
    return data_dir / "runtime.pid"


def runtime_log_path(data_dir: Path) -> Path:
    return data_dir / "runtime.log"


def inline_mode() -> bool:
    return os.environ.get("CLOUDRA_TUI_INLINE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def configured_runtime_url() -> Optional[str]:
    raw = (os.environ.get("CLOUDRA_TUI_RUNTIME_URL") or "").strip()
    return raw or None


def _pick_port() -> int:
    raw = (os.environ.get("CLOUDRA_TUI_RUNTIME_PORT") or "").strip()
    if raw:
        return int(raw)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def health_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/health"


def is_runtime_healthy(base_url: str, *, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(health_url(base_url), timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def wait_runtime_healthy(base_url: str, *, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_runtime_healthy(base_url):
            return True
        time.sleep(0.2)
    return False


def write_runtime_meta(data_dir: Path, *, url: str, pid: int) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    runtime_url_path(data_dir).write_text(url + "\n", encoding="utf-8")
    runtime_pid_path(data_dir).write_text(f"{pid}\n", encoding="utf-8")


def read_runtime_pid(data_dir: Path) -> Optional[int]:
    path = runtime_pid_path(data_dir)
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text.split()[0])
    except (OSError, ValueError, IndexError):
        return None


def clear_runtime_meta(data_dir: Path) -> None:
    for path in (runtime_url_path(data_dir), runtime_pid_path(data_dir)):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def spawn_runtime(data_dir: Path, *, port: Optional[int] = None) -> tuple[subprocess.Popen, str]:
    """拉起本机 API runtime；返回 (proc, base_url)。"""
    port = _pick_port() if port is None else port
    base_url = f"http://127.0.0.1:{port}"
    log_path = runtime_log_path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "ab", buffering=0)  # noqa: SIM115 — 交给子进程继承
    env = os.environ.copy()
    env["CLOUDRA_API_HOST"] = "127.0.0.1"
    env["CLOUDRA_API_PORT"] = str(port)
    # 本机 TUI 信任面：不强制 token
    env.pop("CLOUDRA_API_TOKEN", None)
    bootstrap = (
        "import uvicorn\n"
        f"uvicorn.run('cloudra.services.api:create_app', host='127.0.0.1', "
        f"port={port}, factory=True, log_level='warning')\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", bootstrap],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        log_file.close()
    except OSError:
        pass
    write_runtime_meta(data_dir, url=base_url, pid=proc.pid)
    return proc, base_url


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, OSError):
            return
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass


def stop_runtime(proc: Optional[subprocess.Popen], data_dir: Optional[Path] = None) -> None:
    """结束本机拉起的 runtime。``pid==0`` 表示外部复用，不杀。"""
    if proc is not None and proc.poll() is None:
        _kill_pid(proc.pid)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
    elif data_dir is not None:
        pid = read_runtime_pid(data_dir)
        if pid is not None and pid > 0:
            _kill_pid(pid)
    if data_dir is not None:
        clear_runtime_meta(data_dir)


def ensure_local_runtime(data_dir: Path) -> tuple[Optional[subprocess.Popen], str]:
    """保证有可用的本机 runtime。

    返回 ``(owned_proc_or_None, base_url)``。若环境变量已指向健康实例，则不拉起新进程。
    """
    existing = configured_runtime_url()
    if existing and is_runtime_healthy(existing):
        write_runtime_meta(data_dir, url=existing.rstrip("/"), pid=0)
        return None, existing.rstrip("/")

    url_file = runtime_url_path(data_dir)
    if url_file.is_file():
        try:
            cached = url_file.read_text(encoding="utf-8").strip()
        except OSError:
            cached = ""
        if cached and is_runtime_healthy(cached):
            return None, cached.rstrip("/")

    proc, base_url = spawn_runtime(data_dir)
    if not wait_runtime_healthy(base_url, timeout_s=_env_float("CLOUDRA_TUI_RUNTIME_BOOT_S", 30.0)):
        stop_runtime(proc, data_dir)
        raise RuntimeError(
            f"本机 Agent runtime 未能在时限内就绪（{base_url}）。"
            f"详见 {runtime_log_path(data_dir)}"
        )
    return proc, base_url


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default
