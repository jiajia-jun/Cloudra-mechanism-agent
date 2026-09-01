import os
import subprocess
from pathlib import Path

import pytest

from cloudra.core.message_history import JsonlMessageHistory
from cloudra.infra.compute_utils import (
    build_calculator_cmd,
    check_calculator_script,
    check_job_type,
    get_log_path,
)
from cloudra.tools.Chemtool.submit_compute_job import (
    SubmitComputeJob,
    SubmitComputeJob_input_schema,
)

_GAUSSIAN_MOCK_LOG = Path(__file__).resolve().parent / "fixtures" / "gaussian" / "water_opt_freq_g16.out"


@pytest.fixture
def mock_calc_workdir(tmp_path, monkeypatch):
    """构造一个带 mock 计算程序的任务目录。"""
    workdir = tmp_path / "calc_task"
    workdir.mkdir()

    # mock g16：放到临时 bin 目录并加入 PATH
    bindir = tmp_path / "bin"
    bindir.mkdir()
    g16 = bindir / "g16"
    # mock g16：复制 cclib 可完整解析的真实 Gaussian 日志（含坐标）
    g16.write_text(f"""#!/bin/bash
INPUT_FILE="$1"
BASENAME=$(basename "$INPUT_FILE" .gjf)
WORKDIR=$(cd "$(dirname "$INPUT_FILE")" && pwd)
LOG="$WORKDIR/${{BASENAME}}.log"
cp "{_GAUSSIAN_MOCK_LOG}" "$LOG"
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
def mock_cp2k_workdir(tmp_path, monkeypatch):
    """构造一个带 mock cp2k.popt 的任务目录，cp2k 会写出可解析的 .out。"""
    workdir = tmp_path / "calc_cp2k"
    workdir.mkdir()

    bindir = tmp_path / "bin_cp2k"
    bindir.mkdir()
    cp2k = bindir / "cp2k.popt"
    cp2k.write_text("""#!/bin/bash
OUT=""
while [ $# -gt 0 ]; do
    if [ "$1" = "-o" ]; then OUT="$2"; shift 2; else shift; fi
done
cat > "$OUT" <<'EOF'
 GLOBAL| Run type  ENERGY_FORCE
 ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]              -76.384555551223
 PROGRAM ENDED IN 0.13 SECONDS
 *** CP2K is done ***
EOF
exit 0
""")
    cp2k.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        str(bindir) + os.pathsep + os.environ.get("PATH", ""),
    )

    script = """#!/bin/bash
INPUT_FILE=\"$1\"
JOB_TYPE=\"$2\"
WORKDIR=$(cd \"$(dirname \"$INPUT_FILE\")\" && pwd)
cd \"$WORKDIR\"
if [ \"$JOB_TYPE\" = \"cp2k\" ]; then
    cp2k.popt -i \"$INPUT_FILE\" -o \"${INPUT_FILE%.*}.out\"
else
    echo \"unsupported job_type: $JOB_TYPE\" >&2
    exit 1
fi
"""
    calc_sh = workdir / "calculator.sh"
    calc_sh.write_text(script)
    calc_sh.chmod(0o755)

    inp = workdir / "h2.inp"
    inp.write_text("&GLOBAL\n  RUN_TYPE ENERGY_FORCE\n&END GLOBAL\n")

    return str(workdir)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """使用临时数据目录隔离数据库和上下文。"""
    data_dir = tmp_path / "cloudra_data"
    data_dir.mkdir()

    from cloudra.infra.config import _reset_for_tests, get_config

    # 强制重新加载配置，指向临时目录
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    _reset_for_tests()
    cfg = get_config()
    cfg.data_dir = data_dir
    cfg._ensure_dirs()

    from cloudra.persistence.database import ConversationDB

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
    monkeypatch.setattr("cloudra.infra.compute_utils.shutil.which", lambda _bin: None)
    ok, msg = check_job_type("gaussian", str(empty_dir))
    assert ok is False
    assert "missing" in msg


def test_check_job_type_gaussian_in_path(tmp_path, monkeypatch):
    """工作目录没有 g16，但系统 PATH 中有 g16 时 Gaussian 检查应通过。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    def fake_which(name):
        return "/usr/bin/g16" if name == "g16" else None

    monkeypatch.setattr("cloudra.infra.compute_utils.shutil.which", fake_which)
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
    assert get_log_path("/tmp/test.inp", job_type="cp2k") == "/tmp/test.out"


def test_allocate_gaussian_scratch_is_unique_and_safe_to_clean(tmp_path, monkeypatch):
    """并行任务必须落到 cloudra_g16_* 子目录；清理不得误删全局 SCRDIR。"""
    from cloudra.infra.compute_utils import (
        allocate_gaussian_scratch,
        cleanup_gaussian_scratch,
    )

    shared = tmp_path / "Utsu"
    shared.mkdir()
    marker = shared / "keep_me"
    marker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("GAUSS_SCRDIR", str(shared))

    a = allocate_gaussian_scratch(7, str(tmp_path / "job_a"))
    b = allocate_gaussian_scratch(8, str(tmp_path / "job_b"))
    assert a != b
    assert a.parent == shared
    assert a.name.startswith("cloudra_g16_task7_")
    assert b.name.startswith("cloudra_g16_task8_")
    (a / "Gau-1.inp").write_text("fake", encoding="utf-8")

    cleanup_gaussian_scratch(a)
    assert not a.exists()
    assert shared.exists()
    assert marker.exists()
    # 拒绝清理非 cloudra_g16_* 路径
    cleanup_gaussian_scratch(shared)
    assert shared.exists()


def test_calculator_script_isolates_shared_gauss_scrdir(tmp_path, monkeypatch):
    """回归：共用 GAUSS_SCRDIR 时 calculator 必须把 g16 关进独立子目录。"""
    from cloudra.infra.platform_utils import get_bash_path

    bash = get_bash_path()
    if not bash:
        pytest.skip("bash unavailable")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    g16 = bindir / "g16"
    g16.write_text(
        "#!/bin/bash\n"
        "echo \"SCR=$GAUSS_SCRDIR\"\n"
        "test -d \"$GAUSS_SCRDIR\" || exit 2\n"
        "base=\"${1%.gjf}\"\n"
        "printf 'ok\\n' > \"${base}.log\"\n",
        encoding="utf-8",
    )
    g16.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))

    shared = tmp_path / "Utsu"
    shared.mkdir()
    monkeypatch.setenv("GAUSS_SCRDIR", str(shared))

    gjf = tmp_path / "h2.gjf"
    gjf.write_text(
        "#p hf/sto-3g\n\ntitle\n\n0 1\nH 0 0 0\nH 0 0 0.74\n\n",
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "cloudra" / "calculator.sh"
    result = subprocess.run(
        [bash, str(script), str(gjf), "gaussian"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert "isolated GAUSS_SCRDIR=" in result.stderr
    assert "cloudra_g16_" in result.stderr
    # 任务结束后子目录应由 trap 清掉；全局 Utsu 保留
    assert shared.exists()
    assert list(shared.glob("cloudra_g16_*")) == []
    assert (tmp_path / "h2.log").exists()


def test_check_job_type_cp2k_in_path(tmp_path, monkeypatch):
    """系统 PATH 中有 cp2k.popt 时 CP2K 检查应通过。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    def fake_which(name):
        return "/opt/cp2k/bin/cp2k.popt" if name == "cp2k.popt" else None

    monkeypatch.setattr("cloudra.infra.compute_utils.shutil.which", fake_which)
    ok, msg = check_job_type("cp2k", str(empty_dir))
    assert ok is True
    assert msg == ""


def test_parse_cp2k_log_success(tmp_path):
    """CP2K 输出包含 PROGRAM ENDED 时应判定成功并提取总能量。"""
    from cloudra.runtime.monitor import _parse_cp2k_log

    log = tmp_path / "h2.out"
    log.write_text(
        " GLOBAL| Run type  ENERGY_FORCE\n"
        " ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]              -76.384555551223\n"
        " PROGRAM ENDED IN 0.13 SECONDS\n"
        " *** CP2K is done ***\n",
        encoding="utf-8",
    )
    data_dic, is_success = _parse_cp2k_log(log)
    assert is_success is True
    assert data_dic["is_success"] is True
    assert data_dic["scf_energy_hartree"] == pytest.approx(-76.384555551223)
    assert data_dic["scf_energy_ev"] == pytest.approx(-76.384555551223 * 27.211386245988)


def test_parse_cp2k_log_failure(tmp_path):
    """CP2K 输出包含 ABORT / PROGRAM FAILED 时应判定失败。"""
    from cloudra.runtime.monitor import _parse_cp2k_log

    log = tmp_path / "h2.out"
    log.write_text(
        " PROGRAM FAILED\n"
        " ABORT\n",
        encoding="utf-8",
    )
    data_dic, is_success = _parse_cp2k_log(log)
    assert is_success is False
    assert data_dic["is_success"] is False


def test_parse_cp2k_log_missing_file(tmp_path):
    """CP2K 日志缺失或为空时应返回 None。"""
    from cloudra.runtime.monitor import _parse_cp2k_log

    assert _parse_cp2k_log(tmp_path / "missing.out") is None
    empty = tmp_path / "empty.out"
    empty.write_text("", encoding="utf-8")
    assert _parse_cp2k_log(empty) is None


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
    assert "Job finished" in result.message


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
    assert "Compute job failed" in result.message


@pytest.mark.asyncio
async def test_submit_compute_job_missing_executable(isolated_db, tmp_path, monkeypatch):
    """缺少计算程序时应直接返回失败，不写数据库。"""
    workdir = tmp_path / "no_exe"
    workdir.mkdir()
    gjf = workdir / "h2.gjf"
    gjf.write_text("#p HF/3-21G\n\nH2\n\n0 1\nH 0 0 0\nH 0 0 0.74\n")

    monkeypatch.setattr("cloudra.infra.compute_utils.shutil.which", lambda _bin: None)

    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(input_file=str(gjf), job_type="gaussian", is_async=False),
        session=None,
    )

    assert result.is_success is False
    assert "missing" in result.message


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
async def test_query_compute_job_by_id(isolated_db, mock_calc_workdir):
    """按 job_id 查询：返回状态、路径与日志路径推导。"""
    from cloudra.tools.Chemtool.query_compute_job import (
        QueryComputeJob,
        QueryComputeJob_input_schema,
    )

    gjf = os.path.join(mock_calc_workdir, "h2.gjf")
    submit = SubmitComputeJob()
    submit.subagent = MockAgent("a-0", "test_conv")
    submitted = await submit.tool_call(
        SubmitComputeJob_input_schema(input_file=gjf, job_type="gaussian", is_async=True),
        session=None,
    )
    assert submitted.is_success is True

    query = QueryComputeJob()
    query.subagent = MockAgent("a-0", "test_conv")
    result = await query.tool_call(
        QueryComputeJob_input_schema(job_id=submitted.job_id), session=None,
    )

    assert result.is_success is True
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job["job_id"] == submitted.job_id
    assert job["state"] == "ready"
    assert job["path"] == gjf
    assert job["log_path"].endswith("h2.log")


@pytest.mark.asyncio
async def test_query_compute_job_list_and_missing(isolated_db, mock_calc_workdir):
    """不传 job_id 列出最近任务；查询不存在的 id 返回失败。"""
    from cloudra.tools.Chemtool.query_compute_job import (
        QueryComputeJob,
        QueryComputeJob_input_schema,
    )

    gjf = os.path.join(mock_calc_workdir, "h2.gjf")
    submit = SubmitComputeJob()
    submit.subagent = MockAgent("a-0", "test_conv")
    await submit.tool_call(
        SubmitComputeJob_input_schema(input_file=gjf, job_type="gaussian", is_async=True),
        session=None,
    )

    query = QueryComputeJob()
    query.subagent = MockAgent("a-0", "test_conv")

    listed = await query.tool_call(QueryComputeJob_input_schema(), session=None)
    assert listed.is_success is True
    assert len(listed.jobs) >= 1

    missing = await query.tool_call(QueryComputeJob_input_schema(job_id=99999), session=None)
    assert missing.is_success is False
    assert "No compute job found" in missing.message


@pytest.mark.asyncio
async def test_submit_compute_job_cp2k_sync_success(isolated_db, mock_cp2k_workdir):
    """同步模式成功执行 CP2K 单点任务。"""
    inp = os.path.join(mock_cp2k_workdir, "h2.inp")
    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(input_file=inp, job_type="cp2k", is_async=False),
        session=None,
    )

    assert result.is_success is True
    assert result.state == "done"
    assert result.job_dir == mock_cp2k_workdir
    assert "Job finished" in result.message


def test_calculator_script_cp2k(tmp_path, monkeypatch):
    """calculator.sh 的 cp2k 分支应调用 PATH 中的 cp2k 并写出 .out。"""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    cp2k = bindir / "cp2k.popt"
    cp2k.write_text("""#!/bin/bash
OUT=""
while [ $# -gt 0 ]; do
    if [ "$1" = "-o" ]; then OUT="$2"; shift 2; else shift; fi
done
echo ' PROGRAM ENDED' > "$OUT"
exit 0
""")
    cp2k.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        str(bindir) + os.pathsep + os.environ.get("PATH", ""),
    )

    script_path = Path(__file__).parent.parent / "cloudra" / "calculator.sh"
    inp = tmp_path / "h2.inp"
    inp.write_text("&GLOBAL\n&END GLOBAL\n")
    result = subprocess.run(
        [str(script_path), str(inp), "cp2k"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    out = tmp_path / "h2.out"
    assert out.exists()
    assert "PROGRAM ENDED" in out.read_text()


@pytest.mark.asyncio
async def test_message_history_load_and_append(isolated_db):
    """JsonlMessageHistory 能加载初始上下文并追加消息。"""
    cm = JsonlMessageHistory(
        agent_id="a-0",
        conversation_id="test_conv",
        initial_query="hello",
    )

    ctx = await cm.load()
    assert len(ctx) == 1
    assert ctx[0]["role"] == "user"
    assert ctx[0]["content"] == "hello"

    await cm.append({"role": "assistant", "content": "hi there"})
    ctx = await cm.load()
    assert len(ctx) == 2
    assert ctx[1]["content"] == "hi there"


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
async def test_message_history_session_isolation(isolated_db):
    """同一 conversation_id 下，不同 session_id 的上下文文件应相互隔离。"""
    cm1 = JsonlMessageHistory(
        agent_id="a-1",
        conversation_id="shared_conv",
        initial_query="task 1",
        session_id="session_1",
    )
    await cm1.append({"role": "assistant", "content": "result from task 1"})

    cm2 = JsonlMessageHistory(
        agent_id="a-1",
        conversation_id="shared_conv",
        initial_query="task 2",
        session_id="session_2",
    )
    ctx2 = await cm2.load()

    # 身份层不持久化；ctx2 只含自己的初始 query，不含 task 1 的消息。
    assert len(ctx2) == 1
    assert ctx2[0]["role"] == "user"
    assert ctx2[0]["content"] == "task 2"
    assert not any("task 1" in str(msg.get("content", "")) for msg in ctx2)


@pytest.mark.asyncio
async def test_parse_log_fail_fast_on_incomplete_gaussian_log(tmp_path):
    """缺坐标的 stub 日志不应在 parse_timeout 窗口内空转重试。"""
    import time

    from cloudra.runtime.monitor import _parse_log

    log = tmp_path / "incomplete.log"
    log.write_text(
        " Gaussian, Inc.\n"
        " SCF Done:  E(RHF) =  -1.1175059892     A.U. after    8 cycles\n"
        " Normal termination of Gaussian 16 at ...\n",
        encoding="utf-8",
    )
    started = time.monotonic()
    data, ok = await _parse_log(log, parse_timeout=1800)
    elapsed = time.monotonic() - started

    assert data is None and ok is None
    assert elapsed < 10


def test_log_tail_reason_extracts_gaussian_error(tmp_path):
    """失败原因提取：Gaussian Error termination 段（带上下文行）。"""
    from cloudra.runtime.monitor import _log_tail_reason

    log = tmp_path / "fail.log"
    log.write_text(
        " Step number  42 out of a maximum of 128\n"
        " Convergence failure -- run terminated.\n"
        " Error termination via Lnk1e in /opt/g16/l9999.exe\n"
        " Job cpu time: 0 days 0:01:23.4\n",
        encoding="utf-8",
    )
    reason = _log_tail_reason(log)
    assert "Error termination" in reason
    assert "Convergence failure" in reason


def test_log_tail_reason_falls_back_to_last_lines(tmp_path):
    """没有已知终止标记时退化为末尾三行。"""
    from cloudra.runtime.monitor import _log_tail_reason

    log = tmp_path / "weird.log"
    log.write_text("line1\nline2\nsegfault near end\n", encoding="utf-8")
    reason = _log_tail_reason(log)
    assert "segfault near end" in reason
    assert _log_tail_reason(tmp_path / "missing.log") == ""


@pytest.mark.asyncio
async def test_mark_failed_writes_last_error(isolated_db):
    """guard 标记失败时 last_error 落库，query_compute_job 直接可读。"""
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime.monitor import _mark_failed

    db = ComputeDB().init()
    # 直接插一行 compute_jobs（绕过 submit 工具，只测落库语义）
    async with db.aconnect() as con:
        cur = await con.execute(
            "INSERT INTO compute_jobs (conversation_id, session_id, path, state, start_timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test_conv", "s1", "/tmp/x.gjf", "running", 1.0),
        )
        await con.commit()
        task_id = cur.lastrowid

    await _mark_failed(db, task_id, "env check failed: g16 not found")
    async with db.aconnect() as con:
        row = await (await con.execute(
            "SELECT state, last_error FROM compute_jobs WHERE id=?", (task_id,)
        )).fetchone()
    assert row[0] == "failed"
    assert "g16 not found" in row[1]


@pytest.mark.asyncio
async def test_submit_rejects_over_capacity_request(isolated_db, mock_calc_workdir, monkeypatch):
    """资源申请超过节点容量 → 提交即拒绝，错误文本给出节点上限。"""
    from cloudra.services import nodes as nodes_mod

    monkeypatch.setattr(
        nodes_mod, "default_resources",
        lambda: {"max_concurrent": 2, "cpus": 4, "memory_mb": 4096},
    )
    gjf = os.path.join(mock_calc_workdir, "h2.gjf")
    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=gjf, job_type="gaussian", is_async=True, cpus=8,
        ),
        session=None,
    )
    assert result.is_success is False
    assert "exceeds node capacity" in result.message

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=gjf, job_type="gaussian", is_async=True, cpus=2, memory_mb=8192,
        ),
        session=None,
    )
    assert result.is_success is False
    assert "exceeds node capacity" in result.message


@pytest.mark.asyncio
async def test_submit_records_resource_request(isolated_db, mock_calc_workdir):
    """资源申请与优先级落列，供调度器容量认领读取。"""
    gjf = os.path.join(mock_calc_workdir, "h2.gjf")
    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=gjf, job_type="gaussian", is_async=True,
            cpus=2, memory_mb=1024, priority=3,
        ),
        session=None,
    )
    assert result.is_success is True
    assert result.state == "ready"

    from cloudra.persistence.database import ComputeDB

    db = ComputeDB()
    with db.connect() as con:
        row = con.execute(
            "SELECT priority, req_cpus, req_memory_mb, state FROM compute_jobs WHERE id=?",
            (result.job_id,),
        ).fetchone()
    assert tuple(row) == (3, 2, 1024, "ready")
