"""Computed hard references preserve substrate identity and the step energy frame."""

from pathlib import Path

import pytest

from cloudra.benchmark.schema import NodeRole


def _tasks():
    from cloudra.benchmark.runner import load_tasks

    root = Path(__file__).resolve().parents[1] / "ideapool" / "tasks" / "hard"
    return {task.task_id: task for task in load_tasks(root)}


def test_hi1_uses_two_independent_stereochemical_substrates():
    Chem = pytest.importorskip("rdkit.Chem")
    task = _tasks()["HI1"]
    graph = task.gold.mechanism_graph
    reactants = [node for node in graph.nodes if node.role is NodeRole.REACTANT]
    assert len(reactants) == 2
    assert {node.id for node in reactants} == {"HI1_ERYTHRO_R", "HI1_THREO_R"}
    identities = {Chem.MolToSmiles(Chem.MolFromSmiles(node.smiles[0])) for node in reactants}
    assert len(identities) == 2
    assert all(len(Chem.GetMolFrags(Chem.MolFromSmiles(node.smiles[0]))) == 1 for node in reactants)
    assert len(task.system.reactants) == 1  # a skeleton; the cases are not a mixed complex
    assert len(graph.edges) == 2
    assert len({edge.from_node for edge in graph.edges}) == 2
    assert {edge.barrier_kcal_mol for edge in graph.edges} == {16.62, 15.85}
    assert not any("REGIO" in node.id for node in graph.nodes)
    assert all(edge.favored is None for edge in graph.edges)
    assert task.gold.selectivity is None and task.rubric.accuracy.enabled
    nodes = {node.id: node for node in graph.nodes}
    for edge in graph.edges:
        start = nodes[edge.from_node].properties["energy_hartree"]
        ts = nodes[edge.via].properties["energy_hartree"]
        assert (ts - start) * 627.509474 == pytest.approx(edge.barrier_kcal_mol, abs=0.005)
        assert edge.bond_changes.break_ == [[2, 3], [7, 15]]
        assert edge.bond_changes.form == [[2, 7], [6, 15]]


def test_hl1_barriers_use_each_irc_connected_contact_minimum():
    task = _tasks()["HL1"]
    graph = task.gold.mechanism_graph
    nodes = {node.id: node for node in graph.nodes}
    edges = {edge.channel: edge for edge in graph.edges}
    assert {channel: edge.barrier_kcal_mol for channel, edge in edges.items()} == {
        "exo": 16.18, "endo": 10.77,
    }
    assert len({edge.from_node for edge in edges.values()}) == 2
    assert nodes[edges["exo"].from_node].properties["energy_hartree"] == -441.020095712
    assert nodes[edges["endo"].from_node].properties["energy_hartree"] == -441.019350272
    assert task.gold.selectivity is None and task.rubric.accuracy.enabled
    assert "own IRC-connected contact minimum" in task.prompt.query
    for edge in edges.values():
        start = nodes[edge.from_node].properties["energy_hartree"]
        ts = nodes[edge.via].properties["energy_hartree"]
        assert (ts - start) * 627.509474 == pytest.approx(edge.barrier_kcal_mol, abs=0.005)
        assert edge.favored is None
        assert edge.bond_changes.break_ == [[1, 2], [4, 5]]
        assert edge.bond_changes.form == [[1, 4], [3, 5]]
    assert "no favored-channel assignment is scored" in task.prompt.query
    assert "`favored: true`" not in task.prompt.query
