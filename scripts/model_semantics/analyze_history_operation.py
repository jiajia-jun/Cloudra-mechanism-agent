#!/usr/bin/env python3
"""Describe saved history/operation answers and the observed full-history timeout.

Window and operation runs must be complete; the full-history run has its recorded
request_timeout terminal evidence. No model or transport is run here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.model_semantics.run_local import choice_letters, parse_choice, write_json

RUN_SIZES = {"pilot_history_window": 12, "pilot_operation_feedback": 10}
HISTORY_CONDITIONS = ("report_alone", "window_12")
HISTORY_QUESTIONS = ("latest_report_complete", "formal_short_irc_waiver", "next_workflow_action")


def semantic_choice(probe: dict, letter: str | None) -> tuple[str | None, str | None]:
    if letter is None:
        return None, None
    value = probe["choices"][letter]
    return (value["action"], value["text"]) if isinstance(value, dict) else (value, value)


def read_complete(run_dir: Path, expected_size: int) -> tuple[list[dict], dict]:
    files = {name: run_dir / name for name in ("frozen_probes.jsonl", "results.json", "summary.json")}
    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        raise ValueError("Run is not complete; missing: " + ", ".join(missing))
    probes = [json.loads(line) for line in files["frozen_probes.jsonl"].read_text().splitlines() if line.strip()]
    results = json.loads(files["results.json"].read_text())
    summary = json.loads(files["summary.json"].read_text())
    indexed = {row["id"]: row for row in results}
    probe_ids = {probe["id"] for probe in probes}
    if (len(probes) != expected_size or len(probe_ids) != expected_size or len(results) != expected_size
            or len(indexed) != expected_size or set(indexed) != probe_ids or summary["n"] != expected_size):
        raise ValueError(f"Run is not complete: {run_dir} must contain exactly {expected_size} matching inputs and results")
    rows, response_sources = [], []
    for probe in probes:
        saved = indexed[probe["id"]]
        response_path = Path(saved["response_file"])
        if not response_path.is_file():
            raise ValueError("Missing original response: " + str(response_path))
        content = response_path.read_bytes()
        packet = json.loads(content)
        native = packet.get("response")
        if not isinstance(native, dict) or native.get("done") is not True:
            raise ValueError("Original response is not complete: " + str(response_path))
        expected = probe["expected"]
        if expected not in choice_letters(probe) or saved["expected"] != expected:
            raise ValueError("Missing or inconsistent frozen label: " + probe["id"])
        letter = parse_choice(native, choice_letters(probe))
        meaning, text = semantic_choice(probe, letter)
        expected_meaning, expected_text = semantic_choice(probe, expected)
        raw_count = probe.get("raw_prompt_token_count")
        reported_count = native.get("prompt_eval_count")
        prefill_duration = native.get("prompt_eval_duration")
        rows.append({
            "id": probe["id"], "condition": probe["condition"], "task": probe.get("task"),
            "information_condition": probe.get("information_condition"), "question_type": probe.get("question_type"),
            "option_order": probe.get("option_order"), "option_rotation": probe.get("option_rotation"),
            "choices": probe["choices"], "actual_letter": letter, "actual_semantic_action": meaning,
            "actual_choice_text": text, "expected_letter": expected, "expected_semantic_action": expected_meaning,
            "expected_choice_text": expected_text, "matches_frozen_label": letter == expected,
            "format_valid": letter is not None, "raw_response": native.get("response"),
            "raw_prompt_token_count": raw_count, "reported_prompt_eval_count": reported_count,
            "reported_count_matches_raw": reported_count == raw_count if raw_count is not None and reported_count is not None else None,
            "native_prefill_duration_ns": prefill_duration,
            "native_prefill_seconds": prefill_duration / 1e9 if prefill_duration is not None else None,
            "done_reason": native.get("done_reason"), "eval_count": native.get("eval_count"),
            "configured_num_ctx": packet["request"]["options"].get("num_ctx"),
            "source_label": probe.get("label_source", probe.get("source")),
            "source_response": str(response_path), "source_run": str(run_dir),
        })
        response_sources.append({"path": str(response_path), "sha256": hashlib.sha256(content).hexdigest()})
    sources = {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for name, path in files.items()}
    sources["responses"] = response_sources
    return rows, sources


def describe_group(rows: list[dict]) -> dict:
    meanings = [row["actual_semantic_action"] for row in rows]
    return {"n": len(rows), "n_matching_frozen_labels": sum(row["matches_frozen_label"] for row in rows),
            "all_orders_same_semantic_action": len(set(meanings)) == 1 if all(row["format_valid"] for row in rows) else None,
            "selected_semantic_actions": meanings, "selected_letters": [row["actual_letter"] for row in rows],
            "records": rows}


def read_full_timeout(run_dir: Path) -> tuple[dict, dict]:
    files = {name: run_dir / name for name in (
        "frozen_probes.jsonl", "terminal_status.json", "terminal_exec_result.json", "failed_request.json",
    )}
    for path in files.values():
        if not path.is_file():
            raise ValueError("Missing full-history request_timeout evidence: " + str(path))
    probes = [json.loads(line) for line in files["frozen_probes.jsonl"].read_text().splitlines() if line.strip()]
    terminal = json.loads(files["terminal_status.json"].read_text())
    execution = json.loads(files["terminal_exec_result.json"].read_text())
    failure = json.loads(files["failed_request.json"].read_text())
    if (terminal["status"] != "request_timeout" or terminal["exit_code"] != 1
            or (terminal["n_planned"], terminal["n_attempted"], terminal["n_completed"], terminal["n_not_attempted"]) != (6, 1, 0, 5)
            or terminal["http_timeout_seconds"] != 3600 or len(probes) != 6
            or len({probe["id"] for probe in probes}) != 6 or probes[0]["id"] != terminal["attempted_id"]):
        raise ValueError("Full-history terminal evidence differs from the observed first-request timeout")
    source_request = Path(terminal["source_request"])
    prompt_sha = hashlib.sha256(failure["request"]["prompt"].encode()).hexdigest()
    if (execution["exit_code"] != 1 or "TimeoutError: timed out" not in execution["output"]
            or failure["observed_terminal_status"] != terminal
            or failure["request"] != json.loads(source_request.read_text())
            or prompt_sha != probes[0]["raw_prompt_sha256"]
            or terminal["counted_raw_prompt_tokens"] != probes[0]["raw_prompt_token_count"]
            or terminal["configured_num_ctx"] != failure["request"]["options"]["num_ctx"]
            or list((run_dir / "responses").glob("*.json"))):
        raise ValueError("Full-history saved request, terminal result or zero-answer record is inconsistent")
    sources = {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for name, path in {**files, "source_request": source_request}.items()}
    return {
        "status": "request_timeout", "n_planned": 6, "n_attempted": 1, "n_completed": 0, "n_not_attempted": 5,
        "attempted_id": terminal["attempted_id"], "counted_raw_prompt_tokens": terminal["counted_raw_prompt_tokens"],
        "configured_num_ctx": terminal["configured_num_ctx"], "http_wait_limit_seconds": 3600,
        "exception": terminal["exception"], "exit_code": 1, "observed_at_utc": terminal["observed_at_utc"],
        "interpretation": "首个完整历史请求在3600秒HTTP等待上限结束，未保存答案；其余5题未尝试。记录为操作等待成本，不记为模型答错。",
        "native_prefill_duration": None, "native_reported_prompt_eval_count": None,
        "included_in_correctness_or_option_consistency": False,
        "planned_inputs": [{"id": probe["id"], "task": probe["task"], "option_order": probe["option_order"],
                            "raw_prompt_token_count": probe["raw_prompt_token_count"],
                            "raw_prompt_sha256": probe["raw_prompt_sha256"],
                            "execution_status": "request_timeout" if index == 0 else "not_attempted"}
                           for index, probe in enumerate(probes)],
        "source_files": sources,
    }, sources


def analyze(study_dir: Path) -> dict:
    loaded, sources = {}, {}
    for name, size in RUN_SIZES.items():
        loaded[name], sources[name] = read_complete(study_dir / name, size)
    full_timeout, sources["pilot_history_full"] = read_full_timeout(study_dir / "pilot_history_full")
    history_rows = loaded["pilot_history_window"]
    history = {}
    for condition in HISTORY_CONDITIONS:
        history[condition] = {}
        for question in HISTORY_QUESTIONS:
            rows = sorted((row for row in history_rows if row["condition"] == condition and row["task"] == question),
                          key=lambda row: row["option_order"])
            if len(rows) != 2 or {row["option_order"] for row in rows} != {"forward", "swapped"}:
                raise ValueError(f"Missing history option pair: {condition}/{question}")
            group = describe_group(rows)
            group["two_orders_consistent"] = group["all_orders_same_semantic_action"]
            history[condition][question] = group
    operation = {}
    for information in ("proxy_only", "proxy_plus_target"):
        operation[information] = {}
        for question, expected_n in (("sufficiency", 2), ("next_action", 3)):
            rows = sorted((row for row in loaded["pilot_operation_feedback"]
                           if row["information_condition"] == information and row["question_type"] == question),
                          key=lambda row: row["option_rotation"])
            if len(rows) != expected_n or [row["option_rotation"] for row in rows] != list(range(expected_n)):
                raise ValueError(f"Missing operation option rotation: {information}/{question}")
            operation[information][question] = describe_group(rows)
    transitions = {}
    for question in ("sufficiency", "next_action"):
        before = operation["proxy_only"][question]["records"]
        after = operation["proxy_plus_target"][question]["records"]
        transitions[question] = [{
            "option_rotation": first["option_rotation"], "option_mapping_unchanged": first["choices"] == second["choices"],
            "before_H7_letter": first["actual_letter"], "after_H7_letter": second["actual_letter"],
            "before_H7_action": first["actual_semantic_action"], "after_H7_action": second["actual_semantic_action"],
            "before_H7_choice_text": first["actual_choice_text"], "after_H7_choice_text": second["actual_choice_text"],
            "action_changed": first["actual_semantic_action"] != second["actual_semantic_action"]
            if first["format_valid"] and second["format_valid"] else None,
            "before_response": first["source_response"], "after_response": second["source_response"],
        } for first, second in zip(before, after, strict=True)]
    history_preserved = all(group["n_matching_frozen_labels"] == group["n"] and group["two_orders_consistent"]
                            for questions in history.values() for group in questions.values())
    history_counts_match = all(row["reported_count_matches_raw"] is True for row in history_rows)
    history_description = (
        "构造短报告与12条消息窗口中，报告未完成、没有正式short_irc豁免、应保留交付缺口的状态均在两种选项顺序中得到一致读取。"
        if history_preserved and history_counts_match else
        "所有保存响应均一致读取了报告未完成、没有正式豁免及应保留缺口的状态；原始词表计数与原生报告计数的差异另列于metadata。"
        if history_preserved else
        "原始状态的读取存在条件或选项顺序差异；逐问题保留了实际选择及其语义，见history分组。"
    )
    before_actions = operation["proxy_only"]["next_action"]["selected_semantic_actions"]
    after_actions = operation["proxy_plus_target"]["next_action"]["selected_semantic_actions"]
    measurement_to_B = set(before_actions) == {"request_target_measurement"} and set(after_actions) == {"select_B"}
    action_description = (
        "仅有H5代理量时，三个选项循环均请求目标H7测量；加入H7读数后，三个循环均转为采用候选B。"
        if measurement_to_B else
        "加入H7前后的实际语义动作分别为" + json.dumps(before_actions, ensure_ascii=False)
        + "与" + json.dumps(after_actions, ensure_ascii=False) + "；逐循环动作转变见operation_transitions。"
    )
    all_rows = history_rows + loaded["pilot_operation_feedback"]
    return {
        "status": "completed22_responses_and_full_history_request_timeout", "findings": {
            "explicit_workflow_state": history_description, "target_measurement_to_action": action_description,
            "full_history_operation_cost": full_timeout["interpretation"],
            "workflow_state_retained_in_all_history_pairs": history_preserved,
            "history_reported_token_counts_all_match_raw": history_counts_match,
            "target_information_switches_request_to_candidate_B_in_all_rotations": measurement_to_B,
            "design_connection": {
                "DAG": "DAG把完成、正式豁免和缺口留成可读取的程序状态；本组已完成诊断检查短报告和12条窗口中的状态读取。",
                "geometry": "几何反馈应标明研究意图指定的目标量；本组把是否提供H7读数与信息充分性和下一动作对应起来。",
            },
        },
        "history": history, "full_history_execution": full_timeout,
        "operation": operation, "operation_transitions": transitions,
        "metadata": {
            "sources": sources, "n_completed_responses": 22, "n_history_completed_inputs": 12, "n_operation_inputs": 10,
            "n_full_history_planned": 6, "n_full_history_completed": 0,
            "history_state_pair_n": 6, "operation_next_action_rotation_n_per_condition": 3,
            "reported_count_match_observations": dict(Counter(str(row["reported_count_matches_raw"]) for row in history_rows)),
            "done_reason_counts": dict(Counter(str(row["done_reason"]) for row in all_rows)),
            "history_protocol": "Quoted JSON data in raw ChatML with fixed closed think; not native chat or reconstructed original provider wire.",
            "operation_protocol": "Curated native H5-only display versus the same H5 display plus native H7 values; A/B sufficiency and cyclic A/B/C next actions.",
            "scope": "One IA1 workflow conflict and one E1 geometry operation source; option rotations are repeated presentations.",
            "prefill_duration": "Original native prompt_eval_duration is retained per response in ns and seconds for inspection.",
            "token_count_observation": "Raw tokenizer counts and native reported counts remain separate; matching counts are recorded rather than assumed.",
            "label_source": "Frozen labels and choices are read from each pilot's own frozen_probes.jsonl; actual choices are parsed again from the saved native responses.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=Path("output/cloudra_model_study_20261028"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    study_dir = args.study_dir.resolve()
    try:
        result = analyze(study_dir)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as error:
        parser.exit(2, f"Refusing final summary; saved inputs/results are incomplete or inconsistent: {error}\n")
    output = (args.output or study_dir / "history_operation_analysis.json").resolve()
    write_json(output, result)
    print(output)


if __name__ == "__main__":
    main()
