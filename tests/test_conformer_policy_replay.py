from tests.test_conformer_ai_decision import decision_for
from tests.test_conformer_cards import cards_fixture
from tests.test_conformer_selection import context_for


def test_replay_has_equal_budget_and_evidence(tmp_path):
    from cloudra.tools.core.conformer_replay import replay_policy

    cards = cards_fixture(tmp_path)
    context = context_for(cards)
    decision = decision_for(cards)
    first = replay_policy(
        context, [decision], {}, max_actions=1, validation_standard="same", policy_name="recorded_legacy"
    )
    second = replay_policy(context, [decision], {}, max_actions=1, validation_standard="same", policy_name="regions")
    assert first.budget == second.budget == 1
    assert first.evidence_digest == second.evidence_digest


def test_unmeasured_branch_remains_unknown(tmp_path):
    from cloudra.tools.core.conformer_replay import replay_policy

    cards = cards_fixture(tmp_path)
    report = replay_policy(
        context_for(cards), [decision_for(cards)], {}, max_actions=1, validation_standard="same", policy_name="agent"
    )
    assert report.outcome == "unknown"
    assert report.actual_cpu_hours is None


def test_llm_cost_included_separately(tmp_path):
    from cloudra.tools.core.conformer_replay import ModelTelemetry, replay_policy

    cards = cards_fixture(tmp_path)
    report = replay_policy(
        context_for(cards),
        [decision_for(cards)],
        {},
        max_actions=1,
        validation_standard="same",
        policy_name="agent",
        model_telemetry=ModelTelemetry(calls=1, tokens=100, source="synthetic fixture"),
    )
    assert report.model_calls == 1
    assert report.model_tokens == 100
    assert report.model_monetary_cost is None
    assert report.actual_cpu_hours is None


def test_same_verdict_standard_across_policies(tmp_path):
    import pytest

    from cloudra.tools.core.conformer_replay import ReplayObservation, replay_policy

    cards = cards_fixture(tmp_path)
    cid = cards[0].candidate_ids[0]
    observation = ReplayObservation(
        outcome="verified",
        validation_standard="weaker",
        method_fingerprint="formal-method",
        evidence_refs=["fixture"],
        source_kind="synthetic",
    )
    with pytest.raises(ValueError, match="standard"):
        replay_policy(
            context_for(cards),
            [decision_for(cards)],
            {cid: observation},
            max_actions=1,
            validation_standard="same",
            policy_name="agent",
        )


def test_synthetic_verified_is_not_scientific_success(tmp_path):
    from cloudra.tools.core.conformer_replay import ReplayObservation, replay_policy

    cards = cards_fixture(tmp_path)
    cid = cards[0].candidate_ids[0]
    obs = ReplayObservation(
        outcome="verified",
        validation_standard="same",
        method_fingerprint="formal-method",
        evidence_refs=["fixture"],
        source_kind="synthetic",
        allocated_cpu_hours=1,
    )
    report = replay_policy(
        context_for(cards),
        [decision_for(cards)],
        {cid: obs},
        max_actions=1,
        validation_standard="same",
        policy_name="agent",
    )
    assert report.outcome == "synthetic_verified"
    assert report.actual_cpu_hours is None
    assert report.fixture_cpu_hours == 1


def test_replay_rejects_repeating_failed_candidate_under_new_decision_id(tmp_path):
    import pytest

    from cloudra.tools.core.conformer_replay import ReplayObservation, replay_policy

    cards = cards_fixture(tmp_path)
    first = decision_for(cards)
    second = first.model_copy(update={"decision_id": "new-id-same-failed-input"})
    observation = ReplayObservation(
        outcome="failed",
        validation_standard="same",
        method_fingerprint="formal-method",
        evidence_refs=["fixture"],
        source_kind="synthetic",
    )
    with pytest.raises(ValueError, match="same failed input"):
        replay_policy(
            context_for(cards),
            [first, second],
            {first.candidate_id: observation},
            max_actions=2,
            validation_standard="same",
            policy_name="agent",
        )


def test_recorded_fixture_cases_drive_three_equal_budget_policy_reports(tmp_path):
    import json
    from pathlib import Path

    from cloudra.tools.core.conformer_replay import ModelTelemetry, ReplayObservation, replay_policy

    fixture = json.loads((Path(__file__).parent / "fixtures/conformer_selection/replay_cases.json").read_text())
    cards = cards_fixture(tmp_path)
    decision = decision_for(cards)
    for case in fixture["cases"]:
        observations = {}
        if case.get("fixture_outcome"):
            observations[decision.candidate_id] = ReplayObservation(
                outcome=case["fixture_outcome"],
                validation_standard="same",
                method_fingerprint="formal-method",
                evidence_refs=[fixture["source"]],
                source_kind="synthetic",
                allocated_cpu_hours=case["fixture_cpu_hours"],
            )
        reports = [
            replay_policy(
                context_for(cards),
                [decision],
                observations,
                max_actions=1,
                validation_standard="same",
                policy_name=policy,
                model_telemetry=ModelTelemetry(calls=1, tokens=None, source="synthetic fixture")
                if policy == "regions_ai"
                else None,
            )
            for policy in ["recorded_legacy", "regions_default", "regions_ai"]
        ]
        assert len({r.evidence_digest for r in reports}) == 1
        assert all(r.budget == 1 and r.actual_cpu_hours is None for r in reports)
        assert all(r.outcome == ("synthetic_verified" if observations else "unknown") for r in reports)
