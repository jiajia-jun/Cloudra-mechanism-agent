"""Offline native-input regressions for the shared TS scan writer."""

from pathlib import Path

import pytest
from pydantic import ValidationError

pytest.importorskip("numpy")
pytest.importorskip("ase")
pytest.importorskip("rdkit")

from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

_HYDRONIUM_XYZ = """4
hydronium coordinates; charge must be declared separately
O 0.00 0.00 0.00
H 0.96 0.00 0.00
H -0.24 0.93 0.00
H -0.24 -0.31 0.88
"""


def _arguments(tmp_path, *, engine="gaussian", **overrides):
    base = 0 if engine == "orca" else 1
    arguments = dict(
        mode="scan_prepare",
        engine=engine,
        method="B3LYP",
        basis_set="def2SVP",
        input_text=_HYDRONIUM_XYZ,
        scans=[dict(coord_type="bond", atoms=[base, base + 1], scan_end=1.5, scan_steps=6)],
        output_path=str(tmp_path / ("reaction_scan.inp" if engine == "orca" else "reaction_scan.gjf")),
    )
    arguments.update(overrides)
    return arguments


def _render(arguments):
    result = TsGuess()._scan_prepare(TsGuess_input_schema.model_validate(arguments))
    assert result.is_success, result.message
    assert result.input_file_path == arguments["output_path"]
    return Path(result.input_file_path).read_text(encoding="utf-8")


def test_gaussian_scan_uses_shared_electronic_state_resources_and_checkpoint(tmp_path):
    arguments = _arguments(
        tmp_path,
        charge=1,
        multiplicity=1,
        nproc=8,
        mem="8192MB",
        freeze=[dict(coord_type="bond", atoms=[1, 3])],
    )
    content = _render(arguments)
    lines = content.splitlines()

    assert "%nproc=8" in lines
    assert "%mem=8192MB" in lines
    checkpoint = next(line.removeprefix("%chk=") for line in lines if line.startswith("%chk="))
    assert Path(checkpoint).is_absolute()
    assert Path(checkpoint) == Path(arguments["output_path"]).with_suffix(".chk")
    assert "\n1 1\n" in content
    route = next(line for line in lines if line.startswith("#"))
    assert "modredundant" in route.lower()
    assert "b3lyp/def2svp" in route.lower()
    scan = next(line.split() for line in lines if line.split()[:5] == ["B", "1", "2", "S", "6"])
    assert float(scan[5]) == pytest.approx((1.5 - 0.96) / 6)
    assert any(line.split() == ["B", "1", "3", "F"] for line in lines)


@pytest.mark.parametrize("engine", ["gaussian", "orca"])
def test_independent_xyz_scan_requires_explicit_charge(tmp_path, engine):
    arguments = _arguments(tmp_path, engine=engine)
    with pytest.raises(ValueError, match="charge"):
        TsGuess()._scan_prepare(TsGuess_input_schema.model_validate(arguments))
    assert not Path(arguments["output_path"]).exists()


@pytest.mark.parametrize("engine", ["gaussian", "orca"])
@pytest.mark.parametrize("extension", ["mol", "sdf"])
def test_scan_inherits_mol_or_sdf_formal_charge(tmp_path, engine, extension):
    from rdkit import Chem

    molecule = Chem.AddHs(Chem.MolFromSmiles("[OH3+]"))
    conformer = Chem.Conformer(molecule.GetNumAtoms())
    for index, coordinates in enumerate(((0, 0, 0), (0.96, 0, 0), (-0.24, 0.93, 0), (-0.24, -0.31, 0.88))):
        conformer.SetAtomPosition(index, coordinates)
    molecule.AddConformer(conformer)
    source = tmp_path / f"charged_source.{extension}"
    source.write_text(Chem.MolToMolBlock(molecule) + ("\n$$$$\n" if extension == "sdf" else ""))
    arguments = _arguments(tmp_path, engine=engine, input_path=str(source), multiplicity=1, nproc=8, mem="8192MB")
    arguments.pop("input_text")

    content = _render(arguments)

    assert ("* xyz 1 1" if engine == "orca" else "\n1 1\n") in content


@pytest.mark.parametrize("scan_mode", ["concerted", "grid"])
def test_orca_scan_preserves_two_coordinate_mode_freeze_and_shared_resources(tmp_path, scan_mode):
    second_steps = 6 if scan_mode == "concerted" else 8
    arguments = _arguments(
        tmp_path,
        engine="orca",
        charge=1,
        multiplicity=1,
        nproc=8,
        mem="8192MB",
        scans=[
            dict(coord_type="bond", atoms=[0, 1], scan_end=1.5, scan_steps=6),
            dict(coord_type="bond", atoms=[0, 2], scan_end=1.8, scan_steps=second_steps),
        ],
        scan_mode=scan_mode,
        freeze=[dict(coord_type="bond", atoms=[0, 3])],
    )

    content = _render(arguments)
    tokens = [line.split() for line in content.splitlines()]

    assert "%pal nprocs 8 end" in content
    assert "%maxcore 1024" in content
    assert "* xyz 1 1" in content
    assert any(row[:4] == ["B", "0", "1", "="] and row[-1] == "6" for row in tokens)
    assert any(row[:4] == ["B", "0", "2", "="] and row[-1] == str(second_steps) for row in tokens)
    assert ["{", "B", "0", "3", "C", "}"] in tokens
    assert ("Simul_Scan true" in content) is (scan_mode == "concerted")


@pytest.mark.parametrize("legacy", [{"spin": 1}, {"nprocs": 8}, {"memory_mb": 8192}, {"job_name": "old_scan"}])
def test_scan_rejects_removed_duplicate_fields(tmp_path, legacy):
    arguments = _arguments(tmp_path, engine="orca", charge=1, **legacy)
    field = next(iter(legacy))
    with pytest.raises(ValidationError, match=field):
        TsGuess_input_schema.model_validate(arguments)


def test_scan_wire_schema_exposes_only_shared_writer_resource_and_spin_fields():
    properties = TsGuess_input_schema.to_parameters_schema()["properties"]
    assert {"charge", "multiplicity", "nproc", "mem"} <= properties.keys()
    assert not {"spin", "nprocs", "memory_mb", "job_name"} & properties.keys()


def test_xtb_scan_rejects_explicit_native_writer_memory_but_keeps_its_default(tmp_path):
    arguments = _arguments(
        tmp_path,
        engine="xtb",
        method="GFN2-xTB",
        basis_set="",
        charge=1,
        multiplicity=1,
        nproc=8,
        force_constant=0.1,
        scans=[dict(coord_type="bond", atoms=[1, 2], scan_start=0.96, scan_end=1.5, scan_steps=6)],
        output_path=str(tmp_path / "scan-task.json"),
    )
    request = TsGuess_input_schema.model_validate(arguments)
    assert "mem" not in request.model_fields_set

    with pytest.raises(ValidationError, match="mem"):
        TsGuess_input_schema.model_validate(dict(arguments, mem="8192MB"))


@pytest.mark.parametrize("engine", ["gaussian", "orca"])
def test_scan_calls_the_shared_native_renderer(tmp_path, monkeypatch, engine):
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter

    native_renderer = getattr(QmInputWriter, "render_input", None)
    assert callable(native_renderer), "Scan preparation needs the shared native input renderer"
    rendered_requests = []

    def render(request, molecule):
        rendered_requests.append(request)
        return native_renderer(request, molecule)

    monkeypatch.setattr(QmInputWriter, "render_input", staticmethod(render))
    content = _render(_arguments(tmp_path, engine=engine, charge=1, multiplicity=1,
        electronic_character="closed_shell", nproc=8, mem="8192MB"))

    assert ("* xyz 1 1" if engine == "orca" else "\n1 1\n") in content
    assert len(rendered_requests) == 1
    request = rendered_requests[0]
    assert (request.charge, request.multiplicity, request.electronic_character) == (1, 1, "closed_shell")
    assert (request.nproc, request.mem) == (8, "8192MB")
