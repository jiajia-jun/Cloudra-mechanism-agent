"""API 请求体上限与读取超时（``api_v2.app._BodyGuardMiddleware``）。

红队背景：ASGI/uvicorn 层没有 body 读超时——声明 ``Content-Length: 8388608`` 却只发 20
字节，连接会一直挂在协议解析状态（实测 45s 内无响应、不关连接、也不超时）；请求体也没有
全局上限（上传端点的 413 是 ``await file.read()`` **之后**才判）。

本文件钉死五件事：
- 声明的 ``Content-Length`` 超限 → 413，且**不读** body（receive 调用次数为 0）；
- 分块传输累计超限 → 413；
- 整个 body 读不完 → 408；
- 无 body 的请求（GET、``Content-Length: 0``）完全不进这条路径，行为不变；
- 正常 POST 的 body 仍完整到达路由（缓冲重放不丢字节）。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.services.api_v2 import app as api_app
from cloudra.services.api_v2 import create_v2_app

_PROBE = "/api/v2/projects"
_BIG = 64 * 1024 * 1024


def _scope(method: str, path: str, headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), *(headers or [])],
        "client": ("127.0.0.1", 51234),
        "server": ("127.0.0.1", 8000),
    }


async def _drive(app: Any, scope: dict, messages: list[dict]) -> tuple[int | None, bytes, int]:
    """直接驱动 ASGI app；``messages`` 是 receive 的脚本，末条可带 ``_sleep`` 表示阻塞。"""
    sent: list[dict] = []
    queue = list(messages)
    calls = 0

    async def receive() -> dict:
        nonlocal calls
        calls += 1
        if not queue:
            # 队列耗尽后必须给终止信号：否则应用侧会一直 await 同一片 body（挂死测试）。
            return {"type": "http.disconnect"}
        message = queue.pop(0)
        sleep = message.get("_sleep")
        if sleep:
            await asyncio.sleep(sleep)
        return {k: v for k, v in message.items() if not k.startswith("_")}

    async def send(message: dict) -> None:
        sent.append(message)

    await app(scope, receive, send)
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body, calls


def _app() -> Any:
    return create_v2_app(RuntimeCore(strict_events=True))


@pytest.mark.asyncio
async def test_bodyless_get_never_enters_the_body_guard():
    status, body, calls = await _drive(
        _app(), _scope("GET", "/api/v2/runtime/health"), [{"type": "http.disconnect"}]
    )
    assert status == 200
    assert b'"ok"' in body
    assert calls == 0, "无 body 的 GET 不该被中间件读一次"


@pytest.mark.asyncio
async def test_zero_content_length_post_is_not_buffered():
    # 判别标志是状态码：中间件介入只有 408/413 两种结果，422 说明请求原样落到应用的 body 校验。
    status, _, _ = await _drive(
        _app(),
        _scope("POST", _PROBE, [(b"content-length", b"0"), (b"content-type", b"application/json")]),
        [{"type": "http.request", "body": b"", "more_body": False}],
    )
    assert status == 422, "应落到应用的 body 校验，而不是中间件的 408/413"


@pytest.mark.asyncio
async def test_declared_oversize_body_is_rejected_without_reading():
    status, body, calls = await _drive(
        _app(),
        _scope("POST", _PROBE, [(b"content-length", str(_BIG).encode()), (b"content-type", b"application/json")]),
        [{"type": "http.request", "body": b"x", "more_body": True}],
    )
    assert status == 413
    assert calls == 0, "声明就超限时必须一字节都不读"
    assert b"size limit" in body


@pytest.mark.asyncio
async def test_chunked_body_over_limit_is_rejected(monkeypatch):
    monkeypatch.setattr(api_app, "_MAX_REQUEST_BYTES", 1024)
    chunk = {"type": "http.request", "body": b"x" * 512, "more_body": True}
    status, body, _ = await _drive(
        _app(),
        _scope("POST", _PROBE, [(b"transfer-encoding", b"chunked")]),
        [dict(chunk), dict(chunk), dict(chunk), dict(chunk)],
    )
    assert status == 413
    assert b"size limit" in body


@pytest.mark.asyncio
async def test_slow_body_read_times_out(monkeypatch):
    monkeypatch.setattr(api_app, "_BODY_READ_TIMEOUT_SECONDS", 0.1)
    status, body, _ = await _drive(
        _app(),
        _scope("POST", _PROBE, [(b"content-length", b"8388608"), (b"content-type", b"application/json")]),
        [
            {"type": "http.request", "body": b'{"name":"x"', "more_body": True},
            {"type": "http.request", "body": b"", "more_body": True, "_sleep": 1.0},
        ],
    )
    assert status == 408
    assert b"timed out" in body


@pytest.mark.asyncio
async def test_normal_post_body_reaches_the_router():
    payload = b'{"name":"audit-body-guard"}'
    status, body, _ = await _drive(
        _app(),
        _scope("POST", _PROBE, [(b"content-length", str(len(payload)).encode()), (b"content-type", b"application/json")]),
        [{"type": "http.request", "body": payload, "more_body": False}],
    )
    assert status in (200, 201), body
    assert b"audit-body-guard" in body, "缓冲重放必须把 body 完整交给路由"
