"""Native NU3 regressions; no model or quantum calculation is launched."""
import json
import shutil
from pathlib import Path

import pytest

from cloudra.benchmark.integrity import audit_integrity
from cloudra.benchmark.selfconsistency import audit_self_consistency
from cloudra.tools.core.irc_evidence import verify_short_irc_direction

FIXTURES = Path(__file__).parent / "fixtures" / "benchmark_nu3"
pytest.importorskip('rdkit')


def _delivery(tmp_path, *, source="C1CO[PH3]1", target="C=C.O=[PH3]", ts="ts2_frequency.out"):
    for path in FIXTURES.rglob("*"):
        if path.is_file():
            out = tmp_path / path.relative_to(FIXTURES)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out)
    graph = {"nodes": [
        {"id": "R", "role": "reactant", "smiles": [source]},
        {"id": "P", "role": "product", "smiles": [target]},
        {"id": "TS", "role": "transition_state", "smiles": [],
         "properties": {"evidence_log": ts}},
    ], "edges": [{"id": "e1", "from": "R", "to": "P", "via": "TS"}]}
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(graph))


def test_annotation_cannot_bind_wrong_native_species(tmp_path):
    _delivery(tmp_path, source="C=[PH3].C=O", target="C1CO[PH3]1", ts="ts1_frequency.out")
    report = audit_integrity(tmp_path)
    bindings = {item.node_id: item for item in report.node_bindings}
    assert "mislabeled_rc_minimum.out" not in bindings["R"].bound_files
    assert "mislabeled_op_minimum.out" not in bindings["P"].bound_files


def test_explicit_species_log_with_correct_geometry_binds_without_matching_annotation(tmp_path):
    _delivery(tmp_path, source="C=[PH3].C=O")
    graph_path = tmp_path / "mechanism_graph.json"
    graph = json.loads(graph_path.read_text())
    graph["nodes"][0]["properties"] = {"evidence_log": "rc_minimum.out"}
    graph_path.write_text(json.dumps(graph))
    report = audit_integrity(tmp_path)
    binding = next(item for item in report.node_bindings if item.node_id == "R")
    assert binding.bound_files == ["rc_minimum.out"]
    assert binding.matched


def test_native_saddle_irc_and_minima_need_endpoint_optimization_logs(tmp_path):
    _delivery(tmp_path)
    integrity = audit_integrity(tmp_path)
    result = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings,
                                    integrity.evidence_files, tmp_path)
    assert not result.passed
    assert not next(check for check in result.checks if check.kind == 'edge').covered


def test_native_optimization_anchor_can_use_separate_same_geometry_frequency(tmp_path):
    _delivery(tmp_path, ts='ts2_optimization.out')
    integrity = audit_integrity(tmp_path)
    report = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings, integrity.evidence_files, tmp_path)
    assert not report.passed  # Endpoint Opt source logs are absent from this archive.
    used = next(item.evidence_used for item in report.checks if item.kind == 'edge')
    assert 'ts2_optimization.out' in used and 'ts2_frequency.out' in used


def _species_optimization_anchor(tmp_path, node_id, frequency_name):
    # Remove only the frequency block from captured native evidence to model
    # separate Opt/Freq delivery at the same coordinates, without running QM.
    frequency = (tmp_path / frequency_name).read_text()
    before, _, frequencies = frequency.partition('VIBRATIONAL FREQUENCIES')
    _, marker, after = frequencies.partition('****ORCA TERMINATED NORMALLY****')
    assert before and marker
    anchor_name = f'{node_id}_optimization.out'
    (tmp_path / anchor_name).write_text(before.replace('! Freq ', '! Opt ') + marker + after)
    graph_path = tmp_path / 'mechanism_graph.json'
    graph = json.loads(graph_path.read_text())
    node = next(node for node in graph['nodes'] if node['id'] == node_id)
    node['properties'] = {'evidence_log': anchor_name}
    graph_path.write_text(json.dumps(graph))
    return anchor_name


@pytest.mark.parametrize('node_id,frequency_name', [
    ('R', 'op_minimum.out'),
    ('P', 'product_minimum.out'),
])
def test_explicit_species_optimization_uses_same_geometry_minimum_for_species_and_irc(
    tmp_path, node_id, frequency_name,
):
    _delivery(tmp_path)
    anchor_name = _species_optimization_anchor(tmp_path, node_id, frequency_name)
    integrity = audit_integrity(tmp_path)
    binding = next(item for item in integrity.node_bindings if item.node_id == node_id)
    assert binding.matched and binding.bound_files == [anchor_name]

    report = audit_self_consistency(
        integrity.delivered_graph, integrity.node_bindings, integrity.evidence_files, tmp_path,
    )

    assert not report.passed  # Matching final coordinates do not establish the Opt starting frame.
    checks = {item.element_id: item for item in report.checks}
    assert checks[node_id].evidence_used == [anchor_name, frequency_name]
    assert checks[node_id].covered
    assert not checks['e1'].covered


@pytest.mark.parametrize('bad_frequency', ['different_geometry', 'imaginary', 'abnormal', 'missing'])
def test_species_optimization_cannot_borrow_invalid_minimum_for_species_or_irc(tmp_path, bad_frequency):
    _delivery(tmp_path)
    anchor_name = _species_optimization_anchor(tmp_path, 'R', 'op_minimum.out')
    frequency_path = tmp_path / 'op_minimum.out'
    if bad_frequency == 'different_geometry':
        frequency_path.write_text((tmp_path / 'op_declared_minimum.out').read_text())
    elif bad_frequency == 'imaginary':
        frequency_path.write_text(frequency_path.read_text().replace('113.35 cm**-1', '-113.35 cm**-1'))
    elif bad_frequency == 'abnormal':
        frequency_path.write_text(frequency_path.read_text().replace(
            'ORCA TERMINATED NORMALLY', 'ORCA finished by error termination',
        ))
    else:
        frequency_path.unlink()
    integrity = audit_integrity(tmp_path)
    binding = next(item for item in integrity.node_bindings if item.node_id == 'R')
    assert binding.matched and binding.bound_files == [anchor_name]

    report = audit_self_consistency(
        integrity.delivered_graph, integrity.node_bindings, integrity.evidence_files, tmp_path,
    )

    checks = {item.element_id: item for item in report.checks}
    assert not report.passed
    assert not checks['R'].covered
    assert not checks['e1'].covered


@pytest.mark.parametrize('invalid_anchor', ['missing.out', 'product_minimum.out', ''])
def test_invalid_explicit_species_anchor_cannot_use_historical_minimum(tmp_path, invalid_anchor):
    _delivery(tmp_path)
    graph_path = tmp_path / 'mechanism_graph.json'
    graph = json.loads(graph_path.read_text())
    graph['nodes'][0]['properties'] = {'evidence_log': invalid_anchor}
    graph_path.write_text(json.dumps(graph))
    integrity = audit_integrity(tmp_path)

    report = audit_self_consistency(
        integrity.delivered_graph, integrity.node_bindings, integrity.evidence_files, tmp_path,
    )

    checks = {item.element_id: item for item in report.checks}
    assert not report.passed
    assert not checks['R'].bound and not checks['R'].covered
    assert not checks['e1'].covered


def test_explicit_ts_anchor_cannot_borrow_another_saddle_and_irc(tmp_path):
    _delivery(tmp_path, ts="ts1_frequency.out")
    integrity = audit_integrity(tmp_path)
    result = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings,
                                    integrity.evidence_files, tmp_path)
    assert not result.passed


def test_irc_direction_requires_the_native_starting_ts():
    passed, details = verify_short_irc_direction(
        FIXTURES / "ts1_irc/irc.out",
        [FIXTURES / "ts2_frequency.out"],
        [FIXTURES / "mislabeled_rc_minimum.out"],
        [FIXTURES / "mislabeled_op_minimum.out"])
    assert not passed, details


def test_barrier_uses_explicit_real_species_instead_of_mislabeled_history(tmp_path):
    from cloudra.benchmark.barrier_evidence import collect_barrier_evidence
    _delivery(tmp_path, source='C=[PH3].C=O', ts='ts1_frequency.out')
    path = tmp_path / 'mechanism_graph.json'
    graph = json.loads(path.read_text())
    graph['nodes'][0]['properties'] = {'evidence_log': 'rc_minimum.out'}
    path.write_text(json.dumps(graph))
    report = collect_barrier_evidence(tmp_path)
    assert len(report.steps) == 1, report.notes
    assert report.steps[0].base_path == 'rc_minimum.out'
    assert report.steps[0].ts_path == 'ts1_frequency.out'


@pytest.mark.parametrize('name', ['ts2_frequency.out', 'op_minimum.out'])
def test_abnormally_terminated_native_evidence_cannot_pass(tmp_path, name):
    _delivery(tmp_path)
    path = tmp_path / name
    path.write_text(path.read_text().replace('ORCA TERMINATED NORMALLY', 'ORCA finished by error termination'))
    if name == 'op_minimum.out':
        graph_path = tmp_path / 'mechanism_graph.json'
        graph = json.loads(graph_path.read_text())
        graph['nodes'][0]['properties'] = {'evidence_log': name}
        graph_path.write_text(json.dumps(graph))
    integrity = audit_integrity(tmp_path)
    report = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings, integrity.evidence_files, tmp_path)
    assert not report.passed


def test_explicit_species_reference_preserves_protonation_partial(tmp_path):
    water = Path(__file__).parent / 'fixtures/gaussian/water_opt_freq_g16.out'
    path = tmp_path / 'water.log'
    path.write_text('smiles: O\n' + water.read_text())
    graph = {'nodes': [{'id': 'R', 'role': 'reactant', 'smiles': ['[OH3+]'],
                       'properties': {'evidence_log': 'water.log'}}], 'edges': []}
    (tmp_path/'mechanism_graph.json').write_text(json.dumps(graph))
    binding = audit_integrity(tmp_path).node_bindings[0]
    assert binding.matched and binding.quality == pytest.approx(0.7)


def test_nonexplicit_ts_cannot_borrow_saddle_when_irc_check_disabled(tmp_path):
    from cloudra.benchmark.schema import SelfConsistencyRubric
    _delivery(tmp_path)
    path = tmp_path / 'mechanism_graph.json'
    graph = json.loads(path.read_text())
    graph['nodes'][2]['properties'] = {}
    path.write_text(json.dumps(graph))
    integrity = audit_integrity(tmp_path)
    report = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings, integrity.evidence_files, tmp_path,
                                   SelfConsistencyRubric(irc_connects_endpoints=False))
    assert not report.passed


def test_ambiguous_ts_energy_does_not_choose_a_different_geometry(tmp_path):
    from cloudra.benchmark.schema import SelfConsistencyRubric
    _delivery(tmp_path)
    # Numeric variation solely exercises association ambiguity; coordinates,
    # signed frequencies and native provenance remain the captured facts.
    other = tmp_path / 'ts1_frequency.out'
    other.write_text(other.read_text().replace('-496.538382627706', '-496.547774252793'))
    path = tmp_path / 'mechanism_graph.json'
    graph = json.loads(path.read_text())
    graph['nodes'][2]['properties'] = {'energy_hartree': -496.547774252793}
    path.write_text(json.dumps(graph))
    integrity = audit_integrity(tmp_path)
    report = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings, integrity.evidence_files, tmp_path,
                                   SelfConsistencyRubric(irc_connects_endpoints=False))
    assert not report.passed


def test_concatenated_jobs_cannot_lend_frequency_to_later_optimization(tmp_path):
    from cloudra.benchmark.barrier_evidence import collect_barrier_evidence
    _delivery(tmp_path, ts='mixed.out')
    (tmp_path/'mixed.out').write_bytes((FIXTURES/'ts1_frequency.out').read_bytes() +
                                      (FIXTURES/'ts2_optimization.out').read_bytes())
    (tmp_path/'ts2_frequency.out').unlink()
    (tmp_path/'ts2_optimization.out').unlink()
    integrity = audit_integrity(tmp_path)
    report = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings, integrity.evidence_files, tmp_path)
    assert not report.passed
    assert collect_barrier_evidence(tmp_path).steps == []
