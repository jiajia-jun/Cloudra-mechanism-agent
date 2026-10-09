import hashlib
import json
from copy import deepcopy

import pytest

from cloudra.persistence.database import ComputeDB
from tests.test_ts_inputs import input_payload
from tests.test_ts_pipeline_store import job_payload


def process_fixture(tmp_path, *, status="blocked"):
    from cloudra.services.ts_pipeline_store import create_process

    db = ComputeDB(data_dir=tmp_path).init()
    workspace = tmp_path / "workspace"
    run_dir = workspace / "ts" / "ts_0001"
    run_dir.mkdir(parents=True)
    inputs = input_payload()
    pid = create_process(db, request_key="inspect", payload=dict(project_id='project', owner_id='owner',
        workspace_dir=str(workspace), input=inputs))["process_id"]
    record = dict(format_version=5, pipeline_id=pid, run_id="ts_0001", revision=7, declaration_revision=1,
                  run_dir=str(run_dir), workspace_dir=str(workspace), owner_conversation_id="project", owner_session_id="owner",
                  stage="guess", input=inputs, intervention_count=2, evidence_candidates=["scan.log"],
                  job_steps=[], stage_records=[], blocked={"failure_class": "scan_failed", "message": "native first point failed",
                  "stage": "guess", "needs": ["guess"], "atom_details": []} if status == "blocked" else None,
                  terminal="search_failed" if status == "ended" else None, waiting_for="job:1" if status == "waiting" else "")
    (run_dir / "process.json").write_text(json.dumps(dict(record, revision=3)))
    with db.connect() as con:
        con.execute("UPDATE ts_pipeline_processes SET record=?,revision=9,status=? WHERE process_id=?",
                    (json.dumps(record), status, pid))
    return db, pid, workspace, record


def test_rewrite_recovery_blocker_never_exposes_export_as_current(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view

    _db, _pid, _workspace, record = process_fixture(tmp_path)
    record['export_revision'] = record['revision']
    record['source_rewrite_recovery_blocked'] = True
    record['blocked'] = dict(failure_class='canonical_source_recovery_blocked',
                             stage='build', message='Current sources cannot be recovered safely',
                             needs=['conformers.reactant'])
    view = build_process_view(record, [], can_write=True)
    assert view.run_id == record['run_id'] and view.revision == record['revision']
    assert view.status == 'blocked' and view.result is None
    assert view.details_path == ''
    assert view.next['required_inputs'] == ['conformers.reactant']
    assert view.next['action'] == 'resolve_source_conflict'


@pytest.mark.parametrize("status", ["blocked", "waiting", "ended"])
def test_inspect_has_no_state_or_compute_side_effects(tmp_path, monkeypatch, status):
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core.ts_state_view import inspect_process

    db, pid, workspace, record = process_fixture(tmp_path, status=status)
    def no_advance(*args, **kwargs):
        raise AssertionError("inspect must not advance")
    monkeypatch.setattr("cloudra.tools.core.ts_pipeline_driver.advance_process", no_advance)
    before = deepcopy(get_process(db, pid))
    exported = (workspace / "ts" / record["run_id"] / "process.json").read_bytes()
    view = inspect_process(db, project_id="project", run_id=record["run_id"], workspace_dir=str(workspace), can_write=False)
    assert view.revision == 9
    assert get_process(db, pid) == before
    assert (workspace / "ts" / record["run_id"] / "process.json").read_bytes() == exported
    assert view.usage["interventions"] == 2
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 0


def test_readonly_peer_can_inspect_same_project_but_not_foreign_project(tmp_path):
    from cloudra.tools.core.ts_state_view import inspect_process

    db, _, workspace, record = process_fixture(tmp_path)
    assert inspect_process(db, project_id="project", run_id=record["run_id"], workspace_dir=str(workspace), can_write=False).run_id == "ts_0001"
    with pytest.raises(ValueError, match="authorized project"):
        inspect_process(db, project_id="foreign", run_id=record["run_id"], workspace_dir=str(workspace), can_write=False)


def test_inspect_reports_authoritative_jobs_and_export_revision(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job
    from cloudra.tools.core.ts_state_view import inspect_process

    db, pid, workspace, record = process_fixture(tmp_path, status="waiting")
    job = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key="scan", attempt=1, job_payload=job_payload())
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
    view = inspect_process(db, project_id="project", run_id=record["run_id"], workspace_dir=str(workspace), can_write=True)
    assert view.waiting_for[0]["state"] == "done"
    assert view.waiting_for[0]["job_id"] == job
    assert view.export_revision == 3
    assert view.revision == 10
    assert view.next["action"] == "wait_for_system"


def test_next_is_state_and_permission_dependent(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view

    _, _, _, record = process_fixture(tmp_path)
    readonly = build_process_view(record, [], can_write=False)
    assert readonly.next["action"] == "inspect"
    mutable = build_process_view(record, [], can_write=True)
    assert mutable.next["action"] == "resume"
    assert mutable.next["required_inputs"] == ["guess"]
    assert "recovery_required" not in mutable.next
    active = build_process_view(record, [{"job_id": 1, "state": "ready"}], can_write=True)
    assert active.next["action"] == "wait_for_system"
    missing = dict(record, blocked=dict(record["blocked"], failure_class="missing_input", needs=["verification.irc"]))
    assert "recovery_required" not in build_process_view(missing, [], can_write=True).next


def test_inspect_is_registered_as_readonly_evidence():
    from cloudra.tools.capabilities import role_hidden_tools, supervisor_access_for
    from cloudra.tools.Chemtool.ts_search_process import TsInspect

    assert not TsInspect().is_write()
    assert "ts_inspect" not in role_hidden_tools("explorer")
    assert supervisor_access_for("ts_inspect") == "evidence_read"


@pytest.mark.parametrize("outcome,verified", [
    ("verified", True), ("candidate_only", False),
    ("search_failed", False), ("invalid_input", False),
])
def test_terminal_tool_return_exposes_scientific_verdict_and_recorded_reason(tmp_path, outcome, verified):
    from cloudra.tools.Chemtool.ts_search_process import _to_output
    from cloudra.tools.core.ts_process import _terminal
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path)
    _terminal(record, "verdict", outcome, "Recorded scientific judgement for this attempt")
    output = _to_output(record)
    assert output.is_success  # Successful reading is separate from scientific qualification.
    assert output.status == "ended"
    assert output.result["outcome"] == outcome
    assert output.result["verified"] is verified
    assert output.result["reason"] == "Recorded scientific judgement for this attempt"
    assert output.message == "Recorded scientific judgement for this attempt"
    assert output.available_results[-1]["detail"] == "Recorded scientific judgement for this attempt"
    assert output.available_results[-1]["status"] == "done"


def test_blocked_summary_returns_current_block_reason_without_claiming_a_verdict(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view

    _, _, _, record = process_fixture(tmp_path)
    record["stage_records"] = [{"stage": "verdict", "status": "done", "detail": "Previous attempt passed", "artifacts": []}]
    view = build_process_view(record, [], can_write=True)
    assert view.status == "blocked" and view.result is None
    assert view.message == "native first point failed"


def test_available_stage_results_preserve_recorded_details_without_labeling_jobs_verified(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view

    _, _, _, record = process_fixture(tmp_path, status="waiting")
    record["stage"] = "refine"
    record["stage_records"] = [{"stage": "refine", "status": "waiting", "detail": "Waiting for frequency evidence", "artifacts": []},
        {"stage": "guess", "status": "done", "detail": "Candidate only; formal verification remains required", "artifacts": ["guess.xyz"]}]
    view = build_process_view(record, [], can_write=False)
    assert view.result is None
    assert view.message == "Waiting for frequency evidence"
    assert view.available_results[0]["detail"] == "Candidate only; formal verification remains required"
    assert view.available_results[0]["artifacts"] == ["guess.xyz"]


@pytest.mark.parametrize('format_version', [3, 4])
def test_isolated_input_format_cannot_claim_scientific_verification(tmp_path, format_version):
    from cloudra.tools.core.ts_state_view import build_process_view

    _, _, _, record = process_fixture(tmp_path, status="ended")
    record.update(format_version=format_version, terminal="verified")
    view = build_process_view(record, [], can_write=False)
    assert view.status == "isolated"
    assert view.result is None


def test_inspect_exposes_completed_current_job_logs_for_direct_evidence_submission(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view
    _, _, _, state = process_fixture(tmp_path, status="ended")
    state["terminal"] = "candidate_only"
    state["job_steps"] = [{"purpose": "irc", "job_id": 674}]
    jobs = [dict(job_id=674, purpose="irc", state="done", log_path="/workspace/irc/.cloudra/calc-674.out.log"),
            dict(job_id=600, purpose="irc", state="done", log_path="/workspace/obsolete.out")]
    view = build_process_view(state, jobs, can_write=False)
    evidence = [row for row in view.available_results if row.get("job_id") == 674]
    assert evidence and evidence[0]["artifacts"] == ["/workspace/irc/.cloudra/calc-674.out.log"]
    assert not any("/workspace/obsolete.out" in row.get("artifacts", []) for row in view.available_results)
    assert not view.result["verified"]


def test_inspect_resolves_native_stdout_from_completed_ledger_job(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job
    from cloudra.tools.core.ts_state_view import inspect_process
    db, pid, workspace, state = process_fixture(tmp_path, status="ended")
    source = workspace / "irc.inp"
    source.write_text("synthetic IRC input")
    job = job_payload()
    job["path"] = str(source)
    jid = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key="irc", attempt=1,
                         job_payload=job)
    captured = workspace / ".cloudra" / f"calc-{jid}.out.log"
    captured.parent.mkdir()
    captured.write_text("ORCA TERMINATED NORMALLY")
    state["job_steps"] = [{"purpose": "irc", "job_id": jid}]
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (jid,))
        con.execute("UPDATE ts_pipeline_processes SET record=? WHERE process_id=?", (json.dumps(state), pid))
    view = inspect_process(db, project_id="project", run_id=state["run_id"], workspace_dir=str(workspace), can_write=False)
    evidence = next(row for row in view.available_results if row.get("job_id") == jid)
    assert evidence["artifacts"] == [str(captured)]
    assert captured.read_text() == "ORCA TERMINATED NORMALLY"
    assert not view.result["verified"]


def canonical_table_fixture(workspace):
    xyz = workspace / "reactant.xyz"
    xyz.write_text("3\ncanonical current source\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n")
    digest = hashlib.sha256(xyz.read_bytes()).hexdigest()
    return dict(role="reactant", input_revision=2, xyz_path=str(xyz),
                xyz_sha256=digest, index_base=1,
                atoms=[dict(number=1, symbol="O"), dict(number=2, symbol="H"), dict(number=3, symbol="H")],
                normalization=dict(status="applied", input_revision=2, paths={"xyz": str(xyz)},
                                   canonical_hashes={"xyz": digest},
                                   source_to_canonical=[3, 1, 2], canonical_to_source=[2, 3, 1]))


def test_inspect_current_canonical_atoms_come_from_ledger_even_when_export_has_raw_order(tmp_path):
    from cloudra.tools.core.ts_state_view import inspect_process

    db, pid, workspace, state = process_fixture(tmp_path)
    state["declaration_revision"] = 2
    state["structures"] = {"reactant": canonical_table_fixture(workspace)}
    raw_export = deepcopy(state)
    raw_export["revision"] = 3
    raw_export["structures"]["reactant"]["atoms"] = [dict(number=1, symbol="H"), dict(number=2, symbol="O"), dict(number=3, symbol="H")]
    (workspace / "ts" / state["run_id"] / "process.json").write_text(json.dumps(raw_export))
    with db.connect() as con:
        con.execute("UPDATE ts_pipeline_processes SET record=? WHERE process_id=?", (json.dumps(state), pid))
    view = inspect_process(db, project_id="project", run_id=state["run_id"], workspace_dir=str(workspace), can_write=False)
    table = view.structures["reactant"]
    actual_symbols = [row.split()[0] for row in (workspace / "reactant.xyz").read_text().splitlines()[2:]]
    assert [(row["number"], row["symbol"]) for row in table["atoms"]] == [(1, "O"), (2, "H"), (3, "H")]
    assert [row["symbol"] for row in table["atoms"]] == actual_symbols
    assert table["normalization"]["paths"] == {"xyz": str(workspace / "reactant.xyz")}
    assert table["normalization"]["status"] == "applied"
    assert view.revision == 9 and view.export_revision == 3
    assert view.details_path == ""


@pytest.mark.parametrize("export_revision", [3, None, 9])
def test_only_current_export_can_be_reported_as_current_details_path(tmp_path, export_revision):
    from cloudra.tools.core.ts_state_view import inspect_process

    db, _, workspace, state = process_fixture(tmp_path)
    export = workspace / "ts" / state["run_id"] / "process.json"
    if export_revision is None:
        export.unlink()
    else:
        export.write_text(json.dumps(dict(state, revision=export_revision)))
    view = inspect_process(db, project_id="project", run_id=state["run_id"], workspace_dir=str(workspace), can_write=False)
    assert view.revision == 9 and view.export_revision == export_revision
    assert view.details_path == (str(export) if export_revision == 9 else "")


def test_recorded_notification_reports_current_atoms_and_actual_stale_export_revision(tmp_path):
    from cloudra.tools.core.ts_state_view import recorded_notification_view

    db, pid, workspace, state = process_fixture(tmp_path)
    state["structures"] = {"reactant": canonical_table_fixture(workspace)}
    with db.connect() as con:
        con.execute("UPDATE ts_pipeline_processes SET record=? WHERE process_id=?", (json.dumps(state), pid))
    view = recorded_notification_view(db, state)
    assert view["revision"] == 9 and view["export_revision"] == 3
    assert view["details_path"] == ""
    assert [(row["number"], row["symbol"]) for row in view["structures"]["reactant"]["atoms"]] == [
        (1, "O"), (2, "H"), (3, "H"),
    ]


def test_unapplied_normalization_cannot_be_reported_as_a_current_atom_table(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view

    _, _, workspace, state = process_fixture(tmp_path)
    state["structures"] = {"reactant": canonical_table_fixture(workspace)}
    state["structures"]["reactant"]["normalization"]["status"] = "pending"
    view = build_process_view(state, [], can_write=True)
    assert view.structures == {}
    assert view.run_id == state["run_id"] and view.revision == state["revision"]
    assert view.blocked["failure_class"] == "canonical_structure_unavailable"
    assert view.blocked["needs"] == ["conformers.reactant"]
    assert view.next["required_inputs"] == ["conformers.reactant"]
    assert view.result is None


@pytest.mark.parametrize("drift", ["current_source", "built_snapshot", "missing_current_source"])
def test_changed_canonical_file_cannot_be_reported_as_applied_current_atoms(tmp_path, drift):
    from cloudra.tools.core.ts_state_view import build_process_view

    _, _, workspace, state = process_fixture(tmp_path)
    state["structures"] = {"reactant": canonical_table_fixture(workspace)}
    table = state["structures"]["reactant"]
    source = workspace / "reactant.xyz"
    snapshot = workspace / "seed.xyz"
    snapshot.write_bytes(source.read_bytes())
    table["xyz_path"] = str(snapshot)
    if drift == "missing_current_source":
        source.unlink()
    else:
        changed = source if drift == "current_source" else snapshot
        changed.write_text("3\nraw order changed\nH .96 0 0\nO 0 0 0\nH -.24 .93 0\n")
    product_dir = workspace / "product"
    product_dir.mkdir()
    state["structures"]["product"] = canonical_table_fixture(product_dir)
    state["structures"]["product"]["role"] = "product"
    before = deepcopy(state)
    view = build_process_view(state, [], can_write=True)
    assert "reactant" not in view.structures and "product" in view.structures
    assert view.run_id == state["run_id"] and view.revision == state["revision"]
    assert view.status == "blocked" and view.result is None
    assert view.blocked["failure_class"] == "canonical_structure_unavailable"
    assert view.blocked["needs"] == ["conformers.reactant"]
    assert view.next["required_inputs"] == ["conformers.reactant"]
    assert state == before


def test_canonical_source_blocker_preserves_authoritative_revision_during_active_job(tmp_path):
    from cloudra.tools.core.ts_state_view import inspect_process

    db, pid, workspace, state = process_fixture(tmp_path, status="waiting")
    state["structures"] = {"reactant": canonical_table_fixture(workspace)}
    (workspace / "reactant.xyz").unlink()
    with db.connect() as con:
        con.execute("UPDATE ts_pipeline_processes SET record=? WHERE process_id=?", (json.dumps(state), pid))
    view = inspect_process(db, project_id="project", run_id=state["run_id"], workspace_dir=str(workspace), can_write=True)
    assert view.structures == {}
    assert view.revision == 9 and view.export_revision == 3
    assert view.status == "waiting" and view.next["action"] == "wait_for_system"
    assert view.blocked["needs"] == ["conformers.reactant"]
    assert view.result is None


def test_retained_prior_revision_artifacts_are_identified_as_historical(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view

    _, _, _, state = process_fixture(tmp_path)
    state["declaration_revision"] = 2
    state["stage_records"] = [dict(stage="guess", status="done", artifacts=["old_guess.xyz"], source_input_revision=1),
                              dict(stage="build", status="done", artifacts=["current_seed.xyz"], source_input_revision=2)]
    state["job_steps"] = [dict(purpose="ts_opt", job_id=7, source_input_revision=1),
                          dict(purpose="irc", job_id=None, source_input_revision=1, external_source=dict(
                              source_job_id=8, artifact_hashes={"original_irc.out": "immutable"}))]
    jobs = [dict(job_id=7, purpose="ts_opt", state="done", source_input_revision=1, log_path="original_ts.out")]
    view = build_process_view(state, jobs, can_write=False)
    assert [(row["artifacts"], row["input_revision_relation"]) for row in view.available_results] == [
        (["old_guess.xyz"], "historical"), (["current_seed.xyz"], "current"),
        (["original_irc.out"], "historical"), (["original_ts.out"], "historical"),
    ]
