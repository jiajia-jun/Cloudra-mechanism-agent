"""GH #26：xtb 执行路径测试。

覆盖：xtb_frames 文本原语、guard（monitor）终态判定、log_parser 解析、
submit_compute_job job_type 放行、calculator.sh run_xtb 分支、
method_policy 的 xtb 提交分支。fixtures 按真实 xtb 6.7.1 输出格式合成
（GH #26）。
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cloudra.benchmark.method_policy import intercept
from cloudra.benchmark.schema import MethodPolicy
from cloudra.infra.compute_utils import check_job_type
from cloudra.tools.Chemtool.submit_compute_job import (
    SubmitComputeJob,
    SubmitComputeJob_input_schema,
)
from cloudra.tools.core import xtb_frames
from cloudra.tools.core.qm_engine import detect_qm_engine

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "xtb"
SP_FIXTURE = _FIXTURES / "water_sp_xtb.out"
OPT_FIXTURE = _FIXTURES / "water_opt_xtb.out"
UNCONVERGED_OPT_FIXTURE = _FIXTURES / "water_opt_unconverged_xtb.out"
HESS_FIXTURE = _FIXTURES / "ts_hess_xtb.out"

_WATER_XYZ = (
    "3\nwater\n"
    "O 0.000000 0.000000 0.117300\n"
    "H 0.000000 0.757200 -0.469200\n"
    "H 0.000000 -0.757200 -0.469200\n"
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """使用临时数据目录隔离数据库和上下文（与 test_compute 同款）。"""
    data_dir = tmp_path / "cloudra_data"
    data_dir.mkdir()

    from cloudra.infra.config import _reset_for_tests, get_config

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    _reset_for_tests()
    cfg = get_config()
    cfg.data_dir = data_dir
    cfg._ensure_dirs()

    from cloudra.persistence.database import ConversationDB

    ConversationDB("test_conv").init()

    return str(data_dir)


class MockAgent:
    """用于测试的最小 Agent 替身。"""

    def __init__(self, agent_id, conv_id):
        self.id = agent_id
        self.conversation_id = conv_id


# ---------------------------------------------------------------------------
# xtb_frames 文本原语
# ---------------------------------------------------------------------------


def test_xtb_frames_normal_termination():
    assert xtb_frames.normal_termination(SP_FIXTURE.read_text()) is True
    assert xtb_frames.normal_termination("xtb crashed halfway\n") is False


def test_xtb_frames_opt_converged_states():
    """收敛/未收敛/非优化三态（GH #21 同款语义）。"""
    assert xtb_frames.opt_converged(OPT_FIXTURE.read_text()) is True
    assert xtb_frames.opt_converged(UNCONVERGED_OPT_FIXTURE.read_text()) is False
    assert xtb_frames.opt_converged(SP_FIXTURE.read_text()) is None


def test_xtb_frames_final_energy_by_position():
    """能量按文本位置取最后：最终 TOTAL ENERGY 块 > :: total energy > 周期能量行。"""
    assert xtb_frames.final_energy_hartree(SP_FIXTURE.read_text()) == pytest.approx(-5.070320041234)
    assert xtb_frames.final_energy_hartree(OPT_FIXTURE.read_text()) == pytest.approx(-5.070320229528)
    assert xtb_frames.final_energy_hartree(UNCONVERGED_OPT_FIXTURE.read_text()) == pytest.approx(
        -5.070300120528
    )
    # 截断日志（无最终块）：最后的 opt 周期能量行是最佳估计（GH #22 同款语义）
    truncated = "CYCLE 7\n * total energy  :    -5.0703000 Eh     change -0.1E-05 Eh\n"
    assert xtb_frames.final_energy_hartree(truncated) == pytest.approx(-5.0703000)
    assert xtb_frames.final_energy_hartree("no energy here") is None


def test_xtb_frames_vibfreqs_from_text():
    """频率取最后一个 projected vibrational frequencies 块的 eigval 行。"""
    freqs = xtb_frames.vibfreqs_from_text(HESS_FIXTURE.read_text())
    assert freqs == pytest.approx([-0.0, -0.0, -0.0, -0.0, 0.0, 0.0, -521.21, 218.23, 436.11])
    assert xtb_frames.vibfreqs_from_text(SP_FIXTURE.read_text()) == []


def test_xtb_frames_vibfreqs_i_suffix_parsed_as_imaginary():
    """eigval 行的虚频若以 ``68.66i`` 后缀形式出现，须解析为负值而非抛
    ValueError（与负值=虚频的原生语义一致）。"""
    text = (
        " projected vibrational frequencies (cm⁻¹)\n"
        "eigval :        0.00     0.00     0.00    68.66i   218.23\n"
    )
    assert xtb_frames.vibfreqs_from_text(text) == pytest.approx([0.0, 0.0, 0.0, -68.66, 218.23])


def test_xtb_frames_thermochemistry():
    """热化学从 THERMODYNAMIC 块与最终块文本提取（cclib 对 xtb hess 日志给出
    荒谬值，权威值是 :: 块，GH 实锤：cclib freeenergy=-693 Eh vs 文本 -5.01 Eh）。"""
    thermo = xtb_frames.thermochemistry(HESS_FIXTURE.read_text())
    assert thermo["total_gibbs_free_energy_hartree"] == pytest.approx(-5.016782875363)
    assert thermo["total_enthalpy_hartree"] == pytest.approx(-5.045001756720)
    assert thermo["zero_point_correction_hartree"] == pytest.approx(0.021462987765)
    assert thermo["thermal_gibbs_correction_hartree"] == pytest.approx(0.052218881357)
    # 无热化学块的日志返回空 dict（不得编数）
    assert xtb_frames.thermochemistry(OPT_FIXTURE.read_text()) == {}


def test_xtb_frames_detect_job_types():
    assert xtb_frames.detect_job_types_from_text(SP_FIXTURE.read_text()) == {"sp"}
    assert xtb_frames.detect_job_types_from_text(OPT_FIXTURE.read_text()) == {"opt"}
    assert xtb_frames.detect_job_types_from_text(HESS_FIXTURE.read_text()) == {"sp", "freq"}


# ---------------------------------------------------------------------------
# 引擎嗅探
# ---------------------------------------------------------------------------


def test_detect_qm_engine_xtb():
    assert detect_qm_engine(str(SP_FIXTURE)) == "xtb"
    assert detect_qm_engine(str(HESS_FIXTURE)) == "xtb"


# ---------------------------------------------------------------------------
# guard（monitor）终态判定
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitor_parse_xtb_sp_done(tmp_path):
    from cloudra.runtime.monitor import _parse_log

    log = tmp_path / "water.out"
    log.write_text(SP_FIXTURE.read_text())
    data, ok = await _parse_log(log, parse_timeout=60, job_type="xtb")
    assert ok is True
    assert data["is_success"] is True
    assert data["scf_energy_hartree"] == pytest.approx(-5.070320041234)
    assert data["opt_converged"] is None
    assert data["log_file"] == str(log)


@pytest.mark.asyncio
async def test_monitor_parse_xtb_opt_converged_done(tmp_path):
    from cloudra.runtime.monitor import _parse_log

    log = tmp_path / "water.out"
    log.write_text(OPT_FIXTURE.read_text())
    data, ok = await _parse_log(log, parse_timeout=60, job_type="xtb")
    assert ok is True
    assert data["opt_converged"] is True
    assert data["scf_energy_hartree"] == pytest.approx(-5.070320229528)


@pytest.mark.asyncio
async def test_monitor_parse_xtb_unconverged_opt_failed(tmp_path):
    """未收敛优化：xtb 仍打印 normal termination，须按 GH #21 同款语义判 failed。"""
    from cloudra.runtime.monitor import _parse_log

    log = tmp_path / "water.out"
    log.write_text(UNCONVERGED_OPT_FIXTURE.read_text())
    data, ok = await _parse_log(log, parse_timeout=60, job_type="xtb")
    assert ok is False
    assert data["is_success"] is False
    assert data["opt_converged"] is False
    assert "未收敛" in data["error"]


@pytest.mark.asyncio
async def test_monitor_parse_xtb_abnormal_termination_failed(tmp_path):
    from cloudra.runtime.monitor import _parse_log

    log = tmp_path / "water.out"
    log.write_text(SP_FIXTURE.read_text().replace("normal termination of xtb", ""))
    data, ok = await _parse_log(log, parse_timeout=60, job_type="xtb")
    assert ok is False
    assert data["is_success"] is False


# ---------------------------------------------------------------------------
# log_parser 解析
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_parser_xtb_sp():
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(SP_FIXTURE)), session=None
    )
    assert result.is_success is True
    assert result.engine == "xtb"
    assert result.normal_termination is True
    assert result.scf_energy_hartree == pytest.approx(-5.070320041234)
    assert result.scf_energy_ev == pytest.approx(-5.070320041234 * 27.211386245988)
    assert result.opt_converged is None
    assert result.job_types == ["sp"]
    # cclib 对 xtb 日志不可靠：gap/偶极走 xtb_frames 文本回退（架构审查发现）
    assert result.homo_lumo_gap_ev == pytest.approx(12.345678901234)
    assert result.dipole_moment_debye == pytest.approx(1.852)


@pytest.mark.asyncio
async def test_log_parser_xtb_opt_converged():
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(OPT_FIXTURE)), session=None
    )
    assert result.is_success is True
    assert result.normal_termination is True
    assert result.opt_converged is True
    assert result.job_types == ["opt"]


@pytest.mark.asyncio
async def test_log_parser_xtb_unconverged_opt():
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(UNCONVERGED_OPT_FIXTURE)), session=None
    )
    assert result.is_success is True
    assert result.normal_termination is True
    assert result.opt_converged is False


@pytest.mark.asyncio
async def test_log_parser_xtb_hess_frequencies():
    """频率从 eigval 块文本提取；虚频保留负号（负值=虚频，原生语义）。"""
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(HESS_FIXTURE)), session=None
    )
    assert result.is_success is True
    assert result.engine == "xtb"
    assert "freq" in result.job_types
    assert result.imaginary_frequencies == pytest.approx([-521.21])
    assert result.frequencies_cm == pytest.approx([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 218.23, 436.11])


@pytest.mark.asyncio
async def test_log_parser_xtb_opt_energy_ignores_cclib(monkeypatch):
    """xtb opt 日志能量权威值是最终 boxed TOTAL ENERGY；cclib 的
    scfenergies[-1] 是最后一个 opt cycle 的能量（实锤偏差 ~1.1e-6 Eh，
    真实样本 aldol_selfcond_mech/ts_e1/refine/irc_plus/opt.log）——xtb
    整体跳过 cclib，与 runtime/monitor.py 一致。"""
    import types

    import cclib

    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    # 模拟真实 cclib 行为：能解析但给的是最后 cycle 的能量（≠ boxed 权威值）
    stub = types.SimpleNamespace(scfenergies=[-137.5])
    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: stub)

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(OPT_FIXTURE), properties=["energy"]), session=None
    )
    assert result.is_success is True
    assert result.engine == "xtb"
    # 严格容差：真实样本偏差仅 ~1.1e-6 Eh（cclib -25.585519303 vs boxed
    # -25.585520428），默认 approx 容差盖不住，必须收紧
    assert result.scf_energy_hartree == pytest.approx(-5.070320229528, rel=1e-12)
    assert result.scf_energy_ev == pytest.approx(-5.070320229528 * 27.211386245988)


@pytest.mark.asyncio
async def test_log_parser_xtb_hess_thermochemistry_from_text(monkeypatch):
    """xtb --hess 日志的热化学走 THERMODYNAMIC 块文本；cclib 的热化学兜底
    对 xtb 永不生效（实锤：cclib freeenergy=-693.86 Eh 荒谬值）。"""
    import types

    import cclib

    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    # cclib 对真实 hess 日志给出的垃圾值（aldol_selfcond_mech/ts_e1/refine/hess_ts19/hess.log）
    stub = types.SimpleNamespace(
        freeenergy=-693.8571849416829, enthalpy=-692.5275710158843, zpve=3.156381734019131
    )
    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: stub)

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(HESS_FIXTURE), properties=["thermochemistry"]),
        session=None,
    )
    assert result.is_success is True
    assert result.total_gibbs_free_energy_hartree == pytest.approx(-5.016782875363)
    assert result.total_enthalpy_hartree == pytest.approx(-5.045001756720)
    assert result.zero_point_correction_hartree == pytest.approx(0.021462987765)
    assert result.thermal_gibbs_correction_hartree == pytest.approx(0.052218881357)
    # 兼容别名同步
    assert result.gibbs_free_energy_hartree == pytest.approx(-5.016782875363)
    assert result.zero_point_energy_hartree == pytest.approx(0.021462987765)


# ---------------------------------------------------------------------------
# submit_compute_job 放行 + 端到端（fake xtb 二进制 PATH 劫持）
# ---------------------------------------------------------------------------


def test_check_job_type_xtb_in_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cloudra.infra.compute_utils.shutil.which",
        lambda name: "/usr/bin/xtb" if name == "xtb" else None,
    )
    ok, msg = check_job_type("xtb", str(tmp_path))
    assert ok is True
    assert msg == ""


@pytest.fixture
def mock_xtb_workdir(tmp_path, monkeypatch):
    """fake xtb 二进制（stdout 打印正常终止的 SP 日志）+ xyz 输入；不放置
    本地 calculator.sh，走项目内置脚本的 run_xtb 分支。"""
    workdir = tmp_path / "calc_xtb"
    workdir.mkdir()

    bindir = tmp_path / "bin_xtb"
    bindir.mkdir()
    xtb = bindir / "xtb"
    xtb.write_text(f'#!/bin/bash\ncat "{SP_FIXTURE}"\nexit 0\n')
    xtb.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        str(bindir) + os.pathsep + os.environ.get("PATH", ""),
    )

    xyz = workdir / "water.xyz"
    xyz.write_text(_WATER_XYZ)

    return str(workdir)


@pytest.mark.asyncio
async def test_submit_compute_job_xtb_sync_success(isolated_db, mock_xtb_workdir):
    """job_type='xtb' 全链路：guard → 内置 calculator.sh run_xtb → .out 解析 done。"""
    inp = os.path.join(mock_xtb_workdir, "water.xyz")
    tool = SubmitComputeJob()
    tool.subagent = MockAgent("a-0", "test_conv")

    result = await tool.tool_call(
        SubmitComputeJob_input_schema(input_file=inp, job_type="xtb", is_async=False),
        session=None,
    )

    assert result.is_success is True
    assert result.state == "done"
    assert result.job_dir == mock_xtb_workdir
    # stdout 重定向落盘：guard 按引擎惯例解析 <stem>.out
    assert "normal termination of xtb" in (Path(mock_xtb_workdir) / "water.out").read_text()


# ---------------------------------------------------------------------------
# calculator.sh run_xtb 分支
# ---------------------------------------------------------------------------


def test_calculator_script_xtb(tmp_path, monkeypatch):
    """calculator.sh 的 xtb 分支：stdout 重定向到 <stem>.out。"""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    xtb = bindir / "xtb"
    xtb.write_text('#!/bin/bash\necho "FAKE XTB STDOUT"\nexit 0\n')
    xtb.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        str(bindir) + os.pathsep + os.environ.get("PATH", ""),
    )

    script_path = Path(__file__).parent.parent / "cloudra" / "calculator.sh"
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ)
    result = subprocess.run(
        [str(script_path), str(xyz), "xtb"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    out = tmp_path / "water.out"
    assert out.exists()
    assert "FAKE XTB STDOUT" in out.read_text()


def test_calculator_script_xtb_missing_binary(tmp_path, monkeypatch):
    """PATH 无 xtb：明确报错并非零退出。"""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("PATH", str(bindir))

    script_path = Path(__file__).parent.parent / "cloudra" / "calculator.sh"
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ)
    result = subprocess.run(
        [str(script_path), str(xyz), "xtb"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "xtb" in result.stderr


# 本机有真实 xtb 时顺手实测 calculator.sh 路径（无二进制即 skip）
_real_xtb = shutil.which("xtb")


@pytest.mark.skipif(_real_xtb is None, reason="xtb 二进制不在 PATH")
def test_calculator_script_xtb_real_binary(tmp_path):
    script_path = Path(__file__).parent.parent / "cloudra" / "calculator.sh"
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ)
    result = subprocess.run(
        [str(script_path), str(xyz), "xtb"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0
    out = tmp_path / "water.out"
    assert out.exists()
    assert "normal termination of xtb" in out.read_text()


# ---------------------------------------------------------------------------
# method_policy：xtb 提交分支（xyz 无方法信息，按 job_type 声明族判定）
# ---------------------------------------------------------------------------


def test_method_policy_submit_compute_job_xtb_job_type(tmp_path):
    """GH #26：xtb 作业输入是纯坐标 .xyz（不携带方法信息）——按提交声明的
    job_type 方法族判定；白名单无 xtb 时保持 fail-closed，语义不弱化。"""
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ)
    policy = MethodPolicy(allowed_methods=["xtb"])
    ok = intercept(
        "submit_compute_job", {"input_file": str(xyz), "job_type": "xtb"}, policy
    )
    assert ok.allowed, ok.reason
    # 白名单无 xtb：拦截
    blocked = intercept(
        "submit_compute_job",
        {"input_file": str(xyz), "job_type": "xtb"},
        MethodPolicy(allowed_methods=["b3lyp"]),
    )
    assert not blocked.allowed
    # 同一 xyz 以 gaussian job_type 提交：内容无法验证，strict fail-closed 不弱化
    assert not intercept(
        "submit_compute_job", {"input_file": str(xyz), "job_type": "gaussian"}, policy
    ).allowed


# ---------------------------------------------------------------------------
# electronic_analysis 复用公共能量解析
# ---------------------------------------------------------------------------


def test_electronic_analysis_xtb_stdout_parser_matches_shared_primitives():
    from cloudra.tools.Chemtool.electronic_analysis import ElectronicAnalysis

    data = ElectronicAnalysis._parse_xtb_stdout(SP_FIXTURE.read_text())
    assert data["total_energy_eh"] == pytest.approx(-5.070320041234)
    assert data["gap_ev"] == pytest.approx(12.345678901234)
