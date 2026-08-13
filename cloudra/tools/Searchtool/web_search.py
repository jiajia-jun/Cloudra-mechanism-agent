"""通用网页搜索工具：多后端可切换，自动 fallback。

后端优先级（auto 模式）：Tavily（需 TAVILY_API_KEY）→ Brave（需
BRAVE_SEARCH_API_KEY）→ DuckDuckGo HTML（免 key 兜底）。

设计纪律（与工具 description 一致）：本工具只返回标题/摘要/URL，用于筛选；
需要全文时用 web_fetcher 抓取选中的 URL。
"""

import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Generic web search. Returns title, URL, and snippet — for docs, forum threads, data pages, and other non-paper sources "
    "(prefer paper_searcher / openalex_searcher for academic papers).\n"
    "Two-stage discipline: this tool only returns snippets for screening; after picking the 1–3 most relevant hits, fetch full text with web_fetcher. "
    "When citing a conclusion, include the source URL.\n"
    "Backend auto-select: if TAVILY_API_KEY or BRAVE_SEARCH_API_KEY is set, use that API; otherwise fall back to key-free Bing / DuckDuckGo.\n"
    "Note: if the LLM config has native_search enabled, the provider runs search and inlines citations in the model reply — the Agent must not call this tool as well."
)

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class WebSearch_input_schema(input_schema):
    query: str = Field(description="Search query; use a specific, retrievable phrasing")
    max_results: int = Field(default=8, description="Maximum number of results")
    backend: str = Field(
        default="auto",
        description="Backend: auto (choose automatically) / tavily / brave / duckduckgo"
    )


class WebSearch_output_schema(output_schema):
    is_success: bool = Field(description="Whether the search succeeded")
    results: list = Field(default_factory=list, description="Result list: [{title, url, snippet, source}]")
    backend_used: str = Field(default="", description="Backend actually used")
    error: str = Field(default="", description="Failure message")


class _DDGResultParser(HTMLParser):
    """解析 DuckDuckGo html 版搜索结果页。

    条目结构：<a class="result__a" href="//duckduckgo.com/l/?uddg=<urlencoded>">标题</a>
    摘要：<a class="result__snippet">...</a>
    """

    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._capture = None  # 'title' | 'snippet'

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        cls = attr.get("class", "")
        if tag == "a" and "result__a" in cls:
            self._current = {"title": "", "url": "", "snippet": ""}
            href = attr.get("href", "")
            # DDG 结果链接是跳转包装：uddg 参数里才是真实 URL
            if "uddg=" in href:
                qs = parse_qs(urlparse(href).query)
                self._current["url"] = unquote(qs.get("uddg", [""])[0])
            else:
                self._current["url"] = href
            self._capture = "title"
        elif tag == "a" and "result__snippet" in cls:
            self._capture = "snippet"

    def handle_endtag(self, tag):
        if tag == "a" and self._capture == "title" and self._current is not None:
            self._capture = None
            if self._current.get("url"):
                self.results.append(self._current)
            self._current = None
        elif tag == "a" and self._capture == "snippet":
            self._capture = None

    def handle_data(self, data):
        if self._capture == "title" and self._current is not None:
            self._current["title"] += data.strip()
        elif self._capture == "snippet" and self.results:
            self.results[-1]["snippet"] += data.strip()


class _BingResultParser(HTMLParser):
    """解析 Bing 搜索结果页。

    条目结构：<li class="b_algo"><h2><a href="...">标题</a></h2>...<p>摘要</p></li>
    """

    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._in_h2 = False
        self._capture = None  # 'title' | 'snippet'

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        cls = attr.get("class", "")
        if tag == "li" and "b_algo" in cls:
            self._current = {"title": "", "url": "", "snippet": ""}
        elif self._current is not None:
            if tag == "h2":
                self._in_h2 = True
            elif tag == "a" and self._in_h2 and not self._current["url"]:
                self._current["url"] = attr.get("href", "")
                self._capture = "title"
            elif tag == "p" and not self._current["snippet"]:
                self._capture = "snippet"

    def handle_endtag(self, tag):
        if tag == "li" and self._current is not None:
            if self._current.get("url"):
                self.results.append(self._current)
            self._current = None
            self._in_h2 = False
            self._capture = None
        elif tag == "h2":
            self._in_h2 = False
            if self._capture == "title":
                self._capture = None
        elif tag in ("a", "p") and self._capture:
            self._capture = None

    def handle_data(self, data):
        if self._current is None or not self._capture:
            return
        self._current[self._capture] += data.strip()


class WebSearch(Tool):
    tool_id: str = 't-websearch'
    tool_name: str = 'web_search'
    tool_description: str = description
    input_schema: Any = WebSearch_input_schema
    output_schema: Any = WebSearch_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: WebSearch_input_schema, session: Session) -> WebSearch_output_schema:
        query = user_input.query.strip()
        if not query:
            return WebSearch_output_schema(is_success=False, error="query 不能为空。")
        max_results = max(1, min(user_input.max_results, 20))

        try:
            import httpx
        except ImportError:
            return WebSearch_output_schema(is_success=False, error="缺少 httpx 依赖。")

        backend = user_input.backend.strip().lower()
        errors = []

        candidates = {
            "tavily": (os.environ.get("TAVILY_API_KEY"), self._search_tavily),
            "brave": (os.environ.get("BRAVE_SEARCH_API_KEY"), self._search_brave),
            "bing": (True, self._search_bing),
            "duckduckgo": (True, self._search_ddg),
        }

        if backend == "auto":
            order = ["tavily", "brave", "bing", "duckduckgo"]
        elif backend in candidates:
            order = [backend]
        else:
            return WebSearch_output_schema(
                is_success=False,
                error=f"未知 backend: {backend}，可用：auto / tavily / brave / bing / duckduckgo",
            )

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            for name in order:
                available, fn = candidates[name]
                if not available:
                    errors.append(f"{name}: 未配置 API key，跳过")
                    continue
                try:
                    results = await fn(client, query, max_results)
                except Exception as e:
                    # ConnectTimeout 等异常的 str 可能为空，带上类型名才好诊断
                    detail = str(e) or type(e).__name__
                    errors.append(f"{name}: {detail}")
                    continue
                if results:
                    return WebSearch_output_schema(
                        is_success=True, results=results, backend_used=name
                    )
                errors.append(f"{name}: 无结果")

        return WebSearch_output_schema(
            is_success=False,
            error="所有后端均未返回结果。" + "；".join(errors),
        )

    async def _search_tavily(self, client, query: str, max_results: int) -> list:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": os.environ["TAVILY_API_KEY"],
                "query": query,
                "max_results": max_results,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "source": "tavily",
                "published": item.get("published_date"),
            }
            for item in data.get("results", [])
            if item.get("url")
        ]

    async def _search_brave(self, client, query: str, max_results: int) -> list:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "source": "brave",
                "published": item.get("age"),
            }
            for item in data.get("web", {}).get("results", [])
            if item.get("url")
        ]

    async def _search_bing(self, client, query: str, max_results: int) -> list:
        resp = await client.get(
            "https://www.bing.com/search",
            params={"q": query, "count": max_results},
            headers={"User-Agent": _UA},
        )
        resp.raise_for_status()
        parser = _BingResultParser()
        parser.feed(resp.text)
        results = parser.results[:max_results]
        for item in results:
            item["source"] = "bing"
        return results

    async def _search_ddg(self, client, query: str, max_results: int) -> list:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": _UA},
        )
        resp.raise_for_status()
        parser = _DDGResultParser()
        parser.feed(resp.text)
        results = parser.results[:max_results]
        for item in results:
            item["source"] = "duckduckgo"
        return results


def get_class():
    return WebSearch
