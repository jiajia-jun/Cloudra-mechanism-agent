from pathlib import Path
from types import SimpleNamespace

import json
import math

import pytest

import cloudra.tools.Chemtool.thermo_analysis as thermo_mod
from cloudra.tools.Chemtool.thermo_analysis import (
    ThermoAnalysis,
    ThermoAnalysis_input_schema,
    ThermoSpecies,
)


FIXTURES = Path(__file__).parent / "fixtures" / "gaussian"
WATER_FREQ = FIXTURES / "water_opt_freq_g16.out"
IRC_LOG = FIXTURES / "hcn_ts_irc_g16.log"


def test_reaction_arithmetic_uses_signed_stoichiometric_coefficients():
    reaction = thermo_mod._combine_species_records([
        {"name": "A", "coefficient": -2.0, "electronic_energy_hartree": -10.0,
         "enthalpy_hartree": -9.9, "gibbs_free_energy_hartree": -10.1},
        {"name": "B", "coefficient": 1.0, "electronic_energy_hartree": -19.8,
         "enthalpy_hartree": -19.6, "gibbs_free_energy_hartree": -20.0},
    ])

    assert reaction["delta_e_hartree"] == pytest.approx(0.2)
    assert reaction["delta_h_hartree"] == pytest.approx(0.2)
    assert reaction["delta_g_hartree"] == pytest.approx(0.2)
    assert reaction["delta_e_kcal_mol"] == pytest.approx(0.2 * thermo_mod._EH_TO_KCAL)


@pytest.mark.asyncio
async def test_raw_rrho_applies_numeric_single_point_without_losing_freq_correction():
    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[
                ThermoSpecies(name="A", log_path=str(WATER_FREQ), coefficient=-1,
                              single_point_energy_hartree=-75.0),
                ThermoSpecies(name="B", log_path=str(WATER_FREQ), coefficient=1,
                              single_point_energy_hartree=-74.99),
            ],
            backend="raw_rrho",
            temperature=298.15,
            standard_state="gas_1atm",
        ),
        session=None,
    )

    assert result.is_success is True
    assert result.status == "complete"
    assert result.reaction["delta_e_hartree"] == pytest.approx(0.01)
    assert result.reaction["delta_h_hartree"] == pytest.approx(0.01)
    assert result.reaction["delta_g_hartree"] == pytest.approx(0.01)
    assert all(row["energy_source"] == "supplied_single_point" for row in result.species)
    assert result.provenance["backend"] == "raw_rrho"
    assert "temperature=298.15 K" in result.table
    assert "standard_state=gas_1atm" in result.table
    assert "backend=raw_rrho" in result.table


def test_raw_rrho_uses_literal_gaussian_corrections_not_last_cclib_scf(monkeypatch):
    fake_data = SimpleNamespace(
        scfenergies=[-1.0],  # deliberately unrelated to the thermochemistry block
        temperature=298.15,
        pressure=1.0,
    )
    monkeypatch.setattr("cclib.io.ccread", lambda _path: fake_data)

    record, error = thermo_mod._load_raw_rrho_record(
        ThermoSpecies(
            name="water",
            log_path=str(WATER_FREQ),
            coefficient=1,
            single_point_energy_hartree=-75.0,
        ),
        temperature=298.15,
        standard_state="gas_1atm",
        concentration_molar=None,
    )

    assert error is None
    assert record["enthalpy_correction_hartree"] == pytest.approx(0.028162)
    assert record["gibbs_correction_hartree"] == pytest.approx(0.006648)
    assert record["enthalpy_hartree"] == pytest.approx(-74.971838)
    assert record["gibbs_free_energy_hartree"] == pytest.approx(-74.993352)


def test_raw_rrho_converts_nonstandard_source_pressure_to_one_atm(monkeypatch):
    fake_data = SimpleNamespace(temperature=298.15, pressure=2.0)
    monkeypatch.setattr("cclib.io.ccread", lambda _path: fake_data)

    record, error = thermo_mod._load_raw_rrho_record(
        ThermoSpecies(name="water", log_path=str(WATER_FREQ), coefficient=1),
        temperature=298.15,
        standard_state="gas_1atm",
        concentration_molar=None,
    )

    expected = (
        thermo_mod._R_J_MOL_K * 298.15 * math.log(1.0 / 2.0)
        / thermo_mod._HARTREE_J_MOL
    )
    assert error is None
    assert record["standard_state_g_correction_hartree"] == pytest.approx(expected)


def test_raw_rrho_missing_log_temperature_or_pressure_is_inconclusive(monkeypatch):
    monkeypatch.setattr("cclib.io.ccread", lambda _path: SimpleNamespace())

    record, error = thermo_mod._load_raw_rrho_record(
        ThermoSpecies(name="water", log_path=str(WATER_FREQ), coefficient=1),
        temperature=298.15,
        standard_state="gas_1atm",
        concentration_molar=None,
    )

    assert record is None
    assert "温度" in error or "压力" in error


@pytest.mark.asyncio
async def test_raw_rrho_missing_thermochemistry_is_inconclusive():
    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[ThermoSpecies(name="irc", log_path=str(IRC_LOG), coefficient=1)],
            backend="raw_rrho",
        ),
        session=None,
    )

    assert result.is_success is True
    assert result.status == "inconclusive"
    assert result.reaction == {}
    assert "thermochemistry" in result.message.lower()


@pytest.mark.asyncio
async def test_partial_single_point_coverage_is_inconclusive_instead_of_mixing_levels():
    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[
                ThermoSpecies(name="A", log_path=str(WATER_FREQ), coefficient=-1,
                              single_point_energy_hartree=-75.0),
                ThermoSpecies(name="B", log_path=str(WATER_FREQ), coefficient=1),
            ],
            backend="raw_rrho",
        ),
        session=None,
    )

    assert result.is_success is True
    assert result.status == "inconclusive"
    assert result.reaction == {}
    assert "single-point" in result.message


@pytest.mark.asyncio
async def test_missing_goodvibes_never_silently_falls_back(monkeypatch):
    monkeypatch.setattr(thermo_mod.shutil, "which", lambda _name: None)

    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[ThermoSpecies(name="water", log_path=str(WATER_FREQ), coefficient=1)],
            backend="goodvibes",
        ),
        session=None,
    )

    assert result.is_success is True
    assert result.status == "inconclusive"
    assert result.provenance["backend"] == "goodvibes"
    assert result.provenance["fallback_used"] is False
    assert "GoodVibes" in result.message


@pytest.mark.asyncio
async def test_solution_standard_state_correction_respects_reaction_molecularity():
    common = [
        ThermoSpecies(name="A", log_path=str(WATER_FREQ), coefficient=-2),
        ThermoSpecies(name="B", log_path=str(WATER_FREQ), coefficient=1),
    ]
    gas = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(species=common, standard_state="gas_1atm"),
        session=None,
    )
    solution = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(species=common, standard_state="solution_1m"),
        session=None,
    )

    assert gas.status == solution.status == "complete"
    per_species = thermo_mod._standard_state_correction_hartree(298.15, 1.0, 1.0)
    # Δn = 1 - 2 = -1，因此反应自由能改变 -1 个标准态修正。
    assert (
        solution.reaction["delta_g_hartree"] - gas.reaction["delta_g_hartree"]
    ) == pytest.approx(-per_species)


@pytest.mark.asyncio
async def test_goodvibes_structured_output_and_command_are_preserved(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        json_path = Path(command[command.index("--json") + 1])
        payload = {
            "schema_version": "1.0",
            "goodvibes_version": "4.2.0-test",
            "options": {"Q": True, "temperature": 310.0, "conc": 1.0},
            "results": [
                {
                    "file": str(WATER_FREQ.resolve()),
                    "name": WATER_FREQ.stem,
                    "thermo": {
                        "scf_energy": -75.0,
                        "sp_energy": None,
                        "qh_enthalpy": -74.97,
                        "qh_gibbs_free_energy": -75.01,
                    },
                }
            ],
        }
        json_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(thermo_mod.shutil, "which", lambda _name: "/usr/bin/goodvibes")
    monkeypatch.setattr(thermo_mod.subprocess, "run", fake_run)
    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[
                ThermoSpecies(
                    name="water",
                    log_path=str(WATER_FREQ),
                    coefficient=1,
                    single_point_energy_hartree=-75.2,
                )
            ],
            backend="goodvibes",
            temperature=310.0,
            standard_state="solution_1m",
            frequency_cutoff_cm=80.0,
        ),
        session=None,
    )

    assert result.status == "complete"
    assert result.species[0]["enthalpy_hartree"] == pytest.approx(-75.17)
    assert result.species[0]["gibbs_free_energy_hartree"] == pytest.approx(-75.21)
    assert result.provenance["goodvibes_version"] == "4.2.0-test"
    assert result.provenance["command"] == captured["command"]
    assert "-q" in captured["command"]
    assert captured["command"][captured["command"].index("--conc") + 1] == "1"
    assert captured["command"][captured["command"].index("-f") + 1] == "80"


@pytest.mark.asyncio
async def test_goodvibes_rejects_unsupported_json_schema(monkeypatch):
    def fake_run(command, **kwargs):
        json_path = Path(command[command.index("--json") + 1])
        json_path.write_text(
            json.dumps({
                "schema_version": "2.0",
                "goodvibes_version": "future",
                "results": [],
            }),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(thermo_mod.shutil, "which", lambda _name: "/usr/bin/goodvibes")
    monkeypatch.setattr(thermo_mod.subprocess, "run", fake_run)
    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[ThermoSpecies(name="water", log_path=str(WATER_FREQ), coefficient=1)],
            backend="goodvibes",
        ),
        session=None,
    )

    assert result.status == "inconclusive"
    assert "schema_version" in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message_fragment"),
    [
        ([], "object"),
        (
            {
                "schema_version": "1.0",
                "results": [],
            },
            "goodvibes_version",
        ),
        (
            {
                "schema_version": "1.0",
                "goodvibes_version": "4.2.0",
                "results": [
                    {
                        "file": str(WATER_FREQ.resolve()),
                        "name": WATER_FREQ.stem,
                        "thermo": {
                            "scf_energy": -75.0,
                            "qh_enthalpy": "not-a-number",
                            "qh_gibbs_free_energy": -75.01,
                        },
                    }
                ],
            },
            "numeric",
        ),
    ],
)
async def test_goodvibes_malformed_json_is_inconclusive(monkeypatch, payload, message_fragment):
    def fake_run(command, **kwargs):
        json_path = Path(command[command.index("--json") + 1])
        json_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(thermo_mod.shutil, "which", lambda _name: "/usr/bin/goodvibes")
    monkeypatch.setattr(thermo_mod.subprocess, "run", fake_run)
    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[ThermoSpecies(name="water", log_path=str(WATER_FREQ), coefficient=1)],
            backend="goodvibes",
        ),
        session=None,
    )

    assert result.is_success is True
    assert result.status == "inconclusive"
    assert message_fragment in result.message
