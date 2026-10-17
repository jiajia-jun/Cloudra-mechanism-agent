"""模型原生网页搜索适配层测试。

覆盖：适配器 host/model 匹配、auto/off/强制/custom 模式解析、extra_body 注入、
requests shim 的 extra_body 平铺，以及 Agent 请求装配对 web_search 工具的剔除。
"""

from __future__ import annotations

import pytest

from cloudra.infra.llm_client import serialize_openai_payload
from cloudra.infra.web_search_native import (
    NativeSearchAdapter,
    apply_native_search,
    register,
    resolve_native_search,
)


def test_resolve_off_returns_none():
    assert (
        resolve_native_search(base_url="https://x.example", model="m", mode="off")
        is None
    )


def test_resolve_boolean_aliases_mean_auto():
    """on/true/1 等布尔别名等价于 auto：OpenRouter 端点应命中 openrouter 适配器。"""
    for alias in ("on", "true", "yes", "1", "enabled"):
        adapter = resolve_native_search(
            base_url="https://openrouter.ai/api/v1",
            model="openai/gpt-4.1",
            mode=alias,
        )
        assert adapter is not None
        assert adapter.name == "openrouter"


def test_resolve_openai_search_model_via_auto():
    adapter = resolve_native_search(
        base_url="https://api.example.com/v1",
        model="gpt-5-search-api",
        mode="auto",
    )
    assert adapter is not None
    assert adapter.name == "openai"


def test_resolve_openai_host_via_auto():
    adapter = resolve_native_search(
        base_url="https://api.openai.com/v1",
        model="gpt-4.1",
        mode="auto",
    )
    assert adapter is not None
    assert adapter.name == "openai"


def test_resolve_openrouter_host_via_auto():
    adapter = resolve_native_search(
        base_url="https://openrouter.ai/api/v1",
        model="any/model",
        mode="auto",
    )
    assert adapter is not None
    assert adapter.name == "openrouter"


@pytest.mark.parametrize("mode", ["auto", "on", "true", "yes", "1", "enabled"])
@pytest.mark.parametrize("params", [None, {"tools": [{"type": "web_search"}]}])
def test_resolve_deepseek_auto_requires_explicit_opt_in(mode, params):
    """配置普通 DeepSeek 模型不能自动把整轮推理切换到 Responses。"""
    adapter = resolve_native_search(
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        mode=mode,
        params=params,
    )
    assert adapter is None


def test_deepseek_enrich_injects_web_search_tool():
    """DeepSeek 走 Responses 传输：注入 web_search 服务端工具到 function tools 之后。"""
    kwargs, name = apply_native_search(
        {"model": "deepseek-v4-flash", "tools": [{"type": "function", "function": {"name": "x"}}]},
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        mode="deepseek",
    )
    assert name == "deepseek"
    tools = kwargs["extra_body"]["tools"]
    assert tools == [
        {"type": "function", "function": {"name": "x"}},
        {"type": "web_search"},
    ]


def test_deepseek_enrich_params_tools_override():
    """params 显式给出 tools 时整体覆盖（给特殊端点用）。"""
    kwargs, name = apply_native_search(
        {"model": "deepseek-v4-flash"},
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        mode="deepseek",
        params={"tools": [{"type": "web_search"}, {"type": "web_search_2025_08_26"}]},
    )
    assert name == "deepseek"
    assert kwargs["extra_body"]["tools"] == [
        {"type": "web_search"},
        {"type": "web_search_2025_08_26"},
    ]


def test_resolve_forced_provider_ignores_missing_params():
    """显式强制 deepseek 时即使没有 params 也返回适配器（用户明确选择）。"""
    adapter = resolve_native_search(
        base_url="https://api.deepseek.com",
        model="deepseek-v4-pro",
        mode="deepseek",
    )
    assert adapter is not None
    assert adapter.name == "deepseek"
    assert adapter.transport == "responses"


def test_resolve_custom_mode():
    adapter = resolve_native_search(
        base_url="https://relay.example.com", model="m", mode="custom"
    )
    assert adapter is not None
    assert adapter.name == "custom"


def test_resolve_unknown_mode_falls_back():
    assert (
        resolve_native_search(
            base_url="https://x.example", model="m", mode="no-such-provider"
        )
        is None
    )


def test_custom_adapter_injects_params_verbatim():
    kwargs, name = apply_native_search(
        {"messages": [], "model": "m"},
        base_url="https://relay.example.com",
        model="m",
        mode="custom",
        params={"web_search_options": {"search_context_size": "high"}},
    )
    assert name == "custom"
    assert kwargs["extra_body"] == {"web_search_options": {"search_context_size": "high"}}


def test_openai_enrich_unchanged_without_params():
    kwargs, name = apply_native_search(
        {"model": "gpt-5-search-api"},
        base_url="https://api.example.com",
        model="gpt-5-search-api",
        mode="auto",
    )
    assert name == "openai"
    assert "extra_body" not in kwargs


def test_openai_enrich_passes_web_search_options():
    kwargs, name = apply_native_search(
        {"model": "gpt-5-search-api"},
        base_url="https://api.example.com",
        model="gpt-5-search-api",
        mode="auto",
        params={"web_search_options": {"search_context_size": "high"}},
    )
    assert name == "openai"
    assert kwargs["extra_body"]["web_search_options"]["search_context_size"] == "high"


def test_openrouter_enrich_default_web_plugin():
    kwargs, name = apply_native_search(
        {"model": "openai/gpt-4.1"},
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-4.1",
        mode="auto",
    )
    assert name == "openrouter"
    assert kwargs["extra_body"]["plugins"] == [{"id": "web"}]


def test_openrouter_enrich_custom_plugin_options():
    kwargs, _ = apply_native_search(
        {"model": "openai/gpt-4.1"},
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-4.1",
        mode="auto",
        params={"engine": "exa", "max_results": 3},
    )
    plugins = kwargs["extra_body"]["plugins"]
    assert plugins == [{"id": "web", "engine": "exa", "max_results": 3}]


def test_apply_native_search_keeps_existing_extra_body():
    kwargs, name = apply_native_search(
        {"model": "m", "extra_body": {"thinking": {"type": "enabled"}}},
        base_url="https://openrouter.ai/api/v1",
        model="m",
        mode="auto",
    )
    assert name == "openrouter"
    assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}
    assert kwargs["extra_body"]["plugins"] == [{"id": "web"}]


def test_register_custom_adapter_extension_point():
    custom = NativeSearchAdapter(
        name="my-company",
        hosts=("my.company.com",),
        requires_params=True,
    )
    register(custom)
    try:
        adapter = resolve_native_search(
            base_url="https://my.company.com/v1",
            model="m",
            mode="auto",
            params={"web_search_options": {"enable": True}},
        )
        assert adapter is custom
    finally:
        from cloudra.infra.web_search_native import _REGISTRY

        _REGISTRY.remove(custom)


def test_serialize_openai_payload_flattens_extra_body():
    payload = serialize_openai_payload(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "extra_body": {"plugins": [{"id": "web"}], "web_search_options": {"enable": True}},
        }
    )
    assert payload["plugins"] == [{"id": "web"}]
    assert payload["web_search_options"] == {"enable": True}
    assert "extra_body" not in payload

