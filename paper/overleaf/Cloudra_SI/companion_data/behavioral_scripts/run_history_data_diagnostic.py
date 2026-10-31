#!/usr/bin/env python3
"""Execute counted, frozen history-data requests with the shared local runner.

Historical messages remain quoted data. This is not the original provider's
wire prompt or an autonomous research replay. No inputs are truncated here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.model_semantics.run_local import run, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--conditions", nargs="+", choices=("report_alone", "window_12", "full_306"),
                        default=("report_alone", "window_12"))
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    manifest = json.loads((args.input_dir / "manifest.json").read_text())
    cases = [json.loads(line) for line in (args.input_dir / "frozen_probes.jsonl").read_text().splitlines()]
    selected = [case for case in cases if case["condition"] in args.conditions]
    if not selected or any(case["label_status"] != "known" or not case["executable_under_metadata_limit"]
                           for case in selected):
        raise ValueError("Selected inputs lack supported labels or exceed the counted capacity")
    payloads = {case["id"]: json.loads(Path(case["request_file"]).read_text()) for case in selected}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "frozen_probes.jsonl").write_text(
        "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in selected)
    )
    write_json(output / "manifest.json", {
        "source_manifest": str((args.input_dir / "manifest.json").resolve()),
        "conditions": args.conditions, "n": len(selected),
        "deployment_digest": manifest["deployment_digest"],
        "execution": "Exact counted request JSON through run_local.run; no prompt rebuilding or truncation.",
        "scope": "Three quoted-history questions from one IA1 case; not original research or scientific acceptance.",
        "http_timeout_seconds": 3600 if "full_306" in args.conditions else 300,
    })
    run(selected, output, args.url.rstrip("/"), manifest["model"],
        frozen_requests=payloads, deployment_digest=manifest["deployment_digest"],
        request_timeout=3600 if "full_306" in args.conditions else 300)
    results = {row["id"]: row for row in json.loads((output / "results.json").read_text())}
    count_observations = []
    for case in selected:
        row = results[case["id"]]
        count_observations.append({
            "id": case["id"], "counted_input_tokens": case["raw_prompt_token_count"],
            "configured_num_ctx": case["configured_num_ctx"],
            "reported_prompt_eval_count": row["prompt_eval_count"],
            "reported_count_matches": row["prompt_eval_count"] == case["raw_prompt_token_count"],
        })
    write_json(output / "token_count_observations.json", {
        "records": count_observations,
        "interpretation": "Compare native reported counts with exact vocabulary counts; a discrepancy requires investigation, not a model-error label. Counts alone do not prove semantic retention.",
    })


if __name__ == "__main__":
    main()
