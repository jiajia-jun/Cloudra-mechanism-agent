#!/usr/bin/env python3
"""Audit original structured stop decisions; report candidates, never infer error from prose."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

EVIDENCE = {"dag_bind_evidence", "dag_submit_species_evidence", "dag_submit_step_evidence"}
MUTATIONS = EVIDENCE | {
    "dag_review_evidence", "dag_review_call", "dag_review_species", "dag_review_step",
    "dag_propose_mechanism", "dag_accept_mechanism", "dag_remove_species", "dag_remove_step",
    "write", "edit", "bash", "ts_prepare", "ts_resume", "ts_stop", "submit_compute_job",
}


def locate(event: dict) -> dict:
    return {key: event[key] for key in ("event_id", "project_id", "session_id", "run_id", "seq", "session_seq", "rowid", "type")}


def first_after(events: list[dict], event: dict, *, same_run: bool = False) -> dict | None:
    return next((item for item in events if item["rowid"] > event["rowid"]
                 and item["session_id"] == event["session_id"]
                 and (not same_run or item["run_id"] == event["run_id"])), None)


def stop_disposition(event: dict, progress: dict) -> tuple[str, str]:
    args = event["data"].get("arguments_summary") or {}
    if "delivery_disposition" in args:
        return args["delivery_disposition"], "explicit_arguments"
    effective = progress.get(event["event_id"])
    if effective is not None:
        return effective["data"]["effective_arguments"].get("delivery_disposition", "unknown"), "recorded_effective_arguments"
    return "unknown", "unknown"


def audit(source_root: Path, case_file: Path, output: Path) -> dict:
    source_root = source_root.resolve()
    report_cases, task_map = defaultdict(list), {}
    with case_file.open() as source:
        for line in source:
            case = json.loads(line)
            if case.get("dataset") != "formal48_original":
                continue
            key = (case["arm"], case["round"], case["project_id"])
            task_map[key] = case["task"]
            if case["tool_name"] == "dag_delivery_report":
                report_cases[(case["arm"], case["round"], case["session_id"])].append(case)
    result = {
        "dataset": "formal48_original", "source_root": str(source_root), "case_file": str(case_file.resolve()),
        "scope": "Historical structured report/stop consistency candidates, not scientific acceptance, success rate, or a claim the model could not read DAGs.",
        "method": "Exact tool names, role_id, effective_arguments, enumerated dispositions and completion-gate actions; no natural-language matching.",
        "source_schema": {
            "stop_current_source": "cloudra/tools/Stoptool/stop_tool.py:9-37; reason:str='', final_answer:str='', delivery_disposition:complete|partial|user_terminated='complete'; receipt request_received is not completion.",
            "ts_stop_current_source": "cloudra/tools/Chemtool/ts_search_process.py:32-43,189-227; run_id and nonblank reason; workflow control, not global completion or scientific failure.",
            "historical_default_policy": "Omitted stop disposition is classified only from recorded tool.progress.effective_arguments; never inferred from current source defaults.",
            "historical_field_keys": defaultdict(set),
        },
        "stop_calls": [], "ts_stop_calls": [], "incomplete_report_then_first_action_stop": [],
        "rejected_stop_followups": [], "evaluation_labels_assigned": False,
        "limits": [
            "Any intervening other-agent tool activity is conservatively marked unknown state change; it is not asserted to be an actual mutation.",
            "Explicit evidence-submission calls show an attempt to supply material, not that the evidence is scientifically valid.",
            "Absence of a structured evidence call does not exclude manual, shell, external, or unlogged work.",
            "Context projection is preserved evidence; provider wire delivery remains unknown.",
            "run.finished outcome=succeeded is runtime completion, not scientific success; partial, waits, and review decisions remain distinct.",
        ],
    }
    enums = Counter()
    for database in sorted(source_root.glob("*/r*/runtime/runtime-v2.db")):
        arm, round_name = database.relative_to(source_root).parts[:2]
        roles, requests, progress, gates, feedback, finishes, returns = {}, [], {}, [], [], [], {}
        with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.row_factory = sqlite3.Row
            for row in connection.execute("SELECT rowid,event_id,project_id,session_id,run_id,seq,session_seq,type,data FROM events ORDER BY rowid"):
                data, kind = json.loads(row["data"]), row["type"]
                event = {**dict(row), "data": data}
                if kind == "agent.spawned":
                    roles[data["id"]] = {"role_id": data.get("role_id", "unknown"), "parent_session_id": data.get("parent_session_id"), "spawn_event_id": row["event_id"]}
                elif kind == "tool.requested":
                    requests.append(event)
                    if data.get("tool_name") in {"stop", "ts_stop"}:
                        result["source_schema"]["historical_field_keys"][data["tool_name"] + ".arguments"].update((data.get("arguments_summary") or {}).keys())
                elif kind == "tool.progress" and data.get("tool_name") in {"stop", "ts_stop"}:
                    if data.get("effective_arguments") is not None:
                        progress[data.get("request_event_id")] = event
                        result["source_schema"]["historical_field_keys"][data["tool_name"] + ".effective_arguments"].update(data["effective_arguments"])
                elif kind == "tool.result_recorded":
                    returns[data.get("request_event_id")] = event
                    if data.get("tool_name") in {"stop", "ts_stop"}:
                        payload = (data.get("result") or {}).get("data") or {}
                        result["source_schema"]["historical_field_keys"][data["tool_name"] + ".output"].update(payload)
                elif kind == "agent.completion_gate":
                    gates.append(event)
                elif kind == "agent.message_injected" and data.get("sender") == "completion_gate":
                    feedback.append(event)
                elif kind == "run.finished":
                    finishes.append(event)
                    enums[("run.finished.outcome", str(data.get("outcome")), str(data.get("failure_kind")))] += 1
        stops = [event for event in requests if event["data"].get("tool_name") == "stop"]
        for event in (item for item in requests if item["data"].get("tool_name") in {"stop", "ts_stop"}):
            data, session = event["data"], event["session_id"]
            role = roles.get(session, {"role_id": "unknown", "parent_session_id": None})
            category = ("coordinator_global_delivery" if role["role_id"] == "coordinator" else
                        "supervisor_run_end" if role["role_id"] == "supervisor" else
                        "child_subtask_run_end" if role.get("parent_session_id") else
                        "unknown" if role["role_id"] == "unknown" else "specialized_or_peer_run_end")
            args = data.get("arguments_summary") or {}
            effective = progress.get(event["event_id"])
            disposition, disposition_source = stop_disposition(event, progress)
            record = {"arm": arm, "round": round_name, "task": task_map.get((arm, round_name, event["project_id"]), "unknown"),
                      "database": str(database), "source": locate(event), "role": role, "scope_category": category,
                      "tool_name": data["tool_name"], "tool_call_id": data.get("tool_call_id"),
                      "explicit_disposition": args.get("delivery_disposition", "omitted"),
                      "effective_disposition": disposition, "disposition_source": disposition_source,
                      "effective_arguments_event_id": effective["event_id"] if effective else "unknown"}
            enums[(data["tool_name"], category if data["tool_name"] == "stop" else "ts_workflow_control_not_delivery", disposition)] += 1
            if data["tool_name"] == "ts_stop":
                record["scope_category"] = "ts_workflow_control_not_delivery"
                result["ts_stop_calls"].append(record)
                continue
            next_stop = first_after(stops, event)
            gate = first_after(gates, event, same_run=True)
            if gate is not None and next_stop is not None and gate["rowid"] > next_stop["rowid"]:
                gate = None
            record["completion_gate"] = {"source": locate(gate), "data": gate["data"]} if gate else "unknown"
            record["runtime_interpretation"] = ({
                "wait_background": "background_suspension_not_final_delivery",
                "wait_review": "awaiting_review_not_final_acceptance",
                "continue_work": "runtime_rejected_exit",
                "allow_final": "runtime_allowed_end_not_scientific_validation",
            }.get(gate["data"].get("action"), "unknown") if gate else "unknown")
            result["stop_calls"].append(record)
            reports = [case for case in report_cases[(arm, round_name, session)]
                       if case["source_event"]["source_rowid"] < event["rowid"]]
            report = reports[-1] if reports else None
            if report is not None:
                payload = report["raw_result"].get("data") or {}
                report_result = payload.get("result") or {}
                action = report.get("next_model_action")
                if (payload.get("is_success") is True and report_result.get("complete") is False
                        and isinstance(action, dict) and action.get("event_id") == event["event_id"]):
                    between = [item for item in requests if item["project_id"] == event["project_id"]
                               and report["source_event"]["source_rowid"] < item["rowid"] < event["rowid"]]
                    confounds = []
                    if category != "coordinator_global_delivery":
                        confounds.append("not_a_known_coordinator_global_delivery")
                    if disposition != "complete":
                        confounds.append("not_a_recorded_complete_declaration")
                    if any(item["session_id"] != session for item in between):
                        confounds.append("intervening_other_agent_activity_state_change_unknown")
                    if any(item["data"].get("tool_name") in MUTATIONS for item in between):
                        confounds.append("intervening_mutation_or_work_attempt")
                    if record["runtime_interpretation"] == "background_suspension_not_final_delivery":
                        confounds.append("runtime_identified_background_wait")
                    projection = report.get("context_projection")
                    if not isinstance(projection, dict):
                        confounds.append("report_context_projection_unknown")
                    elif projection.get("intervening_compaction_event_ids"):
                        confounds.append("intervening_compaction_report_retention_unknown")
                    result["incomplete_report_then_first_action_stop"].append({
                        **record, "base_case_id": report["case_id"], "report_source": report["source_event"],
                        "context_projection_source": {key: value for key, value in projection.items() if key != "message"} if isinstance(projection, dict) else "unknown",
                        "next_model_request_source": report.get("next_model_request", "unknown"),
                        "actual_program_outputs": report["program"].get("outputs", []) if isinstance(report.get("program"), dict) else "unknown",
                        "unresolved_codes": [item.get("code") for item in report_result.get("unresolved", [])],
                        "intervening_calls": [{"source": locate(item), "tool_name": item["data"].get("tool_name")} for item in between],
                        "confounds_or_exclusions": confounds,
                        "classification": "structured_completion_conflict_candidate" if not confounds else "candidate_with_exclusions_or_unknowns",
                        "error_verdict": "not_assigned",
                    })
            if gate is not None and gate["data"].get("action") == "continue_work" and gate["data"].get("explicit_stop") is True:
                end = first_after(finishes, gate, same_run=True)
                boundary = min([item["rowid"] for item in (next_stop, end) if item is not None], default=float("inf"))
                subsequent = [item for item in requests if item["session_id"] == session and gate["rowid"] < item["rowid"] < boundary]
                submissions = []
                for item in subsequent:
                    if item["data"].get("tool_name") in EVIDENCE:
                        returned = returns.get(item["event_id"])
                        submissions.append({"source": locate(item), "tool_name": item["data"]["tool_name"],
                                            "return_event_id": returned["event_id"] if returned else "unknown",
                                            "tool_is_success": returned["data"].get("result", {}).get("is_success", "unknown") if returned else "unknown"})
                notice = first_after(feedback, gate, same_run=False)
                if notice is not None and notice["rowid"] >= boundary:
                    notice = None
                result["rejected_stop_followups"].append({
                    "stop_source": locate(event), "role": role, "gate_source": locate(gate), "gate_data": gate["data"],
                    "feedback_event": {"source": locate(notice), "data": notice["data"]} if notice else "unknown",
                    "calls_before_next_stop_or_run_end": [{"source": locate(item), "tool_name": item["data"].get("tool_name")} for item in subsequent],
                    "explicit_evidence_submission_attempts": submissions,
                    "explicit_evidence_submission_observed": bool(submissions),
                    "next_stop_source": locate(next_stop) if next_stop else "unknown",
                    "next_stop_disposition": stop_disposition(next_stop, progress)[0] if next_stop else "unknown",
                    "next_stop_disposition_source": stop_disposition(next_stop, progress)[1] if next_stop else "unknown",
                    "run_end": {"source": locate(end), "data": end["data"]} if end else "unknown",
                    "scientific_improvement": "unknown_not_evaluated",
                })
    result["source_schema"]["historical_field_keys"] = {key: sorted(value) for key, value in result["source_schema"]["historical_field_keys"].items()}
    result["structured_enum_counts"] = [{"field": key[0], "category_or_value": key[1], "disposition_or_failure_kind": key[2], "count": count} for key, count in sorted(enums.items())]
    result["summary"] = {"stop_calls": len(result["stop_calls"]), "ts_stop_calls": len(result["ts_stop_calls"]),
                         "latest_incomplete_report_then_first_action_stop": len(result["incomplete_report_then_first_action_stop"]),
                         "structured_completion_conflict_candidates": sum(item["classification"] == "structured_completion_conflict_candidate" for item in result["incomplete_report_then_first_action_stop"]),
                         "runtime_rejected_explicit_stop": len(result["rejected_stop_followups"]),
                         "rejections_followed_by_explicit_evidence_submission_attempt": sum(item["explicit_evidence_submission_observed"] for item in result["rejected_stop_followups"])}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.source_root, arguments.cases, arguments.output)["summary"], ensure_ascii=False))
