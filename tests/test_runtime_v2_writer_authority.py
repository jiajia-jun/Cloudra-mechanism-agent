"""Durable producers share the runtime writer; hub observers never write again."""

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.email_listener import EmailListenerBroker
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import AgentSession, Command, Project
from cloudra.runtime_v2.turn_pipeline import TurnPipeline
from cloudra.services.api_v2.app import create_v2_app


@pytest.mark.asyncio
async def test_api_does_not_persist_the_same_event_from_its_hub(tmp_path, monkeypatch):
    core = RuntimeCore(strict_events=True)
    create_v2_app(core, store_path=str(tmp_path / "runtime.db"))
    writes = []
    append = core.store.append_event

    def counted(envelope):
        writes.append(envelope.event_id)
        append(envelope)

    monkeypatch.setattr(core.store, "append_event", counted)
    await CommandBus(core).execute(Command(type="project.create", payload={"name": "one write"}))
    assert len(writes) == len(set(writes)) == len(core.event_log)
    await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("producer", ["email", "narration"])
@pytest.mark.parametrize("fails", [False, True])
async def test_durable_producers_persist_before_publication(tmp_path, monkeypatch, producer, fails):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="writer")
    core.agents["a"] = AgentSession(id="a", project_id="p", role_id="coordinator", display_name="a")
    core.store = RuntimeStore(tmp_path / "runtime.db")
    published = []

    async def observe(event):
        published.append((event.type, core.store.has_event(event.event_id)))

    core.event_hub.subscribe(observe)
    if fails:
        def fail(_event):
            raise OSError("disk full")
        monkeypatch.setattr(core.store, "append_event", fail)

    async def emit():
        if producer == "email":
            await EmailListenerBroker(core)._deliver(sender="boss@example.com", subject="test", date="today", body="hi")
        else:
            pipeline = TurnPipeline(event_log=core.event_log, event_writer=core.event_writer,
                                    event_hub=core.event_hub, stages=[], llm=None, tools=None)
            await pipeline._publish(core.event_log.append("agent.thinking", stream="agent",
                                    project_id="p", session_id="a", data={"content": "thinking"}))

    if fails:
        with pytest.raises(EventPersistenceError):
            await emit()
        assert published == []
    else:
        await emit()
        assert published
        assert all(durable for _, durable in published)
    await core.aclose()


@pytest.mark.asyncio
async def test_snapshot_from_hub_observer_captures_applied_command(tmp_path):
    from cloudra.runtime_v2.persistence import restore_core

    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    bus = CommandBus(core)

    async def snapshot_at_publication(event):
        if event.type == "project.created":
            await bus.flush_snapshot()

    core.event_hub.subscribe(snapshot_at_publication)
    result = await bus.execute(Command(type="project.create", payload={"name": "keep project"}))
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, core.store)
    assert result.data.id in restored.projects
    await core.aclose()
    await restored.aclose()


@pytest.mark.asyncio
async def test_snapshot_persists_notice_appended_by_flush_subscriber(tmp_path):
    from cloudra.runtime_v2.persistence import restore_core

    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    core.projects["p"] = Project(id="p", name="notice")
    core.agents["a"] = AgentSession(id="a", project_id="p", role_id="coordinator", display_name="a")

    async def add_notice(event):
        if event.type == "agent.warning":
            core.notices.pin("a", "note", "keep notice")

    core.event_hub.subscribe(add_notice)
    core.record("agent.warning", stream="agent", project_id="p", session_id="a", data={"message": "warning"})
    await CommandBus(core).flush_snapshot()
    snapshot, marks = core.store.load_snapshot()
    notice = core.event_log.query_session("a", types={"context.pin_set"})[-1]
    assert core.store.has_event(notice.event_id)
    assert marks["p"] >= notice.seq
    assert snapshot["notices"]["pins"]["a"]["note"] == "keep notice"
    restored = RuntimeCore(strict_events=True)
    restore_core(restored, core.store)
    assert restored.notices.pin_content("a", "note") == "keep notice"
    await core.aclose()
    await restored.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("binding", ["api", "runner"])
async def test_injected_pipeline_uses_the_owning_core_writer_when_store_attaches_later(tmp_path, binding):
    import asyncio

    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.events import EventHub, EventLog

    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="injected pipeline")
    # The API case reproduces the public same-log/default-writer injection.
    # A separately constructed runner also takes ownership of its pipeline log/hub.
    pipeline = TurnPipeline(event_log=core.event_log if binding == "api" else EventLog(strict=True),
                            event_hub=core.event_hub if binding == "api" else EventHub(),
                            stages=[], llm=None, tools=None)
    if binding == "api":
        create_v2_app(core, pipeline=pipeline, store_path=str(tmp_path / "runtime.db"))
    else:
        core.runner = AgentRunner(core, pipeline)
        core.store = RuntimeStore(tmp_path / "runtime.db")
    seen = []

    async def observe(event):
        seen.append((event.event_id, await asyncio.to_thread(core.store.has_event, event.event_id)))

    core.event_hub.subscribe(observe)
    event = pipeline.event_log.append("agent.thinking", stream="agent", project_id="p", data={"content": "visible only after disk"})
    await pipeline._publish(event)
    assert seen == [(event.event_id, True)]
    assert pipeline.event_log is core.event_log
    assert pipeline.event_hub is core.event_hub
    assert pipeline.event_writer is core.event_writer
    assert pipeline.invocations.event_writer is core.event_writer
    assert pipeline.js_runtime.event_writer is core.event_writer
    await core.aclose()
