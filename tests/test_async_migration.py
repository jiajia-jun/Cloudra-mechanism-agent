"""AsyncOpenAI 迁移相关测试：异步流式消费、chunk 节流、429 重试。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cloudra.reAct import _ChunkPumper, _aiter_chunks


def _make_chunk(content=None, reasoning=None, finish=None):
    delta = SimpleNamespace(content=content, tool_calls=None)
    if reasoning is not None:
        delta.reasoning_content = reasoning
    choice = SimpleNamespace(delta=delta, finish_reason=finish)
    return SimpleNamespace(choices=[choice])


class _FakeAsyncStream:
    """模拟 AsyncOpenAI 的 AsyncStream。"""

    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for chunk in self._chunks:
                yield chunk

        return gen()


@pytest.mark.asyncio
class TestAiterChunks:
    async def test_async_stream(self):
        chunks = [_make_chunk("a"), _make_chunk("b"), _make_chunk("c", finish="stop")]
        received = [c.choices[0].delta.content async for c in _aiter_chunks(_FakeAsyncStream(chunks))]
        assert received == ["a", "b", "c"]

    async def test_sync_generator(self):
        # requests fallback 返回的同步生成器也应被正确消费，且不阻塞事件循环
        chunks = [_make_chunk("x"), _make_chunk("y")]
        received = [c.choices[0].delta.content async for c in _aiter_chunks(iter(chunks))]
        assert received == ["x", "y"]

    async def test_sync_generator_yields_loop(self):
        # 消费同步生成器时事件循环应保持响应
        ticks = 0

        async def ticker():
            nonlocal ticks
            for _ in range(3):
                await asyncio.sleep(0.01)
                ticks += 1

        async def consume():
            return [c async for c in _aiter_chunks(iter([_make_chunk("z")]))]

        _, _ = await asyncio.gather(ticker(), consume())
        assert ticks == 3


@pytest.mark.asyncio
class TestChunkPumper:
    async def test_size_flush(self):
        records = []

        async def record(event_type, data):
            records.append((event_type, data))

        pumper = _ChunkPumper(record)
        # 超过 80 字符应立即 flush
        await pumper.add("content", "a" * 90)
        assert len(records) == 1
        assert records[0][0] == "llm_chunk"
        assert records[0][1]["stream"] == "content"
        assert records[0][1]["delta"] == "a" * 90

    async def test_small_deltas_buffered_until_flush(self):
        records = []

        async def record(event_type, data):
            records.append((event_type, data))

        pumper = _ChunkPumper(record)
        # 小增量在节流窗口内不 flush（注意：add 的时间节流是 0.4s，这里快速连续调用）
        pumper._last_flush = asyncio.get_event_loop().time()  # 重置计时
        import time as _t
        pumper._last_flush = _t.monotonic()
        await pumper.add("content", "hello ")
        await pumper.add("reasoning", "think")
        assert records == []
        await pumper.flush()
        assert len(records) == 2
        streams = {r[1]["stream"] for r in records}
        assert streams == {"content", "reasoning"}

    async def test_empty_flush_is_noop(self):
        records = []

        async def record(event_type, data):
            records.append((event_type, data))

        pumper = _ChunkPumper(record)
        await pumper.flush()
        assert records == []


@pytest.mark.asyncio
class TestLlmRetry:
    async def test_retry_on_429_then_success(self, monkeypatch):
        import httpx
        import openai

        from cloudra.agent import Agent

        monkeypatch.setattr(asyncio, "sleep", AsyncMock())  # 跳过退避等待

        req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        resp = httpx.Response(429, request=req)

        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] <= 2:
                raise openai.RateLimitError("engine overloaded", response=resp, body=None)
            return "OK"

        agent = object.__new__(Agent)
        object.__setattr__(agent, "_llm_call_once", flaky)
        assert await agent.llm_call() == "OK"
        assert calls["n"] == 3

    async def test_400_not_retried(self, monkeypatch):
        import httpx
        import openai

        from cloudra.agent import Agent

        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        resp = httpx.Response(400, request=req)

        async def bad():
            raise openai.BadRequestError("bad request", response=resp, body=None)

        agent = object.__new__(Agent)
        object.__setattr__(agent, "_llm_call_once", bad)
        with pytest.raises(openai.BadRequestError):
            await agent.llm_call()
