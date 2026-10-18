"""Keep a calculated branch attached to its actual starting minimum."""

import pytest


def test_carbamic_acid_decomposition_starts_at_syn_not_anti_conformer():
    pytest.importorskip("rdkit")
    from cloudra.benchmark.gen_normal_tasks import _build_graph, _validate_task

    entry = {
        "name_en": "one-water isocyanic acid hydrolysis",
        "conditions_en": "gas phase",
        "mapped_reactants": "[NH:1]=[C:2]=[O:3].[OH2:4]",
        "steps": [
            {
                "out": "[NH2:1][C:2](=[O:3])[OH:4]",
                "type": "water addition to syn carbamic acid",
                "barrier": 36.79,
            },
            {
                "out": "[NH2:1][C:2](=[O:3])[OH:4]",
                "type": "syn to anti conformational change",
                "conformational": True,
                "barrier": 11.06,
            },
            {
                "out": "[NH3:1].[O:3]=[C:2]=[O:4]",
                "type": "syn carbamic acid decomposition",
                "from_step": 1,
                "barrier": 43.13,
            },
        ],
    }
    assert not _validate_task("Y3", entry, ["N=C=O", "O"], ["N", "O=C=O"])
    graph = _build_graph("Y3", entry)
    assert [(e.from_node, e.to_node) for e in graph.edges] == [
        ("NY3_R", "NY3_I1"),
        ("NY3_I1", "NY3_I2"),
        ("NY3_I1", "NY3_P"),
    ]
    assert graph.edges[2].barrier_kcal_mol == 43.13
    assert graph.edges[2].bond_changes.break_ == [[1, 2]]
    assert graph.edges[2].bond_changes.form == [[2, 4]]
