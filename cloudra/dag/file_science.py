"""Scientific checks for submitted files, shared by review and delivery audit."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cloudra.dag.evidence_ingest import FileEvidenceSnapshot, _extract_qm_log
from cloudra.dag.store import InvalidGraphReference
from cloudra.tools.core import gaussian_frames, orca_frames, xtb_frames
from cloudra.tools.core.irc_evidence import verify_short_irc_direction, verify_short_irc_pair


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


def file_scientific_checks(store, graph, target_id: str, *, irc_files=None, workspace_root=None) -> dict[str, dict]:
    element = next((n for n in graph.nodes if n.node_id == target_id), None)
    is_edge = element is None
    if is_edge:
        element = next(e for e in graph.edges if e.edge_id == target_id)
    logs, problems = _logs(store, element, workspace_root)
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
