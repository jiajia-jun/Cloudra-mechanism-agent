#!/usr/bin/env python3
"""Single-token reported-distance intervention, with both option orders.

Only the first digit of one displayed measurement changes: 2.029 -> 1.029.
The second measurement stays 1.248. This is an explicitly synthetic numerical
comparison, not a new molecular calculation or a modified scientific log.
Matched token positions isolate fact transmission from answer-label transfer.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

from scripts.model_semantics.run_activation_pilot import choice_metrics, write_json


def run_trial(runner: Path, model: Path, prompt: Path, target: Path,
              position: int, capture: str | None = None, donor: Path | None = None,
              layer: int = 31) -> dict:
    if not (target / "metadata.json").exists():
        target.mkdir(parents=True, exist_ok=True)
        command = [str(runner), "--model", str(model), "--prompt", str(prompt),
                   "--out", str(target), "--token-position", str(position)]
        if capture:
            command += ["--capture", capture]
        if donor:
            command += ["--patch", str(donor), "--patch-layer", str(layer)]
        write_json(target / "command.json", command)
        with (target / "run.log").open("w") as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    return choice_metrics(target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry-pilot", type=Path, required=True)
    parser.add_argument("--position-validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--runner", type=Path, default=Path("/private/tmp/cloudra-model-interpretability/activation_runner"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prefix_donor = args.position_validation / "read_position0/capture-31.f32"
    mapping = json.loads((args.position_validation / "read_position0/metadata.json").read_text())
    chunks = [bytes.fromhex(value) for value in mapping["input_token_bytes_hex"]]
    original_bytes = b"".join(chunks)
    fact_start = original_bytes.index(b"2.029")
    offsets = np.cumsum([0, *[len(value) for value in chunks]])
    positions = [i for i, value in enumerate(chunks)
                 if offsets[i] == fact_start and value == b"2"]
    if len(positions) != 1:
        raise ValueError("Source measurement digit is not one exactly aligned token")
    position = positions[0]
    manifest = {"source": str(args.geometry_pilot.resolve()), "fact_token_position": position,
                "changed_measurement": {"source": "2.029", "counterfactual": "1.029", "unchanged_other": "1.248"},
                "synthetic": True, "patch_layers_fixed_before_results": [7, 15, 31, 47],
                "controls": ["same-corrupt-state self-patch at the fact token", "unchanged-prefix patch at token 0", "both answer-option orders"],
                "scope": "Transmission of a reported numerical fact in one short comparison. Not XYZ computation, scientific validity, original DeepSeek mechanism or a chemistry neuron."}
    write_json(output / "manifest.json", manifest)
    results, checks = {}, {}
    for order, filename in (("forward", "distances.prompt.txt"), ("swapped", "swapped_distances.prompt.txt")):
        folder = output / order
        folder.mkdir(exist_ok=True)
        clean = (args.geometry_pilot / filename).read_text()
        if clean.count("2.029") != 1:
            raise ValueError("Measurement must occur exactly once")
        corrupt = clean.replace("2.029", "1.029", 1)
        clean_path, corrupt_path = folder / "clean.prompt.txt", folder / "counterfactual.prompt.txt"
        clean_path.write_text(clean)
        corrupt_path.write_text(corrupt)
        measured = {}
        for name, path in (("clean", clean_path), ("corrupt", corrupt_path)):
            measured[name] = run_trial(args.runner, args.model, path, folder / name,
                                       position, capture="7,15,31,47")
        clean_meta = json.loads((folder / "clean/metadata.json").read_text())
        corrupt_meta = json.loads((folder / "corrupt/metadata.json").read_text())
        if len(clean_meta["token_ids"]) != len(corrupt_meta["token_ids"]):
            raise ValueError("Clean and counterfactual token counts differ")
        differences = [i for i, (a, b) in enumerate(zip(clean_meta["token_ids"], corrupt_meta["token_ids"], strict=True)) if a != b]
        if differences != [position]:
            raise ValueError(f"Expected one changed token at {position}, observed {differences}")
        for layer in (7, 15, 31, 47):
            name = f"fact_patch_layer{layer}"
            measured[name] = run_trial(args.runner, args.model, corrupt_path, folder / name,
                                       position, donor=folder / f"clean/capture-{layer}.f32", layer=layer)
        measured["self_patch"] = run_trial(args.runner, args.model, corrupt_path, folder / "self_patch",
                                             position, donor=folder / "corrupt/capture-31.f32")
        measured["prefix_control"] = run_trial(args.runner, args.model, corrupt_path, folder / "prefix_control",
                                                 0, donor=prefix_donor)
        baseline = np.fromfile(folder / "corrupt/logits.f32", dtype="<f4")
        checks[order] = {"changed_token_positions": differences,
                         "clean_expected": "B" if order == "forward" else "A",
                         "counterfactual_expected": "A" if order == "forward" else "B"}
        for name in ("self_patch", "prefix_control"):
            values = np.fromfile(folder / name / "logits.f32", dtype="<f4")
            checks[order][name] = {"all_vocab_exactly_equal": bool(np.array_equal(baseline, values)),
                                   "max_absolute_logit_difference": float(np.max(np.abs(baseline - values)))}
        results[order] = measured
        write_json(output / "measurements.json", results)
        write_json(output / "controls.json", checks)
        print(order, json.dumps(measured, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
