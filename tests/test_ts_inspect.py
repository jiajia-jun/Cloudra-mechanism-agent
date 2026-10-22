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
    record = dict(format_version=7, pipeline_id=pid, run_id="ts_0001", revision=7, declaration_revision=1,
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


def test_stale_export_never_replaces_the_current_ledger_block_reason(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view
    _db, _pid, _workspace, record = process_fixture(tmp_path)
    record['export_revision'] = 3
    view = build_process_view(record, [], can_write=True)
    assert view.run_id == record['run_id'] and view.revision == record['revision']
    assert view.status == 'blocked' and view.result is None
    assert view.details_path == ''
    assert view.next['required_inputs'] == ['guess']
    assert view.next['action'] == 'resume'


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
    assert active.next["action"] == "resume"
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


def imported_structures(workspace):
    from cloudra.tools.core.molecule import read_molecule
    from cloudra.tools.core.reaction_state import ReactionStructures
    source = workspace / 'reactant.xyz'
    source.write_text('3\nimported source\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n')
    molecule = read_molecule(input_path=str(source), input_format='xyz')
    return ReactionStructures(reactant=molecule).model_dump(mode='json')


@pytest.mark.usefixtures("rdkit_chemistry")
def test_inspect_current_atoms_come_from_owned_molecule_even_when_export_has_old_order(tmp_path):
    from cloudra.tools.core.molecule import renumber_atoms
    from cloudra.tools.core.reaction_state import ReactionStructures
    from cloudra.tools.core.ts_state_view import inspect_process
    db, pid, workspace, state = process_fixture(tmp_path)
    state['structures'] = imported_structures(workspace)
    raw_export = deepcopy(state)
    raw_export['revision'] = 3
    raw = ReactionStructures.model_validate(state['structures'])
    raw.reactant = renumber_atoms(raw.reactant, [1, 0, 2])
    raw_export['structures'] = raw.model_dump(mode='json')
    (workspace / 'ts' / state['run_id'] / 'process.json').write_text(json.dumps(raw_export))
    with db.connect() as con:
        con.execute('UPDATE ts_pipeline_processes SET record=? WHERE process_id=?', (json.dumps(state), pid))
    view = inspect_process(db, project_id='project', run_id=state['run_id'], workspace_dir=str(workspace), can_write=False)
    assert [(row['number'], row['symbol']) for row in view.structures['reactant']['atoms']] == [
        (1, 'O'), (2, 'H'), (3, 'H')]
    assert view.revision == 9 and view.export_revision == 3
    assert view.details_path == ''


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


@pytest.mark.usefixtures("rdkit_chemistry")
def test_recorded_notification_uses_owned_atoms_and_actual_stale_export_revision(tmp_path):
    from cloudra.tools.core.ts_state_view import recorded_notification_view
    db, pid, workspace, state = process_fixture(tmp_path)
    state['structures'] = imported_structures(workspace)
    with db.connect() as con:
        con.execute('UPDATE ts_pipeline_processes SET record=? WHERE process_id=?', (json.dumps(state), pid))
    view = recorded_notification_view(db, state)
    assert view['revision'] == 9 and view['export_revision'] == 3
    assert view['details_path'] == ''
    assert [row['symbol'] for row in view['structures']['reactant']['atoms']] == ['O', 'H', 'H']


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize('change', ['coordinates', 'missing'])
def test_later_source_file_changes_do_not_rewrite_current_atom_view(tmp_path, change):
    from cloudra.tools.core.ts_state_view import build_process_view
    _, _, workspace, state = process_fixture(tmp_path)
    state['structures'] = imported_structures(workspace)
    source = workspace / 'reactant.xyz'
    if change == 'missing':
        source.unlink()
    else:
        source.write_text('3\nchanged raw file order\nH .96 0 0\nO 0 0 0\nH -.24 .93 0\n')
    before = deepcopy(state)
    view = build_process_view(state, [], can_write=True)
    assert [row['symbol'] for row in view.structures['reactant']['atoms']] == ['O', 'H', 'H']
    assert view.blocked['failure_class'] == 'scan_failed'
    assert state == before


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


@pytest.mark.asyncio
@pytest.mark.parametrize("model_calls", [0, 2])
async def test_inspect_tool_renders_real_configured_budget_usage(tmp_path, model_calls):
    import asyncio

    from cloudra.services.exploration_budget_store import (
        CostEstimate,
        ExplorationBudget,
        configure_budget,
        reserve_actions,
    )
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.Chemtool.ts_search_process import TsInspect, TsInspect_input_schema
    from tests.test_ts_search_process_tools import owned_tool

    def configured_process():
        db, pid, workspace, record = process_fixture(tmp_path)
        configure_budget(db, process_id=pid, project_id="project", owner_id="owner",
                         budget=ExplorationBudget(source="explicit_user", max_compute_actions=4, max_model_calls=4))
        reserve_actions(db, process_id=pid, decision_id="fixture-usage", estimates=[
            CostEstimate(action_key="frequency", action_kind="frequency", source="fixture"),
            *[CostEstimate(action_key=f"model:{i}", action_kind="model", source="fixture")
              for i in range(model_calls)],
        ])
        return db, workspace, record

    db, workspace, record = await asyncio.to_thread(configured_process)
    with use_pipeline_database(db):
        output = await owned_tool(TsInspect, workspace=workspace).tool_call(
            TsInspect_input_schema(run_id=record["run_id"]), None,
        )
    receipt = output.model_dump(mode="json")
    assert receipt["is_success"] is True
    assert receipt["usage"]["model_calls"] == model_calls
    assert receipt["usage"]["reserved_compute_actions"] == 1
    assert receipt["usage"]["compute_actions"] == 0
    assert receipt["usage"]["jobs"] == []
    assert receipt["usage"]["interventions"] == 2
