"""History reads reuse cached prefixes and the existing ordered event indexes."""

import contextlib

import pytest

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import RuntimeSettings


@pytest.fixture
def history(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path / "runtime.db")
    log = EventLog(strict=True)
    log.attach_store(store)
    log._max_cached_events = 4
    events = []
    for index in range(150):
        event = log.append("agent.warning", stream="agent", project_id=f"p{index % 2}",
                           session_id=f"a{index % 2}", data={"index": index})
        store.append_event(event)
        log.mark_persisted(index + 1, event)
        events.append(event)
    statements = []
    connect = store._connect

    @contextlib.contextmanager
    def traced_connect():
        with connect() as con:
            con.set_trace_callback(statements.append)
            yield con

    monkeypatch.setattr(store, "_connect", traced_connect)
    return log, store, events, statements


@pytest.mark.parametrize("scope,column", [("project", "seq"), ("session", "session_seq")])
def test_scoped_history_pages_use_existing_sequence_index(history, scope, column):
    _, store, events, statements = history
    filters = {"project_id": "p0"} if scope == "project" else {"session_id": "a0"}
    actual = list(store.iter_events(**filters))
    assert [event.event_id for event in actual] == [event.event_id for event in events[::2]]
    selects = [sql for sql in statements if sql.startswith("SELECT event_id")]
    assert f"ORDER BY {column} ASC LIMIT 500" in selects[0]
    assert "COALESCE(session_seq" not in selects[0]
    assert len(selects) == 2  # one page plus the empty end probe


def test_global_cached_prefix_uses_project_watermarks_without_offset(history):
    log, _, events, statements = history
    assert [event.event_id for event in log.iter_events()] == [event.event_id for event in events]
    assert not any("OFFSET" in sql for sql in statements)


def test_store_event_metadata_only_reads_new_narrow_columns(history):
    log, store, _, statements = history
    store.save_snapshot(projects={}, agents={}, roles={}, runtime_defaults=RuntimeSettings(),
                        last_seqs=log.high_watermarks)
    # The snapshot payload was frozen before this append became durable.
    extra = log.append("agent.warning", stream="agent", project_id="new", session_id="new-agent")
    store.append_event(extra)
    statements.clear()
    count, projects, sessions = store.event_metadata()
    assert count == 151
    assert projects == {"p0": 75, "p1": 75, "new": 1}
    assert sessions == {"a0": 75, "a1": 75, "new-agent": 1}
    assert not any("COUNT(" in sql or "GROUP BY" in sql for sql in statements)
    event_selects = [sql for sql in statements if "FROM events" in sql]
    assert len(event_selects) == 1
    assert event_selects[0].startswith("SELECT rowid, project_id, session_id, seq, session_seq")
    assert "rowid > 150" in event_selects[0]


def test_store_metadata_keeps_late_events_outside_the_state_snapshot(history):
    log, store, _, _ = history
    marks = log.high_watermarks
    late = log.append("agent.warning", stream="agent", project_id="p0", session_id="a0")
    store.append_event(late)
    store.save_snapshot(projects={}, agents={}, roles={}, runtime_defaults=RuntimeSettings(),
                        last_seqs=marks)
    assert store.event_metadata() == (151, {"p0": 76, "p1": 75}, {"a0": 76, "a1": 75})


def test_notice_snapshot_keeps_only_current_pins_and_unconsumed_changes():
    log = EventLog(strict=True)
    notices = NoticeManager()
    notices.attach(log, lambda _: "p")
    notices.pin("a", "goal", "first")
    notices.push("a", "consumed")
    notices.collect_batch("a", fresh=False)
    notices.confirm_consumed("a")
    notices.push("a", "pending")
    snapshot = notices.snapshot()
    assert "consumed" not in str(snapshot)
    restored = NoticeManager()
    restored.restore(snapshot)
    assert restored.pin_content("a", "goal") == "first"
    assert [message["content"] for message in restored.collect_batch("a", fresh=False)] == ["pending"]
    # Applying a late event extends the saved state without rereading the log.
    event = log.append("context.pin_set", stream="agent", project_id="p", session_id="a",
                       data={"key": "goal", "content": "second"})
    restored.apply(event)
    restored.apply(event)
    restored.collect_batch("a", fresh=True)
    assert [message["content"] for message in restored.pending_batch("a")[0]] == ["second", "pending"]
    assert len(restored.snapshot()["changes"]["a"]) == 2
    assert notices.pin_content("a", "goal") == "first"  # detached snapshot


def test_live_notice_apply_is_idempotent_and_consumption_is_shared():
    log = EventLog(strict=True)
    notices = NoticeManager()
    notices.attach(log, lambda _: "p")
    notices.pin("a", "goal", "current")
    notices.push("a", "pending")
    for event in log:
        notices.apply(event)
    assert len(notices.snapshot()["changes"]["a"]) == 2
    consumed = log.append("context.appended", stream="agent", project_id="p", session_id="a",
                          data={"notices_through": 2, "messages": []})
    notices.apply(consumed)
    assert notices.collect_batch("a", fresh=False) == []
    assert notices.pin_content("a", "goal") == "current"


@pytest.mark.parametrize("scope", ["project", "session"])
@pytest.mark.parametrize("tail", [False, True])
def test_sequence_pages_keep_fixed_prefix_when_new_events_arrive(history, scope, tail):
    log, store, events, _ = history
    filters = {"project_id": "p0"} if scope == "project" else {"session_id": "a0"}
    # Make the byte cap split the scoped results across pages.
    with store._connect() as con:
        con.execute("UPDATE events SET data = ?", ('{"padding":"' + "x" * 20000 + '"}',))
    iterator = store.iter_events(**filters, tail=tail)
    first = next(iterator)
    late = log.append("agent.warning", stream="agent", project_id="p0", session_id="a0")
    store.append_event(late)
    actual = [first, *iterator]
    expected = events[::2][::-1] if tail else events[::2]
    assert [event.event_id for event in actual] == [event.event_id for event in expected]
    assert late.event_id not in {event.event_id for event in actual}


def test_metadata_anchor_preserves_counts_when_sqlite_rowids_have_gaps(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    log = EventLog(strict=True)
    log.attach_store(store)
    first = log.append("agent.warning", stream="agent", project_id="p", session_id="a")
    store.append_event(first)
    log.mark_persisted(1, first)
    with store._connect() as con:
        con.execute("UPDATE events SET rowid = 100")
    store.save_snapshot(projects={}, agents={}, roles={}, runtime_defaults=RuntimeSettings(),
                        last_seqs=log.high_watermarks)
    later = log.append("agent.warning", stream="agent", project_id="p", session_id="a")
    store.append_event(later)
    assert store.event_metadata() == (2, {"p": 2}, {"a": 2})
