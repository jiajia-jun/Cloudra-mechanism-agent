"""Native TS writers preserve declared species through input and log annotations."""

from pathlib import Path

import pytest

from cloudra.benchmark.integrity import scan_evidence_files
from cloudra.tools.core import ts_process
from cloudra.tools.core.calculation_intent import inspect_input, native_input_geometry
from cloudra.tools.core.gaussian_frames import FrameRecord
from cloudra.tools.core.molecule import read_molecule
from tests.ts_fixtures import calculation_input

_REACTANT = "[F-].CCl"
_PRODUCT = "CF.[Cl-]"
_ATOMS = [
    ("F", (-2.0, 0.0, 0.0)),
    ("C", (0.0, 0.0, 0.0)),
    ("Cl", (1.8, 0.0, 0.0)),
    ("H", (0.0, 1.0, 0.0)),
    ("H", (0.0, -0.5, 0.8)),
    ("H", (0.0, -0.5, -0.8)),
]
_XYZ = "6\nwriter geometry fixture\n" + "\n".join(
    f"{symbol} {x} {y} {z}" for symbol, (x, y, z) in _ATOMS
) + "\n"


def _record(tmp_path, engine):
    candidate = tmp_path / "candidate.xyz"
    candidate.write_text(_XYZ)
    molecule = read_molecule(input_text=_XYZ, input_format="xyz", charge=-1)
    return ts_process.TsProcessRecord(
        run_id="ts_0001", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        structures={"candidate": molecule, "reactant": molecule, "product": molecule,
                    "product_to_reactant": tuple(range(molecule.GetNumAtoms()))}, path_kind="provided",
        input=calculation_input(
            reactant_smiles=_REACTANT, product_smiles=_PRODUCT,
            charge=-1, method="HF/STO-3G", engine=engine,
        ),
    )


def _upstream_step(record, tmp_path, purpose, engine):
    directory = tmp_path / "upstream" / purpose
    directory.mkdir(parents=True)
    path = directory / ("input.inp" if engine == "orca" else "input.gjf")
    path.write_text("upstream input fixture")
    step = ts_process.TsJobStep(purpose=purpose, job_id=1, input_path=str(path), state="done")
    if purpose in {'reactant_opt', 'product_opt'}:
        import hashlib
        step.endpoint_source = ts_process.EndpointSource(kind='species_reference', label=purpose.partition('_')[0],
            source_path=str(Path(record.run_dir) / "candidate.xyz"), sha256=hashlib.sha256(Path(str(Path(record.run_dir) / "candidate.xyz")).read_bytes()).hexdigest())
    record.job_steps.append(step)
    log = Path(ts_process._refinement_log_path(record, step))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("upstream geometry is supplied by the parsed-frame fixture")
    (directory / "optimized.xyz").write_text(_XYZ)


def _assert_annotated_input(tmp_path, path, engine, expected_smiles, expected_task):
    path = Path(path)
    content = path.read_text()
    intent = inspect_input(content, engine=engine)
    assert intent.tasks == {expected_task}
    assert (intent.charge, intent.multiplicity) == (-1, 1)
    assert native_input_geometry(content, engine=engine) == _ATOMS
    if engine == "orca":
        assert content.splitlines()[0].startswith("# ")
        # Native ORCA echoes each input line with a numbered prefix.
        echo = "\n".join(f"| {index}> {line}" for index, line in enumerate(content.splitlines(), 1))
    else:
        assert f"smiles: {expected_smiles}\n\n-1 1\n" in content
        echo = content
    echo_path = path.with_suffix(".echo.log")
    echo_path.write_text(echo)
    files = {row.path: row for row in scan_evidence_files(tmp_path)}
    assert files[str(path.relative_to(tmp_path))].smiles_found == [expected_smiles]
    assert files[str(echo_path.relative_to(tmp_path))].smiles_found == [expected_smiles]


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("engine", ["orca", "gaussian"])
@pytest.mark.parametrize("purpose", ["ts_opt", "frequency", "irc"])
def test_native_ts_input_and_echo_bind_declared_step_reactant(tmp_path, monkeypatch, engine, purpose):
    record = _record(tmp_path, engine)
    directory = tmp_path / purpose
    directory.mkdir()
    if purpose == "frequency":
        _upstream_step(record, tmp_path, "ts_opt", engine)
        monkeypatch.setattr(
            f"cloudra.tools.core.{engine}_frames.extract_frames",
            lambda _path: [FrameRecord(frame=0, xyz=_XYZ)],
        )
    elif purpose == "irc":
        _upstream_step(record, tmp_path, "frequency", engine)
    writer = {
        "ts_opt": ts_process._write_refinement_input,
        "frequency": ts_process._write_frequency_input,
        "irc": ts_process._write_irc_input,
    }[purpose]
    error, path = writer(record, str(directory))
    assert error == ""
    _assert_annotated_input(tmp_path, path, engine, _REACTANT, purpose)


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("engine", ["orca", "gaussian"])
@pytest.mark.parametrize("role, expected_smiles", [("reactant", _REACTANT), ("product", _PRODUCT)])
@pytest.mark.parametrize("task", ["opt", "frequency"])
def test_native_endpoint_input_records_declaration_without_observed_identity(
    tmp_path, monkeypatch, engine, role, expected_smiles, task
):
    record = _record(tmp_path, engine)
    directory = tmp_path / f"{role}_{task}"
    directory.mkdir()
    if task == "opt":
        _upstream_step(record, tmp_path, "irc", engine)
        monkeypatch.setattr(
            "cloudra.tools.Chemtool.ts_guess.TsGuess._extract_irc_endpoints",
            lambda *_args, **_kwargs: {"path_a": str(Path(record.run_dir) / "candidate.xyz"), "path_b": str(Path(record.run_dir) / "candidate.xyz")},
        )
    else:
        _upstream_step(record, tmp_path, f"{role}_opt", engine)
        monkeypatch.setattr(ts_process, "_endpoint_opt_frame", lambda *_args: (_XYZ, ""))
    error, path = ts_process._write_endpoint_input(record, str(directory), role, task)
    assert error == ""
    expected_task = "minimum_opt" if task == "opt" else "frequency"
    content = Path(path).read_text()
    assert inspect_input(content, engine=engine).tasks == {expected_task}
    assert native_input_geometry(content, engine=engine) == _ATOMS
    assert f'declared_species: {expected_smiles}' in content
    echo = '\n'.join(f'| {index}> {line}' for index, line in enumerate(content.splitlines(), 1))
    echo_path = Path(path).with_suffix('.echo.log')
    echo_path.write_text(echo)
    files = {row.path: row for row in scan_evidence_files(tmp_path)}
    assert files[str(Path(path).relative_to(tmp_path))].smiles_found == []
    assert files[str(echo_path.relative_to(tmp_path))].smiles_found == []
