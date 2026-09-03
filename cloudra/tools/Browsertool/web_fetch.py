import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Generic HTTP fetch/download tool: fetch page HTML and extract body text, or save the response bytes to a local file. "
    "Use for: fetching known-URL literature pages, web content, or data files; binary downloads must set download_path. "
    "Do not use for: JS-rendered dynamic pages (use browser) or keyword search (use search with source=web). "
    "Note: do not fetch PDFs in text mode (you will get garbage); download with download_path and pass the file to read."
)


class WebFetcher_input_schema(input_schema):
    url: str = Field(description="Target URL; must include a scheme (e.g. https://)")
    method: str = Field(
        default="GET",
        description="HTTP method: GET / POST / PUT / DELETE, etc."
    )
    extract_text: bool = Field(
        default=True,
        description="For HTML pages, whether to extract body text; False returns raw HTML"
    )
    download_path: str = Field(
        default="",
        description="If an absolute path is given, save the response bytes as-is to that file (for PDFs, images, archives, and other binaries)"
    )
    timeout: int = Field(
        default=30,
        description="Request timeout in seconds"
    )


class WebFetcher_output_schema(output_schema):
    is_success: bool = Field(description="Whether the request succeeded")
    status_code: int = Field(default=0, description="HTTP status code")
    content: str = Field(default="", description="Extracted text or raw HTML (empty in download mode)")
    downloaded_path: str = Field(default="", description="Absolute local path saved in download mode")
    error: str = Field(default="", description="Error message on failure")


class _HTMLTextExtractor(HTMLParser):
    """极简 HTML 文本提取器。"""

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


class WebFetcher(Tool):
    tool_id: str = 't-7'
    tool_name: str = 'web_fetch'
    tool_description: str = description
    input_schema: Any = WebFetcher_input_schema
    output_schema: Any = WebFetcher_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: WebFetcher_input_schema,
        session: Session
    ) -> WebFetcher_output_schema:
        url = user_input.url.strip()
        method = user_input.method.upper()
        extract_text = user_input.extract_text
        download_path = user_input.download_path.strip()
        timeout = user_input.timeout

        if not url:
            return WebFetcher_output_schema(is_success=False, error="URL must not be empty.")

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return WebFetcher_output_schema(is_success=False, error=f"Invalid URL: {url}")

        if method not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'):
            return WebFetcher_output_schema(is_success=False, error=f"Unsupported HTTP method: {method}")

        try:
            import httpx
        except ImportError:
            return WebFetcher_output_schema(
                is_success=False,
                error="Missing HTTP dependency httpx. Install with: pip install httpx"
            )

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers={
                        'User-Agent': (
                            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        )
                    }
                )
                response.raise_for_status()
        except Exception as e:
            return WebFetcher_output_schema(is_success=False, error=f"Request failed: {str(e)}")

        # 下载模式：原样保存字节到本地
        if download_path:
            try:
                os.makedirs(os.path.dirname(download_path), exist_ok=True)
                with open(download_path, 'wb') as f:
                    f.write(response.content)
                return WebFetcher_output_schema(
                    is_success=True,
                    status_code=response.status_code,
                    downloaded_path=download_path
                )
            except Exception as e:
                return WebFetcher_output_schema(
                    is_success=False,
                    status_code=response.status_code,
                    error=f"Failed to save file: {str(e)}"
                )

        # 非下载模式：按文本处理
        content_type = response.headers.get('content-type', '').lower()
        is_html = 'text/html' in content_type

        # PDF/二进制防护：文本模式下返回解码后的二进制毫无意义，
        # 且动辄数 MB 的乱码会直接把上下文撑爆（百万级 token）。
        is_pdf = (
            'application/pdf' in content_type
            or parsed.path.lower().endswith('.pdf')
            or response.content[:5] == b'%PDF-'
        )
        if is_pdf:
            return WebFetcher_output_schema(
                is_success=False,
                status_code=response.status_code,
                error=(
                    f"The target is a PDF file (~{len(response.content) // 1024} KB); "
                    "text fetch is not suitable for PDF. Use download_path to save it locally, "
                    "then extract with the read tool."
                )
            )

        try:
            raw_text = response.text
        except Exception as e:
            return WebFetcher_output_schema(
                is_success=False,
                status_code=response.status_code,
                error=f"Failed to decode response body: {str(e)}"
            )

        if is_html and extract_text:
            extractor = _HTMLTextExtractor()
            try:
                extractor.feed(raw_text)
            except Exception:
                pass
            title = extractor.get_title()
            text = extractor.get_text()
            # 把标题放在最前面
            if title:
                text = f"[Title]: {title}\n\n{text}"
            content = text
        else:
            content = raw_text

        return WebFetcher_output_schema(
            is_success=True,
            status_code=response.status_code,
            content=content
        )


def get_class():
    return WebFetcher
