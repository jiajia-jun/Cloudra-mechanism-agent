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
import threading
from collections import OrderedDict
from dataclasses import dataclass
from itertools import islice
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
_CACHE_LOCK = threading.RLock()
_SNAPSHOT_CACHE: OrderedDict[tuple[str, str], dict[str, str]] = OrderedDict()
_WORKSPACE_CACHE: OrderedDict[tuple[str, int, int], tuple] = OrderedDict()


def _signature(path: Path):
    try:
        stat = path.lstat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def is_application_checkout(root: Path) -> bool:
    """Recognize Cloudra source checkouts, including separate git worktrees.

    A research workspace may be explicitly located here, but its developer
    instructions and unrelated file inventory must not be injected as task context.
    """
    root = root.resolve()
    return (root / "pyproject.toml").is_file() and (
        root / "cloudra" / "runtime" / "prompt_assembler.py"
    ).is_file()


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
    with _CACHE_LOCK:
        cache_key = (str(root), max_entries, max_depth)
        cached = _WORKSPACE_CACHE.get(cache_key)
        if cached is not None:
            entries, top_level, truncated, signatures = cached
            if all(_signature(root / path) == version for path, version in signatures.items()):
                _WORKSPACE_CACHE.move_to_end(cache_key)
                return entries, top_level, truncated
        entries: dict[str, str] = {}
        signatures = {"": _signature(root)}
        top_level: list[str] = []
        truncated = False
        stack: list[tuple[Path, int]] = [(root, 0)]
        enumerated = 0

        while stack and enumerated < max_entries:
            directory, depth = stack.pop()
            remaining = max_entries - enumerated
            try:
                with os.scandir(directory) as iterator:
                    children = list(islice(iterator, remaining + 1))
            except OSError:
                continue
            if len(children) > remaining:
                truncated = True
                children = children[:remaining]
            enumerated += len(children)
            children.sort(key=lambda item: item.name, reverse=True)
            for child in children:
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
                    signatures[relative] = (
                        stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size,
                        stat.st_mtime_ns, stat.st_ctime_ns,
                    )
                    entries[relative] = f"{kind}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}:{stat.st_ino}"
                    if depth == 0:
                        top_level.append(f"{child.name}/" if kind == "directory" else child.name)
                    if kind == "directory" and depth < max_depth:
                        stack.append((Path(child.path), depth + 1))
                except (OSError, ValueError):
                    continue
        truncated = truncated or bool(stack)
        result = entries, tuple(sorted(top_level)), truncated
        _WORKSPACE_CACHE[cache_key] = (*result, signatures)
        _WORKSPACE_CACHE.move_to_end(cache_key)
        while len(_WORKSPACE_CACHE) > 32:
            _WORKSPACE_CACHE.popitem(last=False)
        return result


def observe_workspace(
    root: Path,
    *,
    observer_id: str,
) -> WorkspaceObservation:
    """Return the current workspace revision and changes since this observer ran."""

    resolved = root.expanduser().resolve()
    entries, top_level, truncated = _snapshot(resolved)
    cache_key = (str(resolved), observer_id)
    with _CACHE_LOCK:
        previous = _SNAPSHOT_CACHE.get(cache_key)
        _SNAPSHOT_CACHE[cache_key] = entries
        _SNAPSHOT_CACHE.move_to_end(cache_key)
        while len(_SNAPSHOT_CACHE) > 128:
            _SNAPSHOT_CACHE.popitem(last=False)
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
    return WorkspaceObservation(
        revision=_digest(entries),
        top_level_entries=top_level,
        changes=tuple(changes),
        entry_count=len(entries),
        truncated=truncated,
    )
