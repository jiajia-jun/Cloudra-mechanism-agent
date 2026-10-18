"""File size cannot turn valid native evidence into unsupported claims."""

import json
from pathlib import Path

import pytest

from cloudra.benchmark.barrier_evidence import _engine_energy_kcal
from cloudra.benchmark.integrity import audit_integrity
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import GoldMechanismGraph, GoldSpec, PromptSpec, SystemSpec, TaskSpec


def test_large_native_log_keeps_binding_selfconsistency_energy_and_score(tmp_path):
    pytest.importorskip('rdkit')
    native = (Path(__file__).parent / 'fixtures/gaussian/water_opt_freq_g16.out').read_text()
    graph = GoldMechanismGraph.model_validate({'nodes': [
        {'id': 'R', 'role': 'reactant', 'smiles': ['O'], 'properties': {'evidence_log': 'water.log'}},
    ], 'edges': []})
    task = TaskSpec(task_id='large_native', tier='easy', prompt=PromptSpec(query='water'),
                    system=SystemSpec(reactants=['O']), gold=GoldSpec(mechanism_graph=graph))
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    from cloudra.benchmark.graph_similarity import GedConfig

    runner.ged_config = GedConfig()
    scores, energies = [], []
    for label, padding in [('original', ''), ('large', ' ' * (20 * 1024 * 1024 + 64) + '\n')]:
        sandbox = tmp_path / label
        sandbox.mkdir()
        # Insert at an existing line boundary; every native scientific byte remains.
        lines = native.splitlines(keepends=True)
        (sandbox / 'water.log').write_text(''.join(lines[:15]) + padding + ''.join(lines[15:]))
        (sandbox / 'mechanism_graph.json').write_text(json.dumps(graph.model_dump(mode='json', by_alias=True)))
        integrity = audit_integrity(sandbox)
        assert integrity.node_bindings[0].matched, (label, integrity.notes)
        result = runner.score_sandbox(task, sandbox)
        assert result.selfconsistency_passed, result.notes
        scores.append(result.final_score)
        energy, error = _engine_energy_kcal(sandbox, 'water.log')
        assert not error
        energies.append(energy)
    assert scores == [1.0, 1.0]
    assert energies[0] is not None and energies[1] == pytest.approx(energies[0])
