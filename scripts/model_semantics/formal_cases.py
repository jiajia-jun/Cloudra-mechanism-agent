#!/usr/bin/env python3
"""Extract scientific-tool cases from original P1b runtime database copies.

Every matching tool.result_recorded event is retained, irrespective of its
reported state. SQLite files are opened read-only/immutable. This produces a
corpus, not scientific truth labels, scores, or claims about provider delivery.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

TOOLS = frozenset({
    "internal_coordinates", "ts_inspect", "dag_delivery_report", "dag_view_evidence",
    "dag_submit_species_evidence", "dag_submit_step_evidence", "log_parser",
    "ts_prepare", "ts_resume", "ts_stop",
})
TASKS = frozenset({"E1", "NB1", "HA1", "IA1"})
UNKNOWN = "unknown"


def event_record(row: sqlite3.Row, data: dict) -> dict:
    return {**{key: row[key] for key in (
        "event_id", "project_id", "session_id", "run_id", "seq", "session_seq", "type", "created_at",
    )}, "source_rowid": row["source_rowid"], "data": data}


def task_identity(project_event: dict | None) -> tuple[str, dict | str]:
    if project_event is None:
        return UNKNOWN, UNKNOWN
    data = project_event["data"]
    candidates = set()
    name = data.get("name", "")
    if isinstance(name, str) and name.startswith("benchmark:"):
        task = name.partition(":")[2]
        if task in TASKS:
            candidates.add(task)
    workspace = data.get("workspace_dir")
    if isinstance(workspace, str):
        parts = PurePosixPath(workspace).parts
        if "sandboxes" in parts:
            index = parts.index("sandboxes") + 1
            if index < len(parts) and parts[index] in TASKS:
                candidates.add(parts[index])
    task = next(iter(candidates)) if len(candidates) == 1 else UNKNOWN
    return task, {"event_id": project_event["event_id"], "project_name": name,
                  "workspace_dir": workspace or UNKNOWN, "explicit_task_candidates": sorted(candidates)}


def reported_state(payload: object, raw_result: dict) -> dict:
    """Copy only reported state fields; deliberately make no scientific judgment."""
    state = {"tool_is_success": raw_result.get("is_success", UNKNOWN)}
    if not isinstance(payload, dict):
        return state
    for key in ("is_success", "status", "stage", "accepted", "normal_termination",
                "opt_converged", "zmat_status", "imaginary_frequencies"):
        if key in payload:
            state[key] = payload[key]
    if isinstance(payload.get("anomalies"), list):
        state["anomalies_count"] = len(payload["anomalies"])
    nested = payload.get("result")
    if isinstance(nested, dict):
        for key in ("complete", "outcome", "verified", "status"):
            if key in nested:
                state[f"result.{key}"] = nested[key]
    for holder in (payload, nested):
        if isinstance(holder, dict) and isinstance(holder.get("scientific_checks"), dict):
            state["scientific_check_statuses"] = {
                stage: check.get("status", UNKNOWN) if isinstance(check, dict) else UNKNOWN
                for stage, check in holder["scientific_checks"].items()
            }
    return state


def after(records: list[dict], position: int) -> dict | None:
    index = bisect.bisect_right([item["source_rowid"] for item in records], position)
    return records[index] if index < len(records) else None


def load_database(database: Path) -> dict:
    index = {
        "cases": [], "projects": {}, "agents": {}, "programs": {}, "requests": {},
        "request_calls": defaultdict(list), "finished": {}, "llm": defaultdict(list),
        "actions": defaultdict(list), "projections": defaultdict(list),
        "compactions": defaultdict(list), "event_counts": Counter(),
        "event_data_keys": defaultdict(set), "message_keys": defaultdict(set),
        "tool_call_keys": set(), "model_alias_counts": Counter(), "tool_counts": Counter(),
        "payload_keys": defaultdict(set),
    }
    with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT rowid AS source_rowid,event_id,project_id,session_id,run_id,seq,session_seq,"
            "type,data,created_at FROM events ORDER BY rowid"
        )
        for row in rows:
            data = json.loads(row["data"])
            kind, session = row["type"], row["session_id"]
            index["event_counts"][kind] += 1
            index["event_data_keys"][kind].update(data)
            record = event_record(row, data)
            if kind == "project.created":
                index["projects"][data.get("id", row["project_id"])] = record
            elif kind == "agent.spawned":
                settings = data.get("settings") or {}
                index["agents"][data.get("id", session)] = {
                    "source_event_id": row["event_id"], "declared_model": settings.get("model") or UNKNOWN,
                    "provider": settings.get("provider") or UNKNOWN,
                    "base_url_host": urlparse(settings.get("base_url") or "").hostname or UNKNOWN,
                    "invocation_protocol": settings.get("invocation_protocol") or UNKNOWN,
                }
            elif kind == "llm.request_started":
                index["llm"][session].append(record)
                index["model_alias_counts"][str(data.get("model", UNKNOWN))] += 1
            elif kind.startswith("program."):
                execution = data.get("execution_id")
                program = index["programs"].setdefault(execution, {"submitted": UNKNOWN, "outputs": [], "finished": UNKNOWN})
                if kind == "program.submitted":
                    program["submitted"] = record
                    index["actions"][session].append(record)
                elif kind == "program.output":
                    program["outputs"].append(record)
                elif kind == "program.finished":
                    program["finished"] = record
            elif kind == "tool.requested":
                index["requests"][row["event_id"]] = record
                index["request_calls"][(session, data.get("tool_call_id"))].append(record)
                if not data.get("execution_id"):
                    index["actions"][session].append(record)
            elif kind == "tool.result_recorded" and data.get("tool_name") in TOOLS:
                index["cases"].append(record)
                tool = data["tool_name"]
                index["tool_counts"][tool] += 1
                payload = (data.get("result") or {}).get("data")
                if isinstance(payload, dict):
                    index["payload_keys"][tool].update(payload)
            elif kind == "tool.finished" and data.get("raw_result_event_id"):
                index["finished"][data["raw_result_event_id"]] = record
            if kind in {"context.appended", "context.prefix_installed", "context.compacted"}:
                for message in data.get("messages", []):
                    role = message.get("role", UNKNOWN)
                    index["message_keys"][role].update(message)
                    for call in message.get("tool_calls") or []:
                        index["tool_call_keys"].update(call)
                    if kind == "context.appended" and role == "tool":
                        index["projections"][(session, message.get("tool_call_id"))].append({
                            **{key: value for key, value in record.items() if key != "data"},
                            "message": message,
                        })
                if kind == "context.compacted":
                    index["compactions"][session].append({key: value for key, value in record.items() if key != "data"})
    return index


def make_case(record: dict, index: dict, database: Path, source_root: Path) -> dict:
    data, session = record["data"], record["session_id"]
    raw_result = data.get("result") or {}
    task, task_evidence = task_identity(index["projects"].get(record["project_id"]))
    request = index["requests"].get(data.get("request_event_id"))
    if request is None:
        preceding = [item for item in index["request_calls"][(session, data.get("tool_call_id"))]
                     if item["source_rowid"] < record["source_rowid"]]
        request = preceding[-1] if preceding else None
    finished = index["finished"].get(record["event_id"])
    execution = data.get("execution_id")
    program = index["programs"].get(execution) if execution else None
    outer_call = data.get("tool_call_id")
    boundary = (finished or record)["source_rowid"]
    if program is not None:
        for part in ("submitted", "finished"):
            if isinstance(program[part], dict):
                outer_call = program[part]["data"].get("outer_tool_call_id", outer_call)
        if isinstance(program["finished"], dict):
            boundary = program["finished"]["source_rowid"]
    projection = after(index["projections"][(session, outer_call)], record["source_rowid"])
    if projection is not None:
        boundary = max(boundary, projection["source_rowid"])
    next_request = after(index["llm"][session], boundary)
    next_action = None
    if next_request is not None:
        next_action = after(index["actions"][session], next_request["source_rowid"])
        following_request = after(index["llm"][session], next_request["source_rowid"])
        if next_action is not None and following_request is not None:
            if next_action["source_rowid"] >= following_request["source_rowid"]:
                next_action = None
    prior_requests = [item for item in index["llm"][session]
                      if item["source_rowid"] < record["source_rowid"]]
    prior_request = prior_requests[-1] if prior_requests else None
    identity = {**index["agents"].get(session, {}),
                "effective_model": prior_request["data"].get("model", UNKNOWN) if prior_request else UNKNOWN,
                "model_request_event_id": prior_request["event_id"] if prior_request else UNKNOWN}
    identity.setdefault("provider", UNKNOWN)
    if projection is not None:
        projection = dict(projection)
        projection["intervening_compaction_event_ids"] = [
            item["event_id"] for item in index["compactions"][session]
            if item["source_rowid"] > projection["source_rowid"]
            and (next_request is None or item["source_rowid"] < next_request["source_rowid"])
        ]
    relative = database.relative_to(source_root)
    missing = [name for name, value in (
        ("task", task), ("source_request", request), ("program", program),
        ("context_projection", projection), ("next_model_request", next_request),
        ("next_model_action", next_action),
    ) if value is None or value == UNKNOWN]
    return {
        "case_id": f"{relative.parts[0]}/{relative.parts[1]}/{record['event_id']}",
        "dataset": "formal48_original", "arm": relative.parts[0], "round": relative.parts[1],
        "task": task, "task_evidence": task_evidence, "project_id": record["project_id"],
        "session_id": session, "run_id": record["run_id"], "tool_name": data.get("tool_name", UNKNOWN),
        "source_database": str(database), "source_database_relative": str(relative),
        "source_event": {key: value for key, value in record.items() if key != "data"},
        "source_request": request or UNKNOWN, "tool_call_id": data.get("tool_call_id", UNKNOWN),
        "execution_id": execution or UNKNOWN, "raw_result": raw_result,
        "tool_finished": finished or UNKNOWN, "program": program or UNKNOWN,
        "context_projection": projection or UNKNOWN, "model_identity": identity,
        "model_visibility": {"wire_request_messages": UNKNOWN,
                             "provider_delivery": UNKNOWN,
                             "interpretation": "Stored context is an observed projection; provider request body and receipt are not logged here."},
        "next_model_request": next_request or UNKNOWN, "next_model_action": next_action or UNKNOWN,
        "reported_state": reported_state(raw_result.get("data"), raw_result),
        "evaluation_label": None, "missing_information": missing,
    }


def extract(source_root: Path, output: Path) -> dict:
    source_root, output = source_root.resolve(), output.resolve()
    if output.is_relative_to(source_root):
        raise ValueError("Output must be outside the read-only source root")
    databases = sorted(source_root.glob("*/r*/runtime/runtime-v2.db"))
    if not databases:
        raise ValueError("No arm/round/runtime/runtime-v2.db files under source root")
    output.mkdir(parents=True, exist_ok=True)
    corpus_path = output / "formal_cases.jsonl"
    summary = {
        "dataset": "formal48_original", "source_root": str(source_root),
        "case_file": str(corpus_path), "case_count": 0, "databases": [],
        "selection": {"method": "all_matching_tool_result_events", "tools": sorted(TOOLS),
                      "state_filter": None, "sampling": "Complete census of these event types in the supplied original runtime copies; not a random sample of model behavior or chemistry tasks."},
        "source_access": "SQLite mode=ro&immutable=1 plus query_only; original data are not modified.",
        "evaluation": "No scientific truth or behavior labels assigned; reported_state only copies original program output states.",
        "visibility": "Projected messages are distinct from unknown provider wire request/receipt. Intervening context compaction is recorded.",
    }
    with corpus_path.open("w", encoding="utf-8") as destination:
        for database in databases:
            index = load_database(database)
            counts, missing = Counter(), Counter()
            for record in index["cases"]:
                case = make_case(record, index, database, source_root)
                destination.write(json.dumps(case, ensure_ascii=False, allow_nan=False) + "\n")
                counts[(case["task"], case["tool_name"]) ] += 1
                missing.update(case["missing_information"])
            relative = database.relative_to(source_root)
            summary["case_count"] += len(index["cases"])
            summary["databases"].append({
                "source_database": str(database), "arm": relative.parts[0], "round": relative.parts[1],
                "bytes": database.stat().st_size, "case_count": len(index["cases"]),
                "model_alias_counts": dict(index["model_alias_counts"]),
                "declared_model_provider_protocol": list({json.dumps(agent, sort_keys=True): agent
                    for agent in index["agents"].values()}.values()),
                "event_counts": dict(index["event_counts"]),
                "event_data_key_schema": {key: sorted(value) for key, value in index["event_data_keys"].items()},
                "message_key_schema_by_role": {key: sorted(value) for key, value in index["message_keys"].items()},
                "assistant_tool_call_keys": sorted(index["tool_call_keys"]),
                "scientific_tool_payload_keys": {key: sorted(value) for key, value in index["payload_keys"].items()},
                "case_counts_by_task_tool": [{"task": task, "tool": tool, "count": count}
                    for (task, tool), count in sorted(counts.items())],
                "missing_information_counts": dict(missing),
            })
            print(json.dumps({"arm": relative.parts[0], "round": relative.parts[1],
                              "cases": len(index["cases"])}, ensure_ascii=False), flush=True)
    summary["case_file_bytes"] = corpus_path.stat().st_size
    (output / "formal_case_inventory.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = extract(args.source_root, args.output)
    print(json.dumps({"case_count": summary["case_count"], "case_file_bytes": summary["case_file_bytes"]}))


if __name__ == "__main__":
    main()
