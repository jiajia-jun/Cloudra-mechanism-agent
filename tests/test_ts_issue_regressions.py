"""Offline regressions for concrete-input identity and native failure evidence."""

import hashlib
from pathlib import Path

import pytest

from cloudra.tools.core import ts_process
from cloudra.tools.core.ts_inputs import FileConformer
from tests.test_ts_stage_inputs import record_fixture


@pytest.mark.parametrize("role", ["reactant", "product"])
def test_mirrored_seed_can_enter_optimization_but_cannot_verify_wrong_stereochemistry(tmp_path, role):
    pytest.importorskip("rdkit", reason="concrete identity requires the chem extra")
    from rdkit import Chem
    from rdkit.Chem import AllChem

    record = record_fixture(tmp_path, stage="map")
    smiles = "F[C@](Cl)(Br)I"
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = smiles
    record.input.reaction.atom_map = list(range(5))
    record.input.reaction.reaction_center = [(0, 1)]
    record.input.conformers.guidance.ring_order = []
    graph = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(graph, randomSeed=11) == 0
    for side in ("reactant", "product"):
        xyz, mol = tmp_path / f"{side}.xyz", tmp_path / f"{side}.mol"
        mol.write_text(Chem.MolToMolBlock(graph))
        coordinates = Chem.Mol(graph)
        if side == role:
            conf = coordinates.GetConformer()
            for index, point in enumerate(conf.GetPositions().tolist()):
                conf.SetAtomPosition(index, [-point[0], point[1], point[2]])
        xyz.write_text(Chem.MolToXYZBlock(coordinates))
        setattr(record.input.conformers, side,
                FileConformer(kind="file", xyz_path=str(xyz), mol_path=str(mol)))
    ts_process._build(record)
    ts_process._map(record)
    assert record.blocked is None
    assert record.input_binding["binding_status"] == "complete"
    assert record.terminal is None
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_inputs import EndpointSeed

    source = getattr(record.input.conformers, role)
    endpoint = getattr(record.input.verification, role + "_endpoint")
    endpoint.seed = EndpointSeed(kind="file", xyz_path=source.xyz_path,
        mol_path=source.mol_path, evidence_refs=[source.xyz_path])
    endpoint.optimization = record.input.ts_optimization
    directory = tmp_path / (role + "_opt")
    directory.mkdir()
    error, input_path = ts_process._write_endpoint_input(record, str(directory), role, "opt")
    assert error == "", error
    assert Path(input_path).is_file()
    atoms = read_xyz_atoms(source.xyz_path)
    error = ts_process._endpoint_identity_error(record, role,
        ([symbol for symbol, _ in atoms], [point for _, point in atoms]))
    assert role in error
    assert "stereo" in error.lower() or "chirality" in error.lower()
    assert record.job_steps == [] and record.scan_step is None


def test_failed_endpoint_keeps_native_nonconvergence_warning_before_normal_footer(tmp_path, monkeypatch):
    record = record_fixture(tmp_path, stage="refine")
    step = ts_process.TsJobStep(purpose="reactant_opt", job_id=7,
                               input_path=str(tmp_path / "endpoint.inp"), state="failed",
                               actual_calculation=record.input.ts_optimization)
    record.job_steps = [step]
    log = Path(ts_process._refinement_log_path(record, step))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "The optimization did not converge but reached the maximum number of\n"
        "optimization cycles.\nPlease check your results very carefully.\n"
        "Energy change 1.0 NO\nRMS gradient 1.0 NO\nMAX gradient 1.0 NO\n"
        + "References and module timings\n" * 25 + "ORCA TERMINATED NORMALLY\n"
    )
    monkeypatch.setattr(ts_process, "_read_job_state", lambda *_: "failed")
    ts_process._refine(record)
    assert record.failed_attempt["failure_class"] == "nonconvergence"
    assert "The optimization did not converge" in "\n".join(record.blocked.atom_details)
    assert record.job_steps == [step] and step.state == "failed"
    assert record.waiting_for == ""


@pytest.mark.parametrize("text,classification", [
    ("SCF NOT CONVERGED\nORCA TERMINATED NORMALLY\n", "nonconvergence"),
    ("ERROR (SHARK): Failed to read input file\n", "unclassified_failure"),
    ("THE OPTIMIZATION HAS CONVERGED\nORCA TERMINATED NORMALLY\n", "unclassified_failure"),
])
def test_native_diagnosis_does_not_confuse_scf_input_or_success_markers(tmp_path, text, classification):
    log = tmp_path / "native.out"
    log.write_text(text)
    actual, details = ts_process._native_failure_details(str(log), "orca")
    assert actual == classification
    assert text.splitlines()[0] in details


def _failed_scan(tmp_path):
    from cloudra.tools.core.ts_inputs import TsResumeRequest

    record = record_fixture(tmp_path, stage="guess")
    source = tmp_path / "failed.inp"
    source.write_text("failed scan input\n")
    step = ts_process.TsJobStep(purpose="scan", job_id=7, input_path=str(source), state="failed",
                               actual_calculation=record.input.guess.calculation)
    record.scan_step = step
    log = Path(ts_process._refinement_log_path(record, step))
    log.write_text("ERROR (SHARK): Failed to read input file\n")
    ts_process._record_candidate_failure(record, "unclassified_failure", step, str(log))
    record.blocked = ts_process.TsBlocked(stage="guess", failure_class="scan_job_failed", message="SHARK failure")
    request = dict(changes={}, reason="Retry the scan after checking the native failure",
                   request_key="retry-scan", expected_revision=record.revision)
    return record, TsResumeRequest, request, source, log


@pytest.mark.parametrize("change_scan", [False, True])
def test_failed_scan_retry_preserves_native_failure_and_history(tmp_path, change_scan):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record, schema, payload, source, log = _failed_scan(tmp_path)
    if change_scan:
        guess = record.input.guess.model_dump(mode="json")
        guess["scans"][0]["scan_steps"] = 8
        payload["changes"] = {"guess": guess}
    original = source.read_bytes(), log.read_bytes()
    request = schema.model_validate(payload)
    receipt = plan_input_revision(record, request)
    revised = revise_record(record, request, receipt)

    assert receipt.changes == (["guess.scans"] if change_scan else [])
    assert revised.input.guess.scans[0].scan_steps == (8 if change_scan else 7)
    assert revised.scan_step is None and revised.stage == "guess"
    assert revised.terminal is None and revised.failed_attempt is None
    assert revised.attempt_history[-1].blocked == record.blocked
    assert revised.attempt_history[-1].failed_attempt == record.failed_attempt
    assert revised.attempt_history[-1].job_steps[0].job_id == 7
    assert record.scan_step.state == "failed" and record.attempt_history == []
    assert (source.read_bytes(), log.read_bytes()) == original


def test_failed_scan_resource_change_keeps_existing_authorized_budget(tmp_path):
    from cloudra.tools.core.ts_inputs import TsExecutionLimits
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record, schema, payload, _, _ = _failed_scan(tmp_path)
    record.input.execution.limits = TsExecutionLimits(source="explicit_user", max_compute_actions=2)
    payload["changes"] = {"execution": {"memory_mb": 4096}}
    change = schema.model_validate(payload)
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert receipt.changes == ["execution.memory_mb"]
    assert revised.input.execution.limits == record.input.execution.limits
    payload["changes"]["execution"]["limits"] = {"source": "explicit_user", "max_compute_actions": 3}
    before = record.model_dump(mode="json")
    with pytest.raises(ValueError, match="cannot raise authorized limits"):
        plan_input_revision(record, schema.model_validate(payload))
    assert record.model_dump(mode="json") == before


@pytest.mark.parametrize("change_scan", [False, True])
def test_failed_scan_revision_receipt_is_durable_and_replay_does_not_duplicate_jobs(tmp_path, change_scan):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import (
        bind_stage_job,
        commit_input_revision,
        create_process,
        get_process,
        get_revision_receipt,
        save_process_record,
    )
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record, schema, payload, source, _ = _failed_scan(tmp_path)
    db = ComputeDB(data_dir=tmp_path / "ledger").init()
    process = create_process(db, request_key="failed-scan", payload=dict(
        project_id="project", owner_id="owner", workspace_dir=str(tmp_path),
        input=record.input.model_dump(mode="json")))
    pid = process["process_id"]
    job = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key="scan", attempt=1,
        job_payload=dict(conversation_id="project", session_id="owner", path=str(source),
                         state="ready", jobtype="orca", node_id="fixture"))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (job,))
    record.pipeline_id = pid
    record.scan_step.job_id, record.scan_step.stage_key = job, "scan"
    log = Path(ts_process._refinement_log_path(record, record.scan_step))
    log.write_text("ERROR (SHARK): Failed to read input file\n")
    ts_process._record_candidate_failure(record, "unclassified_failure", record.scan_step, str(log))
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    record.revision = get_process(db, pid)["revision"]
    payload["expected_revision"] = record.revision
    if change_scan:
        guess = record.input.guess.model_dump(mode="json")
        guess["scans"][0]["scan_steps"] = 8
        payload["changes"] = {"guess": guess}
    original = source.read_bytes(), log.read_bytes()
    request = schema.model_validate(payload)
    receipt = plan_input_revision(record, request)
    revised = revise_record(record, request, receipt)
    accepted = commit_input_revision(db, process_id=pid, request=request,
                                    record=revised.model_dump(mode="json"), receipt=receipt)
    reopened = ComputeDB(data_dir=tmp_path / "ledger").init()
    assert get_revision_receipt(reopened, process_id=pid, request_key=request.request_key) == accepted
    committed = get_process(reopened, pid)
    assert committed["record"]["attempt_history"][-1]["failed_attempt"] == record.failed_attempt
    assert committed["record"]["attempt_history"][-1]["blocked"]["failure_class"] == "scan_job_failed"
    assert committed["record"]["scan_step"] is None
    assert commit_input_revision(reopened, process_id=pid, request=request,
        record=revised.model_dump(mode="json"), receipt=receipt) == accepted
    assert get_process(reopened, pid) == committed
    assert (source.read_bytes(), log.read_bytes()) == original
    with reopened.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1
        assert con.execute("SELECT state FROM compute_jobs WHERE id=?", (job,)).fetchone()[0] == "failed"


def test_revision_bound_source_tampering_still_blocks_build(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    source = tmp_path / "reactant.xyz"
    source.write_text("2\nsource\nH 0 0 0\nH 0 0 .74\n")
    record = record_fixture(tmp_path, stage="build")
    change = dict(changes={"conformers": {"reactant": {"kind": "file", "xyz_path": str(source)}}},
        reason="Supply the file conformer", request_key="source", expected_revision=record.revision)
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    request = TsResumeRequest.model_validate(change)
    revised = revise_record(record, request, plan_input_revision(record, request))
    assert revised.input_binding["revision_source_hashes"]["reactant"]["xyz"] == hashlib.sha256(source.read_bytes()).hexdigest()
    # The actual revision pins the source; editing it before build stays invalid.
    source.write_text("2\nchanged before build\nH 0 0 0\nH 0 0 1.1\n")
    ts_process._build(revised)
    assert revised.blocked is not None
    assert "source changed since atom identity was proved" in revised.blocked.message
    assert revised.job_steps == []
