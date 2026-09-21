import json
import math
from pathlib import Path
from types import SimpleNamespace

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


def test_raw_rrho_rejects_saddle_frequency_job(monkeypatch):
    """n_imag != 0 的频率作业不得给出 complete 热化学。"""
    fake_data = SimpleNamespace(
        temperature=298.15,
        pressure=1.0,
        vibfreqs=[-412.3, 100.0, 200.0],
    )
    monkeypatch.setattr("cclib.io.ccread", lambda _path: fake_data)

    record, error = thermo_mod._load_raw_rrho_record(
        ThermoSpecies(name="ts", log_path=str(WATER_FREQ), coefficient=1),
        temperature=298.15,
        standard_state="gas_1atm",
        concentration_molar=None,
    )
    assert record is None
    assert error is not None
    assert "n_imag" in error


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
    assert captured["command"][captured["command"].index("--qs") + 1] == "grimme"
    assert captured["command"][captured["command"].index("--conc") + 1] == "1"
    assert captured["command"][captured["command"].index("--temp") + 1] == "310"
    assert captured["command"][captured["command"].index("-f") + 1] == "80"


@pytest.mark.asyncio
async def test_goodvibes_truhlar_scheme_and_custom_concentration(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        json_path = Path(command[command.index("--json") + 1])
        json_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "goodvibes_version": "4.2.0-test",
                "options": {"QS": "truhlar", "temperature": 298.15, "conc": 0.5},
                "results": [
                    {
                        "file": str(WATER_FREQ.resolve()),
                        "name": WATER_FREQ.stem,
                        "thermo": {
                            "scf_energy": -75.0,
                            "qh_enthalpy": -74.98,
                            "qh_gibbs_free_energy": -75.02,
                        },
                    }
                ],
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
            qh_scheme="truhlar",
            standard_state="solution_custom",
            concentration_molar=0.5,
            frequency_cutoff_cm=120.0,
        ),
        session=None,
    )

    assert result.status == "complete"
    assert captured["command"][captured["command"].index("--qs") + 1] == "truhlar"
    assert captured["command"][captured["command"].index("--conc") + 1] == "0.5"
    assert captured["command"][captured["command"].index("-f") + 1] == "120"
    assert "qh_scheme=truhlar" in " ".join(result.assumptions) or any(
        "truhlar" in item for item in result.assumptions
    )
    assert result.provenance["qh_scheme"] == "truhlar"


@pytest.mark.asyncio
async def test_goodvibes_gas_omits_conc_flag(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        json_path = Path(command[command.index("--json") + 1])
        json_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "goodvibes_version": "4.2.0-test",
                "results": [
                    {
                        "file": str(WATER_FREQ.resolve()),
                        "name": WATER_FREQ.stem,
                        "thermo": {
                            "scf_energy": -75.0,
                            "qh_enthalpy": -74.97,
                            "qh_gibbs_free_energy": -75.01,
                        },
                    }
                ],
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
            standard_state="gas_1atm",
        ),
        session=None,
    )

    assert result.status == "complete"
    assert "--conc" not in captured["command"]
    assert "-c" not in captured["command"]


# Fixture text mirrors GoodVibes 3.2 README Example 1 table layout.
_GOODVIBES_README_TABLE = """
   Structure                    E        ZPE             H        T.S     T.qh-S          G(T)       qh-G(T)
   *********************************************************************************************************
o  methylaniline      -326.664901   0.142118   -326.514489   0.039668   0.039465   -326.554157   -326.553954
   *********************************************************************************************************
"""


def test_parse_goodvibes_readme_text_table():
    entries, error = thermo_mod._parse_goodvibes_text_table(_GOODVIBES_README_TABLE)

    assert error is None
    assert len(entries) == 1
    assert entries[0]["name"] == "methylaniline"
    assert entries[0]["scf_energy"] == pytest.approx(-326.664901)
    assert entries[0]["qh_enthalpy"] == pytest.approx(-326.514489)
    assert entries[0]["qh_gibbs_free_energy"] == pytest.approx(-326.553954)


def test_parse_goodvibes_text_table_missing_header_is_inconclusive():
    entries, error = thermo_mod._parse_goodvibes_text_table("no thermo table here\n")

    assert entries == []
    assert error is not None
    assert "qh-G(T)" in error


@pytest.mark.asyncio
async def test_goodvibes_falls_back_to_stdout_table_when_json_missing(monkeypatch):
    def fake_run(command, **kwargs):
        # Deliberately do not write the --json path.
        return SimpleNamespace(
            returncode=0,
            stdout=_GOODVIBES_README_TABLE.replace("methylaniline", WATER_FREQ.stem),
            stderr="",
        )

    monkeypatch.setattr(thermo_mod.shutil, "which", lambda _name: "/usr/bin/goodvibes")
    monkeypatch.setattr(thermo_mod.subprocess, "run", fake_run)
    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[ThermoSpecies(name="water", log_path=str(WATER_FREQ), coefficient=1)],
            backend="goodvibes",
        ),
        session=None,
    )

    assert result.status == "complete"
    assert result.provenance.get("parse_source") == "stdout_table"
    assert result.species[0]["gibbs_free_energy_hartree"] == pytest.approx(-326.553954)


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
async def test_raw_rrho_cclib_parse_crash_is_inconclusive_not_raised(monkeypatch):
    """cclib 对不兼容日志（如 cclib 1.8.1 读 ORCA 6.1.1 全抛 IndexError）必须归入
    inconclusive 通道，裸异常不得逃逸 tool_call。"""

    def boom(_path):
        raise IndexError("list index out of range")

    monkeypatch.setattr("cclib.io.ccread", boom)

    record, error = thermo_mod._load_raw_rrho_record(
        ThermoSpecies(name="orca", log_path=str(WATER_FREQ), coefficient=1),
        temperature=298.15,
        standard_state="gas_1atm",
        concentration_molar=None,
    )
    assert record is None
    assert error is not None
    assert "cclib" in error
    assert "IndexError" in error

    result = await ThermoAnalysis().tool_call(
        ThermoAnalysis_input_schema(
            species=[ThermoSpecies(name="orca", log_path=str(WATER_FREQ), coefficient=1)],
            backend="raw_rrho",
        ),
        session=None,
    )
    assert result.is_success is True
    assert result.status == "inconclusive"
    assert result.reaction == {}
    assert "IndexError" in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sp_energy", "expected_source"),
    [
        # GoodVibes 4.x JSON 恒写 sp_energy；与 scf_energy 相同 = 未做 SPC，不能标 goodvibes_spc
        (-75.0, "frequency_log_scf"),
        (-75.000000005, "frequency_log_scf"),  # 数值噪声级差异（<1e-8 Eh）不算 SPC
        (-75.2, "goodvibes_spc"),              # 显著不同 = 真做了 SPC
    ],
)
async def test_goodvibes_spc_label_only_when_sp_differs_from_scf(
    monkeypatch, sp_energy, expected_source,
):
    def fake_run(command, **kwargs):
        json_path = Path(command[command.index("--json") + 1])
        json_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "goodvibes_version": "4.3.0-test",
                "results": [
                    {
                        "file": str(WATER_FREQ.resolve()),
                        "name": WATER_FREQ.stem,
                        "thermo": {
                            "scf_energy": -75.0,
                            "sp_energy": sp_energy,
                            "qh_enthalpy": -74.97,
                            "qh_gibbs_free_energy": -75.01,
                        },
                    }
                ],
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

    assert result.status == "complete"
    assert result.species[0]["energy_source"] == expected_source


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
