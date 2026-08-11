"""web_search 多后端工具钉板测试：

- 注册：web_search / openalex_searcher 在册，chemrxiv_searcher 已除名
- DDG HTML 解析器：fixture 解析标题/真实 URL（uddg 解包）/摘要
- 后端链：tavily/brave 解析、key 缺失跳过、auto fallback 顺序、全部失败不炸
"""

import pytest

from cloudra.core.agent import Follower
from cloudra.tools import get_tools_lst
from cloudra.tools.Searchtool.web_search import (
    WebSearch,
    WebSearch_input_schema,
    _DDGResultParser,
)

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


@pytest.fixture
def agent():
    return Follower(
        id="a-web", name="searcher", prompt="测试", query="q",
        conversation_id="test-websearch",
    )


def _install_fake_client(monkeypatch, routes, calls):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: FakeClient(routes, calls))


class TestRegistry:
    def test_web_search_registered_and_old_name_gone(self):
        names = {e.tool_name for e in get_tools_lst()}
        assert "web_search" in names
        assert "openalex_searcher" in names
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
        from cloudra.tools.Searchtool.web_search import _BingResultParser
        parser = _BingResultParser()
        parser.feed(BING_HTML)
        assert len(parser.results) == 2
        assert parser.results[0]["url"] == "https://example.com/vasp-encut"
        assert "VASP ENCUT" in parser.results[0]["title"]
        assert "ENCUT" in parser.results[0]["snippet"]
        assert parser.results[1]["url"] == "https://wiki.example.org/kpoints"


@pytest.mark.asyncio
class TestBackends:
    async def test_tavily_preferred_when_key_set(self, agent, mock_session, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        calls = []
        _install_fake_client(monkeypatch, {
            "https://api.tavily.com/search": FakeResponse(json_data={
                "results": [{"title": "T", "url": "https://t.example", "content": "snippet"}],
            }),
        }, calls)

        out = await WebSearch(subagent=agent).tool_call(
            WebSearch_input_schema(query="vasp encut"), mock_session)
        assert out.is_success and out.backend_used == "tavily"
        assert out.results[0]["url"] == "https://t.example"
        assert calls == [("POST", "https://api.tavily.com/search")]

    async def test_fallback_to_bing_without_keys(self, agent, mock_session, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        calls = []
        _install_fake_client(monkeypatch, {
            "https://www.bing.com/search": FakeResponse(text=BING_HTML),
        }, calls)

        out = await WebSearch(subagent=agent).tool_call(
            WebSearch_input_schema(query="vasp encut"), mock_session)
        assert out.is_success and out.backend_used == "bing"
        assert len(out.results) == 2
        assert calls == [("GET", "https://www.bing.com/search")]

    async def test_fallback_chain_on_backend_failure(self, agent, mock_session, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        calls = []
        _install_fake_client(monkeypatch, {
            "https://api.tavily.com/search": FakeResponse(status=500),
            "https://www.bing.com/search": FakeResponse(status=403),
            "https://html.duckduckgo.com/html/": FakeResponse(text=DDG_HTML),
        }, calls)

        out = await WebSearch(subagent=agent).tool_call(
            WebSearch_input_schema(query="vasp encut"), mock_session)
        assert out.is_success and out.backend_used == "duckduckgo"
        assert [c[1] for c in calls] == [
            "https://api.tavily.com/search",
            "https://www.bing.com/search",
            "https://html.duckduckgo.com/html/",
        ]

    async def test_all_backends_fail_returns_error(self, agent, mock_session, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        _install_fake_client(monkeypatch, {
            "https://www.bing.com/search": FakeResponse(status=403),
            "https://html.duckduckgo.com/html/": FakeResponse(status=403),
        }, [])

        out = await WebSearch(subagent=agent).tool_call(
            WebSearch_input_schema(query="vasp encut"), mock_session)
        assert not out.is_success
        assert "bing" in out.error and "duckduckgo" in out.error

    async def test_explicit_backend_and_validation(self, agent, mock_session, monkeypatch):
        calls = []
        _install_fake_client(monkeypatch, {
            "https://html.duckduckgo.com/html/": FakeResponse(text=DDG_HTML),
        }, calls)
        tool = WebSearch(subagent=agent)

        out = await tool.tool_call(
            WebSearch_input_schema(query="q", backend="duckduckgo"), mock_session)
        assert out.is_success and out.backend_used == "duckduckgo"

        out = await tool.tool_call(
            WebSearch_input_schema(query="q", backend="google"), mock_session)
        assert not out.is_success

        out = await tool.tool_call(WebSearch_input_schema(query="  "), mock_session)
        assert not out.is_success
