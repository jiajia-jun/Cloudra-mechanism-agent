from pathlib import Path

import pytest

from cloudra.tools.Chemtool.log_parser import (
    LogParser,
    LogParser_input_schema,
    _extract_gaussian_thermochemistry,
)

FIXTURE = Path(__file__).parent / "fixtures" / "gaussian" / "water_opt_freq_g16.out"


@pytest.mark.asyncio
async def test_gaussian_thermochemistry_distinguishes_corrections_from_totals():
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(FIXTURE), properties=["thermochemistry"]),
        session=None,
    )

    assert result.is_success is True
    assert result.zero_point_correction_hartree == pytest.approx(0.024385)
    assert result.thermal_energy_correction_hartree == pytest.approx(0.027218)
    assert result.thermal_enthalpy_correction_hartree == pytest.approx(0.028162)
    assert result.thermal_gibbs_correction_hartree == pytest.approx(0.006648)
    assert result.total_enthalpy_hartree == pytest.approx(-74.937739)
    assert result.total_gibbs_free_energy_hartree == pytest.approx(-74.959254)

    # 兼容字段保留原有调用方式，但不能再把 cclib 的总焓冒充热能校正。
    assert result.zero_point_energy_hartree == pytest.approx(0.024385)
    assert result.thermal_energy_hartree == pytest.approx(0.027218)
    assert result.enthalpy_hartree == pytest.approx(-74.937739)
    assert result.gibbs_free_energy_hartree == pytest.approx(-74.959254)


def test_thermochemistry_parser_never_mixes_separate_summary_blocks(tmp_path):
    log = tmp_path / "two_freq_jobs.log"
    log.write_text(
        """Zero-point correction= 0.010000
Thermal correction to Energy= 0.020000
Thermal correction to Enthalpy= 0.030000
Thermal correction to Gibbs Free Energy= 0.040000
Sum of electronic and zero-point Energies= -9.990000
Sum of electronic and thermal Energies= -9.980000
Sum of electronic and thermal Enthalpies= -9.970000
Sum of electronic and thermal Free Energies= -9.960000
Zero-point correction= 0.110000
Thermal correction to Energy= 0.120000
""",
        encoding="utf-8",
    )

    values = _extract_gaussian_thermochemistry(str(log))

    assert values["zero_point_correction_hartree"] == pytest.approx(0.010000)
    assert values["thermal_energy_correction_hartree"] == pytest.approx(0.020000)
    assert values["total_gibbs_free_energy_hartree"] == pytest.approx(-9.960000)


ORCA_FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "co2_freq_orca42.out"


@pytest.mark.asyncio
async def test_orca_log_full_parse_matches_gaussian_field_semantics():
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(ORCA_FIXTURE)), session=None,
    )

    assert result.is_success is True
    assert result.engine == "orca"
    assert result.job_types == ["freq", "opt"]
    assert result.normal_termination is True
    assert result.scf_energy_hartree == pytest.approx(-184.75776616)
    assert result.dipole_moment_debye == pytest.approx(0.0)
    assert result.zero_point_correction_hartree == pytest.approx(0.00684398)
    assert result.thermal_energy_correction_hartree == pytest.approx(0.00993959)
    assert result.total_enthalpy_hartree == pytest.approx(-184.74688237)
    assert result.total_gibbs_free_energy_hartree == pytest.approx(-184.77272599)
    assert result.imaginary_frequencies == []
    assert result.mulliken_charges is not None


@pytest.mark.asyncio
async def test_orca_opt_without_freq_does_not_fake_zero_imaginary():
    fixture = Path(__file__).parent / "fixtures" / "orca" / "dvb_opt_orca42.out"
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(fixture)), session=None,
    )

    assert result.is_success is True
    assert result.job_types == ["opt"]
    # 无频率数据时必须保持 None（不得被 DAG 侧当成零虚频极小点）
    assert result.frequencies_cm is None
    assert result.imaginary_frequencies is None
