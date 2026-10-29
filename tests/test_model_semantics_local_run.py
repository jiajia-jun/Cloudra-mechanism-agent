"""Research records must preserve interventions and formatting failures."""

from scripts.model_semantics import run_local
from scripts.model_semantics.run_local import case_request, parse_choice, request_key


def test_changed_observation_cannot_reuse_the_original_request_record():
    case = {"id": "same-source", "prompt": "Required frequency evidence is missing."}
    changed = {**case, "prompt": "Required frequency evidence is available."}
    original = case_request(case, "local-model")
    counterfactual = case_request(changed, "local-model")
    assert request_key(original, "weights-a") != request_key(counterfactual, "weights-a")
    assert request_key(original, "weights-a") != request_key(original, "weights-b")
    assert case["prompt"] in original["prompt"]
    assert changed["prompt"] in counterfactual["prompt"]


def test_free_text_is_not_silently_converted_into_a_correct_choice():
    assert parse_choice({"response": " A\n"}) == "A"
    assert parse_choice({"response": "B"}) == "B"
    assert parse_choice({"response": "A because the task is complete"}) is None
    assert parse_choice({"response": "I choose B"}) is None
    assert parse_choice({"response": ""}) is None


def test_requesting_missing_measurement_is_a_valid_third_action_only_when_offered():
    assert parse_choice({"response": "C"}) is None
    assert parse_choice({"response": "C"}, ("A", "B", "C")) == "C"
    assert parse_choice({"response": "C because evidence is missing"}, ("A", "B", "C")) is None
    case = {"prompt": "Choose a next action.", "choices": {"A": "use first", "B": "use second", "C": "measure"}}
    payload = case_request(case, "local-model")
    assert "from A, B, C" in payload["prompt"]


def test_counted_history_request_keeps_its_larger_context_in_the_actual_submission(tmp_path, monkeypatch):
    case = {"id": "history", "base_case_id": "source", "mainline": "B", "condition": "window",
            "prompt": "Read the quoted history.", "expected": "A"}
    frozen = case_request(case, "local-model")
    frozen["options"]["num_ctx"] = 16384
    submitted = []

    def fake_request(url, payload=None, **_):
        if url.endswith("/api/tags"):
            return {"models": [{"name": "local-model", "digest": "weights-a"}]}
        submitted.append(payload)
        return {"response": "A", "prompt_eval_count": 12000}

    monkeypatch.setattr(run_local, "json_request", fake_request)
    run_local.run([case], tmp_path, "http://local", "local-model",
                  frozen_requests={"history": frozen}, deployment_digest="weights-a")
    assert submitted == [frozen]
    assert submitted[0]["options"]["num_ctx"] == 16384
    assert "expected" not in submitted[0]
