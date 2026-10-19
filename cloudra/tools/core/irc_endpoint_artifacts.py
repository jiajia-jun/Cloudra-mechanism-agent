"""Native IRC outer frames ready for a subsequent, independent Opt/Freq job.

A/B retain ``irc_endpoint_geometries`` order and never name chemical roles.
The source-log digest in each filename and exact native-derived content checks
keep a neighboring job, stale export or edited XYZ from becoming a handoff.
"""

from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core import gaussian_frames, irc_evidence, orca_frames, qm_engine

logger = logging.getLogger(__name__)


def _canonical_artifacts(log_path: str | Path) -> dict[str, tuple[Path, str]]:
    path = Path(log_path)
    try:
        native = path.read_bytes()
        text = native.decode('utf-8', errors='replace')
        engine = qm_engine.detect_qm_engine_from_text(text)
        parser = {'gaussian': gaussian_frames, 'orca': orca_frames}.get(engine)
        if parser is None or not parser.normal_termination(text):
            return {}
        # Only an execution/DAG archive may establish ORCA sidecar ownership.
        # Never invoke the native reader's unique-neighbor convenience fallback.
        if engine == 'orca' and orca_frames._archived_irc_endpoints(str(path)) is None:
            return {}
        ends = irc_evidence.irc_endpoint_geometries(path)
        if ends is None or path.read_bytes() != native:
            return {}
        digest = hashlib.sha256(native).hexdigest()
        result = {}
        for side, (symbols, positions) in zip(('a', 'b'), ends, strict=True):
            if not symbols or len(symbols) != len(positions):
                return {}
            rows = [str(len(symbols)), 'Native IRC outer frame; independent Opt/Freq required.']
            for symbol, point in zip(symbols, positions, strict=True):
                if len(point) != 3 or not all(math.isfinite(float(value)) for value in point):
                    return {}
                rows.append(f'{symbol} {point[0]:.12f} {point[1]:.12f} {point[2]:.12f}')
            target = path.parent / f'irc-{digest}.end-{side}.xyz'
            result[f'irc_end_{side}_path'] = (target, '\n'.join(rows) + '\n')
        return result
    except (OSError, ValueError, TypeError, IndexError, KeyError):
        return {}


def write_irc_endpoint_artifacts(log_path: str | Path) -> dict[str, str]:
    """Atomically export both native outer frames alongside this frozen log.

    Non-IRC, abnormal, one-sided or unbound ORCA evidence yields no handoff.
    Existing native logs, sidecars and submitted inputs are never rewritten.
    """
    artifacts = _canonical_artifacts(log_path)
    try:
        for path, content in artifacts.values():
            if not path.is_symlink() and path.is_file() and path.read_bytes() == content.encode('utf-8'):
                continue
            atomic_write_text(str(path), content)
    except OSError as exc:
        # These are derived handoff files, not the native calculation verdict.
        logger.warning('Could not export native IRC endpoints for %s: %s', log_path, exc)
        return {}
    return {key: str(path) for key, (path, _content) in artifacts.items()}


def read_irc_endpoint_artifacts(log_path: str | Path) -> dict[str, str]:
    """Read only a complete, untampered native-derived pair; never create files."""
    artifacts = _canonical_artifacts(log_path)
    try:
        if any(path.is_symlink() or not path.is_file() or path.read_bytes() != content.encode('utf-8')
               for path, content in artifacts.values()):
            return {}
    except OSError:
        return {}
    return {key: str(path) for key, (path, _content) in artifacts.items()}
