"""Read-only receipts from authoritative events; no effects and no text guessing."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from cloudra.runtime_v2.schemas import EventEnvelope

ACTIVE_CALL_STATES = {"queued", "running", "waiting"}
CALL_EVENT_TYPES = {
    "tool.requested",
    "tool.started",
    "tool.progress",
    "tool.result_recorded",
    "tool.finished",
    "tool.blocked",
    "tool.approval_requested",
    "approval.requested",
    "approval.decided",
    "approval.expired",
    "interaction.requested",
    "interaction.responded",
    "interaction.expired",
    "run.finished",
    "agent.cancelled",
}
ACTIVITY_EVENT_TYPES = CALL_EVENT_TYPES | {
    "run.started",
    "llm.request_started",
    "llm.completed",
    "llm.failed",
    "agent.completion_gate",
    "agent.state_changed",
    "agent.message_emitted",
    "agent.spawned",
    "reminder.scheduled",
    "reminder.fired",
    "reminder.cancelled",
}


def tool_receipts(
    events: Iterable[EventEnvelope], *, details: bool = True, request_event_ids: set[str] | None = None
) -> list[dict[str, Any]]:
    """Each request is an attempt, even if the wire call ID is reused.

    Events must be in project sequence order. A raw result is accepted only
    inside its own attempt; arbitrary raw-result references are never followed.
    """
    receipts: list[dict[str, Any]] = []
    current: dict[tuple, dict] = {}
    by_request: dict[str, dict] = {}
    by_run: dict[tuple, list[dict]] = defaultdict(list)
    pending: dict[str, dict] = {}

    def selected_finished():
        return (request_event_ids is not None and request_event_ids <= by_request.keys()
                and all(row["finished_at"] is not None for row in by_request.values()))

    for event in events:
        data = event.data
        kind = event.type
        run_key = (event.session_id, event.run_id)
        key = (*run_key, data.get("tool_call_id"))
        if kind == "tool.requested":
            if request_event_ids is not None and event.event_id not in request_event_ids:
                current.pop(key, None)
                continue
            row = {
                "request_event_id": event.event_id,
                "request_seq": event.session_seq,
                "project_id": event.project_id,
                "session_id": event.session_id,
                "run_id": event.run_id,
                "tool_call_id": data["tool_call_id"],
                "tool_name": data["tool_name"],
                "execution_id": data.get("execution_id"),
                "arguments": data.get("arguments_summary") if details else None,
                "effective_arguments": None,
                "status": "queued",
                "effect_state": "not_started",
                "is_success": None,
                "requested_at": event.created_at.isoformat(),
                "started_at": None,
                "finished_at": None,
                "updated_at": event.created_at.isoformat(),
                "duration_ms": None,
                "phase": None,
                "progress": [],
                "waits": [],
                "result": None,
                "result_summary": None,
                "raw_result_event_id": None,
                "result_availability": "pending",
                "error": None,
                "compute_job_ids": [],
                "artifact_ids": [],
                "events": [],
            }
            current[key] = row
            by_request[event.event_id] = row
            by_run[run_key].append(row)
            receipts.append(row)
        elif kind in {"run.finished", "agent.cancelled"}:
            affected = (
                [r for r in receipts if r["session_id"] == event.session_id]
                if kind == "agent.cancelled"
                else by_run[run_key]
            )
            for row in affected:
                if row["status"] in ACTIVE_CALL_STATES:
                    row.update(
                        status="interrupted",
                        effect_state="unknown",
                        finished_at=event.created_at.isoformat(),
                        updated_at=event.created_at.isoformat(),
                        waits=[],
                    )
                    if row["result_availability"] == "pending":
                        row["result_availability"] = "unavailable"
                    if details:
                        row["events"].append(event.model_dump(mode="json"))
            if selected_finished():
                break
            continue
        else:
            request_id = data.get("request_event_id")
            row = by_request.get(request_id) if request_id else current.get(key)
            if row is not None and (row["session_id"], row["run_id"], row["tool_call_id"]) != key:
                row = None
            if row is None and kind in {
                "approval.decided",
                "approval.expired",
                "interaction.responded",
                "interaction.expired",
            }:
                row = pending.get(data.get("approval_id") or data.get("interaction_id"))
            if row is None or kind not in CALL_EVENT_TYPES:
                continue
        row["updated_at"] = event.created_at.isoformat()
        if details:
            row["events"].append(event.model_dump(mode="json"))
        if kind == "tool.started":
            row.update(
                status="running",
                effect_state="unknown",
                phase="executing",
                started_at=event.created_at.isoformat(),
                waits=[],
            )
        elif kind == "tool.blocked":
            row.update(status="blocked", effect_state="not_started", result_summary=data.get("message"))
        elif kind == "tool.approval_requested":
            row.update(status="waiting", effect_state="not_started", result_summary=data.get("message"))
        elif kind == "tool.progress":
            row["phase"] = data["phase"]
            if details:
                row["progress"].append(event.model_dump(mode="json"))
            row["waits"] = data.get("waits", [])
            if details and data.get("effective_arguments") is not None:
                row["effective_arguments"] = data["effective_arguments"]
            row["compute_job_ids"].extend(data.get("compute_job_ids", []))
        elif kind in {"approval.requested", "interaction.requested"}:
            target = data.get("approval_id") or data.get("interaction_id")
            pending[target] = row
            row["status"] = "waiting"
            row["waits"] = [{"kind": kind.split(".")[0], "target_id": target, "event_id": event.event_id}]
        elif kind in {"approval.decided", "approval.expired", "interaction.responded", "interaction.expired"}:
            if row["status"] == "waiting":
                row.update(status="running", waits=[])
        elif kind == "tool.result_recorded":
            row.update(
                result=data["result"] if details else None,
                raw_result_event_id=event.event_id,
                result_availability="available",
                effect_state="completed",
                phase="postprocessing",
            )
            result_data = data["result"].get("data", {})
            if row["tool_name"] == "submit_compute_job" and isinstance(result_data, dict):
                job_id = result_data.get("job_id")
                if type(job_id) is int and job_id > 0:
                    row["compute_job_ids"].append(job_id)
            elif row["tool_name"] in {"ts_prepare", "ts_resume", "ts_inspect"} and isinstance(result_data, dict):
                # These are the TS view's explicit job records, never IDs
                # guessed from arbitrary JSON fields or prose.
                jobs = (result_data.get("usage") or {}).get("jobs", [])
                jobs = [*jobs, *result_data.get("waiting_for", [])]
                for job in jobs:
                    job_id = job.get("job_id")
                    if type(job_id) is int and job_id > 0:
                        row["compute_job_ids"].append(job_id)
        elif kind == "tool.finished":
            row.update(
                status=data.get("status", "unknown"),
                waits=[],
                effect_state=data.get("effect_state", row["effect_state"]),
                is_success=data.get("is_success"),
                result_summary=data.get("result_summary"),
                error=data.get("error"),
                duration_ms=data.get("duration_ms"),
                finished_at=event.created_at.isoformat(),
            )
            if row["result_availability"] == "pending":
                row["result_availability"] = "unavailable"
            if data.get("artifact_id"):
                row["artifact_ids"].append(data["artifact_id"])
        if not details:
            text = row.get("result_summary")
            if isinstance(text, str) and len(text) > 500:
                row["result_summary"] = text[:500]
                row["summary_truncated"] = True
        if selected_finished():
            break
    for row in receipts:
        row["compute_job_ids"] = list(dict.fromkeys(row["compute_job_ids"]))
    return receipts


def call_summary(row: dict) -> dict:
    """List/activity payloads omit full inputs, raw outputs and event history."""
    summary = {
        key: value
        for key, value in row.items()
        if key
        not in {
            "arguments",
            "effective_arguments",
            "result",
            "events",
            "progress",
        }
    }
    text = summary.get("result_summary")
    summary["summary_truncated"] = bool(summary.get("summary_truncated")) or (
        isinstance(text, str) and len(text) > 500
    )
    if summary["summary_truncated"]:
        summary["result_summary"] = text[:500]
    return summary


def agent_activity(agent, events: list[EventEnvelope], calls: list[dict]) -> dict:
    run_id = agent.current_run.run_id if agent.current_run else None
    state = agent.state.value
    # The caller freezes the existing agent projection with the durable
    # boundary. Historical terminal events must not clear a later live run.
    active = [r for r in calls if r["run_id"] == run_id and r["status"] in ACTIVE_CALL_STATES]
    current_events = [e for e in events if e.run_id == run_id] if run_id else []
    latest = events[-1] if events else None
    activity = "unknown"
    waits = [dict(w, request_event_id=r["request_event_id"]) for r in active for w in r["waits"]]
    if state in {"waiting_approval", "waiting_input"}:
        activity = state
    elif active:
        activity = "waiting" if waits else "running_tool"
    elif current_events:
        llm = [e for e in current_events if e.type in {"llm.request_started", "llm.completed", "llm.failed"}]
        if llm and llm[-1].type == "llm.request_started":
            activity = "waiting_model"
    if run_id is None and state not in {"waiting_approval", "waiting_input"}:
        activity = "queued" if state == "queued" else "idle"
    gates = [e for e in events if e.type == "agent.completion_gate"]
    terminal = [e for e in events if e.type in {"run.finished", "agent.cancelled"}]
    if (
        run_id is None
        and state == "succeeded"
        and gates
        and terminal
        and gates[-1].run_id == terminal[-1].run_id
        and gates[-1].data.get("action") == "wait_background"
    ):
        activity = "waiting_background"
    return {
        "session_id": agent.id,
        "display_name": agent.display_name,
        "role_id": agent.role_id,
        "parent_session_id": agent.parent_session_id,
        "state": state,
        "run_id": run_id,
        "activity": activity,
        "active_calls": [call_summary(r) for r in active],
        "waits": waits,
        "last_event": {
            "event_id": latest.event_id,
            "type": latest.type,
            "created_at": latest.created_at.isoformat(),
            "run_id": latest.run_id,
        }
        if latest
        else None,
        "last_completion_gate": gates[-1].model_dump(mode="json") if gates else None,
    }
