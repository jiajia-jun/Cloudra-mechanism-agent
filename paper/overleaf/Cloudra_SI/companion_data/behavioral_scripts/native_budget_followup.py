#!/usr/bin/env python3
"""Retry saved native-chat budget truncations with only num_predict raised to 2048.

Original requests and responses stay untouched. Expected choices remain offline
labels and are never added to the model payload.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from urllib.error import HTTPError

from scripts.model_semantics.run_local import json_request, request_key, write_json


def run(source_run: Path, output: Path, url: str) -> list[dict]:
    source_run, output = source_run.resolve(), output.resolve()
    if output == source_run:
        raise ValueError("Follow-up output must differ from the original run directory")
    original_manifest = json.loads((source_run / "manifest.json").read_text())
    original_results = json.loads((source_run / "results.json").read_text())
    selected = [row for row in original_results if row["done_reason"] == "length"]
    if not selected:
        raise ValueError("No budget-truncated records in the original results")
    original_model = original_manifest["model"]
    metadata = next(item for item in json_request(f"{url}/api/tags")["models"]
                    if item["name"] == original_model["name"])
    if metadata["digest"] != original_model["digest"]:
        raise ValueError("Current model digest differs from the original native-chat run")
    responses = output / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    write_json(output / "manifest.json", {
        "source_run": str(source_run), "model": metadata, "n_selected": len(selected),
        "selection": "Original results with done_reason=length only.",
        "change": {"options.num_predict": 2048},
        "scope": "Budget follow-up of this frozen local Qwen diagnostic only; original results remain separate.",
        "expected_labels": "Copied offline from original results; never sent to the model.",
    })
    results = []
    for row in selected:
        source_path = Path(row["response_file"])
        original = json.loads(source_path.read_text())
        if original["response"]["done_reason"] != "length":
            raise ValueError(f"Saved native response is not budget-truncated: {source_path}")
        payload = copy.deepcopy(original["request"])
        if payload["model"] != metadata["name"]:
            raise ValueError(f"Saved request model differs from the original manifest: {source_path}")
        payload["options"]["num_predict"] = 2048
        key = request_key(payload, metadata["digest"])
        path = responses / f"{key}.json"
        if path.exists():
            record = json.loads(path.read_text())
            if record["request"] != payload:
                raise ValueError(f"Saved follow-up request differs: {path}")
        else:
            record = {"request_key": key, "source_response_file": str(source_path),
                      "request": payload}
            try:
                record["response"] = json_request(f"{url}/api/chat", payload)
            except HTTPError as error:
                record.update({"http_error": error.code, "body": error.read().decode()})
                write_json(path, record)
                raise
            write_json(path, record)
        native = record["response"]
        content = native["message"].get("content", "").strip()
        prediction = content if content in {"A", "B"} else None
        result = {"id": row["id"], "condition": row["condition"],
                  "thinking": payload["think"], "expected": row["expected"],
                  "prediction": prediction, "format_valid": prediction is not None,
                  "correct": prediction == row["expected"],
                  "done_reason": native.get("done_reason"),
                  "budget_truncated": native.get("done_reason") == "length",
                  "prompt_eval_count": native.get("prompt_eval_count"),
                  "eval_count": native.get("eval_count"),
                  "thinking_chars": len(native["message"].get("thinking", "")),
                  "source_response_file": str(source_path),
                  "response_file": str(path), "content": content}
        results.append(result)
        write_json(output / "results.json", results)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    run(args.source_run, args.output, args.url.rstrip("/"))


if __name__ == "__main__":
    main()
