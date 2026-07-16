import importlib.util
import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from pydantic import Field

from cloudra.config import get_config
from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "使用无头浏览器（Playwright Chromium）访问指定 URL，获取渲染后的页面文本、标题或截图。"
    "适用于需要执行 JavaScript 才能看到内容的动态网页。"
    "如果浏览器环境未就绪，会降级为静态 HTTP 抓取。"
)


class HeadlessBrowser_input_schema(input_schema):
    url: str = Field(description="要访问的目标 URL，必须包含协议（如 https://）")
    action: str = Field(
        default="fetch",
        description="操作类型：fetch（提取页面文本与标题）/ screenshot（截图并保存）"
    )
    wait_for: str = Field(
        default="",
        description="页面加载后等待的条件：可以是 CSS 选择器（等待元素出现）或纯数字秒数（如 '2'），留空则不额外等待"
    )
    max_length: int = Field(
        default=8000,
        description="fetch 模式下返回正文的最大字符数，超出会被截断"
    )
    full_page: bool = Field(
        default=True,
        description="screenshot 模式下是否截取完整页面；False 则只截取当前视口"
    )
    timeout: int = Field(
        default=30,
        description="页面加载超时时间（秒）"
    )


class HeadlessBrowser_output_schema(output_schema):
    success: bool = Field(description="是否成功")
    url: str = Field(default="", description="实际访问的 URL（可能经过重定向）")
    title: str = Field(default="", description="页面标题")
    text: str = Field(default="", description="fetch 模式下提取的页面正文")
    screenshot_path: str = Field(default="", description="screenshot 模式下保存的截图绝对路径")
    error: str = Field(default="", description="失败时的错误信息")


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
    tool_name: str = 'headless_browser'
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
                success=False, error="URL 不能为空。"
            )

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return HeadlessBrowser_output_schema(
                success=False, error=f"URL 格式不合法: {url}"
            )

        if action not in ('fetch', 'screenshot'):
            return HeadlessBrowser_output_schema(
                success=False,
                error=f"不支持的 action: {action}，仅支持 fetch / screenshot。"
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
                        success=False,
                        error=(
                            f"无头浏览器启动失败，无法截图: {str(e)}\n"
                            "请安装系统依赖: sudo playwright install-deps chromium"
                        )
                    )
                fallback = await self._fallback_http_fetch(url, timeout_sec, max_length)
                fallback.error = (
                    f"无头浏览器未就绪，已降级为静态抓取。原错误: {str(e)}"
                )
                return fallback

        if action == 'screenshot':
            return HeadlessBrowser_output_schema(
                success=False,
                error="缺少 playwright，无法截图。请先执行: pip install playwright && playwright install chromium"
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
                    text = text[:max_length] + '\n\n...[内容已截断]'

                await browser.close()
                return HeadlessBrowser_output_schema(
                    success=True, url=final_url, title=title, text=text
                )

            elif action == 'screenshot':
                safe_host = parsed.netloc.replace(':', '_')
                filename = f"{safe_host}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                screenshot_path = os.path.join(screenshot_dir, filename)

                await page.screenshot(path=screenshot_path, full_page=full_page)
                await browser.close()
                return HeadlessBrowser_output_schema(
                    success=True, url=final_url, title=title,
                    screenshot_path=screenshot_path
                )

    async def _fallback_http_fetch(
        self,
        url: str,
        timeout_sec: int,
        max_length: int
    ) -> HeadlessBrowser_output_schema:
        try:
            import httpx
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
                success=False,
                error=f"静态 HTTP 抓取也失败了: {str(e)}"
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
            text = text[:max_length] + '\n\n...[内容已截断]'

        return HeadlessBrowser_output_schema(
            success=True, url=url, title=title, text=text,
            error="已使用静态 HTTP 回退（无头浏览器未就绪）"
        )


def get_class():
    return HeadlessBrowser
