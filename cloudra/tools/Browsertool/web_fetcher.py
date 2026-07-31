import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "通用 HTTP 抓取/下载工具：抓取网页 HTML 并提取正文文本，或把响应原样下载到本地文件。"
    "适用：已知 URL 时抓取在线文献页面、网页内容、数据文件；下载二进制文件必须提供 download_path 保存到本地。"
    "不适用：需要 JavaScript 渲染的动态页面（用 headless_browser）、按关键词找网页（用 web_search）。"
    "注意：PDF 不能用文本模式抓取（会得到乱码），请用 download_path 下载到本地后交给 pdf2md 处理。"
)


class WebFetcher_input_schema(input_schema):
    url: str = Field(description="目标 URL，必须包含协议（如 https://）")
    method: str = Field(
        default="GET",
        description="HTTP 方法：GET / POST / PUT / DELETE 等"
    )
    extract_text: bool = Field(
        default=True,
        description="对于 HTML 页面，是否提取正文文本；False 则返回原始 HTML"
    )
    download_path: str = Field(
        default="",
        description="如果提供绝对路径，则将响应内容原样保存到该文件（适合下载 PDF/图片/压缩包等二进制文件）"
    )
    timeout: int = Field(
        default=30,
        description="请求超时时间（秒）"
    )


class WebFetcher_output_schema(output_schema):
    success: bool = Field(description="是否成功")
    status_code: int = Field(default=0, description="HTTP 状态码")
    content: str = Field(default="", description="提取的文本或原始 HTML（下载模式为空）")
    downloaded_path: str = Field(default="", description="下载模式下保存的本地文件绝对路径")
    error: str = Field(default="", description="失败时的错误信息")


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
    tool_name: str = 'web_fetcher'
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
            return WebFetcher_output_schema(success=False, error="URL 不能为空。")

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return WebFetcher_output_schema(success=False, error=f"URL 格式不合法: {url}")

        if method not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'):
            return WebFetcher_output_schema(success=False, error=f"不支持的 HTTP 方法: {method}")

        try:
            import httpx
        except ImportError:
            return WebFetcher_output_schema(
                success=False,
                error="缺少 HTTP 依赖 httpx，请执行: pip install httpx"
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
            return WebFetcher_output_schema(success=False, error=f"请求失败: {str(e)}")

        # 下载模式：原样保存字节到本地
        if download_path:
            try:
                os.makedirs(os.path.dirname(download_path), exist_ok=True)
                with open(download_path, 'wb') as f:
                    f.write(response.content)
                return WebFetcher_output_schema(
                    success=True,
                    status_code=response.status_code,
                    downloaded_path=download_path
                )
            except Exception as e:
                return WebFetcher_output_schema(
                    success=False,
                    status_code=response.status_code,
                    error=f"保存文件失败: {str(e)}"
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
                success=False,
                status_code=response.status_code,
                error=(
                    f"目标是 PDF 文件（约 {len(response.content) // 1024} KB），"
                    "文本抓取不适用于 PDF。请改用 download_path 参数下载到本地后，"
                    "再用 pdf2md 工具提取内容。"
                )
            )

        try:
            raw_text = response.text
        except Exception as e:
            return WebFetcher_output_schema(
                success=False,
                status_code=response.status_code,
                error=f"解码响应内容失败: {str(e)}"
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
                text = f"【标题】: {title}\n\n{text}"
            content = text
        else:
            content = raw_text

        # 体积护栏：超大文本截断，避免一条工具结果撑爆上下文
        MAX_TEXT_CHARS = 200_000
        if len(content) > MAX_TEXT_CHARS:
            content = (
                content[:MAX_TEXT_CHARS]
                + f"\n\n[... 内容过长已截断，原始共 {len(content)} 字符，"
                "如需完整内容请分段抓取或下载到本地处理 ...]"
            )

        return WebFetcher_output_schema(
            success=True,
            status_code=response.status_code,
            content=content
        )


def get_class():
    return WebFetcher
