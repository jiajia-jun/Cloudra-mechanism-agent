"""cloudra/llm_client.py LLM 传输层行为固定测试：

- ResponseDictWrapper：dict 响应的属性访问包装
- LLMClient._stream_response：手写 SSE 解析器（多行 data 拼接、[DONE]、非 data 行）
- LLMClient.create：三级 fallback（默认请求头 → 自定义 UA → requests shim），带级别记忆
- is_fallback_trigger：触发关键词列表（大小写不敏感 + 词边界）
- LLMClient.create_with_retry：瞬时错误的指数退避重试（唯一的重试层）
- Agent.llm_call / _llm_call_once：请求参数组装与向 LLMClient 的委托

全部在边界处 mock（AsyncOpenAI client / requests），禁止真实网络。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest

from cloudra.agent import Follower
from cloudra.llm_client import (
    FALLBACK_USER_AGENT,
    LLMClient,
    ResponseDictWrapper,
    is_fallback_trigger,
    serialize_openai_payload,
)


def _make_client():
    return LLMClient(api_key="sk-test", base_url="https://example.invalid/v1")


def _make_agent():
    """构造一个最小 Follower：工具缓存置空、context_manager 换成 mock，
    使 _llm_call_once 不触碰工具注册表与上下文文件。"""
    agent = Follower(
        id="a-llm",
        name="tester",
        prompt="测试",
        query="测试问题",
        conversation_id="test-llm",
    )
    agent._tools_schema_cache = []
    cm = MagicMock()
    cm.build_messages = AsyncMock(return_value=[{"role": "user", "content": "你好"}])
    agent.context_manager = cm
    return agent


@pytest.fixture
def client():
    return _make_client()


@pytest.fixture
def agent():
    return _make_agent()


def _mock_client(create):
    """构造一个假的 AsyncOpenAI client，仅 chat.completions.create 可用。"""
    client = MagicMock()
    client.chat.completions.create = create
    return client


class TestNoConfigConstruction:
    def test_construct_without_global_config(self, monkeypatch):
        # llm_client 不读全局配置：get_config 被禁用时仍可正常构造
        import cloudra.config

        monkeypatch.setattr(
            cloudra.config, "get_config",
            MagicMock(side_effect=RuntimeError("config 不可用")),
        )
        client = LLMClient(api_key="sk-x", base_url="https://example.invalid/v1", model="m")
        assert client.api_key == "sk-x"
        assert client.model == "m"

    def test_construction_does_no_io(self):
        # 构造不做任何 I/O：OpenAI 客户端按需惰性创建
        client = _make_client()
        assert client._openai_client is None
        assert client._openai_client_custom is None


class TestResponseDictWrapper:
    def test_nested_attribute_access(self):
        w = ResponseDictWrapper({"choices": [{"message": {"content": "hi"}}]})
        assert w.choices[0].message.content == "hi"
        assert isinstance(w.choices[0], ResponseDictWrapper)
        assert isinstance(w.choices[0].message, ResponseDictWrapper)

    def test_scalar_values_pass_through(self):
        w = ResponseDictWrapper({"id": "chat-1", "created": 123, "usage": None})
        assert w.id == "chat-1"
        assert w.created == 123
        assert w.usage is None

    def test_model_dump_returns_raw_data(self):
        data = {"a": 1, "b": {"c": 2}}
        w = ResponseDictWrapper(data)
        assert w.model_dump() is data

    def test_missing_key_raises_attribute_error(self):
        w = ResponseDictWrapper({"a": 1})
        with pytest.raises(AttributeError):
            _ = w.nonexistent

    def test_non_dict_data_raises_attribute_error(self):
        # 顶层不是 dict 时，任何属性访问都抛 AttributeError（TypeError 被转换）
        w = ResponseDictWrapper([1, 2, 3])
        with pytest.raises(AttributeError):
            _ = w.anything

    def test_repr_contains_data(self):
        w = ResponseDictWrapper({"a": 1})
        assert "'a': 1" in repr(w)

    def test_data_key_shadowed_by_method(self):
        # 固定现状：与类方法同名的 key（如 model_dump）无法通过属性访问取到，
        # 属性查找优先命中类方法本身。
        w = ResponseDictWrapper({"model_dump": 1})
        assert callable(w.model_dump)
        assert w.model_dump() == {"model_dump": 1}


class _FakeSSEResp:
    """模拟 requests 的流式响应：iter_content 返回字节块。"""

    def __init__(self, chunks):
        self._chunks = chunks

    def iter_content(self, chunk_size=1024):
        return iter(self._chunks)


class TestStreamResponseParser:
    def test_single_event(self, client):
        resp = _FakeSSEResp([b'data: {"a": 1}\n\n'])
        chunks = list(client._stream_response(resp))
        assert len(chunks) == 1
        assert chunks[0].a == 1
        assert isinstance(chunks[0], ResponseDictWrapper)

    def test_events_split_across_chunks(self, client):
        # 事件被 arbitrarily 拆到多个字节块中（甚至跨 token 边界），应能正确重组
        resp = _FakeSSEResp([
            b'data: {"a"',
            b'',
            b': 1}\n\nda',
            b'ta: {"b": 2}\n\ndata: [DONE]\n\n',
        ])
        chunks = list(client._stream_response(resp))
        assert [c.model_dump() for c in chunks] == [{"a": 1}, {"b": 2}]

    def test_done_marker_skipped(self, client):
        resp = _FakeSSEResp([b'data: [DONE]\n\n'])
        assert list(client._stream_response(resp)) == []

    def test_non_data_lines_ignored(self, client):
        # event:/注释行不影响 data 行解析；没有 data 行的 block 不产生 chunk
        resp = _FakeSSEResp([
            b'event: message\ndata: {"x": 1}\n\n',
            b': this is a comment\n\n',
            b'event: ping\n\n',
        ])
        chunks = list(client._stream_response(resp))
        assert len(chunks) == 1
        assert chunks[0].x == 1

    def test_invalid_json_skipped(self, client):
        resp = _FakeSSEResp([b'data: {not json}\n\ndata: {"ok": true}\n\n'])
        chunks = list(client._stream_response(resp))
        assert len(chunks) == 1
        assert chunks[0].ok is True

    def test_multiline_data_concatenated(self, client):
        # 修复后行为（原怪癖：只取第一行 data:）：
        # 标准 SSE 要求把同一 block 内多行 data: 用 \n 拼接后再解析
        resp = _FakeSSEResp([b'data: {"a":\ndata: 1}\n\n'])
        chunks = list(client._stream_response(resp))
        assert [c.model_dump() for c in chunks] == [{"a": 1}]

    def test_multiline_data_two_payloads_become_invalid(self, client):
        # 拼接推论：两个完整 JSON 分占两行时，拼接结果不是合法 JSON，按坏事件跳过
        resp = _FakeSSEResp([b'data: {"a": 1}\ndata: {"b": 2}\n\ndata: {"c": 3}\n\n'])
        chunks = list(client._stream_response(resp))
        assert [c.model_dump() for c in chunks] == [{"c": 3}]

    def test_unterminated_event_dropped(self, client):
        # 固定现状：流结束时 buffer 中没有 \n\n 结尾的残余数据直接丢弃
        resp = _FakeSSEResp([b'data: {"a": 1}\n\n', b'data: {"b": 2}\n'])
        chunks = list(client._stream_response(resp))
        assert [c.model_dump() for c in chunks] == [{"a": 1}]


class TestSerializePayload:
    def test_pydantic_objects_serialized(self):
        from pydantic import BaseModel

        class _Msg(BaseModel):
            role: str
            content: str

        payload = serialize_openai_payload({
            "model": "m",
            "messages": [_Msg(role="user", content="hi")],
            "nested": {"items": [_Msg(role="system", content="s")]},
        })
        assert payload == {
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "nested": {"items": [{"role": "system", "content": "s"}]},
        }

    def test_plain_values_pass_through(self):
        payload = serialize_openai_payload({"model": "m", "temperature": 0.7, "stream": True})
        assert payload == {"model": "m", "temperature": 0.7, "stream": True}


class _FakeHttpResp:
    """模拟 requests 的非流式/流式响应。"""

    def __init__(self, data=None, chunks=None):
        self._data = data or {}
        self._chunks = chunks or []

    def raise_for_status(self):
        pass

    def json(self):
        return self._data

    def iter_content(self, chunk_size=1024):
        return iter(self._chunks)


class TestRequestsShim:
    def test_non_stream_returns_wrapped_dict(self, client, monkeypatch):
        post = MagicMock(return_value=_FakeHttpResp(data={"choices": []}))
        monkeypatch.setattr("cloudra.llm_client.requests.post", post)

        result = client._chat_completions_via_requests_sync({"model": "m", "stream": False})

        assert isinstance(result, ResponseDictWrapper)
        assert result.model_dump() == {"choices": []}
        call = post.call_args
        assert call.args[0] == f"{client.base_url.rstrip('/')}/chat/completions"
        assert call.kwargs["headers"]["Authorization"] == f"Bearer {client.api_key}"
        assert call.kwargs["headers"]["User-Agent"] == "curl/7.68.0"
        assert call.kwargs["json"]["stream"] is False

    def test_stream_returns_sse_chunk_generator(self, client, monkeypatch):
        resp = _FakeHttpResp(chunks=[b'data: {"a": 1}\n\ndata: [DONE]\n\n'])
        monkeypatch.setattr("cloudra.llm_client.requests.post", MagicMock(return_value=resp))

        result = client._chat_completions_via_requests_sync({"model": "m", "stream": True})
        chunks = list(result)
        assert len(chunks) == 1
        assert chunks[0].a == 1

    def test_stream_connection_reset_degrades_to_non_stream(self, client, monkeypatch):
        # 固定行为：流式连接被重置后，自动以 stream=False 重发；
        # 此时直接返回非流式的 ResponseDictWrapper（并非单 chunk 流）
        import requests as real_requests

        ok_resp = _FakeHttpResp(data={
            "choices": [{"message": {"content": "降级回复"}}],
        })
        post = MagicMock(side_effect=[real_requests.exceptions.ConnectionError("reset"), ok_resp])
        monkeypatch.setattr("cloudra.llm_client.requests.post", post)

        result = client._chat_completions_via_requests_sync({"model": "m", "stream": True})

        assert post.call_count == 2
        # 第二次请求必须是非流式
        assert post.call_args_list[1].kwargs["json"]["stream"] is False
        assert isinstance(result, ResponseDictWrapper)
        assert result.choices[0].message.content == "降级回复"

    @pytest.mark.asyncio
    async def test_async_wrapper_runs_in_executor(self, client, monkeypatch):
        post = MagicMock(return_value=_FakeHttpResp(data={"ok": True}))
        monkeypatch.setattr("cloudra.llm_client.requests.post", post)
        result = await client._chat_completions_via_requests(model="m", stream=False)
        assert isinstance(result, ResponseDictWrapper)
        assert result.ok is True


class TestFallbackTrigger:
    @pytest.mark.parametrize("msg", [
        "Error code: 403 - your request was blocked",
        "BLOCKED by gateway",
        "access denied",
        "403 Forbidden",
        # 修复后行为：原关键词是 " forbidden"（带前导空格），
        # 消息恰好为 "Forbidden"/"forbidden"（无空格）时不触发；
        # 现在大小写不敏感 + 词边界匹配，独立出现的 forbidden 即触发。
        "Forbidden",
        "forbidden",
        "Too Many Requests",
        "Rate limit exceeded",
        "blocked by Cloudflare",
        "502 Bad Gateway",
        "Connection reset by peer",
    ])
    def test_trigger_keywords(self, msg):
        assert is_fallback_trigger(Exception(msg)) is True

    @pytest.mark.parametrize("msg", [
        "invalid api key",
        "model not found",
        "context length exceeded",
        "Request timed out",
        # 词边界匹配：unblocked 里的 blocked 不是独立单词，不应误触发
        "unblocked by admin",
    ])
    def test_non_trigger_messages(self, msg):
        assert is_fallback_trigger(Exception(msg)) is False


@pytest.mark.asyncio
class TestCreateFallbackChain:
    async def test_normal_path_passthrough_kwargs(self, client):
        create = AsyncMock(return_value="RESP")
        client._openai_client = _mock_client(create)

        assert await client.create(model="m", messages=[{"role": "user", "content": "hi"}]) == "RESP"

        kwargs = create.call_args.kwargs
        assert kwargs["model"] == "m"
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
        # 未发生任何降级
        assert client._use_custom_headers is False
        assert client._curl_mode is False

    async def test_model_default_from_constructor(self):
        client = LLMClient(api_key="sk-test", base_url="https://example.invalid/v1", model="m-default")
        create = AsyncMock(return_value="RESP")
        client._openai_client = _mock_client(create)
        await client.create(messages=[])
        assert create.call_args.kwargs["model"] == "m-default"

    async def test_custom_ua_header_used_by_level2(self, client):
        # 二级 fallback 客户端必须带 curl UA（中转站按 UA 拦截官方客户端）
        assert FALLBACK_USER_AGENT == "curl/7.68.0"
        custom = client._openai_client_with_custom_headers()
        assert custom is client._openai_client_with_custom_headers()  # 实例级缓存

    async def test_trigger_falls_back_to_custom_headers(self, client):
        create1 = AsyncMock(side_effect=Exception("Error code: 403 - your request was blocked"))
        create2 = AsyncMock(return_value="LEVEL2_OK")
        client._openai_client = _mock_client(create1)
        client._openai_client_custom = _mock_client(create2)

        assert await client.create(model="m") == "LEVEL2_OK"
        create1.assert_awaited_once()
        create2.assert_awaited_once()
        # 实例记住第二级，后续调用优先使用
        assert client._use_custom_headers is True
        assert client._curl_mode is False

    async def test_trigger_twice_falls_back_to_requests(self, client, monkeypatch):
        create1 = AsyncMock(side_effect=Exception("Connection reset by peer"))
        create2 = AsyncMock(side_effect=Exception("Too Many Requests"))
        client._openai_client = _mock_client(create1)
        client._openai_client_custom = _mock_client(create2)
        via_requests = AsyncMock(return_value="REQUESTS_OK")
        monkeypatch.setattr(LLMClient, "_chat_completions_via_requests", via_requests)

        assert await client.create(model="m") == "REQUESTS_OK"
        assert client._use_custom_headers is True
        assert client._curl_mode is True
        via_requests.assert_awaited_once()

    async def test_remembered_custom_headers_skips_level1(self, client):
        client._use_custom_headers = True
        create1 = AsyncMock(return_value="LEVEL1")
        create2 = AsyncMock(return_value="LEVEL2_OK")
        client._openai_client = _mock_client(create1)
        client._openai_client_custom = _mock_client(create2)

        assert await client.create(model="m") == "LEVEL2_OK"
        create1.assert_not_awaited()
        create2.assert_awaited_once()

    async def test_remembered_curl_mode_goes_straight_to_requests(self, client, monkeypatch):
        client._curl_mode = True
        create1 = AsyncMock(return_value="LEVEL1")
        client._openai_client = _mock_client(create1)
        via_requests = AsyncMock(return_value="REQUESTS_OK")
        monkeypatch.setattr(LLMClient, "_chat_completions_via_requests", via_requests)

        assert await client.create(model="m") == "REQUESTS_OK"
        create1.assert_not_awaited()
        via_requests.assert_awaited_once()

    async def test_remembered_custom_headers_still_triggerable_to_requests(self, client, monkeypatch):
        # 已记住第二级时再次被拦截：从第二级直接降到 requests
        client._use_custom_headers = True
        create2 = AsyncMock(side_effect=Exception("blocked by Cloudflare"))
        client._openai_client_custom = _mock_client(create2)
        via_requests = AsyncMock(return_value="REQUESTS_OK")
        monkeypatch.setattr(LLMClient, "_chat_completions_via_requests", via_requests)

        assert await client.create(model="m") == "REQUESTS_OK"
        assert client._curl_mode is True

    async def test_non_trigger_error_propagates(self, client):
        create1 = AsyncMock(side_effect=Exception("invalid api key"))
        create2 = AsyncMock(return_value="LEVEL2")
        client._openai_client = _mock_client(create1)
        client._openai_client_custom = _mock_client(create2)

        with pytest.raises(Exception, match="invalid api key"):
            await client.create(model="m")
        create2.assert_not_awaited()
        assert client._use_custom_headers is False
        assert client._curl_mode is False

    async def test_level2_non_trigger_error_propagates_without_requests(self, client, monkeypatch):
        create1 = AsyncMock(side_effect=Exception("your request was blocked"))
        create2 = AsyncMock(side_effect=Exception("invalid api key"))
        client._openai_client = _mock_client(create1)
        client._openai_client_custom = _mock_client(create2)
        via_requests = AsyncMock(return_value="REQUESTS_OK")
        monkeypatch.setattr(LLMClient, "_chat_completions_via_requests", via_requests)

        with pytest.raises(Exception, match="invalid api key"):
            await client.create(model="m")
        via_requests.assert_not_awaited()
        # 已记住第二级，但未降到 requests
        assert client._use_custom_headers is True
        assert client._curl_mode is False


@pytest.mark.asyncio
class TestAgentDelegation:
    """Agent 只负责组装请求参数，传输全部委托给 LLMClient。"""

    def _stub_llm_client(self, agent, **methods):
        stub = MagicMock()
        for name, impl in methods.items():
            setattr(stub, name, impl)
        agent._llm_client = stub
        return stub

    async def test_llm_call_once_builds_request_kwargs(self, agent):
        create = AsyncMock(return_value="RESP")
        self._stub_llm_client(agent, create=create)

        assert await agent._llm_call_once() == "RESP"

        kwargs = create.call_args.kwargs
        assert kwargs["model"] == agent.model
        assert kwargs["messages"] == [{"role": "user", "content": "你好"}]
        assert kwargs["temperature"] == agent.temperature
        assert kwargs["max_tokens"] == agent.max_tokens
        assert kwargs["stream"] == agent.is_stream
        # 工具缓存为空时不传 tools；top_p=None 时不发送（严格端点只接受特定值）
        assert "tools" not in kwargs
        assert "top_p" not in kwargs

    async def test_top_p_sent_when_set(self, agent):
        agent.top_p = 0.95
        create = AsyncMock(return_value="RESP")
        self._stub_llm_client(agent, create=create)
        await agent._llm_call_once()
        assert create.call_args.kwargs["top_p"] == 0.95

    async def test_tools_included_when_cache_non_empty(self, agent):
        agent._tools_schema_cache = [{"type": "function", "function": {"name": "t"}}]
        create = AsyncMock(return_value="RESP")
        self._stub_llm_client(agent, create=create)
        await agent._llm_call_once()
        assert create.call_args.kwargs["tools"] == [{"type": "function", "function": {"name": "t"}}]

    async def test_llm_call_delegates_to_create_with_retry(self, agent):
        create_with_retry = AsyncMock(return_value="OK")
        create = AsyncMock(return_value="NO-RETRY")
        self._stub_llm_client(agent, create=create, create_with_retry=create_with_retry)

        assert await agent.llm_call() == "OK"
        create_with_retry.assert_awaited_once()
        create.assert_not_awaited()


def _status_error(status: int) -> openai.APIStatusError:
    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    resp = httpx.Response(status, request=req)
    return openai.APIStatusError(f"status {status}", response=resp, body=None)


@pytest.mark.asyncio
class TestLlmCallRetry:
    """瞬时错误退避重试：统一在 LLMClient.create_with_retry 一层完成。

    重构前重试层在 Agent.llm_call，内层是 Agent._llm_call_once（含三级 fallback）；
    现在 create_with_retry 直接包装 create，重试次数语义不变（初次 + max_retries 次）。
    """

    async def test_5xx_retried_then_success(self, client, monkeypatch):
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        calls = {"n": 0}

        async def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise _status_error(500)
            return "OK"

        client.create = flaky
        assert await client.create_with_retry(model="m") == "OK"
        assert calls["n"] == 3

    async def test_4xx_status_not_retried(self, client, monkeypatch):
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        calls = {"n": 0}

        async def bad(**kwargs):
            calls["n"] += 1
            raise _status_error(403)

        client.create = bad
        with pytest.raises(openai.APIStatusError):
            await client.create_with_retry(model="m")
        assert calls["n"] == 1

    async def test_retry_exhaustion(self, client, monkeypatch):
        sleep = AsyncMock()
        monkeypatch.setattr(asyncio, "sleep", sleep)
        calls = {"n": 0}

        req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        resp = httpx.Response(429, request=req)

        async def always_limited(**kwargs):
            calls["n"] += 1
            raise openai.RateLimitError("engine overloaded", response=resp, body=None)

        client.create = always_limited
        with pytest.raises(openai.RateLimitError):
            await client.create_with_retry(model="m")
        # 初次 + 4 次重试，共 5 次调用、4 次退避
        assert calls["n"] == 5
        assert sleep.await_count == 4

    async def test_connection_error_retried(self, client, monkeypatch):
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        calls = {"n": 0}
        req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")

        async def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise openai.APIConnectionError(request=req)
            return "OK"

        client.create = flaky
        assert await client.create_with_retry(model="m") == "OK"
        assert calls["n"] == 2

    async def test_backoff_delays_grow_exponentially(self, client, monkeypatch):
        sleep = AsyncMock()
        monkeypatch.setattr(asyncio, "sleep", sleep)
        req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        resp = httpx.Response(429, request=req)

        async def always_limited(**kwargs):
            raise openai.RateLimitError("engine overloaded", response=resp, body=None)

        client.create = always_limited
        with pytest.raises(openai.RateLimitError):
            await client.create_with_retry(model="m")

        delays = [c.args[0] for c in sleep.await_args_list]
        # delay = min(5 * 2**attempt, 60) + jitter(0~2s)：指数增长，上限 60+jitter
        for attempt, delay in enumerate(delays):
            assert 5 * (2 ** attempt) <= delay <= 5 * (2 ** attempt) + 2
