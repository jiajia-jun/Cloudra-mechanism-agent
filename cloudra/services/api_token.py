"""本地 API bearer token 的统一解析（服务端与进程内 HTTP 调用方共用）。

解析顺序：
1. ``CLOUDRA_API_TOKEN`` 环境变量非空且不等于 ``off`` → 用它；
2. ``CLOUDRA_API_TOKEN=off`` → 显式关闭认证（测试/CI），返回 ``None``；
3. 否则读 ``data_dir/.api_token``：不存在（或 strip 后为空）则生成
   ``secrets.token_urlsafe(32)`` 并原子写入 + chmod 0600，之后复用。
"""

from __future__ import annotations

import os
import secrets
import stat

from cloudra.persistence import paths
from cloudra.persistence.fs_utils import atomic_write_text


def _ensure_private_mode(path) -> None:
    """Keep ``.api_token`` at 0600; repair a world-readable leftover in place."""
    try:
        current = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return
    if current != 0o600:
        os.chmod(path, 0o600)


def resolve_api_token(*, create: bool = True) -> str | None:
    """读取 bearer token；服务端可创建，客户端用 create=False 只读。"""
    env = os.environ.get("CLOUDRA_API_TOKEN", "").strip()
    if env == "off":
        return None
    if env:
        return env
    token_file = paths.api_token_path()
    try:
        existing = token_file.read_text(encoding="utf-8").strip()
    except OSError:
        existing = ""
    if existing:
        if create:
            _ensure_private_mode(token_file)
        return existing
    if not create:
        return None
    token = secrets.token_urlsafe(32)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(str(token_file), token + "\n", mode=0o600)
    os.chmod(token_file, 0o600)
    return token


_LOOPBACK_BIND_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", ""}


def require_token_for_bind(bind_host: str | None = None) -> str | None:
    """Refuse ``CLOUDRA_API_TOKEN=off`` on a non-loopback bind.

    Loopback (and unset bind, which defaults to loopback) may disable auth
    for tests/CI.  A LAN or wildcard bind with auth off is an open API.
    """
    token = resolve_api_token()
    host = (bind_host or "").strip()
    if token is None and host not in _LOOPBACK_BIND_HOSTS:
        raise RuntimeError(
            "CLOUDRA_API_TOKEN=off is only allowed on loopback binds; "
            f"refusing to serve on {host}"
        )
    return token
