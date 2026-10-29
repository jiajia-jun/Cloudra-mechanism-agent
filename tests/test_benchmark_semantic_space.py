"""Keep benchmark labels and answers out of the descriptive semantic analysis."""

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from scripts.benchmark_semantic_space import (
    cosine_similarity,
    load_corpus,
    nearest_neighbors,
    reaction_input,
    validate_descriptions,
)


def _task():
    return {
        "task_id": "HA1",
        "tier": "hard",
        "family": "A",
        "name": "3-methylcyclobutene ring opening: determine the stereochemical outcome",
        "system": {
            "reactants": ["CC1C=CC1"],
            "products": ["CC=CC=C"],
            "charge": 0,
            "multiplicity": 1,
            "conditions": "gas phase; report the barrier and verify the product",
        },
        "prompt": {"query": "Keep mechanism_graph.json and calculate the score."},
        "gold": {"answer": "not a descriptor", "barrier": 25.0},
    }


def test_reaction_input_ignores_labels_gold_and_workflow_instructions():
    task = _task()
    original = deepcopy(task)
    expected = {
        "name": "3-methylcyclobutene ring opening",
        "reactants": ["CC1C=CC1"],
        "products": ["CC=CC=C"],
        "charge": 0,
        "multiplicity": 1,
    }
    assert reaction_input(task) == expected
    assert task == original

    altered = deepcopy(task)
    altered.update(task_id="IA99", tier="impossible", family="Z", gold={"answer": "other"})
    altered["prompt"]["query"] = "An entirely different delivery contract"
    altered["system"]["conditions"] = "Different instructions and reference DOI"
    assert reaction_input(altered) == expected


def test_reaction_input_preserves_colons_that_describe_chemistry():
    task = _task()
    task["name"] = "imine formation: formaldehyde + methylamine -> imine + water"
    assert reaction_input(task)["name"] == task["name"]


def test_load_corpus_preserves_all_fifty_tasks_including_species_questions():
    task_root = Path(__file__).resolve().parents[1] / "ideapool" / "tasks"
    rows = load_corpus(task_root)
    task_paths = [
        path
        for tier in ("easy", "normal", "hard", "impossible")
        for path in sorted((task_root / tier).glob("*.json"))
    ]
    assert len(rows) == 50
    assert [row["task_id"] for row in rows] == [path.stem for path in task_paths]
    assert len({row["task_id"] for row in rows}) == 50
    assert {"IC3", "ID2", "IE2", "IF3", "IG8"} <= {
        row["task_id"] for row in rows if row["tier"] == "impossible"
    }
    assert all({"task_id", "tier", "source", "reaction_input", "raw_text"} <= row.keys() for row in rows)
    assert all("mechanism_graph.json" not in row["raw_text"] for row in rows)
    assert all(row["raw_text"] == row["reaction_input"]["name"] for row in rows)


def test_validate_descriptions_retains_input_order_and_strips_whitespace():
    assert validate_descriptions({"descriptions": [" first ", "second"]}, 2) == ["first", "second"]


@pytest.mark.parametrize(
    "payload,count",
    [
        ({"descriptions": ["first"]}, 2),
        ({"descriptions": ["first", "second"]}, 1),
        ({"descriptions": [""]}, 1),
        ({"descriptions": ["   "]}, 1),
        ({"descriptions": [None]}, 1),
        ({"descriptions": "first"}, 1),
        ({"descriptions": ["first"], "answer": "unexpected"}, 1),
        ({"answer": "wrong schema"}, 1),
    ],
)
def test_validate_descriptions_rejects_misaligned_or_invalid_model_output(payload, count):
    with pytest.raises(ValueError):
        validate_descriptions(payload, count)


def test_cosine_similarity_normalizes_rows_without_mutating_vectors():
    vectors = np.array([[3.0, 0.0], [0.0, 7.0], [2.0, 2.0]])
    original = vectors.copy()
    result = cosine_similarity(vectors)
    np.testing.assert_allclose(
        result,
        [[1.0, 0.0, 2**-0.5], [0.0, 1.0, 2**-0.5], [2**-0.5, 2**-0.5, 1.0]],
    )
    np.testing.assert_array_equal(vectors, original)


def test_nearest_neighbors_excludes_self_and_breaks_ties_by_input_order():
    similarity = np.array([[1.0, 0.8, 0.8], [0.8, 1.0, 0.3], [0.8, 0.3, 1.0]])
    original = similarity.copy()
    np.testing.assert_array_equal(nearest_neighbors(similarity, k=2), [[1, 2], [0, 2], [0, 1]])
    np.testing.assert_array_equal(similarity, original)
