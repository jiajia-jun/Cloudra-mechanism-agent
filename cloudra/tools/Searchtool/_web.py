"""Web search backend for `search` (source=web)."""

from __future__ import annotations

import os
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


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


async def _search_tavily(client, query: str, max_results: int) -> list:
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


async def _search_brave(client, query: str, max_results: int) -> list:
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


async def _search_bing(client, query: str, max_results: int) -> list:
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


async def _search_ddg(client, query: str, max_results: int) -> list:
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


async def run(query: str, max_results: int = 8, backend: str = "auto") -> dict:
    query = query.strip()
    if not query:
        return {"is_success": False, "results": [], "backend_used": "", "error": "query must not be empty."}
    max_results = max(1, min(max_results, 20))

    try:
        import httpx
    except ImportError:
        return {"is_success": False, "results": [], "backend_used": "", "error": "httpx dependency is missing."}

    backend = backend.strip().lower()
    errors = []

    candidates = {
        "tavily": (os.environ.get("TAVILY_API_KEY"), _search_tavily),
        "brave": (os.environ.get("BRAVE_SEARCH_API_KEY"), _search_brave),
        "bing": (True, _search_bing),
        "duckduckgo": (True, _search_ddg),
    }

    if backend == "auto":
        order = ["tavily", "brave", "bing", "duckduckgo"]
    elif backend in candidates:
        order = [backend]
    else:
        return {
            "is_success": False,
            "results": [],
            "backend_used": "",
            "error": (
                f"Unknown backend: {backend}; available: auto / tavily / brave / bing / duckduckgo"
            ),
        }

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for name in order:
            available, fn = candidates[name]
            if not available:
                errors.append(f"{name}: API key not configured, skipped")
                continue
            try:
                results = await fn(client, query, max_results)
            except Exception as e:
                detail = str(e) or type(e).__name__
                errors.append(f"{name}: {detail}")
                continue
            if results:
                return {
                    "is_success": True,
                    "results": results,
                    "backend_used": name,
                    "error": "",
                }
            errors.append(f"{name}: no results")

    return {
        "is_success": False,
        "results": [],
        "backend_used": "",
        "error": "All backends returned no results. " + "; ".join(errors),
    }
