"""Bash 习惯守卫（bash_habit_guard）单测 + bashtools / reAct harness 集成。"""

import pytest

from cloudra.persistence.database import ConversationDB
from cloudra.tools.core.bash_habit_guard import (
    bash_file_write_warning,
    bash_habit_warning,
)

# --------------------------------------------------------------------------
# 纯函数：bash_file_write_warning（bash 向工作区文件"键入内容/原地编辑"）
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "cat > f.txt <<EOF\ncontent\nEOF",
    "cat >> log.txt <<'EOF'\nline\nEOF",
    "cat <<EOF | tee out.txt\nline\nEOF",
    "echo hello > log.txt",
    "printf '%s\n' x >> data.txt",
    "ls | tee out.txt",
    "sed -i 's/a/b/' file.txt",
    "awk -i inplace '{print}' f.txt",
    "perl -pi -e 's/a/b/' f.txt",
    "> empty.txt",
])
def test_file_write_detection(cmd):
    assert bash_file_write_warning(cmd) is not None


@pytest.mark.parametrize("cmd", [
    "ls -la",
    "cat file.txt",
    "grep foo bar.txt",
    "echo hello",
    "python script.py > run.log 2>&1",
    "g16 input.gjf > g16.out",
    "cat a.txt b.txt > c.txt",
    "echo hi > /dev/null",
    "ls | tee /dev/null",
    "ls | tee",
])
def test_file_write_no_false_positive(cmd):
    assert bash_file_write_warning(cmd) is None


# --------------------------------------------------------------------------
# 纯函数：bash_habit_warning（长上下文下的习惯性回退提示）
# --------------------------------------------------------------------------

def test_habit_warning_short_context_no_warning():
    assert bash_habit_warning(
        "g16 a.gjf", history_tokens=1000, context_window=128000
    ) is None


def test_habit_warning_compute_in_long_context():
    warning = bash_habit_warning(
        "g16 a.gjf > out.log", history_tokens=80_000, context_window=128_000
    )
    assert warning is not None
    assert "g16" in warning
    assert "DAG" in warning


def test_habit_warning_consecutive_bash_in_long_context():
    warning = bash_habit_warning(
        "ls -la", history_tokens=80_000, context_window=128_000, consecutive_bash=3
    )
    assert warning is not None


def test_habit_warning_single_normal_bash_no_warning():
    assert bash_habit_warning(
        "ls -la", history_tokens=80_000, context_window=128_000, consecutive_bash=1
    ) is None


def test_habit_warning_missing_window_or_tokens():
    assert bash_habit_warning(
        "g16 a.gjf", history_tokens=None, context_window=128_000
    ) is None
    assert bash_habit_warning("g16 a.gjf", history_tokens=80_000, context_window=0) is None


# --------------------------------------------------------------------------
# bashtools 集成：bash 写文件命中时照常执行，结果里附警告（不硬拦）
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bashtools_warns_but_runs_file_write(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from cloudra.tools.Bashtool.bashtools import Bashtools, Bashtools_input_schema
    from cloudra.tools.core.permission_model import Permission

    ConversationDB(f"test-{tmp_path.name}").init()
    agent = SimpleNamespace(
        working_directory=str(tmp_path),
        conversation_id=f"test-{tmp_path.name}",
        name="coder",
        permission_all=lambda: (
            Permission.READ | Permission.WRITE | Permission.SCRIPT | Permission.DESTRUCTIVE
        ),
    )

    async def _approve(self, session, details="", tool_args=None):
        return True, None

    monkeypatch.setattr(Bashtools, "ensure_safety", _approve)
    tool = Bashtools(subagent=agent)
    out = await tool.tool_call(
        Bashtools_input_schema(command="echo hello > note.txt", task_description="写文件"),
        SimpleNamespace(id="s1"),
    )
    assert out.exit_code == 0
    assert "bash 习惯" in out.result
    assert (tmp_path / "note.txt").read_text() == "hello\n"


# --------------------------------------------------------------------------
# reAct harness 集成：长上下文下调用 bash 时注入系统警告
# --------------------------------------------------------------------------

def _make_react(tmp_path, monkeypatch):
    from cloudra.core.agent import Follower
    from cloudra.core.react import reAct

    db_path = str(tmp_path / "conv.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr(
        "cloudra.core.react.get_database_path", lambda _cid, _db=db_path: _db
    )
    agent = Follower(
        id="a-1",
        name="tester",
        prompt="测试",
        query="测试问题",
        conversation_id="conv",
    )
    return reAct(agent)


@pytest.mark.asyncio
async def test_react_injects_bash_habit_warning_in_long_context(tmp_path, monkeypatch):
    react = _make_react(tmp_path, monkeypatch)
    react.agent.context_window = 2000
    # 阈值 = context_window * 0.5 = 1000 token。TokenEstimator 已是 tiktoken
    # 精确计数，重复字符会被 BPE 大幅压缩（"x"*5000 ≈ 630 token），填充量要
    # 保证精确计数与启发式回退（约 len/4）两种模式下都稳超阈值。
    await react.agent.update_context({"role": "system", "content": "x" * 20000})

    await react._check_bash_habit("bashtools", {"command": "g16 ts.gjf"})

    context = await react.agent.get_context()
    assert any("bash 习惯" in str(m.get("content", "")) for m in context)
    assert react._consecutive_bash == 1


@pytest.mark.asyncio
async def test_react_no_warning_in_short_context(tmp_path, monkeypatch):
    react = _make_react(tmp_path, monkeypatch)

    await react._check_bash_habit("bashtools", {"command": "g16 ts.gjf"})

    context = await react.agent.get_context()
    assert not any("bash 习惯" in str(m.get("content", "")) for m in context)
    assert react._consecutive_bash == 1


@pytest.mark.asyncio
async def test_react_resets_bash_counter_on_other_tools(tmp_path, monkeypatch):
    react = _make_react(tmp_path, monkeypatch)

    await react._check_bash_habit("bashtools", {"command": "ls -la"})
    assert react._consecutive_bash == 1
    await react._check_bash_habit("text_writer", {"filepath": "a.txt"})
    assert react._consecutive_bash == 0
