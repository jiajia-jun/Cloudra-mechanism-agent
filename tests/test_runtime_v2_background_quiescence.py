"""A guided delivery wait resumes when the project's last background work settles."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from cloudra.dag.stop_audit import has_running_siblings
from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import Command


async def _setup(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    # We exercise the event-driven runner hook without starting an LLM task.
    runner = AgentRunner(core, pipeline=None)
    runner.schedule = lambda _session_id: None
    core.runner = runner
    bus = CommandBus(core)
    project = (await bus.execute(Command(
        type="project.create", payload={"name": "background-quiescence"},
    ))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator", "settings": {"orchestration_mode": "dag_guided"}},
    ))).data
    return core, runner, bus, project, parent


async def _spawn(bus, project, role, *, parent=None):
    return (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": role, **({"parent_session_id": parent.id} if parent else {})},
    ))).data


async def _finish(core, agent, action, *, source="dag"):
    run_id = await core.agent_host.start_run(agent)
    await core.event_writer.commit(EventDraft(
        "agent.completion_gate", stream="agent", project_id=agent.project_id,
        session_id=agent.id, run_id=run_id,
        data={"action": action, "source": source, "reason": "test"},
    ))
    await core.agent_host.finish_run(agent, outcome="succeeded")
    return run_id


def _notices(core, parent, kind):
    return [
        event for event in core.event_log.query_session(
            parent.id, types={"agent.message_injected"}, limit=1000,
        )
        if (event.data.get("manifest") or {}).get("kind") == kind
    ]


@pytest.mark.asyncio
async def test_guided_parent_wakes_after_previously_reported_child_and_supervisor_settle(tmp_path):
    core, runner, bus, project, parent = await _setup(tmp_path)
    child = await _spawn(bus, project, "explorer", parent=parent)
    supervisor = await _spawn(bus, project, "supervisor")

    await _finish(core, child, "allow_final", source="declared")
    await runner._deliver_completion(child)
    assert len(_notices(core, parent, "child_completion")) == 1
    core.mailbox.inbox(parent.id).get_nowait()
    await core.agent_host.finish_run(parent, outcome="succeeded")

    await core.agent_host.start_run(child)
    await core.agent_host.start_run(supervisor)
    parked_run = await _finish(core, parent, "wait_background")
    assert parent.state.value == "succeeded"

    await core.agent_host.finish_run(child, outcome="succeeded")
    await runner._deliver_completion(child)
    assert parent.state.value == "succeeded", "supervisor still running"
    assert len(_notices(core, parent, "child_completion")) == 1

    await core.agent_host.finish_run(supervisor, outcome="succeeded")
    await runner._deliver_completion(supervisor)
    assert parent.state.value == "running"
    notices = _notices(core, parent, "background_quiescence")
    assert len(notices) == 1
    assert notices[0].data["manifest"]["parked_run_id"] == parked_run
    assert core.mailbox.inbox(parent.id).get_nowait()["content"].startswith(
        "[Background work settled]"
    )

    await asyncio.gather(
        runner.maybe_wake_parked_delivery(project.id),
        runner.maybe_wake_parked_delivery(project.id),
    )
    assert len(_notices(core, parent, "background_quiescence")) == 1
    restored = RuntimeCore(strict_events=True)
    restored.store = core.store
    restore_core(restored, restored.store)
    assert len(_notices(restored, restored.agents[parent.id], "background_quiescence")) == 1


@pytest.mark.asyncio
async def test_unnotified_terminal_compute_blocks_quiescence_until_broker_delivers(tmp_path):
    core, runner, _bus, project, parent = await _setup(tmp_path)
    await _finish(core, parent, "wait_background")
    def insert_job():
        db = ComputeDB().init()
        with db.connect() as con:
            cur = con.execute(
                """INSERT INTO compute_jobs
                (conversation_id, session_id, path, state, jobtype,
                 start_timestamp, end_timestamp, scheduler, scheduler_options)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (project.id, parent.id, str(tmp_path / "job.gjf"), "done", "gaussian",
                 time.time() - 10, time.time(), "local", json.dumps({"type": "local"})),
            )
            con.commit()
            return int(cur.lastrowid)

    job_id = await asyncio.to_thread(insert_job)

    await runner.maybe_wake_parked_delivery(project.id)
    assert parent.state.value == "succeeded"
    assert not _notices(core, parent, "background_quiescence")

    await ComputeNotifyBroker(core)._poll_project(project.id)
    def read_notified_at():
        with ComputeDB().connect() as con:
            return con.execute(
                "SELECT notified_at FROM compute_jobs WHERE id=?", (job_id,),
            ).fetchone()[0]

    notified_at = await asyncio.to_thread(read_notified_at)
    assert notified_at is not None
    assert parent.state.value == "running"
    assert len(_notices(core, parent, "background_quiescence")) == 1


@pytest.mark.asyncio
async def test_parked_child_is_unfinished_background_work(tmp_path):
    core, runner, bus, project, parent = await _setup(tmp_path)
    child = await _spawn(bus, project, "explorer", parent=parent)
    await _finish(core, child, "wait_background")
    await _finish(core, parent, "wait_background")
    assert has_running_siblings(core, project_id=project.id, session_id=parent.id)
    assert not has_running_siblings(
        core, project_id=project.id, session_id=child.id,
    ), "a parked parent cannot keep its child waiting"

    await runner.maybe_wake_parked_delivery(project.id)
    assert parent.state.value == "succeeded"
    assert not _notices(core, parent, "background_quiescence")


@pytest.mark.asyncio
async def test_running_parent_does_not_hold_its_child_open(tmp_path):
    core, _runner, bus, project, parent = await _setup(tmp_path)
    child = await _spawn(bus, project, "explorer", parent=parent)
    await core.agent_host.start_run(parent)

    assert not has_running_siblings(
        core, project_id=project.id, session_id=child.id,
    )
    assert has_running_siblings(
        core, project_id=project.id, session_id=parent.id,
    )


@pytest.mark.asyncio
async def test_queued_group_item_blocks_delivery_between_child_runs(tmp_path):
    core, runner, bus, project, parent = await _setup(tmp_path)
    child = await _spawn(bus, project, "explorer", parent=parent)
    await _finish(core, child, "allow_final", source="declared")
    await runner._deliver_completion(child)
    core.mailbox.inbox(parent.id).get_nowait()
    await core.agent_host.finish_run(parent, outcome="succeeded")

    group_id = "grp_quiescence"
    async def group_event(type_, data):
        event = await core.event_writer.commit(EventDraft(
            type_, stream="project", project_id=project.id,
            session_id=parent.id, data={"group_id": group_id, **data},
        ))
        apply_event(core, event)

    await group_event("launch_group.created", {
        "parent_session_id": parent.id,
        "max_concurrency": 1,
        "items": [
            {"item_id": "first", "query": "a"},
            {"item_id": "queued", "query": "b"},
        ],
    })
    await group_event("launch_group.item_dispatched", {
        "item_id": "first", "child_session_id": child.id,
    })
    await _finish(core, parent, "wait_background")
    await _finish(core, child, "allow_final", source="declared")
    await runner._deliver_completion(child)
    await group_event("launch_group.item_finished", {
        "item_id": "first", "state": "succeeded", "error": "",
    })

    assert has_running_siblings(core, project_id=project.id, session_id=parent.id)
    await runner.maybe_wake_parked_delivery(project.id)
    assert parent.state.value == "succeeded"
    assert not _notices(core, parent, "background_quiescence")

    await group_event("launch_group.item_finished", {
        "item_id": "queued", "state": "failed", "error": "dispatch failed",
    })
    await group_event("launch_group.finished", {"state": "finished", "reason": ""})
    # The group worker invokes this hook when it closes the group.
    await runner.maybe_wake_parked_delivery(project.id)
    assert parent.state.value == "running"
    assert len(_notices(core, parent, "background_quiescence")) == 1


@pytest.mark.asyncio
async def test_launch_group_close_triggers_quiescence_without_polling(tmp_path):
    core, _runner, _bus, project, parent = await _setup(tmp_path)
    await _finish(core, parent, "wait_background")
    group = await core.launch_groups.create(
        group_id="grp_empty", parent_session_id=parent.id,
        items=[], max_concurrency=1, project_id=project.id,
    )
    await group._task

    assert group.state == "finished"
    assert parent.state.value == "running"
    assert len(_notices(core, parent, "background_quiescence")) == 1


@pytest.mark.asyncio
async def test_durable_quiescence_marker_recovers_wake_without_second_message(tmp_path):
    core, runner, _bus, project, parent = await _setup(tmp_path)
    parked_run = await _finish(core, parent, "wait_background")
    await core.event_writer.commit(EventDraft(
        "agent.message_injected", stream="project", project_id=project.id,
        session_id=parent.id,
        data={
            "message_id": "msg_quiescence",
            "sender": "background_quiescence",
            "content": "[Background work settled] Recheck delivery.",
            "manifest": {
                "kind": "background_quiescence",
                "parked_run_id": parked_run,
            },
        },
    ))

    def set_compute_notice(notified: bool):
        db = ComputeDB().init()
        with db.connect() as con:
            if not notified:
                con.execute(
                    """INSERT INTO compute_jobs
                    (conversation_id, session_id, path, state, jobtype,
                     start_timestamp, end_timestamp, scheduler, scheduler_options)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (project.id, parent.id, str(tmp_path / "job.gjf"), "done", "gaussian",
                     time.time() - 10, time.time(), "local", json.dumps({"type": "local"})),
                )
            else:
                con.execute(
                    "UPDATE compute_jobs SET notified_at=? WHERE conversation_id=?",
                    (time.time(), project.id),
                )
            con.commit()

    await asyncio.to_thread(set_compute_notice, False)
    await runner.maybe_wake_parked_delivery(project.id)
    assert parent.state.value == "succeeded", "undelivered compute still blocks wake"
    await asyncio.to_thread(set_compute_notice, True)

    await runner.maybe_wake_parked_delivery(project.id)

    assert parent.state.value == "running"
    assert len(_notices(core, parent, "background_quiescence")) == 1
    assert core.mailbox.inbox(parent.id).get_nowait()["message_id"] == "msg_quiescence"
