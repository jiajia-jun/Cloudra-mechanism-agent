"""Transport-layer cancellation forensics (Task 0) + Task 5 fix regression.

Local fake HTTP/SSE server only — never touches a real provider.  Latches are
``threading.Event`` gates; ``asyncio.wait_for`` / poll deadlines are failure
upper bounds, never timing dependencies.

Created 2026-09-06 (docs/superpowers/plans/2026-09-05-task0-cancellation-forensics.md);
the mid-SSE cancel cases were RED then (connection abandoned), turned green by
the Task 5 transport fixes (abortive close: SO_LINGER + socket shutdown/close
bypassing the cross-thread-blocking high-level close).

Scaffold notes (Task 5):
- The fake server records ``tail_done`` alongside ``write_failures`` so the
  assertion waits until the handler thread actually attempted its writes
  (``counts[path]`` is trivially true and raced the handler thread).
- ``_responses_head_events()`` crafts the two head SSE blocks to total exactly
  2048 bytes: ``iter_content(chunk_size=1024)`` fills each underlying read to
  1024 bytes, so both blocks must fit in the first two reads to be delivered
  pre-gate.
- The subprocess characterization case documents that the *non-streaming*
  requests worker thread survives asyncio task cancellation.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cloudra.infra.llm_client import LLMClient

_WRITE_FAILURES = (BrokenPipeError, ConnectionResetError)


def _sse_block(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _chat_chunk(text: str) -> dict:
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }


def _responses_text_delta(text: str) -> dict:
    return {"type": "response.output_text.delta", "delta": text}


def _responses_head_events() -> list[dict]:
    """两个头事件，保证消费者在门闩前恰好收到两个 chunk。

    ``_iter_sse_chunks`` 经 ``iter_content(chunk_size=1024)`` 读流，底层
    ``BufferedReader.read(1024)`` 会凑满 1024 字节才返回：要让两次读都
    在门闩前完成且第二块完整落在前 2048 字节内，两个 SSE 块合计必须恰好
    2048 字节、且第一块落在首个 1024 字节内（否则第二次读阻塞到门闩后）。
    """
    first = _responses_text_delta("h" * 900)
    first_len = len(_sse_block(first))
    assert first_len < 1024, first_len
    empty_len = len(_sse_block(_responses_text_delta("")))
    second = _responses_text_delta("w" * (2048 - first_len - empty_len))
    assert first_len + len(_sse_block(second)) == 2048
    return [first, second]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence test output
        pass

    def do_POST(self):
        server = self.server.state
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
        with server.lock:
            server.counts[self.path] += 1
            server.uas.append(self.headers.get("User-Agent", ""))
        try:
            if self.path == "/v1/chat/completions":
                self._chat_completions(server, payload)
            elif self.path == "/responses":
                self._responses(server, payload)
            else:
                self.send_error(404)
        except _WRITE_FAILURES:
            with server.lock:
                server.write_failures.append(self.path)

    def _wait_gate(self, gate):
        # Latch: blocks until the test releases it.  The timeout is only a
        # teardown backstop so a failing test cannot wedge the server thread.
        gate.wait(timeout=60)

    def _respond_status(self, status: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _chat_completions(self, server, payload):
        if server.status != 200:
            if server.gate is not None:
                self._wait_gate(server.gate)
            self._respond_status(server.status, server.status_body)
            return
        if payload.get("stream"):
            self._stream_sse(
                server,
                [_chat_chunk("hello"), _chat_chunk(" world")],
                tail=[_chat_chunk("!"), {**_chat_chunk(""), "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}],
            )
            return
        self._respond_status(
            200,
            {
                "id": "chatcmpl-fake",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    def _responses(self, server, payload):
        if payload.get("stream"):
            self._stream_sse(
                server,
                _responses_head_events(),
                tail=[
                    _responses_text_delta("!"),
                    {"type": "response.completed", "response": {"status": "completed", "output": []}},
                ],
            )
            return
        self._respond_status(
            200,
            {
                "id": "resp_fake",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    def _stream_sse(self, server, head: list[dict], tail: list[dict]):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for event in head:
            self.wfile.write(_sse_block(event))
        self.wfile.flush()
        if server.sse_gate is not None:
            self._wait_gate(server.sse_gate)
        for event in tail:
            self.wfile.write(_sse_block(event))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        with server.lock:
            server.tail_done.append(self.path)


class _FakeLLMServer:
    def __init__(self) -> None:
        self.counts: Counter = Counter()
        self.uas: list[str] = []
        self.write_failures: list[str] = []
        # 尾块全部写成功的记录：与 write_failures 一起构成"服务端写结局"，
        # 让等待方能确定服务端已经尝试过写（否则断言会跑赢 handler 线程）。
        self.tail_done: list[str] = []
        self.lock = threading.Lock()
        self.gate: threading.Event | None = None
        self.sse_gate: threading.Event | None = None
        self.status = 200
        self.status_body: dict = {}
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.daemon_threads = True
        self._httpd.state = self
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="fake-llm-server", daemon=True
        )
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def total_requests(self) -> int:
        with self.lock:
            return sum(self.counts.values())

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def fake_server():
    server = _FakeLLMServer()
    try:
        yield server
    finally:
        # Never leave a handler latched: release everything before shutdown.
        for gate in (server.gate, server.sse_gate):
            if gate is not None:
                gate.set()
        server.close()


def _client(server: _FakeLLMServer, **kwargs) -> LLMClient:
    kwargs.setdefault("timeout", 30)
    kwargs.setdefault("max_retries", 2)
    return LLMClient(api_key="test-key", base_url=server.base_url, model="fake-model", **kwargs)


async def _wait_until(predicate, timeout: float = 5.0, what: str = "condition"):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_cancel_before_request_sends_nothing(fake_server):
    """Cancelling before the first await must keep the wire untouched."""
    client = _client(fake_server)
    task = asyncio.create_task(
        client.create(messages=[{"role": "user", "content": "hi"}], stream=False)
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake_server.total_requests() == 0


@pytest.mark.asyncio
async def test_cancel_during_retry_backoff_stops_new_attempts(fake_server):
    """429 -> exponential backoff; cancelling inside the backoff sleep must
    stop any further attempt (guard: passes today, asyncio.sleep cancels)."""
    fake_server.status = 429
    # The body must not match the fallback-trigger keywords ("rate limit"
    # etc.) or create() downgrades to the requests shim before any backoff.
    fake_server.status_body = {"error": {"message": "engine overloaded, try later"}}
    client = _client(fake_server)
    task = asyncio.create_task(
        client.create_with_retry(messages=[{"role": "user", "content": "hi"}], stream=False)
    )
    await _wait_until(lambda: fake_server.total_requests() >= 1, what="first attempt")
    # The first retry sleeps >= 5s; we are deterministically inside the backoff.
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake_server.total_requests() == 1


@pytest.mark.asyncio
async def test_cancel_before_fallback_switch_blocks_level2_request(fake_server):
    """The Level-1 request is parked on a gate before its fallback-triggering
    403 is delivered.  Cancelling there must not let the Level-2 (curl UA)
    fallback request fire after the gate is released."""
    fake_server.status = 403
    fake_server.status_body = {"error": {"message": "your request was blocked by the gateway"}}
    gate = threading.Event()
    fake_server.gate = gate
    client = _client(fake_server)
    task = asyncio.create_task(
        client.create(messages=[{"role": "user", "content": "hi"}], stream=False)
    )
    await _wait_until(lambda: fake_server.total_requests() == 1, what="level-1 request parked")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    gate.set()
    # Give any (buggy) fallback path a chance to fire, then assert it did not.
    deadline = asyncio.get_running_loop().time() + 0.3
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    assert fake_server.total_requests() == 1
    assert not any("curl" in ua for ua in fake_server.uas)


@pytest.mark.asyncio
async def test_cancel_mid_sse_stream_closes_connection(fake_server):
    """Level-1 (httpx AsyncOpenAI) streaming: cancelling the consumer mid-stream
    should close the underlying connection.  RED today: the stream is abandoned
    without aclose (adapters only closes on `except Exception`), so the server
    can still write after the gate is released."""
    gate = threading.Event()
    fake_server.sse_gate = gate
    client = _client(fake_server)
    stream = await client.create(messages=[{"role": "user", "content": "hi"}], stream=True)
    received = []

    async def consume():
        async for chunk in stream:
            received.append(chunk)

    task = asyncio.create_task(consume())
    await _wait_until(lambda: len(received) >= 2, what="two head chunks")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake_server.total_requests() == 1
    gate.set()
    # 等服务端 handler 线程真正尝试过尾写（counts 永真不能当等待条件）。
    await _wait_until(
        lambda: fake_server.write_failures or fake_server.tail_done,
        timeout=3.0,
        what="server write outcome",
    )
    assert fake_server.write_failures, (
        "cancellation did not close the SSE connection: the fake server still "
        "wrote the tail chunks successfully after the consumer was cancelled"
    )


@pytest.mark.asyncio
async def test_cancel_mid_responses_stream_closes_connection(fake_server):
    """Responses-API streaming goes through asyncio.to_thread; cancelling the
    consumer leaves the worker thread blocked in iter_content.  RED today:
    the connection stays open and the orphaned thread keeps consuming once the
    gate is released."""
    gate = threading.Event()
    fake_server.sse_gate = gate
    client = _client(fake_server)
    stream = await client.create_responses(
        messages=[{"role": "user", "content": "hi"}], stream=True
    )
    received = []

    async def consume():
        async for chunk in stream:
            received.append(chunk)

    task = asyncio.create_task(consume())
    await _wait_until(lambda: len(received) >= 2, what="two head chunks")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake_server.total_requests() == 1
    gate.set()
    await _wait_until(
        lambda: fake_server.write_failures or fake_server.tail_done or len(received) > 2,
        timeout=3.0,
        what="orphaned thread consuming tail or closed connection",
    )
    assert fake_server.write_failures, (
        "cancellation did not close the responses stream: the orphaned worker "
        "thread kept consuming after the asyncio task was cancelled"
    )


_CHILD_SCRIPT = r'''
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cloudra.infra.llm_client import LLMClient

gate = threading.Event()
hits = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        hits.append(self.path)
        gate.wait(timeout=60)
        body = json.dumps({
            "id": "x", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                          "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
httpd.daemon_threads = True
threading.Thread(target=httpd.serve_forever, name="child-fake-server", daemon=True).start()
port = httpd.server_address[1]


async def main():
    client = LLMClient(
        api_key="k", base_url=f"http://127.0.0.1:{port}/v1", model="m", timeout=60
    )
    client._curl_mode = True  # force the Level-3 requests shim (run_in_executor)
    task = asyncio.create_task(
        client.create(messages=[{"role": "user", "content": "hi"}], stream=False)
    )
    deadline = asyncio.get_running_loop().time() + 10
    while not hits:
        if asyncio.get_running_loop().time() > deadline:
            print("REQUEST_NEVER_ARRIVED", flush=True)
            return
        await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
        print("TASK_NOT_CANCELLED", flush=True)
        return
    except asyncio.CancelledError:
        print("TASK_CANCELLED", flush=True)
    survivors = [
        t.name
        for t in threading.enumerate()
        if t is not threading.main_thread() and t.name != "child-fake-server"
    ]
    print("WORKER_THREADS_ALIVE:" + json.dumps(survivors), flush=True)
    gate.set()
    await asyncio.sleep(1.0)  # teardown grace for the orphaned worker
    print("DONE", flush=True)


asyncio.run(main())
'''


@pytest.mark.asyncio
async def test_requests_worker_thread_survives_task_cancellation():
    """Characterization test (documents the current limitation, expected to
    pass): cancelling the asyncio task awaiting the Level-3 requests shim does
    NOT stop the executor worker thread blocked inside requests.post.  The
    child process reports the surviving thread, then releases its own gate so
    nothing is left hanging."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _CHILD_SCRIPT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise AssertionError("child process did not finish within 60s")
    stdout = out.decode("utf-8", "replace")
    assert proc.returncode == 0, f"child exited {proc.returncode}: {err.decode()[-2000:]}"
    assert "TASK_CANCELLED" in stdout, stdout
    marker = next(
        (line for line in stdout.splitlines() if line.startswith("WORKER_THREADS_ALIVE:")),
        None,
    )
    assert marker is not None, stdout
    survivors = json.loads(marker.split(":", 1)[1])
    assert survivors, (
        "expected the requests worker thread to survive task cancellation "
        "(documented limitation); got none: " + stdout
    )
    assert "DONE" in stdout, stdout


@pytest.mark.asyncio
async def test_aclose_blocks_new_requests_and_closes_clients(fake_server):
    """aclose 后客户端不再发任何新请求（准入检查抛 CancelledError），
    缓存的 AsyncOpenAI 客户端被关闭并清空。"""
    client = _client(fake_server)
    resp = await client.create(messages=[{"role": "user", "content": "hi"}], stream=False)
    assert resp is not None
    assert fake_server.total_requests() == 1
    assert client._openai_client is not None
    await client.aclose()
    assert client._openai_client is None
    assert client._openai_client_custom is None
    with pytest.raises(asyncio.CancelledError):
        await client.create(messages=[{"role": "user", "content": "hi"}], stream=False)
    with pytest.raises(asyncio.CancelledError):
        await client.create_responses(messages=[{"role": "user", "content": "hi"}], stream=False)
    assert fake_server.total_requests() == 1


@pytest.mark.asyncio
async def test_abort_event_blocks_send_retry_and_fallback(fake_server):
    """abort_event 置位后：发送前 / retry 退避后 / fallback 切换前的准入
    检查都抛 CancelledError，且不被 fallback/retry 分类吞掉。"""
    # 发送前
    abort = asyncio.Event()
    abort.set()
    client = _client(fake_server, abort_event=abort)
    with pytest.raises(asyncio.CancelledError):
        await client.create(messages=[{"role": "user", "content": "hi"}], stream=False)
    assert fake_server.total_requests() == 0

    # retry 退避后：第一次 429 允许发出，退避期间置位 abort → 不再增发
    abort2 = asyncio.Event()
    fake_server.status = 429
    fake_server.status_body = {"error": {"message": "engine overloaded, try later"}}
    client2 = _client(fake_server, abort_event=abort2)

    async def run():
        await client2.create_with_retry(
            messages=[{"role": "user", "content": "hi"}], stream=False
        )

    task = asyncio.create_task(run())
    await _wait_until(lambda: fake_server.total_requests() == 1, what="first 429 attempt")
    abort2.set()  # during the backoff sleep
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake_server.total_requests() == 1

    # fallback 切换前：Level-1 的 403 响应被门闩压住；置位 abort 后放行，
    # 降级判定后的 Level-2/3 发送必须被准入检查拦下
    abort3 = asyncio.Event()
    gate = threading.Event()
    fake_server.gate = gate
    fake_server.status = 403
    fake_server.status_body = {"error": {"message": "your request was blocked by the gateway"}}
    client3 = _client(fake_server, abort_event=abort3)
    task = asyncio.create_task(
        client3.create(messages=[{"role": "user", "content": "hi"}], stream=False)
    )
    await _wait_until(lambda: fake_server.total_requests() == 2, what="level-1 parked")
    abort3.set()
    gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake_server.total_requests() == 2  # 429（上一段） + 本次 Level-1
    assert not any("curl" in ua for ua in fake_server.uas)
