from pathlib import Path

import pytest

from cloudra.services.ts_pipeline_store import get_process, save_process_record
from cloudra.tools.core import ts_process
from tests.test_ts_pipeline_driver import waiting_process


def checkpoint(tmp_path):
    db, pid, job = waiting_process(tmp_path)
    record = ts_process.TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.stage = "guess"
    record.waiting_for = ""
    record.job_steps = [ts_process.TsJobStep(purpose="path", job_id=job, input_path=record.job_steps[0].input_path)]
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.reaction_state import ReactionStructures

    molecule = Chem.AddHs(Chem.MolFromSmiles(record.input.reaction.reactant_smiles))
    assert AllChem.EmbedMolecule(molecule, randomSeed=42) == 0
    record.structures = ReactionStructures(reactant=molecule, product=molecule,
        candidate=molecule, product_to_reactant=tuple(range(molecule.GetNumAtoms())))
    record.path_kind = "xtb_path"
    from cloudra.tools.core.ts_inputs import XtbPathGuess
    record.input.guess = XtbPathGuess(kind="xtb_path",method="GFN2-xTB",refinement_runs=3)
    record.blocked = ts_process.TsBlocked(
        stage="guess", failure_class="path_not_converged", message="fixture failed path"
    )
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (job,))
        con.execute("UPDATE ts_pipeline_stages SET stage_key='path' WHERE job_id=?", (job,))
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    return db, pid, record






@pytest.mark.parametrize("crash_after_ready", [False, True])
def test_scan_submission_recovers_exact_input_after_checkpoint_crash(tmp_path, monkeypatch, crash_after_ready):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.Chemtool.ts_guess import TsGuess_output_schema
    from cloudra.tools.core.ts_pipeline_driver import advance_process

    db, pid, record = checkpoint(tmp_path)
    record.blocked = None
    record.job_steps = []
    from cloudra.tools.core.qm_calculation import QmCalculation
    from cloudra.tools.core.ts_inputs import ScanGuess
    record.input.guess = ScanGuess(kind="scan", calculation=QmCalculation(engine="orca", method="b3lyp", basis_set="def2svp", keywords=""),
        scans=[{"coord_type": "bond", "atoms": [0, 1], "scan_start": 1, "scan_end": 2, "scan_steps": 5}],
    )
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    def prepare(self, request):
        from cloudra.tools.core.molecule import to_xyz

        path = Path(request.output_path)
        geometry = '\n'.join(to_xyz(record.structures.reactant).splitlines()[2:])
        ts_process._write_immutable_input(str(path), f"! Opt B3LYP def2SVP\n%geom Scan B 0 1 = 1., 2., 5 end end\n* xyz 0 1\n{geometry}\n*\n")
        return TsGuess_output_schema(is_success=True, input_file_path=str(path))

    monkeypatch.setattr("cloudra.tools.Chemtool.ts_guess.TsGuess._scan_prepare", prepare)
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    submit = ts_process._submit_step

    def die(*args):
        if crash_after_ready:
            submit(*args)
        raise RuntimeError("crash before checkpoint")

    monkeypatch.setattr(ts_process, "_submit_step", die)
    with pytest.raises(RuntimeError, match="crash before checkpoint"):
        advance_process(db, pid)
    monkeypatch.setattr(ts_process, "_submit_step", submit)
    first = advance_process(db, pid)["record"]
    again = advance_process(db, pid)["record"]
    assert first["scan_step"]["job_id"] == again["scan_step"]["job_id"]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 2
    assert len(list(Path(record.run_dir).rglob("scan.inp"))) == 1


@pytest.mark.parametrize("imaginary", [[], [-300.0], [-300.0, -100.0], None])
def test_frequency_gate_checks_first_order_saddle_before_irc_spend(tmp_path, monkeypatch, imaginary):
    from types import SimpleNamespace

    from cloudra.services.compute_admission import AdmissionOutcome

    db, pid, record = checkpoint(tmp_path)
    record.stage = "refine"
    record.blocked = None
    record.job_steps[0].purpose = "frequency"
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done'")
    log = tmp_path / "frequency.out"
    log.write_text("synthetic frequency evidence")
    monkeypatch.setattr(ts_process, "_refinement_log_path", lambda *args: str(log))
    monkeypatch.setattr(
        "cloudra.dag.evidence_ingest.snapshot_evidence_file",
        lambda *args, **kwargs: SimpleNamespace(frequencies=imaginary, imaginary_frequencies=imaginary),
    )

    def writer(record, folder):
        from cloudra.tools.core.molecule import to_xyz

        target = Path(folder) / "irc.inp"
        geometry = '\n'.join(to_xyz(record.structures.candidate).splitlines()[2:])
        target.write_text(f"! IRC B3LYP def2SVP\n* xyz 0 1\n{geometry}\n*\n")
        return "", str(target)

    monkeypatch.setattr(ts_process, "_write_irc_input", writer)
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    result = ts_process._refine(record)
    expected_jobs = 2 if imaginary is not None and len(imaginary) == 1 else 1
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == expected_jobs
    assert (result.blocked is None) == (expected_jobs == 2)


@pytest.mark.parametrize("stage", ["path", "ts_opt"])
def test_scientific_job_failure_reaches_cards_and_rejects_unchanged_candidate(tmp_path, monkeypatch, stage):
    from cloudra.tools.core.conformer_cards import build_region_cards
    from cloudra.tools.core.conformer_catalog import Qualification, content_digest
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates
    from cloudra.tools.core.conformer_selection import SelectionContext, SelectionDecision, validate_selection
    from cloudra.tools.core.xtb_path_runner import XtbPathResult
    from tests.test_conformer_catalog import make_candidate

    db, pid, record = checkpoint(tmp_path)
    candidate = make_candidate(
        tmp_path, qualification=Qualification(status="qualified", evidence_refs=["fixture qualification"])
    )
    record.catalog_id = candidate.catalog_id
    record.selected_candidate_id = candidate.candidate_id
    record.job_steps[0].purpose = stage
    if stage == "path":
        monkeypatch.setattr(
            ts_process,
            "_queued_path",
            lambda *args: (
                XtbPathResult(
                    run_dir=str(tmp_path), returncode=1, termination_reason="path_not_converged", refinement_runs=3
                ),
                record,
            ),
        )
        result = ts_process._guess(record)
    else:
        log = tmp_path / "failed.out"
        log.write_text("GEOMETRY OPTIMIZATION DID NOT CONVERGE")
        monkeypatch.setattr(ts_process, "_refinement_log_path", lambda *args: str(log))
        result = ts_process._refine(record)
    assert result.candidate_attempts
    assert result.candidate_attempts[-1].job_id == record.job_steps[0].job_id
    assert result.candidate_attempts[-1].failure_class in ("path_failed", "nonconvergence")
    snapshot = partition_candidates(
        [candidate], RegionConfig(descriptor_specs=[DescriptorSpec(kind="distance", stable_atom_ids=["C1", "O1"])])
    )
    cards = build_region_cards(snapshot, [candidate], result.candidate_attempts)
    context = SelectionContext(
        project_id=candidate.project_id,
        owner_id=candidate.owner_id,
        catalog_id=candidate.catalog_id,
        partition_revision=snapshot.revision,
        declaration_hash=content_digest(record.input.model_dump(mode="json")),
        cards=cards,
        attempts=result.candidate_attempts,
        method_fingerprint="fixture",
    )
    decision = SelectionDecision(
        decision_id="repeat",
        catalog_id=context.catalog_id,
        partition_revision=context.partition_revision,
        declaration_hash=context.declaration_hash,
        candidate_id=candidate.candidate_id,
        region_id=cards[0].region_id,
        reason="fixture same-input repeat",
        evidence_refs=cards[0].evidence_refs,
    )
    with pytest.raises(ValueError, match="same failed input"):
        validate_selection(decision, context)


def test_remote_path_pullback_continues_to_budgeted_ts_submission(tmp_path, monkeypatch):
    import shutil

    from cloudra.runtime import chem_task
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core.molecule import to_xyz
    from cloudra.tools.core.xtb_path_runner import XtbPathResult

    db, pid, record = checkpoint(tmp_path)
    remote = tmp_path / "remote"
    local = tmp_path / "pulled-back"
    remote.mkdir()
    manifest = remote / "path.json"
    manifest.write_text(
        chem_task.ChemTask(task="xtb_path", reactant_xyz="x", product_xyz="y", cpus=1).model_dump_json()
    )
    seed = remote / "ts.xyz"
    seed.write_text(to_xyz(record.structures.reactant, comment="synthetic remote TS seed"))
    monkeypatch.setattr(
        "cloudra.tools.core.xtb_path_runner.run_xtb_path",
        lambda *args: XtbPathResult(
            run_dir=str(remote),
            returncode=0,
            usable_as_guess=True,
            ts_xyz_path=str(seed),
            path_xyz_path=str(seed),
            ts_candidate_energy_eh=-1,
            termination_reason="completed",
        ),
    )
    assert chem_task.run_task(str(manifest)) == 0
    shutil.copytree(remote, local)
    shutil.rmtree(remote)
    record.job_steps[0].input_path = str(local / "path.json")
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done'")
    record.blocked = None
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    result = ts_process._guess(record)
    assert result.structures.candidate is not None
    assert str(local / "ts.xyz") in result.evidence_candidates
    assert result.blocked is None
    result = ts_process._submit(result)
    assert result.blocked is None
    assert result.job_steps[-1].purpose == "ts_opt"
    assert Path(result.job_steps[-1].input_path).is_file()
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 2


def test_reaction_center_change_without_ring_invalidates_geometry_dependencies(tmp_path):
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    from tests.test_ts_revision_identity import molecular_fixture
    record, _ = molecular_fixture(tmp_path)
    record.stage = 'guess'
    record.input.reaction.reaction_center = []
    record.input.conformers.guidance.ring_order=[]
    record.job_steps=[ts_process.TsJobStep(purpose='path',job_id=7,state='done')]
    request=TsResumeRequest(changes={'reaction':{'reaction_center':[(0,1)]}},reason='change assembly centre',request_key='assembly',expected_revision=record.revision)
    result=revise_record(record,request,plan_input_revision(record,request))
    assert result.stage=='build'
    assert result.structures.reactant is not None
    assert result.structures.candidate is None
    assert not result.job_steps
    assert result.attempt_history[-1].job_steps[-1].purpose=='path'


@pytest.mark.parametrize("note", ["", "retain the existing scan"])
def test_same_input_retry_is_replayed_once_and_can_retry_again(tmp_path, monkeypatch, note):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_store import get_revision_receipt
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
    from tests.test_ts_fixture_pipeline import waiting_fixture_stage

    monkeypatch.setattr("cloudra.services.compute_admission.admit_job", lambda **_:
        AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"))
    db, initial, old_step = waiting_fixture_stage(tmp_path, purpose="scan")
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (old_step.job_id,))
    state = handle_process_job_terminal(db, old_step.job_id)
    record = ts_process.TsProcessRecord.model_validate(state['record'])
    old_input = Path(old_step.input_path).read_bytes()
    request = TsResumeRequest(changes={}, reason=note or 'Retry the native scan',
        request_key='retry-once', expected_revision=record.revision)
    retried = ts_process.resume(record, request)
    receipt = get_revision_receipt(db, process_id=initial.pipeline_id, request_key=request.request_key)
    replay = ts_process.resume(record, request)
    assert retried.input == replay.input == record.input
    assert replay.intervention_count == retried.intervention_count == 1
    assert replay.scan_step.job_id == retried.scan_step.job_id != old_step.job_id
    assert get_revision_receipt(db, process_id=initial.pipeline_id, request_key=request.request_key) == receipt
    assert retried.attempt_history[-1].failed_attempt == record.failed_attempt
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 2
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (retried.scan_step.job_id,))
    state = handle_process_job_terminal(db, retried.scan_step.job_id)
    failed_again = ts_process.TsProcessRecord.model_validate(state['record'])
    retried_again = ts_process.resume(failed_again, TsResumeRequest(changes={}, reason='Another retry',
        request_key='retry-again', expected_revision=failed_again.revision))
    assert retried_again.intervention_count == 2
    assert retried_again.scan_step.job_id not in (old_step.job_id, retried.scan_step.job_id)
    assert retried_again.attempt_history[-1].failed_attempt == failed_again.failed_attempt
    assert Path(old_step.input_path).read_bytes() == old_input
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 3


pytestmark = pytest.mark.usefixtures("ts_producer_authority")
