"""Independent exact edits merge without losing concurrent text or approval."""

import concurrent.futures
import threading
from types import SimpleNamespace

import pytest

from cloudra.base.tools_class import Tool
from cloudra.persistence.workspace import TextEdit, WorkspaceConflictError, WorkspaceService
from cloudra.tools.Writetool.edit import Edit, Edit_input_schema


def test_stale_read_rebases_only_the_unchanged_target_section(tmp_path):
    path = tmp_path / 'PROCESS.md'
    path.write_text('alpha: pending\nbeta: pending\n')
    service = WorkspaceService(tmp_path)
    before = service.snapshot(path.name)
    path.write_text('alpha: done\nbeta: pending\n')

    change = service.prepare_edit(path.name, before.sha256, [TextEdit('beta: pending', 'beta: done')])
    service.apply(change)

    assert path.read_text() == 'alpha: done\nbeta: done\n'
    assert change.before_content == 'alpha: done\nbeta: pending\n'
    assert '-alpha: pending' not in change.diff


def test_concurrent_target_change_remains_a_conflict(tmp_path):
    path = tmp_path / 'PROCESS.md'
    path.write_text('alpha: pending\nbeta: pending\n')
    service = WorkspaceService(tmp_path)
    before = service.snapshot(path.name)
    path.write_text('alpha: user decision\nbeta: pending\n')

    with pytest.raises(WorkspaceConflictError):
        service.prepare_edit(path.name, before.sha256, [TextEdit('alpha: pending', 'alpha: done')])

    assert path.read_text() == 'alpha: user decision\nbeta: pending\n'


def test_repeated_lines_cannot_hide_an_overlapping_target_edit(tmp_path):
    path = tmp_path / 'PROCESS.md'
    path.write_text('a\na\nb\n')
    service = WorkspaceService(tmp_path)
    before = service.snapshot(path.name)
    path.write_text('a\nz\nb\n')

    with pytest.raises(WorkspaceConflictError):
        change = service.prepare_edit(path.name, before.sha256, [TextEdit('a\na\n', 'a\nb\n')])
        service.apply(change)
    assert path.read_text() == 'a\nz\nb\n'


def test_stale_replace_all_cannot_expand_to_new_concurrent_matches(tmp_path):
    path = tmp_path / 'PROCESS.md'
    path.write_text('alpha: pending\nbeta: finished\n')
    service = WorkspaceService(tmp_path)
    before = service.snapshot(path.name)
    path.write_text('alpha: pending\nbeta: finished\nnew: pending\n')

    with pytest.raises(WorkspaceConflictError):
        service.prepare_edit(path.name, before.sha256, [TextEdit('pending', 'done', replace_all=True)])

    assert path.read_text().endswith('new: pending\n')


def test_unavailable_read_version_never_guesses_a_merge(tmp_path, monkeypatch):
    import cloudra.persistence.workspace as workspace

    monkeypatch.setattr(workspace, '_SNAPSHOT_CACHE_BYTES', 8)
    path = tmp_path / 'PROCESS.md'
    path.write_text('alpha: pending\nbeta: pending\n')
    service = WorkspaceService(tmp_path)
    before = service.snapshot(path.name)
    path.write_text('alpha: done\nbeta: pending\n')

    with pytest.raises(WorkspaceConflictError, match='re-read'):
        service.prepare_edit(path.name, before.sha256, [TextEdit('beta: pending', 'beta: done')])
    assert path.read_text() == 'alpha: done\nbeta: pending\n'


def test_check_and_replace_are_serialized_between_independent_services(tmp_path, monkeypatch):
    import cloudra.persistence.workspace as workspace

    path = tmp_path / 'PROCESS.md'
    path.write_text('pending\n')
    first, second = WorkspaceService(tmp_path), WorkspaceService(tmp_path)
    before = first.snapshot(path.name)
    a = first.prepare_write(path.name, 'first\n', before.sha256)
    b = second.prepare_write(path.name, 'second\n', before.sha256)
    entered, release, second_done = threading.Event(), threading.Event(), threading.Event()
    replace = workspace.os.replace

    def hold_first(source, target):
        if not entered.is_set():
            entered.set()
            assert release.wait(2)
        replace(source, target)

    def apply_second():
        try:
            second.apply(b)
        finally:
            second_done.set()

    monkeypatch.setattr(workspace.os, 'replace', hold_first)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(first.apply, a)
        assert entered.wait(2)
        second_result = pool.submit(apply_second)
        try:
            assert not second_done.wait(0.05), 'a concurrent replacement bypassed the version check'
        finally:
            release.set()
        first_result.result(timeout=2)
        with pytest.raises(WorkspaceConflictError):
            second_result.result(timeout=2)
    assert path.read_text() == 'first\n'


def test_nested_workspace_roots_use_the_same_file_lock(tmp_path, monkeypatch):
    nested = tmp_path / 'nested'
    nested.mkdir()
    # Reuse the same competing-replace regression through two valid roots.
    import cloudra.persistence.workspace as workspace

    path = nested / 'PROCESS.md'
    path.write_text('pending\n')
    first, second = WorkspaceService(tmp_path), WorkspaceService(nested)
    before = first.snapshot('nested/PROCESS.md')
    a = first.prepare_write('nested/PROCESS.md', 'first\n', before.sha256)
    b = second.prepare_write('PROCESS.md', 'second\n', before.sha256)
    entered, release, second_done = threading.Event(), threading.Event(), threading.Event()
    replace = workspace.os.replace

    def hold_first(source, target):
        if not entered.is_set():
            entered.set()
            assert release.wait(2)
        replace(source, target)

    def apply_second():
        try:
            second.apply(b)
        finally:
            second_done.set()

    monkeypatch.setattr(workspace.os, 'replace', hold_first)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(first.apply, a)
        assert entered.wait(2)
        second_result = pool.submit(apply_second)
        try:
            assert not second_done.wait(0.05), 'nested roots acquired different locks for the same file'
        finally:
            release.set()
        first_result.result(timeout=2)
        with pytest.raises(WorkspaceConflictError):
            second_result.result(timeout=2)
    assert path.read_text() == 'first\n'


@pytest.mark.asyncio
@pytest.mark.parametrize('allow_rebased', [True, False])
async def test_approval_race_rechecks_the_rebased_candidate(tmp_path, monkeypatch, mock_session, allow_rebased):
    path = tmp_path / 'PROCESS.md'
    path.write_text('alpha: pending\nbeta: pending\n')
    before = WorkspaceService(tmp_path).snapshot(path.name)
    proposals, events = [], []

    async def approve(self, session, details, tool_args=None):
        proposals.append(details)
        if len(proposals) == 1:
            path.write_text('alpha: done\nbeta: pending\n')
            return True, ''
        return allow_rebased, ''

    async def record(self, session, event_type, data):
        events.append((event_type, data))

    monkeypatch.setattr(Tool, 'ensure_safety', approve)
    monkeypatch.setattr(Tool, 'record_session_event', record)
    actor = SimpleNamespace(working_directory=str(tmp_path), conversation_id='concurrent-edit',
                            name='worker', known_file_sha256=lambda _: before.sha256)
    result = await Edit(subagent=actor).tool_call(
        Edit_input_schema(path=path.name, edits=[{'old_string': 'beta: pending', 'new_string': 'beta: done'}]),
        mock_session,
    )

    assert len(proposals) == 2
    assert 'alpha: done' in proposals[-1]
    assert result.is_written is allow_rebased
    assert result.status == ('applied' if allow_rebased else 'declined')
    assert path.read_text() == 'alpha: done\nbeta: ' + ('done\n' if allow_rebased else 'pending\n')
    applied = [data for name, data in events if name == 'file_change_applied']
    if allow_rebased:
        assert len(applied) == 1
        assert applied[0]['before_sha256'] != before.sha256
    else:
        assert not applied


@pytest.mark.asyncio
async def test_approval_race_does_not_rebase_an_overlapping_edit(tmp_path, monkeypatch, mock_session):
    path = tmp_path / 'PROCESS.md'
    path.write_text('alpha: pending\nbeta: pending\n')
    before = WorkspaceService(tmp_path).snapshot(path.name)
    proposals = []

    async def approve(self, session, details, tool_args=None):
        proposals.append(details)
        path.write_text('alpha: pending\nbeta: user decision\n')
        return True, ''

    async def record(*args):
        pass

    monkeypatch.setattr(Tool, 'ensure_safety', approve)
    monkeypatch.setattr(Tool, 'record_session_event', record)
    actor = SimpleNamespace(working_directory=str(tmp_path), conversation_id='overlapping-edit',
                            name='worker', known_file_sha256=lambda _: before.sha256)
    result = await Edit(subagent=actor).tool_call(
        Edit_input_schema(path=path.name, edits=[{'old_string': 'beta: pending', 'new_string': 'beta: done'}]),
        mock_session,
    )

    assert len(proposals) == 1
    assert result.status == 'conflict'
    assert path.read_text() == 'alpha: pending\nbeta: user decision\n'


@pytest.mark.asyncio
async def test_approval_race_preserves_replace_all_match_scope(tmp_path, monkeypatch, mock_session):
    path = tmp_path / 'PROCESS.md'
    path.write_text('alpha: pending\nbeta: complete\n')
    before = WorkspaceService(tmp_path).snapshot(path.name)

    async def approve(self, session, details, tool_args=None):
        path.write_text('alpha: pending\nbeta: complete\nnew: pending\n')
        return True, ''

    async def record(*args):
        pass

    monkeypatch.setattr(Tool, 'ensure_safety', approve)
    monkeypatch.setattr(Tool, 'record_session_event', record)
    actor = SimpleNamespace(working_directory=str(tmp_path), conversation_id='replace-all-race',
                            name='worker', known_file_sha256=lambda _: before.sha256)
    result = await Edit(subagent=actor).tool_call(
        Edit_input_schema(path=path.name, edits=[{'old_string': 'pending', 'new_string': 'done', 'replace_all': True}]),
        mock_session,
    )

    assert result.status == 'conflict'
    assert path.read_text() == 'alpha: pending\nbeta: complete\nnew: pending\n'
