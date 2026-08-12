"""手写坐标守卫（text_writer / edit_file / bashtools，放行+警告）与会话复活状态测试。"""

import hashlib
from types import SimpleNamespace

import pytest

from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.tools.Bashtool.bashtools import Bashtools, Bashtools_input_schema
from cloudra.tools.core.coord_guard import (
    count_consecutive_coord_lines,
    handwritten_coord_warning,
)
from cloudra.tools.core.permission_model import Permission
from cloudra.tools.Writetool.edit_file import EditFile, EditFile_input_schema
from cloudra.tools.Writetool.text_writer import TextWriter, TextWriter_input_schema

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
    assert "supervisor" in warning and "DAG" in warning


@pytest.mark.asyncio
async def test_text_writer_warns_but_writes_handwritten_coords(tmp_path, monkeypatch):
    """命中手写坐标时照常写入，只在返回消息里附警告（不硬拦）。"""
    monkeypatch.setattr(TextWriter, "ensure_safety", _approve)
    tool = TextWriter(subagent=_subagent(tmp_path))
    out = await tool.tool_call(
        TextWriter_input_schema(
            filepath="ts3_qst2.gjf",
            content=f"%chk=ts.chk\n#p opt b3lyp/def2svp\n\nt\n\n0 1\n{_XYZ_BLOCK}",
        ),
        SimpleNamespace(id="s1"),
    )
    assert out.is_written
    assert "手写坐标" in out.message
    assert (tmp_path / "ts3_qst2.gjf").exists()


@pytest.mark.asyncio
async def test_text_writer_allows_plain_text(tmp_path, monkeypatch):
    monkeypatch.setattr(TextWriter, "ensure_safety", _approve)
    tool = TextWriter(subagent=_subagent(tmp_path))
    out = await tool.tool_call(
        TextWriter_input_schema(filepath="notes.md", content="# 记录\n没有坐标。"),
        SimpleNamespace(id="s1"),
    )
    assert out.is_written


@pytest.mark.asyncio
async def test_edit_file_warns_on_coord_insertion(tmp_path, monkeypatch):
    monkeypatch.setattr(EditFile, "ensure_safety", _approve)
    content = "%chk=ts.chk\n#p opt b3lyp/def2svp\n"
    target = tmp_path / "ts.gjf"
    target.write_text(content, encoding="utf-8")
    tool = EditFile(subagent=_subagent(tmp_path))
    out = await tool.tool_call(
        EditFile_input_schema(
            filepath="ts.gjf",
            expected_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            edits=[{
                "old_str": "#p opt b3lyp/def2svp",
                "new_str": f"#p opt b3lyp/def2svp\n\n0 1\n{_XYZ_BLOCK}",
            }],
        ),
        SimpleNamespace(id="s1"),
    )
    assert out.is_written
    assert "手写坐标" in out.message
    assert "0 1" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_bash_warns_on_heredoc_coords(tmp_path, monkeypatch):
    """heredoc 写坐标不拦截：命令照常执行，结果里附警告。"""
    monkeypatch.setattr(Bashtools, "ensure_safety", _approve)
    tool = Bashtools(subagent=_subagent(tmp_path))
    command = f"cat > ts.gjf <<'EOF'\n%chk=ts.chk\n0 1\n{_XYZ_BLOCK}EOF"
    out = await tool.tool_call(
        Bashtools_input_schema(command=command, task_description="写输入"),
        SimpleNamespace(id="s1"),
    )
    assert out.exit_code == 0
    assert "手写坐标" in out.result
    assert (tmp_path / "ts.gjf").exists()


@pytest.mark.asyncio
async def test_bash_allows_normal_commands(tmp_path):
    tool = Bashtools(subagent=_subagent(tmp_path))
    out = await tool.tool_call(
        Bashtools_input_schema(command="echo hello", task_description="测试"),
        SimpleNamespace(id="s1"),
    )
    assert out.exit_code == 0
    assert "hello" in out.result


@pytest.mark.asyncio
async def test_aresume_session_revives_completed_and_waiting(tmp_path):
    db = ConversationDB(f"resume-{tmp_path.name}").init()
    session_store.create_session_record(
        db,
        session_id="s1",
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="q",
        created_at="2026-08-12T00:00:00+00:00",
    )
    await session_store.afinalize_session(db, "s1", "completed", result="done")

    assert await session_store.aresume_session(db, "s1") is True
    async with db.aconnect() as con:
        cur = await con.execute(
            "SELECT state, finished_at, result FROM session WHERE session_id='s1'"
        )
        state, finished_at, result = await cur.fetchone()
    assert state == "running"
    assert finished_at is None
    assert result == "done"

    # 挂起（waiting）同样应被唤醒续跑
    session_store.create_session_record(
        db,
        session_id="s1b",
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="q",
        created_at="2026-08-12T00:00:00+00:00",
    )
    await session_store.asuspend_session(db, "s1b", result="挂起等后台")
    assert await session_store.aresume_session(db, "s1b") is True
    async with db.aconnect() as con:
        cur = await con.execute(
            "SELECT state, finished_at, result FROM session WHERE session_id='s1b'"
        )
        state, finished_at, result = await cur.fetchone()
    assert state == "running"
    assert finished_at is None
    assert result == "挂起等后台"

    # cancelled 是用户明确终态，绝不被唤醒覆盖
    session_store.create_session_record(
        db,
        session_id="s2",
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="q",
        created_at="2026-08-12T00:00:00+00:00",
    )
    await session_store.afinalize_session(db, "s2", "cancelled")
    assert await session_store.aresume_session(db, "s2") is False
    async with db.aconnect() as con:
        cur = await con.execute("SELECT state FROM session WHERE session_id='s2'")
        assert (await cur.fetchone())[0] == "cancelled"
