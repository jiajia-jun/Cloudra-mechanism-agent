"""Read-only projection of authoritative TS state and recorded compute facts."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cloudra.persistence.database import ComputeDB


class TsProcessView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    revision: int
    run_dir: str
    status: Literal["running", "waiting", "blocked", "ended", "isolated"]
    stage: str
    result: dict | None
    waiting_for: list[dict]
    available_results: list[dict]
    blocked: dict | None
    next: dict
    methods: list[dict]
    usage: dict
    details_path: str
    export_revision: int | None = None
    message: str = ""


def build_process_view(state: dict, jobs: list[dict], *, can_write: bool) -> TsProcessView:
    """Project recorded facts only: no computation, mutation or reparsing logs."""
    active = [deepcopy(job) for job in jobs if job.get("state") not in ("done", "failed", "cancelled")]
    waiting = bool(state.get("waiting_for"))
    blocked = deepcopy(state.get("blocked"))
    terminal = state.get("terminal")
    supported = state.get("format_version") == 3
    status = "isolated" if not supported else "waiting" if active or waiting else "ended" if terminal else "blocked" if blocked else "running"
    next_action = dict(action="inspect", required_inputs=[], recovery_required=False, editable_groups=[])
    if supported and can_write:
        if active or waiting or status == "running":
            next_action["action"] = "wait_for_system"
        else:
            next_action.update(action="resume", editable_groups=list(state.get("input", {})),
                               required_inputs=list((blocked or {}).get("needs", [])),
                               recovery_required=bool(blocked and blocked.get("failure_class") not in (
                                   "missing_input", "permission_denied", "method_contract", "identity_mismatch", "mapping_required")))
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
    for purpose, calculation in calculations.items():
        method_entries.append(dict(purpose=purpose, planned=calculation, actual=None, contract=None))
    for entry in method_entries:
        completed = [step for step in state.get("job_steps", []) if step.get("purpose") == entry["purpose"]]
        if completed:
            entry["actual"] = completed[-1].get("actual_calculation")
            entry["contract"] = completed[-1].get("method_contract")
    usage_jobs = []
    for job in jobs:
        start, end = job.get("start_timestamp"), job.get("end_timestamp")
        elapsed = end - start if start is not None and end is not None and 0 < start <= end else None
        cpus = job.get("req_cpus")
        usage_jobs.append(dict(job_id=job.get("job_id"), runtime_seconds=elapsed, cpus=cpus,
                               memory_mb=job.get("req_memory_mb"), measured_cpu_hours=None,
                               allocated_cpu_hours=cpus * elapsed / 3600 if elapsed is not None and cpus else None))
    available = [dict(stage=row["stage"], artifacts=row.get("artifacts", []),
                      source_input_revision=row.get("source_input_revision"))
                 for row in state.get("stage_records", []) if row.get("status") == "done"]
    return TsProcessView(
        run_id=state["run_id"], revision=state["revision"], run_dir=state["run_dir"], status=status,
        stage=state["stage"], result=dict(outcome=terminal, evidence_refs=state.get("evidence_candidates", [])) if terminal else None,
        waiting_for=active or deepcopy(jobs) if waiting else active,
        available_results=available, blocked=blocked, next=next_action, methods=method_entries,
        usage=dict(interventions=state.get("intervention_count", 0), jobs=usage_jobs),
        details_path=str(Path(state["run_dir"]) / "process.json"), export_revision=state.get("export_revision"),
        message="Unsupported input format: automatic continuation isolated; existing compute jobs remain intact." if not supported else "",
    )


def inspect_process(db: ComputeDB, *, project_id: str, run_id: str, workspace_dir: str, can_write: bool) -> TsProcessView:
    from cloudra.services.ts_pipeline_store import read_process_snapshot

    state, jobs = read_process_snapshot(db, project_id=project_id, run_id=run_id, workspace_dir=workspace_dir)
    details = Path(state["run_dir"]) / "process.json"
    if not details.resolve().is_relative_to(Path(workspace_dir).resolve()):
        raise ValueError("process export is outside the authorized workspace")
    try:
        state["export_revision"] = json.loads(details.read_text(encoding="utf-8")).get("revision")
    except FileNotFoundError:
        state["export_revision"] = None
    return build_process_view(state, jobs, can_write=can_write)
