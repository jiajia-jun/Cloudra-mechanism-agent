"""benchmark/watch.py — GH #30 等待状态机（wait_background / wait_review）。

红绿目标：
- SUCCEEDED + 存活子 agent/后台 = 未完成，继续等（C1 事故回归）；
- WAITING_APPROVAL(reason=wait_review) = 内部督导等待，不套 300s 人工卡死
  取消（NI1 事故回归），只有督导已死才按卡死处理；
- 其余无应答挂起（waiting_input / approval）照旧取消；运行时长不设上限。
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.benchmark.watch import RunWatcher
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentState, Command


async def _spawn_quiet(core, bus, project_id: str, role_id: str, **payload):
    """spawn 不带 query：不投递消息、不调度（纯状态样本）。"""
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project_id},
            payload={"role_id": role_id, **payload},
            actor="system",
        )
    )
    return result.data


async def _core_with_agents(tmp_path, second_role: str = "coordinator"):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={"name": "benchmark:T", "workspace_dir": str(tmp_path)},
            )
        )
    ).data
    parent = await _spawn_quiet(core, bus, project.id, "coordinator")
    binding = {}
    if second_role == "supervisor":
        from cloudra.dag.review_requests import ReviewRequest
        from cloudra.dag.store import DagStore
        from cloudra.persistence.database import ConversationDB

        def queue_exit():
            db = ConversationDB(project.id).init()
            return DagStore(db).enqueue_review(ReviewRequest(kind="exit", requester=parent.id,
                target_ids=["delivery"], question="May this delivery finish?",
                proposal={"disposition": "partial"}, basis_fingerprint="sha256:delivery"))

        binding = {"parent_session_id": parent.id,
                   "final_review_request_id": await asyncio.to_thread(queue_exit)}
    sibling = await _spawn_quiet(core, bus, project.id, second_role, **binding)
    return core, project, parent, sibling


def _watcher(**kwargs) -> RunWatcher:
    params = {
        "stuck_grace_s": 5.0,
        "poll_interval_s": 0.01,
    }
    params.update(kwargs)
    return RunWatcher(**params)


async def _set(core, agent, to: AgentState, reason: str) -> None:
    await core.agent_host.transition(agent, to, reason=reason)


async def _terminal(core, agent, to: AgentState, reason: str) -> None:
    """QUEUED 不能直接落终态：先补 RUNNING 再落终态（对齐真实状态机）。"""
    if agent.state is AgentState.QUEUED:
        await _set(core, agent, AgentState.RUNNING, "run_started")
    await _set(core, agent, to, reason)


@pytest.mark.asyncio
async def test_succeeded_with_live_sibling_keeps_waiting(tmp_path):
    """C1 事故：SUCCEEDED 只是当前 run 休眠（wait_background），子 agent 未竟
    前不得判题目完成。"""
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _set(core, parent, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.SUCCEEDED, "wait_background")
    watcher = _watcher()

    decision = await watcher.decide(core, parent)
    assert decision.kind == "continue"

    # 子 agent 到终态后，后台排空 → 真正完成
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    decision = await watcher.decide(core, parent)
    assert decision.kind == "done"


@pytest.mark.asyncio
async def test_succeeded_without_background_is_done(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.SUCCEEDED, "done")  # 兄弟已终态，不构成后台
    await _set(core, parent, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.SUCCEEDED, "allow_final")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_new_run", [False, True])
async def test_background_probe_discards_a_changed_run_snapshot(tmp_path, finish_new_run):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    await core.agent_host.start_run(parent)
    await core.agent_host.finish_run(parent, outcome="succeeded")
    probe_entered = asyncio.Event()
    release_probe = asyncio.Event()

    async def pending():
        probe_entered.set()
        await release_probe.wait()
        return False

    watcher = _watcher(pending_background=pending)
    decision_task = asyncio.create_task(watcher.decide(core, parent))
    try:
        await asyncio.wait_for(probe_entered.wait(), timeout=1.0)
        await core.agent_host.wake(parent)
        if finish_new_run:
            await core.agent_host.finish_run(parent, outcome="succeeded")
        release_probe.set()
        decision = await asyncio.wait_for(decision_task, timeout=1.0)
        assert decision.kind == "continue"
        # The next poll can use the new snapshot; the invalidated result is not cached.
        assert (await watcher.decide(core, parent)).kind == (
            "done" if finish_new_run else "continue"
        )
    finally:
        release_probe.set()
        await asyncio.gather(decision_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_terminal_child_is_pending_until_its_completion_delivery_finishes(tmp_path, monkeypatch):
    from tests.benchmark_support import ScriptedLLM, assemble_live_pipeline, text

    core, project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    await core.agent_host.start_run(parent)
    await core.agent_host.finish_run(parent, outcome="succeeded")
    llm = ScriptedLLM(core)
    llm.script("explorer", [text(1, "child result")])
    llm.script("coordinator", [text(1, "child result received")])
    _, runner = assemble_live_pipeline(core, llm)
    delivery_entered = asyncio.Event()
    release_delivery = asyncio.Event()
    original_delivery = runner._deliver_completion

    async def held_delivery(agent):
        if agent.role_id == "explorer":
            delivery_entered.set()
            await release_delivery.wait()
        await original_delivery(agent)

    monkeypatch.setattr(runner, "_deliver_completion", held_delivery)
    child = (await CommandBus(core).execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "explorer", "parent_session_id": parent.id, "query": "finish"},
    ))).data
    child_task = runner.task_for(child.id)
    try:
        await asyncio.wait_for(delivery_entered.wait(), timeout=5.0)
        assert child.state is AgentState.SUCCEEDED
        assert child_task is not None and not child_task.done()
        assert (await _watcher().decide(core, parent)).kind == "continue"
        release_delivery.set()
        await asyncio.wait_for(child_task, timeout=5.0)
        parent_task = runner.task_for(parent.id)
        if parent_task is not None:
            await asyncio.wait_for(parent_task, timeout=5.0)
        assert parent.state is AgentState.SUCCEEDED
        assert (await _watcher().decide(core, parent)).kind == "done"
    finally:
        release_delivery.set()
        await runner.cancel_all()


@pytest.mark.asyncio
async def test_injected_background_extends_succeeded_wait(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    await _set(core, parent, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.SUCCEEDED, "wait_background")

    async def pending() -> bool:
        return True

    watcher = _watcher(pending_background=pending)
    assert (await watcher.decide(core, parent)).kind == "continue"
    watcher = _watcher(pending_background=lambda: asyncio.sleep(0, result=False))
    assert (await watcher.decide(core, parent)).kind == "done"


@pytest.mark.asyncio
async def test_parked_run_waits_for_notice_then_requests_resume(tmp_path):
    """A compute result is not scored before its terminal notice is read."""
    from cloudra.runtime_v2.dispatcher import WakePolicy

    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    run_id = await core.agent_host.start_run(parent)
    core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=parent.project_id,
        session_id=parent.id, run_id=run_id,
        data={"action": "wait_background", "basis": "background_wait", "reason": "compute pending"},
    )
    await core.agent_host.finish_run(parent, outcome="succeeded")
    pending = True

    async def background_pending():
        return pending

    watcher = _watcher(pending_background=background_pending)
    assert (await watcher.decide(core, parent)).kind == "continue"

    await core.dispatcher.commit_and_deliver(
        to_session_id=parent.id, project_id=parent.project_id,
        content="[Compute job] job 1 done", sender="system", wake=WakePolicy.NEVER,
    )
    pending = False
    assert (await watcher.decide(core, parent)).kind == "resume"


@pytest.mark.asyncio
async def test_watcher_resumes_parked_run_once_notice_is_ready(tmp_path):
    from cloudra.runtime_v2.dispatcher import WakePolicy

    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    run_id = await core.agent_host.start_run(parent)
    core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=parent.project_id,
        session_id=parent.id, run_id=run_id,
        data={"action": "wait_background", "basis": "background_wait", "reason": "compute pending"},
    )
    await core.agent_host.finish_run(parent, outcome="succeeded")
    resumed = []

    async def resume():
        resumed.append(True)
        await core.agent_host.wake(parent)
        await core.agent_host.finish_run(parent, outcome="succeeded")

    pending = True

    async def background_pending():
        return pending

    watcher = _watcher(pending_background=background_pending, resume_background=resume)
    wait_task = asyncio.create_task(watcher.wait(core, parent, lambda _reason: asyncio.sleep(0)))
    await asyncio.sleep(0.03)
    assert not wait_task.done()
    await core.dispatcher.commit_and_deliver(
        to_session_id=parent.id, project_id=parent.project_id,
        content="[Compute job] job 1 done", sender="system", wake=WakePolicy.NEVER,
    )
    pending = False
    assert await asyncio.wait_for(wait_task, timeout=1.0) is None
    assert resumed == [True]


@pytest.mark.asyncio
async def test_drained_parked_run_retries_then_cancels_if_reconciliation_cannot_wake(tmp_path):
    """GH #203: a no-op reconciliation cannot turn an empty wait into eternity."""
    from types import SimpleNamespace

    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    run_id = await core.agent_host.start_run(parent)
    core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=parent.project_id,
        session_id=parent.id, run_id=run_id,
        data={"action": "wait_background", "basis": "background_wait"},
    )
    await core.agent_host.finish_run(parent, outcome="succeeded")
    reconciled = []

    async def reconcile(project_id):
        reconciled.append(project_id)

    core.runner = SimpleNamespace(maybe_wake_parked_delivery=reconcile)

    watcher = _watcher(
        pending_background=lambda: asyncio.sleep(0, result=False),
        stuck_grace_s=0.03,
    )
    assert (await watcher.decide(core, parent)).kind == "continue"
    await _terminal(core, sibling, AgentState.SUCCEEDED, "done")
    reasons = []

    async def cancel(reason):
        reasons.append(reason)

    reason = await asyncio.wait_for(watcher.wait(core, parent, cancel), timeout=1.0)
    assert reason is not None and "wait_background" in reason
    assert "no pending background work" in reason
    assert len(reconciled) > 1
    assert reasons == [reason]
    assert parent.state is AgentState.SUCCEEDED  # callback decides how to record cancellation


@pytest.mark.asyncio
@pytest.mark.parametrize("persisted_marker", [False, True], ids=["new-notice", "interrupted-notice"])
async def test_scenario_watcher_retries_quiescence_and_consumes_exactly_one_notice(
    tmp_path, monkeypatch, persisted_marker,
):
    """Real runner/dispatcher/context trajectory: retry a lost wake before scoring."""
    from cloudra.runtime_v2.effects import EventDraft
    from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step

    harness = await ScenarioHarness.start(
        tmp_path, provider=ScriptedProvider(default=[Step(text="rechecked delivery", stop=True)]),
    )
    core = harness.core
    parent = await _spawn_quiet(core, harness.bus, harness.project.id, "coordinator")
    parked_run = await core.agent_host.start_run(parent)
    await core.event_writer.commit(EventDraft(
        "agent.completion_gate", stream="agent", project_id=parent.project_id,
        session_id=parent.id, run_id=parked_run,
        data={"action": "wait_background", "basis": "background_wait", "source": "dag"},
    ))
    await core.agent_host.finish_run(parent, outcome="succeeded")
    if persisted_marker:
        # Durable-before-enqueue interruption: recovery must reuse this id.
        await core.event_writer.commit(EventDraft(
            "agent.message_injected", stream="project", project_id=parent.project_id,
            session_id=parent.id,
            data={"message_id": "interrupted-quiescence", "sender": "background_quiescence",
                  "content": "[Background work settled] Recheck delivery.",
                  "manifest": {"kind": "background_quiescence", "parked_run_id": parked_run}},
        ))
    reconcile = harness.runner.maybe_wake_parked_delivery
    attempts = 0

    async def transient_noop(project_id):
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            await reconcile(project_id)

    monkeypatch.setattr(harness.runner, "maybe_wake_parked_delivery", transient_noop)
    cancelled = []

    async def cancel(reason):
        cancelled.append(reason)

    async def resume():
        await core.agent_host.wake(parent, runner=harness.runner)

    watcher = _watcher(
        pending_background=lambda: asyncio.sleep(0, result=False),
        resume_background=resume, stuck_grace_s=0.3,
    )
    try:
        assert await asyncio.wait_for(watcher.wait(core, parent, cancel), timeout=2.0) is None
        notices = [event for event in harness.events(parent)
                   if (event.data.get("manifest") or {}).get("kind") == "background_quiescence"]
        assert len(notices) == 1
        assert notices[0].data["manifest"]["parked_run_id"] == parked_run
        if persisted_marker:
            assert notices[0].data["message_id"] == "interrupted-quiescence"
        consumed = [message for message in core.contexts.current_messages(parent.id)
                    if message.get("message_id") == notices[0].data["message_id"]]
        assert len(consumed) == 1
        assert len(harness.run_rows(parent)) == 2
        gates = [event for event in harness.events(parent) if event.type == "agent.completion_gate"]
        assert gates[-1].data["action"] == "allow_final"
        assert gates[-1].run_id != parked_run
        assert cancelled == []
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_scenario_recovered_guided_delivery_keeps_missing_evidence_open(tmp_path, monkeypatch):
    """A real DAG background gate must re-audit missing evidence after the wake."""
    from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step

    hold = asyncio.Event()
    provider = ScriptedProvider(by_role={"coordinator": [
        Step(tools=[("stop", {"delivery_disposition": "complete"})]),
        Step(tools=[("stop", {"delivery_disposition": "complete"})]),
        Step(wait_for=hold),
    ]})
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    stop = asyncio.Event()
    wait_task = None
    try:
        peer = await harness.spawn("explorer", query="")
        parent = await harness.spawn(
            "coordinator", protocol="traditional", orchestration_mode="dag_guided",
        )
        await harness.wait_for(
            lambda: parent.state is AgentState.SUCCEEDED and harness.runner.task_for(parent.id) is None,
            "DAG coordinator parked behind the queued explorer",
        )
        gates = [event for event in harness.events(parent) if event.type == "agent.completion_gate"]
        assert gates[-1].data["action"] == "wait_background"
        assert gates[-1].data["source"] == "dag"
        parked_run = gates[-1].run_id
        await _terminal(harness.core, peer, AgentState.CANCELLED, "cancel")
        reconcile = harness.runner.maybe_wake_parked_delivery
        attempts = 0

        async def transient_noop(project_id):
            nonlocal attempts
            attempts += 1
            if attempts > 1:
                await reconcile(project_id)

        monkeypatch.setattr(harness.runner, "maybe_wake_parked_delivery", transient_noop)
        cancelled = []

        async def cancel(reason):
            cancelled.append(reason)

        watcher = _watcher(
            pending_background=lambda: asyncio.sleep(0, result=False),
            stop_event=stop, stuck_grace_s=0.3,
        )
        wait_task = asyncio.create_task(watcher.wait(harness.core, parent, cancel))
        await harness.wait_for(
            lambda: provider.call_count("coordinator") == 3,
            "resumed DAG audit rejects complete and returns to the provider",
        )
        gates = [event for event in harness.events(parent) if event.type == "agent.completion_gate"]
        assert gates[-1].data["action"] == "continue_work"
        assert gates[-1].data["source"] == "dag"
        assert gates[-1].run_id != parked_run
        assert parent.state is AgentState.RUNNING
        assert not wait_task.done()
        assert cancelled == []
        notices = [event for event in harness.events(parent)
                   if (event.data.get("manifest") or {}).get("kind") == "background_quiescence"]
        assert len(notices) == 1
        assert any(message.get("message_id") == notices[0].data["message_id"]
                   for message in harness.core.contexts.current_messages(parent.id))
        assert not any(event.type == "run.finished" and event.run_id == gates[-1].run_id
                       for event in harness.events(parent))
    finally:
        stop.set()
        if wait_task is not None:
            assert await asyncio.wait_for(wait_task, timeout=1.0) == "benchmark batch stopped"
        await harness.aclose()


@pytest.mark.asyncio
async def test_unconsumed_notice_with_noop_resume_cancels_instead_of_resetting_grace(tmp_path):
    from cloudra.runtime_v2.dispatcher import WakePolicy

    core, _project, parent, peer = await _core_with_agents(tmp_path)
    await _terminal(core, peer, AgentState.CANCELLED, "cancel")
    run_id = await core.agent_host.start_run(parent)
    core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=parent.project_id,
        session_id=parent.id, run_id=run_id,
        data={"action": "wait_background", "basis": "background_wait"},
    )
    await core.agent_host.finish_run(parent, outcome="succeeded")
    await core.dispatcher.commit_and_deliver(
        to_session_id=parent.id, project_id=parent.project_id,
        content="read the completed result", sender="system", wake=WakePolicy.NEVER,
    )
    attempts, cancelled = [], []

    async def resume():
        attempts.append(True)

    async def cancel(reason):
        cancelled.append(reason)

    watcher = _watcher(resume_background=resume, stuck_grace_s=0.03)
    reason = await asyncio.wait_for(watcher.wait(core, parent, cancel), timeout=1.0)
    assert reason is not None and run_id in reason
    assert len(attempts) > 1
    assert cancelled == [reason]
    assert core.mailbox.inbox(parent.id).qsize() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["state", "run", "same_run"])
async def test_grace_verification_does_not_cancel_a_replacement_wait(tmp_path, monkeypatch, replacement):
    """The expiry probe may observe a different unanswered wait with its own grace."""
    from types import SimpleNamespace

    import cloudra.benchmark.watch as watch_module

    core, _project, parent, peer = await _core_with_agents(tmp_path)
    await _terminal(core, peer, AgentState.CANCELLED, "cancel")
    await core.agent_host.start_run(parent)
    await _set(core, parent, AgentState.WAITING_INPUT, "first question")
    now = 0.0
    monkeypatch.setattr(watch_module, "asyncio", SimpleNamespace(
        get_running_loop=lambda: SimpleNamespace(time=lambda: now), to_thread=asyncio.to_thread,
    ))
    watcher = _watcher(stuck_grace_s=5.0)
    decide = watcher.decide
    calls = 0

    async def replace_wait_at_expiry(runtime, agent):
        nonlocal calls
        calls += 1
        if calls == 3:
            await _set(core, parent, AgentState.RUNNING, "first question answered")
            if replacement == "run":
                await core.agent_host.finish_run(parent, outcome="succeeded")
                await core.agent_host.start_run(parent)
            await _set(
                core, parent,
                AgentState.WAITING_APPROVAL if replacement == "state" else AgentState.WAITING_INPUT,
                "a different unanswered request",
            )
        return await decide(runtime, agent)

    async def advance():
        nonlocal now
        now += 10.0

    monkeypatch.setattr(watcher, "decide", replace_wait_at_expiry)
    monkeypatch.setattr(watcher, "_poll_delay", advance)
    cancelled = []

    async def cancel(reason):
        cancelled.append((now, reason))

    reason = await watcher.wait(core, parent, cancel)
    assert cancelled[0][0] >= 20.0
    assert ("waiting_approval" if replacement == "state" else "waiting_input") in reason


@pytest.mark.asyncio
async def test_succeeded_waits_for_its_own_completion_task(tmp_path, monkeypatch):
    from tests.agent_scenarios import ScenarioHarness

    harness = await ScenarioHarness.start(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    deliver = harness.runner._deliver_completion

    async def held_delivery(agent):
        entered.set()
        await release.wait()
        await deliver(agent)

    monkeypatch.setattr(harness.runner, "_deliver_completion", held_delivery)
    try:
        parent = await harness.spawn("coordinator")
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        assert parent.state is AgentState.SUCCEEDED
        assert (await _watcher().decide(harness.core, parent)).kind == "continue"
        release.set()
        await asyncio.wait_for(harness.runner.task_for(parent.id), timeout=1.0)
        assert (await _watcher().decide(harness.core, parent)).kind == "done"
    finally:
        release.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_success_projection_with_unclosed_run_cannot_be_scored(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    await core.agent_host.start_run(parent)
    # A partial finish can persist SUCCEEDED before run.finished is durable.
    await _set(core, parent, AgentState.SUCCEEDED, "succeeded")
    assert parent.current_run is not None
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "unfinished run" in decision.reason


@pytest.mark.asyncio
async def test_queued_launch_group_without_child_is_pending_background(tmp_path):
    from cloudra.runtime_v2.apply import apply_event
    from cloudra.runtime_v2.effects import EventDraft

    core, project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    await core.agent_host.start_run(parent)
    await core.agent_host.finish_run(parent, outcome="succeeded")
    event = await core.event_writer.commit(EventDraft(
        "launch_group.created", stream="project", project_id=project.id,
        session_id=parent.id,
        data={"group_id": "unadmitted", "parent_session_id": parent.id,
              "max_concurrency": 1, "items": [{"item_id": "queued", "query": "work"}]},
    ))
    apply_event(core, event)
    assert (await _watcher().decide(core, parent)).kind == "continue"


@pytest.mark.asyncio
async def test_parked_succeeded_child_still_counts_as_live_peer(tmp_path):
    from cloudra.benchmark.watch import has_running_peers

    core, project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    bus = CommandBus(core)
    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "explorer", "parent_session_id": parent.id},
    ))).data
    run_id = await core.agent_host.start_run(child)
    core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=project.id,
        session_id=child.id, run_id=run_id,
        data={"action": "wait_background", "basis": "background_wait"},
    )
    await core.agent_host.finish_run(child, outcome="succeeded")
    cache = {}
    assert has_running_peers(core, parent, final_cache=cache) is True
    assert has_running_peers(core, parent, final_cache=cache) is True

    run_id = await core.agent_host.start_run(child)
    core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=project.id,
        session_id=child.id, run_id=run_id,
        data={"action": "allow_final", "basis": "declared"},
    )
    await core.agent_host.finish_run(child, outcome="succeeded")
    assert has_running_peers(core, parent, final_cache=cache) is False


@pytest.mark.asyncio
async def test_wait_review_with_live_supervisor_not_stuck(tmp_path):
    """NI1 事故：wait_review 挂起等内部 Supervisor，不是人工审批卡死。"""
    core, project, parent, supervisor = await _core_with_agents(tmp_path, second_role="supervisor")
    await _set(core, supervisor, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")

    decision = await _watcher().decide(core, parent)
    assert decision.kind == "continue"

    # 督导自身结束（无人会再裁决）→ 落入卡死取消，而不是永远挂着
    await _terminal(core, supervisor, AgentState.SUCCEEDED, "done")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "no live supervisor" in decision.reason


@pytest.mark.asyncio
async def test_wait_review_without_any_supervisor_cancels(tmp_path):
    core, _project, parent, _sibling = await _core_with_agents(tmp_path)
    await _set(core, parent, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "no live supervisor" in decision.reason


@pytest.mark.asyncio
async def test_unanswered_hangs_are_stuck(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.SUCCEEDED, "done")
    await _set(core, parent, AgentState.RUNNING, "run_started")

    await _set(core, parent, AgentState.WAITING_INPUT, "ask_user")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "waiting_input" in decision.reason and "nobody to answer" in decision.reason

    await _set(core, parent, AgentState.RUNNING, "resumed")
    await _set(core, parent, AgentState.WAITING_APPROVAL, "approval")
    decision = await _watcher().decide(core, parent)
    assert decision.kind == "cancel"
    assert "waiting_approval" in decision.reason


@pytest.mark.asyncio
async def test_wait_applies_stuck_grace_then_cancels(tmp_path):
    core, _project, parent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.SUCCEEDED, "done")
    await _set(core, parent, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.WAITING_INPUT, "ask_user")

    reasons: list[str] = []

    async def cancel(reason: str) -> None:
        reasons.append(reason)

    watcher = _watcher(stuck_grace_s=0.05)
    reason = await watcher.wait(core, parent, cancel)
    assert reason is not None and "waiting_input" in reason
    assert reasons == [reason]


@pytest.mark.asyncio
async def test_wait_wait_review_survives_grace_with_live_supervisor(tmp_path):
    core, _project, parent, supervisor = await _core_with_agents(tmp_path, second_role="supervisor")
    await _set(core, supervisor, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")

    cancelled: list[str] = []

    async def cancel(reason: str) -> None:
        cancelled.append(reason)

    watcher = _watcher(stuck_grace_s=0.05)
    wait_task = asyncio.create_task(watcher.wait(core, parent, cancel))
    try:
        # 远超 stuck_grace 的时间窗内不得取消（督导还活着）
        await asyncio.wait_for(asyncio.sleep(0.2), timeout=1.0)
        assert not cancelled
        assert not wait_task.done()
    finally:
        # 督导死亡 → 落入卡死取消，等待收尾
        await _terminal(core, supervisor, AgentState.SUCCEEDED, "done")
        reason = await asyncio.wait_for(wait_task, timeout=2.0)
        assert reason is not None and "no live supervisor" in reason
        assert cancelled == [reason]


@pytest.mark.asyncio
@pytest.mark.parametrize("waiting", ["running", "background", "review"])
async def test_long_running_task_finishes_without_duration_cancel(tmp_path, monkeypatch, waiting):
    """Elapsed wall time cannot cancel active work or internal waits."""
    from types import SimpleNamespace

    import cloudra.benchmark.watch as watch_module

    core, _project, parent, peer = await _core_with_agents(
        tmp_path, second_role="supervisor" if waiting == "review" else "coordinator",
    )
    await _set(core, parent, AgentState.RUNNING, "run_started")
    if waiting == "background":
        await _set(core, parent, AgentState.SUCCEEDED, "wait_background")
    elif waiting == "review":
        await _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")
    else:
        await _terminal(core, peer, AgentState.SUCCEEDED, "done")

    now = 0.0
    polls = 0
    reasons = []
    watcher = _watcher()
    monkeypatch.setattr(
        watch_module, "asyncio",
        SimpleNamespace(
            get_running_loop=lambda: SimpleNamespace(time=lambda: now), to_thread=asyncio.to_thread,
        ),
    )

    async def advance_work():
        nonlocal now, polls
        now += 24 * 60 * 60
        polls += 1
        if polls == 3:
            if peer.state is not AgentState.SUCCEEDED:
                await _terminal(core, peer, AgentState.SUCCEEDED, "done")
            if parent.state is AgentState.WAITING_APPROVAL:
                await _set(core, parent, AgentState.RUNNING, "review_complete")
            if parent.state is not AgentState.SUCCEEDED:
                await _set(core, parent, AgentState.SUCCEEDED, "allow_final")

    async def cancel(reason):
        reasons.append(reason)

    monkeypatch.setattr(watcher, "_poll_delay", advance_work)
    assert await watcher.wait(core, parent, cancel) is None
    assert polls == 3
    assert reasons == []


@pytest.mark.asyncio
async def test_latest_state_reason_reads_event_log(tmp_path):
    from cloudra.runtime_v2.dispatcher import latest_state_reason

    core, _project, parent, _sibling = await _core_with_agents(tmp_path)
    assert latest_state_reason(core, parent.id) == ""
    await _set(core, parent, AgentState.RUNNING, "run_started")
    await _set(core, parent, AgentState.WAITING_APPROVAL, "wait_review")
    assert latest_state_reason(core, parent.id) == "wait_review"
