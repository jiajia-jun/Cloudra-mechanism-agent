"""Codex OAuth transport behavior at the actual asynchronous HTTP boundary."""

import asyncio
import importlib
import json
import threading

import httpx
import openai
import pytest

from cloudra.infra.llm_client import LLMClient

CODEX_URL = "https://chatgpt.com/backend-api/codex"


def _module():
    try:
        return importlib.import_module("cloudra.infra.codex_transport")
    except ModuleNotFoundError:
        pytest.fail("Codex OAuth transport is not implemented")


def _sse(*events):
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()


def _completed(output=None, **fields):
    return {
        "type": "response.completed",
        "response": {
            "id": "resp-1",
            "status": "completed",
            "output": output,
            "usage": {
                "input_tokens": 20,
                "output_tokens": 5,
                "total_tokens": 25,
                "input_tokens_details": {"cached_tokens": 12},
            },
            **fields,
        },
    }


def _final_output(text="done"):
    return [{"type": "message", "role": "assistant", "phase": "final_answer", "content": [{"type": "output_text", "text": text}]}]


def _client(monkeypatch, handler, *, resolver=None, **kwargs):
    module = _module()
    real_client = httpx.AsyncClient

    class BoundaryClient(real_client):
        def __init__(self, **options):
            super().__init__(transport=httpx.MockTransport(handler), **options)

    monkeypatch.setattr(module.httpx, "AsyncClient", BoundaryClient)
    monkeypatch.setattr(
        module,
        "resolve_codex_credentials",
        resolver or (lambda **kwargs: {
            "access_token": "oauth-test",
            "account_id": "workspace-1",
            "residency": "eu",
        }),
    )
    return LLMClient(api_key="", base_url=CODEX_URL, model="gpt-5.4", **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["create", "create_with_retry", "create_responses", "create_responses_with_retry"])
async def test_auxiliary_non_stream_calls_use_oauth_sse_and_preserve_usage(monkeypatch, entrypoint):
    requests = []
    event = {"type": "response.output_text.delta", "delta": "{\"ok\":true}"}

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=_sse(event, _completed()), headers={"Content-Type": "text/event-stream"})

    loop_thread = threading.get_ident()
    credential_threads = []

    def credentials(**kwargs):
        credential_threads.append(threading.get_ident())
        return {"access_token": "oauth-test", "account_id": "workspace-1", "residency": "eu"}

    client = _client(monkeypatch, handler, resolver=credentials)
    try:
        result = await getattr(client, entrypoint)(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert result.choices[0].message.content == '{"ok":true}'
        assert result.choices[0].finish_reason == "stop"
        assert client.last_usage == {
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
            "prompt_tokens_details": {"cached_tokens": 12},
        }
        assert requests[0].url == f"{CODEX_URL}/responses"
        assert requests[0].headers["Authorization"] == "Bearer oauth-test"
        assert requests[0].headers["ChatGPT-Account-ID"] == "workspace-1"
        assert requests[0].headers["x-openai-internal-codex-residency"] == "eu"
        assert requests[0].headers["originator"] == "cloudra"
        assert requests[0].headers["User-Agent"].startswith("Cloudra/")
        assert json.loads(requests[0].content)["stream"] is True
        assert credential_threads[0] != loop_thread
        assert client._openai_client is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_wire_payload_preserves_roles_and_call_ids_and_filters_unsupported_fields(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=_sse(_completed(_final_output())))

    client = _client(monkeypatch, handler)
    try:
        await client.create(
            messages=[
                {"role": "system", "content": "base instructions"},
                {"role": "user", "content": [{"type": "text", "text": "question"}, {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}}]},
                {"role": "system", "content": "late observation"},
                {"role": "assistant", "content": "looking", "reasoning_content": "private past thought", "tool_calls": [{"id": "call-real", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"a"}'}}]},
                {"role": "tool", "tool_call_id": "call-real", "content": "file data"},
            ],
            tools=[{"type": "function", "function": {"name": "read_file", "description": "Read", "parameters": {"type": "object", "properties": {}}, "strict": False}}],
            reasoning_effort="high", temperature=0.1, top_p=0.9, max_tokens=2,
            max_output_tokens=4, extra_headers={"Authorization": "Bearer stolen"},
            extra_body={"store": True, "model": "wrong", "temperature": 0.5, "url": "https://evil.invalid"},
            stream=False,
        )
        payload = json.loads(requests[0].content)
        assert payload["instructions"] == "base instructions"
        assert payload["store"] is False
        assert payload["input"] == [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "question"}, {"type": "input_image", "image_url": "https://example.com/image.png"}]},
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "late observation"}]},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "looking"}]},
            {"type": "function_call", "call_id": "call-real", "name": "read_file", "arguments": '{"path":"a"}'},
            {"type": "function_call_output", "call_id": "call-real", "output": "file data"},
        ]
        assert payload["tools"][0]["strict"] is False
        assert payload["reasoning"] == {"effort": "high", "summary": "auto"}
        assert not set(payload) & {"temperature", "top_p", "max_tokens", "max_output_tokens", "url", "extra_headers", "extra_body"}
        assert requests[0].headers["Authorization"] == "Bearer oauth-test"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_done_only_tool_arguments_and_reasoning_summary_are_streamed_once(monkeypatch):
    item = {"type": "function_call", "id": "fc-1", "call_id": "call-real", "name": "read_file", "arguments": '{"path":"a"}'}
    events = [
        {"type": "response.reasoning_summary_text.delta", "delta": "checking"},
        {"type": "response.output_item.added", "output_index": 1, "item": {**item, "arguments": ""}},
        {"type": "response.output_item.done", "output_index": 1, "item": item},
        _completed(None),
    ]
    client = _client(monkeypatch, lambda request: httpx.Response(200, content=_sse(*events)))
    try:
        stream = await client.create(messages=[{"role": "user", "content": "hello"}], stream=True)
        chunks = [chunk.model_dump() async for chunk in stream]
        calls = [call for chunk in chunks for call in chunk["choices"][0]["delta"]["tool_calls"] or []]
        assert "".join(call["function"].get("arguments", "") for call in calls) == '{"path":"a"}'
        assert calls[0]["id"] == "call-real"
        assert calls[0]["function"]["name"] == "read_file"
        assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"
        assert "".join(chunk["choices"][0]["delta"]["reasoning_content"] or "" for chunk in chunks) == "checking"
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    _sse({"type": "response.output_text.delta", "delta": "unfinished"}),
    b"data: {invalid}\n\n",
    _sse({"type": "error", "message": "backend rejected"}),
    _sse({"type": "response.failed", "response": {"status": "failed", "error": {"message": "backend rejected"}}}),
])
async def test_broken_or_failed_stream_fails_loud_without_fallback(monkeypatch, data):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=data)

    client = _client(monkeypatch, handler)
    try:
        with pytest.raises(RuntimeError):
            await client.create_with_retry(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert len(requests) == 1
        assert client._curl_mode is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_incomplete_response_reports_length(monkeypatch):
    client = _client(monkeypatch, lambda request: httpx.Response(200, content=_sse(
        {"type": "response.output_text.delta", "delta": "partial"},
        {"type": "response.incomplete", "response": {"id": "resp", "status": "incomplete", "output": None}},
    )))
    try:
        result = await client.create(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert result.choices[0].message.content == "partial"
        assert result.choices[0].finish_reason == "length"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_401_refreshes_once_and_each_physical_request_is_accounted(monkeypatch):
    requests, resolves, admissions, failures, statuses = [], [], [], [], []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(401, json={"error": {"message": "expired"}})
        return httpx.Response(200, content=_sse(_completed(_final_output())))

    def credentials(**kwargs):
        resolves.append(kwargs)
        return {"access_token": "fresh" if kwargs.get("force_refresh") else "expired"}

    class Accounting:
        async def before_request(self):
            admissions.append(len(admissions))
            return admissions[-1]

        async def failed_request(self, attempt):
            failures.append(attempt)

    client = _client(monkeypatch, handler, resolver=credentials)
    client.request_accounting = Accounting()
    client.on_status = lambda event, data: statuses.append(event)
    try:
        await client.create(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert [r.headers["Authorization"] for r in requests] == ["Bearer expired", "Bearer fresh"]
        assert resolves == [{}, {"force_refresh": True, "rejected_access_token": "expired"}]
        assert admissions == [0, 1]
        assert failures == [0]
        assert "llm_retry" in statuses
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_repeated_401_never_falls_back_or_refreshes_again(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(401, json={"error": {"message": "unauthorized"}})

    client = _client(monkeypatch, handler)
    try:
        with pytest.raises(openai.AuthenticationError):
            await client.create_with_retry(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert len(requests) == 2
        assert client._openai_client is None
        assert client._curl_mode is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_abort_after_credential_resolution_prevents_request(monkeypatch):
    abort = asyncio.Event()
    requests = []

    def credentials(**kwargs):
        abort.set()
        return {"access_token": "oauth-test"}

    client = _client(monkeypatch, lambda request: requests.append(request), resolver=credentials, abort_event=abort)
    try:
        with pytest.raises(asyncio.CancelledError):
            await client.create(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert requests == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_commentary_is_not_appended_to_final_answer(monkeypatch):
    commentary = {"type": "message", "role": "assistant", "phase": "commentary", "content": []}
    final = {"type": "message", "role": "assistant", "phase": "final_answer", "content": []}
    events = [
        {"type": "response.output_item.added", "output_index": 0, "item": commentary},
        {"type": "response.output_text.delta", "output_index": 0, "delta": "I will check. "},
        {"type": "response.output_item.done", "output_index": 0, "item": {**commentary, "content": [{"type": "output_text", "text": "I will check. "}]}},
        {"type": "response.output_item.added", "output_index": 1, "item": final},
        {"type": "response.output_text.delta", "output_index": 1, "delta": "The answer is 42."},
        {"type": "response.output_item.done", "output_index": 1, "item": {**final, "content": [{"type": "output_text", "text": "The answer is 42."}]}},
        _completed(),
    ]
    client = _client(monkeypatch, lambda request: httpx.Response(200, content=_sse(*events)))
    try:
        stream = await client.create(messages=[{"role": "user", "content": "hello"}], stream=True)
        chunks = [chunk async for chunk in stream]
        assert "".join(chunk.choices[0].delta.content or "" for chunk in chunks) == "The answer is 42."
        assert chunks[-1].choices[0].finish_reason == "stop"
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    {"status": "in_progress", "output": _final_output()},
    {"status": "completed", "output": [{"type": "reasoning", "summary": [{"type": "summary_text", "text": "Thinking only"}]}]},
])
async def test_nonfinal_or_reasoning_only_terminal_cannot_report_success(monkeypatch, response):
    client = _client(monkeypatch, lambda request: httpx.Response(200, content=_sse({"type": "response.completed", "response": response})))
    try:
        with pytest.raises(RuntimeError):
            await client.create(messages=[{"role": "user", "content": "hello"}], stream=False)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_refusal_text_survives_sse_translation(monkeypatch):
    refusal = "I cannot help with that."
    item = {"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": refusal}]}
    events = [{"type": "response.refusal.delta", "output_index": 0, "delta": refusal}, {"type": "response.output_item.done", "output_index": 0, "item": item}, _completed()]
    client = _client(monkeypatch, lambda request: httpx.Response(200, content=_sse(*events)))
    try:
        result = await client.create(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert result.choices[0].message.content == refusal
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("messages,extra", [
    ([{"role": "assistant", "tool_calls": [{"type": "function", "id": "", "function": {"name": "run", "arguments": "{}"}}]}], {}),
    ([{"role": "tool", "tool_call_id": "orphan", "content": "result"}], {}),
    ([{"role": "assistant", "tool_calls": [{"type": "function", "id": "call-1", "function": {"name": "run", "arguments": "{}"}}, {"type": "function", "id": "call-1", "function": {"name": "run", "arguments": "{}"}}]}], {}),
    ([{"role": "user", "content": "hello"}], {"parallel_tool_calls": "false"}),
    ([{"role": "user", "content": "hello"}], {"tools": [{"type": "function", "function": {"name": "run", "strict": "false", "parameters": {"type": "object"}}}]}),
])
async def test_invalid_call_relationships_and_boolean_flags_fail_before_send(monkeypatch, messages, extra):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=_sse(_completed(_final_output())))

    client = _client(monkeypatch, handler)
    try:
        with pytest.raises(ValueError):
            await client.create(messages=messages, stream=False, **extra)
        assert requests == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_assistant_image_history_uses_text_placeholder(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=_sse(_completed(_final_output())))

    client = _client(monkeypatch, handler)
    try:
        await client.create(messages=[{"role": "assistant", "content": [{"type": "text", "text": "Preview"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,secret"}}]}], stream=False)
        parts = json.loads(requests[0].content)["input"][0]["content"]
        assert parts[0] == {"type": "output_text", "text": "Preview"}
        assert parts[1]["type"] == "output_text"
        assert "secret" not in json.dumps(parts)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_stream_failure_emits_transport_error_status(monkeypatch):
    statuses = []
    client = _client(monkeypatch, lambda request: httpx.Response(200, content=_sse({"type": "error", "message": "failed"})))
    client.on_status = lambda event, data: statuses.append(event)
    try:
        stream = await client.create(messages=[{"role": "user", "content": "hello"}], stream=True)
        with pytest.raises(RuntimeError):
            async for _ in stream:
                pass
        assert statuses == ["llm_error"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_rate_limit_retry_uses_same_oauth_route_and_reports_status(monkeypatch):
    requests, statuses, delays = [], [], []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(200, content=_sse(_completed(_final_output())))

    async def sleep(delay):
        delays.append(delay)

    client = _client(monkeypatch, handler, max_retries=1)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    client.on_status = lambda event, data: statuses.append(event)
    try:
        result = await client.create_with_retry(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert result.choices[0].message.content == "done"
        assert [str(request.url) for request in requests] == [f"{CODEX_URL}/responses"] * 2
        assert all(request.headers["Authorization"] == "Bearer oauth-test" for request in requests)
        assert statuses == ["llm_error", "llm_retry"]
        assert len(delays) == 1
        assert client._curl_mode is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_argument_deltas_and_complete_frames_do_not_duplicate_tool_json(monkeypatch):
    item = {"type": "function_call", "id": "fc-1", "call_id": "call-1", "name": "run", "arguments": '{"x":1}'}
    events = [
        {"type": "response.output_item.added", "output_index": 0, "item": {**item, "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '{"x":'},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '1}'},
        {"type": "response.function_call_arguments.done", "output_index": 0, "arguments": '{"x":1}'},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        _completed([item]),
    ]
    client = _client(monkeypatch, lambda request: httpx.Response(200, content=_sse(*events)))
    try:
        result = await client.create(messages=[{"role": "user", "content": "hello"}], stream=False)
        call = result.choices[0].message.tool_calls[0]
        assert call.id == "call-1"
        assert call.function.arguments == '{"x":1}'
        assert result.choices[0].finish_reason == "tool_calls"
    finally:
        await client.aclose()


class _BlockingStream(httpx.AsyncByteStream):
    def __init__(self):
        self.blocked = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        yield _sse({"type": "response.output_text.delta", "delta": "partial"})
        self.blocked.set()
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_cancelled_stream_closes_http_response_deterministically(monkeypatch):
    body = _BlockingStream()
    client = _client(monkeypatch, lambda request: httpx.Response(200, stream=body))
    try:
        stream = await client.create(messages=[{"role": "user", "content": "hello"}], stream=True)

        async def consume():
            async for _ in stream:
                pass

        task = asyncio.create_task(consume())
        await asyncio.wait_for(body.blocked.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert body.closed
        assert client._codex_transport.responses == set()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_owner_close_closes_unconsumed_stream_and_prevents_new_calls(monkeypatch):
    body = _BlockingStream()
    client = _client(monkeypatch, lambda request: httpx.Response(200, stream=body))
    stream = await client.create(messages=[{"role": "user", "content": "hello"}], stream=True)
    await client.aclose()
    assert body.closed
    with pytest.raises(asyncio.CancelledError):
        await client.create(messages=[{"role": "user", "content": "hello"}], stream=True)
    await stream.aclose()


@pytest.mark.asyncio
async def test_redirect_cannot_forward_oauth_token(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(307, headers={"Location": "https://evil.invalid/capture"})

    client = _client(monkeypatch, handler)
    try:
        with pytest.raises(openai.APIStatusError):
            await client.create(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert len(requests) == 1
        assert requests[0].url.host == "chatgpt.com"
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("base_url,want_authorization", [
    ("https://chatgpt.com.evil.invalid/backend-api/codex", "Bearer sk-generic"),
    ("https://chatgpt.com@evil.invalid/backend-api/codex", "Basic Y2hhdGdwdC5jb206"),
    ("http://chatgpt.com/backend-api/codex", "Bearer sk-generic"),
    ("https://chatgpt.com/backend-api/codex/evil", "Bearer sk-generic"),
])
async def test_similar_custom_urls_never_resolve_or_send_oauth_credentials(monkeypatch, base_url, want_authorization):
    requests = []

    def credentials(**kwargs):
        pytest.fail("Custom URLs must not load Codex OAuth credentials")

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "chat-1", "object": "chat.completion", "created": 1, "model": "model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "generic"}}],
        })

    _client(monkeypatch, handler, resolver=credentials)
    client = LLMClient(api_key="sk-generic", base_url=base_url, model="model")
    client._openai_client = openai.AsyncOpenAI(
        api_key="sk-generic", base_url=base_url, http_client=httpx.AsyncClient(), max_retries=0,
    )
    try:
        result = await client.create(messages=[{"role": "user", "content": "hello"}], stream=False)
        assert result.choices[0].message.content == "generic"
        assert requests[0].headers["Authorization"] == want_authorization
        assert requests[0].url.path.endswith("/chat/completions")
    finally:
        await client.aclose()
