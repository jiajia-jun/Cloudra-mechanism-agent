"""Keep semantic consistency, correctness and complete paired coverage distinct."""

import pytest

from scripts.model_semantics.analyze_identity_binding import analyze


def identity_case(predictions=("A", "B", "A", "B")):
    probes, results = [], []
    for index, (representation, order) in enumerate((
        ("literal", "forward"), ("literal", "swapped"),
        ("equivalent_rewrite", "forward"), ("equivalent_rewrite", "swapped"),
    )):
        identifier = f"identity/{representation}/{order}"
        probes.append({"id": identifier, "base_case_id": "identity", "mainline": "chemical_identity/same_identity",
                       "condition": representation + "/" + order, "expected": "A" if order == "forward" else "B"})
        results.append({"id": identifier, "prediction": predictions[index], "correct": True, "format_valid": True})
    return probes, results


def test_consistently_wrong_semantics_are_not_correct():
    probes, results = identity_case(("B", "A", "B", "A"))
    chemical = analyze(probes, results)["chemical_identity"]
    assert chemical["n_distinct_bases"] == 1
    assert chemical["correct"] == 0  # Saved result flags deliberately claim otherwise.
    assert chemical["option_order_summary"]["semantic_same"] == 2
    assert chemical["option_order_summary"]["both_wrong"] == 2
    assert chemical["option_order_summary"]["both_correct"] == 0
    assert chemical["representation_summary"]["semantic_same"] == 2


def test_missing_result_refuses_partial_analysis():
    probes, results = identity_case()
    with pytest.raises(ValueError, match="Probe/result IDs differ"):
        analyze(probes, results[:-1])


def test_invalid_format_is_not_recovered_from_raw_answer_or_saved_flags():
    probes, results = identity_case()
    results[0].update(prediction=None, raw_response="A")
    report = analyze(probes, results)
    assert report["chemical_identity"]["correct"] == 3
    assert report["chemical_identity"]["format_failures"] == 1
    assert report["chemical_identity"]["option_order_summary"]["format_error_pairs"] == 1
    assert report["chemical_identity"]["option_order_summary"]["semantic_same"] == 1
    assert report["invalid_format_records"][0]["selected_meaning"] is None


def test_binding_change_and_presentation_effect_use_the_same_base_and_order():
    probes, results = [], []
    for binding in ("coherent", "altered"):
        for presentation in ("flat", "linked"):
            for order in ("forward", "swapped"):
                identifier = "/".join(("binding", binding, presentation, order))
                expected_satisfied = binding == "coherent"
                predicted_satisfied = binding == "coherent" or presentation == "flat"
                expected = "A" if expected_satisfied == (order == "forward") else "B"
                prediction = "A" if predicted_satisfied == (order == "forward") else "B"
                probes.append({"id": identifier, "base_case_id": "binding", "mainline": "B",
                               "condition": binding + "_" + presentation, "option_order": order, "expected": expected})
                results.append({"id": identifier, "prediction": prediction})
    binding = analyze(probes, results)["evidence_binding"]
    assert binding["n_distinct_bases"] == 1
    changes = {row["presentation"]: row for row in binding["binding_change_by_presentation"]}
    assert changes["flat"]["semantic_same"] == 2
    assert changes["flat"]["both_correct"] == 0
    assert changes["linked"]["semantic_changed"] == changes["linked"]["both_correct"] == 2
    presentation = {row["binding"]: row for row in binding["presentation_by_binding"]}
    assert presentation["coherent"]["both_correct"] == 2
    assert presentation["altered"]["left_wrong_right_correct"] == 2
    assert binding["option_order_summary"]["semantic_same"] == 4
    assert binding["option_order_summary"]["both_correct"] == 3
