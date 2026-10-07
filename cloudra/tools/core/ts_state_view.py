"""Read-only projection of authoritative TS state and recorded compute facts."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cloudra.persistence.database import ComputeDB


class TsProcessView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = ""
    revision: int = 0
    run_dir: str = ""
    status: Literal["running", "waiting", "blocked", "ended", "isolated"] | None = None
    stage: str = ""
    result: dict | None = Field(default=None, description="Scientific verdict: outcome, verified and recorded reason. Tool-call success and an ended workflow do not imply scientific verification.")
    waiting_for: list[dict] = Field(default_factory=list)
    available_results: list[dict] = Field(default_factory=list)
    structures: dict[str, dict] = Field(default_factory=dict, description="Recorded full XYZ atom tables and binding facts")
    blocked: dict | None = None
    failed_attempt: dict | None = None
    next: dict = Field(default_factory=dict)
    methods: list[dict] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)
    details_path: str = ""
    export_revision: int | None = None
    message: str = ""


def build_process_view(state: dict, jobs: list[dict], *, can_write: bool) -> TsProcessView:
    """Project recorded facts only: no computation, mutation or reparsing logs."""
    active = [deepcopy(job) for job in jobs if job.get("state") not in ("done", "failed", "cancelled")]
    waiting = bool(state.get("waiting_for"))
    blocked = deepcopy(state.get("blocked"))
    terminal = state.get("terminal")
    current_stage = next((row for row in reversed(state.get("stage_records", []))
                          if row.get("stage") == state.get("stage")), {})
    detail = (blocked or {}).get("message") or current_stage.get("detail", "")
    supported = state.get("format_version") == 4
    status = "isolated" if not supported else "waiting" if active or waiting else "ended" if terminal else "blocked" if blocked else "running"
    next_action = dict(action="inspect", required_inputs=[], editable_groups=[])
    if supported and can_write:
        if active or waiting or status == "running":
            next_action["action"] = "wait_for_system"
        else:
            next_action.update(action="resume", editable_groups=list(state.get("input", {})),
                               required_inputs=list((blocked or {}).get("needs", [])))
    method_entries = []
    value = state.get("input", {})
    guess = value.get("guess") or {}
    if guess.get("kind") == "scan":
        method_entries.append(dict(purpose="scan", planned=guess.get("calculation"), actual=None, contract=None))
    elif guess.get("kind") == "xtb_path":
        method_entries.append(dict(purpose="path", planned={"engine": "xtb", "method": guess["method"], "solvation": guess.get("solvation")}, actual=None, contract=None))
    verification = value.get("verification", {})
    calculations = dict(ts_opt=value.get("ts_optimization"), frequency=verification.get("frequency"), irc=verification.get("irc"))
    for side in ("reactant", "product"):
        endpoint = verification.get(f"{side}_endpoint", {})
        calculations[f"{side}_opt"] = endpoint.get("optimization")
        calculations[f"{side}_frequency"] = endpoint.get("frequency")
    for role in ('reactant','product'):
        source = value.get('conformers', {}).get(role) or {}
        if source.get('optimization'):
            calculations['candidate_opt' if role == 'reactant' else 'product_seed_opt'] = source['optimization']
    for purpose, calculation in calculations.items():
        method_entries.append(dict(purpose=purpose, planned=calculation, actual=None, contract=None))
    for entry in method_entries:
        completed = [step for step in state.get("job_steps", []) if step.get("purpose") == entry["purpose"]]
        if completed:
            entry["actual"] = completed[-1].get("actual_calculation")
            entry["contract"] = state.get("method_checks", {}).get(completed[-1].get("input_path")) or completed[-1].get("method_contract")
    usage_jobs = []
    for job in jobs:
        start, end = job.get("start_timestamp"), job.get("end_timestamp")
        elapsed = end - start if start is not None and end is not None and 0 < start <= end else None
        cpus = job.get("req_cpus")
        usage_jobs.append(dict(job_id=job.get("job_id"), runtime_seconds=elapsed, cpus=cpus,
                               memory_mb=job.get("req_memory_mb"), measured_cpu_hours=None,
                               allocated_cpu_hours=cpus * elapsed / 3600 if elapsed is not None and cpus else None))
    available = [dict(stage=row["stage"], status=row["status"], detail=row.get("detail", ""), artifacts=row.get("artifacts", []),
                      source_input_revision=row.get("source_input_revision"))
                 for row in state.get("stage_records", []) if row.get("status") == "done"]
    available.extend(dict(stage=step['purpose'], artifacts=list(step['external_source']['artifact_hashes']),
        source_input_revision=step['source_input_revision'], source_job_id=step['external_source']['source_job_id'])
        for step in state.get('job_steps', []) if step.get('external_source'))
    current_job_ids = {step["job_id"] for step in state.get("job_steps", [])}
    available.extend(dict(stage=job["purpose"], status="done", job_id=job["job_id"],
        artifacts=[job["log_path"]], source_input_revision=job.get("source_input_revision"),
        detail="Original compute output for direct evidence submission; keep IRC sidecars in place. Job completion is not scientific verification.")
        for job in jobs if job["job_id"] in current_job_ids and job.get("state") == "done" and job.get("log_path"))
    return TsProcessView(
        run_id=state["run_id"], revision=state["revision"], run_dir=state["run_dir"], status=status,
        stage=state["stage"], result=dict(outcome=terminal, verified=terminal == "verified", reason=detail,
                                           evidence_refs=state.get("evidence_candidates", [])) if supported and terminal else None,
        waiting_for=active or deepcopy(jobs) if waiting else active, failed_attempt=state.get("failed_attempt"),
        available_results=available, structures=deepcopy(state.get('structures', {})), blocked=blocked, next=next_action, methods=method_entries,
        usage=dict(interventions=state.get("intervention_count", 0), compute_actions=len(jobs), model_calls=None, limits=value.get("execution", {}).get("limits"), **state.get("accounted_usage", {}), jobs=usage_jobs),
        details_path=str(Path(state["run_dir"]) / "process.json"), export_revision=state.get("export_revision"),
        message="Unsupported input format: automatic continuation isolated; existing compute jobs remain intact." if not supported else detail,
    )


def inspect_process(db: ComputeDB, *, project_id: str, run_id: str, workspace_dir: str, can_write: bool, owner_id: str | None = None) -> TsProcessView:
    from cloudra.services.ts_pipeline_store import read_process_snapshot

    state, jobs = read_process_snapshot(db, project_id=project_id, run_id=run_id, workspace_dir=workspace_dir)
    _attach_recorded_usage(db, state)
    details = Path(state["run_dir"]) / "process.json"
    if not details.resolve().is_relative_to(Path(workspace_dir).resolve()):
        raise ValueError("process export is outside the authorized workspace")
    try:
        state["export_revision"] = json.loads(details.read_text(encoding="utf-8")).get("revision")
    except FileNotFoundError:
        state["export_revision"] = None
    return build_process_view(state, jobs, can_write=can_write and (owner_id is None or owner_id == state.get("owner_session_id")))


def recorded_notification_view(db, state):
    from cloudra.services.ts_pipeline_store import read_process_snapshot
    current, jobs = read_process_snapshot(db, project_id=state['owner_conversation_id'], run_id=state['run_id'], workspace_dir=state['workspace_dir'])
    _attach_recorded_usage(db, current)
    return build_process_view(current, jobs, can_write=True).model_dump(mode='json')


def _attach_recorded_usage(db, state):
    from cloudra.services.exploration_budget_store import _usage
    pid = state.get('pipeline_id')
    with db.connect() as con:
        if con.execute('SELECT 1 FROM exploration_budgets WHERE process_id=?', (pid,)).fetchone():
            usage = _usage(con, pid)
            state['accounted_usage'] = dict(reserved_compute_actions=usage.compute_actions, model_calls=usage.model_calls)
