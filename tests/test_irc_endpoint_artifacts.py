"""Canonical direct-job handoff from captured native IRC evidence, without QM calls."""

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from cloudra.tools.core import irc_evidence, orca_frames
from cloudra.tools.core.irc_path import parse_xyz, same_geometry

FIXTURES = Path(__file__).parent / 'fixtures'


def _native_irc(directory, engine):
    directory.mkdir(parents=True, exist_ok=True)
    if engine == 'gaussian':
        path = directory / 'irc.log'
        shutil.copy2(FIXTURES / 'gaussian/hcn_ts_irc_g16.log', path)
        return path
    shutil.copytree(FIXTURES / 'benchmark_nu3/ts2_irc', directory, dirs_exist_ok=True)
    return directory / 'irc.out'


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_native_irc_exports_both_actual_outer_frames_and_read_is_pure(tmp_path, engine):
    from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts, write_irc_endpoint_artifacts

    log = _native_irc(tmp_path, engine)
    original = {path: path.read_bytes() for path in tmp_path.iterdir()}
    expected = irc_evidence.irc_endpoint_geometries(log)
    assert expected is not None
    assert read_irc_endpoint_artifacts(log) == {}

    exported = write_irc_endpoint_artifacts(log)

    assert set(exported) == {'irc_end_a_path', 'irc_end_b_path'}
    digest = hashlib.sha256(log.read_bytes()).hexdigest()
    for key, geometry in zip(('irc_end_a_path', 'irc_end_b_path'), expected, strict=True):
        path = Path(exported[key])
        actual = parse_xyz(path.read_text())
        assert path.parent == log.parent
        assert digest in path.name
        assert actual[0] == list(geometry[0])
        np.testing.assert_allclose(actual[1], geometry[1], atol=1e-12, rtol=0)
        assert same_geometry(actual, geometry)
    before_read = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()}
    assert read_irc_endpoint_artifacts(log) == exported
    assert write_irc_endpoint_artifacts(log) == exported
    assert before_read == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()}
    assert all(path.read_bytes() == contents for path, contents in original.items())


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_archived_irc_resolves_native_endpoints_without_mutating_evidence(tmp_path, engine, monkeypatch):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    log = _native_irc(tmp_path / 'native', engine)
    expected = irc_evidence.irc_endpoint_geometries(log)
    frozen = {'process_id': 'fixture', 'atom_map': [1, 2, 3]}
    monkeypatch.setattr('cloudra.services.ts_pipeline_store.atom_binding_for_log', lambda *_: frozen)
    snapshot = snapshot_evidence_file(log, tmp_path)
    archive = Path(snapshot.snapshot_path).parent
    shutil.rmtree(log.parent)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in archive.iterdir()}

    endpoints = orca_frames.extract_irc_endpoints(snapshot.snapshot_path)

    # Gaussian canonical A/B use negative/positive reaction coordinates; the
    # captured HCN log labels these native paths backward/forward respectively.
    directions = ('backward', 'forward') if engine == 'gaussian' else ('forward', 'backward')
    for direction, geometry in zip(directions, expected, strict=True):
        endpoint = endpoints[direction]
        assert endpoint['availability'] == 'available'
        assert Path(endpoint['geometry_ref']).parent == archive
        assert endpoint['atom_binding'] == frozen
        assert same_geometry(parse_xyz(orca_frames.read_endpoint_geometry(endpoint)), geometry)
    if engine == 'gaussian':
        assert all(endpoint['origin'] == 'native_log' for endpoint in endpoints.values())
        assert all(endpoint['filename'] is None for endpoint in
                   json.loads((archive / 'irc_endpoints.json').read_text())['endpoints'].values())
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in archive.iterdir()}


@pytest.mark.parametrize('negative_forward', [False, True])
def test_gaussian_archive_uses_native_path_numbers_for_forward_backward(tmp_path, negative_forward):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    log = _native_irc(tmp_path, 'gaussian')
    if negative_forward:
        # Synthetic parser variant: make Path 1 match the negative summary
        # coordinates. The captured paths have equal lengths, so distinguish
        # them by doubling Path 1 and the negative summary distances together.
        lines = []
        path_number = None
        summary = False
        for line in log.read_text().splitlines(keepends=True):
            if 'Point Number:' in line and 'Path Number:' in line:
                path_number = int(line.split()[-1])
            if 'NET REACTION COORDINATE UP TO THIS POINT =' in line and path_number == 1:
                prefix, _, value = line.partition('=')
                line = f'{prefix}= {2 * float(value):.5f}\n'
            if 'Summary of reaction path following' in line:
                summary = True
            parts = line.split()
            if summary and len(parts) == 3 and parts[0].isdigit() and float(parts[-1]) < 0:
                line = f'{parts[0]} {parts[1]} {2 * float(parts[-1]):.5f}\n'
            lines.append(line)
        log.write_text(''.join(lines))
    snapshot = snapshot_evidence_file(log, tmp_path)

    endpoints = orca_frames.extract_irc_endpoints(snapshot.snapshot_path)

    forward_key, backward_key = (('irc_end_a_path', 'irc_end_b_path') if negative_forward
                                 else ('irc_end_b_path', 'irc_end_a_path'))
    assert endpoints['forward']['geometry_ref'] == snapshot.metadata[forward_key]
    assert endpoints['backward']['geometry_ref'] == snapshot.metadata[backward_key]


@pytest.mark.parametrize('tamper', ['endpoint', 'missing_endpoint'])
def test_gaussian_archive_does_not_repair_untrusted_derived_endpoints(tmp_path, tamper):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    snapshot = snapshot_evidence_file(_native_irc(tmp_path, 'gaussian'), tmp_path)
    endpoint = Path(snapshot.metadata['irc_end_a_path'])
    if tamper == 'missing_endpoint':
        endpoint.unlink()
    else:
        endpoint.write_text('1\nforeign geometry\nH 0 0 0\n')
    before = {path: path.read_bytes() for path in endpoint.parent.iterdir()}

    endpoints = orca_frames.extract_irc_endpoints(snapshot.snapshot_path)

    assert all(item['geometry_ref'] is None and item['availability'] == 'unavailable'
               for item in endpoints.values())
    assert before == {path: path.read_bytes() for path in endpoint.parent.iterdir()}


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
@pytest.mark.parametrize('tamper', ['endpoint', 'log', 'missing_endpoint'])
def test_reader_rejects_changed_log_or_endpoint_without_rewriting(tmp_path, engine, tamper):
    from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts, write_irc_endpoint_artifacts

    log = _native_irc(tmp_path, engine)
    exported = write_irc_endpoint_artifacts(log)
    endpoint = Path(exported['irc_end_a_path'])
    if tamper == 'log':
        log.write_bytes(log.read_bytes() + b'\n')
    elif tamper == 'missing_endpoint':
        endpoint.unlink()
    else:
        endpoint.write_text('1\nforeign geometry\nH 0 0 0\n')
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}

    assert read_irc_endpoint_artifacts(log) == {}
    assert before == {path: path.read_bytes() for path in tmp_path.iterdir()}


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_failed_native_irc_has_no_canonical_handoff(tmp_path, engine):
    from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts, write_irc_endpoint_artifacts

    log = _native_irc(tmp_path, engine)
    # Deliberately abnormal local parser fixture; captured fixture bytes stay untouched.
    normal = 'Normal termination' if engine == 'gaussian' else 'ORCA TERMINATED NORMALLY'
    log.write_text(log.read_text().replace(normal, 'ENGINE ERROR TERMINATION'))

    assert write_irc_endpoint_artifacts(log) == {}
    assert read_irc_endpoint_artifacts(log) == {}
    assert not list(tmp_path.glob('*end-a.xyz'))


@pytest.mark.parametrize('fixture', ['gaussian/water_opt_freq_g16.out', 'orca/co2_freq_orca42.out'])
def test_opt_freq_log_is_not_an_irc_endpoint_source(tmp_path, fixture):
    from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

    log = tmp_path / 'minimum.log'
    shutil.copy2(FIXTURES / fixture, log)

    assert write_irc_endpoint_artifacts(log) == {}


def test_orca_export_requires_frozen_owned_sidecars_and_both_sides(tmp_path):
    from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

    log = _native_irc(tmp_path, 'orca')
    archive = tmp_path / 'irc_endpoints.json'
    manifest = archive.read_bytes()
    archive.unlink()
    assert write_irc_endpoint_artifacts(log) == {}
    archive.write_bytes(manifest)
    (tmp_path / 'irc_IRC_B.xyz').unlink()
    # The remaining direction must never be substituted for the absent one.
    assert write_irc_endpoint_artifacts(log) == {}


def test_gaussian_export_does_not_read_a_neighbor_irc_manifest(tmp_path):
    from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

    log = _native_irc(tmp_path, 'gaussian')
    neighbor = tmp_path / 'irc_endpoints.json'
    neighbor.write_text('{"log_sha256": "another job"}')

    assert len(write_irc_endpoint_artifacts(log)) == 2
    assert neighbor.read_text() == '{"log_sha256": "another job"}'


def test_gaussian_one_sided_native_path_has_no_bilateral_handoff(tmp_path):
    from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

    log = _native_irc(tmp_path, 'gaussian')
    lines = log.read_text().splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if 'Point Number:' in line and 'Path Number:' in line]
    summary = next(index for index, line in enumerate(lines) if 'Energies reported relative to the TS energy' in line)
    # Retain only path 1 in a local incomplete parser fixture, preserving original bytes on disk.
    one_side = ''.join(lines[:starts[0]])
    for first, last in zip(starts, starts[1:] + [summary], strict=True):
        if int(lines[first].split()[-1]) == 1:
            one_side += ''.join(lines[first:last])
    log.write_text(one_side + ''.join(lines[summary:]))

    assert write_irc_endpoint_artifacts(log) == {}


def test_export_io_failure_does_not_turn_native_qm_success_into_failure(tmp_path, monkeypatch, caplog):
    from cloudra.tools.core import irc_endpoint_artifacts

    log = _native_irc(tmp_path, 'gaussian')
    original = log.read_bytes()

    def no_space(*_args, **_kwargs):
        raise OSError('disk full while exporting derived XYZ')

    monkeypatch.setattr(irc_endpoint_artifacts, 'atomic_write_text', no_space)

    assert irc_endpoint_artifacts.write_irc_endpoint_artifacts(log) == {}
    assert irc_endpoint_artifacts.read_irc_endpoint_artifacts(log) == {}
    assert log.read_bytes() == original
    assert 'disk full' in caplog.text
