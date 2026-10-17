import json
from functools import partial
from types import SimpleNamespace

import httpx
import pytest

from cloudra.tools.Browsertool import browser as browser_module
from cloudra.tools.Browsertool.browser import (
    HeadlessBrowser,
    HeadlessBrowser_input_schema,
    HeadlessBrowser_output_schema,
)


@pytest.fixture
def deepseek_config(monkeypatch):
    config = SimpleNamespace(search_provider="deepseek", deepseek_api_key="shared-search-key")
    monkeypatch.setattr(browser_module, "get_config", lambda: config)
    monkeypatch.setattr(browser_module.importlib.util, "find_spec", lambda name: None)
    return config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("max_length", "expected_text"),
    [
        (0, "# Paper\n\nA **chemical** mechanism."),
        (9, "# Paper\n\n\n\n...[content truncated; increase max_length to retrieve more]"),
    ],
)
async def test_fetch_uses_shared_deepseek_key_and_returns_markdown(
    monkeypatch, deepseek_config, max_length, expected_text
):
    def respond(request):
        assert request.method == "POST"
        assert str(request.url) == "https://api.deepseek.com/v1/tools/fetch"
        assert request.headers["Authorization"] == "Bearer shared-search-key"
        assert json.loads(request.content) == {"url": "https://example.org/paper"}
        assert request.extensions["timeout"]["read"] == 17
        return httpx.Response(
            200, json={"title": "Paper", "content": "# Paper\n\nA **chemical** mechanism."}
        )

    monkeypatch.setattr(
        httpx, "AsyncClient", partial(httpx.AsyncClient, transport=httpx.MockTransport(respond))
    )

    result = await HeadlessBrowser().tool_call(
        HeadlessBrowser_input_schema(
            url="https://example.org/paper", max_length=max_length, timeout=17
        ),
        session=None,
    )

    assert result.is_success
    assert result.url == "https://example.org/paper"
    assert result.title == "Paper"
    assert result.text == expected_text
    assert result.error == ""


@pytest.mark.asyncio
async def test_deepseek_fetch_missing_key_returns_configuration_error(monkeypatch, deepseek_config):
    deepseek_config.deepseek_api_key = ""

    def no_network(**kwargs):
        raise AssertionError("No request should be made without a key")

    monkeypatch.setattr(httpx, "AsyncClient", no_network)
    result = await HeadlessBrowser().tool_call(
        HeadlessBrowser_input_schema(url="https://example.org/paper"), session=None
    )

    assert not result.is_success
    assert "deepseek_api_key" in result.error
    assert result.text == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unauthorized", "timeout", "invalid_content"])
async def test_deepseek_fetch_errors_do_not_fall_back(monkeypatch, deepseek_config, failure):
    def respond(request):
        assert str(request.url) == "https://api.deepseek.com/v1/tools/fetch"
        if failure == "timeout":
            raise httpx.ReadTimeout("Fetch timed out", request=request)
        if failure == "unauthorized":
            return httpx.Response(401, json={"error": "Invalid API key"})
        return httpx.Response(200, json={"title": "Paper", "content": 42})

    monkeypatch.setattr(
        httpx, "AsyncClient", partial(httpx.AsyncClient, transport=httpx.MockTransport(respond))
    )
    result = await HeadlessBrowser().tool_call(
        HeadlessBrowser_input_schema(url="https://example.org/paper"), session=None
    )

    assert not result.is_success
    assert "DeepSeek" in result.error
    assert "fallback" not in result.error.lower()
    assert result.text == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "action", "wait_for"),
    [
        ("deepseek", "screenshot", ""),
        ("deepseek", "fetch", "#article"),
        ("auto", "fetch", ""),
        ("tavily", "fetch", ""),
    ],
)
async def test_screenshots_waits_and_other_providers_keep_browser_path(
    monkeypatch, deepseek_config, provider, action, wait_for
):
    deepseek_config.search_provider = provider
    monkeypatch.setattr(browser_module.importlib.util, "find_spec", lambda name: object())

    async def run_browser(self, **kwargs):
        assert kwargs["action"] == action
        assert kwargs["wait_for"] == wait_for
        return HeadlessBrowser_output_schema(
            is_success=True, url="https://example.org/redirected", title="Rendered page"
        )

    monkeypatch.setattr(HeadlessBrowser, "_run_playwright", run_browser)
    result = await HeadlessBrowser().tool_call(
        HeadlessBrowser_input_schema(
            url="https://example.org/paper", action=action, wait_for=wait_for
        ),
        session=None,
    )

    assert result.is_success
    assert result.url == "https://example.org/redirected"
    assert result.title == "Rendered page"
