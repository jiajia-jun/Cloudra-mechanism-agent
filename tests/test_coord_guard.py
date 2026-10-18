"""手写坐标守卫（write / edit / bash，放行+警告）测试。"""

import hashlib
from types import SimpleNamespace

import pytest

from cloudra.persistence.database import ConversationDB
from cloudra.tools.Bashtool.bash import Bash, Bash_input_schema
from cloudra.tools.core.coord_guard import (
    count_consecutive_coord_lines,
    handwritten_coord_warning,
)
from cloudra.tools.core.permission_model import Permission
from cloudra.tools.Writetool.edit import Edit, Edit_input_schema
from cloudra.tools.Writetool.write import Write, Write_input_schema

_XYZ_BLOCK = (
    "C   1.662573  -0.673401   0.051393\n"
    "C   1.662475   0.673655   0.051429\n"
    "H   1.745007  -1.243234  -0.876805\n"
)


def _subagent(root) -> SimpleNamespace:
    # 工作区写管线会把审批/变更记录落到会话库，先建库。
    ConversationDB(f"test-{root.name}").init()
    return SimpleNamespace(
        working_directory=str(root),
        conversation_id=f"test-{root.name}",
        name="coder",
        known_file_sha256=lambda _path: None,
        permission_all=lambda: (
            Permission.READ | Permission.WRITE | Permission.SCRIPT | Permission.DESTRUCTIVE
        ),
    )


async def _approve(self, session, details="", tool_args=None):
    return True, None


def test_coord_line_counter():
    assert count_consecutive_coord_lines(_XYZ_BLOCK) == 3
    # 不足 3 行不判定为坐标块
    assert count_consecutive_coord_lines("C  0.0  0.0  0.0\nC  1.0  0.0  0.0\n") == 2
    # 散文与表格不误伤
    assert count_consecutive_coord_lines("| C2H4 | -78.5355 | opt/eth.log |\n文本") == 0


@pytest.mark.parametrize("coordinates", [
    "0 1 -2",
    "1e2 -2E-3 +3e0",
    ".5 -.25 +1.",
])
def test_warning_detects_complete_numeric_coordinate_tokens(coordinates):
    block = "\n".join(f"{symbol} {coordinates}" for symbol in ("C", "H", "O"))

    assert count_consecutive_coord_lines(block) == 3
    assert handwritten_coord_warning(block, path="typed.xyz") is not None


@pytest.mark.parametrize("line", [
    "C nan 0 0", "C inf 0 0", "C 1e999 0 0", "C 1_000 0 0",
    "C 0 0 0 trailing", "Carbon 0 0 0", "C 0 0", "C １ 0 0",
])
def test_coord_counter_rejects_incomplete_or_invalid_tokens(line):
    assert count_consecutive_coord_lines(f"C 0.0 0.0 0.0\n{line}\nH 1.0 0.0 0.0") == 1


def test_warning_only_for_geometry_paths():
    assert handwritten_coord_warning(_XYZ_BLOCK, path="ts1.gjf") is not None
    assert handwritten_coord_warning(_XYZ_BLOCK, path="o3.xyz") is not None
    # 报告里嵌入 xyz 块是正当内容
    assert handwritten_coord_warning(_XYZ_BLOCK, path="report.md") is None
    # bash 路径（path=None）要求命令提及几何扩展名
    assert handwritten_coord_warning(_XYZ_BLOCK, path=None) is None
    assert handwritten_coord_warning(_XYZ_BLOCK + "# ts.gjf", path=None) is not None
    # 警告里点破绕过 supervisor/DAG 审查
    warning = handwritten_coord_warning(_XYZ_BLOCK, path="ts1.gjf")
    assert "Supervisor" in warning and "DAG" in warning


@pytest.mark.asyncio
async def test_write_warns_but_writes_handwritten_coords(tmp_path, monkeypatch):
    """命中手写坐标时照常写入，只在返回消息里附警告（不硬拦）。"""
    monkeypatch.setattr(Write, "ensure_safety", _approve)
    tool = Write(subagent=_subagent(tmp_path))
    out = await tool.tool_call(
        Write_input_schema(
            path="ts3_qst2.gjf",
            content=f"%chk=ts.chk\n#p opt b3lyp/def2svp\n\nt\n\n0 1\n{_XYZ_BLOCK}",
        ),
        SimpleNamespace(id="s1"),
    )
    assert out.is_written
    assert "handwritten coordinates" in out.message
    assert (tmp_path / "ts3_qst2.gjf").exists()


@pytest.mark.asyncio
async def test_write_allows_plain_text(tmp_path, monkeypatch):
    monkeypatch.setattr(Write, "ensure_safety", _approve)
    tool = Write(subagent=_subagent(tmp_path))
    out = await tool.tool_call(
        Write_input_schema(path="notes.md", content="# 记录\n没有坐标。"),
        SimpleNamespace(id="s1"),
    )
    assert out.is_written


@pytest.mark.asyncio
async def test_edit_warns_on_coord_insertion(tmp_path, monkeypatch):
    monkeypatch.setattr(Edit, "ensure_safety", _approve)
    content = "%chk=ts.chk\n#p opt b3lyp/def2svp\n"
    target = tmp_path / "ts.gjf"
    target.write_text(content, encoding="utf-8")
    actor = _subagent(tmp_path)
    actor.known_file_sha256 = lambda _path: hashlib.sha256(content.encode("utf-8")).hexdigest()
    tool = Edit(subagent=actor)
    out = await tool.tool_call(
        Edit_input_schema(
            path="ts.gjf",
            edits=[{
                "old_str": "#p opt b3lyp/def2svp",
                "new_str": f"#p opt b3lyp/def2svp\n\n0 1\n{_XYZ_BLOCK}",
            }],
        ),
        SimpleNamespace(id="s1"),
    )
    assert out.is_written
    assert "handwritten coordinates" in out.message
    assert "0 1" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_bash_heredoc_coords_no_inline_warning(tmp_path, monkeypatch):
    """heredoc 写坐标不拦截：命令照常执行；警告已迁往 GuidanceStage 的 pin
    上下文通道（行为引导不进工具返回），工具结果里不再前置。"""
    monkeypatch.setattr(Bash, "ensure_safety", _approve)
    tool = Bash(subagent=_subagent(tmp_path))
    command = f"cat > ts.gjf <<'EOF'\n%chk=ts.chk\n0 1\n{_XYZ_BLOCK}EOF"
    out = await tool.tool_call(
        Bash_input_schema(command=command, task_description="写输入"),
        SimpleNamespace(id="s1"),
    )
    assert out.exit_code == 0
    assert "handwritten coordinates" not in out.result
    assert (tmp_path / "ts.gjf").exists()


@pytest.mark.asyncio
async def test_bash_allows_normal_commands(tmp_path):
    tool = Bash(subagent=_subagent(tmp_path))
    out = await tool.tool_call(
        Bash_input_schema(command="echo hello", task_description="测试"),
        SimpleNamespace(id="s1"),
    )
    assert out.exit_code == 0
    assert "hello" in out.result
