"""Offline regressions for concrete-input identity and native failure evidence."""

import hashlib
import json
from pathlib import Path

import pytest

from cloudra.tools.core import ts_process
from cloudra.tools.core.ts_inputs import FileConformer
from tests.test_ts_stage_inputs import record_fixture


@pytest.mark.parametrize("role", ["reactant", "product"])
def test_input_binding_rejects_xyz_mirroring_correct_mol_before_compute(tmp_path, role):
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
    assert record.blocked is not None
    assert record.blocked.failure_class == "input_identity_unconfirmed"
    assert role in record.blocked.message
    assert record.blocked.issues[0]["role"] == role
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


def _failed_scan_recovery(tmp_path):
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
    proof = tmp_path / "repair-receipt.json"
    proof.write_text(json.dumps(dict(failed_attempt_id="1:scan:7",
        failure_input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        repair="temporary-file access repaired")))
    guess = record.input.guess.model_dump(mode="json")
    guess["scans"][0]["scan_steps"] = 8
    request = dict(changes={"guess": guess}, reason="Bound receipt records repaired temporary-file access",
                   request_key="recovered-scan", expected_revision=record.revision,
                   scan_recovery={"failed_attempt_id": "1:scan:7",
                                  "failure_input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                  "failure_log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                                  "evidence_refs": [{"path": str(proof), "sha256": hashlib.sha256(proof.read_bytes()).hexdigest()}]})
    return record, TsResumeRequest, request, proof


def test_failed_scan_bound_recovery_preserves_failure_diff_and_evidence(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record, schema, payload, proof = _failed_scan_recovery(tmp_path)
    request = schema.model_validate(payload)
    receipt = plan_input_revision(record, request)
    revised = revise_record(record, request, receipt)
    assert receipt.recovery_evidence["failed_attempt"]["attempt_id"] == "1:scan:7"
    difference = receipt.recovery_evidence["input_diff"][0]
    assert difference["field"] == "guess.scans"
    assert difference["before"][0]["scan_steps"] == 7
    assert difference["after"][0]["scan_steps"] == 8
    assert receipt.recovery_evidence["evidence_refs"][0]["sha256"] == hashlib.sha256(proof.read_bytes()).hexdigest()
    assert revised.attempt_history[-1].recovery_evidence == receipt.recovery_evidence
    assert revised.attempt_history[-1].blocked.failure_class == "scan_job_failed"
    assert revised.scan_step is None and record.scan_step.job_id == 7


@pytest.mark.parametrize("defect", ["attempt", "failure_log", "evidence", "failure_as_repair"])
def test_failed_scan_recovery_rejects_wrong_binding_without_mutation(tmp_path, defect):
    from cloudra.tools.core.ts_revision import plan_input_revision

    record, schema, payload, proof = _failed_scan_recovery(tmp_path)
    recovery = payload["scan_recovery"]
    if defect == "attempt":
        recovery["failed_attempt_id"] = "1:scan:8"
    elif defect == "failure_log":
        recovery["failure_log_sha256"] = "0" * 64
    elif defect == "failure_as_repair":
        path = Path(ts_process._refinement_log_path(record, record.scan_step))
        recovery["evidence_refs"] = [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
    else:
        proof.write_text("changed after evidence declaration\n")
    before = record.model_dump(mode="json")
    with pytest.raises(ValueError, match="recovery"):
        plan_input_revision(record, schema.model_validate(payload))
    assert record.model_dump(mode="json") == before


def test_failed_scan_environment_recovery_can_keep_chemical_input(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision

    record, schema, payload, _ = _failed_scan_recovery(tmp_path)
    payload["changes"] = {}
    receipt = plan_input_revision(record, schema.model_validate(payload))
    assert receipt.changes == []
    assert receipt.recovery_evidence["input_diff"] == []
    assert record.scan_step.state == "failed"


def test_repair_receipt_must_itself_identify_the_failed_input(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision

    record, schema, payload, proof = _failed_scan_recovery(tmp_path)
    proof.write_text('{"repair":"unrelated repair note"}')
    payload["scan_recovery"]["evidence_refs"][0]["sha256"] = hashlib.sha256(proof.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="recovery.*binding"):
        plan_input_revision(record, schema.model_validate(payload))


def test_failed_scan_resource_repair_keeps_existing_authorized_budget(tmp_path):
    from cloudra.tools.core.ts_inputs import TsExecutionLimits
    from cloudra.tools.core.ts_revision import plan_input_revision

    record, schema, payload, _ = _failed_scan_recovery(tmp_path)
    record.input.execution.limits = TsExecutionLimits(source="explicit_user", max_compute_actions=2)
    payload["changes"] = {"execution": {"memory_mb": 4096}}
    receipt = plan_input_revision(record, schema.model_validate(payload))
    assert receipt.changes == ["execution.memory_mb"]
    assert receipt.recovery_evidence["input_diff"] == [{"field": "execution.memory_mb", "before": 2048, "after": 4096}]
    payload["changes"]["execution"]["limits"] = {"source": "explicit_user", "max_compute_actions": 3}
    with pytest.raises(ValueError, match="cannot raise authorized limits"):
        plan_input_revision(record, schema.model_validate(payload))


def test_failed_scan_can_bind_actual_changed_conformer_file(tmp_path):
    pytest.importorskip("rdkit", reason="concrete identity requires the chem extra")
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.ts_revision import plan_input_revision

    record, schema, payload, _ = _failed_scan_recovery(tmp_path)
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx() + 1)
    assert AllChem.EmbedMolecule(mol, randomSeed=42) == 0
    record.input.reaction.atom_map = list(range(9))
    record.input.conformers.guidance.ring_order = []
    for role in ("reactant", "product"):
        xyz, graph = tmp_path / f"{role}.xyz", tmp_path / f"{role}.mol"
        xyz.write_text(Chem.MolToXYZBlock(mol))
        graph.write_text(Chem.MolToMolBlock(mol))
        setattr(record.input.conformers, role, FileConformer(kind="file", xyz_path=str(xyz), mol_path=str(graph)))
    ts_process._build(record)
    xyz = tmp_path / "reactant.xyz"
    coordinates = mol.GetConformer()
    for index, point in enumerate(coordinates.GetPositions().tolist()):
        coordinates.SetAtomPosition(index, [point[0] + 0.05, point[1], point[2]])
    xyz.write_text(Chem.MolToXYZBlock(mol))
    payload["changes"] = {}
    payload["scan_recovery"]["evidence_refs"] = [{"path": str(xyz), "sha256": hashlib.sha256(xyz.read_bytes()).hexdigest()}]
    receipt = plan_input_revision(record, schema.model_validate(payload))
    assert receipt.recovery_evidence["evidence_refs"][0]["kind"] == "changed_conformer_file"
    assert receipt.recovery_evidence["evidence_refs"][0]["role"] == "reactant"
    assert "conformers.reactant.xyz_path" in receipt.changes


@pytest.mark.parametrize("tamper", [False, True])
def test_scan_recovery_receipt_is_durable_and_rechecked_at_commit(tmp_path, tamper):
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

    record, schema, payload, proof = _failed_scan_recovery(tmp_path)
    db = ComputeDB(data_dir=tmp_path / "ledger").init()
    process = create_process(db, request_key="failed-scan", payload=dict(
        project_id="project", owner_id="owner", workspace_dir=str(tmp_path),
        input=record.input.model_dump(mode="json")))
    pid = process["process_id"]
    job = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key="scan", attempt=1,
        job_payload=dict(conversation_id="project", session_id="owner", path=record.scan_step.input_path,
                         state="ready", jobtype="orca", node_id="fixture"))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (job,))
    record.pipeline_id = pid
    record.scan_step.job_id, record.scan_step.stage_key = job, "scan"
    ts_process._record_candidate_failure(record, "unclassified_failure", record.scan_step,
                                        ts_process._refinement_log_path(record, record.scan_step))
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    record.revision = get_process(db, pid)["revision"]
    payload["expected_revision"] = record.revision
    payload["scan_recovery"]["failed_attempt_id"] = f"1:scan:{job}"
    payload["scan_recovery"]["failure_log_sha256"] = record.failed_attempt["log_sha256"]
    proof.write_text(json.dumps(dict(failed_attempt_id=f"1:scan:{job}",
        failure_input_sha256=record.failed_attempt["input_sha256"], repair="temporary-file access repaired")))
    payload["scan_recovery"]["evidence_refs"][0]["sha256"] = hashlib.sha256(proof.read_bytes()).hexdigest()
    request = schema.model_validate(payload)
    receipt = plan_input_revision(record, request)
    revised = revise_record(record, request, receipt)
    if tamper:
        proof.write_text("recovery artifact changed between planning and commit\n")
        with pytest.raises(ValueError, match="recovery"):
            commit_input_revision(db, process_id=pid, request=request,
                                  record=revised.model_dump(mode="json"), receipt=receipt)
        assert get_revision_receipt(db, process_id=pid, request_key=request.request_key) is None
        assert get_process(db, pid)["record"]["scan_step"]["job_id"] == job
    else:
        commit_input_revision(db, process_id=pid, request=request,
                              record=revised.model_dump(mode="json"), receipt=receipt)
        restored = get_revision_receipt(ComputeDB(data_dir=tmp_path / "ledger").init(),
                                       process_id=pid, request_key=request.request_key)
        assert restored.recovery_evidence == receipt.recovery_evidence
        assert get_process(db, pid)["record"]["attempt_history"][-1]["recovery_evidence"] == receipt.recovery_evidence
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1
        assert con.execute("SELECT state FROM compute_jobs WHERE id=?", (job,)).fetchone()[0] == "failed"
