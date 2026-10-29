#!/usr/bin/env python3
"""Analyze the completed, error-conditioned native identity/binding follow-up."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.model_semantics.analyze_identity_binding import analyze, normalize


def index_unique(rows: list[dict], label: str) -> dict:
    indexed = {row["id"]: row for row in rows}
    if not rows or len(indexed) != len(rows):
        raise ValueError(f"Empty or duplicate IDs in {label}")
    return indexed


def generation_summary(rows: list[dict]) -> dict:
    counts = [row["eval_count"] for row in rows if row["eval_count"] is not None]
    return {"available": len(counts), "missing": len(rows) - len(counts),
            "total": sum(counts) if counts else None,
            "minimum": min(counts) if counts else None, "maximum": max(counts) if counts else None}


def outcome(probe: dict, result: dict, native: bool) -> dict:
    row = normalize(probe, result)
    # Stage-one rows lack generation counts; retain the native saved metadata.
    metadata = result if native else json.loads(Path(result["response_file"]).read_text())["response"]
    row.update({key: metadata.get(key) for key in ("done_reason", "eval_count", "prompt_eval_count")})
    row["thinking_chars"] = result.get("thinking_chars") if native else None
    row["budget_truncated"] = row["done_reason"] == "length"
    if row["budget_truncated"]:
        row["status"] = "budget_truncated"
    elif row["correct"]:
        row["status"] = "correct"
    elif row["format_valid"]:
        row["status"] = "valid_wrong"
    else:
        row["status"] = "invalid_format_without_truncation"
    return row


def summarize(rows: list[dict]) -> dict:
    counts = Counter(row["status"] for row in rows)
    return {
        "n_inputs": len(rows), "n_distinct_bases": len({row["base_case_id"] for row in rows}),
        **{status: counts[status] for status in (
            "correct", "valid_wrong", "budget_truncated", "invalid_format_without_truncation",
        )},
        "budget_truncated_ids": [row["id"] for row in rows if row["budget_truncated"]],
        "budget_truncated_with_valid_choice": sum(row["budget_truncated"] and row["format_valid"] for row in rows),
        "done_reason_counts": dict(Counter(str(row["done_reason"]) for row in rows)),
        "generated_tokens": generation_summary(rows),
    }


def compare(left: list[dict], right: list[dict]) -> dict:
    left_index, right_index = index_unique(left, "left comparison"), index_unique(right, "right comparison")
    if set(left_index) != set(right_index):
        raise ValueError("Mode comparison IDs differ")
    pairs = []
    for identifier, first in left_index.items():
        second = right_index[identifier]
        valid = first["status"] in {"correct", "valid_wrong"} and second["status"] in {"correct", "valid_wrong"}
        pairs.append({
            "id": identifier, "base_case_id": first["base_case_id"], "family": first["family"],
            "status_transition": first["status"] + " -> " + second["status"],
            "left_status": first["status"], "right_status": second["status"],
            "left_prediction": first["prediction"], "right_prediction": second["prediction"],
            "both_nontruncated_valid_choices": valid,
            "semantic_same": first["selected_meaning"] == second["selected_meaning"] if valid else None,
            "left_generated_tokens": first["eval_count"], "right_generated_tokens": second["eval_count"],
            "left_response_file": first["response_file"], "right_response_file": second["response_file"],
        })
    return {
        "n_matched_inputs": len(pairs),
        "by_family": [{
            "family": family, "n_matched_inputs": len(group),
            "n_distinct_bases": len({row["base_case_id"] for row in group}),
            "status_transitions": dict(Counter(row["status_transition"] for row in group)),
            "both_nontruncated_valid_choices": sum(row["both_nontruncated_valid_choices"] for row in group),
            "semantic_same": sum(row["semantic_same"] is True for row in group),
            "semantic_changed": sum(row["semantic_same"] is False for row in group),
        } for family in ("chemical_identity", "evidence_binding")
            if (group := [row for row in pairs if row["family"] == family])],
        "pairs": pairs,
    }


def build(pilot_dir: Path) -> dict:
    paths = {"manifest": pilot_dir / "manifest.json", "frozen_probes": pilot_dir / "frozen_probes.jsonl",
             "results": pilot_dir / "results.json"}
    content = {key: path.read_bytes() for key, path in paths.items()}
    manifest = json.loads(content["manifest"])
    probes = [json.loads(line) for line in content["frozen_probes"].decode().splitlines() if line.strip()]
    results = json.loads(content["results"])
    frozen = index_unique(probes, "native frozen probes")
    if len(probes) != 36 or len(results) != 72 or any(type(row.get("thinking")) is not bool for row in results):
        raise ValueError("Expected exactly 36 frozen inputs and 72 native results in two boolean thinking modes")
    paths.update({"stage_one_probes": Path(manifest["source_probes"]),
                  "stage_one_results": Path(manifest["source_results"])})
    for name, manifest_key in (("stage_one_probes", "source_probes_sha256"),
                               ("stage_one_results", "source_results_sha256")):
        content[name] = paths[name].read_bytes()
        if hashlib.sha256(content[name]).hexdigest() != manifest[manifest_key]:
            raise ValueError(f"Frozen stage-one source changed: {name}")
    original_probes = index_unique(
        [json.loads(line) for line in content["stage_one_probes"].decode().splitlines() if line.strip()], "stage-one probes")
    original_results = index_unique(json.loads(content["stage_one_results"]), "stage-one results")
    if set(original_probes) != set(original_results) or not set(frozen) <= set(original_probes):
        raise ValueError("Incomplete stage-one coverage or native inputs absent from stage one")
    if any(probe != original_probes[identifier] for identifier, probe in frozen.items()):
        raise ValueError("Native follow-up changed the frozen stage-one input")
    identity_bases = {probe["base_case_id"] for probe in probes if probe["mainline"].startswith("chemical_identity/")}
    binding_bases = {probe["base_case_id"] for probe in probes if probe["mainline"] == "B"}
    if (identity_bases != set(manifest["identity_base_case_ids"]) or len(identity_bases) != 5
            or binding_bases != set(manifest["binding_base_case_ids"]) or len(binding_bases) != 2):
        raise ValueError("Expected the selected five identity pairs and two binding cases")
    modes = {"raw_stage_one_selected": [original_results[probe["id"]] for probe in probes],
             "native_think_false": [row for row in results if row["thinking"] is False],
             "native_think_true": [row for row in results if row["thinking"] is True]}
    # This reused analyzer checks exact IDs, unique results and complete paired grids.
    analyses = {mode: analyze(probes, records) for mode, records in modes.items()}
    rows = {mode: [outcome(frozen[row["id"]], row, native=mode != "raw_stage_one_selected") for row in records]
            for mode, records in modes.items()}
    return {
        "scope": {
            "selection": "Error-conditioned exploratory follow-up: five chemical identity pairs and two evidence chains were selected after stage-one errors; every selected base retains all variants.",
            "denominator": "The same 36 frozen inputs per mode: 20 chemical inputs from five base pairs and 16 binding inputs from two base cases. Variants are repeated decisions, not independent chemistry samples.",
            "budget": "done_reason=length is a budget-truncated generation, not a demonstrated reasoning error. Keep all 20/16 family inputs in the denominator; never report only answered inputs as overall accuracy.",
            "generation": "eval_count is consumed generated tokens, including thinking where enabled. The maximum budget is shared but consumed computation is not matched.",
            "reuse": "Paired diagnostics use analyze_identity_binding.analyze unchanged. Its format_failures include no-answer budget truncations; the disjoint status summaries here separate those from other invalid formats and valid wrong choices.",
            "rendering_contrast": "raw_stage_one_selected vs native_think_false holds each frozen question fixed but changes API rendering; differences describe these saved requests only.",
            "limits": "Cannot estimate overall accuracy, scientific acceptance, original DeepSeek behavior or its internal mechanism. Geometry native32 and its 2048-token follow-up are excluded.",
        },
        "maximum_output_tokens": manifest["maximum_output_tokens"],
        "selected_identity_base_case_ids": sorted(identity_bases), "selected_binding_base_case_ids": sorted(binding_bases),
        "modes": {mode: {
            "summary": summarize(records),
            "by_family": [{"family": family, **summarize([row for row in records if row["family"] == family])}
                          for family in ("chemical_identity", "evidence_binding")],
            "paired_diagnostic_analysis": analyses[mode], "generation_records": records,
        } for mode, records in rows.items()},
        "raw_to_native_false": compare(rows["raw_stage_one_selected"], rows["native_think_false"]),
        "native_false_to_true": compare(rows["native_think_false"], rows["native_think_true"]),
        "sources": {name: {"path": str(path.resolve()), "sha256": hashlib.sha256(content[name]).hexdigest()}
                    for name, path in paths.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=Path("output/cloudra_model_study_20261028/pilot_native_diagnostic"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build(args.pilot_dir)
    output = args.output or args.pilot_dir.parent / "native_diagnostic_analysis.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()),
                      "by_mode_and_family": {mode: record["by_family"] for mode, record in report["modes"].items()}}, indent=2))


if __name__ == "__main__":
    main()
