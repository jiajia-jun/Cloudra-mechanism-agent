#!/usr/bin/env python3
"""Freeze local intent-binding probes from a curated native operation display.

Only source-field selection and question/option construction; no model calls,
geometry edits, QM calculations, or scientific acceptance decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

SCOPE = "指定H7二面角目标的信息充分性和下一动作；只按到180°的圆周距离排序，不判TS或科学合格。"
OPTIONS = {
    "sufficient": "信息充分，可以判断哪一候选的 H7-C2-C3-Cl4 更接近180°。",
    "need_target_measurement": "信息不足，需要补测两候选的 H7-C2-C3-Cl4。",
    "select_A": "采用候选A，作为更接近指定角度的下一阶段候选。",
    "select_B": "采用候选B，作为更接近指定角度的下一阶段候选。",
    "request_target_measurement": "先请求两候选的 H7-C2-C3-Cl4 测量，暂不选候选。",
}


def native_measurements(material: dict) -> tuple[dict, str, dict]:
    """Parse the saved actual display using its exact explicit token layout."""
    index, events = material["event_index"], material["source_events"]
    displayed = events[index["target_measure_output"]]
    text = displayed["data"]["value"]
    raw = events[index["target_measure_result"]]["data"]["result"]["data"]["result"]
    if displayed["source"]["type"] != "program.output" or text != raw:
        raise ValueError("native_display_and_result_must_match")
    rows = {}
    for line in text.splitlines():
        tokens = line.split()
        if (len(tokens) != 10 or tokens[0] not in {"A", "B"}
                or tokens[1:3] != ["H7-C2-C3-Cl4", "="]
                or tokens[4:6] != ["H5-C2-C3-Cl4", "="]
                or tokens[7:9] != ["C3-Cl4/H7", "dist"] or tokens[0] in rows):
            raise ValueError("unexpected_native_measurement_tokens")
        numbers = [float(tokens[i]) for i in (3, 6, 9)]
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("nonfinite_native_measurement")
        rows[tokens[0]] = {"H5": tokens[6], "H7": tokens[3]}
    if set(rows) != {"A", "B"}:
        raise ValueError("two_native_candidates_required")
    return rows, text, displayed["source"]


def build_probes(case_file: Path, output: Path) -> dict:
    case_file, output = case_file.resolve(), output.resolve()
    source_bytes = case_file.read_bytes()
    material = json.loads(source_bytes)
    rows, displayed_text, display_source = native_measurements(material)
    target = material["geometric_recalculation"]["target_degrees"]
    if target != 180.0 or material["dataset"] != "formal48_original":
        raise ValueError("unexpected_source_goal_or_dataset")
    residuals = {name: round(abs((float(row["H7"]) - target + 180) % 360 - 180), 1)
                 for name, row in rows.items()}
    if residuals["A"] == residuals["B"]:
        raise ValueError("target_ranking_is_tied")
    preferred = min(residuals, key=residuals.get)
    source = {
        "case_file": str(case_file),
        "source_database": material["source"]["database"],
        "source_database_relative": material["source"]["database_relative"],
        "program_output_event": display_source,
        "display_field": "data.value",
        "native_raw_result_event_id": material["event_index"]["target_measure_result"],
        "original_goal_event_id": material["event_index"]["original_intent"],
    }
    probes = []
    for information in ("proxy_only", "proxy_plus_target"):
        facts = [{"candidate": name, "quadruplet": "H5-C2-C3-Cl4", "absolute_degrees_token": row["H5"]}
                 for name, row in rows.items()]
        added = [{"candidate": name, "quadruplet": "H7-C2-C3-Cl4", "absolute_degrees_token": row["H7"]}
                 for name, row in rows.items()] if information == "proxy_plus_target" else []
        facts += added
        body = (
            "局部几何任务：比较两候选的 H7-C2-C3-Cl4 二面角到180°的圆周距离。"
            "A/B是候选标签。以下是当前可用的测量：\n\n"
            + "\n".join(f"候选{fact['candidate']}：|τ({fact['quadruplet']})|="
                        f"{fact['absolute_degrees_token']}°。" for fact in facts)
        )
        for question, actions in (
            ("sufficiency", ("sufficient", "need_target_measurement")),
            ("next_action", ("select_A", "select_B", "request_target_measurement")),
        ):
            if question == "sufficiency":
                orders = (actions, actions[::-1])
                expected_action = "sufficient" if added else "need_target_measurement"
                question_text = "这些信息是否足以判断哪个候选的目标H7二面角更接近180°？"
            else:
                orders = tuple(actions[i:] + actions[:i] for i in range(3))
                expected_action = f"select_{preferred}" if added else "request_target_measurement"
                question_text = "下一步最符合这个指定局部几何目标的动作是什么？"
            for order_number, order in enumerate(orders):
                choices = {chr(65 + i): {"action": action, "text": OPTIONS[action]}
                           for i, action in enumerate(order)}
                prompt = body + "\n\n" + question_text + "\n" + "\n".join(
                    f"{letter}. {choice['text']}" for letter, choice in choices.items()
                ) + "\n只输出一个选项字母。"
                probes.append({
                    "id": f"A/operation_feedback/{information}/{question}/{order_number}",
                    "mainline": "A", "base_case_id": "guided/r2/evt_585eb8c474754439",
                    "condition": f"{information}/{question}", "information_condition": information,
                    "question_type": question, "option_rotation": order_number,
                    "prompt": prompt, "choices": choices,
                    "expected": next(letter for letter, choice in choices.items()
                                     if choice["action"] == expected_action),
                    "expected_action": expected_action, "source": source, "scope": SCOPE,
                    "expected_rationale": (
                        f"原生展示的H7到180°圆周距离：A={residuals['A']:.1f}°，"
                        f"B={residuals['B']:.1f}°；仅排序更接近者，残差保留。"
                        if added else "未展示目标H7测量，也未给出XYZ或H5/H7相对几何关系，先请求目标测量。"
                    ),
                    "shown_measurements": facts, "information_added": added,
                    "presentation_intervention": "curated_field_selection_and_target_information_addition",
                    "format_only_control": False, "historical_prompt_replay": False,
                    "synthetic_presentation": True, "synthetic_measurements": False,
                })
    assert len(probes) == 10 and len({probe["id"] for probe in probes}) == 10
    for information in ("proxy_only", "proxy_plus_target"):
        for question, letters in (("sufficiency", {"A", "B"}), ("next_action", {"A", "B", "C"})):
            selected = [p for p in probes if p["information_condition"] == information
                        and p["question_type"] == question]
            assert {p["expected"] for p in selected} == letters
            assert all(set(p["choices"]) == letters for p in selected)
    provenance = {
        "mainline": "A", "dataset": "formal48_original", "scope": SCOPE,
        "source": source, "source_case_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "native_display": displayed_text,
        "measurement_source": "Exact numeric tokens from saved original program.output data.value; checked equal to the native raw tool result text.",
        "curation": "Both conditions retain only native H5 A/B values; proxy_plus_target adds only native H7 A/B values. XYZ, the H5/H7 relationship, original model responses/choice, Supervisor input, and high-precision recalculation are withheld from prompts.",
        "not_format_only_or_native_prompt_replay": True,
        "original_embedded_eight_items_used": False,
        "original_goal_event_id": source["original_goal_event_id"], "target_degrees": target,
        "ranking_formula": "abs((displayed_absolute_H7_degrees - 180 + 180) % 360 - 180)",
        "derived_residuals_from_rounded_native_display_degrees": residuals,
        "preferred_candidate_for_given_ranking": preferred,
        "residual_precision": "Derived from the original one-decimal absolute-angle display; not the high-precision XYZ recalculation. Residuals are held out from prompts.",
        "scientific_acceptance_threshold": None,
        "counterbalance": "Sufficiency: two reversed A/B assignments. Next action: three cyclic A/B/C assignments, each semantic action once at every letter.",
        "probe_count": len(probes), "condition_counts": dict(Counter(p["condition"] for p in probes)),
        "expected_counts": dict(Counter(p["expected"] for p in probes)), "no_llm_run": True,
    }
    output.mkdir(parents=True, exist_ok=True)
    output_file = output / "operation_feedback_probes.jsonl"
    provenance_file = output / "operation_feedback_provenance.json"
    if case_file in {output_file, provenance_file}:
        raise ValueError("source_must_not_be_an_output")
    output_file.write_text("".join(json.dumps(probe, ensure_ascii=False, allow_nan=False) + "\n"
                                   for probe in probes), encoding="utf-8")
    assert case_file.read_bytes() == source_bytes
    provenance["source_case_bytes_unchanged_after_build"] = True
    provenance_file.write_text(json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                               encoding="utf-8")
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    provenance = build_probes(args.case, args.output)
    print(json.dumps({key: provenance[key] for key in ("probe_count", "condition_counts", "expected_counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
