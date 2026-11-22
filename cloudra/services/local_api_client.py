"""Shared connection resolution for local/remote Cloudra API adapters."""

from __future__ import annotations

import os

import httpx

from cloudra.persistence import paths
from cloudra.services.api_token import resolve_api_token
from cloudra.services.runtime_ownership import find_store_owner

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def resolve_connection(api_url: str | None) -> tuple[str, str | None]:
    if api_url is None:
        store_path = os.environ.get("CLOUDRA_RUNTIME_STORE") or paths.runtime_db_path()
        owner = find_store_owner(store_path)
        if owner is None or owner.port is None:
            raise RuntimeError(
                "No running Cloudra API owns this runtime store. Start Cloudra or set --api-url."
            )
        return f"http://127.0.0.1:{owner.port}", resolve_api_token(create=False)

    try:
        url = httpx.URL(api_url)
    except httpx.InvalidURL:
        raise RuntimeError("Cloudra API URL must be a valid HTTP or HTTPS base URL.") from None
    if url.scheme not in {"http", "https"} or not url.host or url.userinfo or url.query or url.fragment:
        raise RuntimeError(
            "Cloudra API URL must be an HTTP or HTTPS base URL without credentials, query, or fragment."
        )
    if url.host in LOOPBACK_HOSTS:
        return str(url), resolve_api_token(create=False)
    if url.scheme != "https":
        raise RuntimeError("A remote Cloudra API URL must use HTTPS.")
    token = os.environ.get("CLOUDRA_MCP_API_TOKEN", "").strip()
    if not token or token == "off":
        raise RuntimeError("Set CLOUDRA_MCP_API_TOKEN for the configured remote Cloudra API.")
    return str(url), token
