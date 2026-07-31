"""Bounded, non-identity snapshots of a server workspace.

The model needs to notice that its environment changed, but ordinary files are
not part of the Agent's identity or policy.  This module therefore produces a
separate observation revision and a small change summary.  The snapshot is
metadata-only and bounded so request-time prompt assembly cannot accidentally
walk an unbounded checkout.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

_IGNORED_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)
_SNAPSHOT_CACHE: dict[tuple[str, str], dict[str, str]] = {}


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@dataclass(frozen=True)
class WorkspaceObservation:
    revision: str
    top_level_entries: tuple[str, ...]
    changes: tuple[dict[str, str], ...]
    entry_count: int
    truncated: bool


def _snapshot(
    root: Path,
    *,
    max_entries: int = 2_000,
    max_depth: int = 5,
) -> tuple[dict[str, str], tuple[str, ...], bool]:
    entries: dict[str, str] = {}
    top_level: list[str] = []
    truncated = False
    stack: list[tuple[Path, int]] = [(root, 0)]

    while stack and len(entries) < max_entries:
        directory, depth = stack.pop()
        try:
            children = sorted(
                os.scandir(directory),
                key=lambda item: item.name,
                reverse=True,
            )
        except OSError:
            continue
        for child in children:
            if len(entries) >= max_entries:
                truncated = True
                break
            if child.name in _IGNORED_NAMES:
                continue
            try:
                relative = Path(child.path).relative_to(root).as_posix()
                stat = child.stat(follow_symlinks=False)
                if child.is_symlink():
                    kind = "symlink"
                elif child.is_dir(follow_symlinks=False):
                    kind = "directory"
                elif child.is_file(follow_symlinks=False):
                    kind = "file"
                else:
                    kind = "other"
                entries[relative] = (
                    f"{kind}:{stat.st_size}:{stat.st_mtime_ns}"
                )
                if depth == 0:
                    top_level.append(
                        f"{child.name}/" if kind == "directory" else child.name
                    )
                if kind == "directory" and depth < max_depth:
                    stack.append((Path(child.path), depth + 1))
            except (OSError, ValueError):
                continue
    if stack:
        truncated = True
    return entries, tuple(sorted(top_level)), truncated


def observe_workspace(
    root: Path,
    *,
    observer_id: str,
) -> WorkspaceObservation:
    """Return the current workspace revision and changes since this observer ran."""

    resolved = root.expanduser().resolve()
    entries, top_level, truncated = _snapshot(resolved)
    cache_key = (str(resolved), observer_id)
    previous = _SNAPSHOT_CACHE.get(cache_key)
    changes: list[dict[str, str]] = []
    if previous is not None:
        for path in sorted(set(previous) | set(entries)):
            if path not in previous:
                change = "added"
            elif path not in entries:
                change = "deleted"
            elif previous[path] != entries[path]:
                change = "modified"
            else:
                continue
            changes.append({"path": path, "change": change})
            if len(changes) >= 100:
                break
    _SNAPSHOT_CACHE[cache_key] = entries
    return WorkspaceObservation(
        revision=_digest(entries),
        top_level_entries=top_level,
        changes=tuple(changes),
        entry_count=len(entries),
        truncated=truncated,
    )
