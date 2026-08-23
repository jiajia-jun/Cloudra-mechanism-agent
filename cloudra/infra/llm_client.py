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
from types import SimpleNamespace
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
        data = self._data
        # 与 pydantic 语义一致：exclude_none=True 时剔除 None 值。
        # reAct 用 message.model_dump(exclude_none=True) 写上下文，
        # 不能把 content/tool_calls=None 的占位 key 落库。
        if kwargs.get("exclude_none") and isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data

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
    """把 kwargs 里的 pydantic/model 对象序列化为纯 dict，供 requests 使用。

    OpenAI SDK 的 ``extra_body`` 会被平铺进请求体顶层；requests shim 需要
    做同样的处理，否则 extra_body 会作为嵌套字段原样发送被服务商拒绝。
    """

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

    payload = _to_dict(kwargs)
    extra_body = payload.pop("extra_body", None)
    if isinstance(extra_body, dict):
        payload.update(extra_body)
    return payload


class LLMClient:
    """OpenAI 兼容端点的传输层客户端。

    Args:
        api_key: LLM API key。
        base_url: LLM API base URL。
        model: 默认模型名（create/chat_json 未显式传 model 时使用）。
        timeout: 单次请求超时秒数（OpenAI SDK 与 requests shim 共用）。
        max_retries: 瞬时错误的最大重试次数（初次调用不计）。

    三级 fallback，用于应对中转站对 OpenAI 客户端请求头的拦截：
    1. OpenAI 客户端 + 默认请求头
    2. OpenAI 客户端 + 自定义 User-Agent（curl/7.68.0）
    3. requests 库 + 自定义 User-Agent（放到线程池执行，避免阻塞事件循环）

    一旦某一级成功，该实例会记住这一级，后续调用优先使用。

    on_status: 可选异步/同步回调 ``(event, data)``，在重试/fallback/传输
    异常时触发，供上层（reAct）把传输层状态写入 session_events，避免
    全屏 TUI 下用户对长时间重试完全无感知。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: Optional[str] = None,
        timeout: int = 300,
        max_retries: int = 4,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        # 传输层状态回调（见类 docstring）；由 reAct 在任务启动时挂接
        self.on_status = None
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

    async def count_tokens(
        self,
        messages: list[dict],
        model: Optional[str] = None,
    ) -> dict:
        """对消息列表做 token 计数。

        优先级：
        1. 本地 ``tiktoken``（``TokenEstimator.count_messages``）——确切、无网络
        2. provider tokenize API（若端点可用）
        3. 字符启发式回退（仅 tiktoken 异常时由 TokenEstimator 内部处理）

        返回 ``{"tokens": int, "source": "tiktoken"|"api"|"estimate"}``。
        """
        from cloudra.infra.token_estimator import TokenEstimator

        model_name = model or self.model or ""
        if model_name:
            TokenEstimator.configure(model=model_name)

        # 1) tiktoken 本地精确计数
        try:
            import tiktoken  # noqa: F401

            tokens = await asyncio.to_thread(
                TokenEstimator.count_messages, messages
            )
            return {"tokens": int(tokens), "source": "tiktoken"}
        except Exception:
            pass

        # 2) provider tokenize
        api_count = await asyncio.to_thread(
            self._try_provider_tokenize, messages, model_name
        )
        if api_count is not None:
            return {"tokens": int(api_count), "source": "api"}

        # 3) 启发式（TokenEstimator 内部已回退）
        estimated = await asyncio.to_thread(
            TokenEstimator.count_messages, messages
        )
        return {"tokens": int(estimated), "source": "estimate"}

    def _try_provider_tokenize(
        self, messages: list[dict], model: str
    ) -> Optional[int]:
        """尝试常见 OpenAI 兼容 tokenize 端点；失败返回 None。"""
        if not self.base_url or not self.api_key:
            return None
        base = self.base_url.rstrip("/")
        # 兼容 .../v1 与裸 host
        candidates = [
            f"{base}/tokenize",
            f"{base}/token/count",
            f"{base}/tokens/count",
        ]
        if base.endswith("/v1"):
            root = base[: -len("/v1")]
            candidates.extend(
                [
                    f"{root}/tokenize",
                    f"{root}/v1/tokenize",
                ]
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": FALLBACK_USER_AGENT,
        }
        payloads = [
            {"model": model, "messages": messages},
            {"model": model, "input": messages},
            {"model": model, "text": json.dumps(messages, ensure_ascii=False)},
        ]
        for url in candidates:
            for payload in payloads:
                try:
                    resp = requests.post(
                        url, headers=headers, json=payload, timeout=min(10, self.timeout or 10)
                    )
                    if resp.status_code >= 400:
                        continue
                    data = resp.json()
                    count = self._parse_tokenize_response(data)
                    if count is not None:
                        return count
                except Exception:
                    continue
        return None

    @staticmethod
    def _parse_tokenize_response(data: Any) -> Optional[int]:
        """从各家 tokenize 响应里抽出 token 总数。"""
        if data is None:
            return None
        if isinstance(data, int):
            return data
        if not isinstance(data, dict):
            return None
        for key in ("tokens", "token_count", "total_tokens", "count", "prompt_tokens"):
            value = data.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
        usage = data.get("usage")
        if isinstance(usage, dict):
            for key in ("prompt_tokens", "total_tokens", "input_tokens"):
                value = usage.get(key)
                if isinstance(value, (int, float)):
                    return int(value)
        # OpenAI-ish: {"data": [{"tokens": [...]}]} 或 tokens 为 list
        tokens = data.get("tokens")
        if isinstance(tokens, list):
            return len(tokens)
        return None

    async def _emit_status(self, event: str, **data) -> None:
        """触发传输层状态回调；回调异常绝不外抛，传输层不因遥测失败。"""
        hook = self.on_status
        if hook is None:
            return
        try:
            result = hook(event, data)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

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
                await self._emit_status("llm_error", error=str(e), level="requests")
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
                    await self._emit_status("llm_fallback", error=str(e), level="requests")
                    self._curl_mode = True
                    return await self._chat_completions_via_requests(**kwargs)
                print(f"\033[91m[LLM 异常]\033[0m {e}")
                await self._emit_status("llm_error", error=str(e), level="custom_headers")
                raise

        # Level 1: OpenAI 客户端默认请求头（实例级缓存，避免每步新建连接池）
        # max_retries=0：SDK 自带的静默重试关掉，瞬时错误统一交给
        # create_with_retry 处理，保证每次重试都有事件/日志可见。
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
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
                await self._emit_status("llm_fallback", error=str(e), level="custom_headers")
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
                        await self._emit_status("llm_fallback", error=str(e2), level="requests")
                        self._curl_mode = True
                        return await self._chat_completions_via_requests(**kwargs)
                    print(f"\033[91m[LLM 异常]\033[0m {e2}")
                    await self._emit_status("llm_error", error=str(e2), level="custom_headers")
                    raise
            print(f"\033[91m[LLM 异常]\033[0m {e}")
            await self._emit_status("llm_error", error=str(e), level="default")
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
            await self._emit_status(
                "llm_retry",
                error=str(err),
                attempt=attempt + 1,
                max_retries=self.max_retries,
                delay=round(delay, 1),
            )
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
                timeout=self.timeout,
                max_retries=0,
            )
        return await self._openai_client.embeddings.create(model=model, input=input)

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 1.0,  # 大量模型只接受 temperature=1
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
    # Responses API 传输层（DeepSeek 原生联网搜索走 /responses）
    # ------------------------------------------------------------------

    async def create_responses(
        self,
        **kwargs,
    ) -> ChatResponse:
        """OpenAI Responses API 调用入口（chat.completions 风格 kwargs 进）。

        把 ``messages`` / ``tools`` / ``extra_body`` 等翻译成 Responses API
        请求体（POST ``{base_url}/responses``），再把响应翻译回 reAct 期望的
        Chat Completions 形状。DeepSeek 原生 ``web_search`` 工具只在
        ``/responses`` 支持，因此走此路径。
        """
        if self.model is not None:
            kwargs.setdefault("model", self.model)
        if kwargs.get("stream"):
            kwargs.setdefault("stream_options", {"include_usage": True})

        payload = _build_responses_payload(kwargs)
        stream = bool(payload.get("stream"))
        url = f"{_responses_base_url(self.base_url)}/responses"

        try:
            if stream:
                events = await asyncio.to_thread(
                    self._responses_start_stream, url, payload
                )
                return self._wrap_responses_stream(events)
            result = await asyncio.to_thread(
                self._responses_non_stream, url, payload
            )
            web = getattr(getattr(result, "_data", None), "get", lambda *a: None)("_web_search")
            for w in web or []:
                await self._emit_status("web_search", query=w.get("query"))
            return result
        except Exception as e:
            await self._emit_status("llm_error", error=str(e), level="responses")
            raise

    @staticmethod
    def _raise_for_status_with_body(resp) -> None:
        """非 2xx 时抛出带响应体的 HTTPError（body 截断到 ~800 字符）。

        resp.raise_for_status() 只带状态码一行（"400 Client Error"），把
        DeepSeek 返回的错误 body 丢掉了，日志无从诊断。保持
        requests.exceptions.HTTPError 类型，方便重试层按 status_code 分类。
        """
        if resp.ok:
            return
        body = (resp.text or "")[:800]
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} Error for url {resp.url}: {body}",
            response=resp,
        )

    def _responses_non_stream(self, url: str, payload: dict) -> ChatResponse:
        """非流式：POST /responses，翻译为 Chat Completions 形状。"""
        resp = requests.post(
            url,
            headers=_responses_headers(self.api_key),
            json=payload,
            timeout=self.timeout,
        )
        self._raise_for_status_with_body(resp)
        data = resp.json()
        self._last_usage = _translate_responses_usage(data)
        return ResponseDictWrapper(_translate_responses_completion(data))

    def _responses_start_stream(self, url: str, payload: dict):
        """流式：发起 POST /responses 并返回 (事件翻译生成器, 状态收集器)。"""
        resp = requests.post(
            url,
            headers=_responses_headers(self.api_key),
            json=payload,
            stream=True,
            timeout=self.timeout,
        )
        self._raise_for_status_with_body(resp)
        holder = SimpleNamespace(web_search_log=[], usage=None)
        return _responses_stream_events(resp, holder), holder

    def _wrap_responses_stream(self, events_holder):
        """异步包装流式事件生成器：翻译已在生成器内完成。

        联网搜索事件在流中段到达：逐条通过 on_status 上抛（此时 reasoning
        流仍开着），前端可把它并入「思考过程」，而不是等整条流结束后才补一个
        孤立的系统面板。
        """
        events, holder = events_holder

        async def _iterate():
            sentinel = object()
            emitted = 0
            while True:
                chunk = await asyncio.to_thread(next, events, sentinel)
                if chunk is sentinel:
                    break
                yield ResponseDictWrapper(chunk["completion"])
                emitted = await self._emit_new_web_searches(holder, emitted)
            emitted = await self._emit_new_web_searches(holder, emitted)
            if holder.usage:
                self._last_usage = self._extract_usage(holder.usage)

        return _iterate()

    async def _emit_new_web_searches(self, holder, emitted: int) -> int:
        """把 holder 里新增的 web_search_call 事件逐条上报（返回已上报数）。"""
        web = holder.web_search_log
        for query, _stage in web[emitted:]:
            await self._emit_status("web_search", query=query)
        return len(web)

    async def create_responses_with_retry(self, **kwargs) -> ChatResponse:
        """Responses API 调用，带瞬时错误退避重试（语义同 create_with_retry）。"""
        for attempt in range(self.max_retries + 1):
            try:
                return await self.create_responses(**kwargs)
            except (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError) as e:
                retriable, err = True, e
            except openai.APIStatusError as e:
                retriable, err = (e.status_code is not None and e.status_code >= 500), e
            except (requests.exceptions.RequestException,) as e:
                # requests 的 HTTPError 4xx 是确定性客户端错误（语义同上面的
                # openai.APIStatusError 分支），白重试只会拖延失败；连接/
                # 超时类错误仍可重试。
                retriable, err = not (
                    isinstance(e, requests.exceptions.HTTPError)
                    and e.response is not None
                    and e.response.status_code < 500
                ), e
            if not retriable or attempt >= self.max_retries:
                raise err
            delay = min(5 * (2 ** attempt), 60) + random.uniform(0, 2)
            print(f"\033[93m[LLM 重试]\033[0m Responses 瞬时错误（{err}），{delay:.0f} 秒后重试 ({attempt + 1}/{self.max_retries})")
            await self._emit_status(
                "llm_retry",
                error=str(err),
                attempt=attempt + 1,
                max_retries=self.max_retries,
                delay=round(delay, 1),
            )
            await asyncio.sleep(delay)

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
                timeout=self.timeout,
                max_retries=0,
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


# ---------------------------------------------------------------------------
# Responses API 翻译（DeepSeek 原生联网搜索走 /responses）
# ---------------------------------------------------------------------------


def _responses_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": FALLBACK_USER_AGENT,
        "Accept": "application/json",
    }


def _responses_base_url(base_url: str) -> str:
    """返回 Responses API 的 base_url（去掉尾部的 /v1）。

    DeepSeek 文档里 Responses API 挂在裸 host 上（POST /responses），而 OpenAI
    兼容的 base_url 常写成 .../v1。chat/completions 两者都能用，/responses 只
    在裸 host 可用，这里做兼容处理。
    """
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def _responses_message_content(content: Any) -> list[dict]:
    """Translate chat-style content into Responses API content parts.

    Plain strings become a single ``input_text``; parts lists keep their
    text and map ``image_url`` parts to ``input_image`` so visual-mode
    histories survive the /responses hop instead of being ``str()``-ed.
    """
    if isinstance(content, list):
        parts: list[dict] = []
        for part in content:
            if not isinstance(part, dict):
                parts.append({"type": "input_text", "text": str(part)})
            elif part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url")
                if url:
                    parts.append({"type": "input_image", "image_url": str(url)})
            else:
                parts.append({"type": "input_text", "text": str(part.get("text") or "")})
        return parts or [{"type": "input_text", "text": ""}]
    return [{"type": "input_text", "text": content if isinstance(content, str) else str(content or "")}]


def _responses_tool_output(content: Any) -> str:
    """Flatten a tool result to a plain string (function_call_output is text-only).

    Visual-mode tool results carry parts lists; image parts degrade to a
    placeholder so the base64 payload never lands in the request body.
    """
    if isinstance(content, list):
        texts = []
        for part in content:
            if not isinstance(part, dict):
                texts.append(str(part))
            elif part.get("type") == "image_url":
                texts.append("[Image attached to this tool result]")
            else:
                texts.append(str(part.get("text") or ""))
        return "\n".join(text for text in texts if text)
    return content if isinstance(content, str) else str(content or "")


def _build_responses_payload(kwargs: dict) -> dict:
    """把 chat.completions 风格的 kwargs 翻译成 Responses API 请求体。

    - ``messages`` → ``input``（message / function_call / function_call_output /
      reasoning 条目，DeepSeek 会把相邻条目合并回 assistant）
    - 第一条 system → ``instructions``
    - ``tools``（function schema）+ ``extra_body.tools``（非 function 的原生
      工具如 web_search）→ ``tools``
    - ``max_tokens`` → ``max_output_tokens``；其余 extra_body 字段透传
    """
    payload: dict[str, Any] = {}
    if kwargs.get("model"):
        payload["model"] = kwargs["model"]
    if kwargs.get("stream") is not None:
        payload["stream"] = bool(kwargs["stream"])
    if kwargs.get("temperature") is not None:
        payload["temperature"] = kwargs["temperature"]
    if kwargs.get("top_p") is not None:
        payload["top_p"] = kwargs["top_p"]
    if kwargs.get("max_tokens"):
        payload["max_output_tokens"] = kwargs["max_tokens"]

    instructions = ""
    input_items: list[dict] = []
    for msg in kwargs.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            if not instructions and content:
                instructions = content if isinstance(content, str) else str(content)
            continue
        if role in ("user", "assistant", "developer"):
            reasoning = msg.get("reasoning_content")
            if role == "assistant" and reasoning:
                input_items.append(
                    {
                        "type": "reasoning",
                        "content": [{"type": "reasoning_text", "text": str(reasoning)}],
                    }
                )
            input_items.append(
                {
                    "type": "message",
                    "role": "user" if role == "developer" else role,
                    "content": _responses_message_content(content),
                }
            )
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                input_items.append(
                    {
                        "type": "function_call",
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments") or "",
                        "call_id": tc.get("id") or f"call_{len(input_items)}",
                    }
                )
        elif role == "tool":
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id") or "",
                    "output": _responses_tool_output(content),
                }
            )
    if instructions:
        payload["instructions"] = instructions
    if input_items:
        payload["input"] = input_items
    elif kwargs.get("messages"):
        payload["input"] = [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": ""}]}
        ]

    tools: list[dict] = []
    for tool in kwargs.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        fn = tool.get("function") or {}
        entry: dict[str, Any] = {"type": "function", "name": fn.get("name", "")}
        if fn.get("description"):
            entry["description"] = fn["description"]
        if fn.get("parameters"):
            entry["parameters"] = fn["parameters"]
        tools.append(entry)
    extra = kwargs.get("extra_body") or {}
    for tool in extra.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") != "function":
            # 只追加非 function 的原生工具（如 web_search），避免重复 function schema
            tools.append(tool)
    if tools:
        payload["tools"] = tools
        payload.setdefault("tool_choice", "auto")
    for key, value in extra.items():
        if key != "tools":
            payload.setdefault(key, value)
    return payload


def _translate_responses_usage(data: dict) -> dict:
    usage = data.get("usage") or {}
    return {
        "prompt_tokens": usage.get("input_tokens"),
        "completion_tokens": usage.get("output_tokens"),
        "total_tokens": (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0),
    }


def _translate_responses_completion(data: dict) -> dict:
    """把 Responses API 非流式响应翻译成 Chat Completions 形状（reAct 可消费）。"""
    output = data.get("output") or []
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict] = []
    web_search: list[dict] = []
    for item in output:
        itype = item.get("type")
        if itype == "message":
            for part in item.get("content") or []:
                if part.get("type") in ("output_text", "text"):
                    text_parts.append(part.get("text", ""))
        elif itype == "reasoning":
            for part in item.get("content") or []:
                if part.get("type") == "reasoning_text":
                    reasoning_parts.append(part.get("text", ""))
        elif itype == "function_call":
            tool_calls.append(
                {
                    "id": item.get("call_id") or item.get("id") or f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments") or "",
                    },
                }
            )
        elif itype == "web_search_call":
            web_search.append(
                {
                    "query": (item.get("action") or {}).get("query"),
                    "status": item.get("status"),
                }
            )

    status = (data.get("status") or "").lower()
    if status in ("incomplete", "truncated"):
        finish_reason = "length"
    elif tool_calls:
        finish_reason = "tool_calls"
    else:
        finish_reason = "stop"

    # reAct 直接属性访问 message.content / message.tool_calls，三个 key 必须常驻
    # （无值时 None）；写上下文时由 model_dump(exclude_none=True) 剔除。
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(text_parts) or None,
        "reasoning_content": "".join(reasoning_parts) or None,
        "tool_calls": tool_calls or None,
    }
    completion = {
        "id": data.get("id"),
        "object": "chat.completion",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": _translate_responses_usage(data),
    }
    completion["_web_search"] = web_search
    return completion


def _responses_stream_events(resp, holder=None):
    """把 Responses API 的 SSE 事件翻译成 Chat Completion chunk（同步生成器）。

    DeepSeek 的流以 ``response.completed`` / ``response.incomplete`` /
    ``response.failed`` 结束（无 ``data: [DONE]``）。web_search_call 事件收集到
    ``holder.web_search_log``，usage 收集到 ``holder.usage``，供异步包装层上报。
    """
    events = _iter_sse_chunks(resp)
    tool_state: dict[int, dict] = {}
    tool_first_done: set[int] = set()
    if holder is None:
        holder = SimpleNamespace(web_search_log=[], usage=None)

    def _tool_chunk(idx: int, *, first: bool, arguments: str) -> dict:
        state = tool_state[idx]
        chunk: dict[str, Any] = {"index": idx, "type": "function"}
        if first:
            chunk["id"] = state["call_id"]
            chunk["function"] = {"name": state["name"], "arguments": arguments}
        else:
            chunk["function"] = {"arguments": arguments}
        return chunk

    # reAct 逐 chunk 直接访问 delta.content / delta.tool_calls，三个 key 必须常驻。
    def _emit(delta: dict, finish_reason: Any = None) -> dict:
        return {
            "completion": {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": delta.get("content"),
                            "reasoning_content": delta.get("reasoning_content"),
                            "tool_calls": delta.get("tool_calls"),
                        },
                        "finish_reason": finish_reason,
                    }
                ]
            }
        }

    for raw in events:
        ev = raw._data
        etype = ev.get("type") or ev.get("event") or ""
        if etype == "response.output_item.added":
            item = ev.get("item") or {}
            if item.get("type") == "function_call":
                idx = ev.get("output_index") if ev.get("output_index") is not None else len(tool_state)
                tool_state[idx] = {
                    "call_id": item.get("call_id") or item.get("id") or f"call_{idx}",
                    "name": item.get("name", ""),
                }
                yield _emit({"tool_calls": [_tool_chunk(idx, first=True, arguments="")]})
                tool_first_done.add(idx)
        elif etype == "response.function_call_arguments.delta":
            idx = ev.get("output_index")
            if idx is not None and idx in tool_state:
                delta = ev.get("delta", "") or ""
                first = idx not in tool_first_done
                tool_first_done.add(idx)
                yield _emit({"tool_calls": [_tool_chunk(idx, first=first, arguments=delta)]})
        elif etype == "response.output_text.delta":
            yield _emit({"content": ev.get("delta", "") or ""})
        elif etype == "response.reasoning_text.delta":
            yield _emit({"reasoning_content": ev.get("delta", "") or ""})
        elif etype.startswith("response.web_search_call."):
            # 查询词在事件里的位置因服务商而异：顶层 action / item.action / query 字段
            item = ev.get("item") or {}
            action = ev.get("action") or item.get("action") or {}
            if not isinstance(action, dict):
                action = {}
            query = action.get("query") or ev.get("query") or item.get("query")
            holder.web_search_log.append((query, etype.rsplit(".", 1)[-1]))
        elif etype in ("response.completed", "response.incomplete", "response.failed"):
            full = ev.get("response") or {}
            if full:
                holder.usage = _translate_responses_usage(full)
                output = full.get("output") or []
                has_fn = any(i.get("type") == "function_call" for i in output)
                status = (full.get("status") or "").lower()
                if status in ("incomplete", "truncated") or etype == "response.incomplete":
                    finish_reason = "length"
                elif has_fn:
                    finish_reason = "tool_calls"
                else:
                    finish_reason = "stop"
                if etype == "response.failed":
                    error = full.get("error") or {}
                    raise RuntimeError(f"Responses 流失败: {error.get('message') or error or full}")
            else:
                finish_reason = "length" if etype == "response.incomplete" else "stop"
            yield _emit({}, finish_reason=finish_reason)
            break
