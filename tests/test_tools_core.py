import os

import pytest

from cloudra.tools import get_tools_lst


def test_tool_loading():
    """测试工具加载机制和缓存。"""
    tools = get_tools_lst()
    assert len(tools) > 0
    assert any(t.tool_name == 'bash' for t in tools)
    assert any(t.tool_name == 'edit' for t in tools)

    # 测试缓存
    tools_again = get_tools_lst()
    assert tools is tools_again


def test_skill_loader_cache_invalidates_when_manifest_changes(
    tmp_path,
    monkeypatch,
):
    from cloudra.base import skill_class

    skills = tmp_path / "skills"
    skill_file = skills / "live" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: live\ndescription: v1\n---\ncontent-v1",
        encoding="utf-8",
    )
    monkeypatch.setattr(skill_class.skill_loader, "base_path", str(skills))
    skill_class._SKILL_DATAS_CACHE.clear()

    assert skill_class.skill_loader().get_content("live") == "content-v1"
    skill_file.write_text(
        "---\nname: live\ndescription: v2\n---\ncontent-v2",
        encoding="utf-8",
    )
    assert skill_class.skill_loader().get_content("live") == "content-v2"

@pytest.mark.asyncio
async def test_bash_permission():
    """测试 bash 的权限识别。"""
    from cloudra.tools.Bashtool.bash import Bash
    tool = Bash()

    # review 修复：subagent 为 None 时不再默认放行全部权限，只允许只读命令，
    # 防止注入空子 Agent 获得完整执行权限。
    assert tool.has_command_permission("ls -la") is True
    assert tool.has_command_permission("rm -rf /") is False

def test_write_schema():
    """测试 Write 的 Schema 校验。"""
    from cloudra.tools.Writetool.write import Write, Write_input_schema
    tool = Write()

    # 正确参数
    input_data = Write_input_schema(path="test.txt", content="hello")
    assert input_data.path == "test.txt"
    assert "expected_sha256" not in Write_input_schema.model_fields

    # 验证 tool 属性
    assert tool.tool_name == 'write'
    assert tool.is_write() is True


def test_edit_schema_keeps_nested_operation_definition():
    from cloudra.tools.Writetool.edit import Edit_input_schema

    parameters = Edit_input_schema.to_parameters_schema()
    assert parameters["properties"]["edits"]["items"]["$ref"] == "#/$defs/EditOperation"
    assert parameters["$defs"]["EditOperation"]["additionalProperties"] is False


def test_browser_schema():
    """测试 HeadlessBrowser 工具 Schema。"""
    from cloudra.tools.Browsertool.browser import HeadlessBrowser, HeadlessBrowser_input_schema

    tool = HeadlessBrowser()
    assert tool.tool_name == 'browser'
    assert tool.is_read() is True

    inp = HeadlessBrowser_input_schema(url='https://example.com', action='fetch')
    assert inp.url == 'https://example.com'
    assert inp.action == 'fetch'
    assert inp.max_length == 0


@pytest.mark.asyncio
async def test_bash_oversized_output_offloads_to_workspace(tmp_path, mock_session):
    """超大 stdout 落盘到 .cloudra/tool_output/，observation 只回截断摘要 + 路径。"""
    from types import SimpleNamespace

    from cloudra.tools.Bashtool.bash import Bash, Bash_input_schema
    from cloudra.tools.core.observation_offload import MAX_OBSERVATION_CHARS, TOOL_OUTPUT_DIR
    from cloudra.tools.core.permission_model import Permission

    big = "x" * (MAX_OBSERVATION_CHARS + 5_000) + "\n"
    (tmp_path / "big.txt").write_text(big, encoding="utf-8")

    subagent = SimpleNamespace(
        working_directory=str(tmp_path),
        permission_all=lambda: (
            Permission.READ | Permission.WRITE | Permission.SCRIPT | Permission.DESTRUCTIVE
        ),
    )
    tool = Bash(subagent=subagent)
    result = await tool.tool_call(
        Bash_input_schema(command="cat big.txt", task_description="read big file"),
        mock_session,
    )

    assert result.exit_code == 0
    assert len(result.result) < MAX_OBSERVATION_CHARS
    assert "`read`" in result.result
    assert "offset" in result.result
    assert TOOL_OUTPUT_DIR.replace(os.sep, "/") in result.result

    dumped = list((tmp_path / TOOL_OUTPUT_DIR).glob("bash-*.log"))
    assert len(dumped) == 1
    assert dumped[0].read_text(encoding="utf-8") == big


@pytest.mark.asyncio
async def test_bash_oversized_output_fallback_truncates(tmp_path, mock_session, monkeypatch):
    """落盘失败时优雅降级为纯截断并注明，工具本身不炸。"""
    from types import SimpleNamespace

    import cloudra.tools.core.observation_offload as offload_mod
    from cloudra.tools.Bashtool.bash import Bash, Bash_input_schema
    from cloudra.tools.core.observation_offload import MAX_OBSERVATION_CHARS
    from cloudra.tools.core.permission_model import Permission

    (tmp_path / "big.txt").write_text("y" * (MAX_OBSERVATION_CHARS + 5_000), encoding="utf-8")

    def _failing_write(path, content, encoding="utf-8"):
        raise OSError("disk full")

    monkeypatch.setattr(offload_mod, "atomic_write_text", _failing_write)
    subagent = SimpleNamespace(
        working_directory=str(tmp_path),
        permission_all=lambda: (
            Permission.READ | Permission.WRITE | Permission.SCRIPT | Permission.DESTRUCTIVE
        ),
    )
    tool = Bash(subagent=subagent)
    result = await tool.tool_call(
        Bash_input_schema(command="cat big.txt", task_description="read big file"),
        mock_session,
    )

    assert result.exit_code == 0
    assert len(result.result) < MAX_OBSERVATION_CHARS
    assert "could not be saved" in result.result


@pytest.mark.asyncio
async def test_bash_small_output_untouched(tmp_path, mock_session):
    """阈值以下的输出原样返回，不触发落盘。"""
    from types import SimpleNamespace

    from cloudra.tools.Bashtool.bash import Bash, Bash_input_schema
    from cloudra.tools.core.permission_model import Permission

    subagent = SimpleNamespace(
        working_directory=str(tmp_path),
        permission_all=lambda: Permission.READ,
    )
    tool = Bash(subagent=subagent)
    result = await tool.tool_call(
        Bash_input_schema(command="ls", task_description="list files"),
        mock_session,
    )

    assert result.exit_code == 0
    assert "Full output" not in result.result
    assert not (tmp_path / ".cloudra").exists()
