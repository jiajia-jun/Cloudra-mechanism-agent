#!/usr/bin/env python3
"""Run frozen diagnostic choice probes on the local Qwen deployment.

These are localised decisions, not re-executions of the original DeepSeek runs.
Every exact request, native response and expected label remains inspectable.
No constrained decoding is used; format failures remain separate observations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SYSTEM_PROMPT = (
    "You assist a computational chemist. Answer the given diagnostic with exactly "
    "one uppercase choice letter, A or B. Do not add explanations."
)


def choice_letters(case: dict) -> tuple[str, ...]:
    return tuple(case["choices"]) if "choices" in case else ("A", "B")


def choice_system_prompt(case: dict) -> str:
    letters = choice_letters(case)
    if letters == ("A", "B"):
        return SYSTEM_PROMPT
    return (
        "You assist a computational chemist. Answer the given diagnostic with exactly "
        "one uppercase choice letter from " + ", ".join(letters) + ". Do not add explanations."
    )


def case_request(case: dict, model: str) -> dict:
    prompt = (
        f"<|im_start|>system\n{choice_system_prompt(case)}<|im_end|>\n"
        f"<|im_start|>user\n{case['prompt']}<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
    return {"model": model, "prompt": prompt, "raw": True, "think": False,
            "stream": False, "logprobs": True, "top_logprobs": 20,
            "options": {"temperature": 0, "seed": 42, "num_predict": 8,
                        "num_ctx": 8192, "top_k": 0, "top_p": 1, "min_p": 0,
                        "repeat_penalty": 1, "presence_penalty": 0, "draft_num_predict": 0}}


def request_key(payload: dict, model_digest: str) -> str:
    data = json.dumps([model_digest, payload], sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def parse_choice(response: dict, letters: tuple[str, ...] = ("A", "B")) -> str | None:
    text = response.get("response", "").strip()
    return text if text in letters else None


def json_request(url: str, payload: dict | None = None, *, timeout: float = 300) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(cases: list[dict], output: Path, url: str, model: str, *,
        frozen_requests: dict[str, dict] | None = None, deployment_digest: str | None = None,
        request_timeout: float = 300) -> dict:
    if frozen_requests is not None and set(frozen_requests) != {case["id"] for case in cases}:
        raise ValueError("Frozen request IDs differ from selected cases")
    output.mkdir(parents=True, exist_ok=True)
    responses = output / "responses"
    responses.mkdir(exist_ok=True)
    metadata = next(item for item in json_request(f"{url}/api/tags")["models"]
                    if item["name"] == model)
    if deployment_digest is not None and metadata["digest"] != deployment_digest:
        raise ValueError("Current deployment differs from the frozen request deployment")
    write_json(output / "deployment.json", metadata)
    results = []
    groups = defaultdict(list)
    for index, case in enumerate(cases):
        payload = frozen_requests[case["id"]] if frozen_requests is not None else case_request(case, model)
        if payload["model"] != model:
            raise ValueError("Frozen request model differs from selected deployment")
        key = request_key(payload, metadata["digest"])
        path = responses / f"{key}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
        else:
            try:
                native = json_request(f"{url}/api/generate", payload, timeout=request_timeout)
            except HTTPError as error:
                write_json(path, {"request_key": key, "request": payload,
                                  "http_error": error.code, "body": error.read().decode()})
                raise
            record = {"request_key": key, "request": payload, "response": native}
            write_json(path, record)
        if "response" not in record:
            raise ValueError(f"Saved request failed; inspect {path}")
        prediction = parse_choice(record["response"], choice_letters(case))
        row = {"id": case["id"], "base_case_id": case["base_case_id"],
               "mainline": case["mainline"], "condition": case["condition"],
               "expected": case["expected"], "prediction": prediction,
               "correct": prediction == case["expected"], "format_valid": prediction is not None,
               "response_file": str(path.resolve()),
               "prompt_eval_count": record["response"].get("prompt_eval_count"),
               "raw_response": record["response"].get("response", "")}
        results.append(row)
        groups[(row["mainline"], row["condition"])].append(row)
        write_json(output / "results.json", results)
        print(f"{index + 1}/{len(cases)} {row['id']}: {prediction} (expected {row['expected']})", flush=True)
    with (output / "results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    summary = {"n": len(results), "model": metadata,
               "by_condition": [{"mainline": line, "condition": condition, "n": len(rows),
                                 "correct": sum(row["correct"] for row in rows),
                                 "format_failures": sum(not row["format_valid"] for row in rows)}
                                for (line, condition), rows in sorted(groups.items())],
               "scope": "Frozen localised diagnostic probes; not independent chemistry tasks or original run success rates.",
               "decoding": "Raw explicit ChatML research prompt, thinking disabled, greedy; no answer grammar.",
               "probability_limit": "Native top-20 log probabilities are retained; an absent choice is censored, not probability zero."}
    write_json(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="qwen3.8:27b")
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    cases = [json.loads(line) for path in args.input for line in path.read_text().splitlines() if line.strip()]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Probe IDs must be nonempty and unique")
    write_path = args.output.resolve()
    write_path.mkdir(parents=True, exist_ok=True)
    with (write_path / "frozen_probes.jsonl").open("w", encoding="utf-8") as stream:
        for case in cases:
            stream.write(json.dumps(case, ensure_ascii=False) + "\n")
    print(json.dumps(run(cases, write_path, args.url.rstrip("/"), args.model), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
