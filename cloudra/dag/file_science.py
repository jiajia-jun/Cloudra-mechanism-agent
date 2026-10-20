"""Scientific checks for submitted files, shared by review and delivery audit."""
from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cloudra.dag.evidence_ingest import FileEvidenceSnapshot, _extract_qm_log
from cloudra.dag.store import InvalidGraphReference
from cloudra.tools.core import gaussian_frames, orca_frames, xtb_frames
from cloudra.tools.core.irc_evidence import (
    irc_endpoint_recovery_hint,
    normal_log,
    verify_short_irc_direction,
    verify_short_irc_pair,
)
from cloudra.tools.core.qm_log_facts import read_qm_log
from cloudra.tools.core.species_identity import chemical_smiles, species_smiles


class ScientificCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['passed', 'failed', 'incomplete']
    detail: str
    next_action: str = ''


_SCIENCE_CACHE_LOCK = threading.Lock()
_SCIENCE_CACHE: OrderedDict[str, tuple[dict, int]] = OrderedDict()
_SCIENCE_CACHE_BYTES = 4 * 1024 * 1024


def _science_cache_key(store, graph, target_id, *, irc_files, workspace_root, evidence_refs, endpoint_refs):
    """Version only bound immutable dependencies; mutable workflow logs stay fresh."""
    from cloudra.dag.models import GraphRef

    element = next((n for n in graph.nodes if n.node_id == target_id), None)
    if element is None:
        element = next((e for e in graph.edges if e.edge_id == target_id), None)
    if element is None:
        return None
    elements = [element]
    if hasattr(element, 'source_node_id'):
        elements.extend(node for node in graph.nodes
                        if node.node_id in (element.source_node_id, element.target_node_id))
    refs = []
    for item in elements:
        if item is element and evidence_refs is not None:
            refs.extend(evidence_refs)
        else:
            refs.extend([*item.refs, *[stage.ref for stage in item.stages
                                     if stage.ref is not None and stage.status.value == 'supported']])
    refs.extend(GraphRef.model_validate(ref) for ref in (endpoint_refs or {}).values())
    payloads = []
    for ref in dict.fromkeys(refs):
        try:
            payload = store.resolve_evidence(ref)
        except InvalidGraphReference:
            return None
        if not isinstance(payload, dict):
            continue
        if 'snapshot_path' not in payload:
            if (payload.get('arguments') or {}).get('log_path'):
                return None
            continue
        payloads.append(payload)
    payloads.extend((irc_files or {}).values())
    versions = {}
    for payload in payloads:
        snap = FileEvidenceSnapshot.model_validate(payload)
        paths = [snap.snapshot_path, *[item['snapshot_path'] for item in snap.metadata.get('irc_sidecars', [])]]
        if snap.metadata.get('irc_manifest'):
            paths.append(snap.metadata['irc_manifest']['snapshot_path'])
        recovery_paths = {snap.metadata[key] for key in ('irc_end_a_path', 'irc_end_b_path')
                          if snap.metadata.get(key)}
        paths.extend(recovery_paths)
        for raw in paths:
            path = Path(raw)
            try:
                stat = path.lstat() if raw in recovery_paths else path.stat()
            except OSError:
                versions[str(path)] = None
            else:
                versions[str(path)] = (stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size,
                                       stat.st_mtime_ns, stat.st_ctime_ns)
    payload = [graph.model_dump(mode='json'), target_id, str(workspace_root), payloads,
               [ref.model_dump(mode='json') for ref in evidence_refs] if evidence_refs is not None else None,
               irc_files, endpoint_refs, versions]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _qm_data(path, parsed=None):
    if parsed is None:
        return _extract_qm_log(Path(path))
    key = str(path)
    if key not in parsed:
        parsed[key] = _extract_qm_log(Path(path))
    return parsed[key]


def _logs(store, element, workspace_root=None, *, atom_bindings=None, parsed=None):
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
            is_qm, engine, freqs, imag, energy, modes = _qm_data(path, parsed)
            from cloudra.services.ts_pipeline_context import pipeline_database
            from cloudra.services.ts_pipeline_store import atom_binding_for_log
            binding = atom_binding_for_log(pipeline_database(), path, workspace_root or path.parent)
            snap = FileEvidenceSnapshot(original_path=str(path), snapshot_path=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), file_size=path.stat().st_size,
                is_qm_log=is_qm, engine=engine, frequencies=freqs,
                imaginary_frequencies=imag, final_energy_hartree=energy, normal_modes=modes,
                metadata={'atom_binding': binding} if binding else {})
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
        if parser is None or not (parser.normal_termination(path.read_text(errors='replace')) if engine == 'xtb' else normal_log(path)):
            problems.append(f'No usable normally terminated calculation segment in {path}; frequency and final geometry must describe the same calculation structure.')
            continue
        logs.append(str(path))
        if atom_bindings is not None and snap.metadata.get('atom_binding'):
            atom_bindings[str(path)] = snap.metadata['atom_binding']
    return logs, problems


def _final_geometry(path):
    from cloudra.tools.core.irc_path import parse_xyz
    from cloudra.tools.core.qm_engine import detect_qm_engine

    if Path(path).suffix.lower() == '.xyz':
        return parse_xyz(Path(path).read_text(errors='replace'))

    if detect_qm_engine(str(path)) == 'xtb':
        return parse_xyz(xtb_frames.final_xyz_from_text(Path(path).read_text(errors='replace')))
    return read_qm_log(path).geometry


def validate_frequency_geometry(opt_snap, freq_snap):
    """Require the same coordinates up to atom order, translation and rotation.

    The error bound is the rounding error of two six-decimal XYZ records,
    using the existing XYZ output precision; it is not a conformer/RMSD cutoff.
    Reflections and changes of molecular geometry are not rigid rotations.
    """
    from cloudra.tools.core.irc_path import same_geometry

    if opt_snap.sha256 == freq_snap.sha256:
        return
    geometries = [_final_geometry(s.snapshot_path) for s in (opt_snap, freq_snap)]
    if any(geo is None for geo in geometries):
        raise ValueError('Optimization/frequency identity requires final geometry in both files.')
    if not same_geometry(*geometries):
        raise ValueError('Optimization and frequency files contain different geometries; '
                         'submit the frequency calculation for the delivered optimized structure.')


def _geometry_species(path: str, smiles: str | list[str], *, diagnostics: list[str] | None = None) -> bool:
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

    expected = Chem.MolFromSmiles(chemical_smiles(smiles))
    if expected is None:
        raise ValueError(f"Invalid species SMILES: {smiles}")
    for atom in expected.GetAtoms():
        atom.SetAtomMapNum(0)
    expected = Chem.AddHs(expected)
    geometry = _final_geometry(path)
    if geometry is None:
        raise ValueError(f"No final geometry in {path}")
    symbols, positions = geometry
    counts = Counter(atom.GetSymbol() for atom in expected.GetAtoms())
    if Counter(symbols) != counts:
        if diagnostics is not None:
            diagnostics.append(f'Geometry composition mismatch for declared {smiles}: '
                               f'expected {dict(counts)}, observed {dict(Counter(symbols))}.')
        return False
    actual = Chem.MolFromXYZBlock(xyz_block(symbols, positions))
    if actual is None:
        raise ValueError(f"Cannot read final geometry in {path}")
    rdDetermineBonds.DetermineBonds(actual, charge=Chem.GetFormalCharge(expected))
    # Compare both full explicit-H graphs. RemoveHs preserves neighbours of
    # non-tetrahedral stereocentres, so comparing it with an implicit-H query
    # incorrectly rejects e.g. a correctly perceived five-coordinate P ring.
    # Unspecified stereochemistry permits either configuration. Explicit
    # stereochemistry remains part of the query and must match.
    matches = (actual.GetNumAtoms() == expected.GetNumAtoms()
               and actual.GetNumBonds() == expected.GetNumBonds()
               and actual.HasSubstructMatch(expected, useChirality=True))
    if not matches and diagnostics is not None:
        diagnostics.append(f'Geometry identity mismatch: declared {smiles}; '
                           f'perceived {Chem.MolToSmiles(actual)}. '
                           'Check the optimized connectivity, charge and bond orders; '
                           'a mismatch is not proof of a perception failure.')
    return matches


def _species_minimum_check(smiles, logs, problems, *, parsed=None):
    if not smiles:
        return ScientificCheck(status='incomplete', detail='Species identity is not declared.',
            next_action='Declare the species SMILES before submitting minimum evidence.')
    minimum_logs = [p for p in logs if _qm_data(p, parsed)[3] == []]
    components = species_smiles(smiles)
    covered = set()
    for path in minimum_logs:
        for identity in dict.fromkeys(components):
            try:
                matches = _geometry_species(path, identity, diagnostics=problems)
            except (ValueError, RuntimeError) as exc:
                problems.append(str(exc))
                continue
            if matches:
                covered.add(identity)
    missing = sorted(set(components) - covered)
    if not missing:
        return ScientificCheck(status='passed', detail=(
            'All separated species have matching normally terminated zero-imaginary-frequency geometries; '
            'this does not verify a complex minimum or a combined energy reference.'
            if len(components) > 1 else
            'Normally terminated zero-imaginary-frequency geometry matches the complete species.'))
    return ScientificCheck(status='incomplete',
        detail='Missing matching minimum evidence for: ' + ', '.join(missing) + '. ' + ' '.join(dict.fromkeys(problems)),
        next_action='Submit matching normally terminated frequency logs for each declared species; a dot-connected complex requires its own minimum. '
                    'Keep IRC and complex-energy requirements separate; unsuccessful searches do not establish nonexistence.')


def _optimization_converged(path: str, engine: str | None) -> bool | None:
    if engine in {'orca', 'gaussian'}:
        return read_qm_log(path).opt_converged
    if engine == 'xtb':
        return xtb_frames.opt_converged(Path(path).read_text(errors='replace'))
    return None


def _ts_optimization_check(logs: list[str], *, parsed=None) -> ScientificCheck:
    frequency_logs = [p for p in logs if len(_qm_data(p, parsed)[3] or []) == 1]
    problems = []
    failed = False
    for path in logs:
        engine = _qm_data(path, parsed)[1]
        converged = _optimization_converged(path, engine)
        if converged is False:
            failed = True
            problems.append(f'Optimization did not converge in {path}.')
            continue
        if converged is not True:
            continue
        for frequency in frequency_logs:
            def snapshot(p):
                return FileEvidenceSnapshot(original_path=p, snapshot_path=p,
                    sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest(), file_size=Path(p).stat().st_size)
            try:
                validate_frequency_geometry(snapshot(path), snapshot(frequency))
            except ValueError as exc:
                failed = True
                problems.append(str(exc))
                continue
            return ScientificCheck(status='passed',
                detail='Native optimization convergence and one-imaginary-frequency evidence for the same geometry passed; reaction direction is checked separately.')
    return ScientificCheck(status='failed' if failed else 'incomplete',
        detail='Native converged optimization with matching first-order-saddle frequency evidence required. ' + ' '.join(dict.fromkeys(problems)),
        next_action='Submit the normally terminated converged optimization and its matching frequency log; a frequency-only calculation is not optimization evidence.')


def file_scientific_checks(store, graph, target_id: str, *, irc_files=None, workspace_root=None, evidence_refs=None, endpoint_refs=None, use_cache=False) -> dict[str, dict]:
    """Reuse derived prompt checks only; submit/review/delivery always verify afresh."""
    options = dict(irc_files=irc_files, workspace_root=workspace_root,
                   evidence_refs=evidence_refs, endpoint_refs=endpoint_refs)
    key = _science_cache_key(store, graph, target_id, **options) if use_cache else None
    if key is not None:
        with _SCIENCE_CACHE_LOCK:
            cached = _SCIENCE_CACHE.get(key)
            if cached is not None:
                _SCIENCE_CACHE.move_to_end(key)
                return deepcopy(cached[0])
    checks = _file_scientific_checks(store, graph, target_id, **options)
    if key is not None and _science_cache_key(store, graph, target_id, **options) == key:
        size = len(json.dumps(checks).encode())
        if size <= _SCIENCE_CACHE_BYTES:
            with _SCIENCE_CACHE_LOCK:
                _SCIENCE_CACHE[key] = deepcopy(checks), size
                _SCIENCE_CACHE.move_to_end(key)
                while len(_SCIENCE_CACHE) > 64 or sum(item[1] for item in _SCIENCE_CACHE.values()) > _SCIENCE_CACHE_BYTES:
                    _SCIENCE_CACHE.popitem(last=False)
    return checks


def _step_endpoint_logs(store, graph, element, workspace_root=None, *, endpoint_refs=None, parsed=None, problems=None):
    """Select the same bound native endpoint logs for review and file delivery."""
    problems = problems if problems is not None else []

    def endpoint_candidates(key, node):
        candidates, _ = _logs(store, node, workspace_root, parsed=parsed) if node else ([], [])
        node_candidates = candidates
        if endpoint_refs and key in endpoint_refs:
            from cloudra.dag.models import GraphRef
            ref = GraphRef.model_validate(endpoint_refs[key])
            if ref not in element.refs:
                return []
            candidates, errors = _logs(store, element.model_copy(update={'refs': [ref], 'stages': []}), workspace_root, parsed=parsed)
            problems.extend(errors)
            # An explicit minimum fixes the final geometry, while a
            # separate bound Opt log supplies its native IRC starting frame.
            from cloudra.tools.core.irc_path import same_geometry
            minima = [_final_geometry(path) for path in candidates if _qm_data(path, parsed)[3] == []]
            candidates = list(dict.fromkeys([*candidates, *[path for path in node_candidates
                if any(same_geometry(_final_geometry(path), minimum) for minimum in minima)]]))
        verified = []
        for path in candidates:
            try:
                data = _qm_data(path, parsed)
                if (node and node.smiles
                        and (data[3] == [] or _optimization_converged(path, data[1]) is True)
                        and any(_geometry_species(path, identity, diagnostics=problems)
                                for identity in species_smiles(node.smiles))):
                    verified.append(path)
            except (ValueError, RuntimeError) as exc:
                problems.append(str(exc))
        return verified

    source = next((n for n in graph.nodes if n.node_id == element.source_node_id), None)
    target = next((n for n in graph.nodes if n.node_id == element.target_node_id), None)
    return {'source': endpoint_candidates('endpoint_b', source),
            'target': endpoint_candidates('endpoint_a', target)}


def _file_scientific_checks(store, graph, target_id: str, *, irc_files=None, workspace_root=None, evidence_refs=None, endpoint_refs=None) -> dict[str, dict]:
    element = next((n for n in graph.nodes if n.node_id == target_id), None)
    is_edge = element is None
    if is_edge:
        element = next((e for e in graph.edges if e.edge_id == target_id), None)
    if element is None:
        raise InvalidGraphReference(f"Delivery target {target_id!r} no longer exists in the current graph.")
    if evidence_refs is not None:
        element = element.model_copy(update={'refs': list(evidence_refs), 'stages': []})
    atom_bindings = {}
    parsed = {}
    logs, problems = _logs(store, element, workspace_root, atom_bindings=atom_bindings, parsed=parsed)
    if is_edge and endpoint_refs:
        from cloudra.dag.models import GraphRef
        refs = [GraphRef.model_validate(ref) for ref in endpoint_refs.values()]
        endpoint_logs, endpoint_problems = _logs(store, element.model_copy(update={'refs': refs, 'stages': []}), workspace_root, parsed=parsed)
        logs = [path for path in logs if path not in endpoint_logs]
        problems.extend(endpoint_problems)
    if not is_edge:
        return {'geometry': _species_minimum_check(element.smiles, logs, problems, parsed=parsed).model_dump()}
    frequencies = [_qm_data(p, parsed)[3] for p in logs]
    expected = 1 if is_edge else 0
    passed = any(f is not None and len(f) == expected for f in frequencies)
    status = 'passed' if passed else 'failed' if any(f is not None for f in frequencies) else 'incomplete'
    frequency_check = ScientificCheck(status=status,
        detail=f'Native normal termination and exactly {expected} imaginary frequencies required. ' + ' '.join(problems),
        next_action='' if passed else f'Submit a normally terminated frequency log showing {expected} imaginary frequencies; repair the calculation or supply missing evidence.')
    checks = {'frequency' if is_edge else 'geometry': frequency_check}
    if is_edge:
        checks['ts_opt'] = _ts_optimization_check(logs, parsed=parsed)
        source = next((n for n in graph.nodes if n.node_id == element.source_node_id), None)
        target = next((n for n in graph.nodes if n.node_id == element.target_node_id), None)
        endpoints = _step_endpoint_logs(store, graph, element, workspace_root,
            endpoint_refs=endpoint_refs, parsed=parsed, problems=problems)
        source_logs, target_logs = endpoints['source'], endpoints['target']
        charge = next((binding['charge'] for binding in atom_bindings.values() if 'charge' in binding), 0)
        if source_logs and source and source.smiles:
            from rdkit import Chem
            molecule = Chem.MolFromSmiles(chemical_smiles(source.smiles))
            if molecule is not None:
                charge = Chem.GetFormalCharge(molecule)
        details = list(problems)
        recovery = []
        irc_passed = False
        for path in logs:
            try:
                engine = _qm_data(path, parsed)[1]
                if engine == 'orca':
                    orca_frames.extract_irc(path)
                elif engine == 'gaussian':
                    gaussian_frames.extract_irc(path)
                else:
                    continue
            except ValueError:
                continue
            try:
                irc_passed, reason = verify_short_irc_direction(path, logs, target_logs, source_logs,
                    charge=charge, atom_bindings=atom_bindings, product_smiles=target.smiles if target else None,
                    reactant_smiles=source.smiles if source else None)
                details.extend(reason)
                if not irc_passed:
                    hint = irc_endpoint_recovery_hint(path)
                    if hint:
                        recovery.append(hint)
            except Exception as exc:
                details.append(f'IRC direction proof could not be evaluated: {exc}')
            if irc_passed:
                details = reason
                break
        if not irc_passed and irc_files and irc_files.get('irc_forward_file') and irc_files.get('irc_reverse_file'):
            forward = FileEvidenceSnapshot.model_validate(irc_files['irc_forward_file']).snapshot_path
            reverse = FileEvidenceSnapshot.model_validate(irc_files['irc_reverse_file']).snapshot_path
            if forward in logs and reverse in logs:
                irc_passed, reason = verify_short_irc_pair(forward, reverse, logs, target_logs, source_logs,
                    charge=charge, atom_bindings=atom_bindings, product_smiles=target.smiles if target else None,
                    reactant_smiles=source.smiles if source else None)
                details = reason if irc_passed else [*details, *reason]
        checks['short_irc'] = ScientificCheck(status='passed' if irc_passed else 'incomplete',
            detail=' '.join(details) or ('Native IRC outer-frame optimization to the declared verified minima passed.' if irc_passed else 'No usable bound bidirectional IRC evidence.'),
            next_action='' if irc_passed else 'Submit same-TS bidirectional IRC and native Opt/Freq logs connecting each outer frame to its declared minimum; geometric interval checks are advisory. Separated products need each declared species minimum. Full IRC convergence is not required.'
                + (' ' + ' '.join(dict.fromkeys(recovery)) if recovery else ''))
    return {stage: check.model_dump() for stage, check in checks.items()}
