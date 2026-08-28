"""ORCA frames: engine/job-type detection, thermochemistry, frame extraction."""

from pathlib import Path

import pytest

pytest.importorskip("cclib", reason="orca_frames requires cclib (chem extra)")

from cloudra.tools.core import orca_frames
from cloudra.tools.core.qm_engine import detect_qm_engine

ORCA_FIXTURES = Path(__file__).parent / "fixtures" / "orca"
GAUSSIAN_FIXTURES = Path(__file__).parent / "fixtures" / "gaussian"


def test_engine_detection_distinguishes_orca_from_gaussian():
    assert detect_qm_engine(str(ORCA_FIXTURES / "co2_freq_orca42.out")) == "orca"
    assert detect_qm_engine(str(ORCA_FIXTURES / "dvb_opt_orca42.out")) == "orca"
    assert detect_qm_engine(str(GAUSSIAN_FIXTURES / "water_opt_freq_g16.out")) == "gaussian"
    assert detect_qm_engine(str(GAUSSIAN_FIXTURES / "hcn_ts_irc_g16.log")) == "gaussian"


def test_orca_job_type_detection():
    assert orca_frames.detect_job_types(str(ORCA_FIXTURES / "co2_freq_orca42.out")) == {"opt", "freq"}
    assert orca_frames.detect_job_types(str(ORCA_FIXTURES / "dvb_opt_orca42.out")) == {"opt"}
    assert orca_frames.detect_job_types(str(ORCA_FIXTURES / "dvb_scan_unrelaxed_orca42.out")) == {"scan"}
    assert orca_frames.detect_job_types(str(ORCA_FIXTURES / "hcn_irc_orca60.out")) == {"irc"}


def test_orca_irc_extraction_from_main_output():
    """ORCA IRC 的点数/收敛/端点能量从主输出的 FORWARD/BACKWARD 迭代块与
    IRC PATH SUMMARY 提取（无需追 trj 边文件），供 short_irc 阶段绑定。"""
    meta = orca_frames.extract_irc(str(ORCA_FIXTURES / "hcn_irc_orca60.out"))
    assert meta["num_points_forward"] == 5
    assert meta["num_points_backward"] == 7
    assert meta["forward_converged"] is True
    assert meta["backward_converged"] is True
    # PATH SUMMARY 首行=反应物端、末行=产物端；"<= TS" 行为 TS 能量（最高）
    assert meta["endpoint_energies_hartree"] == pytest.approx((-1404.7228, -1404.7223))
    assert meta["ts_energy_hartree"] == pytest.approx(-1404.7175)
    assert meta["ts_energy_hartree"] > max(meta["endpoint_energies_hartree"])


def test_orca_thermochemistry_matches_gaussian_field_semantics():
    thermo = orca_frames.extract_thermochemistry(str(ORCA_FIXTURES / "co2_freq_orca42.out"))

    # 修正量
    assert thermo["zero_point_correction_hartree"] == pytest.approx(0.00684398)
    # 含 ZPE 口径（Total thermal correction 0.00309561 + ZPE 0.00684398）
    assert thermo["thermal_energy_correction_hartree"] == pytest.approx(0.00993959)
    assert thermo["thermal_enthalpy_correction_hartree"] == pytest.approx(0.00094421)
    assert thermo["thermal_gibbs_correction_hartree"] == pytest.approx(-0.01495982)
    # 总量
    assert thermo["total_thermal_energy_hartree"] == pytest.approx(-184.74782658)
    assert thermo["total_enthalpy_hartree"] == pytest.approx(-184.74688237)
    assert thermo["total_gibbs_free_energy_hartree"] == pytest.approx(-184.77272599)
    # 派生：E(el) + ZPE = -184.75776616 + 0.00684398
    assert thermo["total_zero_point_energy_hartree"] == pytest.approx(-184.75092218)


def test_orca_opt_frames_carry_convergence_and_xyz():
    frames = orca_frames.extract_frames(str(ORCA_FIXTURES / "dvb_opt_orca42.out"))
    assert len(frames) == 4
    assert all(f.xyz for f in frames)
    assert all(f.scf_energy_hartree is not None for f in frames)
    assert frames[-1].converged is True


def test_orca_unrelaxed_scan_frames_have_parameter_series():
    frames = orca_frames.extract_frames(str(ORCA_FIXTURES / "dvb_scan_unrelaxed_orca42.out"))
    assert len(frames) == 12
    rx = [f.reaction_coordinate for f in frames]
    assert rx[0] == pytest.approx(0.0)
    assert rx[1] == pytest.approx(32.72727273)
    assert all(v is not None for v in rx)
    # 单调递增的二面角扫描
    assert rx == sorted(rx)


@pytest.mark.asyncio
async def test_log_parser_orca_irc_end_to_end():
    """log_parser 走 ORCA 引擎时透出 short_irc deriver 消费的字段，
    使 ORCA 路线的 short_irc 阶段绑定可达（不再结构性断供）。"""
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(
            log_path=str(ORCA_FIXTURES / "hcn_irc_orca60.out"),
            properties=["job_type", "irc"],
        ),
        session=None,
    )
    assert result.is_success is True
    assert result.job_types == ["irc"]
    assert result.irc_num_points_forward == 5
    assert result.irc_num_points_backward == 7
    assert result.irc_both_directions_converged is True
    assert result.irc_endpoint_energies_hartree == pytest.approx(
        [-1404.7228, -1404.7223]
    )
