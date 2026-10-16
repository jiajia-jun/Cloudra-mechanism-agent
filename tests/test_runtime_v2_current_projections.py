"""Current requests and unread input reuse durable projections, never history scans."""

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import AgentSession, Project


def _core():
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="projections")
    core.agents["a"] = AgentSession(id="a", project_id="p", role_id="explorer", display_name="a")
    return core


@pytest.mark.asyncio
async def test_pending_and_reminders_do_not_rebuild_history_after_cache_eviction(tmp_path, monkeypatch):
    core = _core()
    core.store = RuntimeStore(tmp_path / "runtime.db")
    requests = [
        ("approval.requested", {"approval_id": "apv", "tool_name": "write", "details": "review"}),
        ("interaction.requested", {"interaction_id": "ixn", "prompt": "which solvent?"}),
        ("reminder.scheduled", {"message": "check", "wake_ts": 9999999999}),
    ]
    for type_, data in requests:
        await core.event_writer.commit(EventDraft(type_, stream="agent", project_id="p", session_id="a", data=data))
    for index in range(520):
        core.record("agent.warning", stream="agent", project_id="p", session_id="a", data={"i": index})
    await core.event_writer.flush()

    def no_history(*_args, **_kwargs):
        raise AssertionError("current-state query scanned historical events")
    monkeypatch.setattr(core.event_log, "query_project", no_history)
    monkeypatch.setattr(core.event_log, "iter_events", no_history)
    assert core.pending.list_pending_approvals("p")[0]["id"] == "apv"
    assert core.pending.list_pending_interactions("p")[0]["interaction_id"] == "ixn"
    assert core.reminders.pending_in_project("p")[0]["message"] == "check"
    await core.pending.respond_interaction("p", "ixn", "water")
    assert core.pending.list_pending_interactions("p") == []
    await core.aclose()


@pytest.mark.asyncio
async def test_failed_persistence_does_not_publish_pending_projection(tmp_path, monkeypatch):
    core = _core()
    core.store = RuntimeStore(tmp_path / "runtime.db")
    def fail(_event):
        raise OSError("disk unavailable")
    monkeypatch.setattr(core.store, "append_event", fail)
    with pytest.raises(EventPersistenceError):
        await core.event_writer.commit(EventDraft("interaction.requested", stream="agent", project_id="p", session_id="a", data={"interaction_id": "ixn", "prompt": "question"}))
    assert core.pending.list_pending_interactions("p") == []
    await core.aclose()


@pytest.mark.asyncio
async def test_unread_projection_keeps_drained_but_uncommitted_input():
    core = _core()
    event = await core.event_writer.commit(EventDraft("agent.message_injected", stream="agent", project_id="p", session_id="a", data={"message_id": "m", "sender": "user", "content": "hello"}))
    core.mailbox.enqueue("a", core.mailbox.message_payload(message_id="m", sender="user", content="hello"))
    core.mailbox.inbox("a").get_nowait()
    saved = core.mailbox.snapshot()
    restored = _core()
    restored.mailbox.restore(saved)
    assert restored.mailbox.unread()[0].event_id == event.event_id
    await core.event_writer.commit(EventDraft("context.appended", stream="agent", project_id="p", session_id="a", data={"messages": [{"role": "user", "message_id": "m", "content": "hello"}]}))
    assert core.mailbox.unread() == []
    await core.aclose()
    await restored.aclose()


@pytest.mark.asyncio
async def test_cold_restore_reuses_snapshot_views_and_reads_only_tail(tmp_path, monkeypatch):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.persistence import restore_core

    core = _core()
    core.store = RuntimeStore(tmp_path / "runtime.db")
    await core.event_writer.commit(EventDraft("agent.message_injected", stream="agent", project_id="p", session_id="a", data={"message_id": "unread", "sender": "user", "content": "retain"}))
    for index in range(520):
        core.record("agent.warning", stream="agent", project_id="p", session_id="a", data={"i": index})
    await CommandBus(core).flush_snapshot()
    original = core.store.iter_events
    reads = []

    def scoped_reads(**kwargs):
        reads.append(kwargs)
        assert kwargs.get("last_seqs") or kwargs.get("tail") and kwargs.get("limit") == 512, "warm snapshot triggered a historical scan"
        return original(**kwargs)

    monkeypatch.setattr(core.store, "iter_events", scoped_reads)
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, core.store)
    assert restored.store is core.store
    assert restored.mailbox.inbox("a").get_nowait()["message_id"] == "unread"
    assert restored.agents["a"].state.value == "queued"
    assert len(reads) == 2
    await core.aclose()
    await restored.aclose()


@pytest.mark.asyncio
async def test_snapshot_failure_still_publishes_its_durable_notice(tmp_path, monkeypatch):
    from cloudra.runtime_v2.commands import CommandBus

    core = _core()
    core.store = RuntimeStore(tmp_path / "runtime.db")
    seen = []

    async def observe(event):
        seen.append(event.type)
        if event.type == "agent.warning":
            core.notices.pin("a", "note", "durable notice")

    def fail_snapshot(**_kwargs):
        raise OSError("snapshot unavailable")

    core.event_hub.subscribe(observe)
    monkeypatch.setattr(core.store, "save_snapshot", fail_snapshot)
    core.record("agent.warning", stream="agent", project_id="p", session_id="a", data={"message": "warning"})
    with pytest.raises(OSError, match="snapshot unavailable"):
        await CommandBus(core).flush_snapshot()
    assert seen == ["agent.warning", "context.pin_set"]
    await core.event_writer.flush()
    assert seen == ["agent.warning", "context.pin_set"]
    await core.aclose()
