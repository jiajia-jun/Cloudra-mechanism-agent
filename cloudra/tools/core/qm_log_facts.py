"""Native QM facts shared by tools and scientific evidence consumers.

Normal termination and optimization are independent native facts. cclib is an
optional source for numerical properties; failure never erases native output.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cloudra.tools.core import gaussian_frames, orca_frames, xtb_frames
from cloudra.tools.core.irc_path import parse_xyz, same_geometry
from cloudra.tools.core.qm_engine import detect_qm_engine_from_text

_FLOAT = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][+-]?\d+)?)"
_ORCA_SCF_ENERGY = re.compile(rf"^\s*(?:Total Energy\s*:|SCF Energy\s*:)\s*{_FLOAT}\s+Eh", re.M)


@dataclass
class QmLogFacts:
    engine: str
    text: str
    normal_termination: bool
    opt_converged: bool | None
    job_types: set[str]
    frequencies_cm: list[float] | None
    scf_energy_hartree: float | None
    electronic_energy_hartree: float | None
    geometry: tuple | None
    parser_data: Any | None
    thermochemistry: dict[str, float]


def read_qm_log(path: str | Path) -> QmLogFacts:
    """Read a native log once; parse already-read text off the async loop."""
    with open(path, encoding='utf-8', errors='replace') as handle:
        text = handle.read()
    return parse_qm_log_text(text, source_path=str(path))


def parse_qm_log_text(text: str, *, source_path: str | None = None, engine: str | None = None) -> QmLogFacts:
    """Extract explicit native facts; absent data stays unknown, never zero."""
    detected = detect_qm_engine_from_text(text)
    if engine is not None and (engine not in {'gaussian', 'orca', 'xtb'}
                               or detected not in {'unknown', engine}):
        raise ValueError(f'Native log engine {detected!r} does not match {engine!r}.')
    engine = engine or detected
    data = None
    if engine != 'xtb':
        try:
            import cclib
            source = io.StringIO(text)
            if source_path is not None:
                source.name = source_path
            data = cclib.io.ccread(source)
        except Exception:
            pass
    parser = {'gaussian': gaussian_frames, 'orca': orca_frames, 'xtb': xtb_frames}.get(engine)
    normal = parser.normal_termination(text) if parser else False
    converged = parser.opt_converged(text) if parser else None
    jobs = parser.detect_job_types_from_text(text) if parser else set()
    frequencies = (parser.vibfreqs_from_text(text) or None) if parser else None
    geometry = None
    scf = None
    electronic = None
    thermo = {}
    if engine == 'gaussian':
        scf = gaussian_frames.scf_energy_hartree(text)
        electronic = gaussian_frames.electronic_energy_hartree(text)
        geometry = parse_xyz(gaussian_frames.final_xyz_from_text(text))
        thermo = gaussian_frames.extract_thermochemistry_from_text(text)
    elif engine == 'orca':
        matches = list(_ORCA_SCF_ENERGY.finditer(text))
        if matches:
            scf = float(matches[-1].group(1).replace('D', 'E').replace('d', 'e'))
        electronic = orca_frames.final_energy_hartree(text)
        geometry = parse_xyz(orca_frames.final_xyz_from_text(text))
        thermo = orca_frames.extract_thermochemistry_from_text(text)
    elif engine == 'xtb':
        electronic = xtb_frames.final_energy_hartree(text)
        scf = electronic
        geometry = parse_xyz(xtb_frames.final_xyz_from_text(text))
        thermo = xtb_frames.thermochemistry(text)
    if data is not None:
        if frequencies is None:
            values = getattr(data, 'vibfreqs', None)
            if values is not None and len(values):
                frequencies = [float(value) for value in values]
        if geometry is None:
            atomnos = getattr(data, 'atomnos', None)
            coords = getattr(data, 'atomcoords', None)
            if atomnos is not None and coords is not None and len(coords):
                geometry = parse_xyz(gaussian_frames._coords_to_xyz(atomnos, coords[-1]))
    if engine in {'gaussian', 'orca'} and geometry is not None:
        markers = ('Optimization stopped.', 'Optimization completed.', 'Stationary point found.') if engine == 'gaussian' else (
            'The optimization did not converge', 'THE OPTIMIZATION HAS CONVERGED')
        opt_index = max(text.rfind(marker) for marker in markers)
        if opt_index >= 0 and not same_geometry(geometry, _geometry_at_marker(text, engine, opt_index, after=True)):
            converged = None
        frequency_index = text.rfind('Frequencies --' if engine == 'gaussian' else 'VIBRATIONAL FREQUENCIES')
        if frequency_index >= 0 and not same_geometry(geometry, _geometry_at_marker(text, engine, frequency_index)):
            frequencies = None
    return QmLogFacts(engine=engine, text=text, normal_termination=normal,
        opt_converged=converged, job_types=jobs, frequencies_cm=frequencies,
        scf_energy_hartree=scf, electronic_energy_hartree=electronic,
        geometry=geometry, parser_data=data, thermochemistry=thermo)


def _geometry_at_marker(text: str, engine: str, index: int, *, after: bool = False) -> tuple | None:
    """Geometry belonging to a native result marker, before another job starts."""
    parser = gaussian_frames if engine == 'gaussian' else orca_frames
    start = parser.last_job_start(text[:index])
    geometry = parse_xyz(parser.final_xyz_from_text(text[start:index]))
    if geometry is not None and not after:
        return geometry
    # Some native optimization summaries precede their final Cartesian printout.
    labels = ('Standard orientation:', 'Input orientation:') if engine == 'gaussian' else (
        'CARTESIAN COORDINATES (ANGSTROEM)',)
    positions = sorted(position for label in labels
                       for position in [text.find(label, index)] if position >= 0)
    if not positions or parser.last_job_start(text[:positions[0]]) > start:
        return geometry
    if after and engine == 'orca' and 'FINAL ENERGY EVALUATION AT THE STATIONARY POINT' not in text[index:positions[0]]:
        return geometry
    following = [position for label in labels
                 for position in [text.find(label, positions[0] + 1)] if position >= 0]
    end = min(following) if following else len(text)
    return parse_xyz(parser.final_xyz_from_text(text[positions[0]:end]))
