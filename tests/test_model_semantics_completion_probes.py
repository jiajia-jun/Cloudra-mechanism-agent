"""Probe construction contracts; the generated cases here are test data only."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/model_semantics/completion_probes.py"


def extractor():
    assert SCRIPT.is_file(), "Completion probe builder has not been implemented"
    spec = importlib.util.spec_from_file_location("completion_probes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case(case_id, report, *, output=None, success=True):
    payload = {"is_success": success, "action": "dag_delivery_report", "result": report,
               "accepted": None, "rejection_code": None, "error": ""}
    return {"case_id": case_id, "dataset": "formal48_original", "arm": "guided", "round": "r1",
            "task": "NB1", "tool_name": "dag_delivery_report", "project_id": "project",
            "session_id": "session", "source_database": "/copied/runtime-v2.db",
            "source_event": {"event_id": case_id, "seq": 1},
            "raw_result": {"is_success": success, "data": payload},
            "program": {"outputs": [] if output is None else [
                {"event_id": "output-event", "data": {"value": output}}]}}


def report(complete, *, unresolved=None, inconclusive=None, waived=None):
    return {"complete": complete, "satisfied": [{"detail": "recorded work"}],
            "unresolved": unresolved or [], "inconclusive": inconclusive or [],
            "waived": waived or [], "output_artifact": None}


def build(tmp_path, cases):
    source = tmp_path / "formal_cases.jsonl"
    source.write_text("".join(json.dumps(value) + "\n" for value in cases))
    before = source.read_bytes()
    output = tmp_path / "probes"
    provenance = extractor().build_probes(source, output)
    records = [json.loads(line) for line in (output / "completion_probes.jsonl").read_text().splitlines()]
    assert source.read_bytes() == before
    return records, provenance


def test_earliest_selection_excludes_mixed_or_waived_positive_reports(tmp_path):
    negative = report(False, unresolved=[{"code": "missing", "detail": "supply evidence"}])
    positive = report(True)
    records, provenance = build(tmp_path, [
        case("waived", report(True, waived=[{"detail": "waived obligation"}])),
        case("mixed", report(True, unresolved=[{"detail": "still missing"}])),
        case("uncertain", report(True, inconclusive=[{"detail": "unknown"}])),
        case("failed", negative, success=False),
        case("first-negative", negative), case("later-negative", negative),
        case("first-positive", positive), case("later-positive", positive),
    ])
    assert {record["base_case_id"] for record in records} == {"first-negative", "first-positive"}
    chosen = {(entry["arm"], entry["round"], entry["state"]): entry for entry in provenance["selection"]}
    assert chosen[("guided", "r1", "negative")]["base_case_id"] == "first-negative"
    assert chosen[("guided", "r1", "positive")]["base_case_id"] == "first-positive"
    assert chosen[("standard", "r1", "positive")]["status"] == "missing"
    assert all(record["mainline"] == "B" for record in records)


def test_actual_display_is_strict_and_answer_letters_are_counterbalanced(tmp_path):
    negative = report(False, unresolved=[{"code": "missing", "detail": "supply evidence"}])
    raw = case("negative", negative)
    displayed = json.dumps(raw["raw_result"]["data"], separators=(",", ":"))
    raw["program"]["outputs"] = [
        {"event_id": "not-json", "data": {"value": "complete=false"}},
        {"event_id": "wrong-action", "data": {"value": json.dumps({"action": "dag_view"})}},
        {"event_id": "actual-report", "data": {"value": displayed}},
    ]
    records, provenance = build(tmp_path, [raw])
    actual = [record for record in records if record["condition"] == "actual_displayed"]
    assert len(actual) == 2
    assert all(record["source"]["program_output_event_id"] == "actual-report" for record in actual)
    assert all(displayed in record["prompt"] for record in actual)
    for condition in {record["condition"] for record in records}:
        pair = [record for record in records if record["condition"] == condition]
        assert {record["expected"] for record in pair} == {"A", "B"}
        assert pair[0]["expected_action"] == pair[1]["expected_action"] == "continue_work"
        assert pair[0]["choice_order"] == list(reversed(pair[1]["choice_order"]))
    assert not provenance["actual_displayed_missing"]


def test_counterfactual_changes_only_complete_and_missing_display_is_not_fabricated(tmp_path):
    negative = report(False, unresolved=[{"code": "missing", "detail": "supply endpoint logs"}])
    original = case("negative", negative)
    records, provenance = build(tmp_path, [original])
    by_condition = {}
    for value in records:
        by_condition.setdefault(value["condition"], value)
    assert "actual_displayed" not in by_condition
    assert provenance["actual_displayed_missing"][0]["base_case_id"] == "negative"
    raw = by_condition["raw"]["stimulus"]
    counterfactual = by_condition["counterfactual_complete_true"]["stimulus"]
    assert raw == original["raw_result"]["data"]
    assert raw["result"]["complete"] is False
    assert counterfactual["result"]["complete"] is True
    counterfactual["result"]["complete"] = False
    assert counterfactual == raw
    assert by_condition["counterfactual_complete_true"]["synthetic"] is True
    assert by_condition["counterfactual_complete_true"]["expected_action"] == "continue_work"
    assert by_condition["requirements_only"]["stimulus"] == raw["result"]
    without_flag = by_condition["without_complete_field"]["stimulus"]
    assert "complete" not in without_flag["result"]
    without_flag["result"]["complete"] = False
    assert without_flag == raw
    assert all("<|im_start|>" not in value["prompt"] for value in records)
