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


def test_resolve_log_path_prefers_guard_state_json(tmp_path):
    """GH #20：guard state json 的 log_file 是实际解析的日志（如 macOS ORCA
    不落 .out，真实日志是 .cloudra/calc-<id>.out.log）——存在时优先于预测。"""
    import json as _json

    from cloudra.infra.compute_utils import resolve_log_path

    inp = tmp_path / "job.inp"
    inp.write_text("! ExtOpt Opt\n", encoding="utf-8")
    run_dir = tmp_path / ".cloudra"
    run_dir.mkdir()
    captured = run_dir / "calc-7.out.log"
    captured.write_text("ORCA TERMINATED NORMALLY\n", encoding="utf-8")
    (tmp_path / "state_7.json").write_text(
        _json.dumps({"log_file": str(captured)}), encoding="utf-8"
    )

    assert resolve_log_path(str(inp), job_type="orca", task_id=7) == str(captured)


def test_resolve_log_path_prefers_captured_stdout_over_prediction(tmp_path):
    """GH #20：无 state json 时，calc 落盘文件存在即优先于预测的 .out。"""
    from cloudra.infra.compute_utils import resolve_log_path

    inp = tmp_path / "job.inp"
    inp.write_text("! ExtOpt Opt\n", encoding="utf-8")
    run_dir = tmp_path / ".cloudra"
    run_dir.mkdir()
    captured = run_dir / "calc-7.out.log"
    captured.write_text("partial output\n", encoding="utf-8")

    assert resolve_log_path(str(inp), job_type="orca", task_id=7) == str(captured)


def test_resolve_log_path_falls_back_to_prediction(tmp_path):
    """state json 与落盘文件都不存在时回退引擎惯例预测路径。"""
    from cloudra.infra.compute_utils import resolve_log_path

    inp = tmp_path / "job.inp"
    inp.write_text("! Opt\n", encoding="utf-8")

    assert resolve_log_path(str(inp), job_type="orca", task_id=7) == str(tmp_path / "job.out")
    assert resolve_log_path(str(inp), job_type="gaussian", task_id=7) == str(tmp_path / "job.log")
    # state json 记录的 log_file 已不存在（被清理）时同样回退
    (tmp_path / "state_7.json").write_text(
        '{"log_file": "/nonexistent/gone.out.log"}', encoding="utf-8"
    )
    assert resolve_log_path(str(inp), job_type="orca", task_id=7) == str(tmp_path / "job.out")


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
async def test_query_compute_job_log_path_prefers_guard_state_json(isolated_db, tmp_path):
    """GH #20：query 的 log_path 与 guard 实际解析的日志一致——优先取
    state json 的 log_file（macOS ORCA 不落 .out/.log，真实日志是
    .cloudra/calc-<id>.out.log），不再报不存在的预测路径。"""
    import json as _json

    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.Chemtool.query_compute_job import (
        QueryComputeJob,
        QueryComputeJob_input_schema,
    )

    workdir = tmp_path / "calc_task"
    workdir.mkdir()
    inp = workdir / "acetaldehyde_opt.inp"
    inp.write_text("! ExtOpt Opt\n", encoding="utf-8")

    ComputeDB(isolated_db).init()
    async with ComputeDB(isolated_db).aconnect() as con:
        cur = await con.execute(
            "INSERT INTO compute_jobs (conversation_id, session_id, path, state, jobtype, start_timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test_conv", "s1", str(inp), "done", "orca", 1.0),
        )
        await con.commit()
        task_id = cur.lastrowid

    run_dir = workdir / ".cloudra"
    run_dir.mkdir()
    captured = run_dir / f"calc-{task_id}.out.log"
    captured.write_text("ORCA TERMINATED NORMALLY\n", encoding="utf-8")
    (workdir / f"state_{task_id}.json").write_text(
        _json.dumps({"log_file": str(captured)}), encoding="utf-8"
    )

    query = QueryComputeJob()
    query.subagent = MockAgent("a-0", "test_conv")
    result = await query.tool_call(
        QueryComputeJob_input_schema(job_id=task_id), session=None,
    )
    assert result.is_success is True
    assert result.jobs[0]["log_path"] == str(captured)


@pytest.mark.asyncio
async def test_query_compute_job_log_path_prefers_captured_stdout(isolated_db, tmp_path):
    """GH #20：state json 缺失（guard 死在写 json 前）时退到 calc 落盘文件，
    仍优先于预测的 .out。"""
    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.Chemtool.query_compute_job import (
        QueryComputeJob,
        QueryComputeJob_input_schema,
    )

    workdir = tmp_path / "calc_task"
    workdir.mkdir()
    inp = workdir / "job.inp"
    inp.write_text("! Opt\n", encoding="utf-8")

    ComputeDB(isolated_db).init()
    async with ComputeDB(isolated_db).aconnect() as con:
        cur = await con.execute(
            "INSERT INTO compute_jobs (conversation_id, session_id, path, state, jobtype, start_timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test_conv", "s1", str(inp), "running", "orca", 1.0),
        )
        await con.commit()
        task_id = cur.lastrowid

    run_dir = workdir / ".cloudra"
    run_dir.mkdir()
    captured = run_dir / f"calc-{task_id}.out.log"
    captured.write_text("partial output\n", encoding="utf-8")

    query = QueryComputeJob()
    query.subagent = MockAgent("a-0", "test_conv")
    result = await query.tool_call(
        QueryComputeJob_input_schema(job_id=task_id), session=None,
    )
    assert result.is_success is True
    assert result.jobs[0]["log_path"] == str(captured)


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


_CP2K_OK_LOG = (
    " GLOBAL WALL CLOCK TIME (seconds): 1.2\n"
    " PROGRAM ENDED IN CP2K\n"
    "ENERGY| Total FORCE_EVAL energy [a.u.]            -76.433670\n"
)
_CP2K_FAIL_LOG = (
    " PROGRAM ABORTED\n"
    " PROGRAM FAILED IN CP2K\n"
)


@pytest.mark.asyncio
async def test_parse_log_falls_back_to_captured_stdout_when_derived_log_missing(tmp_path):
    """引擎不自写日志文件（本机 ORCA 6.1.1 macOS 把主输出全写 stdout、从不落 .out）：
    推导日志缺失时回退解析 calculator 的 stdout/stderr 落盘文件。"""
    from cloudra.runtime.monitor import _parse_log

    derived = tmp_path / "job.out"
    fallback = tmp_path / "calc-1.out.log"
    fallback.write_text(_CP2K_OK_LOG, encoding="utf-8")

    data, ok = await _parse_log(
        derived, parse_timeout=60, job_type="cp2k", fallback_log_path=fallback
    )
    assert data is not None and ok is True
    assert data["total_energy_hartree"] == pytest.approx(-76.433670)


@pytest.mark.asyncio
async def test_parse_log_fallback_used_when_derived_log_empty(tmp_path):
    """推导日志为空（引擎没写）而落盘有内容时同样回退。"""
    from cloudra.runtime.monitor import _parse_log

    derived = tmp_path / "job.out"
    derived.write_text("", encoding="utf-8")
    fallback = tmp_path / "calc-1.out.log"
    fallback.write_text(_CP2K_OK_LOG, encoding="utf-8")

    data, ok = await _parse_log(
        derived, parse_timeout=60, job_type="cp2k", fallback_log_path=fallback
    )
    assert data is not None and ok is True


@pytest.mark.asyncio
async def test_parse_log_keeps_derived_log_when_present(tmp_path):
    """自写日志的引擎（Gaussian 等）：推导日志存在时不用落盘回退。"""
    from cloudra.runtime.monitor import _parse_log

    derived = tmp_path / "job.out"
    derived.write_text(_CP2K_OK_LOG, encoding="utf-8")
    fallback = tmp_path / "calc-1.out.log"
    fallback.write_text(_CP2K_FAIL_LOG, encoding="utf-8")

    data, ok = await _parse_log(
        derived, parse_timeout=60, job_type="cp2k", fallback_log_path=fallback
    )
    assert data is not None and ok is True


@pytest.mark.asyncio
async def test_parse_log_fallback_reports_failure_from_capture(tmp_path):
    """落盘内容带失败标记（ABORT/FAILED）：回退解析仍如实报 failed。"""
    from cloudra.runtime.monitor import _parse_log

    derived = tmp_path / "job.out"
    fallback = tmp_path / "calc-1.out.log"
    fallback.write_text(_CP2K_FAIL_LOG, encoding="utf-8")

    data, ok = await _parse_log(
        derived, parse_timeout=60, job_type="cp2k", fallback_log_path=fallback
    )
    assert data is not None and ok is False


_ORCA_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "orca"
_ORCA_EXTOPT_IRC_LOG = _ORCA_FIXTURE_DIR / "cope_irc_extopt_mace_orca611.out"


@pytest.mark.skipif(
    not __import__("cloudra.infra.platform_utils", fromlist=["is_posix"]).is_posix(),
    reason="calculator.sh 需要 POSIX bash",
)
def test_calculator_sh_resolves_orca_symlink_and_exposes_helpers(tmp_path):
    """GH #15：PATH 上的 orca 是符号链接（conda 风格）时，calculator.sh 必须解析
    到真实安装路径调用（并行 ORCA 要求 full pathname，exit 126），并把真实目录
    prepend 到 PATH 让 orca_util 等 helpers 可见。"""
    from cloudra.infra.compute_utils import _default_calculator_path
    from cloudra.infra.platform_utils import get_bash_path

    # 真实 ORCA 安装目录：orca + helper，均不在 PATH 上
    install = tmp_path / "orca_6_1_1"
    install.mkdir()
    orca_util = install / "orca_util"
    orca_util.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    orca_util.chmod(0o755)
    orca_real = install / "orca"
    orca_real.write_text(
        "#!/bin/bash\n"
        'case "$0" in /*) ;; *) echo "orca not invoked with full pathname: $0" >&2; exit 126;; esac\n'
        'command -v orca_util >/dev/null 2>&1 || { echo "sh: orca_util: command not found" >&2; exit 127; }\n'
        'echo "FAKE ORCA RUN: $1"\n',
        encoding="utf-8",
    )
    orca_real.chmod(0o755)

    # conda 风格 bin 目录：只有 orca 符号链接，无 helpers
    bindir = tmp_path / "conda_bin"
    bindir.mkdir()
    (bindir / "orca").symlink_to(orca_real)

    workdir = tmp_path / "job"
    workdir.mkdir()
    inp = workdir / "job.inp"
    inp.write_text("! ExtOpt Opt\n* xyz 0 1\n*\n", encoding="utf-8")

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:/usr/bin:/bin"
    result = subprocess.run(
        [get_bash_path(), _default_calculator_path(), str(inp), "orca"],
        capture_output=True,
        text=True,
        env=env,
        cwd=workdir,
    )
    assert result.returncode == 0, result.stderr
    assert "FAKE ORCA RUN" in result.stdout


@pytest.mark.skipif(
    not __import__("cloudra.infra.platform_utils", fromlist=["is_posix"]).is_posix(),
    reason="calculator.sh 需要 POSIX bash",
)
def test_calculator_sh_orca_resolution_failure_falls_back_to_bare_call(tmp_path):
    """GH #15：orca 是悬挂符号链接（解析失败）时，calculator.sh 不得在解析阶段
    崩溃——回退到修复前的裸调用行为（exec 失败按 127 传播，而非解析器报错）。"""
    from cloudra.infra.compute_utils import _default_calculator_path
    from cloudra.infra.platform_utils import get_bash_path

    bindir = tmp_path / "conda_bin"
    bindir.mkdir()
    # 悬挂链接：目标不存在，符号链接链解析必然失败
    (bindir / "orca").symlink_to(tmp_path / "nonexistent_orca_install" / "orca")

    workdir = tmp_path / "job"
    workdir.mkdir()
    inp = workdir / "job.inp"
    inp.write_text("! Opt\n* xyz 0 1\n*\n", encoding="utf-8")

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:/usr/bin:/bin"
    result = subprocess.run(
        [get_bash_path(), _default_calculator_path(), str(inp), "orca"],
        capture_output=True,
        text=True,
        env=env,
        cwd=workdir,
    )
    assert "orca 路径解析失败，回退裸调用" in result.stderr
    # 回退后 exec 悬挂链接失败：127，而不是解析阶段的 set -e 中止
    assert result.returncode == 127


@pytest.mark.asyncio
async def test_parse_orca_log_extopt_done_even_when_cclib_fails(monkeypatch):
    """GH #17/#18：外部 MLIP（ExtOpt）日志无 SCF 块，cclib 解析抛错（ccdata 缺
    spin multiplicity / Unexpectedly encountered end of logfile），但日志以
    ORCA TERMINATED NORMALLY 结束——终止标记是终态权威、cclib 只取数据，
    任务必须落 done，且文本提取到外部能量。"""
    import cclib

    from cloudra.runtime.monitor import _parse_log

    def _boom(*_args, **_kwargs):
        raise ValueError("ccdata object does not have spin multiplicity")

    monkeypatch.setattr(cclib.io, "ccread", _boom)

    data, ok = await _parse_log(_ORCA_EXTOPT_IRC_LOG, parse_timeout=60, job_type="orca")
    assert data is not None and ok is True
    assert data["is_success"] is True
    assert data["total_energy_hartree"] == pytest.approx(-234.506295105500)


@pytest.mark.asyncio
async def test_parse_orca_log_failed_without_normal_termination(tmp_path):
    """正常终止标记缺失（error termination / 被 kill）即 failed——即使日志里
    有能量行也不能靠数据反推成功。"""
    from cloudra.runtime.monitor import _parse_log

    log = tmp_path / "job.out"
    log.write_text(
        "FINAL SINGLE POINT ENERGY (From external program)     -234.500000000000\n"
        "ORCA finished by error termination in ORCA_GSTEP\n",
        encoding="utf-8",
    )
    data, ok = await _parse_log(log, parse_timeout=60, job_type="orca")
    assert ok is False
    assert data["is_success"] is False


@pytest.mark.asyncio
async def test_parse_orca_log_keeps_cclib_data_when_parseable():
    """普通 DFT ORCA 日志：cclib 可解析时仍用 cclib 数据（不丢字段），
    终态同样由终止标记决定。"""
    from cloudra.runtime.monitor import _parse_log

    data, ok = await _parse_log(
        _ORCA_FIXTURE_DIR / "co2_freq_orca42.out", parse_timeout=60, job_type="orca"
    )
    assert ok is True
    assert data["is_success"] is True
    assert "vibfreqs" in data or "properties" in data


# GH #21/#22：未收敛的 MACE ExtOpt Opt 日志片段（GH #21/#22 真实样本，原日志已随工作区清理删除
# ——跑满最大步数仍打印 ORCA TERMINATED NORMALLY）。
_ORCA_EXTOPT_OPT_NOT_CONVERGED = (
    "! ExtOpt Opt\n"
    "FINAL SINGLE POINT ENERGY (From external program)      -383.418935837100\n"
    "                        GEOMETRY OPTIMIZATION CYCLE   1\n"
    "Current Energy                          ....  -383.543545238 Eh\n"
    "                        GEOMETRY OPTIMIZATION CYCLE  25\n"
    "Current Energy                          ....  -383.544742265 Eh\n"
    "                                  WARNING !!!\n"
    "       The optimization did not converge but reached the maximum number of\n"
    "       optimization cycles.\n"
    "       Please check your results very carefully.\n"
    "                             ****ORCA TERMINATED NORMALLY****\n"
)
# 收敛对照（calc-25 型）：收敛标记 + 收敛几何的 FINAL SP 在 Current Energy 之后。
_ORCA_EXTOPT_OPT_CONVERGED = (
    "! ExtOpt Opt\n"
    "FINAL SINGLE POINT ENERGY (From external program)      -153.826408146800\n"
    "                        GEOMETRY OPTIMIZATION CYCLE   1\n"
    "Current Energy                          ....  -153.827552874 Eh\n"
    "                    ***        THE OPTIMIZATION HAS CONVERGED     ***\n"
    "FINAL SINGLE POINT ENERGY (From external program)      -153.827552913800\n"
    "                             ****ORCA TERMINATED NORMALLY****\n"
)


@pytest.mark.asyncio
async def test_parse_orca_log_unconverged_opt_is_failed(tmp_path, monkeypatch):
    """GH #21：优化跑满最大步数未收敛时 ORCA 仍打印 TERMINATED NORMALLY——
    终止标记不构成成功判据，文本收敛标记判 failed 且错误信息指出未收敛；
    能量取最后的 Current Energy（GH #22，起始几何的 FINAL SP 是错的）。"""
    import cclib

    from cloudra.runtime.monitor import _parse_log

    def _boom(*_args, **_kwargs):
        raise ValueError("Unexpectedly encountered end of logfile")

    monkeypatch.setattr(cclib.io, "ccread", _boom)

    log = tmp_path / "job.out"
    log.write_text(_ORCA_EXTOPT_OPT_NOT_CONVERGED, encoding="utf-8")
    data, ok = await _parse_log(log, parse_timeout=60, job_type="orca")
    assert ok is False
    assert data["is_success"] is False
    assert data["opt_converged"] is False
    assert "未收敛" in data["error"]
    assert data["total_energy_hartree"] == pytest.approx(-383.544742265)


@pytest.mark.asyncio
async def test_parse_orca_log_converged_opt_stays_done(tmp_path, monkeypatch):
    """收敛的 ExtOpt Opt 仍判 done（opt_converged=True），能量取收敛几何的
    FINAL SP（位置在最后）。"""
    import cclib

    from cloudra.runtime.monitor import _parse_log

    def _boom(*_args, **_kwargs):
        raise ValueError("Unexpectedly encountered end of logfile")

    monkeypatch.setattr(cclib.io, "ccread", _boom)

    log = tmp_path / "job.out"
    log.write_text(_ORCA_EXTOPT_OPT_CONVERGED, encoding="utf-8")
    data, ok = await _parse_log(log, parse_timeout=60, job_type="orca")
    assert ok is True
    assert data["is_success"] is True
    assert data["opt_converged"] is True
    assert data["total_energy_hartree"] == pytest.approx(-153.827552913800)


@pytest.mark.asyncio
async def test_parse_orca_log_unconverged_opt_via_cclib_optdone(tmp_path, monkeypatch):
    """GH #21 cclib 辅助路径：文本收敛标记缺失（如版本差异）但 cclib 可解析
    且 optdone=False 的 Opt 日志，同样判 failed。"""
    import cloudra.runtime.monitor as monitor

    async def _fake_cclib(target):
        return {"log_file": str(target), "optdone": False}, True

    monkeypatch.setattr(monitor, "_cclib_parse", _fake_cclib)

    log = tmp_path / "job.out"
    log.write_text(
        "! Opt\n"
        "                        GEOMETRY OPTIMIZATION CYCLE   1\n"
        "FINAL SINGLE POINT ENERGY     -76.000000000001\n"
        "                             ****ORCA TERMINATED NORMALLY****\n",
        encoding="utf-8",
    )
    data, ok = await monitor._parse_log(log, parse_timeout=60, job_type="orca")
    assert ok is False
    assert data["is_success"] is False
    assert data["opt_converged"] is False
    assert "未收敛" in data["error"]


@pytest.mark.asyncio
async def test_guard_marks_failed_for_unconverged_extopt_opt(
    isolated_db, monkeypatch, tmp_path
):
    """GH #21 端到端：guard 对未收敛的 ExtOpt Opt 落 failed，last_error 与
    state json 明确指出未收敛（不能因 TERMINATED NORMALLY 误判 done）。"""
    import json as _json
    import sys

    import cclib

    import cloudra.runtime.monitor as monitor
    from cloudra.persistence.database import ComputeDB

    workdir = tmp_path / "calc_task"
    workdir.mkdir()
    inp = workdir / "ts_opt.inp"
    inp.write_text("! ExtOpt Opt\n* xyz 0 1\n*\n", encoding="utf-8")
    db_path = os.path.join(isolated_db, "compute.db")

    ComputeDB(isolated_db).init()
    async with ComputeDB(isolated_db).aconnect() as con:
        cur = await con.execute(
            "INSERT INTO compute_jobs (conversation_id, session_id, path, state, start_timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test_conv", "s1", str(inp), "running", 1.0),
        )
        await con.commit()
        task_id = cur.lastrowid

    def _boom(*_args, **_kwargs):
        raise ValueError("Unexpectedly encountered end of logfile")

    monkeypatch.setattr(cclib.io, "ccread", _boom)
    monkeypatch.setattr(monitor, "check_job_type", lambda _jt, _wd: (True, ""))
    stdout_code = (
        "import sys; sys.stdout.write("
        f"{_ORCA_EXTOPT_OPT_NOT_CONVERGED!r})"
    )
    monkeypatch.setattr(
        monitor,
        "build_calculator_cmd",
        lambda input_file, job_type, **_kwargs: (True, [sys.executable, "-c", stdout_code], ""),
    )

    await monitor.run_guard(
        task_id, str(inp), "test_conv", parse_timeout=60, db_path=db_path, job_type="orca"
    )

    async with ComputeDB(isolated_db).aconnect() as con:
        row = await (await con.execute(
            "SELECT state, last_error FROM compute_jobs WHERE id=?", (task_id,)
        )).fetchone()
    assert row[0] == "failed"
    assert "未收敛" in row[1]

    payload = _json.loads((workdir / f"state_{task_id}.json").read_text(encoding="utf-8"))
    assert payload["is_success"] is False
    assert "未收敛" in payload["error"]
    assert payload["total_energy_hartree"] == pytest.approx(-383.544742265)


@pytest.mark.asyncio
async def test_guard_marks_done_for_extopt_orca_stdout_only(
    isolated_db, monkeypatch, tmp_path
):
    """GH #18 端到端：macOS ORCA 不落 .out（主输出全在 stdout 落盘）且 ExtOpt
    日志 cclib 无法解析——guard 回退解析落盘输出、按终止标记落 done。"""
    import sys

    import cclib

    import cloudra.runtime.monitor as monitor
    from cloudra.persistence.database import ComputeDB

    workdir = tmp_path / "calc_task"
    workdir.mkdir()
    inp = workdir / "ts_irc.inp"
    inp.write_text("! ExtOpt IRC\n* xyz 0 1\n*\n", encoding="utf-8")
    db_path = os.path.join(isolated_db, "compute.db")

    ComputeDB(isolated_db).init()
    async with ComputeDB(isolated_db).aconnect() as con:
        cur = await con.execute(
            "INSERT INTO compute_jobs (conversation_id, session_id, path, state, start_timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test_conv", "s1", str(inp), "running", 1.0),
        )
        await con.commit()
        task_id = cur.lastrowid

    def _boom(*_args, **_kwargs):
        raise ValueError("Unexpectedly encountered end of logfile")

    monkeypatch.setattr(cclib.io, "ccread", _boom)
    monkeypatch.setattr(monitor, "check_job_type", lambda _jt, _wd: (True, ""))
    stdout_code = (
        "import sys; sys.stdout.write("
        f"open({str(_ORCA_EXTOPT_IRC_LOG)!r}).read())"
    )
    monkeypatch.setattr(
        monitor,
        "build_calculator_cmd",
        lambda input_file, job_type, **_kwargs: (True, [sys.executable, "-c", stdout_code], ""),
    )

    await monitor.run_guard(
        task_id, str(inp), "test_conv", parse_timeout=60, db_path=db_path, job_type="orca"
    )

    async with ComputeDB(isolated_db).aconnect() as con:
        row = await (await con.execute(
            "SELECT state FROM compute_jobs WHERE id=?", (task_id,)
        )).fetchone()
    assert row[0] == "done"

    state_json = workdir / f"state_{task_id}.json"
    assert state_json.exists()
    import json as _json

    payload = _json.loads(state_json.read_text(encoding="utf-8"))
    assert payload["is_success"] is True
    assert payload["total_energy_hartree"] == pytest.approx(-234.506295105500)


@pytest.mark.asyncio
async def test_guard_marks_done_via_captured_stdout_for_stdout_only_engine(
    isolated_db, monkeypatch, tmp_path
):
    """stdout-only 引擎（orca macOS 行为）端到端：guard 落盘 calculator 输出、
    推导 .out 缺失时回退解析 → 正常完成的作业落 done，不再误判失败。"""
    import sys

    import cloudra.runtime.monitor as monitor

    workdir = tmp_path / "calc_task"
    workdir.mkdir()
    inp = workdir / "job.inp"
    inp.write_text("dummy input", encoding="utf-8")
    db_path = os.path.join(isolated_db, "compute.db")

    from cloudra.persistence.database import ComputeDB

    ComputeDB(isolated_db).init()
    async with ComputeDB(isolated_db).aconnect() as con:
        cur = await con.execute(
            "INSERT INTO compute_jobs (conversation_id, session_id, path, state, start_timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test_conv", "s1", str(inp), "running", 1.0),
        )
        await con.commit()
        task_id = cur.lastrowid

    def _fake_check(job_type, workdir):
        return True, ""

    stdout_code = (
        "import sys; sys.stdout.write("
        "'GLOBAL WALL CLOCK TIME (seconds): 1.2\\nPROGRAM ENDED IN CP2K\\n"
        "ENERGY| Total FORCE_EVAL energy [a.u.]            -76.433670\\n')"
    )
    monkeypatch.setattr(monitor, "check_job_type", _fake_check)
    monkeypatch.setattr(
        monitor,
        "build_calculator_cmd",
        lambda input_file, job_type, **_kwargs: (True, [sys.executable, "-c", stdout_code], ""),
    )

    await monitor.run_guard(
        task_id, str(inp), "test_conv", parse_timeout=60, db_path=db_path, job_type="cp2k"
    )

    async with ComputeDB(isolated_db).aconnect() as con:
        row = await (await con.execute(
            "SELECT state FROM compute_jobs WHERE id=?", (task_id,)
        )).fetchone()
    assert row[0] == "done"

    capture = workdir / ".cloudra" / f"calc-{task_id}.out.log"
    assert capture.exists() and capture.stat().st_size > 0
    state_json = workdir / f"state_{task_id}.json"
    assert state_json.exists()
    import json as _json

    payload = _json.loads(state_json.read_text(encoding="utf-8"))
    assert payload["is_success"] is True


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
