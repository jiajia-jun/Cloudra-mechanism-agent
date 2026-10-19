"""Final-result consumers must not parse unused calculation trajectories."""

import pytest

from cloudra.benchmark import barrier_evidence
from cloudra.dag.file_science import _final_geometry
from cloudra.tools.core import gaussian_frames
from tests.ts_fixtures import native_qm_log


@pytest.mark.parametrize('consumer', ['dag', 'frequency_support', 'energy_identity'])
def test_final_geometry_consumers_do_not_parse_unused_frames(tmp_path, monkeypatch, consumer):
    symbols = ['H', 'H']
    positions = [[0., 0., 0.], [0., 0., .74]]
    for name, frequencies in [('a.log', None), ('b.log', [1000.])]:
        text = native_qm_log('gaussian', symbols, positions,
            optimization=None, frequencies=frequencies)
        (tmp_path / name).write_text(text.replace('Normal termination',
            'SCF Done: E(RHF) = -75.0 A.U.\nNormal termination'))

    original = gaussian_frames.extract_frames_from_text
    frame_parses = []

    def counted_frames(text):
        frame_parses.append(text)
        return original(text)

    monkeypatch.setattr(gaussian_frames, 'extract_frames_from_text', counted_frames)
    if consumer == 'dag':
        geometry = _final_geometry(tmp_path / 'a.log')
        assert geometry[0] == symbols
        assert geometry[1] == positions
    elif consumer == 'frequency_support':
        assert barrier_evidence._frequency_supported(tmp_path, 'a.log', ['b.log'], 0)
    else:
        assert barrier_evidence._identify_by_declared_energy(
            tmp_path, ['a.log', 'b.log'], -75.) == 'a.log'

    assert len(frame_parses) == 0
