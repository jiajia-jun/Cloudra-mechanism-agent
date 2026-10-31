#!/usr/bin/env python3
"""Sparse last-position interventions for one preselected formal geometry case.

Includes an option-swapped donor and an unrelated same-answer donor. A transferred
answer preference alone is not evidence for a geometry-specific representation.
The exact raw prompts come from the completed native diagnostic run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def choice_metrics(directory: Path) -> dict:
    metadata = json.loads((directory / "metadata.json").read_text())
    logits = np.fromfile(directory / "logits.f32", dtype="<f4").astype(float)
    log_z = float(np.logaddexp.reduce(logits))
    masses = {}
    for choice in ("A", "B"):
        candidates = [metadata["choice_token_ids"][text] for text in (choice, " " + choice)]
        if any(len(ids) != 1 for ids in candidates):
            raise ValueError("This pilot requires single-token choice spellings")
        ids = sorted({item[0] for item in candidates})
        masses[choice] = float(np.logaddexp.reduce(logits[ids]))
    return {"top1": metadata["top_tokens"][0],
            "log_mass_A_minus_B": masses["A"] - masses["B"],
            "all_vocab_probability_A": float(np.exp(masses["A"] - log_z)),
            "all_vocab_probability_B": float(np.exp(masses["B"] - log_z)),
            "token_count": len(metadata["token_ids"]),
            "global_token_position": metadata["global_token_position"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner", type=Path, default=Path("/private/tmp/cloudra-model-interpretability/activation_runner"))
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases = [json.loads(line) for line in (args.source_run / "frozen_probes.jsonl").read_text().splitlines()]
    results = json.loads((args.source_run / "results.json").read_text())
    rows = {row["id"]: row for row in results}
    seed = "geometry/guided/r1/evt_9964bbb2ba494123"
    chosen = {
        "xyz": seed + "/original_xyz/forward",
        "distances": seed + "/tool_distances/forward",
        "swapped_distances": seed + "/tool_distances/swapped",
        "unrelated_completion": next(case["id"] for case in cases
                                     if case["mainline"] == "B" and case["condition"] == "raw"
                                     and rows[case["id"]]["prediction"] == "B"
                                     and rows[case["id"]]["correct"]),
    }
    source_records = {}
    for name, case_id in chosen.items():
        row = rows[case_id]
        record = json.loads(Path(row["response_file"]).read_text())
        prompt = record["request"]["prompt"]
        path = output / f"{name}.prompt.txt"
        if path.exists() and path.read_text() != prompt:
            raise ValueError(f"Existing prompt differs: {path}")
        path.write_text(prompt, encoding="utf-8")
        source_records[name] = {"case_id": case_id, "expected": row["expected"],
                                "native_prediction": row["prediction"],
                                "native_response_file": row["response_file"],
                                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
    manifest = {"selection": "Prescribed NB1 seed fixed before model results; donors are its distance view, its swapped options, and first correct raw B-line B-answer control.",
                "sources": source_records, "patch_layer": 31, "capture_layers": [7, 15, 31, 47, 63],
                "interpretation_limits": ["One geometry case only; exploratory interventions.",
                                          "Representation and prompt length differ between XYZ and distance views.",
                                          "A last-position donor can transfer answer preference without transferring geometry reasoning.",
                                          "Unrelated and option-swapped donors test this alternative; no intervention alone establishes a geometry circuit."]}
    write_json(output / "manifest.json", manifest)
    trials = [("xyz_baseline", "xyz", None, None),
              ("xyz_capture", "xyz", "7,15,31,47,63", None),
              ("distances_capture", "distances", "7,15,31,47,63", None),
              ("swapped_distances_capture", "swapped_distances", "31", None),
              ("unrelated_completion_capture", "unrelated_completion", "31", None),
              ("xyz_self_patch", "xyz", None, "xyz_capture"),
              ("xyz_distance_patch", "xyz", None, "distances_capture"),
              ("xyz_swapped_distance_patch", "xyz", None, "swapped_distances_capture"),
              ("xyz_unrelated_patch", "xyz", None, "unrelated_completion_capture")]
    measured = {}
    for name, prompt_name, capture, donor in trials:
        target = output / name
        command = [str(args.runner), "--model", str(args.model), "--prompt",
                   str(output / f"{prompt_name}.prompt.txt"), "--out", str(target)]
        if capture:
            command += ["--capture", capture]
        if donor:
            command += ["--patch", str(output / donor / "capture-31.f32"), "--patch-layer", "31"]
        if not (target / "metadata.json").exists():
            target.mkdir(exist_ok=True)
            write_json(target / "command.json", command)
            with (target / "run.log").open("w") as stream:
                subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
        measured[name] = choice_metrics(target)
        write_json(output / "measurements.json", measured)
        print(name, json.dumps(measured[name], ensure_ascii=False), flush=True)
    baseline = np.fromfile(output / "xyz_baseline/logits.f32", dtype="<f4")
    controls = {}
    for name in ("xyz_capture", "xyz_self_patch"):
        values = np.fromfile(output / name / "logits.f32", dtype="<f4")
        controls[name] = {"all_vocab_exactly_equal": bool(np.array_equal(baseline, values)),
                          "max_absolute_logit_difference": float(np.max(np.abs(baseline - values)))}
    write_json(output / "controls.json", controls)


if __name__ == "__main__":
    main()
