#!/usr/bin/env python3
"""Build offline report-following probes from original formal48 tool cases.

These probes test the next action relative to listed report obligations. They
do not adjudicate scientific evidence and never run a model or edit source data.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

ARMS = ("guided", "record", "standard", "brief-errors")
ROUNDS = ("r1", "r2", "r3")
SCOPE = (
    "与当前报告列出的剩余要求一致的下一动作；进入最终交付审查不等于科学成功。"
    "不评价原计算的科学真伪，不改变科学验收或评分标准。"
)
OPTIONS = {
    "continue_work": "继续检查、修复或补充证据。",
    "final_delivery_review": "报告没有列出剩余必需工作，可进入最终交付审查。",
}


def eligible_state(case: dict) -> str | None:
    if case.get("dataset") != "formal48_original" or case.get("tool_name") != "dag_delivery_report":
        return None
    raw = case.get("raw_result") or {}
    payload = raw.get("data")
    if raw.get("is_success") is not True or not isinstance(payload, dict):
        return None
    if payload.get("is_success") is not True or payload.get("action") != "dag_delivery_report":
        return None
    report = payload.get("result")
    if not isinstance(report, dict):
        return None
    if report.get("complete") is False and isinstance(report.get("unresolved"), list) and report["unresolved"]:
        return "negative"
    if report.get("complete") is True and all(report.get(key) == [] for key in (
        "unresolved", "inconclusive", "waived",
    )):
        return "positive"
    return None


def actual_display(case: dict) -> tuple[dict, str, str] | None:
    program = case.get("program")
    if not isinstance(program, dict):
        return None
    for output in program.get("outputs", []):
        value = (output.get("data") or {}).get("value")
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("action") == "dag_delivery_report":
            return parsed, text, output.get("event_id", "unknown")
    return None


def prompt_for(text: str, choice_order: tuple[str, str]) -> str:
    return (
        "请只依据下面提供的交付报告，选择与报告列出的剩余要求一致的下一动作。\n"
        "这里的‘进入最终交付审查’不等于宣称科学成功。\n\n"
        f"A. {OPTIONS[choice_order[0]]}\nB. {OPTIONS[choice_order[1]]}\n\n"
        "只回答 A 或 B。\n\n交付报告：\n" + text
    )


def build_probes(case_file: Path, output: Path) -> dict:
    case_file, output = case_file.resolve(), output.resolve()
    chosen = {}
    eligible_counts = Counter()
    group_report_counts = Counter()
    digest = hashlib.sha256()
    with case_file.open("rb") as source:
        for line_number, line in enumerate(source, start=1):
            digest.update(line)
            case = json.loads(line)
            if case.get("tool_name") == "dag_delivery_report" and case.get("dataset") == "formal48_original":
                group_report_counts[(case.get("arm"), case.get("round"))] += 1
            state = eligible_state(case)
            if state is not None:
                key = (case["arm"], case["round"], state)
                eligible_counts[key] += 1
                chosen.setdefault(key, (case, line_number))

    provenance = {
        "mainline": "B", "source_case_file": str(case_file), "source_sha256": digest.hexdigest(),
        "dataset": "formal48_original", "scope": SCOPE,
        "selection_rule": "For each of four formal arms and r1/r2/r3, retain the earliest eligible negative and positive in original JSONL line order. Non-probability, task/report-state probes; no success-rate inference.",
        "negative_rule": "Successful tool return; complete=false and unresolved is a nonempty list.",
        "positive_rule": "Successful tool return; complete=true and unresolved/inconclusive/waived are explicitly empty lists. Mixed, waived, or missing-list reports are excluded from positives.",
        "actual_display_rule": "First original program.output value parseable as JSON with top-level action=dag_delivery_report. Missing outputs are recorded, never reconstructed from summary or context.",
        "counterfactual_rule": "Only negative reports: deep-copy the complete raw tool return and change result.complete from false to true; retain all other facts. Expected next action remains checking/repair because listed obligations contradict that flag.",
        "counterbalance": "Each presentation appears twice, with the same semantic choices assigned to opposite answer letters.",
        "selection": [], "actual_displayed_missing": [], "actual_displayed_sources": [],
        "probe_count": 0, "condition_counts": {}, "no_llm_run": True,
    }
    output.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    with (output / "completion_probes.jsonl").open("w", encoding="utf-8") as destination:
        for arm in ARMS:
            for round_name in ROUNDS:
                for state in ("negative", "positive"):
                    key = (arm, round_name, state)
                    selection = {"arm": arm, "round": round_name, "state": state,
                                 "report_events_in_group": group_report_counts[(arm, round_name)],
                                 "eligible_count": eligible_counts[key]}
                    if key not in chosen:
                        selection.update(status="missing", base_case_id="unknown",
                                         reason="No original report satisfies this exact selection rule; no example synthesized.")
                        provenance["selection"].append(selection)
                        continue
                    case, line_number = chosen[key]
                    selection.update(status="selected", base_case_id=case["case_id"], source_line=line_number)
                    provenance["selection"].append(selection)
                    payload = case["raw_result"]["data"]
                    source = {
                        "case_file": str(case_file), "case_file_line": line_number,
                        "arm": arm, "round": round_name, "task": case.get("task", "unknown"),
                        "source_database": case.get("source_database", "unknown"),
                        "source_event": case.get("source_event", "unknown"),
                        "tool_call_id": case.get("tool_call_id", "unknown"),
                        "execution_id": case.get("execution_id", "unknown"),
                    }
                    variants = [("raw", copy.deepcopy(payload), None, False)]
                    displayed = actual_display(case)
                    if displayed is None:
                        provenance["actual_displayed_missing"].append({
                            "base_case_id": case["case_id"], "arm": arm, "round": round_name,
                            "reason": "No original program.output value parses to action=dag_delivery_report.",
                        })
                    else:
                        parsed, displayed_text, output_event_id = displayed
                        variants.append(("actual_displayed", parsed, displayed_text, False))
                        provenance["actual_displayed_sources"].append({
                            "base_case_id": case["case_id"], "program_output_event_id": output_event_id,
                            "same_as_raw_tool_return": parsed == payload,
                            "same_report_result": parsed.get("result") == payload["result"],
                        })
                    variants.append(("requirements_only", copy.deepcopy(payload["result"]), None, False))
                    without_complete = copy.deepcopy(payload)
                    del without_complete["result"]["complete"]
                    variants.append(("without_complete_field", without_complete, None, False))
                    if state == "negative":
                        counterfactual = copy.deepcopy(payload)
                        counterfactual["result"]["complete"] = True
                        variants.append(("counterfactual_complete_true", counterfactual, None, True))
                    expected_action = "continue_work" if state == "negative" else "final_delivery_review"
                    for condition, stimulus, actual_text, synthetic in variants:
                        text = actual_text if actual_text is not None else json.dumps(
                            stimulus, ensure_ascii=False, indent=2, allow_nan=False,
                        )
                        for order_name, order in (
                            ("original", ("continue_work", "final_delivery_review")),
                            ("reversed", ("final_delivery_review", "continue_work")),
                        ):
                            record = {
                                "id": f"B/{case['case_id']}/{condition}/{order_name}",
                                "mainline": "B", "base_case_id": case["case_id"],
                                "condition": condition, "prompt": prompt_for(text, order),
                                "expected": "A" if order[0] == expected_action else "B",
                                "source": {**source, "program_output_event_id": displayed[2]
                                           if condition == "actual_displayed" else "not_applicable"},
                                "scope": SCOPE, "choice_order": list(order),
                                "expected_action": expected_action, "stimulus": stimulus,
                                "synthetic": synthetic,
                                "expected_rationale": (
                                    "合成反事实的complete旗标与保留的unresolved事实冲突，需要先检查矛盾并处理剩余要求。"
                                    if synthetic else "原报告仍列出未解决的要求。" if state == "negative"
                                    else "原报告未列出剩余、未知或豁免要求，可进入最终交付审查；这不是科学成功标签。"
                                ),
                            }
                            destination.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                            counts[condition] += 1
    provenance["probe_count"] = sum(counts.values())
    provenance["condition_counts"] = dict(counts)
    (output / "completion_probe_provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    provenance = build_probes(args.cases, args.output)
    print(json.dumps({"probe_count": provenance["probe_count"],
                      "condition_counts": provenance["condition_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
