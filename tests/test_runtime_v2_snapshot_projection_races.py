"""Snapshots taken by event subscribers must include the event's projection."""

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import AgentSession, Project


def setup_core(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    core.projects["p"] = Project(id="p", name="snapshot", workspace_dir=str(tmp_path))
    core.agents["a"] = AgentSession(id="a", project_id="p", role_id="coordinator", display_name="a")
    return core


@pytest.mark.asyncio
async def test_context_event_snapshot_keeps_consumed_user_message(tmp_path):
    core = setup_core(tmp_path)
    await core.dispatcher.commit_and_deliver(
        to_session_id="a",
        project_id="p",
        content="input",
        sender="user",
        wake=WakePolicy.NEVER,
    )
    message = core.mailbox.inbox("a").get_nowait()
    captured = []

    async def snapshot_on_context(event):
        if event.type == "context.appended":
            await CommandBus(core).flush_snapshot()
            captured.append(core.store.load_snapshot()[0])

    core.event_hub.subscribe(snapshot_on_context)
    await core.contexts.commit_input(
        agent=core.agents["a"],
        run_id="r",
        context_prefix=None,
        notices=None,
        user_messages=[{"role": "user", "message_id": message["message_id"], "content": message["content"]}],
    )
    assert len(captured) == 1
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, core.store)
    assert [item["message_id"] for item in restored.contexts.current_messages("a")] == [message["message_id"]]
    assert restored.mailbox.unread() == []


@pytest.mark.asyncio
async def test_group_event_snapshot_keeps_created_group(tmp_path):
    core = setup_core(tmp_path)
    captured = []

    async def snapshot_on_group(event):
        if event.type == "launch_group.created":
            await CommandBus(core).flush_snapshot()
            captured.append(core.store.load_snapshot()[0])

    core.event_hub.subscribe(snapshot_on_group)
    await core.launch_groups._commit(
        "launch_group.created",
        project_id="p",
        session_id="a",
        data={"group_id": "group", "max_concurrency": 1, "items": [{"item_id": "one", "query": "task"}]},
    )
    assert len(captured) == 1
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, core.store)
    group = restored.launch_groups.get("group")
    assert group is not None
    assert group.state == "interrupted"
    assert group.items[0].query == "task"


@pytest.mark.asyncio
async def test_drained_mailbox_message_is_unread_until_context_commit(tmp_path):
    core = setup_core(tmp_path)
    await core.dispatcher.commit_and_deliver(
        to_session_id="a",
        project_id="p",
        content="input",
        sender="user",
        wake=WakePolicy.NEVER,
    )
    message = core.mailbox.inbox("a").get_nowait()
    await CommandBus(core).flush_snapshot()
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, core.store)
    assert restored.mailbox.inbox("a").get_nowait()["message_id"] == message["message_id"]


@pytest.mark.asyncio
async def test_restore_releases_cancelled_dead_letters_but_keeps_peer_and_hub(tmp_path):
    from cloudra.runtime_v2.effects import EventDraft
    from cloudra.runtime_v2.schemas import AgentState

    core = setup_core(tmp_path)
    ordinary = await core.dispatcher.commit_and_deliver(
        to_session_id="a",
        project_id="p",
        content="old input",
        sender="user",
        wake=WakePolicy.NEVER,
    )
    peer = await core.dispatcher.commit_and_deliver(
        to_session_id="a",
        project_id="p",
        content="peer result",
        sender="peer",
        wake=WakePolicy.NEVER,
        manifest={"kind": "peer_call_completion", "session_id": "peer"},
    )
    post = await core.event_writer.commit(
        EventDraft(
            "hub.posted",
            stream="project",
            project_id="p",
            data={"notification_target_ids": ["a"], "author_agent": "peer", "content": "post"},
        )
    )
    hub = await core.dispatcher.commit_and_deliver(
        to_session_id="a",
        project_id="p",
        content="hub notice",
        sender="peer",
        wake=WakePolicy.NEVER,
        post_id=post.event_id,
    )
    await core.agent_host.transition(core.agents["a"], AgentState.CANCELLED, reason="cancel")
    await CommandBus(core).flush_snapshot()
    for _ in range(2):
        restored = RuntimeCore(strict_events=True)
        restore_core(restored, core.store)
        live_ids = {event.event_id for event in restored.mailbox.unread()}
        assert live_ids == {peer.event_id, hub.event_id}
        assert ordinary.event_id not in live_ids
        inbox = restored.mailbox.inbox("a")
        assert {inbox.get_nowait()["message_id"] for _ in range(inbox.qsize())} == {
            peer.data["message_id"],
            hub.data["message_id"],
        }
        snapshot, _ = core.store.load_snapshot()
        assert {event["event_id"] for event in snapshot["mailbox"]["unread"]} == live_ids
