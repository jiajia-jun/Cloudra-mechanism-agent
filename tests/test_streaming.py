"""cloudra/streaming.py 流式辅助工具测试：

- dynamic_deep_merge：流式 tool_call chunk 的增量合并
- _aiter_chunks：统一异步迭代 LLM chunk（AsyncStream / 同步生成器）
- _ChunkPumper：token 增量节流落库

更完整的 dynamic_deep_merge 用例见 tests/test_react_dispatch.py。
"""

import asyncio
import time
from types import SimpleNamespace

import pytest

from cloudra.streaming import _aiter_chunks, _ChunkPumper, dynamic_deep_merge


class TestDynamicDeepMerge:
    def test_string_fields_accumulate(self):
        buf = {}
        dynamic_deep_merge(buf, {"function": {"arguments": '{"text":'}})
        dynamic_deep_merge(buf, {"function": {"arguments": ' "hi"}'}})
        assert buf["function"]["arguments"] == '{"text": "hi"}'

    def test_fixed_enum_fields_overwrite(self):
        # type/name 是固定枚举值，重复 chunk 必须覆盖而不是累加
        buf = {}
        dynamic_deep_merge(buf, {"type": "function", "function": {"name": "stop"}})
        dynamic_deep_merge(buf, {"type": "function", "function": {"name": "stop"}})
        assert buf["type"] == "function"
        assert buf["function"]["name"] == "stop"


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
        pumper._last_flush = time.monotonic()  # 重置计时
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
