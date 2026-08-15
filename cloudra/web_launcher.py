"""Web frontend launcher used by the `cloudra` command.

Keeps Node/npm knowledge out of the CLI module.  The launcher works for source
checkouts and editable installs; packaged wheels can point CLOUDRA_FRONTEND_DIR
at an unpacked frontend directory.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


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


def _ensure_frontend(frontend: Path, *, rebuild: bool = False, skip_build: bool = False) -> None:
    _check_node(frontend)
    if not (frontend / "node_modules").is_dir():
        print("[cloudra] installing frontend dependencies...")
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=frontend, check=True)
    if skip_build:
        if not (frontend / "dist" / "index.html").is_file():
            raise RuntimeError("--skip-build was requested but frontend/dist is missing")
        return
    if rebuild or not (frontend / "dist" / "index.html").is_file():
        print("[cloudra] building frontend...")
        subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)


def _free_port(preferred: int, env_name: str) -> int:
    env_value = os.environ.get(env_name)
    if env_value:
        return int(env_value)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
        except OSError as exc:
            raise RuntimeError(
                f"port {preferred} is unavailable; set {env_name} to a free port"
            ) from exc
        return preferred


def _ensure_electron(frontend: Path) -> None:
    """npm install can finish with a broken electron package when its
    postinstall download was interrupted.  Re-run electron's install script
    and verify the binary before launching."""
    electron_dir = frontend / "node_modules" / "electron"
    binary = electron_dir / "dist" / "electron"
    if binary.is_file() and os.access(binary, os.X_OK):
        return
    print("[cloudra] electron binary missing, repairing electron install...")
    if not (electron_dir / "install.js").is_file():
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=frontend, check=True)
    subprocess.run(["node", "install.js"], cwd=electron_dir, check=True)
    if not (binary.is_file() and os.access(binary, os.X_OK)):
        raise RuntimeError(
            "electron failed to install its binary; run: "
            f"rm -rf {electron_dir} && npm install --prefix {frontend}"
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


def launch_electron(frontend: Path, *, rebuild: bool, skip_build: bool) -> int:
    _ensure_frontend(frontend, rebuild=rebuild, skip_build=skip_build)
    _ensure_electron(frontend)
    env = os.environ.copy()
    # Electron main spawns `python3`; point it at the interpreter that is
    # running this CLI so venvs work out of the box.
    env["CLOUDRA_PYTHON"] = sys.executable
    print("[cloudra] starting Electron desktop frontend...")
    return subprocess.call(["npm", "run", "electron"], cwd=frontend, env=env)


def launch_browser(frontend: Path, *, rebuild: bool, skip_build: bool) -> int:
    _ensure_frontend(frontend, rebuild=rebuild, skip_build=skip_build)
    api_port = _free_port(8000, "CLOUDRA_API_PORT")
    web_port = _free_port(5173, "CLOUDRA_WEB_PORT")
    from cloudra.infra.config import get_config

    store_path = os.environ.get(
        "CLOUDRA_RUNTIME_STORE",
        str(Path(get_config().data_dir) / "runtime-v2.db"),
    )
    env = os.environ.copy()
    env["CLOUDRA_RUNTIME_STORE"] = store_path
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
    static = None
    try:
        _wait_healthy(f"http://127.0.0.1:{api_port}/api/v2/runtime/health")
        static = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "http.server",
                str(web_port),
                "--bind",
                "127.0.0.1",
                "--directory",
                str(frontend / "dist"),
            ]
        )
        url = f"http://127.0.0.1:{web_port}"
        print(f"[cloudra] web frontend: {url}")
        with contextlib.redirect_stderr(io.StringIO()):
            opened = webbrowser.open(url)
        if not opened:
            print(f"[cloudra] open {url} manually")
        return runtime.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        for proc in (static, runtime):
            if proc is not None and proc.poll() is None:
                proc.terminate()
