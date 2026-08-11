"""模型原生网页搜索（provider 端代理）适配层。

背景
----
传统的 ``web_search`` 工具由 Agent 通过 function calling 发起，第三方搜索代理
（Tavily / Brave / Bing / DuckDuckGo）返回摘要，再由 Agent 自行筛选。而多家模型
服务商现在提供"模型端原生搜索"：搜索在服务商侧完成，结果以内联引用
（``message.annotations`` / ``url_citation`` / ``citations``）直接出现在模型回复里，
Agent 无需再走一次 function call 转第三方搜索。

适配器注册表
------------
本模块的核心是一个"注册表"（``_REGISTRY``）：一张把「服务商 → 如何开启原生搜索」
登记成列表的表。每行是一个 :class:`NativeSearchAdapter`：

- ``name``: 适配器名，同时是 ``config.native_search`` 可强制指定的值；
- ``hosts`` / ``model_markers``: 匹配条件，供 ``auto`` 模式按 base_url+model 查表；
- ``requires_params``: 官方接口无原生搜索的服务商（如 DeepSeek），置 True，
  表示 auto 模式下没有注入参数就视为不可用；
- ``enrich``: 真正把搜索参数写进请求（统一走 ``extra_body``，OpenAI SDK 与
  requests shim 都支持）。

业务代码（agent.py）不关心具体服务商，只调用 :func:`resolve_native_search`
「查表」：根据配置模式（off / auto / 服务商名 / custom）返回命中的适配器，
再由 :func:`apply_native_search` 注入请求。这样新增服务商 = 往表里追加一行并
``register``，agent.py 等调用方零改动——这就是可扩展性所在。

表里的内置适配器见 ``_REGISTRY`` 下方注释；第三方服务商 / 自建中转站调用
:func:`register` 注册自己的适配器即可（``custom`` 是 verbatim 注入参数的万能兜底）。

配置（LLMConfig）
----------------
- ``native_search``: 默认 ``auto``（按 base_url+model 自动识别并启用服务商侧搜索，
  识别不到的服务商回退传统 web_search 工具）。可选值：``off``（保持传统工具）/
  ``auto`` / 具体服务商名（强制）/ ``custom``（verbatim 注入）；
  ``on`` / ``true`` / ``1`` 等布尔别名等价于 ``auto``。
- ``native_search_params``: 注入参数，verbatim 写入 ``extra_body``。对注入方式
  不确定的端点（如自建中转站），用它精确指定
  ``{"web_search_options": {...}}``、``{"plugins": [{"id": "web"}]}``、
  ``{"tools": [{"type": "web_search"}]}`` 等字段。

服务商支持情况
--------------
- OpenAI：搜索模型（``gpt-*-search-api`` / ``search-preview``）总是联网。
- OpenRouter：``plugins: [{"id": "web"}]`` 给任意模型加搜索。
- DeepSeek：官方联网搜索只在 **Responses API**（/responses）支持，走 ``transport=
  "responses"``（``auto`` 模式自动启用）。chat/completions 的 tools schema 只接受
  ``function``，注入 ``{"type": "web_search"}`` 会被 400 拒绝，所以原生搜索
  一律走 /responses。注意：Responses 目前只支持 ``deepseek-v4-flash``。
- Google Gemini：OpenAI 兼容端点可用原生搜索，但注入字段因端点而异，
  建议通过 ``native_search_params`` 精确指定（``requires_params=True``）。
- 其他/自建中转站：用 ``custom`` 模式 + ``native_search_params``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

# OpenAI SDK 的 chat.completions.create 接受 extra_body；requests shim 也会把它
# 平铺到 payload 顶层（见 cloudra.infra.llm_client.serialize_openai_payload）。
_EXTRA_BODY = "extra_body"


def _host_of(base_url: str) -> str:
    """从 base_url 提取 hostname（小写），无法解析时返回空串。"""
    try:
        parsed = urlsplit(base_url if "://" in base_url else f"//{base_url}")
        return (parsed.hostname or "").lower()
    except (TypeError, ValueError):
        return ""


def _merge_extra_body(kwargs: dict, additions: dict) -> dict:
    """把 additions 合并进 kwargs 的 extra_body（保留已有键）。"""
    extra = dict(kwargs.get(_EXTRA_BODY) or {})
    extra.update(additions)
    kwargs = dict(kwargs)
    kwargs[_EXTRA_BODY] = extra
    return kwargs


@dataclass(frozen=True)
class NativeSearchAdapter:
    """一个模型端原生搜索适配器。

    Attributes:
        name: 适配器名，同时是 config.native_search 可强制指定的值。
        hosts: base_url hostname 匹配集合（小写、子串匹配）。
        model_markers: model 名必须包含的标记（任一命中即匹配）。
        requires_params: 为 True 时，auto 模式下若未提供 native_search_params
            则不启用（该服务商官方接口无原生搜索，或注入参数无法保证正确）。
        transport: 传输路径：chat（chat/completions，默认）或 responses（/responses）。
            DeepSeek 的原生搜索只在 Responses API 支持。
        inject_fn: 把原生搜索参数注入请求 kwargs 的可选回调（默认 verbatim 合并
            params 到 extra_body）。
    """

    name: str
    hosts: tuple[str, ...] = ()
    model_markers: tuple[str, ...] = ()
    requires_params: bool = False
    transport: str = "chat"
    inject_fn: Any = None

    def matches(self, *, base_url: str, model: str) -> bool:
        host = _host_of(base_url)
        if self.hosts and any(marker in host for marker in self.hosts):
            return True
        if self.model_markers:
            lowered = (model or "").lower()
            return any(marker in lowered for marker in self.model_markers)
        return False

    def inject(self, kwargs: dict, params: dict | None = None) -> dict:
        """把原生搜索参数注入请求 kwargs（默认 verbatim 合并到 extra_body）。"""
        if self.inject_fn is not None:
            return self.inject_fn(kwargs, params)
        return _merge_extra_body(kwargs, dict(params or {}))


# ---------------------------------------------------------------------------
# 内置适配器
# ---------------------------------------------------------------------------

def _openai_enrich(kwargs: dict, params: dict | None) -> dict:
    """OpenAI Chat Completions 搜索模型（gpt-*-search-api / search-preview）。

    这类模型本身总是联网搜索，无需注入工具；仅当 params 里给了
    ``web_search_options`` 等字段时透传（如 search_context_size）。
    """
    if not params:
        return kwargs
    return _merge_extra_body(kwargs, params)


def _openrouter_enrich(kwargs: dict, params: dict | None) -> dict:
    """OpenRouter ``web`` 插件（任何模型都能获得模型端/Exa 搜索）。

    默认注入 ``plugins: [{"id": "web"}]``；params 中 ``engine`` /
    ``max_results`` / ``include_domains`` / ``exclude_domains`` 等会写入插件。
    若 params 显式给出 ``plugins``，则整体覆盖。
    """
    additions: dict[str, Any] = {}
    if params and isinstance(params.get("plugins"), list):
        additions["plugins"] = params["plugins"]
    else:
        plugin: dict[str, Any] = {"id": "web"}
        for key in (
            "engine",
            "max_results",
            "search_prompt",
            "include_domains",
            "exclude_domains",
        ):
            if params and key in params:
                plugin[key] = params[key]
        additions["plugins"] = [plugin]
    return _merge_extra_body(kwargs, additions)


def _web_search_tool_enrich(kwargs: dict, params: dict | None) -> dict:
    """注入 ``web_search`` 服务端工具（供 Responses API 传输层用）。

    DeepSeek 的原生搜索只在 Responses API（/responses）支持；这里把
    ``{"type": "web_search"}`` 追加到已有的 function tools 之后，由
    LLMClient 的 Responses 传输把 extra_body 里的非 function 工具并入请求。
    若 params 显式给出 ``tools``，则整体覆盖。
    """
    if params and isinstance(params.get("tools"), list):
        return _merge_extra_body(kwargs, params)
    existing_tools = list(kwargs.get("tools") or [])
    additions = {"tools": [*existing_tools, {"type": "web_search"}]}
    return _merge_extra_body(kwargs, additions)


_REGISTRY: list[NativeSearchAdapter] = [
    NativeSearchAdapter(
        name="openai",
        hosts=("api.openai.com", "api.azure.com"),
        model_markers=("search-api", "search-preview"),
        inject_fn=_openai_enrich,
    ),
    NativeSearchAdapter(
        name="openrouter",
        hosts=("openrouter.ai",),
        inject_fn=_openrouter_enrich,
    ),
    NativeSearchAdapter(
        name="deepseek",
        hosts=("api.deepseek.com", "deepseek.com"),
        transport="responses",
        inject_fn=_web_search_tool_enrich,
    ),
    NativeSearchAdapter(
        name="gemini",
        hosts=("generativelanguage.googleapis.com", "googleapis.com"),
        requires_params=True,
    ),
]

# custom：verbatim 注入 native_search_params 的万能适配器
_CUSTOM_ADAPTER = NativeSearchAdapter(name="custom")


def register(adapter: NativeSearchAdapter) -> None:
    """注册自定义适配器（扩展点：第三方服务商 / 自建中转站）。"""
    _REGISTRY.append(adapter)


def resolve_native_search(
    *,
    base_url: str,
    model: str,
    mode: str,
    params: dict | None = None,
) -> NativeSearchAdapter | None:
    """根据配置模式解析当前 endpoint 的原生搜索适配器。

    Returns:
        命中的适配器；返回 None 表示原生搜索不可用（调用方应保留传统
        web_search 工具）。
    """
    mode = (mode or "off").strip().lower()
    params = params or {}
    # on/true/yes/1 等布尔别名统一视为 auto：按 base_url+model 自动识别。
    if mode in ("on", "true", "yes", "1", "enabled"):
        mode = "auto"
    if mode == "off":
        return None
    if mode == "custom":
        return _CUSTOM_ADAPTER
    if mode == "auto":
        for adapter in _REGISTRY:
            if adapter.matches(base_url=base_url, model=model):
                if adapter.requires_params and not params:
                    # 服务商官方接口无原生搜索，且没有注入参数可透传：
                    # 视为不可用，回退传统工具。
                    return None
                return adapter
        return None
    # 显式指定服务商名：强制使用该适配器（即使 auto 可能识别不到）
    for adapter in _REGISTRY:
        if adapter.name == mode:
            return adapter
    return None


def apply_native_search(
    kwargs: dict,
    *,
    base_url: str,
    model: str,
    mode: str,
    params: dict | None = None,
) -> tuple[dict, str | None]:
    """把原生搜索注入请求 kwargs。

    Returns:
        (修改后的 kwargs, 命中的适配器名或 None)。
    """
    adapter = resolve_native_search(
        base_url=base_url, model=model, mode=mode, params=params
    )
    if adapter is None:
        return kwargs, None
    return adapter.inject(kwargs, params), adapter.name
