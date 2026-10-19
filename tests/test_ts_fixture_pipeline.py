"""Offline replay of repository artifacts through the durable TS pipeline.

Only compute admission is substituted; parsers, writers, stage bindings, event
handling and reloads remain real. benchmark_synthetic fixtures are CONTRACT DATA,
not actual transition states. No engine or scheduler is started by these tests.
"""

import hashlib
import shutil
from pathlib import Path

import pytest

pytest.importorskip("cclib")

from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_admission import AdmissionOutcome
from cloudra.services.ts_pipeline_context import use_pipeline_database
from cloudra.services.ts_pipeline_store import create_process
from cloudra.tools.core import ts_process as process
from cloudra.tools.core.ts_pipeline_driver import advance_process, handle_process_job_terminal
from tests.ts_fixtures import calculation_input

pytestmark = pytest.mark.usefixtures("ts_producer_authority")

FIXTURES = Path(__file__).parent / "fixtures"
CO2_XYZ = "3\nfixture CO2 final frame\nO 0 0 -1.252682\nC 0 0 0\nO 0 0 1.252682\n"
WATER_XYZ = "3\nfixture water final frame\nO 0 0 0.127131\nH 0 0.758039 -0.508525\nH 0 -0.758039 -0.508525\n"
HCN_SCAN_XYZ = "3\nExtOpt scan atom order\nC 0 0 0\nH 1.09 0 0\nN 0 1.5 0\n"


@pytest.fixture
def admission(monkeypatch):
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )


def waiting_fixture_stage(tmp_path, *, purpose="frequency", engine="orca", seed=CO2_XYZ,
                          project_id="project", owner_id="owner", smiles="O=C=O", limits=None):
    """Prepare one real immutable binding as a calculator's queued input boundary."""
    db = ComputeDB().init()
    declaration = calculation_input(
        reactant_smiles=smiles, product_smiles=smiles, engine=engine,
        method="b3lyp/def2svp",
    )
    if limits is not None:
        from cloudra.tools.core.ts_inputs import TsExecutionLimits
        declaration.execution.limits = TsExecutionLimits.model_validate(limits)
    if purpose == "scan":
        from cloudra.tools.core.ts_inputs import ScanGuess
        declaration.guess = ScanGuess(kind="scan",calculation={"engine":engine,"method":"b3lyp","basis_set":"def2svp","keywords":""},
            scans=[dict(atoms=[0, 1], scan_start=1.0, scan_end=2.0, scan_steps=5)],
            freeze=[dict(coord_type="bond", atoms=[0, 2])],
        )
    state = create_process(db, request_key="fixture", payload=dict(
        project_id=project_id, owner_id=owner_id, workspace_dir=str(tmp_path),
        input=declaration.model_dump(mode="json"),
    ))
    if limits is not None:
        from cloudra.services.exploration_budget_store import ExplorationBudget, configure_budget
        configure_budget(db, process_id=state['process_id'], project_id=project_id,
            owner_id=owner_id, budget=ExplorationBudget(
                source=declaration.execution.limits.source,
                max_compute_actions=declaration.execution.limits.max_compute_actions,
                max_model_calls=declaration.execution.limits.max_model_calls))
    record = process.TsProcessRecord(
        run_id="ts_0001", pipeline_id=state["process_id"], workspace_dir=str(tmp_path),
        run_dir=str(tmp_path / "ts" / "ts_0001"), input=declaration,
        owner_conversation_id=project_id, owner_session_id=owner_id,
        stage="guess" if purpose == "scan" else "refine",
    )
    folder = Path(record.run_dir) / "jobs" / "initial"
    folder.mkdir(parents=True)
    geometry = folder / "optimized.xyz"
    geometry.write_text(seed)
    from cloudra.tools.core.molecule import read_molecule
    from cloudra.tools.core.reaction_state import ReactionStructures
    molecule = read_molecule(input_path=str(geometry), input_format='xyz')
    record.structures = ReactionStructures(reactant=molecule, product=molecule,
        candidate=None if purpose == 'scan' else molecule,
        product_to_reactant=tuple(range(molecule.GetNumAtoms())))
    source = folder / (purpose + (".inp" if engine == "orca" else ".gjf"))
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    if purpose == "scan":
        TsGuess()._scan_prepare(TsGuess_input_schema(
            mode="scan_prepare", input_path=str(geometry), output_path=str(source),
            charge=declaration.reaction.charge, multiplicity=declaration.reaction.multiplicity,
            electronic_character=declaration.reaction.electronic_character,
            **declaration.guess.calculation.model_dump(mode='json'),
            scans=[dict(atoms=[0, 1], scan_start=1.0, scan_end=2.0, scan_steps=5)],
            freeze=[dict(coord_type="bond", atoms=[0, 2])],
        ))
    else:
        task = {"irc": None} if purpose == "irc" else {"opt": None} if purpose.endswith("_opt") else {"freq": None}
        request = QmInputWriter_input_schema(
            engine=engine, method="b3lyp", basis_set="def2svp", task_type=[task],
            source_type="xyz_file", source_value=str(geometry), output_path=str(source),
        )
        from cloudra.tools.core.molecule import read_molecule
        mol = read_molecule(str(geometry))
        source.write_text(QmInputWriter._build_orca_input(request, mol) if engine == "orca"
                          else QmInputWriter._build_gjf(request, mol))
    with use_pipeline_database(db):
        error, job = process._submit_step(record, purpose, str(source), engine)
    assert error == ""
    step = process.TsJobStep(purpose=purpose, job_id=job, input_path=str(source), state="ready", actual_calculation=process.stage_calculation(record,purpose),source_input_revision=record.declaration_revision)
    if purpose in {"reactant_opt", "product_opt"}:
        # This replay starts at the queued Opt boundary. Preserve its real seed
        # exactly as the endpoint writer does, without claiming an IRC origin.
        role = purpose.partition("_")[0]
        endpoint_source = folder / f"{role}_source.xyz"
        process._write_immutable_input(str(endpoint_source), geometry.read_text())
        origin = process.EndpointSource(
            kind="species_reference", label=role, source_path=str(endpoint_source),
            sha256=hashlib.sha256(endpoint_source.read_bytes()).hexdigest(),
        )
        provenance = folder / "endpoint_source.json"
        process._write_immutable_input(str(provenance), origin.model_dump_json())
        step.endpoint_source = process.EndpointSource.model_validate_json(provenance.read_text())
    if purpose == "scan":
        record.scan_step = step
    else:
        record.job_steps = [step]
    record.waiting_for = f"job:{job}"
    with use_pipeline_database(db):
        process.save_record(record)
    return db, record, step


def install_log(record, step, fixture):
    target = Path(process._refinement_log_path(record, step))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / fixture, target)
    return target


def finish(db, job, state="done"):
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state=? WHERE id=?", (state, job))
    return handle_process_job_terminal(db, job)


def job_count(db):
    with db.connect() as con:
        return con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0]


@pytest.mark.parametrize("fixture,engine,failure", [
    ("orca/co2_freq_orca42.out", "orca", "wrong_mode"),
    ("gaussian/water_opt_freq_g16.out", "gaussian", "wrong_mode"),
    ("orca/dvb_opt_orca42.out", "orca", "frequency_evidence_missing"),
    ("orca/segfault_mid_opt/dvb_opt_truncated_no_termination.out", "orca", "frequency_evidence_missing"),
    ("gaussian/hcn_ts_irc_g16.log", "gaussian", "frequency_evidence_missing"),
])
def test_native_non_ts_frequency_blocks_irc_and_repeated_event_spend(
    tmp_path, admission, fixture, engine, failure,
):
    db, record, step = waiting_fixture_stage(tmp_path, engine=engine)
    install_log(record, step, fixture)
    first = finish(db, step.job_id)
    assert first["record"]["blocked"]["failure_class"] == failure
    assert first["record"]["waiting_for"] == ""
    assert first["record"]["terminal"] is None
    assert handle_process_job_terminal(db, step.job_id) == first
    assert job_count(db) == 1


@pytest.mark.parametrize("hessian", [False, True])
def test_contract_single_mode_admits_one_irc_and_preserves_same_geometry(
    tmp_path, admission, hessian,
):
    db, record, step = waiting_fixture_stage(tmp_path)
    install_log(record, step, "benchmark_synthetic/ts_freq.out")
    stale_guess = Path(record.run_dir) / "stale_guess.xyz"
    stale_guess.write_text("3\nstale preoptimization guess\nO 0 0 -5\nC 0 0 0\nO 0 0 5\n")
    from cloudra.tools.core.molecule import read_molecule
    record.structures.candidate = read_molecule(input_path=str(stale_guess), input_format='xyz')
    process.save_record(record)
    hess = Path(step.input_path).with_suffix(".hess")
    if hessian:
        hess.write_text("contract Hessian placeholder; engine is never executed\n")
    result = finish(db, step.job_id)
    persisted = process.load_record(str(tmp_path), record.run_id)
    assert persisted.blocked is None and persisted.terminal is None
    assert [s.purpose for s in persisted.job_steps] == ["frequency", "irc"]
    irc = persisted.job_steps[-1]
    text = Path(irc.input_path).read_text()
    assert "%irc" not in text
    assert "Direction" not in text
    lines = text.splitlines()
    coordinate_start = next(i + 1 for i, line in enumerate(lines) if line.split() == ["*", "xyz", "0", "1"])
    atoms = [line.split() for line in lines[coordinate_start:coordinate_start + 3]]
    assert [atom[0] for atom in atoms] == ["O", "C", "O"]
    for atom, expected in zip(atoms, [[0, 0, -1.252682], [0, 0, 0], [0, 0, 1.252682]], strict=True):
        assert [float(value) for value in atom[1:]] == pytest.approx(expected)
    assert "def2-SVP" in text and "def2svp" not in text
    assert "InitHess" not in text
    assert "Hess_Filename" not in text
    assert persisted.input.verification.irc == record.input.verification.irc
    if hessian:
        assert hess.read_text() == "contract Hessian placeholder; engine is never executed\n"
    from cloudra.tools.core.calculation_intent import inspect_input
    assert inspect_input(text, engine="orca").tasks == {"irc"}
    assert handle_process_job_terminal(db, step.job_id) == result
    assert advance_process(db, record.pipeline_id) == result
    assert job_count(db) == 2


@pytest.mark.parametrize("missing", ["log", "geometry"])
def test_contract_single_mode_missing_artifact_never_submits_irc(tmp_path, admission, missing):
    db, record, step = waiting_fixture_stage(tmp_path)
    if missing != "log":
        install_log(record, step, "benchmark_synthetic/ts_freq.out")
        Path(step.input_path).with_name("optimized.xyz").unlink()
    result = finish(db, step.job_id)["record"]
    assert result["blocked"]["failure_class"] == (
        "frequency_evidence_missing" if missing == "log" else "irc_input_failed"
    )
    assert result["terminal"] is None and result["waiting_for"] == ""
    assert job_count(db) == 1


def test_contract_extra_imaginary_mode_blocks_irc(tmp_path, admission):
    db, record, step = waiting_fixture_stage(tmp_path)
    target = install_log(record, step, "benchmark_synthetic/ts_freq.out")
    text = target.read_text()
    assert "458.10" in text
    target.write_text(text.replace("458.10", "-458.10", 1))
    result = finish(db, step.job_id)["record"]
    assert result["blocked"]["failure_class"] == "wrong_mode"
    assert job_count(db) == 1


@pytest.mark.parametrize("fixture,outcome", [
    ("orca/extopt_relaxed_scan/scan_extopt_grouped.out", "peak"),
    ("orca/cope_relaxed_scan", "no_peak"),
])
def test_fixture_scan_terminal_event_preserves_peak_gate_and_no_duplicate_jobs(
    tmp_path, admission, fixture, outcome,
):
    seed = HCN_SCAN_XYZ if outcome == "peak" else (FIXTURES / fixture / "ts_scan.001.xyz").read_text()
    db, record, step = waiting_fixture_stage(tmp_path, purpose="scan", seed=seed)
    if outcome == "peak":
        install_log(record, step, fixture)
    else:
        folder = Path(step.input_path).parent
        for source in (FIXTURES / fixture).iterdir():
            shutil.copyfile(source, folder / source.name.replace("ts_scan", "scan"))
        # Sidecars contain real sampled geometries but no internal energy peak.
        Path(process._refinement_log_path(record, step)).parent.mkdir(parents=True, exist_ok=True)
    result = finish(db, step.job_id)
    saved = process.load_record(str(tmp_path), record.run_id)
    if outcome == "peak":
        assert saved.blocked is None and saved.waiting_for.startswith("job:")
        assert saved.path_kind == "scan" and saved.terminal is None
        assert saved.job_steps[-1].purpose == "ts_opt"
        text = Path(saved.job_steps[-1].input_path).read_text()
        assert "OptTS" in text and "Constraints" not in text
        candidate = saved.structures.candidate
        atoms = list(zip([atom.GetSymbol() for atom in candidate.GetAtoms()],
            candidate.GetConformer().GetPositions().tolist(), strict=True))
        assert [s for s, _ in atoms] == ["C", "H", "N"]
        assert atoms[0][1] == pytest.approx([2.1, 0.0, 0.0])
        assert job_count(db) == 2
    else:
        assert saved.blocked.failure_class == "scan_no_candidate"
        assert saved.structures.candidate is None and saved.terminal is None
        assert job_count(db) == 1
    assert handle_process_job_terminal(db, step.job_id) == result


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_failed_scan_retry_keeps_fixture_artifacts_and_charges_the_new_attempt(tmp_path, admission, state):
    db, record, step = waiting_fixture_stage(tmp_path, purpose="scan")
    log = install_log(record, step, "orca/segfault_mid_opt/dvb_opt_truncated_no_termination.out")
    before = log.read_bytes()
    result = finish(db, step.job_id, state)["record"]
    assert result["blocked"]["failure_class"] == "scan_job_failed"
    assert result["blocked"]["needs"] == ["compute_artifacts"]
    assert result["structures"]["candidate"] is None
    saved = process.load_record(str(tmp_path), record.run_id)
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    resumed = process.resume(saved, TsResumeRequest(changes={'guess':saved.input.guess.model_dump()},reason='keep unchanged scan',request_key='unchanged',expected_revision=saved.revision))
    assert resumed.intervention_count == 1
    assert resumed.declaration_revision == 2
    assert resumed.attempt_history[-1].blocked.model_dump() == result["blocked"]
    assert resumed.scan_step.job_id != step.job_id
    assert resumed.waiting_for == f'job:{resumed.scan_step.job_id}'
    assert log.read_bytes() == before and job_count(db) == 2


@pytest.mark.parametrize("fixture", ["orca/hcn_irc_orca60.out", "orca/cope_irc_extopt_mace_orca611.out"])
def test_normal_irc_without_geometry_sidecars_cannot_admit_endpoint_opt(tmp_path, admission, fixture):
    db, record, step = waiting_fixture_stage(tmp_path, purpose="irc")
    install_log(record, step, fixture)
    result = finish(db, step.job_id)["record"]
    assert result["blocked"]["failure_class"] == "endpoint_input_failed"
    assert result["terminal"] is None and result["waiting_for"] == ""
    assert job_count(db) == 1


def test_partial_gaussian_irc_submits_outer_frame_opt_but_never_claims_verified(tmp_path, admission):
    from rdkit import Chem

    from cloudra.tools.core import gaussian_frames
    from cloudra.tools.core.irc_path import xyz_block

    # Use the job's first native Input orientation; extracted IRC frames are
    # sorted by reaction coordinate and do not carry a starting TS XYZ here.
    native = (FIXTURES / 'gaussian/hcn_ts_irc_g16.log').read_text()
    rows = gaussian_frames._parse_last_input_orientation(native.split('Distance matrix', 1)[0])
    assert rows is not None
    symbols = [Chem.GetPeriodicTable().GetElementSymbol(number) for number, *_ in rows]
    positions = [point for _, *point in rows]
    assert symbols == ['C', 'N', 'H']
    db, record, step = waiting_fixture_stage(tmp_path, purpose="irc", engine="gaussian",
        seed=xyz_block(symbols, positions), smiles='C#N')
    install_log(record, step, "gaussian/hcn_ts_irc_g16.log")
    result = finish(db, step.job_id)
    saved = process.load_record(str(tmp_path), record.run_id)
    assert saved.blocked is None and saved.terminal is None
    assert saved.job_steps[-1].purpose == "reactant_opt"
    source = Path(saved.job_steps[-1].input_path).with_name("reactant_source.xyz")
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    atoms = read_xyz_atoms(source)
    assert [s for s, _ in atoms] == ["C", "N", "H"]
    # Negative-coordinate outer frame; maxsteps is not connectivity evidence.
    assert atoms[0][1] == pytest.approx([0.480862, -0.459245, 0.0])
    from cloudra.tools.core.calculation_intent import inspect_input
    assert inspect_input(Path(saved.job_steps[-1].input_path).read_text(), engine="gaussian").tasks == {"minimum_opt"}
    assert handle_process_job_terminal(db, step.job_id) == result
    assert job_count(db) == 2


@pytest.mark.parametrize("engine,fixture,xyz,smiles", [
    ("orca", "orca/co2_freq_orca42.out", CO2_XYZ, "O=C=O"),
    ("gaussian", "gaussian/water_opt_freq_g16.out", WATER_XYZ, "O"),
])
@pytest.mark.parametrize("defect", ["none", "missing_log", "missing_geometry", "saved_mismatch", "log_mismatch", "no_frequencies", "synthetic_wrong_mode"])
def test_native_endpoint_opt_freq_chain_requires_same_geometry_and_real_frequency(
    tmp_path, admission, engine, fixture, xyz, smiles, defect,
):
    db, record, step = waiting_fixture_stage(
        tmp_path, purpose="reactant_opt", engine=engine, seed=xyz, smiles=smiles,
    )
    install_log(record, step, fixture)
    opt_result = finish(db, step.job_id)
    saved = process.load_record(str(tmp_path), record.run_id)
    assert saved.job_steps[-1].purpose == "reactant_frequency"
    assert saved.terminal is None
    assert handle_process_job_terminal(db, step.job_id) == opt_result
    frequency = saved.job_steps[-1]
    assert frequency.endpoint_source == step.endpoint_source
    origin = frequency.endpoint_source
    assert origin.kind == "species_reference" and origin.label == "reactant"
    assert Path(origin.source_path).read_text() == xyz
    assert origin.sha256 == hashlib.sha256(Path(origin.source_path).read_bytes()).hexdigest()
    frequency_log = install_log(saved, frequency, fixture)
    geometry = Path(frequency.input_path).with_name("optimized.xyz")
    if defect == "missing_log":
        frequency_log.unlink()
    elif defect == "missing_geometry":
        geometry.unlink()
    elif defect == "saved_mismatch":
        geometry.write_text("3\nwrong geometry\nO 0 0 0\nH 4 0 0\nH 0 4 0\n")
    elif defect == "log_mismatch":
        install_log(saved, frequency, "gaussian/water_opt_freq_g16.out" if engine == "orca" else "orca/co2_freq_orca42.out")
    elif defect == "no_frequencies":
        install_log(saved, frequency, "orca/dvb_opt_orca42.out" if engine == "orca" else "gaussian/hcn_ts_irc_g16.log")
    elif defect == "synthetic_wrong_mode":
        # Contract-only fault injection; this is NOT a new scientific calculation.
        text = frequency_log.read_text()
        marker = "5:       289.50 cm**-1" if engine == "orca" else "Frequencies --   2169.7613"
        replacement = "5:       -289.50 cm**-1" if engine == "orca" else "Frequencies --   -2169.7613"
        assert text.count(marker) == 1
        frequency_log.write_text(text.replace(marker, replacement))
    result = finish(db, frequency.job_id)
    saved = process.load_record(str(tmp_path), record.run_id)
    minimum, _reason = process._validated_endpoint_minimum(saved, "reactant")
    if defect == "none":
        assert minimum is not None
        assert minimum[0] == (["O", "C", "O"] if engine == "orca" else ["O", "H", "H"])
        # A minimum alone cannot verify a TS: this replay has no IRC provenance.
        assert saved.blocked.failure_class == "endpoint_input_failed"
        assert saved.terminal is None
    else:
        assert minimum is None
        assert saved.terminal == "candidate_only"
    assert job_count(db) == 2
    assert handle_process_job_terminal(db, frequency.job_id) == result


@pytest.mark.parametrize("engine,fixture,xyz,smiles", [
    ("orca", "orca/co2_freq_orca42.out", CO2_XYZ, "O=C=O"),
    ("gaussian", "gaussian/water_opt_freq_g16.out", WATER_XYZ, "O"),
])
def test_endpoint_opt_without_source_provenance_never_submits_frequency(
    tmp_path, admission, engine, fixture, xyz, smiles,
):
    db, record, step = waiting_fixture_stage(
        tmp_path, purpose="reactant_opt", engine=engine, seed=xyz, smiles=smiles,
    )
    step.endpoint_source = None
    with use_pipeline_database(db):
        process.save_record(record)
    install_log(record, step, fixture)

    result = finish(db, step.job_id)
    saved = process.load_record(str(tmp_path), record.run_id)
    assert saved.terminal == "candidate_only"
    assert "accepted optimization has no endpoint source provenance" in saved.stage_record("verdict").detail
    assert saved.waiting_for == ""
    assert [job.purpose for job in saved.job_steps] == ["reactant_opt"]
    assert job_count(db) == 1
    assert handle_process_job_terminal(db, step.job_id) == result


@pytest.mark.parametrize("purpose", ["scan", "frequency", "irc"])
def test_fixture_completion_cannot_advance_after_immutable_input_tampering(tmp_path, admission, purpose):
    db, record, step = waiting_fixture_stage(tmp_path, purpose=purpose)
    log = install_log(record, step, "benchmark_synthetic/ts_freq.out")
    log_bytes = log.read_bytes()
    Path(step.input_path).write_text("changed input after binding\n")
    result = finish(db, step.job_id)
    assert result["record"]["blocked"]["failure_class"] == "stage_input_changed"
    assert result["record"]["terminal"] is None
    assert log.read_bytes() == log_bytes and job_count(db) == 1
    assert handle_process_job_terminal(db, step.job_id) == result


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture,engine,success,failure", [
    ("orca/co2_freq_orca42.out", "orca", True, "wrong_mode"),
    ("gaussian/water_opt_freq_g16.out", "gaussian", True, "wrong_mode"),
    ("orca/segfault_mid_opt/dvb_opt_truncated_no_termination.out", "orca", False, "job_failed"),
])
async def test_native_monitor_result_flows_into_pipeline_without_bypassing_science(
    tmp_path, admission, fixture, engine, success, failure,
):
    import asyncio

    from cloudra.runtime import monitor

    db, record, step = await asyncio.to_thread(waiting_fixture_stage, tmp_path, engine=engine)
    log = await asyncio.to_thread(install_log, record, step, fixture)
    parser = monitor._parse_orca_log if engine == "orca" else monitor._parse_gaussian_log
    parsed, actual = await parser(log)
    assert actual is success and parsed["is_success"] is success
    result = await asyncio.to_thread(finish, db, step.job_id, "done" if actual else "failed")
    assert result["record"]["blocked"]["failure_class"] == failure
    assert result["record"]["terminal"] is None
    assert await asyncio.to_thread(job_count, db) == 1


@pytest.mark.asyncio
async def test_agent_native_frequency_failure_survives_repeated_inspection_without_irc_spend(tmp_path, admission):
    """Real Agent calls observe the durable fixture-driven frequency gate and budget."""
    import asyncio

    from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step

    ready, completed = asyncio.Event(), asyncio.Event()
    provider = ScriptedProvider(by_role={"small_mol": [
        Step(wait_for=ready, tools=[("ts_inspect", {"run_id": "ts_0001"})]),
        Step(wait_for=completed, tools=[("ts_inspect", {"run_id": "ts_0001"})]),
        Step(tools=[("ts_inspect", {"run_id": "ts_0001"})]),
        Step(tools=[("ts_inspect", {"run_id": "ts_0001"})]),
        Step(stop=True),
    ]})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        agent = await harness.spawn("small_mol", protocol="traditional")
        db, record, step = await asyncio.to_thread(
            waiting_fixture_stage, tmp_path, project_id=harness.project.id, owner_id=agent.id,
        )
        await asyncio.to_thread(install_log, record, step, "orca/co2_freq_orca42.out")
        ready.set()
        await harness.wait_for(
            lambda: any(call["status"] == "completed" for call in harness.tool_events(agent)),
            "Agent observed the queued frequency job",
        )
        await asyncio.to_thread(finish, db, step.job_id)
        completed.set()
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        assert len(calls) == 4 and all(call["is_success"] for call in calls), harness.describe(agent)
        assert calls[0]["result_data"]["waiting_for"][0]["job_id"] == step.job_id
        for call in calls[1:]:
            result = call["result_data"]
            assert result["blocked"]["failure_class"] == "wrong_mode"
            assert result["usage"]["interventions"] == 0 and result["result"] is None
            assert result["waiting_for"] == []
        saved = await asyncio.to_thread(process.load_record, str(tmp_path), record.run_id)
        assert saved.declaration_revision == 1 and saved.intervention_count == 0
        assert [step.purpose for step in saved.job_steps] == ["frequency"]
        assert await asyncio.to_thread(job_count, db) == 1
    finally:
        ready.set()
        completed.set()
        await harness.aclose()
