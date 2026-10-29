"""Matched probes must not turn answer position or sample composition into effects."""

import pytest


def report_pair(base_case_id, condition, predictions):
    probes, results = [], []
    for order, choices, expected, prediction in (
        ("original", ["continue_work", "final_delivery_review"], "A", predictions[0]),
        ("reversed", ["final_delivery_review", "continue_work"], "B", predictions[1]),
    ):
        identifier = f"B/{base_case_id}/{condition}/{order}"
        probes.append({
            "id": identifier, "mainline": "B", "base_case_id": base_case_id,
            "condition": condition, "choice_order": choices, "expected": expected,
            "expected_action": "continue_work", "source": {"task": "NB1"},
        })
        results.append({
            "id": identifier, "mainline": "B", "base_case_id": base_case_id,
            "condition": condition, "expected": expected, "prediction": prediction,
            "format_valid": prediction is not None, "correct": prediction == expected,
            "response_file": f"responses/{identifier}.json",
        })
    return probes, results


@pytest.mark.parametrize(("predictions", "outcome", "correct", "format_errors", "letter"), [
    (("A", "B"), "both_correct", 2, 0, None),
    (("B", "A"), "both_wrong", 0, 0, None),
    (("A", "A"), "letter_preference", 1, 0, "A"),
    (("B", "B"), "letter_preference", 1, 0, "B"),
    (("A", None), "format_error", 1, 1, None),
])
def test_pair_outcomes_distinguish_semantic_answers_from_same_letter(
    predictions, outcome, correct, format_errors, letter,
):
    from scripts.model_semantics.analyze_pilot import analyze

    probes, results = report_pair("case-1", "raw", predictions)
    analysis = analyze(probes, results)
    pair = analysis["pairs"][0]
    assert pair["outcome"] == outcome
    assert pair["correct_records"] == correct
    assert pair["format_failures"] == format_errors
    assert pair["same_letter"] == letter
    assert [row["id"] for row in pair["records"]] == [row["id"] for row in probes]
    assert analysis["condition_summaries"][0]["format_failures"] == format_errors


def test_different_sample_composition_does_not_become_a_presentation_effect():
    from scripts.model_semantics.analyze_pilot import analyze

    shared_raw = report_pair("shared", "raw", ("B", "A"))
    raw_only = report_pair("only-in-raw", "raw", ("A", "B"))
    shared_display = report_pair("shared", "actual_displayed", ("B", "A"))
    probes = shared_raw[0] + raw_only[0] + shared_display[0]
    results = shared_raw[1] + raw_only[1] + shared_display[1]
    analysis = analyze(probes, results)

    totals = {row["condition"]: row for row in analysis["condition_summaries"]}
    assert totals["raw"]["correct_records"] == 2
    assert totals["raw"]["n_records"] == 4
    assert totals["actual_displayed"]["correct_records"] == 0
    assert totals["actual_displayed"]["n_records"] == 2
    comparison = analysis["matched_comparisons"][0]
    assert comparison["n_matched_bases"] == 1
    assert comparison["n_matched_records_per_condition"] == 2
    assert comparison["right_minus_left_correct_records"] == 0
    assert [row["base_case_id"] for row in comparison["matched_records"]] == ["shared"]
    excluded = comparison["excluded_left_bases"] + comparison["excluded_right_bases"]
    assert excluded == ["only-in-raw"]


def test_non_reversed_semantic_choices_are_not_counted_as_a_pair():
    from scripts.model_semantics.analyze_pilot import analyze

    probes, results = report_pair("case-1", "raw", ("A", "B"))
    probes[1]["choice_order"] = probes[0]["choice_order"]
    with pytest.raises(ValueError, match="semantic alternatives are not reversed"):
        analyze(probes, results)


def test_missing_reverse_result_cannot_silently_become_an_independent_observation():
    from scripts.model_semantics.analyze_pilot import analyze

    probes, results = report_pair("case-1", "raw", ("A", "B"))
    with pytest.raises(ValueError, match="Probe/result IDs differ"):
        analyze(probes, results[:1])
