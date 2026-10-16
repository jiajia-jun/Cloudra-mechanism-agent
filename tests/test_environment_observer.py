"""Workspace observations bound enumeration and reuse unchanged metadata."""

import pytest

from cloudra.runtime import environment_observer as module


@pytest.fixture(autouse=True)
def clear_observations():
    module._SNAPSHOT_CACHE.clear()
    if hasattr(module, "_WORKSPACE_CACHE"):
        module._WORKSPACE_CACHE.clear()


def _count_scandir(monkeypatch):
    original = module.os.scandir
    counts = {"calls": 0, "entries": 0}

    class Scan:
        def __init__(self, path):
            counts["calls"] += 1
            self.iterator = original(path)

        def __iter__(self):
            return self

        def __next__(self):
            entry = next(self.iterator)
            counts["entries"] += 1
            return entry

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.iterator.close()

    scan = Scan

    monkeypatch.setattr(module.os, "scandir", scan)
    return counts


def test_single_directory_enumeration_stops_before_sorting_all_children(tmp_path, monkeypatch):
    for index in range(100):
        (tmp_path / f"file-{index:03}.txt").write_text("x")
    counts = _count_scandir(monkeypatch)
    entries, _, truncated = module._snapshot(tmp_path, max_entries=2)
    assert len(entries) == 2
    assert truncated
    assert counts["entries"] <= 3


def test_unchanged_workspace_is_shared_between_agent_observers(tmp_path, monkeypatch):
    (tmp_path / "note.txt").write_text("hello")
    counts = _count_scandir(monkeypatch)
    first = module.observe_workspace(tmp_path, observer_id="a")
    second = module.observe_workspace(tmp_path, observer_id="b")
    again = module.observe_workspace(tmp_path, observer_id="a")
    assert first.revision == second.revision == again.revision
    assert again.changes == ()
    assert counts["calls"] == 1


def test_shared_snapshot_detects_content_nested_additions_and_deletions(tmp_path):
    nested = tmp_path / "results"
    nested.mkdir()
    path = nested / "note.txt"
    path.write_text("old")
    first = module.observe_workspace(tmp_path, observer_id="a")
    module.observe_workspace(tmp_path, observer_id="b")
    path.write_text("new content")
    changed = module.observe_workspace(tmp_path, observer_id="a")
    assert changed.revision != first.revision
    assert {"path": "results/note.txt", "change": "modified"} in changed.changes
    (nested / "added.txt").write_text("new")
    path.unlink()
    other = module.observe_workspace(tmp_path, observer_id="b")
    assert {"path": "results/note.txt", "change": "deleted"} in other.changes
    assert {"path": "results/added.txt", "change": "added"} in other.changes


def test_ignored_directories_and_symlinks_are_not_followed(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "skip.txt").write_text("skip")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "original.txt").write_text("keep")
    (tmp_path / "alias").symlink_to(outside, target_is_directory=True)
    entries, _, _ = module._snapshot(tmp_path)
    assert "node_modules" not in entries
    assert "alias" in entries and "alias/original.txt" not in entries
    assert "outside/original.txt" in entries


def test_workspace_and_observer_caches_remain_bounded(tmp_path):
    for index in range(150):
        workspace = tmp_path / str(index)
        workspace.mkdir()
        module.observe_workspace(workspace, observer_id=str(index))
    assert len(module._WORKSPACE_CACHE) <= 32
    assert len(module._SNAPSHOT_CACHE) <= 128


def test_same_size_rewrite_with_restored_mtime_expires_shared_snapshot(tmp_path):
    import os

    path = tmp_path / "note.txt"
    path.write_text("old")
    original = path.stat()
    first = module.observe_workspace(tmp_path, observer_id="a")
    path.write_text("new")
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    current = module.observe_workspace(tmp_path, observer_id="a")
    assert current.revision != first.revision
    assert {"path": "note.txt", "change": "modified"} in current.changes
