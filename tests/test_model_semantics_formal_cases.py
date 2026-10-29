"""Extraction contracts; these generated events are not research trajectories."""

import importlib.util
import json
import sqlite3
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/model_semantics/formal_cases.py"


def load_extractor():
    assert SCRIPT.is_file(), "Formal case extractor has not been implemented"
    spec = importlib.util.spec_from_file_location("formal_cases", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_archive_copy(tmp_path, events):
    source = tmp_path / "source"
    database = source / "guided/r1/runtime/runtime-v2.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE events(event_id TEXT, project_id TEXT, session_id TEXT, "
            "run_id TEXT, seq INTEGER, session_seq INTEGER, type TEXT, data TEXT, created_at TEXT)"
        )
        for number, (kind, data) in enumerate(events, start=1):
            connection.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)",
                (f"evt_{number}", "project", "session", "run", number, number,
                 kind, json.dumps(data), "2026-10-24T00:00:00Z"),
            )
    return source, database


def test_all_states_and_actual_js_outputs_are_preserved_without_claiming_wire_visibility(tmp_path):
    extractor = load_extractor()
    events = [
        ("project.created", {"id": "project", "name": "benchmark:NB1",
                             "workspace_dir": "/original/guided/r1/sandboxes/NB1/batch"}),
        ("agent.spawned", {"id": "session", "settings": {
            "model": "", "invocation_protocol": "javascript"}}),
        ("llm.request_started", {"model": "deepseek-v4-flash"}),
        ("program.submitted", {"execution_id": "exec", "outer_tool_call_id": "outer",
                               "code": "const r = await tools.internal_coordinates({}); text(r.data);"}),
        ("tool.requested", {"tool_call_id": "call1", "tool_name": "internal_coordinates",
                            "execution_id": "exec", "arguments_summary": {"mode": "analyze"}}),
        ("tool.result_recorded", {"tool_call_id": "call1", "tool_name": "internal_coordinates",
                                  "execution_id": "exec", "request_event_id": "evt_5",
                                  "result": {"is_success": True, "summary": "successful with an anomaly",
                                             "data": {"is_success": True, "anomalies": [{"value": 2.1}]}}}),
        ("program.output", {"execution_id": "exec", "outer_tool_call_id": "outer",
                            "output_index": 1, "value": {"is_success": True, "anomalies": [{"value": 2.1}]}}),
        ("tool.requested", {"tool_call_id": "call2", "tool_name": "ts_inspect",
                            "execution_id": "exec", "arguments_summary": {"run_id": "absent"}}),
        ("tool.result_recorded", {"tool_call_id": "call2", "tool_name": "ts_inspect",
                                  "execution_id": "exec", "request_event_id": "evt_8",
                                  "result": {"is_success": False, "summary": "not found",
                                             "data": {"is_success": False, "message": "not found"}}}),
        ("program.output", {"execution_id": "exec", "outer_tool_call_id": "outer",
                            "output_index": 2, "value": "not found"}),
        ("program.finished", {"execution_id": "exec", "outer_tool_call_id": "outer",
                              "status": "completed", "calls": []}),
        ("context.appended", {"messages": [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "outer", "name": "js_exec", "arguments": {"code": "source"}}]},
            {"role": "tool", "tool_call_id": "outer", "content": "the actual projected program text"}]}),
        ("llm.request_started", {"model": "deepseek-v4-flash"}),
        ("tool.requested", {"tool_call_id": "stop", "tool_name": "stop", "execution_id": None,
                            "arguments_summary": {"reason": "report available evidence"}}),
    ]
    source, database = make_archive_copy(tmp_path, events)
    before = database.read_bytes()
    output = tmp_path / "output"
    inventory = extractor.extract(source, output)
    cases = [json.loads(line) for line in (output / "formal_cases.jsonl").read_text().splitlines()]

    assert len(cases) == 2
    assert [case["raw_result"]["is_success"] for case in cases] == [True, False]
    assert all(case["task"] == "NB1" for case in cases)
    assert cases[0]["raw_result"]["data"]["anomalies"] == [{"value": 2.1}]
    assert cases[0]["source_request"]["data"]["arguments_summary"] == {"mode": "analyze"}
    assert [item["data"]["value"] for item in cases[0]["program"]["outputs"]] == [
        {"is_success": True, "anomalies": [{"value": 2.1}]}, "not found",
    ]
    assert cases[0]["next_model_action"]["data"]["tool_name"] == "stop"
    assert cases[0]["next_model_action"]["event_id"] == "evt_14"
    assert cases[0]["context_projection"]["message"]["content"] == "the actual projected program text"
    assert cases[0]["model_visibility"]["wire_request_messages"] == "unknown"
    assert cases[0]["evaluation_label"] is None
    assert inventory["selection"]["method"] == "all_matching_tool_result_events"
    assert inventory["databases"][0]["model_alias_counts"] == {"deepseek-v4-flash": 2}
    assert database.read_bytes() == before


def test_missing_task_and_program_are_unknown_and_child_calls_are_not_next_model_actions(tmp_path):
    extractor = load_extractor()
    source, _ = make_archive_copy(tmp_path, [
        ("tool.result_recorded", {"tool_call_id": "source", "tool_name": "log_parser",
                                  "result": {"is_success": True, "data": {"normal_termination": True}}}),
        ("llm.request_started", {"model": "recorded-model"}),
        ("program.submitted", {"execution_id": "next", "outer_tool_call_id": "next-outer",
                               "code": "text(await tools.ts_inspect({run_id: 'a'}));"}),
        ("tool.requested", {"tool_call_id": "child", "tool_name": "ts_inspect",
                            "execution_id": "next", "arguments_summary": {"run_id": "a"}}),
    ])
    output = tmp_path / "output"
    extractor.extract(source, output)
    case = json.loads((output / "formal_cases.jsonl").read_text())
    assert case["task"] == "unknown"
    assert case["source_request"] == "unknown"
    assert case["program"] == "unknown"
    assert case["context_projection"] == "unknown"
    assert case["next_model_action"]["type"] == "program.submitted"
    assert case["next_model_action"]["event_id"] == "evt_3"
    assert case["model_identity"]["provider"] == "unknown"


def test_compaction_between_projection_and_next_request_is_explicit(tmp_path):
    extractor = load_extractor()
    source, _ = make_archive_copy(tmp_path, [
        ("tool.result_recorded", {"tool_call_id": "call", "tool_name": "dag_delivery_report",
                                  "result": {"is_success": True, "data": {"result": {"complete": False}}}}),
        ("tool.finished", {"tool_call_id": "call", "raw_result_event_id": "evt_1"}),
        ("context.appended", {"messages": [{"role": "tool", "tool_call_id": "call", "content": "complete=false"}]}),
        ("context.compacted", {"messages": [{"role": "assistant", "content": "summary"}]}),
        ("llm.request_started", {"model": "recorded-model"}),
    ])
    output = tmp_path / "output"
    extractor.extract(source, output)
    case = json.loads((output / "formal_cases.jsonl").read_text())
    assert case["context_projection"]["intervening_compaction_event_ids"] == ["evt_4"]
    assert case["model_visibility"]["wire_request_messages"] == "unknown"
    assert case["next_model_action"] == "unknown"
