"""Native scan path regressions; fixtures never run quantum calculations."""
import json
from pathlib import Path

import pytest

from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
from cloudra.tools.core.qm_calculation import QmCalculation
from cloudra.tools.core.ts_inputs import ScanGuess, TsInput, TsInputChanges, apply_input_changes

WATER = "3\nwater\nO 0 0 0\nH 0 0 1\nH 1 0 0\n"
ORCA = dict(engine="orca", method="B3LYP", basis_set="def2-SVP", keywords="D3BJ")
ROWS = [dict(atoms=[0, 1], scan_start=1., scan_end=2., scan_steps=3),
        dict(atoms=[0, 2], scan_start=1., scan_end=2., scan_steps=3)]


def _inputs(engine="xtb", reference=False, **scan_fields):
    calculation = ORCA if engine == "orca" else dict(engine="xtb", method="GFN2-xTB", basis_set="")
    guess = dict(kind="scan", calculation={"ref": "scan"} if reference else calculation,
                 scans=ROWS, mode="concerted", **scan_fields)
    if engine == "xtb":
        guess.setdefault("force_constant", .5)
    return TsInput.model_validate(dict(
        reaction=dict(reactant_smiles="O", product_smiles="O", charge=0, multiplicity=1),
        calculations={"scan": calculation} if reference else {}, guess=guess))


def _orca_files(tmp_path, energies, concerted=False, grid=False):
    job = tmp_path / "scan"
    scan_lines = ["Scan", "  B 0 1 = 1, 3, 3"]
    if concerted or grid:
        scan_lines.append("  B 0 2 = 1, 3, 3")
    scan_lines.append("end")
    if concerted:
        scan_lines.append("Simul_Scan true")
    native = "! OPT B3LYP def2-SVP D3BJ\n%geom\n" + "\n".join(scan_lines) + "\nend\n"
    Path(str(job) + ".inp").write_text(native)
    log = Path(str(job) + ".out")
    log.write_text("* O   R   C   A *\nNAME = " + str(job) + ".inp\n" + native + "ORCA TERMINATED NORMALLY\n")
    rows = []
    for i, energy in enumerate(energies, 1):
        columns = f"{i} {i + .5} {energy}" if concerted or grid else f"{i} {energy}"
        rows.append(columns)
        Path(f"{job}.{i:03d}.xyz").write_text(f"3\npoint {i}\nO 0 0 0\nH {i} 0 0\nH 0 {i + .5} 0\n")
    Path(str(job) + ".relaxscanact.dat").write_text("\n".join(rows) + "\n")
    return log, job


def test_orca_concerted_schema_renderer_and_native_admission(tmp_path):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    inputs = _inputs("orca")
    assert inputs.guess.mode == "concerted"
    output = tmp_path / "coupled.inp"
    result = TsGuess()._scan_prepare(TsGuess_input_schema(
        charge=0, mode="scan_prepare", input_text=WATER, output_path=str(output),
        scans=ROWS, scan_mode="concerted", **ORCA))
    assert result.is_success
    text = output.read_text()
    assert "Scan\n        B 0 1 = 1.000000, 2.000000, 3\n" in text
    assert "B 0 2 = 1.000000, 2.000000, 3\n    end" in text
    assert "Simul_Scan true" in text
    assert compare_calculation_input(text, ORCA, charge=0, multiplicity=1) == []


@pytest.mark.parametrize('extra', ['MaxIter 200', 'Calc_Hess true', 'Recalc_Hess 5', 'true'])
def test_concerted_scan_does_not_admit_undeclared_native_controls(extra):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    native = ('! B3LYP def2-SVP D3BJ\n%geom\n Scan\n B 0 1 = 1, 2, 3\n end\n'
              f' Simul_Scan true\n {extra}\nend\n* xyz 0 1\nO 0 0 0\nH 0 0 1\nH 1 0 0\n*\n')
    differences = compare_calculation_input(native, ORCA, charge=0, multiplicity=1)
    assert any(item.field == 'orca_blocks' for item in differences)


def test_process_forwards_concerted_intent_to_real_renderer(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_process import TsProcessRecord, _check_calculation_submission, _guess_scan

    source = tmp_path / "water.xyz"
    source.write_text(WATER)
    record = TsProcessRecord(run_id="scan", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
                             owner_conversation_id="project", owner_session_id="owner", input=_inputs("orca"))
    monkeypatch.setattr("cloudra.tools.core.ts_process._read_built_xyz",
                        lambda *_: (["O", "H", "H"], [[0., 0., 0.], [0., 0., 1.], [1., 0., 0.]], str(source), ""))
    monkeypatch.setattr("cloudra.services.ts_pipeline_context.require_pipeline_authority", lambda *_: None)
    captured = []

    def submit(record, purpose, path, engine):
        _check_calculation_submission(record, purpose, path, engine)
        captured.append(Path(path).read_text())
        return "", 101

    monkeypatch.setattr("cloudra.tools.core.ts_process._submit_step", submit)
    _guess_scan(record)
    assert record.blocked is None
    assert record.waiting_for == "job:101"
    assert "Simul_Scan true" in captured[0]


@pytest.mark.parametrize("reference", [False, True])
def test_engine_switch_removes_only_inherited_force_constant(reference):
    current = _inputs(reference=reference)
    patch = {"calculations": {"scan": {"replace": ORCA}}} if reference else {"guess": {"calculation": {"replace": ORCA}}}
    updated = apply_input_changes(current, TsInputChanges.model_validate(patch))
    assert updated.guess.force_constant is None
    assert updated.guess.mode == "concerted"
    assert [row.atoms for row in updated.guess.scans] == [[0, 1], [0, 2]]
    assert current.guess.force_constant == .5


def test_engine_switch_does_not_drop_explicit_force_constant_or_solvent():
    current = _inputs(solvation={"model": "alpb", "solvent": "water"})
    with pytest.raises(ValueError, match="solvation"):
        apply_input_changes(current, TsInputChanges.model_validate({"guess": {"calculation": {"replace": ORCA}}}))
    current = _inputs()
    with pytest.raises(ValueError, match="force_constant"):
        apply_input_changes(current, TsInputChanges.model_validate({"guess": {"calculation": {"replace": ORCA}, "force_constant": .5}}))


def test_concerted_sidecar_reads_energy_after_both_coordinates(tmp_path):
    log, job = _orca_files(tmp_path, [-10., -9., -11.], concerted=True)
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    assert parsed.scan_has_internal_peak is True
    assert parsed.candidate["scan_index"] == 1
    assert parsed.candidate["energy"] == -9.
    assert float(Path(parsed.ts_candidate_path).read_text().splitlines()[3].split()[1]) == 2.
    assert str(job) in parsed.candidate["geometry_ref"]


def test_boundary_maximum_does_not_hide_unique_internal_candidate(tmp_path):
    log, _ = _orca_files(tmp_path, [-10., -12., -11., -13.])
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    assert parsed.scan_has_internal_peak is True
    assert parsed.candidate["scan_index"] == 2
    assert parsed.candidate["energy"] == -11.
    assert float(Path(parsed.ts_candidate_path).read_text().splitlines()[3].split()[1]) == 3.
    assert parsed.barrier_kcal is None


def test_multiple_local_candidates_keep_native_paths_for_provided_choice(tmp_path):
    log, job = _orca_files(tmp_path, [-10., -12., -11., -13., -12., -14.])
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    assert parsed.scan_has_internal_peak is True
    assert parsed.candidate is None and parsed.ts_candidate_path == ""
    details = "\n".join(parsed.verdicts)
    for point, energy in [(3, -11.), (5, -12.)]:
        assert f"point {point}" in details.lower()
        assert f"{energy:.12f}" in details
        assert f"{job}.{point:03d}.xyz" in details
    assert "provided" in parsed.message
    assert parsed.barrier_kcal is None


def test_orca_independent_grid_is_not_flattened_into_a_path(tmp_path):
    log, _ = _orca_files(tmp_path, [-10., -9., -11.], grid=True)
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    assert parsed.candidate is None and not parsed.ts_candidate_path
    assert parsed.scan_has_internal_peak is None
    assert "grid" in parsed.message.lower()


def test_gaussian_grid_is_not_flattened_into_a_path(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import cclib

    log = tmp_path / "scan.log"
    log.write_text("Gaussian\nSummary of Optimized Potential Surface Scan\n 1 2 3\n Eigenvalues -- -10.000000 -9.000000 -11.000000\n")
    monkeypatch.setattr(cclib.io, "ccread", lambda *_: SimpleNamespace(
        scanparm=[[1., 1., 2.], [1., 2., 1.]], scancoords=[[[0., 0., 0.], [i, 0., 0.]] for i in (1., 2., 3.)], atomnos=[1, 1]))
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="gaussian", log_path=str(log)))
    assert parsed.scan_has_internal_peak is None
    assert parsed.candidate is None and "grid" in parsed.message.lower()


@pytest.mark.parametrize('energies,expected', [([-10., -12., -11., -13., -12., -14.], [3, 5]),
                                               ([-10., -12., -11., -13.], [3])])
def test_xtb_native_candidates_include_lower_local_peaks(tmp_path, monkeypatch, energies, expected):
    from cloudra.runtime.chem_task import ChemTask
    from cloudra.tools.core.xtb_scan_runner import parse_xtb_scan

    task = ChemTask(task="xtb_scan", cpus=1, reactant_xyz="2\nH2\nH 0 0 0\nH 1 0 0\n", scan={
        "kind": "scan", "calculation": {"engine": "xtb", "method": "GFN2-xTB", "basis_set": ""}, "force_constant": .5,
        "scans": [{"atoms": [0, 1], "scan_start": 1., "scan_end": float(len(energies)), "scan_steps": len(energies)}]})
    (tmp_path / "input.xyz").write_text(task.reactant_xyz)
    (tmp_path / "scan.inp").write_text("$scan\nend\n")
    native = "RELAXED SCAN\n"
    trajectory = ""
    for i, energy in enumerate(energies, 1):
        native += "GEOMETRY OPTIMIZATION CONVERGED\nFinal Singlepoint\n" + f":: total energy {energy} Eh ::\n:: add. restraining 0.0 Eh ::\nconvergence criteria satisfied\nA N C O P T\n"
        trajectory += f"2\n energy: {energy} xtb: 6.7.1\nH 0 0 0\nH {i} 0 0\n"
    (tmp_path / "engine.out").write_text(native + "normal termination of xtb\n")
    (tmp_path / "xtbscan.log").write_text(trajectory)
    result = parse_xtb_scan(task, tmp_path, 0)
    assert result["scan_status"] == "complete"
    assert [candidate["point_index"] for candidate in result["candidates"]] == expected
    assert result["usable_as_guess"] is (len(expected) == 1)
    assert all(Path(candidate["frame_path"]).is_file() for candidate in result["candidates"])
    manifest = tmp_path / 'scan-task.json'
    manifest.write_text(task.model_dump_json())
    monkeypatch.setattr('cloudra.runtime.chem_task.read_task_result', lambda *_: ({'result': result}, True))
    parsed = TsGuess()._xtb_scan_parse(TsGuess_input_schema(mode='scan_parse', engine='xtb', log_path=str(manifest)))
    assert parsed.barrier_kcal is None
    assert str(tmp_path / 'engine.out') in parsed.message
    if len(expected) > 1:
        details = '\n'.join(parsed.verdicts)
        for point in expected:
            assert str(tmp_path / f'point_{point:04d}.xyz') in details
            assert f'{energies[point - 1]:.12f}' in details


@pytest.mark.parametrize("recorded_manifest", [False, True])
def test_missing_xtb_result_never_calls_manifest_a_native_log(tmp_path, recorded_manifest):
    from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord, _refinement_log_path

    manifest = tmp_path / "scan-task.json"
    from cloudra.runtime.chem_task import ChemTask

    manifest.write_text(ChemTask(task="xtb_scan", cpus=1, reactant_xyz=WATER, scan=_inputs().guess).model_dump_json())
    record = TsProcessRecord(run_id="scan", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
                             owner_conversation_id="project", owner_session_id="owner", input=_inputs())
    step = TsJobStep(purpose="scan", job_id=9, input_path=str(manifest), state="failed",
                     actual_calculation=QmCalculation(engine="xtb", method="GFN2-xTB", basis_set=""))
    if recorded_manifest:
        (tmp_path / "state_9.json").write_text(json.dumps({"log_file": str(manifest)}))
    captured = tmp_path / ".cloudra/calc-9.out.log"
    captured.parent.mkdir()
    captured.write_text("Native task failed before result persistence")
    assert _refinement_log_path(record, step) == str(captured)


@pytest.mark.parametrize("energies,multiple", [([-10., -12., -11., -13.], False),
                                              ([-10., -12., -11., -13., -12., -14.], True)])
def test_scan_pipeline_unique_continues_multiple_uses_existing_provided(tmp_path, monkeypatch, energies, multiple):
    from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord, _guess, _guess_scan

    log, job = _orca_files(tmp_path, energies)
    inputs = _inputs()
    inputs.guess = ScanGuess(kind="scan", calculation=ORCA, scans=[ROWS[0]])
    record = TsProcessRecord(run_id="scan", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
                             owner_conversation_id="project", owner_session_id="owner", input=inputs,
                             scan_step=TsJobStep(purpose="scan", job_id=101, state="done",
                                 input_path=str(job) + ".inp", actual_calculation=QmCalculation(**ORCA)))
    monkeypatch.setattr("cloudra.tools.core.ts_process._step_state", lambda *_: "done")
    monkeypatch.setattr("cloudra.tools.core.ts_process._read_built_xyz",
                        lambda *_: (["O", "H", "H"], [[0., 0., 0.], [0., 0., 1.], [1., 0., 0.]], str(job) + ".001.xyz", ""))
    from tests.test_ts_workflow_scan import own_water
    own_water(record)
    _guess_scan(record)
    if not multiple:
        assert record.blocked is None
        assert record.structures.candidate.GetConformer().GetAtomPosition(1).x == 3.
    else:
        assert record.blocked is not None
        assert record.blocked.failure_class == "scan_choice_required"
        assert str(log) in record.blocked.message
        assert str(job) + ".003.xyz" in "\n".join(record.blocked.atom_details)
        selected = str(job) + ".005.xyz"
        record.input = apply_input_changes(record.input, TsInputChanges.model_validate({"guess": {
            "kind": "provided", "xyz_path": selected, "evidence_refs": [selected, str(log)]}}))
        record.blocked = None
        _guess(record)
        assert record.blocked is None and record.path_kind == "provided"
        from cloudra.tools.core.structure_artifacts import read_xyz_atoms
        assert record.structures.candidate.GetConformer().GetPositions().tolist() == [point for _, point in read_xyz_atoms(selected)]


@pytest.mark.parametrize("energies,peak", [([-10., -12., -11., -13.], 3),
                                         ([-10., -12., -11., -13., -12., -14.], None)])
def test_readonly_scan_summary_uses_same_local_candidates(tmp_path, energies, peak):
    from cloudra.tools.Chemtool.log_parser import LogParser

    log, job = _orca_files(tmp_path, energies)
    summary = LogParser._scan_summary(str(log), "orca", log.read_text())
    assert summary["scan_has_internal_peak"] is True
    if peak is not None:
        assert summary["scan_peak"].point_number == peak
        assert summary["scan_peak"].geometry_ref == f"{job}.{peak:03d}.xyz"
    else:
        assert summary["scan_peak"] is None
        for point in (3, 5):
            assert f"{job}.{point:03d}.xyz" in summary["message"]


def test_readonly_grid_summary_does_not_offer_a_path_peak(tmp_path):
    from cloudra.tools.Chemtool.log_parser import LogParser

    log, _ = _orca_files(tmp_path, [-10., -9., -11.], grid=True)
    summary = LogParser._scan_summary(str(log), "orca", log.read_text())
    assert summary["scan_has_internal_peak"] is None and summary["scan_peak"] is None
    assert "grid" in summary["message"].lower()


def test_local_candidate_messages_do_not_claim_zero_barrier(tmp_path):
    from cloudra.tools.Chemtool.log_parser import LogParser

    log, _ = _orca_files(tmp_path, [-10., -12., -11., -13.])
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    assert "barrier (highest" not in parsed.message.lower()
    assert "0.00 kcal/mol" not in parsed.message
    assert "energy-maximum frame" not in "\n".join(parsed.verdicts)
    summary = LogParser._scan_summary(str(log), "orca", log.read_text())
    assert f"{summary['scan_peak'].relative_to_first_point_kcal:.4f}" in summary["message"]


def test_readonly_gaussian_grid_summary_does_not_offer_a_path_peak(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import cclib

    from cloudra.tools.Chemtool.log_parser import LogParser

    log = tmp_path / "scan.log"
    log.write_text("Gaussian\nSummary of Optimized Potential Surface Scan\n Eigenvalues -- -10.000000 -9.000000 -11.000000\n")
    monkeypatch.setattr(cclib.io, "ccread", lambda *_: SimpleNamespace(scanparm=[[1., 1., 2.], [1., 2., 1.]]))
    summary = LogParser._scan_summary(str(log), "gaussian", log.read_text())
    assert summary["scan_has_internal_peak"] is None and summary["scan_peak"] is None
    assert "grid" in summary["message"].lower()


def test_multiple_peaks_do_not_offer_a_frame_with_wrong_atom_order(tmp_path):
    log, job = _orca_files(tmp_path, [-10., -12., -11., -13., -12., -14.])
    wrong = Path(f"{job}.005.xyz")
    wrong.write_text(wrong.read_text().replace("O 0 0 0", "N 0 0 0"))
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    assert parsed.candidate_unavailable is True
    assert not parsed.ts_candidate_path
    assert str(wrong) not in "\n".join(parsed.verdicts)


def test_single_orca_scan_block_grid_is_not_flattened_without_sidecar(tmp_path):
    from cloudra.tools.Chemtool.log_parser import LogParser

    log, job = _orca_files(tmp_path, [-10., -9., -11.], grid=True)
    native = "! OPT B3LYP def2-SVP\n%geom\n Scan\n B 0 1 = 1,3,3\n B 0 2 = 1,3,3\n end\nend\n"
    Path(str(job) + ".inp").write_text(native)
    text = "* O   R   C   A *\nNAME = " + str(job) + ".inp\n" + native
    for point, energy in enumerate((-10., -9., -11.), 1):
        text += f"RELAXED SURFACE SCAN STEP {point}\nCARTESIAN COORDINATES (ANGSTROEM)\n---\nO 0 0 0\nH {point} 0 0\nH 0 1 0\n\nFINAL SINGLE POINT ENERGY {energy}\n"
    log.write_text(text)
    Path(str(job) + ".relaxscanact.dat").unlink()
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    assert parsed.scan_has_internal_peak is None and not parsed.ts_candidate_path
    summary = LogParser._scan_summary(str(log), "orca", text)
    assert summary["scan_has_internal_peak"] is None and summary["scan_peak"] is None


def test_gaussian_modredundant_grid_remains_a_grid_without_cclib(tmp_path, monkeypatch):
    import cclib

    from cloudra.tools.Chemtool.log_parser import LogParser

    text = "Gaussian\nB 1 2 S 2 0.1\nB 1 3 S 2 0.1\nSummary of Optimized Potential Surface Scan\n Eigenvalues -- -10.000000 -9.000000 -11.000000\n"
    log = tmp_path / "scan.log"
    log.write_text(text)
    monkeypatch.setattr(cclib.io, "ccread", lambda *_: None)
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="gaussian", log_path=str(log)))
    assert parsed.scan_has_internal_peak is None and not parsed.ts_candidate_path
    summary = LogParser._scan_summary(str(log), "gaussian", text)
    assert summary["scan_has_internal_peak"] is None and summary["scan_peak"] is None


def test_multi_candidate_profile_never_marks_boundary_as_internal(tmp_path):
    log, _ = _orca_files(tmp_path, [-10., -12., -11., -13., -12., -14.])
    parsed = TsGuess()._scan_parse(TsGuess_input_schema(mode="scan_parse", engine="orca", log_path=str(log)))
    rows = parsed.profile_table.splitlines()[1:]
    assert "peak" not in rows[0]
    assert all("candidate" in rows[index] for index in (2, 4))
