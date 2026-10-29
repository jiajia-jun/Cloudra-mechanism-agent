#!/usr/bin/env python3
"""Curate full stored-context boundaries for an audited native completion candidate.

No model calls, counterfactuals, source edits, or scientific truth labels.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
from pathlib import Path

from historical_completion import locate

CONTEXT_TYPES = {"context.prefix_installed", "context.appended", "context.compacted", "agent.context_reset",
                 "tool_documents.selection_started", "tool_documents.selection_finished"}


def snapshot(events: list[dict], boundary: dict) -> dict:
    messages, lineage, history, prefix_meta = [], [], [], {}
    for event in events:
        if event["session_seq"] >= boundary["session_seq"]:
            break
        if event["type"] not in CONTEXT_TYPES:
            continue
        data, kind = event["data"], event["type"]
        incoming = copy.deepcopy(data.get("messages") or [])
        sources = [{"source_event": locate(event), "source_message_index": number}
                   for number in range(len(incoming))]
        if kind == "context.prefix_installed":
            messages, lineage = incoming + messages, sources + lineage
            prefix_meta = copy.deepcopy(data.get("meta") or {})
            operation = "prepend_prefix"
        elif kind == "context.compacted":
            messages, lineage = incoming, sources
            prefix_meta = copy.deepcopy(data.get("prefix_meta"))
            operation = "replace_all_messages"
        elif kind == "agent.context_reset":
            messages, lineage, prefix_meta = [], [], {}
            operation = "clear_projection"
        else:
            messages.extend(incoming)
            lineage.extend(sources)
            if data.get("prefix_meta") is not None:
                prefix_meta = {**(prefix_meta or {}), **data["prefix_meta"]}
            if kind.startswith("tool_documents.selection_"):
                prefix_meta = {**(prefix_meta or {}), "tool_selection": copy.deepcopy(data["record"])}
            versions = dict((prefix_meta or {}).get("tool_document_revisions") or {})
            for message in incoming:
                if message.get("role") in {"system", "tool"}:
                    if "tool_document_revisions" in message:
                        versions = dict(message["tool_document_revisions"])
                    for document in message.get("tool_documents") or []:
                        versions[document["name"]] = document["revision"]
            if versions:
                prefix_meta = {**(prefix_meta or {}), "tool_document_revisions": versions}
            operation = "append_messages"
        history.append({"source_event": locate(event), "operation": operation,
                        "messages_in_event": len(incoming), "projected_messages_after": len(messages)})
    serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    return {"boundary_before_model_request": {"source": locate(boundary), "data": boundary["data"]},
            "messages": messages, "message_sources": lineage, "context_event_history": history,
            "prefix_meta": prefix_meta, "message_count": len(messages),
            "serialized_message_characters": len(serialized),
            "serialized_message_utf8_bytes": len(serialized.encode()),
            "serialized_message_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
            "truncated": False}


def local_window(state: dict, *, task_message_id: str, review_ids: list[str], tool_call_ids: list[str], feedback_message_id: str | None = None) -> dict:
    """Explicit selection of whole original messages; retain all matched tool pairs."""
    messages = state["messages"]
    selected = set()
    last_system = next((index for index in reversed(range(len(messages))) if messages[index].get("role") == "system"), None)
    for index, message in enumerate(messages):
        content = json.dumps(message, ensure_ascii=False)
        source_kind = state["message_sources"][index]["source_event"]["type"]
        if ((message.get("role") == "system" and (source_kind in {
                "context.prefix_installed", "tool_documents.selection_started", "tool_documents.selection_finished",
            } or index == last_system)) or message.get("message_id") == task_message_id
                or (feedback_message_id and message.get("message_id") == feedback_message_id)
                or message.get("tool_call_id") in tool_call_ids or any(token in content for token in review_ids)):
            selected.add(index)
    changed = True
    while changed:
        before = set(selected)
        call_ids = {messages[index].get("tool_call_id") for index in selected if messages[index].get("role") == "tool"}
        for index, message in enumerate(messages):
            if any(call.get("id") in call_ids for call in message.get("tool_calls") or []):
                selected.add(index)
        required_calls = {call.get("id") for index in selected for call in messages[index].get("tool_calls") or []}
        selected.update(index for index, message in enumerate(messages) if message.get("tool_call_id") in required_calls)
        changed = before != selected
    indices = sorted(selected)
    window = [copy.deepcopy(messages[index]) for index in indices]
    serialized = json.dumps(window, ensure_ascii=False, separators=(",", ":"))
    return {"selection_rule": "Whole original prefix/tool-selection system messages plus the most recent system message, original task, exact cited review IDs, selected report/stop tool exchanges and gate feedback; tool pairs closed. This is an explicitly selected context condition, not the original full context; intervening unrelated dynamic system messages are omitted by this documented selection.",
            "original_message_indices": indices, "messages": window,
            "message_sources": [state["message_sources"][index] for index in indices],
            "message_count": len(window), "serialized_message_characters": len(serialized),
            "truncated_messages": False, "is_original_full_context": len(window) == len(messages)}


def curate(audit_file: Path, case_file: Path, output: Path) -> dict:
    audit = json.loads(audit_file.read_text())
    candidates = [row for row in audit["incomplete_report_then_first_action_stop"]
                  if row["classification"] == "structured_completion_conflict_candidate"]
    if len(candidates) != 1:
        raise ValueError("This curation requires the one explicitly audited candidate; do not invent or silently choose another")
    candidate = candidates[0]
    followup = next(row for row in audit["rejected_stop_followups"] if row["stop_source"]["event_id"] == candidate["source"]["event_id"])
    with case_file.open() as source:
        case = next(item for item in (json.loads(line) for line in source) if item["case_id"] == candidate["base_case_id"])
    database = Path(candidate["database"])
    with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        events = [{**dict(row), "data": json.loads(row["data"])} for row in connection.execute(
            "SELECT rowid,event_id,project_id,session_id,run_id,seq,session_seq,type,data FROM events WHERE session_id=? ORDER BY session_seq",
            (candidate["source"]["session_id"],),
        )]
    by_id = {event["event_id"]: event for event in events}
    complete_stop = by_id[candidate["source"]["event_id"]]
    partial_stop = by_id[followup["next_stop_source"]["event_id"]]
    complete_request = by_id[case["next_model_request"]["event_id"]]
    partial_request = next(event for event in reversed(events) if event["type"] == "llm.request_started" and event["session_seq"] < partial_stop["session_seq"])
    spawn = next(event for event in events if event["type"] == "agent.spawned")
    task = next(event for event in events if event["type"] == "agent.message_injected" and event["data"].get("sender") == "user")
    gate = by_id[candidate["completion_gate"]["source"]["event_id"]]
    feedback = by_id[followup["feedback_event"]["source"]["event_id"]]
    before_complete, before_partial = snapshot(events, complete_request), snapshot(events, partial_request)
    conversation_db = database.parent / "conversations" / candidate["source"]["project_id"] / "tasks/database.db"
    cited_reviews = []
    arguments_text = json.dumps(complete_stop["data"].get("arguments_summary") or {}, ensure_ascii=False)
    with sqlite3.connect(conversation_db.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        for row in connection.execute("SELECT * FROM dag_review_decisions"):
            if row["decision_id"] not in arguments_text:
                continue
            request = connection.execute("SELECT * FROM dag_review_requests WHERE request_id=?", (row["request_id"],)).fetchone()
            cited_reviews.append({"database": str(conversation_db), "decision_table": "dag_review_decisions",
                                  "decision_row": dict(row), "request_table": "dag_review_requests",
                                  "request_row": dict(request) if request else "unknown",
                                  "selection_rule": "Exact full decision_id appears in original complete-stop parameters; no semantic inference from review prose."})
    decision_ids = [item["decision_row"]["decision_id"] for item in cited_reviews]
    receipt_events = [event for event in events if event["type"] == "tool.progress"
                      and event["data"].get("request_event_id") in {complete_stop["event_id"], partial_stop["event_id"]}]
    source_thinking = []
    for stop, request in ((complete_stop, complete_request), (partial_stop, partial_request)):
        source_thinking.extend({"source": locate(event), "original_source_text": event["data"].get("content"),
                                "status": "Original archived model response record, not this study's reasoning or an evaluation label."}
                               for event in events if event["type"] == "agent.thinking" and request["session_seq"] < event["session_seq"] < stop["session_seq"])
    usages = []
    for request in (complete_request, partial_request):
        completed = next((event for event in events if event["type"] == "llm.completed" and event["session_seq"] > request["session_seq"]), None)
        usages.append({"request_event_id": request["event_id"], "source": locate(completed), "data": completed["data"]} if completed else "unknown")
    benchmark_db = database.parent.parent / "benchmark.db"
    with sqlite3.connect(benchmark_db.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        scores = [dict(row) for row in connection.execute("SELECT * FROM runs WHERE task_id=?", (candidate["task"],))]
    material = {
        "dataset": "formal48_original", "base_case_id": candidate["base_case_id"],
        "source_audit": str(audit_file.resolve()), "source_case_file": str(case_file.resolve()),
        "source_runtime_database": str(database), "candidate_scope": "Original IA1 completion-declaration sequence; no judgment that missing IRC makes the chemical conclusion false. No counterfactual or evaluation label generated.",
        "original_task": {"source": locate(task), "data": task["data"]},
        "role_and_original_settings": {"source": locate(spawn), "data": spawn["data"]},
        "native_complete_stop": {"source": locate(complete_stop), "data": complete_stop["data"]},
        "native_partial_stop": {"source": locate(partial_stop), "data": partial_stop["data"]},
        "stop_effective_argument_records": [{"source": locate(event), "data": event["data"]} for event in receipt_events],
        "native_full_report": {"source": case["source_event"], "raw_result": case["raw_result"]},
        "brief_actual_report_program_outputs": case["program"]["outputs"],
        "report_program_source": case["program"]["submitted"],
        "specific_gate_feedback": {"gate": {"source": locate(gate), "data": gate["data"]},
                                   "feedback": {"source": locate(feedback), "data": feedback["data"]}},
        "explicit_original_sources_for_completion_rationale": {"archived_model_response_text": source_thinking,
                                                                "cited_original_supervisor_review_rows": cited_reviews,
                                                                "interpretation": "Original texts retained verbatim; acceptance validity, claimed method limitations and chemistry have not been adjudicated. Generated response text is held out from each corresponding pre-decision replay input."},
        "stored_context_before_complete_stop_request": before_complete,
        "stored_context_after_gate_before_partial_stop_request": before_partial,
        "local_window_before_complete_stop": local_window(before_complete, task_message_id=task["data"]["message_id"],
            review_ids=decision_ids, tool_call_ids=[case["program"]["submitted"]["data"]["outer_tool_call_id"]]),
        "local_window_after_gate_before_partial_stop": local_window(before_partial, task_message_id=task["data"]["message_id"],
            review_ids=decision_ids, tool_call_ids=[case["program"]["submitted"]["data"]["outer_tool_call_id"], complete_stop["data"]["tool_call_id"]],
            feedback_message_id=feedback["data"]["message_id"]),
        "recorded_request_usage": usages,
        "replay_input_contract": {
            "before_complete": "Use only stored_context_before_complete_stop_request.messages or local_window_before_complete_stop.messages as the selected input condition. The native complete-stop parameters, its generated thinking, later gate/partial action and all scores are held-out or future annotations, not extra prompt text.",
            "before_partial": "Use only stored_context_after_gate_before_partial_stop_request.messages or local_window_after_gate_before_partial_stop.messages. The prior complete action and gate appear only as actually stored historical messages; generated partial-action thinking, target partial parameters and scores are held out.",
            "tool_protocol": "Do not silently substitute present-day tool schemas for the unknown exact historical provider wire tool set.",
        },
        "projection_restoration_rule": "Original session_seq order; prefix_installed prepends, context.appended and tool-document selection append, context.compacted replaces the entire projection, agent.context_reset clears. Source message lineage and all restoration event locators retained.",
        "projection_rule_source": "cloudra/runtime_v2/apply.py:214-263 (current owning source); this session's encountered operation types are separately listed in each state history.",
        "replay_readiness": {"complete_stored_projections_available": True, "truncation_applied": False,
                             "original_provider_wire_prompt_reconstructed": False, "target_model_context_capacity": "unknown_not_tested",
                             "safe_complete_target_model_replay": "unknown_until_target_tokenizer_capacity_and_protocol_are_checked; original recorded requests used about 204k-206k prompt tokens",
                             "first_stage_available_modes": "Full stored projection, or the explicitly selected whole-message local window as a different context condition. No silent truncation.",
                             "unknowns": ["Provider-side hidden/system additions and exact final wire encoding are not logged.",
                                          "Stored system-prefix messages and capability tool names are present; exact historical per-request wire tool schemas/default settings outside the events are not fully reconstructed.",
                                          "Image/media reference resolution and provider-specific transformations at send time are not reproduced.",
                                          "The recorded model alias is not an immutable server-weight revision; target tokenizer and context capacity remain unverified."]},
        "scoring_separation": {"archived_original_benchmark_database": str(benchmark_db), "archived_original_run_rows": scores,
                               "timing_scope": "Archived final-run score rows may postdate these decision boundaries; they are not contemporaneous correctness labels.",
                               "subsequent_offline_rescoring": "Not imported or merged into source context, native report, original action or rationale."},
    }
    output.write_text(json.dumps(material, ensure_ascii=False, indent=2) + "\n")
    return material


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = curate(args.audit, args.cases, args.output)
    print(json.dumps({key: {"messages": value[key]["message_count"], "characters": value[key]["serialized_message_characters"]}
                      for key in ("stored_context_before_complete_stop_request", "stored_context_after_gate_before_partial_stop_request",
                                  "local_window_before_complete_stop", "local_window_after_gate_before_partial_stop")}, ensure_ascii=False))
