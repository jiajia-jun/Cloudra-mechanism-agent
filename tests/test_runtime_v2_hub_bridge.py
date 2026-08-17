"""v2-native AgentHub: forum posts as events, notifications via Mailbox."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.hub_bridge import handle_hub_tool
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
    assert browse.data["posts"] == [
        {"topic": "CO2 literature", "post_count": 1, "latest_at": browse.data["posts"][0]["latest_at"]}
    ]

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
async def test_directory_lists_live_sessions():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")
    child = await _spawn(core, coordinator, "dft")

    result = await handle_hub_tool(core, coordinator, _hub({"action": "directory"}))
    rows = {r["session_id"]: r for r in result.data["sessions"]}
    assert coordinator.id in rows and child.id in rows
    assert rows[child.id]["agent_id"] == "dft"
    assert rows[coordinator.id]["agent_type"] == "coordinator"


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


@pytest.mark.asyncio
async def test_call_to_role_spawns_fresh_child():
    core, _, coordinator = await _setup()
    await _wait_state(coordinator, "succeeded")

    result = await handle_hub_tool(
        core, coordinator, _hub({"action": "call", "to": "a-4", "message": "optimize water"})
    )
    assert result.is_success is True
    child = core.agents[result.data["session_id"]]
    assert child.role_id == "small_mol"
    await _wait_state(child, "succeeded")


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
