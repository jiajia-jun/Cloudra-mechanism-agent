"""AsyncOpenAI 迁移相关测试：瞬时错误的退避重试。

重构前重试层在 Agent.llm_call（内层 _llm_call_once 含三级 fallback），
属于"两层重试"；现在网络重试统一收拢到 LLMClient.create_with_retry 一层，
create 内部只做三级 fallback 不做瞬时重试，总尝试次数语义不变（初次 + 4 次重试）。

流式消费工具（_aiter_chunks / _ChunkPumper）已迁移到 cloudra/streaming.py，
对应测试见 tests/test_streaming.py。
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from cloudra.infra.llm_client import LLMClient


@pytest.mark.asyncio
class TestLlmRetry:
    async def test_retry_on_429_then_success(self, monkeypatch):
        import httpx
        import openai

        monkeypatch.setattr(asyncio, "sleep", AsyncMock())  # 跳过退避等待

        req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        resp = httpx.Response(429, request=req)

        calls = {"n": 0}

        async def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise openai.RateLimitError("engine overloaded", response=resp, body=None)
            return "OK"

        client = LLMClient(api_key="sk-test", base_url="https://example.invalid/v1")
        client.create = flaky
        assert await client.create_with_retry(model="m") == "OK"
        assert calls["n"] == 3

    async def test_400_not_retried(self, monkeypatch):
        import httpx
        import openai

        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        resp = httpx.Response(400, request=req)

        async def bad(**kwargs):
            raise openai.BadRequestError("bad request", response=resp, body=None)

        client = LLMClient(api_key="sk-test", base_url="https://example.invalid/v1")
        client.create = bad
        with pytest.raises(openai.BadRequestError):
            await client.create_with_retry(model="m")
