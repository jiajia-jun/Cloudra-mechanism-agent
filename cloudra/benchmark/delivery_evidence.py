"""Program-authored endpoint bindings for portable, offline delivery scoring.

This file supplies candidate native logs, never a scientific verdict. The
shared IRC validator still checks their actual IRC → Opt → Freq lineage.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from cloudra.persistence.fs_utils import atomic_write_json
from cloudra.persistence.paths import mechanism_evidence_path


def _digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("Expected a lowercase SHA256 digest.")
    return value


_Digest = Annotated[str, AfterValidator(_digest)]


class _EndpointLog(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1)
    sha256: _Digest


class _StepEndpoints(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: list[_EndpointLog]
    target: list[_EndpointLog]


class _EndpointEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    graph_sha256: _Digest
    steps: dict[str, _StepEndpoints]


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Path escapes the delivery workspace: {path}")
    return resolved


def _endpoint_paths(root: Path, document: _EndpointEvidence) -> dict[str, dict[str, list[str]]]:
    steps = {}
    digests = {}
    for edge_id, endpoints in document.steps.items():
        steps[edge_id] = {}
        for side in ("source", "target"):
            paths = []
            for record in getattr(endpoints, side):
                relative = Path(record.path)
                if relative.is_absolute():
                    raise ValueError(f"Endpoint log path must be workspace-relative: {record.path}")
                path = _inside(root, root / relative)
                if path not in digests:
                    if not path.is_file():
                        raise ValueError(f"Endpoint log is missing: {record.path}")
                    digests[path] = hashlib.sha256(path.read_bytes()).hexdigest()
                if digests[path] != record.sha256:
                    raise ValueError(f"SHA256 mismatch for endpoint log: {record.path}")
                paths.append(str(path.relative_to(root)))
            steps[edge_id][side] = list(dict.fromkeys(paths))
    return steps


def write_step_endpoint_evidence(workspace_root, graph_sha256: str, steps: dict) -> None:
    """Publish validated existing snapshots after the authored graph is approved."""
    try:
        root = Path(workspace_root).resolve()
        path = _inside(root, mechanism_evidence_path(root))
        document = _EndpointEvidence.model_validate({"graph_sha256": graph_sha256, "steps": steps})
        _endpoint_paths(root, document)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(str(path), document.model_dump())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Step endpoint evidence is unusable: {exc}") from exc


def read_step_endpoint_evidence(workspace_root, graph_sha256: str) -> dict[str, dict[str, list[str]]]:
    """Return per-step native candidates; reject stale or changed bindings loudly."""
    root = Path(workspace_root).resolve()
    path = mechanism_evidence_path(root)
    if not path.exists() and not path.is_symlink():
        return {}
    try:
        path = _inside(root, path)
        document = _EndpointEvidence.model_validate_json(path.read_text(encoding="utf-8"))
        if document.graph_sha256 != graph_sha256:
            raise ValueError("The endpoint evidence does not match the current mechanism graph SHA256.")
        return _endpoint_paths(root, document)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Step endpoint evidence is unusable: {exc}") from exc
