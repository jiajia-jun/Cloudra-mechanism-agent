"""v2-native AgentHub: forum posts as events, notifications via Mailbox."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.failures import RunFailureKind
from cloudra.runtime_v2.hub_bridge import handle_hub_tool
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class StopLLM:
    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(content=f"{agent.role_id} done", stop_requested=True)


async def _setup() -> tuple[RuntimeCore, object, object]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=StopLLM(),
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "hub"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    return core, project, result.data


async def _wait_state(agent, state: str, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


def _hub(args: dict) -> ToolCall:
    return ToolCall(id="t1", name="agent_hub", arguments=args)


@pytest.mark.parametrize("text,want", [
    ("CO2_GAP + 90%", {"co2_gap", "90"}),
    ("反应机理, 单", {"反应", "应机", "机理", "单"}),
    ("Sn2反应 / C_H 键", {"sn2", "反应", "c_h", "键"}),
    ("é-water-ΔG", {"water", "g"}),
    ("", set()),
])
def test_hub_search_tokenizes_words_and_cjk_bigrams(text, want):
    from cloudra.tools.Managetool.agent_hub import _query_tokens

    assert _query_tokens(text) == want


async def _spawn(core, parent, role_id: str, query: str = "help out"):
    bus = CommandBus(core)
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": parent.project_id},
            payload={"role_id": role_id, "parent_session_id": parent.id, "query": query},
        )
    )
    child = result.data
    await _wait_state(child, "succeeded")
    return child


def _inbox_texts(core, session_id: str) -> list[str]:
    inbox = core.mailbox.inbox(session_id)
    texts = []
    if inbox is not None:
        while not inbox.empty():
            texts.append(str(inbox.get_nowait().get("content", "")))
    return texts


@pytest.mark.asyncio
async def test_post_read_browse_search_roundtrip():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")

    posted = await handle_hub_tool(
        core, coordinator, _hub({"action": "post", "topic": "CO2 literature", "content": "Catalyst X gives 90% selectivity"})
    )
    assert posted.is_success is True
    assert posted.data["post_id"].startswith("evt_")

    read = await handle_hub_tool(core, coordinator, _hub({"action": "read", "topic": "CO2 literature"}))
    assert read.is_success is True
    assert read.data["posts"][0]["content"] == "Catalyst X gives 90% selectivity"
    assert read.data["posts"][0]["author_agent"] == "coordinator"

    browse = await handle_hub_tool(core, coordinator, _hub({"action": "browse"}))
    rows = browse.data["posts"]
    assert len(rows) == 1
    row = rows[0]
    assert row["topic"] == "CO2 literature"
    assert row["post_count"] == 1
    assert row["latest_author"] == "coordinator"
    assert row["preview"] == "Catalyst X gives 90% selectivity"
    assert row["latest_post_id"].startswith("evt_")
    assert "read" in browse.data["message"]

    hit = await handle_hub_tool(core, coordinator, _hub({"action": "search", "keyword": "selectivity"}))
    assert hit.is_success is True and len(hit.data["posts"]) == 1
    miss = await handle_hub_tool(core, coordinator, _hub({"action": "search", "keyword": "zzznohit"}))
    assert miss.is_success is True and miss.data["posts"] == []


@pytest.mark.asyncio
async def test_post_validation():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    assert (await handle_hub_tool(core, coordinator, _hub({"action": "post", "topic": "t"}))).is_success is False
    assert (
        await handle_hub_tool(core, coordinator, _hub({"action": "post", "topic": "t", "content": "c", "kind": "message"}))
    ).is_success is False
    assert (await handle_hub_tool(core, coordinator, _hub({"action": "teleport"}))).is_success is False


@pytest.mark.asyncio
async def test_hub_bridge_validates_receipts_before_returning(monkeypatch):
    from pydantic import ValidationError

    from cloudra.runtime_v2 import hub_bridge
    from cloudra.runtime_v2.policies.base import ToolResult

    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    monkeypatch.setattr(hub_bridge, "_directory", lambda *_: ToolResult(
        is_success=True, summary="bad receipt", data={"is_success": True, "sessions": [{"session_id": 42}]},
    ))
    try:
        with pytest.raises(ValidationError):
            await handle_hub_tool(core, coordinator, _hub({"action": "directory"}))
    finally:
        await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_hub_typed_posts_include_user_authored_posts():
    from cloudra.runtime_v2.hub_bridge import post_user_post

    core, project, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    await post_user_post(core, project.id, topic="user question", content="Please review the result")
    try:
        read = await handle_hub_tool(core, coordinator, _hub({"action": "read", "topic": "user question"}))
        assert read.data["posts"][0]["author_agent"] == "user"
        assert read.data["posts"][0]["author_session"] is None
        search = await handle_hub_tool(core, coordinator, _hub({"action": "search", "keyword": "review"}))
        assert search.data["posts"][0]["author_session"] is None
    finally:
        await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_call_receipt_distinguishes_durable_delivery_from_parked_wake():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    target = await _spawn(core, coordinator, "small_mol")
    await core.agent_host.start_run(target)
    await CommandBus(core).execute(Command(type="agent.cancel", target={"session_id": target.id}))
    result = await handle_hub_tool(core, coordinator, _hub({
        "action": "call", "to": target.id, "message": "Review the result on resume",
    }))
    assert result.is_success is True
    receipt = result.data["notifications"][0]
    assert receipt["delivery"] == "parked"
    assert receipt["wake_status"] == "parked"
    assert receipt["target_state"] == "cancelled"
    event = core.event_log.get(receipt["message_event_id"])
    assert event.type == "agent.message_injected"
    assert event.session_id == target.id
    assert core.mailbox.inbox(target.id).qsize() > 0
    assert target.state.value == "cancelled"
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_post_receipt_keeps_delivery_separate_for_already_running_recipient():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    target = await _spawn(core, coordinator, "small_mol")
    await core.agent_host.start_run(target)
    before = len(core.event_log.query_session(target.id, types={"run.started"}))
    result = await handle_hub_tool(core, coordinator, _hub({
        "action": "post", "topic": "progress", "content": "Review this on the next turn", "to_agent": target.id,
    }))
    receipt = result.data["notifications"][0]
    assert receipt["delivery"] == "delivered"
    assert receipt["wake_status"] == "already_running"
    assert receipt["target_state"] == "running"
    assert len(core.event_log.query_session(target.id, types={"run.started"})) == before
    assert core.event_log.get(receipt["message_event_id"]).type == "agent.message_injected"
    await core.runner.cancel_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("role_id", ["coordinator", "supervisor"])
async def test_hub_native_entry_rejects_unknown_fields_before_posting(role_id):
    core, project, author = await _setup()
    await _wait_state(author, "succeeded")
    if role_id == "supervisor":
        author = (await CommandBus(core).execute(Command(
            type="agent.spawn", target={"project_id": project.id},
            payload={"role_id": "supervisor", "settings": {"orchestration_mode": "dag_guided"}},
            actor="system",
        ))).data
    result = await LegacyToolExecutor(core).execute(author, _hub({
        "action": "post", "topic": "t", "content": "must not be published", "typo": True,
    }))
    assert result.is_success is False
    assert "arguments.typo" in result.summary
    assert core.event_log.query_project(project.id, types={"hub.posted"}) == []
    await core.runner.cancel_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments,field", [
    ({"action": "post", "topic": "t", "content": "reply", "parent_id": 1}, "parent_id"),
    ({"action": "browse", "cursor": 1}, "cursor"),
])
async def test_hub_rejects_integer_event_identifiers(arguments, field):
    core, project, author = await _setup()
    await _wait_state(author, "succeeded")
    result = await handle_hub_tool(core, author, _hub(arguments))
    assert result.is_success is False
    assert f"arguments.{field}" in result.summary
    assert core.event_log.query_project(project.id, types={"hub.posted"}) == []
    await core.runner.cancel_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["call", "post"])
async def test_hub_rejects_legacy_role_targets_without_side_effects(action):
    core, project, author = await _setup()
    await _wait_state(author, "succeeded")
    arguments = (
        {"action": "call", "to": "a-4", "message": "work"} if action == "call" else
        {"action": "post", "to_agent": "a-4", "topic": "t", "content": "work"}
    )
    result = await handle_hub_tool(core, author, _hub(arguments))
    assert result.is_success is False
    assert not any(a.role_id == "small_mol" for a in core.agents.values())
    assert core.event_log.query_project(project.id, types={"hub.posted"}) == []
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_to_agent_notification_via_mailbox():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "explorer")

    posted = await handle_hub_tool(
        core,
        coordinator,
        _hub({"action": "post", "topic": "t", "content": "explorer please check", "to_agent": "explorer"}),
    )
    assert posted.is_success is True
    assert "Notified explorer." in posted.summary
    texts = _inbox_texts(core, child.id)
    assert any("mentioned you in AgentHub" in t for t in texts)


@pytest.mark.asyncio
async def test_reply_notifies_original_author():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "explorer")

    original = await handle_hub_tool(core, child, _hub({"action": "post", "topic": "t", "content": "my finding"}))
    reply = await handle_hub_tool(
        core,
        coordinator,
        _hub({"action": "post", "topic": "t", "content": "nice work", "parent_id": original.data["post_id"]}),
    )
    assert reply.is_success is True
    assert "Notified original author explorer." in reply.summary
    texts = _inbox_texts(core, child.id)
    assert any("replied to your AgentHub post" in t for t in texts)


@pytest.mark.asyncio
async def test_broadcast_reply_parks_notice_for_failed_original_author():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    author = await _spawn(core, coordinator, "explorer")
    original = await handle_hub_tool(
        core, author, _hub({"action": "post", "topic": "t", "content": "finding"})
    )
    await core.agent_host.start_run(author)
    await core.agent_host.finish_run(
        author, outcome="failed", error="prior task failed",
        failure_kind=RunFailureKind.PROVIDER_PERMANENT,
    )
    reply = await handle_hub_tool(
        core, coordinator,
        _hub({
            "action": "post", "kind": "broadcast", "topic": "t", "content": "decision",
            "parent_id": original.data["post_id"],
        }),
    )
    assert reply.is_success is True
    assert reply.data["notified_count"] == 1
    texts = _inbox_texts(core, author.id)
    assert any("replied to your AgentHub post" in text for text in texts)
    assert author.state.value == "failed"


@pytest.mark.asyncio
async def test_directory_lists_live_sessions():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "dft")

    result = await handle_hub_tool(core, coordinator, _hub({"action": "directory"}))
    rows = {r["session_id"]: r for r in result.data["sessions"]}
    assert coordinator.id in rows and child.id in rows
    assert rows[child.id]["agent_id"] == "dft"
    assert rows[coordinator.id]["agent_type"] == "peer"
    assert rows[child.id]["agent_type"] == "subagent"
    assert rows[child.id]["parent_session_id"] == coordinator.id
    assert rows[coordinator.id]["role_id"] == "coordinator"
    assert rows[child.id]["role_id"] == "dft"


@pytest.mark.asyncio
async def test_directory_marks_system_supervisor_without_calling_it_a_subagent():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    supervisor = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": coordinator.project_id},
                payload={
                    "role_id": "supervisor",
                    "parent_session_id": coordinator.id,
                    "settings": {"orchestration_mode": "dag_guided"},
                },
                actor="system",
            )
        )
    ).data
    result = await handle_hub_tool(core, coordinator, _hub({"action": "directory"}))
    rows = {row["session_id"]: row for row in result.data["sessions"]}
    assert rows[supervisor.id]["agent_type"] == "system"
    assert rows[supervisor.id]["parent_session_id"] == coordinator.id


@pytest.mark.asyncio
async def test_call_to_live_session_delivers_via_mailbox():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "small_mol")

    result = await handle_hub_tool(
        core, coordinator, _hub({"action": "call", "to": child.id, "message": "ping me back"})
    )
    assert result.is_success is True
    assert result.data["session_id"] == child.id
    texts = _inbox_texts(core, child.id)
    assert any("[Incoming call]" in t and "ping me back" in t for t in texts)
    assert any("Reply to the caller through AgentHub" in t for t in texts)


@pytest.mark.asyncio
async def test_call_wakes_sleeping_agent():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "small_mol")
    runs_before = [e for e in core.event_log.query_session(child.id) if e.type == "run.started"]
    assert len(runs_before) == 1

    result = await handle_hub_tool(
        core, coordinator, _hub({"action": "call", "to": child.id, "message": "wake up"})
    )
    assert result.is_success is True
    await _wait_state(child, "succeeded")
    runs_after = [e for e in core.event_log.query_session(child.id) if e.type == "run.started"]
    assert len(runs_after) == 2


@pytest.mark.asyncio
async def test_to_agent_mention_wakes_sleeping_agent():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "explorer")
    runs_before = [e for e in core.event_log.query_session(child.id) if e.type == "run.started"]
    assert len(runs_before) == 1

    posted = await handle_hub_tool(
        core,
        coordinator,
        _hub({"action": "post", "topic": "t", "content": "explorer please check", "to_agent": "explorer"}),
    )
    assert posted.is_success is True
    await _wait_state(child, "succeeded")
    runs_after = [e for e in core.event_log.query_session(child.id) if e.type == "run.started"]
    assert len(runs_after) == 2


@pytest.mark.asyncio
async def test_mention_to_cancelled_agent_parks_without_reopening():
    """A2：hub mention 不复活用户取消的 agent——通知照常投递信箱驻留
    （parked），状态保持 cancelled、不开新 run。旧实现 _notify 无终态守卫，
    mention 会把 cancelled agent 直接 reopen。"""
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    # 子 agent 停在 queued（无 query）再取消——已 terminal 的 agent 不可 cancel。
    bus = CommandBus(core)
    child = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": coordinator.project_id},
                payload={"role_id": "explorer", "parent_session_id": coordinator.id},
            )
        )
    ).data
    await bus.execute(Command(type="agent.cancel", target={"session_id": child.id}, payload={}))
    assert child.state.value == "cancelled"
    runs_before = len([e for e in core.event_log.query_session(child.id) if e.type == "run.started"])

    posted = await handle_hub_tool(
        core,
        coordinator,
        _hub({"action": "post", "topic": "t", "content": "explorer please check", "to_agent": "explorer"}),
    )
    assert posted.is_success is True
    assert "Notified explorer." in posted.summary
    await asyncio.sleep(0.05)
    assert child.state.value == "cancelled"
    assert len([e for e in core.event_log.query_session(child.id) if e.type == "run.started"]) == runs_before
    texts = _inbox_texts(core, child.id)
    assert any("mentioned you in AgentHub" in t for t in texts)


@pytest.mark.asyncio
async def test_call_to_failed_agent_parks_without_reopening():
    """A2：hub call 对 failed agent 同样 parked 不唤醒（统一不复活纪律）。"""
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "small_mol")
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(
        child,
        outcome="failed",
        error="boom",
        failure_kind=RunFailureKind.PROVIDER_PERMANENT,
    )
    assert child.state.value == "failed"
    runs_before = len([e for e in core.event_log.query_session(child.id) if e.type == "run.started"])

    result = await handle_hub_tool(
        core, coordinator, _hub({"action": "call", "to": child.id, "message": "ping me back"})
    )
    assert result.is_success is True
    await asyncio.sleep(0.05)
    assert child.state.value == "failed"
    assert len([e for e in core.event_log.query_session(child.id) if e.type == "run.started"]) == runs_before
    texts = _inbox_texts(core, child.id)
    assert any("[Incoming call]" in t and "ping me back" in t for t in texts)


@pytest.mark.asyncio
async def test_call_to_role_replaces_failed_session_with_new_peer():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    failed = await _spawn(core, coordinator, "small_mol")
    await core.agent_host.start_run(failed)
    await core.agent_host.finish_run(
        failed,
        outcome="failed",
        error="prior work failed",
        failure_kind=RunFailureKind.PROVIDER_PERMANENT,
    )

    result = await handle_hub_tool(
        core, coordinator, _hub({"action": "call", "to": "small_mol", "message": "try a new task"})
    )
    assert result.is_success is True
    peer = core.agents[result.data["session_id"]]
    assert peer.id != failed.id
    assert peer.parent_session_id is None
    assert failed.state.value == "failed"


@pytest.mark.asyncio
async def test_call_to_role_spawns_independent_peer():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")

    result = await handle_hub_tool(
        core, coordinator, _hub({"action": "call", "to": "small_mol", "message": "optimize water"})
    )
    assert result.is_success is True
    peer = core.agents[result.data["session_id"]]
    assert peer.role_id == "small_mol"
    assert peer.parent_session_id is None
    await _wait_state(peer, "succeeded")
    injected = core.event_log.query_session(peer.id, types={"agent.message_injected"})
    assert any(coordinator.id in event.data["content"] and "optimize water" in event.data["content"] for event in injected)
    assert "final answer will be delivered to the caller automatically" in injected[-1].data["content"]
    assert injected[-1].data["sender"] == "coordinator"
    requested = [event for event in core.event_log.query_project(peer.project_id) if event.type == "agent.spawn_requested"]
    assert requested[-1].data["requested_by_session_id"] == coordinator.id


@pytest.mark.asyncio
async def test_call_normalizes_case_and_at_prefix_for_absent_role():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    result = await handle_hub_tool(
        core, coordinator, _hub({"action": "call", "to": "@SMALL_MOL", "message": "check this"})
    )
    assert result.is_success is True
    assert core.agents[result.data["session_id"]].role_id == "small_mol"
    requested = [
        event for event in core.event_log.query_project(coordinator.project_id)
        if event.type == "agent.spawn_requested"
    ]
    assert requested[-1].data["actor"] == "agent"
    assert not any("[Sub-agent finished] role=small_mol" in text for text in _inbox_texts(core, coordinator.id))


@pytest.mark.asyncio
async def test_non_coordinator_call_spawns_peer_without_inheriting_caller_settings():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    explorer = await _spawn(core, coordinator, "small_mol")
    await CommandBus(core).execute(
        Command(
            type="agent.settings_update",
            target={"session_id": explorer.id},
            payload={"yolo": True, "unattended": True},
        )
    )
    assert explorer.settings.yolo and explorer.settings.unattended

    result = await handle_hub_tool(
        core, explorer, _hub({"action": "call", "to": "researcher", "message": "check this method"})
    )
    assert result.is_success is True
    peer = core.agents[result.data["session_id"]]
    assert peer.role_id == "researcher"
    assert peer.parent_session_id is None
    assert peer.settings.yolo is False
    assert peer.settings.unattended is False
    assert result.data["settings"]["sources"]["yolo"] == "schema_default"
    await _wait_state(peer, "succeeded")


@pytest.mark.asyncio
async def test_hub_cannot_create_system_managed_supervisor():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    result = await handle_hub_tool(
        core, coordinator, _hub({"action": "call", "to": "supervisor", "message": "review this"})
    )
    assert result.is_success is False
    assert "system-managed" in result.summary
    assert not any(agent.role_id == "supervisor" for agent in core.agents.values())


@pytest.mark.asyncio
async def test_call_retries_message_persistence_without_duplicate_peer():
    class FailFirstMessageStore:
        def __init__(self):
            self.failed = False

        def append_event(self, event):
            if event.type == "agent.message_injected" and not self.failed:
                self.failed = True
                raise OSError("transient write failure")

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "partial-call"}))).data
    caller = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    store = FailFirstMessageStore()
    core.store = store

    result = await handle_hub_tool(
        core, caller, _hub({"action": "call", "to": "researcher", "message": "review the method"})
    )
    assert store.failed is True
    assert result.is_success is True
    peer = core.agents[result.data["session_id"]]
    injected = core.event_log.query_session(peer.id, types={"agent.message_injected"})
    assert len(injected) == 1
    assert injected[0].data["sender"] == "coordinator"
    assert "review the method" in injected[0].data["content"]


@pytest.mark.asyncio
async def test_call_reports_created_peer_when_message_remains_undeliverable():
    class FailMessageStore:
        def append_event(self, event):
            if event.type == "agent.message_injected":
                raise OSError("disk unavailable")

    class RecordingRunner:
        def __init__(self):
            self.scheduled = []

        def schedule(self, session_id):
            self.scheduled.append(session_id)

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "failed-call"}))).data
    caller = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    core.store = FailMessageStore()
    core.runner = RecordingRunner()

    result = await handle_hub_tool(
        core, caller, _hub({"action": "call", "to": "researcher", "message": "review the method"})
    )
    assert result.is_success is False
    peer = core.agents[result.data["session_id"]]
    assert peer.role_id == "researcher"
    assert peer.state.value == "queued"
    assert core.runner.scheduled == []
    assert "not delivered" in result.summary
    assert core.event_log.query_session(peer.id, types={"agent.message_injected"}) == []


@pytest.mark.asyncio
async def test_cancel_peer_succeeds_when_completion_notice_cannot_persist():
    class FailReportStore:
        def append_event(self, event):
            if (event.data.get("manifest") or {}).get("kind") == "peer_call_completion":
                raise OSError("notice write failed")

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "cancel-peer"}))).data
    caller = (
        await bus.execute(
            Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "researcher"})
        )
    ).data
    peer = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "researcher", "requested_by_session_id": caller.id},
            )
        )
    ).data
    core.store = FailReportStore()

    result = await bus.execute(Command(type="agent.cancel", target={"session_id": peer.id}))
    assert result.accepted is True
    assert peer.state.value == "cancelled"
    assert not any(
        (event.data.get("manifest") or {}).get("kind") == "peer_call_completion"
        for event in core.event_log
    )


@pytest.mark.asyncio
async def test_call_to_unknown_target_rejected():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    result = await handle_hub_tool(core, coordinator, _hub({"action": "call", "to": "nonsense", "message": "hi"}))
    assert result.is_success is False


@pytest.mark.asyncio
async def test_executor_intercepts_agent_hub():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    executor = LegacyToolExecutor(core)
    result = await executor.execute(coordinator, _hub({"action": "browse"}))
    assert result.is_success is True
    assert "forum" in result.summary


@pytest.mark.asyncio
async def test_browse_cursor_and_search_sources_status():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    for i in range(3):
        await handle_hub_tool(
            core,
            coordinator,
            _hub({"action": "post", "topic": f"topic-{i}", "content": f"content {i}"}),
        )
    first = await handle_hub_tool(core, coordinator, _hub({"action": "browse", "limit": 1}))
    assert first.is_success is True
    assert first.data["next_cursor"] is not None
    second = await handle_hub_tool(
        core, coordinator, _hub({"action": "browse", "limit": 1, "cursor": first.data["next_cursor"]})
    )
    assert second.is_success is True
    assert second.data["posts"]
    assert second.data["posts"][0]["topic"] != first.data["posts"][0]["topic"]

    search = await handle_hub_tool(core, coordinator, _hub({"action": "search", "keyword": "content"}))
    assert search.is_success is True
    assert search.data.get("sources_status", {}).get("project_posts") == "available"


@pytest.mark.asyncio
async def test_notification_consumed_event_emitted_when_context_built():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "explorer")
    posted = await handle_hub_tool(
        core,
        coordinator,
        _hub({"action": "post", "topic": "t", "content": "explorer please read", "to_agent": "explorer"}),
    )
    assert posted.is_success is True
    await _wait_state(child, "succeeded")
    consumed = [
        e for e in core.event_log.query_session(child.id)
        if e.type == "hub.notification_consumed"
    ]
    assert consumed
    assert consumed[-1].data.get("post_id")


@pytest.mark.asyncio
async def test_subagent_at_coordinator_wakes_coordinator():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "small_mol")

    posted = await handle_hub_tool(
        core,
        child,
        _hub({"action": "post", "topic": "TS result", "content": "TS found!", "to_agent": "@coordinator"}),
    )
    assert posted.is_success is True
    assert "Notified @coordinator" in posted.summary
    # Coordinator wakes up and transitions through runner
    await _wait_state(coordinator, "succeeded")
    events = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})
    assert any("TS found!" in e.data.get("content", "") for e in events)


@pytest.mark.asyncio
async def test_broadcast_notifies_all_other_sessions_regardless_of_author_role():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "small_mol")
    peer = await _spawn(core, coordinator, "explorer")
    failed = await _spawn(core, coordinator, "dft")
    await core.agent_host.start_run(failed)
    await core.agent_host.finish_run(
        failed,
        outcome="failed",
        error="prior work failed",
        failure_kind=RunFailureKind.PROVIDER_PERMANENT,
    )

    posted = await handle_hub_tool(
        core,
        child,
        _hub({"action": "post", "kind": "broadcast", "topic": "milestone", "content": "All jobs complete"}),
    )
    assert posted.is_success is True
    assert posted.data["notified_count"] == 2
    assert "Notified 2 project sessions" in posted.summary
    for target in (coordinator, peer):
        events = core.event_log.query_session(target.id, types={"agent.message_injected"})
        assert any("All jobs complete" in e.data.get("content", "") for e in events)
    failed_events = core.event_log.query_session(failed.id, types={"agent.message_injected"})
    assert not any("All jobs complete" in e.data.get("content", "") for e in failed_events)

    posted_by_coordinator = await handle_hub_tool(
        core,
        coordinator,
        _hub({"action": "post", "kind": "broadcast", "topic": "next step", "content": "Review the result"}),
    )
    assert posted_by_coordinator.is_success is True
    assert posted_by_coordinator.data["notified_count"] == 2
    for target in (child, peer):
        events = core.event_log.query_session(target.id, types={"agent.message_injected"})
        assert any("Review the result" in e.data.get("content", "") for e in events)
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_failed_broadcast_can_retry_only_missing_notifications():
    class FailSecondRecipientOnce:
        def __init__(self, second_id):
            self.second_id = second_id
            self.failed = False

        def append_event(self, event):
            if (
                event.type == "agent.message_injected"
                and event.session_id == self.second_id
                and not self.failed
            ):
                self.failed = True
                raise OSError("transient recipient write failure")

    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    first = await _spawn(core, coordinator, "small_mol")
    second = await _spawn(core, coordinator, "explorer")
    core.event_writer.mark_restored()
    core.store = FailSecondRecipientOnce(second.id)

    args = {"action": "post", "kind": "broadcast", "topic": "result", "content": "Review this"}
    partial = await handle_hub_tool(core, coordinator, _hub(args))
    assert partial.is_success is False
    assert partial.data["post_id"]
    assert partial.data["notified_count"] == 1
    assert partial.data["failed_session_ids"] == [second.id]

    retried = await handle_hub_tool(core, coordinator, _hub({**args, "post_id": partial.data["post_id"]}))
    assert retried.is_success is True
    assert retried.data["post_id"] == partial.data["post_id"]
    assert len([p for p in core.event_log.query_project(coordinator.project_id, types={"hub.posted"})]) == 1
    for target in (first, second):
        notices = [
            e for e in core.event_log.query_session(target.id, types={"agent.message_injected"})
            if e.data.get("post_id") == partial.data["post_id"]
        ]
        assert len(notices) == 1
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_post_commit_then_error_does_not_duplicate_notification(tmp_path, monkeypatch):
    core, project, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    recipient = await _spawn(core, coordinator, "explorer")
    await core.runner.cancel_all()
    core.runner = None
    store = RuntimeStore(tmp_path / "runtime.db")
    core.store = store
    await core.event_writer.flush()
    original_append = store.append_event
    raised = False

    def committed_then_raised(event):
        nonlocal raised
        original_append(event)
        if event.type == "agent.message_injected" and event.session_id == recipient.id and not raised:
            raised = True
            raise OSError("acknowledgement lost after commit")

    monkeypatch.setattr(store, "append_event", committed_then_raised)
    args = {"action": "post", "topic": "result", "content": "Please inspect", "to_agent": recipient.id}
    posted = await handle_hub_tool(core, coordinator, _hub(args))
    assert raised is True
    assert posted.is_success is True
    retried = await handle_hub_tool(core, coordinator, _hub({**args, "post_id": posted.data["post_id"]}))
    assert retried.is_success is True
    notices = [
        event for event in store.events_after({})
        if event["type"] == "agent.message_injected" and event["session_id"] == recipient.id
        and event["data"].get("post_id") == posted.data["post_id"]
    ]
    assert len(notices) == 1
    assert notices[0]["project_id"] == project.id


@pytest.mark.asyncio
async def test_restore_repairs_only_frozen_missing_broadcast_notifications(tmp_path, monkeypatch):
    core, project, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    first = await _spawn(core, coordinator, "small_mol")
    second = await _spawn(core, coordinator, "explorer")
    store = RuntimeStore(tmp_path / "runtime.db")
    core.store = store
    await core.event_writer.flush()
    original_append = store.append_event
    failed = False

    def fail_second_once(event):
        nonlocal failed
        if event.type == "agent.message_injected" and event.session_id == second.id and not failed:
            failed = True
            raise OSError("simulated notification write failure")
        return original_append(event)

    monkeypatch.setattr(store, "append_event", fail_second_once)
    partial = await handle_hub_tool(
        core, coordinator,
        _hub({"action": "post", "kind": "broadcast", "topic": "results", "content": "Review the data"}),
    )
    assert partial.is_success is False
    post_id = partial.data["post_id"]
    monkeypatch.setattr(store, "append_event", original_append)
    late = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "researcher"},
            )
        )
    ).data
    await _wait_state(first, "succeeded")

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    notices = [
        event for event in restored.event_log
        if event.type == "agent.message_injected" and event.data.get("post_id") == post_id
    ]
    assert {event.session_id for event in notices} == {first.id, second.id}
    assert len(notices) == 2
    expected = (
        f"coordinator broadcast in AgentHub topic 'results' (post {post_id}): Review the data"
    )
    assert all(event.data["content"] == expected for event in notices)
    assert not any(event.session_id == late.id for event in notices)
    assert restored.agents[second.id].state.value == "succeeded"  # restore never wakes

    again = RuntimeCore(strict_events=True)
    again.store = store
    restore_core(again, store)
    assert len([
        event for event in again.event_log
        if event.type == "agent.message_injected" and event.data.get("post_id") == post_id
    ]) == 2
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_restore_repairs_reply_notice_for_cancelled_original_author(tmp_path, monkeypatch):
    core, _project, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    original_author = await _spawn(core, coordinator, "explorer")
    store = RuntimeStore(tmp_path / "runtime.db")
    core.store = store
    await core.event_writer.flush()
    original = await handle_hub_tool(
        core, original_author,
        _hub({"action": "post", "topic": "original topic", "content": "finding"}),
    )
    await core.agent_host.start_run(original_author)
    cancelled = await CommandBus(core).execute(
        Command(type="agent.cancel", target={"session_id": original_author.id})
    )
    assert cancelled.accepted
    original_append = store.append_event
    failed = False

    def fail_reply_once(event):
        nonlocal failed
        if event.type == "agent.message_injected" and event.session_id == original_author.id and not failed:
            failed = True
            raise OSError("simulated reply notification write failure")
        return original_append(event)

    monkeypatch.setattr(store, "append_event", fail_reply_once)
    partial = await handle_hub_tool(
        core, coordinator,
        _hub({
            "action": "post", "kind": "broadcast", "topic": "response",
            "content": "decision", "parent_id": original.data["post_id"],
        }),
    )
    assert partial.is_success is False
    post_id = partial.data["post_id"]
    monkeypatch.setattr(store, "append_event", original_append)

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    author = restored.agents[original_author.id]
    assert author.state.value == "cancelled"
    notices = [
        event for event in restored.event_log
        if event.type == "agent.message_injected" and event.session_id == author.id
        and event.data.get("post_id") == post_id
    ]
    assert len(notices) == 1
    expected = (
        f"coordinator replied to your AgentHub post in topic 'original topic' "
        f"{original.data['post_id']} (reply {post_id}): decision"
    )
    assert notices[0].data["content"] == expected
    inbox = restored.mailbox.inbox(author.id)
    assert inbox is not None and inbox.get_nowait()["content"] == expected

    again = RuntimeCore(strict_events=True)
    again.store = store
    restore_core(again, store)
    assert again.agents[author.id].state.value == "cancelled"
    inbox_again = again.mailbox.inbox(author.id)
    assert inbox_again is not None
    restored_notice = inbox_again.get_nowait()
    assert restored_notice["content"] == expected
    assert restored_notice["post_id"] == post_id
    assert len([
        event for event in again.event_log
        if event.type == "agent.message_injected" and event.session_id == author.id
        and event.data.get("post_id") == post_id
    ]) == 1
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_call_unknown_role_fuzzy_suggestion():
    core, project, author = await _setup()
    call = _hub({
        "action": "call",
        "to": "smallmol",
        "message": "check this structure",
    })
    result = await handle_hub_tool(core, author, call)
    assert result.is_success is False
    assert "Did you mean 'small_mol'?" in result.summary
    assert "Available roles:" in result.summary
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_project_supervisor_feedback_wakes_its_coordinator():
    from cloudra.runtime_v2.supervision import _spawn_supervisor

    core, project, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    supervisor = await _spawn_supervisor(core, project.id)
    assert supervisor is not None
    before = len(core.event_log.query_session(coordinator.id, types={"run.started"}))
    posted = await handle_hub_tool(core, supervisor, _hub({
        "action": "post", "topic": "review", "content": "Review needs revision",
        "to_agent": coordinator.id,
    }))
    await _wait_state(coordinator, "succeeded")
    assert len(core.event_log.query_session(coordinator.id, types={"run.started"})) == before + 1
    assert posted.data["notifications"][0]["wake_policy"] == "park_terminal"
    await core.runner.cancel_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("author_kind", ["ordinary", "unbound_supervisor"])
async def test_posts_deliver_and_wake_recipient(author_kind):
    from cloudra.runtime_v2.schemas import PermissionSet

    core, project, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    author = (await CommandBus(core).execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "supervisor" if author_kind == "unbound_supervisor" else "explorer"},
        actor="system",
    ))).data
    author.capabilities.permissions = PermissionSet(read=True)
    posted = await handle_hub_tool(core, author, _hub({
        "action": "post", "topic": "review", "content": "Evidence report",
        "to_agent": coordinator.id,
    }))
    assert posted.is_success is True
    assert posted.data["notifications"][0]["delivery"] == "delivered"
    assert posted.data["notifications"][0]["wake_policy"] == "park_terminal"
    await core.runner.cancel_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
async def test_supervisor_feedback_never_revives_terminal_coordinator(terminal):
    from cloudra.runtime_v2.supervision import _spawn_supervisor

    core, project, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    supervisor = await _spawn_supervisor(core, project.id)
    await core.agent_host.start_run(coordinator)
    if terminal == "failed":
        await core.agent_host.finish_run(
            coordinator, outcome="failed", error="failed before review",
            failure_kind=RunFailureKind.PROVIDER_PERMANENT,
        )
    else:
        await CommandBus(core).execute(Command(type="agent.cancel", target={"session_id": coordinator.id}))
    before = len(core.event_log.query_session(coordinator.id, types={"run.started"}))
    result = await handle_hub_tool(core, supervisor, _hub({
        "action": "post", "topic": "review", "content": "Review needs revision", "to_agent": coordinator.id,
    }))
    assert coordinator.state.value == terminal
    assert len(core.event_log.query_session(coordinator.id, types={"run.started"})) == before
    assert result.data["notifications"][0]["delivery"] == "parked"
    assert result.data["notifications"][0]["target_state"] == terminal
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_supervisor_can_call_coordinator_and_post_to_peers():
    from cloudra.runtime_v2.supervision import _spawn_supervisor

    core, project, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    supervisor = await _spawn_supervisor(core, project.id)
    call = await handle_hub_tool(core, supervisor, _hub({
        "action": "call", "to": coordinator.id, "message": "Review suggestions",
    }))
    assert call.is_success is True
    peer = await _spawn(core, coordinator, "small_mol")
    posted = await handle_hub_tool(core, supervisor, _hub({
        "action": "post", "topic": "review", "content": "Review feedback", "to_agent": peer.id,
    }))
    assert posted.is_success is True
    assert posted.data["notifications"][0]["delivery"] == "delivered"
    assert posted.data["notifications"][0]["wake_policy"] == "park_terminal"
    other_core, other_project, other = await _setup()
    await _wait_state(other, "succeeded")
    core.projects[other_project.id] = other_project
    core.agents[other.id] = other
    cross = await handle_hub_tool(core, supervisor, _hub({
        "action": "post", "topic": "review", "content": "Run privileged work", "to_agent": other.id,
    }))
    assert cross.is_success is False
    assert core.event_log.query_session(other.id, types={"agent.message_injected"}) == []
    await core.runner.cancel_all()
    await other_core.runner.cancel_all()


@pytest.mark.asyncio
async def test_call_persists_bound_assignment_before_child_run():
    core, project, coordinator = await _setup()
    try:
        await _wait_state(coordinator, "succeeded")
        child = (await CommandBus(core).execute(Command(
            type="agent.spawn", target={"project_id": project.id},
            payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
        ))).data
        result = await handle_hub_tool(core, coordinator, _hub({
            "action": "call", "to": child.id, "message": "new task",
        }))
        injected = core.event_log.get(result.data["notifications"][0]["message_event_id"])
        assert injected.data.get("manifest") == {
            "kind": "task_assignment", "session_id": child.id, "parent_session_id": coordinator.id,
        }
        await _wait_state(child, "succeeded")
        started = core.event_log.query_session(child.id, types={"run.started"})[0]
        assert injected.seq < started.seq
    finally:
        await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_low_permission_expected_child_reply_wakes_parent_without_granting_tools():
    from cloudra.runtime_v2.schemas import PermissionSet

    core, project, coordinator = await _setup()
    release = asyncio.Event()
    entered = asyncio.Event()

    class WaitingChildLLM(StopLLM):
        async def complete(self, agent, messages, tools, **kwargs):
            if agent.role_id == "small_mol":
                entered.set()
                await release.wait()
            return await super().complete(agent, messages, tools, **kwargs)

    try:
        await _wait_state(coordinator, "succeeded")
        core.runner.pipeline.llm = WaitingChildLLM()
        child = (await CommandBus(core).execute(Command(
            type="agent.spawn", target={"project_id": project.id},
            payload={"role_id": "small_mol", "parent_session_id": coordinator.id},
        ))).data
        await handle_hub_tool(core, coordinator, _hub({
            "action": "call", "to": child.id, "message": "report this task",
        }))
        await asyncio.wait_for(entered.wait(), 5)
        child.capabilities.permissions = PermissionSet(read=True)
        permissions = child.capabilities.model_dump()
        before = len(core.event_log.query_session(coordinator.id, types={"run.started"}))
        result = await handle_hub_tool(core, child, _hub({
            "action": "post", "kind": "answer", "topic": "task result", "content": "result",
            "to_agent": coordinator.id,
        }))
        assert result.data["notifications"][0]["wake_policy"] == "park_terminal"
        await _wait_state(coordinator, "succeeded")
        assert len(core.event_log.query_session(coordinator.id, types={"run.started"})) == before + 1
        assert child.capabilities.model_dump() == permissions
        called = await handle_hub_tool(core, child, _hub({
            "action": "call", "to": coordinator.id, "message": "report progress to parent",
        }))
        assert called.is_success is True
        unrelated = await _spawn(core, coordinator, "dft")
        unrelated.parent_session_id = None
        called_peer = await handle_hub_tool(core, child, _hub({
            "action": "call", "to": unrelated.id, "message": "coordinate on TS",
        }))
        assert called_peer.is_success is True
    finally:
        release.set()
        await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_completed_child_post_delivers_to_parent():
    from cloudra.runtime_v2.schemas import PermissionSet

    core, _, coordinator = await _setup()
    try:
        await _wait_state(coordinator, "succeeded")
        child = await _spawn(core, coordinator, "small_mol")
        await _wait_state(child, "succeeded")
        await _wait_state(coordinator, "succeeded")
        child.capabilities.permissions = PermissionSet(read=True)
        result = await handle_hub_tool(core, child, _hub({
            "action": "post", "kind": "answer", "topic": "old task", "content": "late post",
            "to_agent": coordinator.id,
        }))
        assert result.is_success is True
        assert result.data["notifications"][0]["wake_policy"] == "park_terminal"
    finally:
        await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_child_can_call_parent_coordinator_via_parent_alias_or_id():
    """Issue #177: Child subagent calling its parent coordinator is control-plane feedback,

    not delegation, and must not fail with 'Delegation would grant permissions absent from the caller: manage'.
    Also verifies 'to="parent"' and 'to="@coordinator"' resolve to author.parent_session_id.
    """
    from cloudra.runtime_v2.schemas import PermissionSet

    core, project, coordinator = await _setup()
    try:
        await _wait_state(coordinator, "succeeded")
        child = await _spawn(core, coordinator, "small_mol")
        child.capabilities.permissions = PermissionSet(read=True, write=True)

        # 1. Call by coordinator session ID
        call_by_id = await handle_hub_tool(core, child, _hub({
            "action": "call", "to": coordinator.id, "message": "Reporting intermediate TS result",
        }))
        assert call_by_id.is_success is True
        assert call_by_id.data["session_id"] == coordinator.id

        # 2. Call by alias 'parent'
        call_by_parent = await handle_hub_tool(core, child, _hub({
            "action": "call", "to": "parent", "message": "Calling parent directly",
        }))
        assert call_by_parent.is_success is True
        assert call_by_parent.data["session_id"] == coordinator.id

        # 3. Call by role '@coordinator'
        call_by_role = await handle_hub_tool(core, child, _hub({
            "action": "call", "to": "@coordinator", "message": "Calling @coordinator",
        }))
        assert call_by_role.is_success is True
        assert call_by_role.data["session_id"] == coordinator.id
    finally:
        await core.runner.cancel_all()
