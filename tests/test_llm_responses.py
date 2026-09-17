"""Responses API 传输层测试（DeepSeek 原生联网搜索走 /responses）。

覆盖：chat.completions kwargs → Responses 请求体翻译、非流式响应翻译、
SSE 流式事件翻译（含 web_search_call 捕获与 tool_call 增量合并）、
以及 Agent 的 Responses 传输路由。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests

from cloudra.infra.llm_client import (
    _build_responses_payload,
    _responses_stream_events,
    _translate_responses_completion,
    _translate_responses_usage,
)


class _FakeResp:
    """模拟 requests.Response：按 chunk 输出 SSE 字节。"""

    def __init__(self, events: list[dict]) -> None:
        body = "".join(
            f"data: {json.dumps(event)}\n\n"
            for event in events
        )
        self._body = body.encode("utf-8")

    def iter_content(self, chunk_size: int = 1024):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]


def _kwargs(**overrides) -> dict:
    base = {
        "model": "deepseek-v4-flash",
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hi"},
        ],
        "tools": [
            {"type": "function", "function": {"name": "bash", "description": "d", "parameters": {}}}
        ],
        "extra_body": {"tools": [{"type": "web_search"}]},
    }
    base.update(overrides)
    return base


def test_build_responses_payload_translates_kwargs():
    payload = _build_responses_payload(_kwargs())
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["instructions"] == "You are helpful"
    assert payload["max_output_tokens"] == 4096
    assert payload["temperature"] == 0.7
    assert payload["stream"] is False
    assert payload["tool_choice"] == "auto"
    # function 工具 + extra_body 里的原生 web_search 工具合并（不重复 function）
    assert payload["tools"] == [
        {"type": "function", "name": "bash", "description": "d"},
        {"type": "web_search"},
    ]
    assert payload["input"] == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
    ]


def test_build_responses_payload_translates_reasoning_effort():
    """reasoning_effort 不原样透传顶层字段，翻译为 Responses 的 reasoning.effort。"""
    payload = _build_responses_payload(_kwargs(reasoning_effort="high"))
    assert payload["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in payload


def test_build_responses_payload_omits_reasoning_when_unset():
    payload = _build_responses_payload(_kwargs())
    assert "reasoning" not in payload


def test_build_responses_payload_preserves_leading_system_layers_and_serial_flag():
    """开头连续的 system 层（角色身份 + JS 协议）都进入 instructions。"""
    payload = _build_responses_payload({
        **_kwargs(),
        "messages": [
            {"role": "system", "content": "role identity"},
            {"role": "system", "content": "javascript protocol"},
            {"role": "user", "content": "user must stay input"},
        ],
        "parallel_tool_calls": False,
    })
    assert payload["instructions"] == "role identity\n\njavascript protocol"
    assert "user must stay input" not in payload["instructions"]
    assert payload["parallel_tool_calls"] is False


def test_build_responses_payload_keeps_late_system_inline_for_cache():
    """对话开始后追加的 system 快照必须留在 input 原位，不得提升到 instructions。

    DeepSeek 把 instructions 插到「第一条 system 消息」位置；提升会导致 input
    之前插入新 token，打断 append-only 前缀，使其后的整段 input 无法命中
    DeepSeek 的边界缓存单元。
    """
    payload = _build_responses_payload({
        **_kwargs(),
        "messages": [
            {"role": "system", "content": "role identity"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "system", "content": "workspace update"},
            {"role": "user", "content": "u3"},
        ],
    })
    assert payload["instructions"] == "role identity"
    roles = [item["role"] for item in payload["input"]]
    assert roles == ["user", "assistant", "user", "system", "user"]
    assert payload["input"][3]["content"] == [{"type": "input_text", "text": "workspace update"}]


def test_build_responses_payload_stays_append_only_when_system_appended():
    """前缀追加（含动态 system 快照）后，序列化输入必须以上一请求为完整前缀。"""
    base = [
        {"role": "system", "content": "role identity"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    first = _build_responses_payload(_kwargs(messages=base))
    second = _build_responses_payload(_kwargs(messages=[*base, {"role": "system", "content": "workspace update"}, {"role": "user", "content": "u3"}]))
    assert second["instructions"] == first["instructions"]
    assert second["input"][: len(first["input"])] == first["input"]


def test_build_responses_payload_roundtrips_tool_turn():
    """带 reasoning/tool_calls/tool 结果的往返消息应翻译为相邻条目。"""
    payload = _build_responses_payload(
        _kwargs(
            messages=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u"},
                {
                    "role": "assistant",
                    "content": "let me",
                    "reasoning_content": "think",
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": "bash", "arguments": "{}"}}
                    ],
                },
                {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            ]
        )
    )
    types = [item["type"] for item in payload["input"]]
    assert types == ["message", "reasoning", "message", "function_call", "function_call_output"]
    assert payload["input"][1]["content"][0]["text"] == "think"
    assert payload["input"][3]["name"] == "bash"
    assert payload["input"][4]["call_id"] == "c1"


def test_build_responses_payload_carries_image_parts():
    """visual 模式的多模态 content parts 必须翻译为 input_image，而不是被 str() 丢掉。"""
    payload = _build_responses_payload(
        _kwargs(
            messages=[
                {"role": "system", "content": "s"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what is this molecule?"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "c1",
                    "content": [
                        {"type": "text", "text": "rendered: /ws/render.png"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,REVG"}},
                    ],
                },
            ]
        )
    )
    user_item = payload["input"][0]
    assert user_item["content"] == [
        {"type": "input_text", "text": "what is this molecule?"},
        {"type": "input_image", "image_url": "data:image/png;base64,QUJD"},
    ]
    # tool 结果仍是 function_call_output：图片部分降级为文本占位，
    # output 字段必须是字符串。
    tool_item = payload["input"][1]
    assert tool_item["type"] == "function_call_output"
    assert "rendered: /ws/render.png" in tool_item["output"]
    assert "[Image attached to this tool result]" in tool_item["output"]
    assert "REVG" not in tool_item["output"]


def test_translate_responses_completion_non_stream():
    data = {
        "id": "r1",
        "status": "completed",
        "output": [
            {"type": "reasoning", "content": [{"type": "reasoning_text", "text": "think"}]},
            {"type": "message", "content": [{"type": "output_text", "text": "answer"}]},
            {"type": "function_call", "name": "bash", "arguments": "{}", "call_id": "call_1"},
            {"type": "web_search_call", "status": "completed", "action": {"query": "q1"}},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }
    completion = _translate_responses_completion(data)
    message = completion["choices"][0]["message"]
    assert message["content"] == "answer"
    assert message["reasoning_content"] == "think"
    assert message["tool_calls"][0]["function"]["name"] == "bash"
    assert completion["choices"][0]["finish_reason"] == "tool_calls"
    assert completion["_web_search"] == [{"query": "q1", "status": "completed"}]
    assert completion["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    }


def test_translate_responses_completion_stop_without_tools():
    completion = _translate_responses_completion(
        {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "hi"}]}],
            "usage": {},
        }
    )
    assert completion["choices"][0]["finish_reason"] == "stop"
    assert completion["choices"][0]["message"]["content"] == "hi"


def test_completion_message_supports_react_attribute_access():
    """reAct 直接访问 message.content / message.tool_calls，缺 key 会 AttributeError。"""
    from cloudra.infra.llm_client import ResponseDictWrapper

    completion = ResponseDictWrapper(
        _translate_responses_completion(
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "hi"}]}],
                "usage": {},
            }
        )
    )
    message = completion.choices[0].message
    assert message.content == "hi"
    assert message.tool_calls is None  # 无工具时 key 常驻且为 None
    assert hasattr(message, "reasoning_content")
    # 写上下文时 model_dump(exclude_none=True) 应剔除 None 占位 key
    block = message.model_dump(exclude_none=True)
    assert block == {"role": "assistant", "content": "hi"}
    assert "tool_calls" not in block
    assert "reasoning_content" not in block


def test_stream_chunks_support_react_delta_attribute_access():
    """每个 chunk 的 delta 必须常驻 content/reasoning_content/tool_calls，避免 AttributeError。"""
    from cloudra.infra.llm_client import ResponseDictWrapper

    events = [
        {"type": "response.output_text.delta", "delta": "A"},
        {"type": "response.reasoning_text.delta", "delta": "think"},
        {"type": "response.completed", "response": {"status": "completed", "output": [], "usage": {}}},
    ]
    holder = SimpleNamespace(web_search_log=[], usage=None)
    chunks = [
        ResponseDictWrapper(c["completion"])
        for c in _responses_stream_events(_FakeResp(events), holder)
    ]
    for chunk in chunks:
        delta = chunk.choices[0].delta
        # 这三个属性直接访问必须不抛异常
        assert delta.content is not None or delta.tool_calls is not None or delta.content is None
        _ = delta.tool_calls
        _ = delta.content
    assert chunks[0].choices[0].delta.content == "A"
    assert chunks[1].choices[0].delta.reasoning_content == "think"


def test_stream_events_translate_chunks_and_capture_web_search():
    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"type": "function_call", "name": "bash", "call_id": "call_1"},
        },
        {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '{"a":1}'},
        {"type": "response.reasoning_text.delta", "delta": "think "},
        {"type": "response.output_text.delta", "delta": "hello"},
        {"type": "response.web_search_call.completed", "action": {"query": "q1"}},
        {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "output": [{"type": "function_call", "name": "bash"}],
                "usage": {"input_tokens": 5, "output_tokens": 7},
            },
        },
    ]
    holder = SimpleNamespace(web_search_log=[], usage=None)
    gen = _responses_stream_events(_FakeResp(events), holder)
    chunks = [chunk["completion"] for chunk in gen]

    # tool_call 首帧带 id/name，后续只带 arguments 增量（避免 id 被拼接）
    tool_chunks = [
        chunk["choices"][0]["delta"]["tool_calls"][0]
        for chunk in chunks
        if chunk["choices"][0]["delta"].get("tool_calls")
    ]
    assert tool_chunks[0]["id"] == "call_1"
    assert tool_chunks[0]["function"]["name"] == "bash"
    assert tool_chunks[0]["function"]["arguments"] == ""
    assert tool_chunks[1]["function"]["arguments"] == '{"a":1}'
    assert "id" not in tool_chunks[1]

    reasoning = [c["choices"][0]["delta"]["reasoning_content"] for c in chunks if c["choices"][0]["delta"].get("reasoning_content")]
    assert reasoning == ["think "]

    content = "".join(
        c["choices"][0]["delta"]["content"]
        for c in chunks
        if c["choices"][0]["delta"].get("content")
    )
    assert content == "hello"

    assert holder.web_search_log == [("q1", "completed")]
    assert holder.usage == {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
    # 结束帧给出 tool_calls finish_reason
    assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_stream_events_incomplete_maps_to_length():
    events = [
        {"type": "response.incomplete", "response": {"status": "incomplete", "output": [], "usage": {}}}
    ]
    holder = SimpleNamespace(web_search_log=[], usage=None)
    chunks = list(_responses_stream_events(_FakeResp(events), holder))
    assert chunks[-1]["completion"]["choices"][0]["finish_reason"] == "length"


@pytest.mark.asyncio
async def test_stream_emits_web_search_status_mid_stream():
    """web_search_call 事件应在流中段逐条上抛（query 从 item.action 提取）。"""
    from cloudra.infra.llm_client import LLMClient, _StreamHandle

    client = LLMClient(api_key="k", base_url="https://api.deepseek.com", model="m")
    statuses = []
    client.on_status = lambda event, data: statuses.append((event, data))

    events = [
        {"type": "response.reasoning_text.delta", "delta": "搜 "},
        {
            "type": "response.web_search_call.completed",
            "item": {"action": {"type": "search", "query": "光子时间晶体 2026"}},
        },
        {"type": "response.reasoning_text.delta", "delta": "到了"},
        {"type": "response.completed", "response": {"status": "completed", "output": [], "usage": {}}},
    ]
    resp = _FakeResp(events)
    holder = SimpleNamespace(web_search_log=[], usage=None)
    gen = _responses_stream_events(resp, holder)

    # 句柄对假响应找不到底层 socket，abort 为 no-op（仅测事件上抛语义）。
    async for chunk in client._wrap_responses_stream((gen, holder, _StreamHandle(resp))):
        pass

    assert statuses == [("web_search", {"query": "光子时间晶体 2026"})]


@pytest.mark.asyncio
async def test_wrap_responses_stream_captures_usage_with_cache_details():
    """流式收尾必须把 usage（含 cached_tokens）落到 client.last_usage。

    回归：旧实现用 _extract_usage(holder.usage) 处理已是 usage dict 的
    holder.usage，返回 None，导致所有 Responses 调用 usage 为空、缓存命中率
    与成本遥测全 0。
    """
    from cloudra.infra.llm_client import LLMClient, _StreamHandle

    client = LLMClient(api_key="k", base_url="https://api.deepseek.com", model="m")
    events = [
        {"type": "response.output_text.delta", "delta": "hi"},
        {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "output": [],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 7,
                    "input_tokens_details": {"cached_tokens": 96},
                },
            },
        },
    ]
    resp = _FakeResp(events)
    holder = SimpleNamespace(web_search_log=[], usage=None)
    gen = _responses_stream_events(resp, holder)
    async for _ in client._wrap_responses_stream((gen, holder, _StreamHandle(resp))):
        pass

    assert client.last_usage["prompt_tokens"] == 100
    assert client.last_usage["completion_tokens"] == 7
    # Responses 细项翻译成 chat 后端的键名，telemetry 的 prompt_tokens_details
    # 解析对两个后端一致。
    assert client.last_usage["prompt_tokens_details"]["cached_tokens"] == 96


def test_translate_responses_usage():
    assert _translate_responses_usage({"usage": {"input_tokens": 3, "output_tokens": 4}}) == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }


def test_responses_usage_is_readable_by_telemetry_cache_parser():
    """Responses 的 usage 翻译成 chat 形状后，telemetry 缓存命中解析同样生效。"""
    from cloudra.services.telemetry import cached_tokens_of

    usage = _translate_responses_usage(
        {
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 50,
                "input_tokens_details": {"cached_tokens": 896},
            }
        }
    )
    assert usage["prompt_tokens_details"]["cached_tokens"] == 896
    assert cached_tokens_of(usage) == 896


@pytest.mark.asyncio
async def test_agent_routes_deepseek_native_search_to_responses(monkeypatch):
    """DeepSeek 原生搜索（默认 auto、无需 params）应走 Responses 传输；OpenRouter 走 chat。"""
    from cloudra.core.agent import Coordinator
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg.coordinator, "native_search", "auto")
    monkeypatch.setattr(cfg.coordinator, "native_search_params", {})
    monkeypatch.setattr(cfg.coordinator, "url", "https://api.deepseek.com")

    agent = Coordinator(query="t", conversation_id="c")
    assert agent._uses_responses_transport() is True

    monkeypatch.setattr(cfg.coordinator, "native_search", "openrouter")
    monkeypatch.setattr(cfg.coordinator, "url", "https://openrouter.ai/api/v1")
    agent2 = Coordinator(query="t", conversation_id="c2")
    assert agent2._uses_responses_transport() is False


def test_responses_base_url_strips_v1():
    from cloudra.infra.llm_client import _responses_base_url

    assert _responses_base_url("https://api.deepseek.com/v1") == "https://api.deepseek.com"
    assert _responses_base_url("https://api.deepseek.com/v1/") == "https://api.deepseek.com"
    assert _responses_base_url("https://api.deepseek.com") == "https://api.deepseek.com"


def _error_response(status: int, body: str):
    """模拟 requests.Response 的错误响应（非 2xx）。"""
    return SimpleNamespace(
        ok=False,
        status_code=status,
        text=body,
        url="https://api.deepseek.com/responses",
    )


@pytest.mark.asyncio
class TestResponsesHttpErrors:
    """Responses 传输的 HTTP 错误处理。

    背景：DeepSeek 对孤儿 function_call_output 返回确定性 400，旧代码
    一方面把错误 body 丢掉（日志只有 "400 Client Error" 无从诊断），
    另一方面把 requests 的 HTTPError 当瞬时错误白重试 4 次（~80 秒）。
    """

    async def test_400_not_retried_and_error_contains_body(self, monkeypatch):
        """400 是确定性客户端错误：只调用 1 次不重试，异常消息带响应 body。"""
        from cloudra.infra.llm_client import LLMClient

        client = LLMClient(api_key="k", base_url="https://api.deepseek.com", model="m")
        post = MagicMock(return_value=_error_response(
            400, '{"error": {"message": "Invalid request: orphan function_call_output"}}'
        ))
        monkeypatch.setattr("cloudra.infra.llm_client.requests.post", post)
        sleep = AsyncMock()
        monkeypatch.setattr(asyncio, "sleep", sleep)

        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            await client.create_responses_with_retry(
                model="m", messages=[{"role": "user", "content": "hi"}]
            )

        assert post.call_count == 1
        sleep.assert_not_awaited()
        assert "orphan function_call_output" in str(exc_info.value)
        assert exc_info.value.response.status_code == 400

    async def test_500_retried_until_exhausted(self, monkeypatch):
        """5xx 仍按原逻辑重试（初次 + max_retries 次）。"""
        from cloudra.infra.llm_client import LLMClient

        client = LLMClient(api_key="k", base_url="https://api.deepseek.com", model="m")
        post = MagicMock(return_value=_error_response(500, '{"error": "internal"}'))
        monkeypatch.setattr("cloudra.infra.llm_client.requests.post", post)
        sleep = AsyncMock()
        monkeypatch.setattr(asyncio, "sleep", sleep)

        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            await client.create_responses_with_retry(
                model="m", messages=[{"role": "user", "content": "hi"}]
            )

        assert post.call_count == client.max_retries + 1
        assert sleep.await_count == client.max_retries
        assert "internal" in str(exc_info.value)

    async def test_error_body_truncated(self):
        """超长错误 body 截断到 ~800 字符。"""
        from cloudra.infra.llm_client import LLMClient

        resp = _error_response(400, "x" * 5000)
        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            LLMClient._raise_for_status_with_body(resp)
        assert "x" * 800 in str(exc_info.value)
        assert "x" * 801 not in str(exc_info.value)
