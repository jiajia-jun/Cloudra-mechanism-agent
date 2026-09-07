"""xtb 调度通道端到端测试（GH #26 收尾）。

覆盖：submit_compute_job 的显式任务参数（charge/multiplicity/task/solvent）
校验与入库、calculator.sh 的 xtb flag 拼接（--chrg/--uhf/--opt/--hess/--ohess/
--alpb/--parallel）、submit → 认领 → guard → calculator 的 fake xtb 链路透传，
以及 monitor 对 xtb hess 日志不误判 failed 的回归。
"""

import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from cloudra.infra.compute_utils import (
    build_calculator_cmd,
    validate_xtb_params,
)
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import (
    aget_compute_job,
    claim_ready_compute_job_with_capacity,
)
from cloudra.tools.Chemtool.submit_compute_job import (
    SubmitComputeJob,
    SubmitComputeJob_input_schema,
)

_CALCULATOR_SH = Path(__file__).resolve().parents[1] / "cloudra" / "calculator.sh"

# fake xtb：把 argv 与 OMP_NUM_THREADS 记进 spy 文件，按 flag 输出最小
# 可解析日志（opt 收敛 / hess 频率块 / sp 能量块均以 normal termination 收尾）。
_FAKE_XTB = """#!/bin/bash
{
  printf 'argv:'
  printf ' %s' "$@"
  printf '\\n'
  echo "omp=${OMP_NUM_THREADS:-unset}"
} >> "$XTB_SPY_FILE"
mode=sp
for a in "$@"; do
  case "$a" in
    --ohess|--hess) mode=hess ;;
    --opt) [ "$mode" = "sp" ] && mode=opt ;;
  esac
done
if [ "$mode" = "hess" ]; then
  cat <<'EOF'
| TOTAL ENERGY              -5.070441234567 Eh
projected vibrational frequencies
eigval :   -0.00    0.00    0.00   12.50  1300.00  3100.50
normal termination of xtb
EOF
elif [ "$mode" = "opt" ]; then
  cat <<'EOF'
 * total energy  :    -5.0704 Eh
GEOMETRY OPTIMIZATION CONVERGED
| TOTAL ENERGY              -5.070441234567 Eh
normal termination of xtb
EOF
else
  cat <<'EOF'
| TOTAL ENERGY              -5.070441234567 Eh
normal termination of xtb
EOF
fi
exit 0
"""

_XYZ = "3\nenolate\nC  0.0 0.0 0.0\nO  0.0 0.0 1.2\nH  0.0 0.0 2.2\n"


class MockAgent:
    """用于测试的最小 Agent 替身。"""

    def __init__(self, agent_id, conv_id):
        self.id = agent_id
        self.conversation_id = conv_id


@pytest.fixture
def xtb_workdir(tmp_path, monkeypatch):
    """带 fake xtb 二进制的任务目录；spy 文件记录 fake xtb 收到的 argv/OMP。"""
    workdir = tmp_path / "xtb_task"
    workdir.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    xtb = bindir / "xtb"
    xtb.write_text(_FAKE_XTB)
    xtb.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    spy = tmp_path / "xtb_spy.log"
    monkeypatch.setenv("XTB_SPY_FILE", str(spy))
    xyz = workdir / "enolate.xyz"
    xyz.write_text(_XYZ, encoding="utf-8")
    return {"workdir": workdir, "xyz": xyz, "spy": spy}


def _make_tool(conv_id="test_conv"):
    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", conv_id)
    return tool


# ---------------------------------------------------------------------------
# submit 参数校验与入库
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_xtb_defaults_persist_params(xtb_workdir):
    """缺省参数：charge=0 / multiplicity=1 / task=sp / solvent=NULL 入库。"""
    tool = _make_tool()
    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=str(xtb_workdir["xyz"]), job_type="xtb", is_async=True
        ),
        session=None,
    )
    assert result.is_success is True, result.message

    row = await aget_compute_job(ComputeDB(), result.job_id)
    assert row is not None
    assert row["charge"] == 0
    assert row["multiplicity"] == 1
    assert row["xtb_task"] == "sp"
    assert row["xtb_solvent"] is None


@pytest.mark.asyncio
async def test_submit_xtb_explicit_params_persist(xtb_workdir):
    """显式参数（charge=-1/mult=2/opt/water/cpus=2）原样入库。

    cpus 取 2（CI runner 节点容量为 2 核；申请不得超节点硬校验上限，
    cpus=3 会在 2 核 runner 上被资源校验拒收）。
    """
    tool = _make_tool()
    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=str(xtb_workdir["xyz"]),
            job_type="xtb",
            is_async=True,
            charge=-1,
            multiplicity=2,
            task="opt",
            solvent="water",
            cpus=2,
        ),
        session=None,
    )
    assert result.is_success is True, result.message

    row = await aget_compute_job(ComputeDB(), result.job_id)
    assert row is not None
    assert row["charge"] == -1
    assert row["multiplicity"] == 2
    assert row["xtb_task"] == "opt"
    assert row["xtb_solvent"] == "water"
    assert row["req_cpus"] == 2


def test_submit_xtb_invalid_task_rejected_by_schema():
    """非法 task 值在 schema 层即 fail-loud（不静默降级为裸 SP）。"""
    with pytest.raises(ValidationError):
        SubmitComputeJob_input_schema(
            input_file="/tmp/x.xyz", job_type="xtb", task="md"
        )


def test_submit_xtb_invalid_multiplicity_rejected_by_schema():
    """multiplicity < 1 在 schema 层 fail-loud。"""
    with pytest.raises(ValidationError):
        SubmitComputeJob_input_schema(
            input_file="/tmp/x.xyz", job_type="xtb", multiplicity=0
        )


@pytest.mark.asyncio
async def test_submit_xtb_runtime_validation_catches_schema_bypass(xtb_workdir):
    """畸形 JSON 兜底绕过 pydantic 时，tool_call 运行时校验仍 fail-loud。"""
    tool = _make_tool()
    bypassed = SubmitComputeJob_input_schema.model_construct(
        input_file=str(xtb_workdir["xyz"]), job_type="xtb", is_async=True,
        execution_backend="auto", cpus=1, memory_mb=None, priority=0,
        charge=0, multiplicity=1, task="molecular_dynamics", solvent=None,
    )
    result = await tool.tool_call(bypassed, session=None)
    assert result.is_success is False
    assert "task" in result.message


@pytest.mark.asyncio
async def test_submit_xtb_params_rejected_for_other_job_types(tmp_path):
    """charge/task/solvent 是 xtb 专属：gaussian 作业带这些参数 fail-loud 拒收。"""
    gjf = tmp_path / "h2.gjf"
    gjf.write_text("#p HF/3-21G\n\nH2\n\n0 1\nH 0 0 0\nH 0 0 0.74\n", encoding="utf-8")
    tool = _make_tool()
    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=str(gjf), job_type="gaussian", is_async=True, charge=-1
        ),
        session=None,
    )
    assert result.is_success is False
    assert "xtb" in result.message.lower()


def test_validate_xtb_params_solvent_charset():
    """溶剂名走字符白名单（名字表随 xtb 版本变化，未知名由 xtb 运行时报错）。"""
    assert validate_xtb_params(
        job_type="xtb", charge=0, multiplicity=1, task="sp", solvent="water"
    ) is None
    assert validate_xtb_params(
        job_type="xtb", charge=0, multiplicity=1, task="sp", solvent="h2o"
    ) is None
    bad = validate_xtb_params(
        job_type="xtb", charge=0, multiplicity=1, task="sp", solvent="water; rm -rf /"
    )
    assert bad is not None and "solvent" in bad


# ---------------------------------------------------------------------------
# calculator.sh flag 拼接
# ---------------------------------------------------------------------------


def _run_calculator(xyz: Path, extra_args: list[str], spy: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_CALCULATOR_SH), str(xyz), "xtb", *extra_args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_calculator_sh_xtb_flag_assembly(xtb_workdir):
    """透传参数拼成 xtb CLI flag：--chrg/--uhf/--ohess/--alpb/--parallel。"""
    result = _run_calculator(
        xtb_workdir["xyz"],
        ["--chrg", "-1", "--uhf", "1", "--task", "ohess", "--alpb", "water", "--parallel", "3"],
        xtb_workdir["spy"],
    )
    assert result.returncode == 0, result.stderr
    argv_line = xtb_workdir["spy"].read_text(encoding="utf-8").splitlines()[0]
    assert "--chrg -1" in argv_line
    assert "--uhf 1" in argv_line
    assert "--ohess" in argv_line
    assert "--alpb water" in argv_line
    assert "--parallel 3" in argv_line
    # 资源治理：OMP 线程数与申请的 cpus 一致（堵 OMP 空洞）
    assert "omp=3" in xtb_workdir["spy"].read_text(encoding="utf-8")
    out = xtb_workdir["workdir"] / "enolate.out"
    assert "normal termination of xtb" in out.read_text(encoding="utf-8")


def test_calculator_sh_xtb_task_flag_mapping(xtb_workdir):
    """task → flag 映射：opt→--opt、hess→--hess、sp→无任务 flag。"""
    for task, flag in (("opt", "--opt"), ("hess", "--hess")):
        xtb_workdir["spy"].write_text("", encoding="utf-8")
        result = _run_calculator(xtb_workdir["xyz"], ["--task", task], xtb_workdir["spy"])
        assert result.returncode == 0, result.stderr
        argv_line = xtb_workdir["spy"].read_text(encoding="utf-8").splitlines()[0]
        assert flag in argv_line

    xtb_workdir["spy"].write_text("", encoding="utf-8")
    result = _run_calculator(xtb_workdir["xyz"], [], xtb_workdir["spy"])
    assert result.returncode == 0, result.stderr
    argv_line = xtb_workdir["spy"].read_text(encoding="utf-8").splitlines()[0]
    # 缺省也显式声明电荷/多重度，绝不再读 xyz 注释行的隐式语义
    assert "--chrg 0" in argv_line
    assert "--uhf 0" in argv_line
    assert "--opt" not in argv_line and "--hess" not in argv_line


def test_calculator_sh_xtb_rejects_unknown_task(xtb_workdir):
    """未知 task / 未知参数在 calculator 层 fail-loud（exit≠0）。"""
    result = _run_calculator(xtb_workdir["xyz"], ["--task", "md"], xtb_workdir["spy"])
    assert result.returncode != 0
    result = _run_calculator(xtb_workdir["xyz"], ["--bogus", "1"], xtb_workdir["spy"])
    assert result.returncode != 0


def test_build_calculator_cmd_appends_xtb_args(xtb_workdir):
    """build_calculator_cmd 透传 xtb 参数到 calculator.sh 命令行。"""
    from cloudra.infra.compute_utils import XtbParams

    params = XtbParams(charge=-1, multiplicity=2, task="hess", solvent="water", cpus=3)
    ok, cmd, msg = build_calculator_cmd(
        str(xtb_workdir["xyz"]), "xtb", xtb_params=params
    )
    assert ok is True, msg
    tail = cmd[4:]
    assert tail == [
        "--chrg", "-1", "--uhf", "1", "--task", "hess",
        "--parallel", "3", "--alpb", "water",
    ]


# ---------------------------------------------------------------------------
# 链路级：submit → （认领）→ guard → calculator → fake xtb
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_xtb_sync_opt_end_to_end(xtb_workdir):
    """同步链路：opt + charge=-1 + cpus=2 一路透传到 fake xtb，终态 done。

    cpus=2（CI runner 节点容量为 2 核；cpus=3 会在 2 核 runner 上被资源校验拒收）。
    """
    tool = _make_tool()
    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=str(xtb_workdir["xyz"]),
            job_type="xtb",
            is_async=False,
            charge=-1,
            multiplicity=2,
            task="opt",
            solvent="water",
            cpus=2,
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    assert result.state == "done"

    spy = xtb_workdir["spy"].read_text(encoding="utf-8")
    argv_line = spy.splitlines()[0]
    assert "--chrg -1" in argv_line
    assert "--uhf 1" in argv_line
    assert "--opt" in argv_line
    assert "--alpb water" in argv_line
    assert "--parallel 2" in argv_line
    assert "omp=2" in spy

    row = await aget_compute_job(ComputeDB(), result.job_id)
    assert row["state"] == "done"
    assert row["charge"] == -1 and row["multiplicity"] == 2
    assert row["xtb_task"] == "opt" and row["xtb_solvent"] == "water"

    import json

    state = json.loads(
        (xtb_workdir["workdir"] / f"state_{result.job_id}.json").read_text(encoding="utf-8")
    )
    assert state["is_success"] is True
    assert state["opt_converged"] is True
    assert state["total_energy_hartree"] == pytest.approx(-5.070441234567)


@pytest.mark.asyncio
async def test_submit_xtb_sync_hess_end_to_end(xtb_workdir):
    """同步链路：hess 任务终态 done，不被"优化未收敛"第二判据误伤。"""
    tool = _make_tool()
    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=str(xtb_workdir["xyz"]),
            job_type="xtb",
            is_async=False,
            task="hess",
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    assert result.state == "done"

    argv_line = xtb_workdir["spy"].read_text(encoding="utf-8").splitlines()[0]
    assert "--hess" in argv_line

    import json

    state = json.loads(
        (xtb_workdir["workdir"] / f"state_{result.job_id}.json").read_text(encoding="utf-8")
    )
    assert state["is_success"] is True
    assert state["opt_converged"] is None


@pytest.mark.asyncio
async def test_submit_xtb_scheduler_claim_end_to_end(xtb_workdir):
    """调度链路：ready 行被容量认领后 run_compute 拉起 detach guard，
    fake xtb 收到透传参数，终态落 done。"""
    from cloudra.runtime.compute_executor import run_compute

    tool = _make_tool()
    submitted = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=str(xtb_workdir["xyz"]),
            job_type="xtb",
            is_async=True,
            charge=-1,
            task="opt",
            cpus=2,
        ),
        session=None,
    )
    assert submitted.is_success is True, submitted.message

    db = ComputeDB()
    capacity = {"max_concurrent": 2, "cpus": 8, "memory_mb": 8192}
    claimed = await asyncio.to_thread(
        claim_ready_compute_job_with_capacity,
        db,
        worker_id="test-worker",
        capacity=capacity,
    )
    assert claimed == submitted.job_id

    rc = await run_compute(submitted.job_id, db, worker_id="test-worker")
    assert rc == 0

    # detach guard 异步收尾：有界轮询终态
    deadline = asyncio.get_running_loop().time() + 60
    row = None
    while asyncio.get_running_loop().time() < deadline:
        row = await aget_compute_job(db, submitted.job_id)
        if row and row["state"] in ("done", "failed", "cancelled"):
            break
        await asyncio.sleep(0.5)
    assert row is not None and row["state"] == "done", (
        f"终态未达 done: {row and (row['state'], row['last_error'])}"
    )

    argv_line = xtb_workdir["spy"].read_text(encoding="utf-8").splitlines()[0]
    assert "--chrg -1" in argv_line
    assert "--opt" in argv_line
    assert "--parallel 2" in argv_line


# ---------------------------------------------------------------------------
# monitor 终态判定回归
# ---------------------------------------------------------------------------


def test_parse_xtb_log_hess_not_misjudged(tmp_path):
    """hess 日志（normal termination + 频率块）判 done；优化收敛判据不适用。"""
    from cloudra.runtime.monitor import _parse_xtb_log

    log = tmp_path / "freq.out"
    log.write_text(
        "| TOTAL ENERGY              -5.070441234567 Eh\n"
        "projected vibrational frequencies\n"
        "eigval :   -0.00    0.00    0.00   12.50  1300.00  3100.50\n"
        "normal termination of xtb\n",
        encoding="utf-8",
    )
    data, is_success = _parse_xtb_log(log, task="hess")
    assert is_success is True
    assert data["is_success"] is True
    assert data["opt_converged"] is None
    assert data["total_energy_hartree"] == pytest.approx(-5.070441234567)


def test_parse_xtb_log_opt_not_converged_failed_only_for_opt_tasks(tmp_path):
    """优化未收敛判据只对 opt/ohess 任务生效：hess/sp 任务不因此误判 failed。"""
    from cloudra.runtime.monitor import _parse_xtb_log

    log = tmp_path / "job.out"
    log.write_text(
        "| TOTAL ENERGY              -5.070441234567 Eh\n"
        "FAILED TO CONVERGE GEOMETRY OPTIMIZATION\n"
        "normal termination of xtb\n",
        encoding="utf-8",
    )
    data, is_success = _parse_xtb_log(log, task="opt")
    assert is_success is False
    assert "未收敛" in data["error"]

    data, is_success = _parse_xtb_log(log, task="ohess")
    assert is_success is False

    data, is_success = _parse_xtb_log(log, task="hess")
    assert is_success is True

    # 未知任务（旧行）保持历史行为：未收敛标记即 failed
    data, is_success = _parse_xtb_log(log, task=None)
    assert is_success is False
