"""流式消费的通用辅助工具（从 reAct.py 抽离）。

包含：
- dynamic_deep_merge：流式 tool_call chunk 的增量合并
- _aiter_chunks：统一异步迭代 LLM chunk（AsyncStream / 同步生成器）
- _ChunkPumper：token 增量节流落库
"""

import asyncio
import time


def dynamic_deep_merge(buffer_dict: dict, delta_dict: dict) -> dict:
    """通用动态拼接工具：不硬编码任何字段名，自动合并字符串，自动递归字典。

    注意：tool_call 中的 'type' 和 'name' 是固定枚举值，收到重复 chunk 时应
    直接覆盖，而不是字符串累加；否则会出现 'functionfunction...' 这种非法值，
    导致部分 provider（如 Xiaomi token-plan）返回 400。
    """
    # 这些字段在 OpenAI tool_call chunk 中是固定值，不应累加。
    overwrite_fields = {"type", "name"}

    for key, value in delta_dict.items():
        if isinstance(value, dict):
            # 如果是嵌套字典（比如 'function'），递归进去拼接
            if key not in buffer_dict:
                buffer_dict[key] = {}
            dynamic_deep_merge(buffer_dict[key], value)

        elif isinstance(value, str):
            # 固定值字段直接覆盖，其余字符串字段累加。
            if key in overwrite_fields:
                buffer_dict[key] = value
            else:
                if key not in buffer_dict:
                    buffer_dict[key] = ""
                buffer_dict[key] += value

        else:
            # 如果是数字或其他类型（比如 'index'），直接覆盖/初始化
            buffer_dict[key] = value

    return buffer_dict


_STREAM_SENTINEL = object()


async def _aiter_chunks(response):
    """统一异步迭代 LLM chunk。

    AsyncStream（AsyncOpenAI）直接 async 迭代；requests fallback 返回的
    同步生成器用线程拉取 next()，避免网络阻塞冻结事件循环。
    """
    if hasattr(response, "__aiter__"):
        async for chunk in response:
            yield chunk
        return
    iterator = iter(response)
    while True:
        chunk = await asyncio.to_thread(next, iterator, _STREAM_SENTINEL)
        if chunk is _STREAM_SENTINEL:
            break
        yield chunk


class _ChunkPumper:
    """把 LLM token 增量节流落库为 llm_chunk 事件。

    节流规则：单流缓冲满 80 字符，或距上次落库满 0.4s，即flush。
    目标是兼顾前端流式观感和 SQLite 写入压力（约 2.5 写/秒/Agent）。
    """

    FLUSH_INTERVAL = 0.4
    FLUSH_SIZE = 80

    def __init__(self, record):
        # record: async callable(event_type: str, data: dict)，由 reAct._record_event 提供
        self._record = record
        self._buffers: dict[str, list[str]] = {"content": [], "reasoning": []}
        self._sizes: dict[str, int] = {"content": 0, "reasoning": 0}
        self._last_flush = time.monotonic()

    async def add(self, stream: str, delta: str) -> None:
        if not delta:
            return
        self._buffers[stream].append(delta)
        self._sizes[stream] += len(delta)
        if (
            self._sizes[stream] >= self.FLUSH_SIZE
            or (time.monotonic() - self._last_flush) >= self.FLUSH_INTERVAL
        ):
            await self.flush(stream)

    async def flush(self, stream: str = None) -> None:
        targets = (stream,) if stream else ("content", "reasoning")
        for name in targets:
            if not self._buffers[name]:
                continue
            delta = "".join(self._buffers[name])
            self._buffers[name].clear()
            self._sizes[name] = 0
            await self._record("llm_chunk", {"stream": name, "delta": delta})
        self._last_flush = time.monotonic()
