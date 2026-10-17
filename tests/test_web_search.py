"""web search backend 钉板测试：

- 注册：search 在册，旧 web_search / openalex_searcher / paper_searcher / chemrxiv_searcher 已除名
- DDG HTML 解析器：fixture 解析标题/真实 URL（uddg 解包）/摘要
- 后端链：配置选择、DeepSeek 摘要映射、key 缺失报错、显式 auto fallback
"""

from types import SimpleNamespace

import httpx
import pytest

from cloudra.tools import get_tools_lst
from cloudra.tools.Searchtool import _web
from cloudra.tools.Searchtool._web import _DDGResultParser, run

DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fvasp-encut&amp;rut=abc">VASP ENCUT convergence</a>
  <a class="result__snippet">How to converge <b>ENCUT</b> in VASP calculations.</a>
</div>
<div class="result">
  <a class="result__a" href="https://direct.example.org/page">Direct link page</a>
  <a class="result__snippet">A direct result without wrapper.</a>
</div>
</body></html>
"""

BING_HTML = """
<html><body>
<ol id="b_results">
<li class="b_algo"><h2><a href="https://example.com/vasp-encut">VASP ENCUT convergence</a></h2>
<div class="b_caption"><p>How to converge ENCUT in VASP calculations.</p></div></li>
<li class="b_algo"><h2><a href="https://wiki.example.org/kpoints">k-point sampling wiki</a></h2>
<p>Choosing k-point grids for periodic DFT.</p></li>
</ol>
</body></html>
"""


class FakeResponse:
    def __init__(self, json_data=None, text="", status=200):
        self._json = json_data
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeClient:
    """按 URL 路由的假 httpx.AsyncClient。"""

    def __init__(self, routes, calls):
        self._routes = routes
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self._calls.append(("POST", url))
        return self._routes[url]

    async def get(self, url, **kwargs):
        self._calls.append(("GET", url))
        return self._routes[url]


def _install_fake_client(monkeypatch, routes, calls):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: FakeClient(routes, calls))


class TestRegistry:
    def test_search_registered_and_old_names_gone(self):
        names = {e.tool_name for e in get_tools_lst()}
        assert "search" in names
        assert "web_search" not in names
        assert "openalex_searcher" not in names
        assert "paper_searcher" not in names
        assert "chemrxiv_searcher" not in names


class TestDDGParser:
    def test_parse_results(self):
        parser = _DDGResultParser()
        parser.feed(DDG_HTML)
        assert len(parser.results) == 2
        first = parser.results[0]
        assert first["url"] == "https://example.com/vasp-encut"  # uddg 解包
        assert "VASP ENCUT" in first["title"]
        assert "ENCUT" in first["snippet"]
        assert parser.results[1]["url"] == "https://direct.example.org/page"


class TestBingParser:
    def test_parse_results(self):
        from cloudra.tools.Searchtool._web import _BingResultParser
        parser = _BingResultParser()
        parser.feed(BING_HTML)
        assert len(parser.results) == 2
        assert parser.results[0]["url"] == "https://example.com/vasp-encut"
        assert "VASP ENCUT" in parser.results[0]["title"]
        assert "ENCUT" in parser.results[0]["snippet"]
        assert parser.results[1]["url"] == "https://wiki.example.org/kpoints"


@pytest.mark.asyncio
class TestBackends:
    async def test_tavily_preferred_when_key_set(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        calls = []
        _install_fake_client(monkeypatch, {
            "https://api.tavily.com/search": FakeResponse(json_data={
                "results": [{"title": "T", "url": "https://t.example", "content": "snippet"}],
            }),
        }, calls)

        out = await run(query="vasp encut", max_results=8, backend="auto")
        assert out["is_success"] and out["backend_used"] == "tavily"
        assert out["results"][0]["url"] == "https://t.example"
        assert calls == [("POST", "https://api.tavily.com/search")]

    async def test_fallback_to_bing_without_keys(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        calls = []
        _install_fake_client(monkeypatch, {
            "https://www.bing.com/search": FakeResponse(text=BING_HTML),
        }, calls)

        out = await run(query="vasp encut", max_results=8, backend="auto")
        assert out["is_success"] and out["backend_used"] == "bing"
        assert len(out["results"]) == 2
        assert calls == [("GET", "https://www.bing.com/search")]

    async def test_fallback_chain_on_backend_failure(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        calls = []
        _install_fake_client(monkeypatch, {
            "https://api.tavily.com/search": FakeResponse(status=500),
            "https://www.bing.com/search": FakeResponse(status=403),
            "https://html.duckduckgo.com/html/": FakeResponse(text=DDG_HTML),
        }, calls)

        out = await run(query="vasp encut", max_results=8, backend="auto")
        assert out["is_success"] and out["backend_used"] == "duckduckgo"
        assert [c[1] for c in calls] == [
            "https://api.tavily.com/search",
            "https://www.bing.com/search",
            "https://html.duckduckgo.com/html/",
        ]

    async def test_all_backends_fail_returns_error(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        _install_fake_client(monkeypatch, {
            "https://www.bing.com/search": FakeResponse(status=403),
            "https://html.duckduckgo.com/html/": FakeResponse(status=403),
        }, [])

        out = await run(query="vasp encut", max_results=8, backend="auto")
        assert not out["is_success"]
        assert "bing" in out["error"] and "duckduckgo" in out["error"]

    async def test_explicit_backend_and_validation(self, monkeypatch):
        calls = []
        _install_fake_client(monkeypatch, {
            "https://html.duckduckgo.com/html/": FakeResponse(text=DDG_HTML),
        }, calls)

        out = await run(query="q", max_results=8, backend="duckduckgo")
        assert out["is_success"] and out["backend_used"] == "duckduckgo"

        out = await run(query="q", max_results=8, backend="google")
        assert not out["is_success"]

        out = await run(query="  ", max_results=8)
        assert not out["is_success"]


@pytest.mark.asyncio
async def test_search_uses_configured_deepseek_and_returns_model_summary(monkeypatch, mock_session):
    """Configured provider must receive the query and return usable hits through search."""
    from cloudra.tools.Searchtool.search import Search, Search_input_schema

    monkeypatch.setattr(_web, "get_config", lambda: SimpleNamespace(
        search_provider="deepseek", deepseek_api_key="shared-search-key",
    ), raising=False)
    requests = []

    def handle(request):
        import json

        requests.append(request)
        assert str(request.url) == "https://api.deepseek.com/v1/tools/search"
        assert request.headers["Authorization"] == "Bearer shared-search-key"
        assert json.loads(request.content) == {
            "query": "Cope rearrangement site:acs.org", "count": 3, "need_content": False,
        }
        return httpx.Response(200, json={"results": [{
            "title": "Cope rearrangement", "url": "https://example.org/cope",
            "snippet": "Short display summary", "summary": "Long summary for the model",
            "content": "", "date": None, "site_name": "Example", "site_icon": None,
            "rerank_score": 2.4, "authority": 3,
        }]})

    client_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client_cls(
        **kw, transport=httpx.MockTransport(handle),
    ))
    output = await Search().tool_call(Search_input_schema(
        query="Cope rearrangement site:acs.org", max_results=3,
    ), mock_session)
    assert output.is_success
    assert output.backend_used == "deepseek"
    assert output.results == [{
        "title": "Cope rearrangement", "url": "https://example.org/cope",
        "snippet": "Long summary for the model", "source": "deepseek", "published": None,
    }]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_selected_deepseek_without_key_reports_configuration_error(monkeypatch):
    monkeypatch.setattr(_web, "get_config", lambda: SimpleNamespace(
        search_provider="deepseek", deepseek_api_key="",
    ), raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "available-but-not-selected")
    calls = []
    _install_fake_client(monkeypatch, {}, calls)

    output = await run("Cope rearrangement")
    assert not output["is_success"]
    assert "deepseek" in output["error"].lower()
    assert "key" in output["error"].lower()
    assert calls == []


@pytest.mark.asyncio
async def test_selected_deepseek_http_error_does_not_change_provider(monkeypatch):
    monkeypatch.setattr(_web, "get_config", lambda: SimpleNamespace(
        search_provider="deepseek", deepseek_api_key="shared-search-key",
    ), raising=False)
    calls = []
    _install_fake_client(monkeypatch, {
        "https://api.deepseek.com/v1/tools/search": FakeResponse(status=401),
    }, calls)

    output = await run("Cope rearrangement")
    assert not output["is_success"]
    assert "401" in output["error"]
    assert calls == [("POST", "https://api.deepseek.com/v1/tools/search")]


@pytest.mark.asyncio
async def test_explicit_auto_tries_deepseek_before_existing_backends(monkeypatch):
    monkeypatch.setattr(_web, "get_config", lambda: SimpleNamespace(
        search_provider="auto", deepseek_api_key="shared-search-key",
    ), raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-test-key")
    calls = []
    _install_fake_client(monkeypatch, {
        "https://api.deepseek.com/v1/tools/search": FakeResponse(status=500),
        "https://api.tavily.com/search": FakeResponse(json_data={"results": [{
            "title": "Cope", "url": "https://example.org/cope", "content": "Summary",
        }]}),
    }, calls)

    output = await run("Cope rearrangement")
    assert output["is_success"]
    assert output["backend_used"] == "tavily"
    assert calls == [
        ("POST", "https://api.deepseek.com/v1/tools/search"),
        ("POST", "https://api.tavily.com/search"),
    ]
