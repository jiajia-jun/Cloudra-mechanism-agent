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

from cloudra.services.daemon_supervisor import ensure_daemons

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
            "Node.js >= 18 and npm are required for the Cloudra web frontend. "
            f"Frontend found at {frontend}. Install from https://nodejs.org/"
        )


def _npm_argv() -> list[str]:
    """npm as an invokable argv prefix.

    On Windows npm is a ``npm.cmd`` batch file: ``shutil.which`` finds it (it
    honours PATHEXT) but ``CreateProcess`` cannot execute ``.cmd`` scripts
    directly — ``subprocess.run(["npm", ...])`` dies with ``WinError 2`` even
    though the pre-check passed.  Route through ``cmd /c`` with the fully
    resolved path; POSIX keeps the resolved executable directly.
    """
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError(
            "npm not found on PATH; install Node.js >= 18 or run with --skip-build"
        )
    if os.name == "nt":
        return ["cmd", "/c", npm]
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
    _check_node(frontend)
    if not (frontend / "node_modules").is_dir():
        print("[cloudra] installing frontend dependencies...", flush=True)
        subprocess.run(_npm_argv() + ["install", "--no-audit", "--no-fund"], cwd=frontend, check=True)
    dist = frontend / "dist"
    if skip_build:
        if not (dist / "index.html").is_file():
            raise RuntimeError("--skip-build was requested but frontend/dist is missing")
        return
    stale = _frontend_source_newer_than_dist(frontend)
    if rebuild or not (dist / "index.html").is_file() or stale:
        if stale and not rebuild and (dist / "index.html").is_file():
            print("[cloudra] frontend source changed — rebuilding...", flush=True)
        else:
            print("[cloudra] building frontend...", flush=True)
        subprocess.run(_npm_argv() + ["run", "build"], cwd=frontend, check=True)


def _port_is_bindable(preferred: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
        except OSError:
            return False
        return True


def _runtime_is_healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v2/runtime/health", timeout=1.0
        ) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _runtime_serves_spa(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1.0) as resp:
            body = resp.read(4096).decode("utf-8", "ignore")
            return 200 <= resp.status < 300 and '<div id="root"></div>' in body
    except Exception:
        return False


def _find_api_port(preferred: int, env_name: str) -> tuple[int, bool]:
    """Return (port, reused_existing_runtime).

    A runtime is only reused when it both serves the API and the built SPA on
    the same port; otherwise we start a fresh single-port runtime on a free
    port so the frontend never points at a stale or foreign server.
    """
    env_value = os.environ.get(env_name)
    if env_value:
        port = int(env_value)
        return port, _runtime_is_healthy(port) and _runtime_serves_spa(port)
    if _port_is_bindable(preferred):
        return preferred, False
    if _runtime_is_healthy(preferred) and _runtime_serves_spa(preferred):
        return preferred, True
    for port in range(preferred + 1, preferred + 100):
        if _port_is_bindable(port):
            return port, False
    raise RuntimeError(f"no free port near {preferred}; set {env_name} explicitly")


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


def launch_browser(frontend: Path, *, rebuild: bool, skip_build: bool) -> int:
    api_port, reused_runtime = _find_api_port(8000, "CLOUDRA_API_PORT")
    _ensure_frontend(frontend, rebuild=rebuild, skip_build=skip_build)
    ensure_daemons()
    from cloudra.infra.config import get_config

    store_path = os.environ.get(
        "CLOUDRA_RUNTIME_STORE",
        str(Path(get_config().data_dir) / "runtime-v2.db"),
    )
    env = os.environ.copy()
    env["CLOUDRA_RUNTIME_STORE"] = store_path
    env["CLOUDRA_FRONTEND_SERVE_DIR"] = str(frontend / "dist")
    runtime = None
    if reused_runtime:
        print(f"[cloudra] reusing existing Cloudra runtime on port {api_port}", flush=True)
    else:
        print(f"[cloudra] starting web server on port {api_port}...", flush=True)
        runtime = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "cloudra.services.api_v2:create_default_v2_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
                "--log-level",
                "warning",
            ],
            env=env,
        )
    try:
        _wait_healthy(f"http://127.0.0.1:{api_port}/api/v2/runtime/health")
        url = f"http://127.0.0.1:{api_port}"
        print(f"[cloudra] web UI: {url}", flush=True)
        if os.environ.get("CLOUDRA_NO_BROWSER", "").strip().lower() not in {"1", "true", "yes"}:
            webbrowser.open(url)
        if runtime is None:
            return 0
        return runtime.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if runtime is not None and runtime.poll() is None:
            runtime.terminate()
