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
