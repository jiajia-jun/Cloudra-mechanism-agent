"""Scientific checks for submitted files, shared by review and delivery audit."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cloudra.dag.evidence_ingest import FileEvidenceSnapshot, _extract_qm_log
from cloudra.dag.store import InvalidGraphReference
from cloudra.tools.core import gaussian_frames, orca_frames, xtb_frames
from cloudra.tools.core.irc_evidence import (
    frames_for,
    last_geometry,
    verify_short_irc_direction,
    verify_short_irc_pair,
)


class ScientificCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['passed', 'failed', 'incomplete']
    detail: str
    next_action: str = ''


def _logs(store, element, workspace_root=None):
    """Use bound immutable file snapshots; never substitute a workflow verdict."""
    logs, problems = [], []
    refs = list(element.refs) + [s.ref for s in element.stages if s.ref is not None and s.status.value == 'supported']
    for ref in refs:
        try:
            payload = store.resolve_evidence(ref)
        except InvalidGraphReference as exc:
            problems.append(str(exc))
            continue
        if not isinstance(payload, dict):
            continue
        if 'snapshot_path' not in payload:
            raw = (payload.get('arguments') or {}).get('log_path')
            if not isinstance(raw, str) or not raw:
                continue
            path = Path(raw)
            if not path.is_absolute():
                if workspace_root is None:
                    problems.append(f'Relative stage log needs its workspace: {raw}')
                    continue
                path = Path(workspace_root) / path
            if not path.is_file():
                problems.append(f'Bound stage log is missing: {path}')
                continue
            is_qm, engine, freqs, imag, energy, modes = _extract_qm_log(path)
            snap = FileEvidenceSnapshot(original_path=str(path), snapshot_path=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), file_size=path.stat().st_size,
                is_qm_log=is_qm, engine=engine, frequencies=freqs,
                imaginary_frequencies=imag, final_energy_hartree=energy, normal_modes=modes)
        else:
            snap = FileEvidenceSnapshot.model_validate(payload)
        path = Path(snap.snapshot_path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != snap.sha256:
            problems.append(f'Immutable evidence is missing or changed: {path}')
            continue
        artifacts = [*snap.metadata.get("irc_sidecars", []),
                     *([snap.metadata["irc_manifest"]] if snap.metadata.get("irc_manifest") else [])]
        if any(not Path(item["snapshot_path"]).is_file() or
               hashlib.sha256(Path(item["snapshot_path"]).read_bytes()).hexdigest() != item["sha256"]
               for item in artifacts):
            problems.append(f'Immutable IRC endpoint evidence is missing or changed: {path}')
            continue
        if str(path) in logs:
            continue
        engine = snap.engine
        parser = {'orca': orca_frames, 'gaussian': gaussian_frames, 'xtb': xtb_frames}.get(engine)
        if parser is None or not parser.normal_termination(path.read_text(errors='replace')):
            problems.append(f'No native normal termination in {path}')
            continue
        logs.append(str(path))
    return logs, problems


def _final_geometry(path):
    from cloudra.tools.core.irc_path import parse_xyz
    from cloudra.tools.core.qm_engine import detect_qm_engine

    if detect_qm_engine(str(path)) == 'xtb':
        return parse_xyz(xtb_frames.final_xyz_from_text(Path(path).read_text(errors='replace')))
    return last_geometry(path, frames_for(path)[0])


def validate_frequency_geometry(opt_snap, freq_snap):
    """Require the same coordinates up to atom order, translation and rotation.

    The error bound is the rounding error of two six-decimal XYZ records,
    using the existing XYZ output precision; it is not a conformer/RMSD cutoff.
    Reflections and changes of molecular geometry are not rigid rotations.
    """
    import numpy as np

    from cloudra.tools.core.irc_path import align_atom_order

    if opt_snap.sha256 == freq_snap.sha256:
        return
    geometries = [_final_geometry(s.snapshot_path) for s in (opt_snap, freq_snap)]
    if any(geo is None for geo in geometries):
        raise ValueError('Optimization/frequency identity requires final geometry in both files.')
    reference, mobile = geometries
    alignment = align_atom_order(*reference, *mobile)
    matches = False
    if alignment is not None:
        ref = np.asarray(reference[1], dtype=float)
        mob = np.asarray(mobile[1], dtype=float)[alignment[0]]
        ref = ref - ref.mean(axis=0)
        mob = mob - mob.mean(axis=0)
        u, _, vt = np.linalg.svd(mob.T @ ref)
        if np.linalg.det(u @ vt) < 0:
            u[:, -1] *= -1
        residual = np.linalg.norm(mob @ (u @ vt) - ref, axis=1)
        matches = bool(np.max(residual) <= np.sqrt(3) * 10 ** -6)
    if not matches:
        raise ValueError('Optimization and frequency files contain different geometries; '
                         'submit the frequency calculation for the delivered optimized structure.')


def _geometry_species(path: str, smiles: str) -> bool:
    """Match the actual final structure using the existing RDKit bond perception.

    A SMILES annotation alone is not molecular evidence. Failure to perceive
    bonds remains missing identity evidence, never an inferred match.
    """
    from collections import Counter

    try:
        from rdkit import Chem
        from rdkit.Chem import rdDetermineBonds
    except ImportError as exc:
        raise RuntimeError(
            "Species geometry identity requires RDKit; install or repair cloudra[chem] "
            "and re-submit the evidence."
        ) from exc

    from cloudra.tools.core.irc_path import xyz_block

    expected = Chem.MolFromSmiles(smiles)
    if expected is None:
        raise ValueError(f"Invalid species SMILES: {smiles}")
    for atom in expected.GetAtoms():
        atom.SetAtomMapNum(0)
    geometry = _final_geometry(path)
    if geometry is None:
        raise ValueError(f"No final geometry in {path}")
    symbols, positions = geometry
    counts = Counter(atom.GetSymbol() for atom in Chem.AddHs(expected).GetAtoms())
    if Counter(symbols) != counts:
        return False
    actual = Chem.MolFromXYZBlock(xyz_block(symbols, positions))
    if actual is None:
        raise ValueError(f"Cannot read final geometry in {path}")
    rdDetermineBonds.DetermineBonds(actual, charge=Chem.GetFormalCharge(expected))
    actual = Chem.RemoveHs(actual)
    expected = Chem.RemoveHs(expected)
    # Unspecified stereochemistry permits either configuration. Explicit
    # stereochemistry remains part of the query and must match.
    return (actual.GetNumAtoms() == expected.GetNumAtoms()
            and actual.GetNumBonds() == expected.GetNumBonds()
            and actual.HasSubstructMatch(expected, useChirality=True))


def _species_minimum_check(smiles, logs, problems):
    if not smiles:
        return ScientificCheck(status='incomplete', detail='Species identity is not declared.',
            next_action='Declare the species SMILES before submitting minimum evidence.')
    minimum_logs = [p for p in logs if _extract_qm_log(Path(p))[3] == []]
    components = smiles.split('.')
    covered = set()
    for path in minimum_logs:
        for identity in dict.fromkeys([smiles, *components]):
            try:
                matches = _geometry_species(path, identity)
            except (ValueError, RuntimeError) as exc:
                problems.append(str(exc))
                continue
            if matches:
                if identity == smiles:
                    return ScientificCheck(status='passed',
                        detail='Normally terminated zero-imaginary-frequency geometry matches the complete species.')
                covered.add(identity)
    missing = sorted(set(components) - covered)
    if not missing and len(components) > 1:
        return ScientificCheck(status='passed', detail=(
            'All component species have matching zero-imaginary-frequency evidence. '
            'Component coverage does not verify a complex minimum, an IRC endpoint or an energy reference.'))
    return ScientificCheck(status='incomplete',
        detail='Missing matching minimum evidence for: ' + ', '.join(missing) + '. ' + ' '.join(dict.fromkeys(problems)),
        next_action='Submit matching normally terminated frequency logs for the whole species or all components together. '
                    'Keep IRC and complex-energy requirements separate; unsuccessful searches do not establish nonexistence.')


def file_scientific_checks(store, graph, target_id: str, *, irc_files=None, workspace_root=None, evidence_refs=None) -> dict[str, dict]:
    element = next((n for n in graph.nodes if n.node_id == target_id), None)
    is_edge = element is None
    if is_edge:
        element = next(e for e in graph.edges if e.edge_id == target_id)
    if evidence_refs is not None:
        element = element.model_copy(update={'refs': list(evidence_refs), 'stages': []})
    logs, problems = _logs(store, element, workspace_root)
    if not is_edge:
        return {'geometry': _species_minimum_check(element.smiles, logs, problems).model_dump()}
    frequencies = [_extract_qm_log(Path(p))[3] for p in logs]
    expected = 1 if is_edge else 0
    passed = any(f is not None and len(f) == expected for f in frequencies)
    status = 'passed' if passed else 'failed' if any(f is not None for f in frequencies) else 'incomplete'
    frequency_check = ScientificCheck(status=status,
        detail=f'Native normal termination and exactly {expected} imaginary frequencies required. ' + ' '.join(problems),
        next_action='' if passed else f'Submit a normally terminated frequency log showing {expected} imaginary frequencies; repair the calculation or supply missing evidence.')
    checks = {'frequency' if is_edge else 'geometry': frequency_check}
    if is_edge:
        checks['ts_opt'] = frequency_check
        source = next((n for n in graph.nodes if n.node_id == element.source_node_id), None)
        target = next((n for n in graph.nodes if n.node_id == element.target_node_id), None)
        source_logs, _ = _logs(store, source, workspace_root) if source else ([], [])
        target_logs, _ = _logs(store, target, workspace_root) if target else ([], [])
        details = []
        irc_passed = False
        for path in logs:
            try:
                engine = _extract_qm_log(Path(path))[1]
                if engine == 'orca':
                    orca_frames.extract_irc(path)
                elif engine == 'gaussian':
                    gaussian_frames.extract_irc(path)
                else:
                    continue
            except ValueError:
                continue
            try:
                irc_passed, reason = verify_short_irc_direction(path, logs, target_logs, source_logs)
                details.extend(reason)
            except Exception as exc:
                details.append(f'IRC direction proof could not be evaluated: {exc}')
            if irc_passed:
                break
        if not irc_passed and irc_files and irc_files.get('irc_forward_file') and irc_files.get('irc_reverse_file'):
            forward = FileEvidenceSnapshot.model_validate(irc_files['irc_forward_file']).snapshot_path
            reverse = FileEvidenceSnapshot.model_validate(irc_files['irc_reverse_file']).snapshot_path
            if forward in logs and reverse in logs:
                irc_passed, reason = verify_short_irc_pair(forward, reverse, logs, target_logs, source_logs)
                details.extend(reason)
        checks['short_irc'] = ScientificCheck(status='passed' if irc_passed else 'incomplete',
            detail='Geometric IRC direction interval proof passed.' if irc_passed else ' '.join(details) or 'No usable bound bidirectional IRC evidence.',
            next_action='' if irc_passed else 'Submit the IRC log with both endpoint geometries and frequency-verified source/target minima. Re-submit this step after adding evidence; full IRC convergence is not required.')
    return {stage: check.model_dump() for stage, check in checks.items()}
