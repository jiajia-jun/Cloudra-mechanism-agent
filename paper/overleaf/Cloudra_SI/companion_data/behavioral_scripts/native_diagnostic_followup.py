#!/usr/bin/env python3
"""Run an exploratory/error-conditioned native-chat diagnostic follow-up.

Select complete variants of the fixed stage-one error sources, retaining their
existing labels. This selected subset cannot estimate overall accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.model_semantics.native_chat_controls import run_native_cases
from scripts.model_semantics.run_local import json_request, write_json

IDENTITY_BASE_IDS = (
    "chemical_identity_06", "chemical_identity_07", "chemical_identity_11",
    "chemical_identity_12", "chemical_identity_14",
)
BINDING_BASE_IDS = (
    "brief-errors/r1/evt_8ed26719359e47e0",
    "brief-errors/r1/evt_f7ad8d7092784698",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    output = args.output.resolve()
    source = (args.source_run / "frozen_probes.jsonl").resolve()
    source_results = (args.source_run / "results.json").resolve()
    lines = source.read_text().splitlines()
    probes = [json.loads(line) for line in lines if line.strip()]
    selected_bases = set(IDENTITY_BASE_IDS + BINDING_BASE_IDS)
    selected = [probe for probe in probes if probe["base_case_id"] in selected_bases]
    expected_ids = {
        f"{base}/{variant}/{order}" for base in IDENTITY_BASE_IDS
        for variant in ("literal", "equivalent_rewrite") for order in ("forward", "swapped")
    } | {
        f"evidence_binding/{base}/{binding}/{presentation}/{order}"
        for base in BINDING_BASE_IDS for binding in ("coherent", "altered")
        for presentation in ("flat", "linked") for order in ("forward", "swapped")
    }
    if len(selected) != 36 or {probe["id"] for probe in selected} != expected_ids:
        raise ValueError("Expected twenty identity and sixteen binding inputs with all paired variants")
    prior_results = json.loads(source_results.read_text())
    if len(prior_results) != len(probes) or {row["id"] for row in prior_results} != {row["id"] for row in probes}:
        raise ValueError("Stage-one results do not cover the frozen inputs")
    model = "qwen3.8:27b"
    url = args.url.rstrip("/")
    metadata = next(item for item in json_request(f"{url}/api/tags")["models"] if item["name"] == model)
    original_deployment = json.loads((args.source_run / "deployment.json").read_text())
    if metadata["digest"] != original_deployment["digest"]:
        raise ValueError("Current model digest differs from the stage-one deployment")
    output.mkdir(parents=True, exist_ok=True)
    selected_ids = {probe["id"] for probe in selected}
    (output / "frozen_probes.jsonl").write_text(
        "".join(line + "\n" for line in lines if line.strip() and json.loads(line)["id"] in selected_ids)
    )
    write_json(output / "manifest.json", {
        "selection": "exploratory/error-conditioned follow-up",
        "selection_reason": "Fixed sources selected after inspecting stage-one errors; all complete variants retained.",
        "preregistered": False,
        "identity_base_case_ids": list(IDENTITY_BASE_IDS),
        "binding_base_case_ids": list(BINDING_BASE_IDS),
        "n_identity_inputs": 20, "n_binding_inputs": 16,
        "n_source_probes": len(selected), "thinking_modes": [False, True],
        "n_planned_native_requests": 2 * len(selected), "maximum_output_tokens": 1024,
        "source_probes": str(source),
        "source_probes_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_results": str(source_results),
        "source_results_sha256": hashlib.sha256(source_results.read_bytes()).hexdigest(),
        "n_stage_one_inputs": len(probes),
        "stage_one_errors_in_selected_sources": [
            {key: row[key] for key in ("id", "expected", "prediction")}
            for row in prior_results if row["id"] in selected_ids and not row["correct"]
        ],
        "model": metadata,
        "rendering": "Native /api/chat; no manually inserted model delimiters.",
        "labels": "Existing frozen labels copied unchanged; no new scientific judgments.",
        "scope": "Exploratory/error-conditioned local Qwen diagnostics; cannot estimate overall accuracy, original DeepSeek behavior or scientific acceptance.",
        "compute_limit": "Same maximum output budget, potentially different consumed computation; think changes native conditioning and generation together.",
    })
    run_native_cases(selected, output, url)


if __name__ == "__main__":
    main()
