#!/usr/bin/env python3
"""Analyze frozen two-choice outputs by reversed options and matched source cases.

Reads saved records only. No models are called and no scientific labels are made.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

OUTCOMES = ("both_correct", "both_wrong", "letter_preference", "format_error")


def semantic_options(probe: dict) -> list:
    if "choice_order" in probe:
        return probe["choice_order"]
    return [probe["choices"][label] for label in ("A", "B")]


def summarize(pairs: list[dict]) -> dict:
    counts = Counter(pair["outcome"] for pair in pairs)
    return {
        "n_base_pairs": len(pairs), "n_records": sum(len(pair["records"]) for pair in pairs),
        "correct_records": sum(pair["correct_records"] for pair in pairs),
        "valid_wrong_records": sum(pair["valid_wrong_records"] for pair in pairs),
        "format_failures": sum(pair["format_failures"] for pair in pairs),
        "pair_outcomes": {name: counts[name] for name in OUTCOMES},
    }


def analyze(probes: list[dict], results: list[dict]) -> dict:
    by_id = {row["id"]: row for row in results}
    if len(by_id) != len(results) or len({row["id"] for row in probes}) != len(probes):
        raise ValueError("Duplicate probe/result IDs")
    if set(by_id) != {row["id"] for row in probes}:
        raise ValueError("Probe/result IDs differ")
    groups = defaultdict(list)
    for probe in probes:
        result = by_id[probe["id"]]
        for key in ("base_case_id", "mainline", "condition", "expected"):
            if result[key] != probe[key]:
                raise ValueError(f"Frozen probe/result mismatch: {probe['id']}:{key}")
        prediction = result["prediction"]
        valid = prediction in ("A", "B")
        correct = valid and prediction == probe["expected"]
        if result["format_valid"] != valid or result["correct"] != correct:
            raise ValueError(f"Saved prediction flags disagree: {probe['id']}")
        groups[(probe["mainline"], probe["base_case_id"], probe["condition"])].append((probe, {
            "id": probe["id"],
            "option_order": probe.get("option_order", probe["id"].rsplit("/", 1)[-1]),
            "expected": probe["expected"], "prediction": prediction,
            "correct": correct, "format_valid": valid, "response_file": result["response_file"],
        }))

    pairs, conditions = [], defaultdict(dict)
    for (mainline, base_case_id, condition), group in sorted(groups.items()):
        if len(group) != 2 or {probe["expected"] for probe, _ in group} != {"A", "B"}:
            raise ValueError(f"Expected two reversed choices: {base_case_id}/{condition}")
        options = [semantic_options(probe) for probe, _ in group]
        if len(options[0]) != 2 or options[0] != list(reversed(options[1])):
            raise ValueError(f"Pair semantic alternatives are not reversed: {base_case_id}/{condition}")
        for probe, _ in group:
            if "expected_action" in probe:
                if semantic_options(probe)[("A", "B").index(probe["expected"])] != probe["expected_action"]:
                    raise ValueError(f"Frozen expected action disagrees: {probe['id']}")
        records = [row for _, row in group]
        correct = sum(row["correct"] for row in records)
        invalid = sum(not row["format_valid"] for row in records)
        letter = None
        if invalid:
            outcome = "format_error"
        elif correct == 2:
            outcome = "both_correct"
        elif correct == 0:
            outcome = "both_wrong"
        else:
            outcome = "letter_preference"
            letter = records[0]["prediction"]
        pair = {
            "mainline": mainline, "base_case_id": base_case_id, "condition": condition,
            "source": group[0][0].get("source", {}), "outcome": outcome, "same_letter": letter,
            "correct_records": correct, "valid_wrong_records": 2 - correct - invalid,
            "format_failures": invalid, "records": records,
        }
        pairs.append(pair)
        conditions[(mainline, condition)][base_case_id] = pair

    comparisons = []
    for mainline in sorted({key[0] for key in conditions}):
        names = sorted(condition for line, condition in conditions if line == mainline)
        for left_name, right_name in itertools.combinations(names, 2):
            left, right = conditions[(mainline, left_name)], conditions[(mainline, right_name)]
            shared = sorted(left.keys() & right.keys())
            if not shared:
                continue
            left_summary = summarize([left[base] for base in shared])
            right_summary = summarize([right[base] for base in shared])
            comparisons.append({
                "mainline": mainline, "left_condition": left_name, "right_condition": right_name,
                "n_matched_bases": len(shared), "n_matched_records_per_condition": 2 * len(shared),
                "excluded_left_bases": sorted(left.keys() - right.keys()),
                "excluded_right_bases": sorted(right.keys() - left.keys()),
                "left_matched": left_summary, "right_matched": right_summary,
                "right_minus_left_correct_records": right_summary["correct_records"] - left_summary["correct_records"],
                "right_minus_left_format_failures": right_summary["format_failures"] - left_summary["format_failures"],
                "matched_records": [{
                    "base_case_id": base,
                    "left_records": left[base]["records"], "right_records": right[base]["records"],
                    "left_outcome": left[base]["outcome"], "right_outcome": right[base]["outcome"],
                    "right_minus_left_correct_records": right[base]["correct_records"] - left[base]["correct_records"],
                } for base in shared],
            })

    geometry = {row["base_case_id"]: row.get("source", {}) for row in probes
                if row["mainline"] == "A" and row["condition"] == "original_xyz"}
    return {
        "metadata": {
            "measurement": "Agreement with frozen local two-choice diagnostic labels; no new failure or scientific-success labels.",
            "pairing": "Two reversed alternatives per base_case_id + condition. A pair is one repeated local decision, not two independent chemistry samples.",
            "pair_outcome_definitions": {
                "both_correct": "Both valid letters select the labeled semantic answer after reversal.",
                "both_wrong": "Both valid letters select the other semantic answer after reversal.",
                "letter_preference": "Same letter on the two reversals, exactly one correct. Describes this pair only; no stable model preference is inferred.",
                "format_error": "At least one response has no valid A/B prediction; counted separately from valid wrong choices.",
            },
            "comparisons": "All differences use only common base cases. Each listed record is traceable to its saved response; difference is right minus left correct record count with 2*n records per condition. No unpaired condition accuracy is an effect estimate.",
            "condition_meanings": {
                "requirements_only": "Historical condition name retained: contains the whole report.result, including complete and satisfied/unresolved/inconclusive/waived status. It is report_result_only, not facts-only.",
                "actual_displayed": "Historical condition name retained: one original program.output printed report fragment. It excludes other outputs/context wrappers and does not establish provider wire receipt.",
                "without_complete_field": "Removes only complete; other report-assigned status cues remain.",
                "counterfactual_complete_true": "Synthetic complete=true contradicts retained unresolved obligations. Tests report consistency, not scientific truth.",
                "tool_distances": "Tool-supplied computed relations; computation outsourcing rather than a pure equivalent coordinate presentation.",
            },
            "mainline_A_scope": {
                "geometry_structures": len(geometry),
                "tasks": dict(Counter(source.get("task", "unknown") for source in geometry.values())),
                "geometry_base_case_ids": sorted(geometry),
                "interpretation": "This pilot has four NB1 structures plus HA1 carbon-count/name text diagnostics. It does not test general geometry ability, chemical operation execution or stereochemical/mechanism correctness.",
            },
            "inference_scope": "Local Qwen deployment, explicit raw ChatML, thinking disabled, greedy decoding, short direct A/B answers. No generalization to historical DeepSeek internal mechanisms, original research success rates or scientific acceptance.",
        },
        "n_records": len(results), "n_base_condition_pairs": len(pairs),
        "format_failures": sum(pair["format_failures"] for pair in pairs),
        "condition_summaries": [{"mainline": line, "condition": condition,
                                 **summarize(list(values.values()))}
                                for (line, condition), values in sorted(conditions.items())],
        "pairs": pairs, "matched_comparisons": comparisons,
        "interpretation": {
            "observations": "Pair outcomes and matched record-count differences below describe only the saved pilot responses against frozen diagnostic labels. Condition totals describe their own case composition.",
            "hypotheses": [
                "A difference between XYZ and tool_distances could reflect avoided numerical computation or supplied relational information; this pilot does not isolate those causes.",
                "Following unresolved requirements despite a conflicting complete flag could reflect use of list/status cues; it need not require chemical evidence-to-target reasoning.",
            ],
            "not_proven": [
                "A selective causal representation of chemical geometry or scientific evidence binding.",
                "Repair of full research trajectories, correct quantum-chemical evidence, or scientific acceptance.",
                "Native deployment/activation-runner equivalence on these research prompts or an explanation of historical DeepSeek activations.",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=Path("output/cloudra_model_study_20261028/pilot_local"))
    parser.add_argument("--output", type=Path, default=Path("output/cloudra_model_study_20261028/pilot_analysis.json"))
    args = parser.parse_args()
    probes_path, results_path = args.pilot_dir / "frozen_probes.jsonl", args.pilot_dir / "results.json"
    probes = [json.loads(line) for line in probes_path.read_text().splitlines() if line.strip()]
    report = analyze(probes, json.loads(results_path.read_text()))
    report["sources"] = {
        name: {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for name, path in (("frozen_probes", probes_path), ("results", results_path))
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output.resolve()), "n_records": report["n_records"],
                      "n_pairs": report["n_base_condition_pairs"], "format_failures": report["format_failures"]}))


if __name__ == "__main__":
    main()
