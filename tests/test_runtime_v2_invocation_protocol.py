"""Run-fixed invocation protocol: schemas, planners, apply and replay."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cloudra.runtime_v2.agent_host import plan_start_run
from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import (
    AgentSession,
    AgentState,
    Command,
    InvocationProtocol,
    configured_invocation_protocol,
    effective_invocation_protocol,
)


def _agent(**kwargs) -> AgentSession:
    return AgentSession(id="a", project_id="p", role_id="explorer", display_name="explorer", **kwargs)


def test_protocol_is_frozen_only_on_run_start():
    agent = _agent()
    agent.settings.invocation_protocol = InvocationProtocol.JAVASCRIPT
    _, drafts = plan_start_run(agent)
    started = next(d for d in drafts if d.type == "run.started")
    assert started.data["invocation_protocol"] == "javascript"
    assert "api_key" not in started.data


async def _spawn_agent(core: RuntimeCore):
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    return project, next(iter(core.agents.values()))


def _run_started_events(core: RuntimeCore, agent_id: str):
    return [e for e in core.event_log.query_session(agent_id) if e.type == "run.started"]


@pytest.mark.asyncio
async def test_javascript_is_the_default_protocol():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    assert configured_invocation_protocol(agent) is InvocationProtocol.JAVASCRIPT
    assert effective_invocation_protocol(agent) is InvocationProtocol.JAVASCRIPT
    bus = CommandBus(core)
    await bus.execute(
        Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "hi"})
    )
    started = _run_started_events(core, agent.id)[-1]
    assert started.data["invocation_protocol"] == "javascript"
    assert started.data["settings_summary"]["invocation_protocol"] == "javascript"
    assert "api_key" not in started.data
    assert agent.current_run.invocation_protocol is InvocationProtocol.JAVASCRIPT


@pytest.mark.asyncio
async def test_unknown_protocol_value_is_rejected():
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn_agent(core)
    with pytest.raises(ValidationError):
        await CommandBus(core).execute(
            Command(
                type="agent.settings_update",
                target={"session_id": agent.id},
                payload={"invocation_protocol": "cobol"},
            )
        )


@pytest.mark.asyncio
async def test_protocol_frozen_for_run_and_applied_on_next_run():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    _, agent = await _spawn_agent(core)
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"invocation_protocol": "javascript"},
        )
    )
    await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "go"}))
    assert _run_started_events(core, agent.id)[-1].data["invocation_protocol"] == "javascript"
    assert agent.current_run.invocation_protocol is InvocationProtocol.JAVASCRIPT
    assert effective_invocation_protocol(agent) is InvocationProtocol.JAVASCRIPT

    # Changing the setting mid-run must not touch the active run.
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"invocation_protocol": "traditional"},
        )
    )
    assert configured_invocation_protocol(agent) is InvocationProtocol.TRADITIONAL
    assert effective_invocation_protocol(agent) is InvocationProtocol.JAVASCRIPT
    assert agent.current_run.invocation_protocol is InvocationProtocol.JAVASCRIPT

    # Finish the run; the next run picks up the configured value.
    core.agent_host.finish_run(agent, outcome="succeeded")
    assert agent.current_run is None
    assert effective_invocation_protocol(agent) is InvocationProtocol.TRADITIONAL
    await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "again"}))
    assert _run_started_events(core, agent.id)[-1].data["invocation_protocol"] == "traditional"
    assert agent.current_run.invocation_protocol is InvocationProtocol.TRADITIONAL


@pytest.mark.asyncio
async def test_waiting_resume_keeps_the_frozen_protocol():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    _, agent = await _spawn_agent(core)
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"invocation_protocol": "javascript"},
        )
    )
    await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "go"}))
    run_id = agent.current_run.run_id
    core.agent_host.transition(agent, AgentState.WAITING_INPUT, reason="ask_user", run_id=run_id)
    started_before = len(_run_started_events(core, agent.id))
    await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "answer"}))
    # Resume opens no new run, so the frozen protocol is untouched.
    assert len(_run_started_events(core, agent.id)) == started_before
    assert agent.current_run.run_id == run_id
    assert agent.current_run.invocation_protocol is InvocationProtocol.JAVASCRIPT
    assert effective_invocation_protocol(agent) is InvocationProtocol.JAVASCRIPT


@pytest.mark.asyncio
async def test_replay_keeps_the_frozen_protocol():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    _, agent = await _spawn_agent(core)
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"invocation_protocol": "javascript"},
        )
    )
    await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "go"}))
    assert agent.current_run.invocation_protocol is InvocationProtocol.JAVASCRIPT

    replayed = RuntimeCore(strict_events=True)
    for envelope in core.event_log:
        replayed.event_log.restore([envelope])
        apply_event(replayed, envelope)
    twin = replayed.agents[agent.id]
    assert twin.current_run is not None
    assert twin.current_run.invocation_protocol is InvocationProtocol.JAVASCRIPT
    assert effective_invocation_protocol(twin) is InvocationProtocol.JAVASCRIPT


@pytest.mark.asyncio
async def test_snapshot_roundtrip_keeps_the_frozen_protocol(tmp_path):
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    _, agent = await _spawn_agent(core)
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"invocation_protocol": "javascript"},
        )
    )
    await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "go"}))

    store = RuntimeStore(tmp_path / "runtime.db")
    for envelope in core.event_log:
        store.append_event(envelope)
    store.save_snapshot(
        projects=core.projects,
        agents=core.agents,
        roles=core.roles._roles,
        runtime_defaults=core.runtime_defaults,
        last_seqs=core.event_log.high_watermarks,
    )
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, store)
    twin = restored.agents[agent.id]
    # Restore finalizes zombie running agents as failed; the frozen protocol
    # must survive in the replayed run.started history.
    assert twin.state is AgentState.FAILED
    started = [e for e in restored.event_log.query_session(agent.id) if e.type == "run.started"]
    assert started[-1].data["invocation_protocol"] == "javascript"
