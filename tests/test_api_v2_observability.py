"""User-visible tool receipts and activity, without LLM or compute processes."""

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentSession, AgentState, CurrentRun, Project, utc_now
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.compute_store import insert_compute_job


def setup_core():
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="project")
    core.projects["other"] = Project(id="other", name="other")
    for sid, pid in [("a", "p"), ("b", "p"), ("foreign", "other")]:
        core.agents[sid] = AgentSession(
            id=sid,
            project_id=pid,
            role_id="explorer",
            display_name=sid,
            state="running",
            current_run=CurrentRun(run_id="r", started_at=utc_now()),
        )
    return core


def emit(core, kind, data, *, session="a", run="r"):
    return core.event_log.append(
        kind,
        stream="agent",
        project_id=core.agents[session].project_id,
        session_id=session,
        run_id=run,
        data=data,
    )


def request(core, call="same", *, session="a", run="r", arguments=None, name="echo"):
    return emit(
        core,
        "tool.requested",
        {
            "tool_call_id": call,
            "tool_name": name,
            "arguments_summary": arguments or {"nested": {"value": "x" * 12000}},
            "execution_id": "js1",
        },
        session=session,
        run=run,
    )


def client_for(core):
    return AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver")


@pytest.mark.asyncio
async def test_detail_keeps_full_arguments_raw_result_and_postprocessing_error():
    core = setup_core()
    req = request(core)
    emit(core, "tool.started", {"tool_call_id": "same"})
    raw = emit(
        core,
        "tool.result_recorded",
        {
            "tool_call_id": "same",
            "result": {"is_success": True, "data": {"text": "y" * 14000}},
        },
    )
    emit(
        core,
        "tool.finished",
        {
            "tool_call_id": "same",
            "status": "failed",
            "is_success": True,
            "effect_state": "completed",
            "result_summary": "short",
            "raw_result_event_id": raw.event_id,
            "error": {"code": "postprocessing_failed", "message": "cannot register artifact"},
        },
    )
    async with client_for(core) as client:
        response = await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")
        assert response.status_code == 200
        row = response.json()
        assert row["arguments"]["nested"]["value"] == "x" * 12000
        assert row["result"]["data"]["text"] == "y" * 14000
        assert row["result_availability"] == "available"
        assert row["status"] == "failed" and row["effect_state"] == "completed"
        assert row["error"]["code"] == "postprocessing_failed"
        assert row["raw_result_event_id"] == raw.event_id
        assert (await client.get(f"/api/v2/agents/b/tool-calls/{req.event_id}")).status_code == 404


@pytest.mark.asyncio
async def test_reused_call_ids_remain_separate_and_pagination_counts_calls():
    core = setup_core()
    first = request(core)
    emit(core, "tool.finished", {"tool_call_id": "same", "status": "blocked"})
    second = request(core)
    emit(core, "tool.finished", {"tool_call_id": "same", "status": "completed"})
    third = request(core, run="r2")
    for i in range(20):
        emit(core, "agent.message_emitted", {"content": str(i)}, run="r2")
    async with client_for(core) as client:
        rows = (await client.get("/api/v2/agents/a/tool-calls", params={"limit": 2})).json()
        assert [x["request_event_id"] for x in rows["items"]] == [third.event_id, second.event_id]
        assert "result" not in rows["items"][0]
        older = (
            await client.get(
                "/api/v2/agents/a/tool-calls",
                params={
                    "limit": 2,
                    "before": rows["next_before"],
                },
            )
        ).json()
        assert [x["request_event_id"] for x in older["items"]] == [first.event_id]
        assert older["next_before"] is None
        assert older["items"][0]["status"] == "blocked"


@pytest.mark.asyncio
async def test_ended_run_closes_unfinished_call_without_claiming_effect_failed():
    core = setup_core()
    req = request(core)
    emit(core, "tool.started", {"tool_call_id": "same"})
    emit(core, "run.finished", {"outcome": "failed"})
    # Another run using the same wire ID must never supply the old raw result.
    request(core, run="new")
    emit(core, "tool.result_recorded", {"tool_call_id": "same", "result": {"data": 99}}, run="new")
    async with client_for(core) as client:
        row = (await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")).json()
        assert row["status"] == "interrupted"
        assert row["effect_state"] == "unknown"
        assert row["result"] is None
        assert row["result_availability"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["queued", "waiting", "postprocessing"])
async def test_interrupted_run_projection_is_read_only_and_scoped_to_its_run(tmp_path, stage):
    import asyncio

    from cloudra.runtime_v2.persistence import RuntimeStore

    core = setup_core()
    core.store = await asyncio.to_thread(RuntimeStore, tmp_path / "runtime.db")
    req = request(core)
    if stage == "waiting":
        emit(core, "tool.approval_requested", {"tool_call_id": "same", "message": "approval"})
    elif stage == "postprocessing":
        emit(core, "tool.started", {"tool_call_id": "same"})
        emit(core, "tool.result_recorded", {"tool_call_id": "same", "result": {"data": 42}})
    terminal = emit(core, "run.finished", {"outcome": "failed", "failure_kind": "runtime_interrupted"})
    emit(core, "run.started", {}, run="new")
    active = request(core, run="new")
    emit(core, "tool.started", {"tool_call_id": "same"}, run="new")
    core.agents["a"].current_run = CurrentRun(run_id="new", started_at=utc_now())
    await core.event_writer.flush()
    persisted = await asyncio.to_thread(lambda: list(core.store.iter_events()))

    async with client_for(core) as client:
        row = (await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")).json()
        assert row["status"] == "interrupted"
        assert row["effect_state"] == "unknown"
        assert row["finished_at"] == terminal.created_at.isoformat()
        assert row["waits"] == []
        if stage == "postprocessing":
            assert row["result"] == {"data": 42}
            assert row["result_availability"] == "available"
        else:
            assert row["result_availability"] == "unavailable"
        rows = (await client.get("/api/v2/agents/a/tool-calls")).json()["items"]
        assert [(r["request_event_id"], r["status"]) for r in rows] == [
            (active.event_id, "running"), (req.event_id, "interrupted"),
        ]
        activity = (await client.get("/api/v2/projects/p/activity")).json()["agents"][0]
        assert activity["activity"] == "running_tool"
        assert [r["request_event_id"] for r in activity["active_calls"]] == [active.event_id]

    await core.event_writer.flush()
    assert await asyncio.to_thread(lambda: list(core.event_log)) == persisted
    assert await asyncio.to_thread(lambda: list(core.store.iter_events())) == persisted


@pytest.mark.asyncio
async def test_job_links_use_structured_results_and_never_leak_other_projects():
    core = setup_core()
    db = await ComputeDB().ainit()
    import asyncio

    def add(pid):
        return insert_compute_job(
            db,
            conversation_id=pid,
            session_id="a",
            node_id="node-a",
            path="/tmp/input.inp",
            state="running",
            jobtype="orca",
        )

    own = await asyncio.to_thread(add, "p")
    foreign = await asyncio.to_thread(add, "other")
    req = request(core, name="submit_compute_job")
    emit(
        core,
        "tool.result_recorded",
        {
            "tool_call_id": "same",
            "result": {"data": {"job_id": own, "is_success": True}},
        },
    )
    emit(core, "tool.finished", {"tool_call_id": "same", "status": "completed", "is_success": True})
    bad = request(core, call="foreign", name="submit_compute_job")
    emit(
        core,
        "tool.result_recorded",
        {
            "tool_call_id": "foreign",
            "result": {"data": {"job_id": foreign}},
        },
    )
    async with client_for(core) as client:
        row = (await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")).json()
        assert row["status"] == "completed"
        assert row["compute_jobs"][0]["state"] == "running"
        assert row["compute_jobs"][0]["id"] == own
        bad_row = (await client.get(f"/api/v2/agents/a/tool-calls/{bad.event_id}")).json()
        assert bad_row["compute_jobs"] == []
        assert bad_row["unavailable_compute_job_ids"] == [foreign]
        assert (await client.get(f"/api/v2/projects/p/compute/jobs/{foreign}")).status_code == 404
        assert (await client.get(f"/api/v2/projects/p/compute/jobs/{own}")).json()["id"] == own


@pytest.mark.asyncio
async def test_activity_shows_all_parallel_calls_and_does_not_invent_wait_causes():
    core = setup_core()
    first = request(core, call="one")
    second = request(core, call="two")
    request(core, call="hidden", session="foreign")
    emit(core, "tool.started", {"tool_call_id": "one"})
    emit(core, "tool.started", {"tool_call_id": "two"})
    async with client_for(core) as client:
        response = await client.get("/api/v2/projects/p/activity")
        assert response.status_code == 200
        body = response.json()
        assert body["as_of_seq"] == core.event_log.high_watermarks["p"]
        assert {x["session_id"] for x in body["agents"]} == {"a", "b"}
        a, b = body["agents"]
        assert {x["request_event_id"] for x in a["active_calls"]} == {first.event_id, second.event_id}
        assert a["activity"] == "running_tool"
        assert b["activity"] == "unknown"
        assert b["waits"] == []
        assert (await client.get("/api/v2/projects/missing/activity")).status_code == 404


@pytest.mark.asyncio
async def test_missing_raw_reference_is_explicit_and_cannot_borrow_foreign_data():
    core = setup_core()
    req = request(core)
    other = emit(
        core,
        "tool.result_recorded",
        {
            "tool_call_id": "same",
            "result": {"data": "secret"},
        },
        session="foreign",
    )
    emit(
        core,
        "tool.finished",
        {
            "tool_call_id": "same",
            "status": "completed",
            "raw_result_event_id": other.event_id,
        },
    )
    async with client_for(core) as client:
        row = (await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")).json()
        assert row["result"] is None
        assert row["result_availability"] == "unavailable"


@pytest.mark.asyncio
async def test_progress_waits_are_replayable_and_approval_resolution_clears_them():
    core = setup_core()
    req = request(core)
    emit(core, "tool.started", {"tool_call_id": "same"})
    emit(
        core,
        "tool.progress",
        {
            "request_event_id": req.event_id,
            "tool_call_id": "same",
            "phase": "waiting",
            "effective_arguments": {"cpus": 4},
            "waits": [{"kind": "agent", "target_id": "b"}],
        },
    )
    async with client_for(core) as client:
        a = (await client.get("/api/v2/projects/p/activity")).json()["agents"][0]
        assert a["activity"] == "waiting"
        assert a["waits"][0]["target_id"] == "b"
    emit(core, "approval.requested", {"tool_call_id": "same", "approval_id": "apv"})
    emit(core, "approval.decided", {"approval_id": "apv", "decision": "approved"})
    restored = setup_core()
    restored.event_log.restore(list(core.event_log))
    async with client_for(restored) as client:
        row = (await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")).json()
        assert row["effective_arguments"] == {"cpus": 4}
        assert row["status"] == "running"
        assert row["waits"] == []


@pytest.mark.asyncio
async def test_background_gate_is_waiting_not_idle_and_ts_jobs_are_linked():
    core = setup_core()
    req = request(core, name="ts_prepare")
    emit(
        core,
        "tool.result_recorded",
        {
            "tool_call_id": "same",
            "result": {
                "data": {
                    "run_id": "ts-run",
                    "status": "waiting",
                    "stage": "ts_opt",
                    "waiting_for": [{"job_id": 42, "state": "ready"}],
                    "usage": {"jobs": [{"job_id": 41}, {"job_id": 42}]},
                    "result": {"verified": False},
                }
            },
        },
    )
    emit(core, "tool.finished", {"tool_call_id": "same", "status": "completed", "is_success": True})
    emit(core, "agent.completion_gate", {"action": "wait_background", "basis": "background_wait"})
    emit(core, "run.finished", {"outcome": "succeeded"})
    core.agents["a"].current_run = None
    core.agents["a"].state = AgentState.SUCCEEDED
    async with client_for(core) as client:
        row = (await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")).json()
        assert row["compute_job_ids"] == [41, 42]
        assert row["result"]["data"]["result"]["verified"] is False
        a = (await client.get("/api/v2/projects/p/activity")).json()["agents"][0]
        assert a["activity"] == "waiting_background"
        assert a["last_completion_gate"]["data"]["basis"] == "background_wait"


@pytest.mark.asyncio
async def test_explicit_attempt_identity_handles_overlapping_reused_wire_ids():
    core = setup_core()
    first = request(core, arguments={"value": 1})
    second = request(core, arguments={"value": 2})
    emit(
        core,
        "tool.result_recorded",
        {
            "tool_call_id": "same",
            "request_event_id": first.event_id,
            "result": {"data": {"value": 1}},
        },
    )
    emit(
        core,
        "tool.finished",
        {
            "tool_call_id": "same",
            "request_event_id": first.event_id,
            "status": "completed",
        },
    )
    async with client_for(core) as client:
        a = (await client.get(f"/api/v2/agents/a/tool-calls/{first.event_id}")).json()
        b = (await client.get(f"/api/v2/agents/a/tool-calls/{second.event_id}")).json()
        assert a["result"]["data"] == {"value": 1}
        assert a["status"] == "completed"
        assert b["result"] is None and b["status"] == "queued"


@pytest.mark.asyncio
async def test_background_wait_exposes_reminder_and_active_job_sources():
    import asyncio

    core = setup_core()
    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(
        insert_compute_job,
        db,
        conversation_id="p",
        session_id="a",
        node_id="node-a",
        path="/tmp/input.inp",
        state="ready",
        jobtype="orca",
    )
    reminder = emit(
        core,
        "reminder.scheduled",
        {
            "message": "check",
            "wake_at": "2099-01-01T00:00:00+00:00",
            "wake_ts": 4070908800,
        },
    )
    emit(core, "agent.completion_gate", {"action": "wait_background", "basis": "background_wait"})
    emit(core, "run.finished", {"outcome": "succeeded"})
    core.agents["a"].current_run = None
    core.agents["a"].state = AgentState.SUCCEEDED
    async with client_for(core) as client:
        a = (await client.get("/api/v2/projects/p/activity")).json()["agents"][0]
        assert {(w["kind"], w["target_id"]) for w in a["waits"]} == {
            ("compute_job", str(job_id)),
            ("reminder", str(reminder.seq)),
        }
        # Pending work alone is not evidence that a running agent is waiting.
        core.agents["a"].current_run = CurrentRun(run_id="new", started_at=utc_now())
        core.agents["a"].state = AgentState.RUNNING
        a = (await client.get("/api/v2/projects/p/activity")).json()["agents"][0]
        assert a["waits"] == []


@pytest.mark.asyncio
async def test_detail_and_job_lookup_do_not_create_missing_ledger(tmp_path, monkeypatch):
    from cloudra.services.api_v2.routers import compute, observability

    core = setup_core()
    missing_db = ComputeDB(str(tmp_path / "not-created.db"))
    monkeypatch.setattr(compute, "ComputeDB", lambda: missing_db)
    monkeypatch.setattr(observability, "ComputeDB", lambda: missing_db)
    req = request(core, name="submit_compute_job")
    emit(core, "tool.result_recorded", {"tool_call_id": "same", "result": {"data": {"job_id": 1}}})
    async with client_for(core) as client:
        row = (await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")).json()
        assert row["unavailable_compute_job_ids"] == [1]
        assert (await client.get("/api/v2/projects/p/compute/jobs/1")).status_code == 404
    assert not (tmp_path / "not-created.db").exists()


@pytest.mark.asyncio
async def test_session_cancellation_closes_unfinished_calls_without_a_run_id():
    core = setup_core()
    req = request(core)
    emit(core, "tool.started", {"tool_call_id": "same"})
    emit(core, "agent.cancelled", {}, run=None)
    async with client_for(core) as client:
        row = (await client.get(f"/api/v2/agents/a/tool-calls/{req.event_id}")).json()
        assert row["status"] == "interrupted"
        assert row["effect_state"] == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["approval", "interaction"])
async def test_pending_broker_attaches_wait_to_its_exact_attempt(kind):
    import asyncio

    from cloudra.runtime_v2.invocation_context import InvocationScope, reset_invocation_scope, set_invocation_scope

    core = setup_core()
    first = request(core)
    second = request(core)
    token = set_invocation_scope(InvocationScope("same", "echo", request_event_id=first.event_id))
    try:
        if kind == "approval":
            task = asyncio.create_task(
                core.pending.request_approval(
                    core.agents["a"],
                    tool_name="echo",
                    details="write",
                    normalized_arguments={},
                    risk_summary="write",
                    candidate_diff="",
                )
            )
        else:
            task = asyncio.create_task(core.pending.request_interaction(core.agents["a"], "choose"))
    finally:
        reset_invocation_scope(token)
    try:
        async with asyncio.timeout(2):
            while not core.event_log.query_session("a", types={f"{kind}.requested"}):
                await asyncio.sleep(0)
        async with client_for(core) as client:
            a = (await client.get(f"/api/v2/agents/a/tool-calls/{first.event_id}")).json()
            b = (await client.get(f"/api/v2/agents/a/tool-calls/{second.event_id}")).json()
            assert a["status"] == "waiting"
            assert b["status"] == "queued"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_activity_cursor_and_calls_never_expose_unpersisted_events(tmp_path):
    from cloudra.runtime_v2.persistence import RuntimeStore

    core = setup_core()
    core.store = RuntimeStore(tmp_path / "runtime.db")
    first = request(core)
    await core.event_writer.flush()
    transient = request(core, call="uncommitted")
    async with client_for(core) as client:
        activity = (await client.get("/api/v2/projects/p/activity")).json()
        assert activity["as_of_seq"] == first.seq
        assert [r["request_event_id"] for r in activity["agents"][0]["active_calls"]] == [first.event_id]
        rows = (await client.get("/api/v2/agents/a/tool-calls")).json()["items"]
        assert [r["request_event_id"] for r in rows] == [first.event_id]
        assert (await client.get(f"/api/v2/agents/a/tool-calls/{transient.event_id}")).status_code == 404
        core.event_writer.discard_unpersisted()
        replacement = request(core, call="replacement")
        await core.event_writer.flush()
        assert replacement.seq > activity["as_of_seq"]
