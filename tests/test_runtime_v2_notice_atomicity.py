"""A persisted notice is either pending or present in context, never lost."""

import asyncio

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import Command


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_context_write", [True, False])
async def test_notice_body_and_consumption_survive_same_durable_boundary(
    tmp_path, monkeypatch, fail_context_write
):
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "atomic"}))
    project = next(iter(core.projects.values()))
    agent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator"},
    ))).data
    core.notices.push(agent.id, "Do not discard this user correction")
    core.notices.collect_batch(agent.id, fresh=False)
    append_event = store.append_event

    def write(event):
        if fail_context_write and event.type == "context.appended":
            raise OSError("simulated disk failure before context body")
        append_event(event)

    monkeypatch.setattr(store, "append_event", write)
    commit = core.contexts.commit_input(
        agent=agent, run_id="run-test", context_prefix=None,
        notices=core.notices, user_messages=[],
    )
    if fail_context_write:
        with pytest.raises(EventPersistenceError):
            await commit
    else:
        await commit

    restored = RuntimeCore(strict_events=True)
    await asyncio.to_thread(restore_core, restored, store)
    messages = restored.contexts.current_messages(agent.id)
    pending = restored.notices.collect_batch(agent.id, fresh=False)
    contents = [m["content"] for m in [*messages, *pending]]
    assert contents == ["Do not discard this user correction"]
    assert bool(pending) is fail_context_write
