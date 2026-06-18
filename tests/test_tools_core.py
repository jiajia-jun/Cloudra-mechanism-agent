import pytest
from cloudra.tools import get_tools_lst
from cloudra.tools_class import Tool

def test_tool_loading():
    """测试工具加载机制和缓存。"""
    tools = get_tools_lst()
    assert len(tools) > 0
    assert any(t.tool_name == 'bashtools' for t in tools)
    
    # 测试缓存
    tools_again = get_tools_lst()
    assert tools is tools_again

@pytest.mark.asyncio
async def test_bashtools_permission():
    """测试 bashtools 的权限识别。"""
    from cloudra.tools.Bashtool.bashtools import Bashtools, Bashtools_input_schema
    tool = Bashtools()
    
    # 模拟没有 subagent 的情况（默认全开）
    assert tool.has_command_permission("ls -la") is True
    assert tool.has_command_permission("rm -rf /") is True

def test_text_writer_schema():
    """测试 TextWriter 的 Schema 校验。"""
    from cloudra.tools.Writetool.text_writer import TextWriter, TextWriter_input_schema
    tool = TextWriter()
    
    # 正确参数
    input_data = TextWriter_input_schema(filepath="/tmp/test.txt", content="hello")
    assert input_data.filepath == "/tmp/test.txt"
    
    # 验证 tool 属性
    assert tool.tool_name == 'text_writer'
    assert tool.is_write() is True


def test_text_writer_multiline_parsing():
    """回归测试：LLM 返回的含未转义换行符的 JSON 参数应能被正确解析并保留换行。"""
    import json
    from cloudra.tools.Writetool.text_writer import TextWriter_input_schema

    # 模拟 LLM 生成的 arguments 中直接包含换行符（未转义）
    raw_args = '{"filepath": "/tmp/multi.txt", "content": "line1\nline2\nline3"}'
    parsed = json.loads(raw_args, strict=False)
    input_data = TextWriter_input_schema(**parsed)
    assert input_data.content == "line1\nline2\nline3"


def test_subagent_hash_caching():
    """测试 Subagent_hash 在同进程内复用缓存。"""
    from cloudra.subagents import Subagent_hash

    h1 = Subagent_hash()
    h2 = Subagent_hash()
    # 复用缓存，字典对象应为同一个
    assert h1.subagents_dict is h2.subagents_dict
    assert hasattr(h1, 'a-1') or 'a-1' in h1.subagents_dict


def test_web_fetcher_schema():
    """测试 WebFetcher 工具 Schema 与 HTML 文本提取。"""
    from cloudra.tools.Browsertool.web_fetcher import (
        WebFetcher, WebFetcher_input_schema, _HTMLTextExtractor
    )

    tool = WebFetcher()
    assert tool.tool_name == 'web_fetcher'
    assert tool.is_read() is True

    inp = WebFetcher_input_schema(url='https://example.com')
    assert inp.url == 'https://example.com'
    assert inp.extract_text is True

    html = '<html><head><title>Test Page</title></head><body><p>Hello</p><script>alert(1)</script></body></html>'
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    assert extractor.get_title() == 'Test Page'
    assert extractor.get_text() == 'Hello'


def test_headless_browser_schema():
    """测试 HeadlessBrowser 工具 Schema。"""
    from cloudra.tools.Browsertool.headless_browser import (
        HeadlessBrowser, HeadlessBrowser_input_schema
    )

    tool = HeadlessBrowser()
    assert tool.tool_name == 'headless_browser'
    assert tool.is_read() is True

    inp = HeadlessBrowser_input_schema(url='https://example.com', action='fetch')
    assert inp.url == 'https://example.com'
    assert inp.action == 'fetch'
