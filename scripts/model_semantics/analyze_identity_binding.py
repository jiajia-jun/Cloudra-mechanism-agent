#!/usr/bin/env python3
"""Analyze complete saved identity/binding controls without making model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def normalize(probe: dict, result: dict) -> dict:
    """Interpret only recorded A/B predictions; never recover prose answers."""
    row = {key: probe[key] for key in ("id", "base_case_id", "mainline", "condition", "expected")}
    if probe["mainline"].startswith("chemical_identity/"):
        representation, order = probe["condition"].split("/")
        if representation not in {"literal", "equivalent_rewrite"}:
            raise ValueError("Unknown chemical representation")
        row.update(family="chemical_identity", representation=representation,
                   change_type=probe["mainline"].split("/", 1)[1])
        meanings = ("same_identity", "different_identity")
    elif probe["mainline"] == "B":
        binding, presentation = probe["condition"].split("_")
        order = probe["option_order"]
        if binding not in {"coherent", "altered"} or presentation not in {"flat", "linked"}:
            raise ValueError("Unknown binding condition")
        row.update(family="evidence_binding", binding=binding, presentation=presentation)
        meanings = ("given_binding_requirements_satisfied", "given_binding_requirements_not_satisfied")
    else:
        raise ValueError("Unexpected probe family")
    if order not in {"forward", "swapped"} or row["expected"] not in {"A", "B"}:
        raise ValueError("Invalid frozen option order or expected label")
    options = dict(zip(("A", "B"), meanings if order == "forward" else meanings[::-1], strict=True))
    prediction = result.get("prediction")
    valid = prediction in ("A", "B")
    row.update(order=order, prediction=prediction, format_valid=valid,
               correct=prediction == row["expected"], expected_meaning=options[row["expected"]],
               selected_meaning=options[prediction] if valid else None,
               response_file=result.get("response_file"), raw_response=result.get("raw_response"))
    return row


def record_summary(rows: list[dict]) -> dict:
    return {
        "n_records": len(rows), "n_distinct_bases": len({row["base_case_id"] for row in rows}),
        "correct": sum(row["correct"] for row in rows),
        "valid_wrong": sum(row["format_valid"] and not row["correct"] for row in rows),
        "format_failures": sum(not row["format_valid"] for row in rows),
        "selected_meaning_counts": dict(Counter(row["selected_meaning"] for row in rows if row["format_valid"])),
    }


def stratify(rows: list[dict], fields: tuple[str, ...], summarizer) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in fields)].append(row)
    return [{**dict(zip(fields, key, strict=True)), **summarizer(group)}
            for key, group in sorted(groups.items())]


def matched_pairs(rows: list[dict], axis: str, values: tuple[str, str], fixed: tuple[str, ...]) -> list[dict]:
    groups = defaultdict(dict)
    for row in rows:
        key = tuple(row[field] for field in fixed)
        if row[axis] in groups[key]:
            raise ValueError(f"Duplicate matched condition for {key}")
        groups[key][row[axis]] = row
    pairs = []
    for key, group in sorted(groups.items()):
        if set(group) != set(values):
            raise ValueError(f"Incomplete matched {axis} conditions for {key}")
        left, right = (group[value] for value in values)
        valid = left["format_valid"] and right["format_valid"]
        if axis == "order" and left["expected_meaning"] != right["expected_meaning"]:
            raise ValueError("Option reversal changed the frozen semantic label")
        pairs.append({
            **dict(zip(fixed, key, strict=True)), "axis": axis,
            "left_condition": values[0], "right_condition": values[1],
            "both_valid": valid,
            "semantic_same": left["selected_meaning"] == right["selected_meaning"] if valid else None,
            "expected_meaning_changed": left["expected_meaning"] != right["expected_meaning"],
            "both_correct": left["correct"] and right["correct"],
            "both_wrong": valid and not left["correct"] and not right["correct"],
            "left_correct_right_wrong": valid and left["correct"] and not right["correct"],
            "left_wrong_right_correct": valid and not left["correct"] and right["correct"],
            "same_letter": left["prediction"] == right["prediction"] if valid else None,
            "left": left, "right": right,
        })
    return pairs


def pair_summary(pairs: list[dict]) -> dict:
    return {
        "n_matched_pairs": len(pairs),
        "n_distinct_bases": len({pair["base_case_id"] for pair in pairs}),
        "both_valid": sum(pair["both_valid"] for pair in pairs),
        "semantic_same": sum(pair["semantic_same"] is True for pair in pairs),
        "semantic_changed": sum(pair["semantic_same"] is False for pair in pairs),
        **{key: sum(pair[key] for pair in pairs) for key in (
            "both_correct", "both_wrong", "left_correct_right_wrong", "left_wrong_right_correct",
        )},
        "format_error_pairs": sum(not pair["both_valid"] for pair in pairs),
    }


def analyze(probes: list[dict], results: list[dict]) -> dict:
    probe_ids, result_ids = [row["id"] for row in probes], [row["id"] for row in results]
    if not probes or len(set(probe_ids)) != len(probe_ids) or len(set(result_ids)) != len(result_ids):
        raise ValueError("Probe/result IDs must be nonempty and unique")
    if set(probe_ids) != set(result_ids):
        raise ValueError(f"Probe/result IDs differ: missing={sorted(set(probe_ids) - set(result_ids))}, "
                         f"extra={sorted(set(result_ids) - set(probe_ids))}")
    # No summaries or partial matches are computed before the exact ID check.
    result_by_id = {row["id"]: row for row in results}
    rows = [normalize(probe, result_by_id[probe["id"]]) for probe in probes]
    chemical = [row for row in rows if row["family"] == "chemical_identity"]
    binding = [row for row in rows if row["family"] == "evidence_binding"]
    chemical_options = matched_pairs(chemical, "order", ("forward", "swapped"),
                                     ("base_case_id", "change_type", "representation"))
    representations = matched_pairs(chemical, "representation", ("literal", "equivalent_rewrite"),
                                    ("base_case_id", "change_type", "order"))
    binding_options = matched_pairs(binding, "order", ("forward", "swapped"),
                                    ("base_case_id", "binding", "presentation"))
    binding_changes = matched_pairs(binding, "binding", ("coherent", "altered"),
                                    ("base_case_id", "presentation", "order"))
    presentations = matched_pairs(binding, "presentation", ("flat", "linked"),
                                   ("base_case_id", "binding", "order"))
    return {
        "scope": {
            "measurement": "Agreement with frozen local identity and given-association labels; not scientific success or acceptance.",
            "unit": "Base identity pairs and base evidence cases. Repeated representations and option orders are paired variants, not independent chemical samples.",
            "chemical_baseline": "Literal same-identity positives use identical strings; treat them as a string-matching baseline. Sixteen identity pairs are derived from four chemical tasks, not sixteen independent tasks.",
            "binding_sources": "Four source chains cover three tasks; both NB1 chains share one original run. Synthetic association labels do not establish scientific acceptance.",
            "prediction": "Only the saved prediction exactly equal to A or B is valid. Stored correct/format_valid flags are ignored; no natural-language answer is guessed.",
            "option_consistency": "Semantic equality across reversed options is separate from both_correct: stable wrong semantic answers are consistent and both_wrong.",
            "contrasts": "Identity compares literal to equivalent_rewrite at fixed base/order; binding compares coherent to altered at fixed base/presentation/order; presentation compares flat to linked at fixed base/binding/order.",
            "invalid_format": "Invalid records are listed separately; pairs containing one are excluded from semantic same/change and valid wrong transitions.",
            "inference": "Descriptive results for this saved local deployment only; no significance tests, causal mechanism claim, new thresholds or scoring weights.",
        },
        "n_records": len(rows),
        "chemical_identity": {
            **record_summary(chemical),
            "by_change_type_and_representation": stratify(chemical, ("change_type", "representation"), record_summary),
            "option_order_summary": pair_summary(chemical_options),
            "option_order_by_change_type_and_representation": stratify(
                chemical_options, ("change_type", "representation"), pair_summary),
            "option_order_pairs": chemical_options,
            "representation_summary": pair_summary(representations),
            "representation_by_change_type": stratify(representations, ("change_type",), pair_summary),
            "representation_pairs": representations,
        },
        "evidence_binding": {
            **record_summary(binding),
            "by_binding_and_presentation": stratify(binding, ("binding", "presentation"), record_summary),
            "option_order_summary": pair_summary(binding_options),
            "option_order_by_binding_and_presentation": stratify(binding_options, ("binding", "presentation"), pair_summary),
            "option_order_pairs": binding_options,
            "binding_change_summary": pair_summary(binding_changes),
            "binding_change_by_presentation": stratify(binding_changes, ("presentation",), pair_summary),
            "binding_change_pairs": binding_changes,
            "presentation_summary": pair_summary(presentations),
            "presentation_by_binding": stratify(presentations, ("binding",), pair_summary),
            "presentation_pairs": presentations,
        },
        "invalid_format_records": [row for row in rows if not row["format_valid"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=Path("output/cloudra_model_study_20261028/pilot_identity_binding"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    probes_path, results_path = args.pilot_dir / "frozen_probes.jsonl", args.pilot_dir / "results.json"
    probes_bytes, results_bytes = probes_path.read_bytes(), results_path.read_bytes()
    probes = [json.loads(line) for line in probes_bytes.decode().splitlines() if line.strip()]
    report = analyze(probes, json.loads(results_bytes))
    report["sources"] = {
        name: {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest()}
        for name, path, data in (("frozen_probes", probes_path, probes_bytes), ("results", results_path, results_bytes))
    }
    output = args.output or args.pilot_dir.parent / "identity_binding_analysis.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), "n_records": report["n_records"],
                      "format_failures": len(report["invalid_format_records"])}))


if __name__ == "__main__":
    main()
