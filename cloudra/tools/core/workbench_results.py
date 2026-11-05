"""Disk-backed workbench documents, reusing native scientific frame parsers.

These synchronous helpers belong on the service's worker thread. Only scalar
summaries and the selected geometry cross the API; trajectory coordinates stay
in separate disk records and are materialized one frame at a time.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from cloudra.persistence.fs_utils import atomic_write_json
from cloudra.tools.core import gaussian_frames, orca_frames
from cloudra.tools.core.molecule import _copy_molecule, read_molecule, serialize_molecule
from cloudra.tools.core.qm_engine import detect_qm_engine


def _sidecar_root(source: Path) -> Path:
    return source.parent.parent if source.parent.name == '.cloudra' else source.parent


def _trajectory_record(source: Path):
    from cloudra.tools.core.structure_artifacts import read_trajectory

    if source.resolve().parent != source.parent:
        raise ValueError('Force-field trajectory manifest must stay in its source directory')
    record = read_trajectory(str(source))
    if any(Path(path).resolve().parent != source.parent for path in (record.frames_path, record.frames_jsonl_path)):
        raise ValueError('Force-field trajectory sidecars must stay in their source directory')
    return record


def _trajectory_source(source: Path) -> Path | None:
    if source.name == 'trajectory.json':
        return source
    if source.name == 'frames.xyz' and source.with_name('trajectory.json').is_file():
        manifest = source.with_name('trajectory.json')
        if Path(_trajectory_record(manifest).frames_path).resolve() == source:
            return manifest
    return None


def _source_files(source: Path) -> list[Path]:
    """Fingerprint only actual local native sidecars, with symlinks bounded."""
    paths = {source}
    if source.suffix.lower() in {'.log', '.out'} and detect_qm_engine(str(source)) == 'orca':
        text = source.read_text(encoding='utf-8', errors='replace')
        bound = str(_sidecar_root(source))
        for directory, stem in orca_frames._bounded_sidecar_roots(str(source), text, bound):
            folder = Path(directory)
            candidates = [folder / (stem + suffix) for suffix in (
                '_IRC_F_trj.xyz', '_IRC_B_trj.xyz', '_NEB-TS_converged.xyz')]
            candidates.extend(path for path in folder.glob(stem + '_im*.xyz')
                              if path.name[len(stem) + 3:-4].isdigit())
            paths.update(path for path in candidates if orca_frames._allowed_sidecar(str(path), bound))
    elif trajectory := _trajectory_source(source):
        record = _trajectory_record(trajectory)
        paths.update((trajectory, Path(record.frames_path), Path(record.frames_jsonl_path)))
    return sorted(path for path in paths if path.is_file())


def _signature(source: Path) -> list[list]:
    return [[str(path), path.stat().st_mtime_ns, path.stat().st_size] for path in _source_files(source)]


def _document_directory(cache_root: Path, document_id: str) -> Path:
    if len(document_id) != 64 or any(char not in '0123456789abcdef' for char in document_id):
        raise ValueError('Invalid workbench document ID')
    return cache_root / document_id


def _read_metadata(cache_root: Path, document_id: str) -> dict:
    directory = _document_directory(cache_root, document_id)
    try:
        metadata = json.loads((directory / 'document.json').read_text())
    except FileNotFoundError as exc:
        raise ValueError('Workbench document is unavailable; reopen its source') from exc
    source = Path(metadata['source_path'])
    if metadata.get('_format_version') != 2 or metadata['_signature'] != _signature(source):
        open_document(source, cache_root)
        metadata = json.loads((directory / 'document.json').read_text())
    return metadata


def _frame_identities(mol, document_id: str):
    for atom in mol.GetAtoms():
        if not atom.HasProp('cloudra_atom_id'):
            atom.SetProp('cloudra_atom_id', f'{document_id}:{atom.GetIdx() + 1}')
    return mol


def _frame_geometry(directory: Path, index: int) -> dict:
    from cloudra.tools.core.workbench_geometry import geometry_view

    path = directory / f'frame-{index}.json'
    stored = json.loads(path.read_text())
    if 'molecule' in stored:
        mol = _copy_molecule(stored['molecule'])
    elif stored.get('xyz'):
        mol = read_molecule(input_text=stored['xyz'], input_format='xyz')
    else:
        raise ValueError(f'Frame {index} has no native geometry in this source')
    view = geometry_view(_frame_identities(mol, directory.name))
    if 'molecule' not in stored:
        atomic_write_json(path, {'molecule': view['molecule']})
    return view


def document_frame(cache_root: Path, document_id: str, index: int) -> dict:
    """Materialize one geometry; unavailable native coordinates stay unknown."""
    metadata = _read_metadata(cache_root, document_id)
    if index < 0 or index >= len(metadata['frames']):
        raise ValueError(f'Invalid frame index: {index}')
    return _frame_geometry(_document_directory(cache_root, document_id), index)


def _summary(frame) -> dict:
    summary = {'step': frame.step if frame.step is not None else frame.frame}
    for public, native in (
        ('energy_hartree', 'electronic_energy_hartree'), ('rms_force', 'rms_force'),
        ('max_force', 'max_force'), ('force_unit', 'force_unit'),
        ('reaction_coordinate', 'reaction_coordinate'), ('path_number', 'path_number'),
        ('converged', 'converged'),
    ):
        value = getattr(frame, native)
        if value is not None:
            summary[public] = value
    if frame.scan_coordinates:
        summary['scan_coordinates'] = frame.scan_coordinates
    return summary


def _normal_modes(parser, text: str, directory: Path, frames: list[dict]) -> tuple[list[dict], dict | None]:
    from cloudra.tools.core.workbench_geometry import geometry_view

    frequencies = parser.vibfreqs_from_text(text)
    if not frequencies:
        return [], None
    # A later linked SP job can change geometry. Bind modes to the geometry
    # actually printed before the last native frequency section.
    marker = 'Harmonic frequencies' if parser is gaussian_frames else 'VIBRATIONAL FREQUENCIES'
    position = text.rfind(marker)
    reference_xyz = parser.final_xyz_from_text(text[:position] if position >= 0 else text)
    if not reference_xyz:
        return [], None
    mol = read_molecule(input_text=reference_xyz, input_format='xyz')
    if parser is gaussian_frames:
        displacements = parser.vibdisps_from_text(text, len(frequencies))
    else:
        displacements = parser.vibdisps_from_text(text, len(frequencies), mol.GetNumAtoms())
    if displacements is None or displacements.shape != (len(frequencies), mol.GetNumAtoms(), 3):
        return [], None
    reference = geometry_view(_frame_identities(mol, directory.name))
    reference_frame = None
    # Comparison is by native coordinates/symbols, not frame order or energy.
    for index in range(len(frames) - 1, -1, -1):
        stored = json.loads((directory / f'frame-{index}.json').read_text())
        if stored.get('xyz', '').splitlines()[2:] == reference_xyz.splitlines()[2:]:
            reference_frame = index
            break
    return [dict(frequency_cm=float(frequency), displacements=displacements[index].tolist(),
                 reference_frame=reference_frame) for index, frequency in enumerate(frequencies)], reference


def _forcefield_frames(source: Path):
    """Consume the existing paired XYZ/JSONL writer contract incrementally."""
    from cclib.parser.utils import convertor

    record = _trajectory_record(source)
    with open(record.frames_jsonl_path, encoding='utf-8') as scalars:
        for xyz in gaussian_frames.iter_xyz_blocks(record.frames_path):
            line = scalars.readline()
            if not line:
                raise ValueError('Force-field trajectory is missing its paired scalar record')
            scalar = json.loads(line)
            summary = {'step': scalar['step'], 'energy': scalar['energy'],
                       'energy_unit': scalar['energy_unit'],
                       'energy_hartree': float(convertor(scalar['energy'], scalar['energy_unit'], 'hartree'))}
            if scalar.get('max_gradient') is not None:
                summary.update(max_force=scalar['max_gradient'], force_unit=scalar['energy_unit'] + '/angstrom')
            if scalar['step'] == record.frame_count - 1:
                summary['converged'] = record.status == 'converged'
            yield {'xyz': xyz}, summary


def _structure_frames(source: Path, data: dict | None):
    from rdkit import Chem

    if data is not None:
        yield {'molecule': data['molecule']}, {'step': 0}
    elif source.suffix.lower() == '.xyz':
        for index, xyz in enumerate(gaussian_frames.iter_xyz_blocks(source)):
            yield {'xyz': xyz}, {'step': index}
    elif source.suffix.lower() == '.sdf':
        with source.open('rb') as handle:
            for index, mol in enumerate(Chem.ForwardSDMolSupplier(handle, removeHs=False)):
                if mol is None:
                    raise ValueError(f'Cannot parse SDF molecule {index}')
                yield {'molecule': serialize_molecule(mol)}, {'step': index}
    else:
        mol = read_molecule(input_path=str(source), input_format='auto')
        yield {'molecule': serialize_molecule(mol)}, {'step': 0}


def open_document(source_path: Path, cache_root: Path, frame_index: int | None = None) -> dict:
    """Open/reopen a source, invalidating derived data when it or sidecars change."""
    source = source_path.resolve(strict=True)
    document_id = hashlib.sha256(str(source).encode()).hexdigest()
    directory = _document_directory(cache_root, document_id)
    signature = _signature(source)
    metadata_path = directory / 'document.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else None
    if metadata is None or metadata.get('_format_version') != 2 or metadata['_signature'] != signature:
        directory.mkdir(parents=True, exist_ok=True)
        metadata = {'document_id': document_id, 'title': source.name, 'source_path': str(source),
                    'task_type': 'structure', 'frames': [], 'modes': [], 'modes_reference_geometry': None,
                    'settings': {}, 'warnings': [], '_signature': signature, '_format_version': 2}
        parser = None
        text = ''
        if source.suffix.lower() in {'.log', '.out'}:
            engine = detect_qm_engine(str(source))
            if engine not in {'gaussian', 'orca'}:
                raise ValueError('This output is not a recognized Gaussian or ORCA log')
            parser = gaussian_frames if engine == 'gaussian' else orca_frames
            text = source.read_text(encoding='utf-8', errors='replace')
            metadata['task_type'] = '+'.join(sorted(parser.detect_job_types_from_text(text)))
            metadata['settings']['engine'] = engine
            native = (parser.extract_frames_from_text(text) if engine == 'gaussian' else
                      parser.extract_frames_from_text(text, log_path=str(source), sidecar_root=str(_sidecar_root(source))))
            frames = (({'xyz': frame.xyz}, _summary(frame)) for frame in native)
        elif trajectory := _trajectory_source(source):
            metadata['task_type'] = 'forcefield_optimization'
            metadata['settings']['forcefield'] = _trajectory_record(trajectory).engine
            frames = _forcefield_frames(trajectory)
        else:
            saved = None
            if source.suffix.lower() in {'.json', '.cloudra'}:
                saved = json.loads(source.read_text())
                if not isinstance(saved, dict) or not isinstance(saved.get('molecule'), str):
                    raise ValueError('Saved workbench file requires its native molecule state')
                metadata.update(title=saved.get('title', source.name), settings=saved.get('settings', {}))
                for key in ('frozen_coordinates', 'scan_coordinates', 'source_frame'):
                    if key in saved:
                        metadata[key] = saved[key]
            frames = _structure_frames(source, saved)
        for index, (geometry, summary) in enumerate(frames):
            atomic_write_json(directory / f'frame-{index}.json', geometry)
            metadata['frames'].append({'index': index, **summary, 'has_geometry': bool(geometry.get('xyz') or geometry.get('molecule'))})
        if not metadata['frames']:
            reason = parser.frames_unavailable_reason(str(source)) if parser is orca_frames else None
            raise ValueError(reason or 'No complete molecular frames are available in this source')
        if parser:
            modes, reference = _normal_modes(parser, text, directory, metadata['frames'])
            metadata.update(modes=modes, modes_reference_geometry=reference)
            if parser.vibfreqs_from_text(text) and not modes:
                metadata['warnings'].append('Native frequencies are present, but complete mode displacements/reference geometry are unavailable.')
            if any(not frame['has_geometry'] for frame in metadata['frames']):
                metadata['warnings'].append('Some native points have no printed geometry; their scalar facts remain available.')
        atomic_write_json(metadata_path, metadata)
    selected = (next((frame['index'] for frame in reversed(metadata['frames']) if frame['has_geometry']),
                     len(metadata['frames']) - 1) if frame_index is None else frame_index)
    if selected < 0 or selected >= len(metadata['frames']):
        raise ValueError(f'Invalid frame index: {selected}')
    geometry = _frame_geometry(directory, selected) if metadata['frames'][selected]['has_geometry'] else None
    return {key: value for key, value in metadata.items() if not key.startswith('_')} | {
        'selected_frame': selected, 'geometry': geometry,
    }


def document_csv(cache_root: Path, document_id: str) -> str:
    """Export scalar observations with explicit units and native point identity."""
    metadata = _read_metadata(cache_root, document_id)
    columns = ['index', 'step', 'has_geometry', 'path_number', 'reaction_coordinate', 'scan_coordinates',
               'energy_hartree', 'energy', 'energy_unit', 'rms_force', 'max_force', 'force_unit', 'converged']
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for frame in metadata['frames']:
        row = dict(frame)
        if 'scan_coordinates' in row:
            row['scan_coordinates'] = json.dumps(row['scan_coordinates'])
        writer.writerow(row)
    return buffer.getvalue()
