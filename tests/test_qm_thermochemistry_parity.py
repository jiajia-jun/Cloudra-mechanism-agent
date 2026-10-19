"""Native thermochemistry keeps one block and one physical field definition."""

from pathlib import Path

import pytest

from cloudra.tools.Chemtool.log_parser import LogParser
from cloudra.tools.Chemtool.thermo_analysis import (
    ThermoAnalysis,
    ThermoAnalysis_input_schema,
    ThermoSpecies,
    _load_raw_rrho_record,
)
from cloudra.tools.core import gaussian_frames, orca_frames

FIXTURES = Path(__file__).parent / "fixtures"
GAUSSIAN = FIXTURES / "gaussian" / "water_opt_freq_g16.out"
ORCA = FIXTURES / "orca" / "co2_freq_orca42.out"


def _unreadable(_path):
    raise IndexError("synthetic cclib failure")


def test_orca_enthalpy_correction_is_h_minus_same_block_electronic_energy():
    values = orca_frames.extract_thermochemistry_from_text(ORCA.read_text())
    assert values["thermal_enthalpy_correction_hartree"] == pytest.approx(
        -184.74688237 - (-184.75776616), abs=1e-10,
    )
    assert values["electronic_energy_hartree"] == pytest.approx(-184.75776616)
    assert values["temperature_k"] == 298.15
    assert values["pressure_atm"] == 1.0


def test_orca_later_single_point_cannot_change_frequency_corrections():
    text = ORCA.read_text()
    text += "\nFINAL SINGLE POINT ENERGY -999.0\nORCA TERMINATED NORMALLY\n"
    values = orca_frames.extract_thermochemistry_from_text(text)
    assert values["thermal_gibbs_correction_hartree"] == pytest.approx(-0.01495983)
    assert values["total_zero_point_energy_hartree"] == pytest.approx(-184.75092218)


@pytest.mark.parametrize("engine,path", [("gaussian", GAUSSIAN), ("orca", ORCA)])
def test_last_incomplete_thermochemistry_block_does_not_borrow_old_fields(engine, path):
    if engine == "gaussian":
        tail = "\n - Thermochemistry -\n Temperature 400.0 Kelvin. Pressure 2.0 Atm.\nZero-point correction= 0.25\n"
        parser = gaussian_frames.extract_thermochemistry_from_text
    else:
        tail = "\nTHERMOCHEMISTRY AT 400.0K\nTemperature ... 400.0 K\nPressure ... 2.0 atm\nZero point energy ... 0.25 Eh\n"
        parser = orca_frames.extract_thermochemistry_from_text
    values = parser(path.read_text() + tail)
    assert values["zero_point_correction_hartree"] == 0.25
    assert values["temperature_k"] == 400.0
    assert values["pressure_atm"] == 2.0
    assert "total_enthalpy_hartree" not in values
    assert "total_gibbs_free_energy_hartree" not in values
    assert "electronic_energy_hartree" not in values


@pytest.mark.parametrize("path", [GAUSSIAN, ORCA])
def test_raw_rrho_native_material_survives_cclib_failure(path, monkeypatch):
    monkeypatch.setattr("cclib.io.ccread", _unreadable)
    record, error = _load_raw_rrho_record(
        ThermoSpecies(name="minimum", log_path=str(path), coefficient=1),
        temperature=298.15, standard_state="gas_1atm", concentration_molar=None,
    )
    assert error is None
    assert record["rrho_temperature_k"] == 298.15
    assert record["rrho_pressure_atm"] == 1.0
    assert record["gibbs_free_energy_hartree"] == pytest.approx(
        -74.9592535 if path == GAUSSIAN else -184.77272599,
    )


@pytest.mark.parametrize("engine,path", [("gaussian", GAUSSIAN), ("orca", ORCA)])
def test_log_parser_never_fills_last_partial_thermo_with_cclib_totals(engine, path, tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("cclib.io.ccread", lambda _path: SimpleNamespace(
        enthalpy=-1.0, freeenergy=-2.0, zpve=123.0,
    ))
    tail = (
        "\n - Thermochemistry -\n Temperature 400.0 Kelvin. Pressure 2.0 Atm.\nZero-point correction= 0.25\n"
        if engine == "gaussian" else
        "\nTHERMOCHEMISTRY AT 400.0K\nTemperature ... 400.0 K\nPressure ... 2.0 atm\nZero point energy ... 0.25 Eh\n"
    )
    log = tmp_path / f"partial_{engine}.out"
    log.write_text(path.read_text() + tail)
    result = LogParser()._parse_log(str(log), LogParser._resolve_requested_fields(["thermochemistry"]))
    assert result.is_success
    assert result.zero_point_correction_hartree == 0.25
    assert result.total_enthalpy_hartree is None
    assert result.total_gibbs_free_energy_hartree is None


@pytest.mark.parametrize("path,error_marker", [
    (GAUSSIAN, "Error termination via Lnk1e"),
    (ORCA, "ORCA finished by error termination"),
])
def test_raw_rrho_requires_native_success_even_with_complete_thermochemistry(path, error_marker, tmp_path, monkeypatch):
    monkeypatch.setattr("cclib.io.ccread", _unreadable)
    log = tmp_path / path.name
    log.write_text(path.read_text() + "\n" + error_marker + "\n")
    record, error = _load_raw_rrho_record(
        ThermoSpecies(name="failed", log_path=str(log), coefficient=1),
        temperature=298.15, standard_state="gas_1atm", concentration_molar=None,
    )
    assert record is None
    assert "terminat" in error.lower()


@pytest.mark.parametrize("path", [GAUSSIAN, ORCA])
def test_raw_rrho_rejects_changed_temperature_without_recomputing_native_corrections(path, monkeypatch):
    monkeypatch.setattr("cclib.io.ccread", _unreadable)
    record, error = _load_raw_rrho_record(
        ThermoSpecies(name="minimum", log_path=str(path), coefficient=1),
        temperature=310.0, standard_state="gas_1atm", concentration_molar=None,
    )
    assert record is None
    assert "298.15" in error and "310" in error


@pytest.mark.parametrize("engine,path", [("gaussian", GAUSSIAN), ("orca", ORCA)])
def test_raw_rrho_missing_frequencies_is_inconclusive(engine, path, tmp_path, monkeypatch):
    monkeypatch.setattr("cclib.io.ccread", _unreadable)
    log = tmp_path / path.name
    text = path.read_text()
    if engine == "gaussian":
        text = text.replace("Frequencies --", "Modes unavailable")
    else:
        text = text.replace("VIBRATIONAL FREQUENCIES", "Modes unavailable")
    log.write_text(text)
    record, error = _load_raw_rrho_record(
        ThermoSpecies(name="missing", log_path=str(log), coefficient=1),
        temperature=298.15, standard_state="gas_1atm", concentration_molar=None,
    )
    assert record is None
    assert "频率" in error


def test_orca_partial_thermo_does_not_treat_rt_as_full_enthalpy_correction():
    values = orca_frames.extract_thermochemistry_from_text(
        "THERMOCHEMISTRY AT 298.15K\nThermal Enthalpy correction ... 0.00094421 Eh\n"
        "Total Enthalpy ... -184.74688237 Eh\n",
    )
    assert values["total_enthalpy_hartree"] == pytest.approx(-184.74688237)
    assert "thermal_enthalpy_correction_hartree" not in values


@pytest.mark.asyncio
@pytest.mark.parametrize("path,enthalpy_correction", [(GAUSSIAN, 0.028162), (ORCA, 0.01088379)])
async def test_raw_rrho_public_tool_supports_both_engines_and_supplied_single_point(path, enthalpy_correction, monkeypatch):
    monkeypatch.setattr("cclib.io.ccread", _unreadable)
    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(species=[
            ThermoSpecies(name="minimum", log_path=str(path), coefficient=1,
                          single_point_energy_hartree=-200.0),
        ]),
        session=None,
    )
    assert result.is_success
    assert result.status == "complete"
    assert result.species[0]["energy_source"] == "supplied_single_point"
    assert result.species[0]["enthalpy_correction_hartree"] == pytest.approx(enthalpy_correction)
    assert result.reaction["delta_h_hartree"] == pytest.approx(-200.0 + enthalpy_correction)
    assert result.provenance["fallback_used"] is False
