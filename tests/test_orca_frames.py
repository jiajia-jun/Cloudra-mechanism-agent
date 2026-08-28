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
