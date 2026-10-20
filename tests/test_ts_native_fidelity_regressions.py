"""Offline TS stage rendering preserves native declarations without task guessing."""

from pathlib import Path

import pytest

pytest.importorskip("rdkit")
pytest.importorskip("ase")
pytest.importorskip("cclib")

from cloudra.tools.core import ts_process
from cloudra.tools.core.calculation_intent import inspect_input
from cloudra.tools.core.molecule import read_molecule
from cloudra.tools.core.qm_calculation import QmCalculation
from cloudra.tools.core.ts_inputs import TsInput
from tests.ts_fixtures import native_qm_log

_XYZ = "3\nowned geometry\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n"
_STAGES = {
    "ts_opt": ts_process._write_refinement_input,
    "frequency": ts_process._write_frequency_input,
    "irc": ts_process._write_irc_input,
}


@pytest.fixture(autouse=True)
def _never_submit_compute(monkeypatch):
    def refuse_submission(*args, **kwargs):
        pytest.fail("Native input regressions must not submit compute jobs")

    monkeypatch.setattr(ts_process, "_submit_step", refuse_submission)


def _prepare_stage(tmp_path, stage, *, engine="gaussian", **native):
    calculation = QmCalculation(engine=engine, method="HF", basis_set="STO-3G", **native)
    inputs = TsInput.model_validate(dict(
        reaction=dict(reactant_smiles="O", product_smiles="O", charge=0, multiplicity=1),
        ts_optimization=calculation,
        verification=dict(frequency=calculation, irc=calculation),
        execution=dict(cpus=3, memory_mb=4096),
    ))
    record = ts_process.TsProcessRecord(run_id="ts_0001", run_dir=str(tmp_path),
        workspace_dir=str(tmp_path), input=inputs)
    record.structures.candidate = read_molecule(input_text=_XYZ, input_format="xyz", charge=0)
    extension = "gjf" if engine == "gaussian" else "inp"
    if stage == "frequency":
        source = tmp_path / "source_optimization"
        source.mkdir()
        input_path = source / f"refine.{extension}"
        input_path.write_text("offline source input\n")
        log_name = "refine.log" if engine == "gaussian" else "refine.out"
        source.joinpath(log_name).write_text(native_qm_log(engine, ["O", "H", "H"],
            [[0., 0., 0.], [.96, 0., 0.], [-.24, .93, 0.]]))
        record.job_steps.append(ts_process.TsJobStep(purpose="ts_opt", state="done",
            input_path=str(input_path), actual_calculation=calculation))
    elif stage == "irc":
        source = tmp_path / "source_frequency"
        source.mkdir()
        input_path = source / f"frequency.{extension}"
        input_path.write_text("offline source input\n")
        source.joinpath("optimized.xyz").write_text(_XYZ)
        record.job_steps.append(ts_process.TsJobStep(purpose="frequency", state="done",
            input_path=str(input_path), actual_calculation=calculation))
    output = tmp_path / "output"
    output.mkdir()
    return record, output


def _render_stage(tmp_path, stage, *, engine="gaussian", checkpoint=None, **native):
    record, output = _prepare_stage(tmp_path, stage, engine=engine, **native)
    if checkpoint is not None:
        (output / "irc.chk").write_bytes(checkpoint)
    error, path = _STAGES[stage](record, str(output))
    assert not error, error
    return record, Path(path).read_text()


def _route(content, engine):
    marker = "#p" if engine == "gaussian" else "!"
    return next(line for line in content.splitlines() if line.startswith(marker))


@pytest.mark.parametrize("stage", _STAGES)
@pytest.mark.parametrize("engine", ["gaussian", "orca"])
def test_empty_native_declaration_uses_only_basic_stage_task(tmp_path, stage, engine):
    _, content = _render_stage(tmp_path, stage, engine=engine)
    assert inspect_input(content, engine=engine).tasks == {stage}
    route = _route(content, engine).lower()
    assert "calcfc" not in route and "noeigen" not in route


@pytest.mark.parametrize("stage", _STAGES)
@pytest.mark.parametrize("engine,keywords", [
    ("gaussian", 'SCF=Tight External="/CaseSensitive/Run_QM"'),
    ("orca", "TightSCF"),
])
def test_native_electronic_settings_do_not_add_an_implicit_stage_task(
    tmp_path, stage, engine, keywords,
):
    record, content = _render_stage(tmp_path, stage, engine=engine, keywords=keywords)
    if engine == "gaussian":
        expected = f"#p HF/STO-3G {keywords}"
    else:
        expected = f"! HF STO-3G {keywords}"
    assert _route(content, engine) == expected
    assert inspect_input(content, engine=engine).tasks == set()
    assert any(item["code"] == "native_task_uncertain" for item in record.warnings)


@pytest.mark.parametrize("engine,keywords", [
    ("gaussian", "IRCMax=(HF/3-21G*:HF/6-31G*)"),
    ("orca", "GOAT"),
])
def test_unclassified_native_task_does_not_gain_ts_optimization(tmp_path, engine, keywords):
    _, content = _render_stage(tmp_path, "ts_opt", engine=engine, keywords=keywords)
    prefix = "#p HF/STO-3G" if engine == "gaussian" else "! HF STO-3G"
    assert _route(content, engine) == f"{prefix} {keywords}"


@pytest.mark.parametrize("keywords", [
    'External="/CaseSensitive/Run_QM" SCF=Tight',
    'MaxPoints=40,StepSize=10 External="/CaseSensitive/Run_QM"',
    'Recalc=5 SCF=Tight',
])
def test_gaussian_irc_preserves_bare_options_and_case_sensitive_values(tmp_path, keywords):
    _, content = _render_stage(tmp_path, "irc", keywords=keywords)
    assert _route(content, "gaussian") == f"#p HF/STO-3G {keywords}"


@pytest.mark.parametrize("stage", _STAGES)
@pytest.mark.parametrize("engine,field,value", [
    ("orca", "orca_blocks", "%geom\n MaxIter 200\nend"),
    ("gaussian", "end_setting", "NativeTrailingSetting"),
])
def test_native_blocks_or_trailing_settings_do_not_add_stage_tasks(
    tmp_path, stage, engine, field, value,
):
    _, content = _render_stage(tmp_path, stage, engine=engine, **{field: value})
    assert value in content
    assert inspect_input(content, engine=engine).tasks == set()


@pytest.mark.parametrize("keywords", [
    'IRC=(CalcFC,MaxPoints=40,StepSize=10) External="/CaseSensitive/Run_QM"',
    'IRC=(ReadFC,Reverse) SCF=Tight',
])
def test_explicit_gaussian_irc_is_preserved_without_invented_hessian_options(tmp_path, keywords):
    _, content = _render_stage(tmp_path, "irc", keywords=keywords, checkpoint=b"pre-staged checkpoint")
    assert _route(content, "gaussian") == f"#p HF/STO-3G {keywords}"


@pytest.mark.parametrize("option", ["ReadFC", "RCFC", "ReadCartesianFC"])
def test_gaussian_irc_checkpoint_read_reports_missing_target_despite_neighbor(tmp_path, option):
    record, output = _prepare_stage(tmp_path, "irc", keywords=f"IRC=({option},Reverse)")
    neighbor = tmp_path / "source_frequency" / "frequency.chk"
    neighbor.write_bytes(b"unbound neighboring checkpoint is not a fallback")

    error, path = ts_process._write_irc_input(record, str(output))

    assert "missing" in error.lower() and "checkpoint" in error.lower()
    assert str(output / "irc.chk") in error
    assert not path and not (output / "irc.gjf").exists()
    assert not (output / "irc.chk").exists()
    assert neighbor.read_bytes() == b"unbound neighboring checkpoint is not a fallback"


@pytest.mark.parametrize("option", ["ReadFC", "RCFC", "ReadCartesianFC"])
def test_gaussian_irc_checkpoint_read_preserves_prestaged_target_bytes(tmp_path, option):
    checkpoint = b"pre-staged checkpoint; scientific evidence is checked separately\x00\xff"
    _, content = _render_stage(tmp_path, "irc", keywords=f"IRC={option}", checkpoint=checkpoint)

    assert (tmp_path / "output" / "irc.chk").read_bytes() == checkpoint
    assert _route(content, "gaussian") == f"#p HF/STO-3G IRC={option}"
    assert "CalcFC" not in content and "%oldchk" not in content


def test_gaussian_irc_explicit_calcfc_needs_no_prestaged_checkpoint(tmp_path):
    _, content = _render_stage(tmp_path, "irc", keywords="IRC=CalcFC")
    assert _route(content, "gaussian") == "#p HF/STO-3G IRC=CalcFC"
    assert not (tmp_path / "output" / "irc.chk").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("engine,keywords", [
    ("orca", "GOAT"),
    ("gaussian", "IRCMax=(HF/3-21G*:HF/6-31G*)"),
])
async def test_scan_preserves_unclassified_native_task_without_adding_opt(tmp_path, engine, keywords):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    target = tmp_path / ("scan.inp" if engine == "orca" else "scan.gjf")
    request = TsGuess_input_schema(mode="scan_prepare", engine=engine, method="HF", basis_set="STO-3G",
        keywords=keywords, input_text=_XYZ, charge=0,
        scans=[dict(atoms=[0, 1] if engine == "orca" else [1, 2], scan_end=1.56, scan_steps=6)],
        output_path=str(target))
    result = await TsGuess().tool_call(request, session=None)

    assert result.is_success, result.message
    content = target.read_text()
    prefix = "! HF STO-3G" if engine == "orca" else "#p HF/STO-3G"
    assert _route(content, engine) == f"{prefix} {keywords}"
    assert ("B 0 1 = 0.960000, 1.560000, 6" if engine == "orca" else "B 1 2 S 6 0.100000") in content


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["gaussian", "orca"])
async def test_scan_without_native_text_keeps_its_basic_default_task(tmp_path, engine):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    target = tmp_path / ("scan.inp" if engine == "orca" else "scan.gjf")
    request = TsGuess_input_schema(mode="scan_prepare", engine=engine, method="HF", basis_set="STO-3G",
        input_text=_XYZ, charge=0,
        scans=[dict(atoms=[0, 1] if engine == "orca" else [1, 2], scan_end=1.56, scan_steps=6)],
        output_path=str(target))
    result = await TsGuess().tool_call(request, session=None)

    assert result.is_success, result.message
    content = target.read_text()
    expected = "! Opt HF STO-3G" if engine == "orca" else "#p opt=modredundant HF/STO-3G"
    assert _route(content, engine) == expected


@pytest.mark.asyncio
async def test_scan_keeps_native_resources_when_structured_resources_are_omitted(tmp_path):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    target = tmp_path / "scan.inp"
    request = TsGuess_input_schema(mode="scan_prepare", engine="orca", method="HF", basis_set="STO-3G",
        orca_blocks="%pal nprocs 2 end\n%maxcore 1234", input_text=_XYZ, charge=0,
        scans=[dict(atoms=[0, 1], scan_end=1.56, scan_steps=6)], output_path=str(target))
    assert not {"nproc", "mem"} & request.model_fields_set

    result = await TsGuess().tool_call(request, session=None)

    assert result.is_success, result.message
    resources = [line for line in target.read_text().splitlines() if line.startswith(("%pal", "%maxcore"))]
    assert resources == ["%pal nprocs 2 end", "%maxcore 1234"]
