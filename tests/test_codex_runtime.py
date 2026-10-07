"""Codex acceptance through the real runtime and auxiliary adapters."""

import json
from types import SimpleNamespace

import httpx
import pytest

from cloudra.infra import codex_transport
from cloudra.infra.config import get_config
from cloudra.infra.providers import apply_provider_preset
from cloudra.runtime_v2.adapters import LegacyLLMProvider
from cloudra.runtime_v2.compaction import summarize_with_agent_settings
from cloudra.runtime_v2.schemas import RuntimeSettings


def _response(output):
    event = {"type": "response.completed", "response": {
        "id": "response-runtime", "status": "completed", "output": output,
        "usage": {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
    }}
    return httpx.Response(200, content=f"data: {json.dumps(event)}\n\n".encode(),
                          headers={"Content-Type": "text/event-stream"})


def _install(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(codex_transport.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    monkeypatch.setattr(codex_transport, "resolve_codex_credentials", lambda **kwargs: {
        "access_token": "test-oauth-access", "account_id": "test-account",
    })
    apply_provider_preset(get_config().coordinator, "codex", overwrite_model=True)
    return SimpleNamespace(
        id="agent-codex", project_id="project-codex", role_id="coordinator",
        settings=RuntimeSettings(invocation_protocol="javascript"), current_run=None,
    )


@pytest.mark.asyncio
async def test_codex_runtime_tool_roundtrip_uses_oauth_without_api_key(monkeypatch):
    requests = []

    def handler(request):
        assert request.url == "https://chatgpt.com/backend-api/codex/responses"
        assert request.headers["Authorization"] == "Bearer test-oauth-access"
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return _response([{
                "type": "function_call", "call_id": "call-runtime", "name": "js_exec",
                "arguments": '{"code":"text(await tools.echo({text: \'hello\'}))"}',
            }])
        return _response([{"type": "message", "role": "assistant", "phase": "final_answer",
                           "content": [{"type": "output_text", "text": "Received tool result"}]}])

    agent = _install(monkeypatch, handler)
    messages = [{"role": "system", "content": "Cloudra protocol"}, {"role": "user", "content": "Use echo"}]
    provider = LegacyLLMProvider()
    first = await provider.complete(agent, messages, ["echo", "stop"])
    assert first.finish_reason == "tool_calls"
    assert first.tool_calls[0].id == "call-runtime"
    assert first.tool_calls[0].name == "js_exec"
    messages.extend([
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": first.tool_calls[0].id, "name": first.tool_calls[0].name,
            "arguments": first.tool_calls[0].arguments,
        }]},
        {"role": "tool", "tool_call_id": "call-runtime", "content": "hello"},
    ])
    second = await provider.complete(agent, messages, ["echo", "stop"])
    assert second.content == "Received tool result"
    assert second.usage["total_tokens"] == 60
    assert requests[0]["parallel_tool_calls"] is False
    assert requests[0]["instructions"] == "Cloudra protocol"
    assert requests[1]["input"][-1] == {
        "type": "function_call_output", "call_id": "call-runtime", "output": "hello",
    }


@pytest.mark.asyncio
async def test_codex_compaction_uses_same_oauth_with_nonstream_caller(monkeypatch):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return _response([{"type": "message", "role": "assistant", "phase": "final_answer",
                           "content": [{"type": "output_text", "text": "Preserved research context"}]}])

    agent = _install(monkeypatch, handler)
    result = await summarize_with_agent_settings(agent, [
        {"role": "system", "content": "Summarize the context"},
        {"role": "user", "content": "Existing mechanism evidence"},
    ])
    assert result == "Preserved research context"
    assert requests[0]["stream"] is True
    assert requests[0]["store"] is False
    assert "temperature" not in requests[0]
