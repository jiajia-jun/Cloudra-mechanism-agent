from pathlib import Path

import pytest

from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema


def _scan_files(tmp_path, energies):
    log = tmp_path / '.cloudra' / 'calc-43.out.log'
    log.parent.mkdir()
    job = tmp_path / 'scan'
    blocks = ['* O   R   C   A *', f'NAME = {job}.inp']
    for point, energy in enumerate(energies, 1):
        xyz = f'2\npoint {point}\nH 0 0 0\nH {point} 0 0\n'
        Path(f'{job}.{point:03d}.xyz').write_text(xyz)
        blocks.append(
            f'RELAXED SURFACE SCAN STEP {point}\n'
            'CARTESIAN COORDINATES (ANGSTROEM)\n'
            '-------------------------------\n'
            f'H 0 0 0\nH {point} 0 0\n\n'
            'THE OPTIMIZATION HAS CONVERGED\n'
            f'FINAL SINGLE POINT ENERGY {energy:.12f}\n'
        )
    blocks.append('ORCA TERMINATED NORMALLY')
    log.write_text('\n'.join(blocks))
    return log, job


@pytest.mark.asyncio
async def test_convergence_request_also_receives_scan_peak_and_existing_frame(tmp_path, monkeypatch):
    import cclib

    monkeypatch.setattr(cclib.io, 'ccread', lambda *_: None)
    energies = [
        -496.540781012776, -496.540711208504, -496.540437282722,
        -496.539980513546, -496.539387787395, -496.538762222423,
        -496.538391301586, -496.539643131435, -496.543788062415,
        -496.549942677032, -496.556954418877, -496.563630216755,
        -496.568558861648, -496.573698031640,
    ]
    log, job = _scan_files(tmp_path, energies)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=['convergence']), session=None,
    )

    assert result.is_success is True
    assert result.normal_termination is True
    assert result.scan_has_internal_peak is True
    assert result.scan_peak.point_number == 7
    assert result.scan_peak.energy_hartree == pytest.approx(energies[6])
    assert result.scan_peak.relative_to_first_point_kcal == pytest.approx(1.49956647)
    assert result.scan_peak.geometry_ref == f'{job}.007.xyz'
    assert {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


@pytest.mark.asyncio
async def test_monotonic_scan_does_not_offer_endpoint_as_peak(tmp_path, monkeypatch):
    import cclib

    monkeypatch.setattr(cclib.io, 'ccread', lambda *_: None)
    log, _ = _scan_files(tmp_path, [-10.0, -9.0, -8.0])

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=['convergence']), session=None,
    )

    assert result.is_success is True
    assert result.scan_has_internal_peak is False
    assert result.scan_peak is None


@pytest.mark.asyncio
async def test_missing_peak_frame_is_not_replaced_with_last_frame(tmp_path, monkeypatch):
    import cclib

    monkeypatch.setattr(cclib.io, 'ccread', lambda *_: None)
    log, job = _scan_files(tmp_path, [-10.0, -9.0, -11.0])
    Path(f'{job}.002.xyz').unlink()

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=['convergence']), session=None,
    )

    assert result.scan_has_internal_peak is True
    assert result.scan_peak.point_number == 2
    assert result.scan_peak.geometry_ref is None


@pytest.mark.asyncio
@pytest.mark.parametrize('missing_point', [2, 3])
async def test_sidecar_missing_geometry_keeps_known_peak(tmp_path, monkeypatch, missing_point):
    import cclib

    monkeypatch.setattr(cclib.io, 'ccread', lambda *_: None)
    log, job = _scan_files(tmp_path, [-10.0, -9.0, -11.0])
    Path(f'{job}.relaxscanact.dat').write_text('1 -10\n2 -9\n3 -11\n')
    Path(f'{job}.{missing_point:03d}.xyz').unlink()

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=['convergence']), session=None,
    )

    assert result.is_success is True
    assert result.scan_has_internal_peak is True
    assert result.scan_peak.point_number == 2
    assert result.scan_peak.energy_hartree == -9.0
    assert result.scan_peak.geometry_ref is None


@pytest.mark.asyncio
async def test_gaussian_scan_peak_is_reported_without_writing_geometry(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import cclib

    monkeypatch.setattr(cclib.io, 'ccread', lambda *_: SimpleNamespace())
    log = tmp_path / 'scan.log'
    log.write_text(
        'Entering Gaussian System\n#p hf/sto-3g opt=modredundant\n'
        'Summary of Optimized Potential Surface Scan\n'
        'Eigenvalues -- -10.000000 -9.000000 -11.000000\n'
        'Normal termination of Gaussian\n'
    )
    before = log.read_bytes()

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=['convergence']), session=None,
    )

    assert result.is_success is True
    assert result.scan_has_internal_peak is True
    assert result.scan_peak.point_number == 2
    assert result.scan_peak.geometry_ref is None
    assert list(tmp_path.iterdir()) == [log]
    assert log.read_bytes() == before
