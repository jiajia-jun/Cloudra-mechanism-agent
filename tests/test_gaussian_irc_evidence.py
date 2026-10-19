"""Gaussian native IRC evidence uses the same strict Opt/Freq chain as ORCA.

The IRC is a captured Gaussian calculation. The small Opt/Freq logs below are
synthetic parser fixtures, not claimed quantum-chemical calculation results.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cloudra.benchmark.integrity import EvidenceFile, NodeBinding
from cloudra.benchmark.schema import GoldMechanismGraph
from cloudra.benchmark.selfconsistency import _LogProbe, audit_self_consistency
from cloudra.tools.core import irc_evidence
from cloudra.tools.core.irc_path import xyz_block

FIXTURES = Path(__file__).parent / 'fixtures' / 'gaussian'


def _orientation(geometry):
    from cclib.parser.utils import PeriodicTable

    symbols, positions = geometry
    table = PeriodicTable()
    return (' Standard orientation:\n'
        ' ---------------------------------------------------------------------\n'
        ' Center     Atomic      Atomic             Coordinates (Angstroms)\n'
        ' Number     Number       Type             X           Y           Z\n'
        ' ---------------------------------------------------------------------\n'
        + ''.join(f' {index} {table.number[symbol]} 0 {x:.12f} {y:.12f} {z:.12f}\n'
                  for index, (symbol, (x, y, z)) in enumerate(zip(symbols, positions, strict=True), 1))
        + ' ---------------------------------------------------------------------\n')


def _native_log(path, initial, final=None, *, imaginary=None):
    text = 'Entering Gaussian System\n # hf/sto-3g\n' + _orientation(initial)
    if final is not None:
        text += ' Optimization completed.\n' + _orientation(final)
    text += ' SCF Done: E(RHF) = -92.0 A.U.\n'
    if imaginary is not None:
        text += ' Harmonic frequencies\n Frequencies -- ' + ('-100.' if imaginary else '100.') + ' 200. 300.\n'
    path.write_text(text + ' Normal termination of Gaussian 16\n')
    return path


def _bundle(directory):
    irc = directory / 'irc.log'
    irc.write_bytes((FIXTURES / 'hcn_ts_irc_g16.log').read_bytes())
    ts = irc_evidence.irc_start_geometry(irc)
    source_end, target_end = irc_evidence.irc_endpoint_geometries(irc)
    symbols = ['C', 'N', 'H']
    source = (symbols, [[0., 0., 0.], [1.16, 0., 0.], [-1.06, 0., 0.]])
    target = (symbols, [[0., 0., 0.], [1.16, 0., 0.], [2.17, 0., 0.]])
    return {
        'irc': irc,
        'ts': _native_log(directory / 'ts.log', ts, imaginary=True),
        'reactant_opt': _native_log(directory / 'reactant_opt.log', source_end, source),
        'reactant_freq': _native_log(directory / 'reactant_freq.log', source, imaginary=False),
        'product_opt': _native_log(directory / 'product_opt.log', target_end, target),
        'product_freq': _native_log(directory / 'product_freq.log', target, imaginary=False),
    }


def _audit(directory, bundle, *, extra_files=()):
    graph = GoldMechanismGraph.model_validate({'nodes': [
        {'id': 'R', 'role': 'reactant', 'smiles': ['C#N']},
        {'id': 'P', 'role': 'product', 'smiles': ['[C-]#[NH+]']},
        {'id': 'TS', 'role': 'transition_state', 'smiles': []},
    ], 'edges': [{'id': 'E', 'from': 'R', 'to': 'P', 'via': 'TS'}]})
    bindings = [NodeBinding(node_id=node, bound_files=[bundle[key].name], matched=True, quality=1.)
        for node, key in [('R', 'reactant_freq'), ('P', 'product_freq'), ('TS', 'ts')]]
    files = [EvidenceFile(path=path.name, kind='gaussian', size=path.stat().st_size)
             for path in bundle.values() if path.is_file()]
    return audit_self_consistency(graph, bindings, [*files, *extra_files], directory)


def test_unmanaged_native_gaussian_irc_accepts_complete_endpoint_opt_freq_chain(tmp_path, rdkit_chemistry):
    bundle = _bundle(tmp_path)

    report = _audit(tmp_path, bundle)

    assert report.passed, report.notes
    edge = next(check for check in report.checks if check.element_id == 'E')
    assert {path.name for path in bundle.values()} <= set(edge.evidence_used)
    assert not (tmp_path / 'irc_endpoints.json').exists()


@pytest.mark.parametrize('broken', ['missing_opt', 'wrong_start', 'imaginary', 'wrong_ts', 'abnormal'])
def test_native_gaussian_irc_preserves_strict_endpoint_chain(tmp_path, broken, rdkit_chemistry):
    bundle = _bundle(tmp_path)
    if broken == 'missing_opt':
        bundle['reactant_opt'].unlink()
    elif broken == 'wrong_start':
        path = bundle['reactant_opt']
        path.write_text(path.read_text().replace('0.480862000000', '0.580862000000', 1))
    elif broken == 'imaginary':
        path = bundle['reactant_freq']
        path.write_text(path.read_text().replace('Frequencies -- 100.', 'Frequencies -- -100.'))
    elif broken == 'wrong_ts':
        path = bundle['ts']
        path.write_text(path.read_text().replace('0.427601046333', '0.627601046333', 1))
    else:
        path = bundle['reactant_opt']
        path.write_text(path.read_text().replace('Normal termination', 'Error termination'))

    assert not _audit(tmp_path, bundle).passed


def _split_native_irc(bundle):
    """Keep each captured native path's point segments in its own parser fixture."""
    text = bundle.pop('irc').read_text()
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if 'Point Number:' in line and 'Path Number:' in line]
    summary = next(index for index, line in enumerate(lines) if 'Energies reported relative to the TS energy' in line)
    prefix, suffix = ''.join(lines[:starts[0]]), ''.join(lines[summary:])
    for path_number, name in ((1, 'forward'), (2, 'reverse')):
        segments = []
        for first, last in zip(starts, starts[1:] + [summary], strict=True):
            if int(lines[first].split()[-1]) == path_number:
                segments.extend(lines[first:last])
        path = bundle['ts'].with_name(name + '.log')
        path.write_text(prefix + ''.join(segments) + suffix)
        bundle[name] = path
    (bundle['ts'].parent / 'irc.log').unlink()


@pytest.mark.parametrize('broken', ['', 'same_direction', 'wrong_reverse_ts', 'abnormal_reverse', 'missing_reverse'])
def test_independent_gaussian_directions_require_two_sides_of_the_same_ts(tmp_path, broken, rdkit_chemistry):
    bundle = _bundle(tmp_path)
    _split_native_irc(bundle)
    if broken == 'same_direction':
        bundle['reverse'].write_bytes(bundle['forward'].read_bytes())
    elif broken == 'wrong_reverse_ts':
        path = bundle['reverse']
        path.write_text(path.read_text().replace('0.427601046333', '0.627601046333', 1))
    elif broken == 'abnormal_reverse':
        path = bundle['reverse']
        path.write_text(path.read_text().replace('Normal termination', 'Error termination'))
    elif broken == 'missing_reverse':
        bundle['reverse'].unlink()

    report = _audit(tmp_path, bundle)

    assert report.passed is (not broken), report.notes


def test_benchmark_failure_retains_candidate_paths_and_native_verifier_reason(tmp_path, rdkit_chemistry):
    bundle = _bundle(tmp_path)
    bundle['reactant_opt'].unlink()

    edge = next(check for check in _audit(tmp_path, bundle).checks if check.element_id == 'E')

    notes = '\n'.join(edge.notes)
    for path in ('ts.log', 'irc.log', 'reactant_freq.log', 'product_freq.log'):
        assert path in notes
    assert 'atom binding' in notes.lower()
    assert 'supply a normally converged Opt log' in notes


def test_wrong_endpoint_start_names_the_opt_that_must_be_recomputed(tmp_path, rdkit_chemistry):
    bundle = _bundle(tmp_path)
    path = bundle['reactant_opt']
    path.write_text(path.read_text().replace('0.480862000000', '0.580862000000', 1))

    passed, details = irc_evidence.verify_short_irc_direction(bundle['irc'], [bundle['ts']],
        [bundle['product_opt'], bundle['product_freq']],
        [bundle['reactant_opt'], bundle['reactant_freq']],
        reactant_smiles='C#N', product_smiles='[C-]#[NH+]')

    assert not passed
    assert any(str(path) in detail and 'starting geometry' in detail
               and 'neither' in detail for detail in details), details


def test_missing_unrelated_qm_file_does_not_abort_valid_irc_proof(tmp_path, rdkit_chemistry):
    bundle = _bundle(tmp_path)

    report = _audit(tmp_path, bundle, extra_files=[EvidenceFile(path='missing.log', kind='gaussian')])

    assert report.passed, report.notes


@pytest.mark.parametrize('ending,reason', [
    ('Error termination', 'native error termination'),
    ('Normal termination', 'normally terminated but IRC evidence is incomplete'),
    ('', 'native normal termination is absent'),
])
def test_benchmark_retains_native_gaussian_incomplete_irc_reason(tmp_path, ending, reason, rdkit_chemistry):
    bundle = _bundle(tmp_path)
    path = bundle['irc']
    text = path.read_text().partition('Energies reported relative to the TS energy')[0]
    path.write_text(text + '\n' + ending + '\n')

    report = _audit(tmp_path, bundle)

    assert not report.passed
    assert reason in '\n'.join(report.notes)
    assert 'Summary of reaction path following' in '\n'.join(report.notes)


def test_gaussian_snapshot_keeps_hash_verified_frozen_binding_offline(tmp_path, monkeypatch):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    bundle = _bundle(tmp_path)
    frozen = {'process_id': 'fixture', 'declaration_revision': 1,
              'atom_map': [1, 2, 3], 'ts_log_sha256': hashlib.sha256(bundle['ts'].read_bytes()).hexdigest()}
    monkeypatch.setattr('cloudra.services.ts_pipeline_store.atom_binding_for_log', lambda *_: frozen)
    snapshot = snapshot_evidence_file(bundle['irc'], tmp_path)
    path = Path(snapshot.snapshot_path)
    relative = str(path.relative_to(tmp_path))
    probe = _LogProbe(tmp_path, {relative: EvidenceFile(path=relative, kind='gaussian', size=path.stat().st_size)})

    assert probe.irc_atom_binding(relative) == frozen
    manifest = json.loads(path.with_name('irc_endpoints.json').read_text())
    assert manifest['log_sha256'] == snapshot.sha256
    assert all(endpoint['filename'] is None for endpoint in manifest['endpoints'].values())
    # Re-archiving relies on the frozen archive, even without the live ledger.
    monkeypatch.setattr('cloudra.services.ts_pipeline_store.atom_binding_for_log', lambda *_: None)
    rearchived = snapshot_evidence_file(path, tmp_path)
    assert rearchived.metadata['atom_binding'] == frozen
    # A file copy without its verified archive must never borrow this map.
    copied = tmp_path / 'unrelated.log'
    copied.write_bytes(path.read_bytes())
    copy_probe = _LogProbe(tmp_path, {copied.name: EvidenceFile(path=copied.name, kind='gaussian')})
    assert copy_probe.irc_atom_binding(copied.name) is None
    path.write_text(path.read_text() + '\nChanged native bytes.\n')
    with pytest.raises(ValueError, match='hash mismatch'):
        probe.irc_atom_binding(relative)


def test_non_irc_gaussian_log_does_not_read_a_neighbors_irc_manifest(tmp_path):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    irc = tmp_path / 'irc.log'
    irc.write_bytes((FIXTURES / 'hcn_ts_irc_g16.log').read_bytes())
    archive = snapshot_evidence_file(irc, tmp_path)
    frequency = Path(archive.snapshot_path).with_name('frequency.log')
    frequency.write_bytes((FIXTURES / 'water_opt_freq_g16.out').read_bytes())

    snapshot = snapshot_evidence_file(frequency, tmp_path)

    assert snapshot.engine == 'gaussian'
    assert snapshot.frequencies
    assert 'atom_binding' not in snapshot.metadata


@pytest.mark.parametrize('valid_map', [False, True])
def test_gaussian_archived_binding_still_checks_complete_atom_identities(tmp_path, monkeypatch, valid_map, rdkit_chemistry):
    from rdkit import Chem

    from cloudra.benchmark.selfconsistency import _strict_irc_proof
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    bundle = _bundle(tmp_path)
    frozen = dict(process_id='fixture', declaration_revision=1, charge=0,
        atom_map=[1, 2, 3] if valid_map else [2, 1, 3],
        ts_log_sha256=hashlib.sha256(bundle['ts'].read_bytes()).hexdigest(),
        reactant_mol=Chem.MolToMolBlock(Chem.AddHs(Chem.MolFromSmiles('C#N'))),
        product_mol=Chem.MolToMolBlock(Chem.AddHs(Chem.MolFromSmiles('[C-]#[NH+]'))))
    monkeypatch.setattr('cloudra.services.ts_pipeline_store.atom_binding_for_log', lambda *_: frozen)
    snapshots = {key: snapshot_evidence_file(path, tmp_path) for key, path in bundle.items()}
    paths = {key: str(Path(snapshot.snapshot_path).relative_to(tmp_path)) for key, snapshot in snapshots.items()}
    files = {path: EvidenceFile(path=path, kind='gaussian') for path in paths.values()}

    proof = _strict_irc_proof(_LogProbe(tmp_path, files), list(paths.values()),
        [paths['reactant_freq']], [paths['product_freq']], ts_files=[paths['ts']])

    assert (proof is not None) is valid_map


@pytest.mark.parametrize('reorder', [False, True])
def test_pipeline_gaussian_endpoint_accepts_native_standard_orientation(tmp_path, monkeypatch, reorder):
    """Real water Freq output may reorient the same saved Opt geometry."""
    from cloudra.tools.core import ts_process

    frequency = tmp_path / 'frequency.log'
    frequency.write_bytes((FIXTURES / 'water_opt_freq_g16.out').read_bytes())
    _, geometry = irc_evidence.probe_log(frequency)
    symbols, positions = geometry
    transformed = np.asarray(positions) @ np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]]) + [2., -3., 1.]
    optimized = (symbols, transformed.tolist())
    order = [2, 0, 1] if reorder else [0, 1, 2]
    (tmp_path / 'optimized.xyz').write_text(xyz_block(
        [symbols[index] for index in order], [transformed[index] for index in order]))
    steps = [SimpleNamespace(purpose=purpose, state='done', input_path=str(tmp_path / (purpose + '.gjf')))
             for purpose in ('reactant_opt', 'reactant_frequency')]
    record = SimpleNamespace(job_steps=steps, workspace_dir=str(tmp_path))
    monkeypatch.setattr(ts_process, '_endpoint_opt_frame', lambda *_: (xyz_block(*optimized), ''))
    monkeypatch.setattr(ts_process, '_refinement_log_path', lambda *_: str(frequency))
    monkeypatch.setattr(ts_process, '_step_calculation', lambda *_: SimpleNamespace(engine='gaussian'))

    minimum, reason = ts_process._validated_endpoint_minimum(record, 'reactant')

    assert minimum is not None, reason


@pytest.mark.parametrize('change', ['mirror', 'distortion'])
def test_pipeline_endpoint_rejects_reflection_and_actual_geometry_changes(tmp_path, monkeypatch, change):
    from cloudra.tools.core import ts_process
    from tests.ts_fixtures import native_qm_log

    geometry = (['C', 'F', 'Cl', 'Br', 'H'], [[0., 0., 0.], [1., 1., 1.],
        [-1., -1., 1.], [-1., 1., -1.], [1., -1., -1.]])
    measured = np.array(geometry[1])
    if change == 'mirror':
        measured[:, 0] *= -1
    else:
        measured[1, 0] += .01
    frequency = tmp_path / 'frequency.log'
    frequency.write_text(native_qm_log('gaussian', geometry[0], measured,
        optimization=None, frequencies=[100., 200.]))
    (tmp_path / 'optimized.xyz').write_text(xyz_block(*geometry))
    steps = [SimpleNamespace(purpose=purpose, state='done', input_path=str(tmp_path / (purpose + '.gjf')))
             for purpose in ('reactant_opt', 'reactant_frequency')]
    record = SimpleNamespace(job_steps=steps, workspace_dir=str(tmp_path))
    monkeypatch.setattr(ts_process, '_endpoint_opt_frame', lambda *_: (xyz_block(*geometry), ''))
    monkeypatch.setattr(ts_process, '_refinement_log_path', lambda *_: str(frequency))
    monkeypatch.setattr(ts_process, '_step_calculation', lambda *_: SimpleNamespace(engine='gaussian'))
    monkeypatch.setattr('cloudra.dag.evidence_ingest.snapshot_evidence_file',
        lambda *_, **__: SimpleNamespace(frequencies=[100., 200.], imaginary_frequencies=[]))

    minimum, reason = ts_process._validated_endpoint_minimum(record, 'reactant')

    assert minimum is None
    assert 'geometry' in reason

