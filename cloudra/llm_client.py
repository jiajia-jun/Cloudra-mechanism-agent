"""LLM 传输层：OpenAI 兼容端点的统一调用入口。

从 agent.py 抽离的可复用传输层，包含：
- ResponseDictWrapper：dict 响应的属性访问包装
- is_fallback_trigger：中转站拦截/流控关键词判断
- requests shim（curl/7.68.0 UA）与手写 SSE 解析器
- 三级 fallback（默认请求头 → 自定义 UA → requests shim），带级别记忆
- 瞬时错误（429/5xx/连接错误）的指数退避重试

本模块不读取全局配置：所有连接参数由构造方显式传入；
构造不做任何网络 I/O（OpenAI 客户端按需惰性创建）。
"""

import asyncio
import json
import random
import re
from typing import Any, Optional, Union

import openai
import requests
from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletion, ChatCompletionChunk

ChatResponse = Union[ChatCompletion, AsyncStream[ChatCompletionChunk]]

# 模拟 curl 的 User-Agent：部分中转站按 UA 拦截 OpenAI 官方客户端
FALLBACK_USER_AGENT = "curl/7.68.0"


class ResponseDictWrapper:
    """把 requests 返回的 dict 包装成同时支持属性访问和 model_dump 的对象。"""

    __slots__ = ("_data",)

    def __init__(self, data: Any):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            val = self._data[name]
        except (KeyError, TypeError):
            raise AttributeError(name)
        return self._wrap(val)

    def model_dump(self, **kwargs) -> Any:
        return self._data

    @classmethod
    def _wrap(cls, val: Any) -> Any:
        if isinstance(val, dict):
            return cls(val)
        if isinstance(val, list):
            return [cls._wrap(x) for x in val]
        return val

    def __repr__(self) -> str:
        return f"ResponseDictWrapper({self._data!r})"


# 常见被拦截/流控关键词：大小写不敏感 + 词边界匹配，
# 避免 "Forbidden"（恰好等于关键词）或 "unblocked" 这类词的误判。
_BLOCKED_KEYWORDS = (
    "blocked",
    "your request was blocked",
    "access denied",
    "forbidden",
    "too many requests",
    "rate limit",
    "cloudflare",
    "bad gateway",
    "connection reset",
)
_BLOCKED_PATTERNS = tuple(
    re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE)
    for k in _BLOCKED_KEYWORDS
)


def is_fallback_trigger(exc: Exception) -> bool:
    """判断异常是否由中转站拦截/流控导致，需要切到 requests fallback。"""
    msg = str(exc)
    return any(p.search(msg) for p in _BLOCKED_PATTERNS)


def serialize_openai_payload(kwargs: dict) -> dict:
    """把 kwargs 里的 pydantic/model 对象序列化为纯 dict，供 requests 使用。"""

    def _to_dict(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return obj.model_dump(exclude_none=True)
        if hasattr(obj, "dict"):
            return obj.dict(exclude_none=True)
        if isinstance(obj, dict):
            return {k: _to_dict(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_dict(x) for x in obj]
        return obj

    return _to_dict(kwargs)


class LLMClient:
    """OpenAI 兼容端点的传输层客户端。

    Args:
        api_key: LLM API key。
        base_url: LLM API base URL。
        model: 默认模型名（create/chat_json 未显式传 model 时使用）。
        timeout: requests shim 的 HTTP 超时秒数。
        max_retries: 瞬时错误的最大重试次数（初次调用不计）。

    三级 fallback，用于应对中转站对 OpenAI 客户端请求头的拦截：
    1. OpenAI 客户端 + 默认请求头
    2. OpenAI 客户端 + 自定义 User-Agent（curl/7.68.0）
    3. requests 库 + 自定义 User-Agent（放到线程池执行，避免阻塞事件循环）

    一旦某一级成功，该实例会记住这一级，后续调用优先使用。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 4,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        # 兼容被中转站拦截的 OpenAI 客户端：启用后改用 requests 发送请求
        self._curl_mode = False
        # 启用 OpenAI 客户端 + 自定义请求头（比 requests 更规范）
        self._use_custom_headers = False
        # OpenAI 客户端实例级缓存：避免每个推理步骤都新建 httpx 连接池。
        # 惰性创建，保证构造本身不做任何 I/O。
        self._openai_client: Optional[AsyncOpenAI] = None
        self._openai_client_custom: Optional[AsyncOpenAI] = None
        # 记录最近一次调用返回的真实 token usage（流式/非流式均尝试捕获）
        self._last_usage: Optional[dict] = None

    @property
    def last_usage(self) -> Optional[dict]:
        """返回最近一次响应中的 usage 字段（prompt_tokens/completion_tokens/total_tokens）。"""
        return self._last_usage

    # ------------------------------------------------------------------
    # 公开调用入口
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_usage(obj: Any) -> Optional[dict]:
        """从响应对象或 dict 中提取 usage 字段。"""
        usage = getattr(obj, "usage", None)
        if usage is None and isinstance(obj, dict):
            usage = obj.get("usage")
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump(exclude_none=True)
        if hasattr(usage, "dict"):
            return usage.dict(exclude_none=True)
        return dict(usage) if not isinstance(usage, dict) else usage

    async def _wrap_stream(self, stream):
        """包装 OpenAI AsyncStream，在迭代过程中捕获 usage。"""
        async for chunk in stream:
            usage = self._extract_usage(chunk)
            if usage:
                self._last_usage = usage
            yield chunk

    async def create(self, **kwargs) -> ChatResponse:
        """单次调用 chat completions，内部完成三级 fallback（不重试瞬时错误）。"""
        if self.model is not None:
            kwargs.setdefault("model", self.model)

        # 流式调用时请求 provider 返回 usage，避免只能 token 估算
        if kwargs.get("stream"):
            kwargs.setdefault("stream_options", {"include_usage": True})

        # Level 3: requests fallback（已彻底降级）
        if self._curl_mode:
            try:
                return await self._chat_completions_via_requests(**kwargs)
            except Exception as e:
                print(f"\033[91m[LLM curl 异常]\033[0m {e}")
                raise

        # Level 2: OpenAI 客户端 + 自定义请求头（之前 fallback 成功过）
        if self._use_custom_headers:
            client = self._openai_client_with_custom_headers()
            try:
                response = await client.chat.completions.create(**kwargs)
                if kwargs.get("stream"):
                    return self._wrap_stream(response)
                self._last_usage = self._extract_usage(response)
                return response
            except Exception as e:
                if is_fallback_trigger(e):
                    print(f"\033[93m[LLM fallback] 自定义请求头仍被拦截，切到 requests: {e}\033[0m")
                    self._curl_mode = True
                    return await self._chat_completions_via_requests(**kwargs)
                print(f"\033[91m[LLM 异常]\033[0m {e}")
                raise

        # Level 1: OpenAI 客户端默认请求头（实例级缓存，避免每步新建连接池）
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        client = self._openai_client

        try:
            response = await client.chat.completions.create(**kwargs)
            if kwargs.get("stream"):
                return self._wrap_stream(response)
            self._last_usage = self._extract_usage(response)
            return response
        except Exception as e:
            if is_fallback_trigger(e):
                print(f"\033[93m[LLM fallback] OpenAI 默认请求头被拦截，尝试自定义请求头: {e}\033[0m")
                self._use_custom_headers = True
                client2 = self._openai_client_with_custom_headers()
                try:
                    response = await client2.chat.completions.create(**kwargs)
                    if kwargs.get("stream"):
                        return self._wrap_stream(response)
                    self._last_usage = self._extract_usage(response)
                    return response
                except Exception as e2:
                    if is_fallback_trigger(e2):
                        print(f"\033[93m[LLM fallback] 自定义请求头仍被拦截，切到 requests: {e2}\033[0m")
                        self._curl_mode = True
                        return await self._chat_completions_via_requests(**kwargs)
                    print(f"\033[91m[LLM 异常]\033[0m {e2}")
                    raise
            print(f"\033[91m[LLM 异常]\033[0m {e}")
            raise

    async def create_with_retry(self, **kwargs) -> ChatResponse:
        """调用 chat completions，带瞬时错误退避重试。

        429（限流/engine overloaded）、5xx、连接/超时错误属于瞬时故障，
        统一做指数退避重试；其他错误（认证、参数错误等）不重试，直接抛出。
        """
        for attempt in range(self.max_retries + 1):
            try:
                return await self.create(**kwargs)
            except (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError) as e:
                retriable, err = True, e
            except openai.APIStatusError as e:
                retriable, err = (e.status_code is not None and e.status_code >= 500), e
            if not retriable or attempt >= self.max_retries:
                raise err
            delay = min(5 * (2 ** attempt), 60) + random.uniform(0, 2)
            print(f"\033[93m[LLM 重试]\033[0m 瞬时错误（{err}），{delay:.0f} 秒后重试 ({attempt + 1}/{self.max_retries})")
            await asyncio.sleep(delay)

    async def embed(self, input: str, *, model: str):
        """调用 embeddings 端点，返回原始 embedding 响应。

        复用 Level 1 的客户端缓存；不做 fallback——embedding 失败时
        由调用方自行降级（如 Supervisor 退化为零向量）。
        """
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return await self._openai_client.embeddings.create(model=model, input=input)

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **extra,
    ) -> tuple[Optional[dict], Optional[Exception]]:
        """JSON 补全助手：system+user 进，解析后的 dict 出。

        供 Supervisor / YoloGuard 等"调一次模型拿结构化结论"的场景使用。
        首次输出被截断（finish_reason='length'，表现为 JSON Unterminated）时，
        用加倍的 max_tokens 重试一次。返回 (data, error)；data 为 None 时 error 非空。
        """
        request_kwargs = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            **extra,
        }
        try:
            response = await self.create(**request_kwargs)
        except Exception as exc:
            return None, exc
        content = response.choices[0].message.content or "{}"
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        try:
            return json.loads(content), None
        except Exception as exc:
            if finish_reason != "length":
                return None, exc
        # 截断重试一次：thinking 段吃掉了预算，翻倍后 JSON 通常能完整生成
        retry_kwargs = dict(request_kwargs)
        retry_kwargs["max_tokens"] = max_tokens * 2
        try:
            response = await self.create(**retry_kwargs)
        except Exception as exc:
            return None, exc
        try:
            return json.loads(response.choices[0].message.content or "{}"), None
        except Exception as exc:
            return None, exc

    # ------------------------------------------------------------------
    # requests shim（Level 3）
    # ------------------------------------------------------------------

    async def _chat_completions_via_requests(self, **kwargs) -> ChatResponse:
        """异步包装：把同步的 requests 调用放到线程池执行，避免阻塞事件循环。"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._chat_completions_via_requests_sync,
            kwargs,
        )

    def _chat_completions_via_requests_sync(self, kwargs: dict) -> ChatResponse:
        """使用 requests 直接调用 chat completions，模拟 openai 接口返回结构。"""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": FALLBACK_USER_AGENT,
            "Accept": "application/json",
        }
        payload = serialize_openai_payload(kwargs)
        stream = payload.get("stream", False)

        if stream:
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return self._stream_response(resp)
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
                # 部分中转站不支持 SSE，退化为非流式返回
                print("\033[93m[LLM fallback] 流式连接被重置，退化为非流式返回\033[0m")
                payload["stream"] = False
                stream = False

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        self._last_usage = self._extract_usage(data)
        return ResponseDictWrapper(data)

    def _openai_client_with_custom_headers(self) -> AsyncOpenAI:
        """返回带自定义 User-Agent 的 OpenAI 客户端（实例级缓存），用于二级 fallback。"""
        if self._openai_client_custom is None:
            self._openai_client_custom = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                default_headers={"User-Agent": FALLBACK_USER_AGENT},
            )
        return self._openai_client_custom

    def _stream_response(self, resp) -> Any:
        """解析 SSE 流，生成与 openai 兼容的 chunk 对象，并捕获 usage。"""
        for chunk in _iter_sse_chunks(resp):
            usage = self._extract_usage(chunk)
            if usage:
                self._last_usage = usage
            yield chunk


def _iter_sse_chunks(resp):
    """解析 SSE 流，生成 ResponseDictWrapper chunk。

    标准 SSE：同一事件块内的多行 data: 用 \\n 拼接后再解析；
    流末尾没有 \\n\\n 结尾的残余事件直接丢弃。
    """
    buffer = ""
    for raw in resp.iter_content(chunk_size=1024):
        if not raw:
            continue
        buffer += raw.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            data_parts = [
                line[5:].strip()
                for line in block.splitlines()
                if line.startswith("data:")
            ]
            if not data_parts:
                continue
            data_line = "\n".join(data_parts)
            if data_line == "[DONE]":
                continue
            try:
                chunk = json.loads(data_line)
            except json.JSONDecodeError:
                continue
            yield ResponseDictWrapper(chunk)
