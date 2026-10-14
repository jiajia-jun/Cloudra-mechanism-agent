"""Structured ORCA scans retain surface/path intent; no QM binaries are run."""
import pytest

from cloudra.tools.Chemtool.log_parser import LogParser
from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
from cloudra.tools.core.calculation_intent import compare_calculation_input
from cloudra.tools.core.qm_calculation import QmCalculation
from cloudra.tools.core.ts_inputs import ScanGuess, TsInput
from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord, _guess_scan

WATER = "3\nwater\nO 0 0 0\nH 0 0 1\nH 1 0 0\n"
ORCA = dict(engine="orca", method="B3LYP", basis_set="def2-SVP", keywords="D3BJ")
ROWS = [dict(atoms=[0, 1], scan_start=1., scan_end=2., scan_steps=3),
        dict(atoms=[0, 2], scan_start=1., scan_end=3., scan_steps=4)]


def test_explicit_orca_grid_renders_one_nested_scan_with_independent_steps(tmp_path):
    output = tmp_path / "grid.inp"
    result = TsGuess()._scan_prepare(TsGuess_input_schema(
        mode="scan_prepare", input_text=WATER, output_path=str(output),
        scans=ROWS, scan_mode="grid", **ORCA))
    assert result.is_success
    native = output.read_text()
    assert "%geom\n    Scan\n        B 0 1 = 1.000000, 2.000000, 3\n        B 0 2 = 1.000000, 3.000000, 4\n    end\nend" in native
    assert "Simul_Scan" not in native
    assert compare_calculation_input(native, ORCA, charge=0, multiplicity=1) == []


@pytest.mark.parametrize("concerted", [False, True])
def test_nested_scan_retains_single_coordinate_or_concerted_path(tmp_path, concerted):
    scans = [ROWS[0], dict(ROWS[1], scan_steps=3)] if concerted else ROWS[:1]
    output = tmp_path / "path.inp"
    result = TsGuess()._scan_prepare(TsGuess_input_schema(
        mode="scan_prepare", input_text=WATER, output_path=str(output),
        scans=scans, scan_mode="concerted" if concerted else None,
        freeze=[dict(coord_type="bond", atoms=[1, 2])], nprocs=8, memory_mb=768, **ORCA))
    assert result.is_success
    native = output.read_text()
    assert native.count("    Scan\n") == 1
    assert "        B 0 1 = 1.000000, 2.000000, 3\n" in native
    assert ("Simul_Scan true" in native) is concerted
    assert "{ B 1 2 C }" in native
    assert "%pal nprocs 8 end" in native and "%maxcore 256" in native
    assert "* xyz 0 1\nO" in native


@pytest.mark.parametrize("mode,rows", [(None, ROWS), ("sequential", ROWS), ("concerted", ROWS)])
def test_orca_two_coordinate_intent_stays_explicit_and_concerted_steps_equal(mode, rows):
    with pytest.raises(ValueError):
        ScanGuess(kind="scan", calculation=ORCA, scans=rows, mode=mode)


def test_xtb_does_not_acquire_grid_semantics():
    with pytest.raises(ValueError):
        ScanGuess(kind="scan", calculation=dict(engine="xtb", method="GFN2-xTB", basis_set=""),
                  scans=ROWS, mode="grid", force_constant=.5)


def test_grid_completion_preserves_surface_without_automatic_ts_guess(tmp_path, monkeypatch):
    native_input = tmp_path / "grid.inp"
    native_input.write_text("! OPT B3LYP def2-SVP D3BJ\n%geom\n  Scan\n    B 0 1 = 1, 2, 2\n    B 0 2 = 1, 2, 2\n  end\nend\n")
    log = tmp_path / "grid.out"
    log.write_text("* O   R   C   A *\nNAME = " + str(native_input) + "\nORCA TERMINATED NORMALLY\n")
    surface = tmp_path / "grid.relaxscanact.dat"
    surface.write_text("1 1 -10\n1 2 -9\n2 1 -11\n2 2 -12\n")
    for point in range(1, 5):
        (tmp_path / f"grid.{point:03d}.xyz").write_text(WATER)
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    assert parsed.candidate is None and not parsed.ts_candidate_path
    assert parsed.barrier_kcal is None and parsed.scan_has_internal_peak is None
    summary = LogParser._scan_summary(str(log), "orca", log.read_text())
    assert summary["scan_peak"] is None and summary["scan_has_internal_peak"] is None
    inputs = TsInput.model_validate(dict(
        reaction=dict(reactant_smiles="O", product_smiles="O", charge=0, multiplicity=1),
        guess=dict(kind="scan", calculation=ORCA, scans=ROWS, mode="grid")))
    record = TsProcessRecord(run_id="grid", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        owner_conversation_id="project", owner_session_id="owner", input=inputs,
        scan_step=TsJobStep(purpose="scan", job_id=1, state="done",
            input_path=str(native_input), actual_calculation=QmCalculation(**ORCA)))
    monkeypatch.setattr("cloudra.tools.core.ts_process._step_state", lambda *_: "done")
    monkeypatch.setattr("cloudra.tools.core.ts_process._refinement_log_path", lambda *_: str(log))
    _guess_scan(record)
    assert record.blocked and record.blocked.failure_class == "scan_no_candidate"
    assert not record.current_ts_guess_path
    assert not any(step.purpose == "ts_opt" for step in record.job_steps)
    assert surface.read_text() == "1 1 -10\n1 2 -9\n2 1 -11\n2 2 -12\n"
    assert all((tmp_path / f"grid.{point:03d}.xyz").exists() for point in range(1, 5))


@pytest.mark.asyncio
@pytest.mark.parametrize("tasks,blocks", [
    ([{"scan": None}], None),
    ([{"scan": None}], "%geom\n  Scan B 0 1 = 1, 2, 3 end\nend"),
    ([{"opt": None}], "%geom\n  Scan\n    B 0 1 = 1, 2, 3\n  end\nend"),
])
async def test_writer_retires_orca_scan_and_raw_opt_bypass(tmp_path, tasks, blocks):
    source = tmp_path / "water.xyz"
    source.write_text(WATER)
    output = tmp_path / "retired.inp"
    result = await QmInputWriter().tool_call(QmInputWriter_input_schema(
        source_type="xyz_file", source_value=str(source), output_path=str(output),
        task_type=tasks, orca_blocks=blocks, **ORCA), session=None)
    assert not result.is_success and not output.exists()
    assert "ts_guess" in result.message and "scan_prepare" in result.message


@pytest.mark.asyncio
async def test_writer_keeps_ordinary_geom_settings_and_ignores_scan_comment(tmp_path):
    source = tmp_path / "water.xyz"
    source.write_text(WATER)
    output = tmp_path / "minimum.inp"
    result = await QmInputWriter().tool_call(QmInputWriter_input_schema(
        source_type="xyz_file", source_value=str(source), output_path=str(output),
        orca_blocks="%geom\n  MaxIter 200\n  # Scan is handled by a different operation\nend", **ORCA), session=None)
    assert result.is_success, result.message
    assert "MaxIter 200" in output.read_text()
    assert result.interpreted_intent["tasks"] == ["minimum_opt"]


@pytest.mark.parametrize("cpus,memory_mb,maxcore", [(4, None, 1024), (8, 8192, 1024), (3, 8192, 2730)])
def test_standalone_scan_total_budget_uses_existing_writer_allocation(tmp_path, cpus, memory_mb, maxcore):
    output = tmp_path / "budget.inp"
    result = TsGuess()._scan_prepare(TsGuess_input_schema(
        mode="scan_prepare", input_text=WATER, output_path=str(output),
        scans=ROWS[:1], nprocs=cpus, memory_mb=memory_mb, **ORCA))
    assert result.is_success
    assert f"%pal nprocs {cpus} end" in output.read_text()
    assert f"%maxcore {maxcore}\n" in output.read_text()


@pytest.mark.parametrize("surface", ["wire", "model"])
def test_scan_budget_and_grid_intent_are_exposed_only_in_prepare_mode(surface):
    from jsonschema import Draft202012Validator, ValidationError

    schema = (TsGuess_input_schema.to_parameters_schema() if surface == "wire"
              else TsGuess_input_schema.model_json_schema())
    validator = Draft202012Validator(schema)
    validator.validate(dict(mode="scan_prepare", engine="orca", method="B3LYP", basis_set="def2-SVP",
        input_text=WATER, output_path="grid.inp", scans=ROWS, scan_mode="grid", memory_mb=8192))
    with pytest.raises(ValidationError):
        validator.validate(dict(mode="scan_parse", log_path="grid.out", memory_mb=8192))


@pytest.mark.parametrize("blocks", ["%pal nprocs 16 end", "%maxcore 8192"])
def test_scan_raw_blocks_cannot_override_declared_resources(tmp_path, blocks):
    output = tmp_path / "duplicate-budget.inp"
    request = TsGuess_input_schema(mode="scan_prepare", input_text=WATER, output_path=str(output),
        scans=ROWS[:1], nprocs=4, memory_mb=4096, orca_blocks=blocks, **ORCA)
    with pytest.raises(ValueError, match="nprocs|memory_mb"):
        TsGuess()._scan_prepare(request)
    assert not output.exists()


@pytest.mark.parametrize("blocks", [
    "# %pal nprocs 16 end\n# %maxcore 8192\n# %geom is program-generated",
    '%method\n  ProgExt "/usr/bin/true"\n  Ext_Params "--note %pal %maxcore %geom --model /abs/model"\nend',
])
def test_scan_resource_words_in_comments_or_strings_are_not_directives(tmp_path, blocks):
    output = tmp_path / "unchanged-budget.inp"
    result = TsGuess()._scan_prepare(TsGuess_input_schema(
        mode="scan_prepare", input_text=WATER, output_path=str(output), scans=ROWS[:1],
        nprocs=4, memory_mb=4096, orca_blocks=blocks, **dict(ORCA, method="ExtOpt", basis_set="")))
    assert result.is_success
    native = output.read_text()
    assert [line for line in native.splitlines() if line.startswith(("%pal", "%maxcore"))] == [
        "%pal nprocs 4 end", "%maxcore 1024"]
