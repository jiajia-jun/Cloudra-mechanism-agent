import importlib.util
import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, StrictStr

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.config import get_config

description = (
    "Fetch a known URL using the configured search provider (DeepSeek returns Markdown), or use "
    "a headless browser for screenshots and explicit page waits. Other providers use the browser "
    "with a static HTTP fallback when the browser environment is not ready. "
    "Use for: fetching known-URL pages or files, JS-rendered pages, SPAs, or full-page screenshots. "
    "Do not use for: keyword search (use search with source=web or source=arxiv)."
)


class HeadlessBrowser_input_schema(input_schema):
    url: str = Field(description="Target URL to visit; must include a scheme (e.g. https://)")
    action: str = Field(
        default="fetch",
        description="Action: fetch (extract page text and title) / screenshot (capture and save)"
    )
    wait_for: str = Field(
        default="",
        description="Wait condition after load: a CSS selector (wait for the element) or a number of seconds (e.g. '2'); empty means no extra wait"
    )
    max_length: int = Field(
        default=0,
        description="Max characters of body text in fetch mode; 0 means no truncation. Use only when the caller explicitly wants a shorter result."
    )
    full_page: bool = Field(
        default=True,
        description="In screenshot mode, capture the full page; False captures the current viewport only"
    )
    timeout: int = Field(
        default=30,
        description="Page-load timeout in seconds"
    )


class HeadlessBrowser_output_schema(output_schema):
    is_success: bool = Field(description="Whether the operation succeeded")
    url: str = Field(default="", description="Requested URL for DeepSeek fetch; visited URL for browser operations (may follow redirects)")
    title: str = Field(default="", description="Page title")
    text: str = Field(default="", description="Extracted page body in fetch mode")
    screenshot_path: str = Field(default="", description="Absolute path of the saved screenshot in screenshot mode")
    error: str = Field(default="", description="Error message on failure")


class _DeepSeekFetchResponse(BaseModel):
    title: StrictStr
    content: StrictStr


class _HTMLTextExtractor(HTMLParser):
    """极简 HTML 文本提取器，用于静态 HTTP 回退。"""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.title_parts = []
        self.in_title = False
        self.skip_tags = {'script', 'style', 'noscript', 'iframe', 'canvas', 'svg'}
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower == 'title':
            self.in_title = True
        if tag_lower in self.skip_tags:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == 'title':
            self.in_title = False
        if tag_lower in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        stripped = data.strip()
        if not stripped:
            return
        if self.in_title:
            self.title_parts.append(stripped)
        else:
            self.text_parts.append(stripped)

    def get_text(self):
        return '\n'.join(self.text_parts)

    def get_title(self):
        return ' '.join(self.title_parts)


class HeadlessBrowser(Tool):
    tool_id: str = 't-28'
    tool_name: str = 'browser'
    tool_description: str = description
    input_schema: Any = HeadlessBrowser_input_schema
    output_schema: Any = HeadlessBrowser_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: HeadlessBrowser_input_schema,
        session: Session
    ) -> HeadlessBrowser_output_schema:
        url = user_input.url.strip()
        action = user_input.action.lower()
        wait_for = user_input.wait_for.strip()
        max_length = user_input.max_length
        full_page = user_input.full_page
        timeout_sec = user_input.timeout

        if not url:
            return HeadlessBrowser_output_schema(
                is_success=False, error="URL must not be empty."
            )

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return HeadlessBrowser_output_schema(
                is_success=False, error=f"Invalid URL format: {url}"
            )

        if action not in ('fetch', 'screenshot'):
            return HeadlessBrowser_output_schema(
                is_success=False,
                error=f"Unsupported action: {action}; only fetch / screenshot are supported."
            )

        config = get_config()
        if config.search_provider == 'deepseek' and action == 'fetch' and not wait_for:
            api_key = config.deepseek_api_key.strip()
            if not api_key:
                return HeadlessBrowser_output_schema(
                    is_success=False,
                    error="DeepSeek fetch requires deepseek_api_key; Search and Fetch share this key."
                )
            try:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    response = await client.post(
                        'https://api.deepseek.com/v1/tools/fetch',
                        headers={'Authorization': f'Bearer {api_key}'},
                        json={'url': url}
                    )
                    response.raise_for_status()
                    page = _DeepSeekFetchResponse.model_validate(response.json())
                text = page.content
                if max_length > 0 and len(text) > max_length:
                    text = text[:max_length] + '\n\n...[content truncated; increase max_length to retrieve more]'
                return HeadlessBrowser_output_schema(
                    is_success=True, url=url, title=page.title, text=text
                )
            except Exception as e:
                return HeadlessBrowser_output_schema(
                    is_success=False, error=f"DeepSeek fetch failed: {e}"
                )

        playwright_available = importlib.util.find_spec("playwright.async_api") is not None

        if playwright_available:
            try:
                return await self._run_playwright(
                    url=url,
                    action=action,
                    wait_for=wait_for,
                    max_length=max_length,
                    full_page=full_page,
                    timeout_sec=timeout_sec,
                    parsed=parsed
                )
            except Exception as e:
                if action == 'screenshot':
                    return HeadlessBrowser_output_schema(
                        is_success=False,
                        error=(
                            f"Headless browser failed to start; cannot take a screenshot: {str(e)}\n"
                            "Install system dependencies: sudo playwright install-deps chromium"
                        )
                    )
                fallback = await self._fallback_http_fetch(url, timeout_sec, max_length)
                fallback.error = (
                    f"Headless browser not ready; fell back to a static fetch. Original error: {str(e)}"
                )
                return fallback

        if action == 'screenshot':
            return HeadlessBrowser_output_schema(
                is_success=False,
                error="playwright is not installed; cannot take a screenshot. Run: pip install playwright && playwright install chromium"
            )

        return await self._fallback_http_fetch(url, timeout_sec, max_length)

    async def _run_playwright(
        self,
        url: str,
        action: str,
        wait_for: str,
        max_length: int,
        full_page: bool,
        timeout_sec: int,
        parsed
    ) -> HeadlessBrowser_output_schema:
        from datetime import datetime

        from playwright.async_api import async_playwright

        data_dir = get_config().data_dir
        screenshot_dir = os.path.join(data_dir, 'screenshots')
        os.makedirs(screenshot_dir, exist_ok=True)

        timeout_ms = timeout_sec * 1000

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1280, 'height': 800})

            await page.goto(url, timeout=timeout_ms, wait_until='networkidle')

            if wait_for:
                if wait_for.isdigit():
                    import asyncio
                    await asyncio.sleep(int(wait_for))
                else:
                    await page.wait_for_selector(wait_for, timeout=timeout_ms)

            title = await page.title()
            final_url = page.url

            if action == 'fetch':
                text = await page.inner_text('body')
                if not text.strip():
                    text = await page.content()

                lines = [line.strip() for line in text.splitlines() if line.strip()]
                text = '\n'.join(lines)

                if max_length > 0 and len(text) > max_length:
                    text = text[:max_length] + '\n\n...[content truncated; increase max_length to retrieve more]'

                await browser.close()
                return HeadlessBrowser_output_schema(
                    is_success=True, url=final_url, title=title, text=text
                )

            elif action == 'screenshot':
                safe_host = parsed.netloc.replace(':', '_')
                filename = f"{safe_host}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                screenshot_path = os.path.join(screenshot_dir, filename)

                await page.screenshot(path=screenshot_path, full_page=full_page)
                await browser.close()
                return HeadlessBrowser_output_schema(
                    is_success=True, url=final_url, title=title,
                    screenshot_path=screenshot_path
                )

    async def _fallback_http_fetch(
        self,
        url: str,
        timeout_sec: int,
        max_length: int
    ) -> HeadlessBrowser_output_schema:
        try:
            async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    'User-Agent': (
                        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                })
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            return HeadlessBrowser_output_schema(
                is_success=False,
                error=f"Static HTTP fetch also failed: {str(e)}"
            )

        extractor = _HTMLTextExtractor()
        try:
            extractor.feed(html)
        except Exception:
            pass

        title = extractor.get_title()
        text = extractor.get_text()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines)

        if max_length > 0 and len(text) > max_length:
            text = text[:max_length] + '\n\n...[content truncated; increase max_length to retrieve more]'

        return HeadlessBrowser_output_schema(
            is_success=True, url=url, title=title, text=text,
            error="Static HTTP fallback was used (headless browser not ready)"
        )
