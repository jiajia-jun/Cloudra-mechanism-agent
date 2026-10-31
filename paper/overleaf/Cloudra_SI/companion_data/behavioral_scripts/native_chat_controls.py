#!/usr/bin/env python3
"""Check native chat rendering and thinking on the four frozen geometry sources.

This exploratory follow-up uses the same maximum decoding budget in both modes.
Consumed computation can differ; it is not a compute-matched causal comparison.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError

from scripts.model_semantics.run_local import (
    choice_letters,
    choice_system_prompt,
    json_request,
    request_key,
    write_json,
)


def run_native_cases(
    cases: list[dict], output: Path, url: str, thinking_modes: tuple[bool, ...] = (False, True),
) -> list[dict]:
    """Run native requests using the deployment frozen in output/manifest.json."""
    output = output.resolve()
    responses = output / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((output / "manifest.json").read_text())["model"]
    model = metadata["name"]
    results = []
    for thinking in thinking_modes:
        for case in cases:
            payload = {"model": model, "messages": [
                {"role": "system", "content": choice_system_prompt(case)},
                {"role": "user", "content": case["prompt"]}],
                "stream": False, "think": thinking,
                "options": {"temperature": 0, "seed": 42, "num_predict": 1024,
                            "num_ctx": 8192, "top_k": 0, "top_p": 1, "min_p": 0,
                            "repeat_penalty": 1, "presence_penalty": 0, "draft_num_predict": 0}}
            key = request_key(payload, metadata["digest"])
            path = responses / f"{key}.json"
            if path.exists():
                record = json.loads(path.read_text())
            else:
                try:
                    native = json_request(f"{url}/api/chat", payload)
                except HTTPError as error:
                    write_json(path, {"request": payload, "status": error.code, "body": error.read().decode()})
                    raise
                record = {"request": payload, "response": native}
                write_json(path, record)
            native = record["response"]
            content = native["message"].get("content", "").strip()
            choice = content if content in choice_letters(case) else None
            row = {"id": case["id"], "condition": case["condition"], "thinking": thinking,
                   "expected": case["expected"], "prediction": choice,
                   "format_valid": choice is not None, "correct": choice == case["expected"],
                   "done_reason": native.get("done_reason"),
                   "prompt_eval_count": native.get("prompt_eval_count"), "eval_count": native.get("eval_count"),
                   "thinking_chars": len(native["message"].get("thinking", "")),
                   "response_file": str(path), "content": content}
            results.append(row)
            write_json(output / "results.json", results)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = "qwen3.8:27b"
    metadata = next(item for item in json_request(f"{args.url}/api/tags")["models"] if item["name"] == model)
    cases = [json.loads(line) for line in (args.source_run / "frozen_probes.jsonl").read_text().splitlines()]
    selected = [case for case in cases
                if case["condition"] in {"original_xyz", "tool_distances"}]
    source_ids = sorted({case["base_case_id"] for case in selected})
    if len(source_ids) != 4 or len(selected) != 16:
        raise ValueError("Expected four frozen geometry sources and sixteen counterbalanced inputs")
    (output / "frozen_probes.jsonl").write_text(
        "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in selected)
    )
    write_json(output / "manifest.json", {
        "selection": "All four previously frozen NB1 sources, both option orders, XYZ and measured distances.",
        "source_ids": source_ids,
        "model": metadata, "n_source_probes": len(selected), "maximum_output_tokens": 1024,
        "rendering": "Native /api/chat; no manually inserted model delimiters.",
        "scope": "Four-source exploratory rendering/thinking control, not general geometry or scientific acceptance.",
        "compute_limit": "Same maximum output budget, potentially different consumed computation."})
    run_native_cases(selected, output, args.url)


if __name__ == "__main__":
    main()
