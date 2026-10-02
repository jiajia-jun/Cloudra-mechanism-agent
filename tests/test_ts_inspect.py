import json
from copy import deepcopy

import pytest

from cloudra.persistence.database import ComputeDB
from tests.test_ts_inputs import input_payload
from tests.test_ts_pipeline_store import job_payload, payload


def process_fixture(tmp_path, *, status="blocked"):
    from cloudra.services.ts_pipeline_store import create_process

    db = ComputeDB(data_dir=tmp_path).init()
    workspace = tmp_path / "workspace"
    run_dir = workspace / "ts" / "ts_0001"
    run_dir.mkdir(parents=True)
    pid = create_process(db, request_key="inspect", payload=payload(workspace_dir=str(workspace)))["process_id"]
    record = dict(format_version=3, pipeline_id=pid, run_id="ts_0001", revision=7, declaration_revision=1,
                  run_dir=str(run_dir), workspace_dir=str(workspace), owner_conversation_id="project", owner_session_id="owner",
                  stage="guess", input=input_payload(), intervention_count=2, evidence_candidates=["scan.log"],
                  job_steps=[], stage_records=[], blocked={"failure_class": "scan_failed", "message": "native first point failed",
                  "stage": "guess", "needs": ["guess"], "atom_details": []} if status == "blocked" else None,
                  terminal="search_failed" if status == "ended" else None, waiting_for="job:1" if status == "waiting" else "")
    (run_dir / "process.json").write_text(json.dumps(dict(record, revision=3)))
    with db.connect() as con:
        con.execute("UPDATE ts_pipeline_processes SET record=?,revision=9,status=? WHERE process_id=?",
                    (json.dumps(record), status, pid))
    return db, pid, workspace, record


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
    assert not mutable.next["recovery_required"]  # No bound failed attempt exists in this fixture.
    active = build_process_view(record, [{"job_id": 1, "state": "ready"}], can_write=True)
    assert active.next["action"] == "wait_for_system"
    missing = dict(record, blocked=dict(record["blocked"], failure_class="missing_input", needs=["verification.irc"]))
    assert not build_process_view(missing, [], can_write=True).next["recovery_required"]


def test_inspect_is_registered_as_readonly_evidence():
    from cloudra.tools.capabilities import role_hidden_tools, supervisor_access_for
    from cloudra.tools.Chemtool.ts_search_process import TsInspect

    assert not TsInspect().is_write()
    assert "ts_inspect" not in role_hidden_tools("explorer")
    assert supervisor_access_for("ts_inspect") == "evidence_read"
