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

from cloudra.persistence import paths
from cloudra.persistence.fs_utils import atomic_write_text


def resolve_api_token() -> str | None:
    """返回生效的 bearer token；认证显式关闭时返回 ``None``。"""
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
        return existing
    token = secrets.token_urlsafe(32)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(str(token_file), token + "\n")
    os.chmod(token_file, 0o600)
    return token
