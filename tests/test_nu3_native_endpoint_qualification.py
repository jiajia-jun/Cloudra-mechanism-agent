"""Real NU3 endpoint replay: valid provenance does not replace minimum qualification."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from cloudra.tools.core import irc_evidence
from cloudra.tools.core.irc_path import same_geometry
from cloudra.tools.core.qm_log_facts import read_qm_log

FIXTURE = Path(__file__).parent / 'fixtures/nu3_endpoint_20261020'


@pytest.fixture
def native_endpoint(tmp_path):
    manifest = json.loads((FIXTURE / 'manifest.json').read_text())
    for record in manifest['files']:
        compressed = (FIXTURE / record['archive']).read_bytes()
        assert hashlib.sha256(compressed).hexdigest() == record['gzip_sha256']
        raw = gzip.decompress(compressed)
        assert len(raw) == record['uncompressed_bytes']
        assert hashlib.sha256(raw).hexdigest() == record['sha256']
        path = tmp_path / record['restore_path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return tmp_path


def test_normal_native_completion_does_not_make_a_zero_imaginary_minimum(native_endpoint):
    optimization = read_qm_log(native_endpoint / 'opt/calc-124.out.log')
    frequency = read_qm_log(native_endpoint / 'freq/calc-125.out.log')

    assert optimization.normal_termination is True
    assert optimization.opt_converged is True
    assert frequency.normal_termination is True
    assert irc_evidence.imag_freqs(frequency.frequencies_cm) == pytest.approx([-84.93])
    assert same_geometry(optimization.geometry, frequency.geometry)


def test_optimization_starts_at_the_original_irc_outer_frame(native_endpoint):
    irc_log = native_endpoint / 'irc/calc-108.out.log'
    receipt = json.loads((native_endpoint / 'opt/endpoint_source.json').read_text())
    assert receipt['irc_job_id'] == 108
    assert receipt['irc_log_sha256'] == hashlib.sha256(irc_log.read_bytes()).hexdigest()
    assert receipt['sha256'] == hashlib.sha256(
        (native_endpoint / 'opt/reactant_source.xyz').read_bytes()).hexdigest()

    endpoints = irc_evidence.irc_endpoint_geometries(irc_log)
    optimization = irc_evidence._optimization_geometries(native_endpoint / 'opt/calc-124.out.log')
    assert endpoints is not None
    assert optimization is not None
    assert same_geometry(optimization[0], endpoints[0])


def test_shared_endpoint_verifier_rejects_the_native_imaginary_frequency(native_endpoint):
    logs = [native_endpoint / 'opt/calc-124.out.log', native_endpoint / 'freq/calc-125.out.log']
    details = []
    minima = irc_evidence._optimized_minima(
        logs, smiles=None, side='SOURCE', charge=0, details=details,
    )
    assert minima == []
    assert any('n_imag=1' in item for item in details)
