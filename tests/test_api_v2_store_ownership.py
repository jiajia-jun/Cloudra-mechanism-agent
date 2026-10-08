"""Different ports must not create two authoritative runtimes over one event DB."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2.app import create_default_v2_app


@pytest.mark.asyncio
async def test_same_runtime_store_refuses_second_service_and_releases_on_shutdown(tmp_path):
    store = str(tmp_path / "runtime.db")
    first = await asyncio.to_thread(create_default_v2_app, store_path=store)
    async with first.router.lifespan_context(first):
        with pytest.raises(RuntimeError, match="already in use"):
            await asyncio.to_thread(create_default_v2_app, store_path=store)
        other = await asyncio.to_thread(create_default_v2_app, store_path=str(tmp_path / "other.db"))
        async with other.router.lifespan_context(other):
            assert other.state.runtime_core is not first.state.runtime_core
    replacement = await asyncio.to_thread(create_default_v2_app, store_path=store)
    async with replacement.router.lifespan_context(replacement):
        assert replacement.state.runtime_core is not first.state.runtime_core


@pytest.mark.asyncio
async def test_store_ownership_released_when_startup_fails(tmp_path):
    store = str(tmp_path / "runtime.db")
    app = await asyncio.to_thread(create_default_v2_app, store_path=store)

    @asynccontextmanager
    async def failing_start(*args):
        raise RuntimeError("startup probe failed")
        yield  # pragma: no cover

    # Failure in a real startup dependency must release ownership too.
    async def rearm_failure():
        async with failing_start():
            pass

    app.state.runtime_core.reminders.rearm_all = rearm_failure
    with pytest.raises(RuntimeError, match="startup probe failed"):
        async with app.router.lifespan_context(app):
            pass
    replacement = await asyncio.to_thread(create_default_v2_app, store_path=store)
    async with replacement.router.lifespan_context(replacement):
        assert replacement.state.runtime_core is not app.state.runtime_core


@pytest.mark.asyncio
async def test_partial_startup_closes_started_reminder_before_unlocking_store(tmp_path):
    store = str(tmp_path / "runtime.db")
    app = await asyncio.to_thread(create_default_v2_app, store_path=store)
    core = app.state.runtime_core
    bus = CommandBus(core)
    project = (await bus.execute(Command(
        type="project.create", payload={"name": "startup", "workspace_dir": str(tmp_path)},
    ))).data
    agent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "explorer"},
    ))).data
    wake = datetime.now(timezone.utc) + timedelta(hours=1)
    await core.event_writer.commit(EventDraft(
        "reminder.scheduled", "agent", project.id, session_id=agent.id,
        data={"message": "future reminder", "wake_at": wake.isoformat(), "wake_ts": wake.timestamp()},
    ))
    armed = []

    async def fail_after_reminders():
        armed.extend(task for tasks in core.reminders._timers.values() for task in tasks)
        assert armed and all(not task.done() for task in armed)
        raise RuntimeError("email startup failed")

    core.email_listener.start = fail_after_reminders
    try:
        with pytest.raises(RuntimeError, match="email startup failed"):
            async with app.router.lifespan_context(app):
                pass
        assert all(task.done() for task in armed), "old reminder writers survive after ownership unlock"
        assert not core.reminders._timers
        replacement = await asyncio.to_thread(create_default_v2_app, store_path=store)
        async with replacement.router.lifespan_context(replacement):
            assert replacement.state.runtime_core is not core
    finally:
        await core.reminders.close()


@pytest.mark.asyncio
async def test_closed_runtime_cannot_reenter_lifespan_without_ownership(tmp_path):
    store = str(tmp_path / "runtime.db")
    app = await asyncio.to_thread(create_default_v2_app, store_path=store)
    async with app.router.lifespan_context(app):
        pass
    replacement = await asyncio.to_thread(create_default_v2_app, store_path=store)
    async with replacement.router.lifespan_context(replacement):
        with pytest.raises(RuntimeError, match="already closed"):
            async with app.router.lifespan_context(app):
                pass
