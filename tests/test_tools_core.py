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
