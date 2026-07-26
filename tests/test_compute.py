import os
import subprocess
from pathlib import Path

import pytest

from cloudra.compute_utils import (
    build_calculator_cmd,
    check_calculator_script,
    check_job_type,
    get_log_path,
)
from cloudra.context_manager import ContextManager
from cloudra.tools.Chemtool.submit_compute_job import (
    SubmitComputeJob,
    SubmitComputeJob_input_schema,
)


@pytest.fixture
def mock_calc_workdir(tmp_path, monkeypatch):
    """构造一个带 mock 计算程序的任务目录。"""
    workdir = tmp_path / "calc_task"
    workdir.mkdir()

    # mock g16：放到临时 bin 目录并加入 PATH
    bindir = tmp_path / "bin"
    bindir.mkdir()
    g16 = bindir / "g16"
    # mock g16：输出一个 cclib 可解析的最小 Gaussian log
    g16.write_text("""#!/bin/bash
INPUT_FILE="$1"
BASENAME=$(basename "$INPUT_FILE" .gjf)
WORKDIR=$(cd "$(dirname \"$INPUT_FILE\")" && pwd)
LOG="$WORKDIR/${BASENAME}.log"
cat > "$LOG" <<'EOF'
 Gaussian, Inc.
                          Gaussian 16:  ES64L-G16RevA.03

 Cite this work as:
 Gaussian 16, Revision A.03, M. J. Frisch et al.

 SCF Done:  E(RHF) =  -1.1175059892     A.U. after    8 cycles
            Convg  =    0.2571D-08             -V/T =  2.0031
 S**2 =   0.0000
 Population analysis using the SCF density.
 Orbital energies:
  1 0.000000
          1          2
    1   0.000000   0.000000
 Normal termination of Gaussian 16 at ...
EOF
exit 0
""")
    g16.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        str(bindir) + os.pathsep + os.environ.get("PATH", ""),
    )

    # mock calculator.sh：直接通过 PATH 调用 g16，g16 会写出 .log
    script = """#!/bin/bash
INPUT_FILE=\"$1\"
JOB_TYPE=\"$2\"
WORKDIR=$(cd \"$(dirname \"$INPUT_FILE\")\" && pwd)
cd \"$WORKDIR\"
if [ \"$JOB_TYPE\" = \"gaussian\" ]; then
    g16 \"$INPUT_FILE\"
else
    echo \"unsupported job_type: $JOB_TYPE\" >&2
    exit 1
fi
"""
    calc_sh = workdir / "calculator.sh"
    calc_sh.write_text(script)
    calc_sh.chmod(0o755)

    # mock 输入文件
    gjf = workdir / "h2.gjf"
    gjf.write_text("#p HF/3-21G\n\nH2 single point\n\n0 1\nH 0 0 0\nH 0 0 0.74\n")

    return str(workdir)


@pytest.fixture
def mock_calc_workdir_fail(tmp_path, monkeypatch):
    """构造一个 calculator 会失败的任务目录。"""
    workdir = tmp_path / "calc_task_fail"
    workdir.mkdir()

    bindir = tmp_path / "bin_fail"
    bindir.mkdir()
    g16 = bindir / "g16"
    g16.write_text("#!/bin/bash\necho 'mock g16 failed' >&2\nexit 1\n")
    g16.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        str(bindir) + os.pathsep + os.environ.get("PATH", ""),
    )

    script = """#!/bin/bash
INPUT_FILE=\"$1\"
JOB_TYPE=\"$2\"
WORKDIR=$(cd \"$(dirname \"$INPUT_FILE\")\" && pwd)
cd \"$WORKDIR\"
g16 \"$INPUT_FILE\"
"""
    calc_sh = workdir / "calculator.sh"
    calc_sh.write_text(script)
    calc_sh.chmod(0o755)

    gjf = workdir / "h2.gjf"
    gjf.write_text("#p HF/3-21G\n\nH2 single point\n\n0 1\nH 0 0 0\nH 0 0 0.74\n")

    return str(workdir)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """使用临时数据目录隔离数据库和上下文。"""
    data_dir = tmp_path / "cloudra_data"
    data_dir.mkdir()

    from cloudra.config import get_config, reload_config

    # 强制重新加载配置，指向临时目录
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    cfg = get_config()
    cfg.data_dir = data_dir
    cfg._ensure_dirs()

    from cloudra.database import ConversationDB

    # 初始化 conversation-scoped 数据库
    ConversationDB("test_conv").init()

    return str(data_dir)


class MockAgent:
    """用于测试的最小 Agent 替身。"""
    def __init__(self, agent_id, conv_id):
        self.id = agent_id
        self.conversation_id = conv_id


def test_check_job_type_missing_executable(tmp_path, monkeypatch):
    """工作目录和系统 PATH 都缺少计算程序时应返回失败。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr("cloudra.compute_utils.shutil.which", lambda _bin: None)
    ok, msg = check_job_type("gaussian", str(empty_dir))
    assert ok is False
    assert "缺少" in msg


def test_check_job_type_gaussian_in_path(tmp_path, monkeypatch):
    """工作目录没有 g16，但系统 PATH 中有 g16 时 Gaussian 检查应通过。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    def fake_which(name):
        return "/usr/bin/g16" if name == "g16" else None

    monkeypatch.setattr("cloudra.compute_utils.shutil.which", fake_which)
    ok, msg = check_job_type("gaussian", str(empty_dir))
    assert ok is True
    assert msg == ""


def test_check_job_type_with_executable(mock_calc_workdir):
    """工作目录有 g16 时 Gaussian 检查应通过。"""
    ok, msg = check_job_type("gaussian", mock_calc_workdir)
    assert ok is True
    assert msg == ""


def test_check_calculator_script_local(mock_calc_workdir):
    """优先使用工作目录下的 calculator.sh。"""
    ok, path = check_calculator_script(mock_calc_workdir)
    assert ok is True
    assert path == os.path.join(mock_calc_workdir, "calculator.sh")


def test_build_calculator_cmd(mock_calc_workdir):
    """构建 calculator 命令：[bash, calculator.sh, 输入文件, 任务类型]。"""
    gjf = os.path.join(mock_calc_workdir, "h2.gjf")
    ok, cmd, msg = build_calculator_cmd(gjf, "gaussian")
    assert ok is True
    assert cmd[1].endswith("calculator.sh")
    assert cmd[2] == gjf
    assert cmd[3] == "gaussian"


def test_get_log_path():
    """根据输入文件路径与任务类型推导正确的日志路径。"""
    assert get_log_path("/tmp/test.gjf", job_type="gaussian") == "/tmp/test.log"
    assert get_log_path("/tmp/test.gjf", job_type="orca") == "/tmp/test.out"
    assert get_log_path("/tmp/test.gjf", job_type="vasp") == "/tmp/test.out"


@pytest.mark.asyncio
async def test_submit_compute_job_sync_success(isolated_db, mock_calc_workdir):
    """同步模式成功执行 H2 单点能任务。"""
    gjf = os.path.join(mock_calc_workdir, "h2.gjf")
    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(input_file=gjf, job_type="gaussian", is_async=False),
        session=None,
    )

    assert result.is_success is True
    assert result.state == "done"
    assert result.job_dir == mock_calc_workdir
    assert "运行完毕" in result.message


@pytest.mark.asyncio
async def test_submit_compute_job_sync_failure(isolated_db, mock_calc_workdir_fail):
    """同步模式 calculator 失败时应返回 failed。"""
    gjf = os.path.join(mock_calc_workdir_fail, "h2.gjf")
    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(input_file=gjf, job_type="gaussian", is_async=False),
        session=None,
    )

    assert result.is_success is False
    assert "运行计算任务失败" in result.message


@pytest.mark.asyncio
async def test_submit_compute_job_missing_executable(isolated_db, tmp_path, monkeypatch):
    """缺少计算程序时应直接返回失败，不写数据库。"""
    workdir = tmp_path / "no_exe"
    workdir.mkdir()
    gjf = workdir / "h2.gjf"
    gjf.write_text("#p HF/3-21G\n\nH2\n\n0 1\nH 0 0 0\nH 0 0 0.74\n")

    monkeypatch.setattr("cloudra.compute_utils.shutil.which", lambda _bin: None)

    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(input_file=str(gjf), job_type="gaussian", is_async=False),
        session=None,
    )

    assert result.is_success is False
    assert "缺少" in result.message


@pytest.mark.asyncio
async def test_submit_compute_job_async_creates_record(isolated_db, mock_calc_workdir):
    """异步模式应在数据库创建 ready 记录。"""
    gjf = os.path.join(mock_calc_workdir, "h2.gjf")
    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(input_file=gjf, job_type="gaussian", is_async=True),
        session=None,
    )

    assert result.is_success is True
    assert result.state == "ready"
    assert result.job_id > 0


@pytest.mark.asyncio
async def test_context_manager_load_and_append(isolated_db):
    """ContextManager 能加载初始上下文并追加消息。"""
    cm = ContextManager(
        agent_id="a-0",
        conversation_id="test_conv",
        prompt="You are a helpful assistant.",
        query="hello",
    )

    ctx = await cm.load()
    assert len(ctx) == 2
    assert ctx[0]["role"] == "system"
    assert ctx[1]["role"] == "user"
    assert ctx[1]["content"] == "hello"

    await cm.append({"role": "assistant", "content": "hi there"})
    ctx = await cm.load()
    assert len(ctx) == 3
    assert ctx[2]["content"] == "hi there"


@pytest.mark.asyncio
async def test_context_manager_poll_external_events(isolated_db):
    """ContextManager 能轮询并消费外部事件。"""
    await ContextManager.inject_event(
        conversation_id="test_conv",
        agent_id="a-0",
        event_type="email",
        content="用户发来新邮件",
    )

    cm = ContextManager(
        agent_id="a-0",
        conversation_id="test_conv",
        prompt="You are a helpful assistant.",
        query="hello",
    )

    events = await cm.poll_external_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "email"
    assert "新邮件" in events[0]["content"]

    # 再次轮询应无 pending 事件
    events = await cm.poll_external_events()
    assert len(events) == 0


def test_calculator_script_help():
    """calculator.sh 参数不足时应返回非零退出码。"""
    script_path = Path(__file__).parent.parent / "cloudra" / "calculator.sh"
    result = subprocess.run(
        [str(script_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "用法" in result.stderr


def test_calculator_script_missing_input():
    """calculator.sh 输入文件不存在时应返回非零退出码。"""
    script_path = Path(__file__).parent.parent / "cloudra" / "calculator.sh"
    result = subprocess.run(
        [str(script_path), "/nonexistent/path.gjf", "gaussian"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "输入文件不存在" in result.stderr


@pytest.mark.asyncio
async def test_context_manager_session_isolation(isolated_db):
    """同一 conversation_id 下，不同 session_id 的上下文文件应相互隔离。"""
    cm1 = ContextManager(
        agent_id="a-1",
        conversation_id="shared_conv",
        prompt="You are agent a-1.",
        query="task 1",
        session_id="session_1",
    )
    await cm1.append({"role": "assistant", "content": "result from task 1"})

    cm2 = ContextManager(
        agent_id="a-1",
        conversation_id="shared_conv",
        prompt="You are agent a-1.",
        query="task 2",
        session_id="session_2",
    )
    ctx2 = await cm2.load()

    # ctx2 应该是初始上下文 [system, user query]，不包含 task 1 的消息
    assert len(ctx2) == 2
    assert ctx2[0]["role"] == "system"
    assert ctx2[1]["role"] == "user"
    assert ctx2[1]["content"] == "task 2"
    assert not any("task 1" in str(msg.get("content", "")) for msg in ctx2)


@pytest.mark.asyncio
async def test_subagent_launcher_no_template_pollution(isolated_db):
    """SubAgentLauncher 使用类实例化（注册表存类），全局模板不收污染。"""
    from cloudra.database import ConversationDB
    from cloudra.subagents import Subagent_hash
    from cloudra.tools.Managetool.subagent_launcher import SubAgentLauncher, SubAgentLauncher_input_schema

    ConversationDB("parent_conv").init()

    tool = SubAgentLauncher()
    tool.subagent = MockAgent("a-0", "parent_conv")

    hash_before = Subagent_hash()
    agent_cls = hash_before.get("a-1")
    assert agent_cls is not None

    input_inst = SubAgentLauncher_input_schema(
        agent_id="a-1",
        query="new task for a-1",
        is_wait=False,
    )
    result = await tool.tool_call(input_inst, session=None)

    assert result.session_id.startswith("a-1_task")
    assert result.act_agent is not None

    hash_after = Subagent_hash()
    agent_cls_after = hash_after.get("a-1")
    assert agent_cls_after is agent_cls
