"""Reaction topology and stable-intermediate energy references are distinct."""

import pytest


def test_carbamic_acid_decomposition_connects_anti_but_references_stable_syn():
    pytest.importorskip("rdkit")
    from cloudra.benchmark.gen_normal_tasks import _build_graph, _validate_task
    from cloudra.benchmark.normal_registry import REGISTRY

    entry = REGISTRY["Y3"]
    assert not _validate_task("Y3", entry, ["N=C=O", "O"], ["N", "O=C=O"])
    graph = _build_graph("Y3", entry)
    assert [(e.from_node, e.to_node) for e in graph.edges] == [
        ("NY3_R", "NY3_I1"),
        ("NY3_I1", "NY3_I2"),
        ("NY3_I2", "NY3_P"),
    ]
    assert [e.barrier_kcal_mol for e in graph.edges] == [36.79, 11.06, 43.13]
    assert "stable syn" in graph.edges[2].step_type
    assert graph.edges[2].bond_changes.break_ == [[1, 2], [4, 7]]
    assert graph.edges[2].bond_changes.form == [[1, 7], [2, 4]]


def test_formamide_dehydration_references_stable_int1a():
    pytest.importorskip("rdkit")
    from cloudra.benchmark.gen_normal_tasks import _build_graph
    from cloudra.benchmark.normal_registry import REGISTRY

    graph = _build_graph("R1", REGISTRY["R1"])
    assert [e.barrier_kcal_mol for e in graph.edges] == [46.32, 22.80, 7.25, 68.85]
    assert graph.edges[-1].from_node == "NR1_I3"
    assert "stable INT-1a" in graph.edges[-1].step_type
    expected = (-169.641371451 + 169.751090026) * 627.509474
    assert graph.edges[-1].barrier_kcal_mol == pytest.approx(expected, abs=0.005)
