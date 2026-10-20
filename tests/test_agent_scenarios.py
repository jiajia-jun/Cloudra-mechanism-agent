"""场景级 Agent 回归场景（评审 5.8）。

每个用例 = 一条真实轨迹 + 一组**事件/状态不变量**断言（不断言模型措辞）。
harness 与断言面见 ``tests/agent_scenarios.py`` 的模块 docstring。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.dispatcher import WakePolicy
from tests.agent_scenarios import (
    ProviderFault,
    ScenarioHarness,
    ScriptedProvider,
    Step,
    confirm_partial_stop_step,
    malformed_shell_steps,
    pending_stop_answer_step,
)


@pytest.mark.asyncio
async def test_stale_file_review_retires_wakes_and_requires_real_resubmission(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.evidence_facts import EvidenceFact, FactSubject
    from cloudra.dag.models import UpdateEdge
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB
    from cloudra.runtime_v2.supervision import (
        find_project_supervisor,
        flush_review_notifications,
        notify_supervisor,
    )
    from tests.agent_scenarios import stale_review_resubmit_steps
    from tests.test_dag_file_review_contract import _mutate

    review_old, review_new, resubmit, finish, park = [asyncio.Event() for _ in range(5)]
    old_step, new_step = Step(wait_for=review_old), Step(wait_for=review_new)
    fixture = Path(__file__).parent / "fixtures/benchmark_synthetic/ts_freq.out"
    provider = ScriptedProvider(by_role={
        "coordinator": stale_review_resubmit_steps(fixture.name, resubmit, finish, park),
        "supervisor": [Step(stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        await _set_supervisor_traditional(harness)
        workspace = _workspace(harness.project.id)
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture, workspace / fixture.name)
        await asyncio.to_thread(_seed_guided_step_for_file_review, harness.project.id)
        db = await asyncio.to_thread(lambda: ConversationDB(harness.project.id).init())
        store = DagStore(db)
        await asyncio.to_thread(_mutate, store, UpdateEdge(op="update_edge", graph="delivery", edge_id="step1",
            changes={"stages": [{"kind": "ts_opt"}, {"kind": "frequency"}, {"kind": "short_irc"}]}))
        coordinator = await harness.spawn("coordinator", protocol="traditional", orchestration_mode="dag_guided")
        await harness.wait_for(lambda: any(a.role_id == 'supervisor' and a.state.value == 'succeeded'
                                          for a in harness.core.agents.values()), 'Supervisor idle after initial submission')
        park.set()
        await harness.wait_for(lambda: coordinator.state.value == "waiting_approval", "Coordinator parked awaiting review")
        await harness.wait_for(lambda: all(a.state.value == "succeeded" for a in harness.core.agents.values()
            if a.role_id == "supervisor"), "process and final reviewers are idle")
        process = find_project_supervisor(harness.core, harness.project.id)
        assert process is not None and process.final_review_request_id is None
        provider.script("supervisor", old_step, new_step, Step(wait_for=finish, text="await more evidence"))
        submitted = next(t for t in harness.tool_events(coordinator) if t["tool_name"] == "dag_submit_step_evidence")
        old_id = submitted["result_data"]["result"]["review_id"]
        old_request = await asyncio.to_thread(store.get_review_request, old_id)
        await asyncio.to_thread(store.record_facts, [EvidenceFact(fact_id="new-related-fact", check="path", outcome="refutes",
            subject=FactSubject(target_hint="step1"), source_refs=old_request.supporting_refs, details={"missing_direction": True})])
        await notify_supervisor(harness.core, harness.project.id,
                                observation="A new related path fact requires process review.")
        old_step.tools = [("dag_review_evidence", {"request_id": old_id, "verdict": "accept", "reason": "review old file snapshot"})]
        review_old.set()
        await harness.wait_for(lambda: any(t["tool_name"] == "dag_review_evidence" and t["status"] in {"completed", "failed"}
            for a in harness.core.agents.values() if a.role_id == "supervisor" for t in harness.tool_events(a)), "stale review rejected")
        old_result = next(t for a in harness.core.agents.values() if a.role_id == "supervisor"
            for t in harness.tool_events(a) if t["tool_name"] == "dag_review_evidence")
        assert not old_result["is_success"]
        assert old_result["result_data"]["rejection_code"] == "stale_basis"
        assert (await asyncio.to_thread(store.get_review_request, old_id)).state == "superseded"
        assert await asyncio.to_thread(store.get_review_decision_for_request, old_id) is None
        await harness.wait_for(lambda: coordinator.state.value == "running" and provider.call_count("coordinator") >= 4,
                               "original requester wakes after stale notice")
        def notices():
            with db.connect() as con:
                return con.execute("SELECT kind,request_id,recipient_session_id,state FROM dag_review_notifications WHERE request_id=?",
                                   (old_id,)).fetchall()
        assert await asyncio.to_thread(notices) == [("review_superseded", old_id, coordinator.id, "sent")]
        assert await flush_review_notifications(harness.core, harness.project.id) == 0
        assert old_id not in [r.request_id for r in await asyncio.to_thread(store.list_review_requests)]
        controller = DagController(db, coordinator.id, "dag_guided", conversation_id=harness.project.id)
        report = await asyncio.to_thread(controller.delivery_report)
        assert any(g.code == "stale_evidence_review" for g in report.unresolved)
        resubmit.set()
        await harness.wait_for(lambda: len([t for t in harness.tool_events(coordinator)
            if t["tool_name"] == "dag_submit_step_evidence" and t["status"] == "completed"]) == 2, "explicit resubmission")
        submissions = [t for t in harness.tool_events(coordinator) if t["tool_name"] == "dag_submit_step_evidence"]
        new_id = submissions[-1]["result_data"]["result"]["review_id"]
        assert new_id != old_id
        new_step.tools = [("dag_review_evidence", {"request_id": new_id, "verdict": "needs_evidence",
            "reason": "IRC direction material remains missing", "next_action": "submit a two-sided IRC with verified minima"})]
        review_new.set()
        await harness.wait_for(lambda: len([t for a in harness.core.agents.values() if a.role_id == "supervisor"
            for t in harness.tool_events(a) if t["tool_name"] == "dag_review_evidence" and t["status"] in {"completed", "failed"}]) == 2,
            "new material adjudicated")
        assert (await asyncio.to_thread(store.get_review_request, new_id)).state == "resolved"
        report = await asyncio.to_thread(controller.delivery_report)
        assert not report.complete
        assert any(g.code == "supervisor_review_gap" for g in report.unresolved)
        assert any("short_irc" in g.detail for g in report.unresolved)
        assert not any(g.code == "stale_evidence_review" for g in report.unresolved)
        assert len([m for m in harness.messages(coordinator) if old_id in str(m.get("content", ""))]) == 1
    finally:
        for event in (review_old, review_new, resubmit, finish, park):
            event.set()
        await harness.aclose()



@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["traditional", "javascript"])
async def test_stop_answer_is_emitted_only_after_final_gate_authorizes_it(tmp_path, protocol):
    from cloudra.dag.review_requests import ReviewDecision
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB
    from cloudra.runtime_v2.supervision import flush_review_notifications

    candidate = "candidate-answer-marker"
    release = asyncio.Event()
    final = confirm_partial_stop_step(release)
    provider = ScriptedProvider(by_role={
        "coordinator": [pending_stop_answer_step(candidate) for _ in range(4)],
        "supervisor": [Step(stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        coordinator = await harness.spawn("coordinator", protocol=protocol, orchestration_mode="dag_guided")
        await harness.wait_for(lambda: coordinator.state.value == "waiting_approval", "pending exit review")
        messages = [e for e in harness.events(coordinator) if e.type == "agent.message_emitted"]
        assert not any(candidate in e.data.get("content", "") for e in messages)
        await harness.wait_for(lambda: all(a.state.value == "succeeded" for a in harness.core.agents.values()
            if a.role_id == "supervisor"), "Supervisor idle while exit decision is pending")
        provider.script("coordinator", *[final for _ in range(4)])

        def approve():
            store = DagStore(ConversationDB(harness.project.id))
            request = next(r for r in store.list_review_requests(state="queued") if r.kind == "exit")
            decision = ReviewDecision(request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
                verdict="accept", reason="approved partial with all gaps retained")
            assert store.resolve_review(decision, expected_basis=request.basis_fingerprint)["accepted"]

        await asyncio.to_thread(approve)
        await flush_review_notifications(harness.core, harness.project.id)
        release.set()
        await harness.wait_for(
            lambda: coordinator.state.value == "succeeded" and any(
                e.type == "agent.message_emitted" and e.data.get("content") == candidate
                for e in harness.events(coordinator)), "authorized final stop and durable answer")
        events = harness.events(coordinator)
        gate = next(e for e in events if e.type == "agent.completion_gate" and e.data["action"] == "allow_final")
        emitted = next(e for e in events if e.type == "agent.message_emitted" and e.data.get("content") == candidate)
        assert gate.seq < emitted.seq
        assert not any(candidate in e.data.get("content", "") for e in events
            if e.type == "agent.message_emitted" and e.seq < gate.seq)
    finally:
        release.set()
        await harness.aclose()


def _todo_store_file(project_id: str, session_id: str) -> Path:
    """todo_write 的 per-agent 存储文件（副作用观测点）。"""
    from cloudra.persistence.paths import data_dir

    plan_dir = Path(data_dir()) / "conversations" / project_id / "plan"
    matches = sorted(plan_dir.glob("*_todos.json"))
    assert matches, f"todo store missing under {plan_dir}"
    return next(path for path in matches if session_id in path.name)


def _workspace(project_id: str) -> Path:
    """该项目的真实默认工作区（GH #24 之后相对路径都以此为根）。"""
    from cloudra.persistence.paths import project_workspace_dir

    return Path(project_workspace_dir(project_id))


# ------------------------------------------------------ harness 自身契约


@pytest.mark.asyncio
async def test_compute_result_wakes_agent_during_high_throughput_batch(tmp_path):
    """逐作业通知应触发结果处理；剩余作业仍须阻止最终交付。"""
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from tests.agent_scenarios import compute_result_recovery_steps
    from tests.test_runtime_v2_compute_notify import _insert_terminal_job

    release = asyncio.Event()
    provider = ScriptedProvider(default=[Step(wait_for=release, stop=True)])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await harness.spawn("small_mol", protocol="traditional")
        finished = await asyncio.to_thread(
            _insert_terminal_job, harness.project.id, session_id=agent.id, state="failed", path="",
        )
        running = await asyncio.to_thread(
            _insert_terminal_job, harness.project.id, session_id=agent.id, state="running", path="",
        )
        release.set()
        await harness.wait_terminal(agent)
        assert any(e.type == "agent.completion_gate" and e.data.get("action") == "wait_background"
                   for e in harness.events(agent)), harness.describe(agent)
        provider.script_default(*compute_result_recovery_steps())

        broker = ComputeNotifyBroker(harness.core)
        await broker._poll_project(harness.project.id)
        await harness.wait_for(lambda: len(harness.run_rows(agent)) == 2, "result processing run")

        assert any(call["tool_name"] == "todo_write" and call["is_success"]
                   for call in harness.tool_events(agent)), harness.describe(agent)
        gates = [e for e in harness.events(agent) if e.type == "agent.completion_gate"]
        assert gates[-1].data["action"] == "wait_background"
        notices = [e for e in harness.events(agent)
                   if e.type == "agent.message_injected" and (e.data.get("manifest") or {}).get("kind") == "compute_completion"]
        assert [task_id for e in notices for task_id in e.data["manifest"]["task_ids"]] == [finished]
        async with ComputeDB().aconnect() as con:
            row = await (await con.execute("SELECT state FROM compute_jobs WHERE id=?", (running,))).fetchone()
        assert row[0] == "running"
    finally:
        release.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_malformed_shell_is_blocked_without_crashing_agent(tmp_path):
    """Shell 校验失败需落 requested/blocked/finished，且后续回合可执行。"""
    harness = await ScenarioHarness.start(
        tmp_path, provider=ScriptedProvider(default=malformed_shell_steps()),
    )
    try:
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        shell = next((call for call in calls if call["tool_name"] == "bash"), None)
        assert shell is not None, harness.describe(agent)
        assert shell["status"] == "blocked"
        assert shell["effect_state"] == "not_started"
        assert shell["block_stage"] == "permission"
        assert shell["started"] is False
        assert any(call["tool_name"] == "todo_write" and call["is_success"] for call in calls)
        assert agent.state.value == "succeeded"
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_scripted_provider_exhausts_its_final_step():
    provider = ScriptedProvider(default=[Step(tools=[("todo_read", {})])])
    agent = SimpleNamespace(role_id="coordinator")

    first = await provider.complete(agent, [], [])
    exhausted = await provider.complete(agent, [], [])

    assert [call.name for call in first.tool_calls] == ["todo_read"]
    assert exhausted.stop_requested is True
    assert exhausted.tool_calls == []


@pytest.mark.asyncio
async def test_scenario_harness_shares_the_core_event_writer(tmp_path):
    harness = await ScenarioHarness.start(tmp_path)
    try:
        assert harness.pipeline.event_writer is harness.core.event_writer
        assert harness.pipeline.invocations.event_writer is harness.core.event_writer
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_snapshot_restore_keeps_invocations_on_the_live_agent_registry(tmp_path):
    harness = await ScenarioHarness.start(tmp_path)
    try:
        agent = await harness.spawn("coordinator")
        await harness.wait_terminal(agent)
        await harness.bus.flush_snapshot()
    finally:
        await harness.aclose()

    restored = await ScenarioHarness.restore(tmp_path)
    try:
        assert restored.pipeline.invocations._agents is restored.core.agents
        assert agent.id in restored.pipeline.invocations._agents
    finally:
        await restored.aclose()


# --------------------------------------------------------------- 1. 普通问答


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_ordinary_project_method_input_survives_stored_policy(tmp_path):
    import json

    from cloudra.runtime_v2.schemas import AgentState, Command, InvocationProtocol
    from tests.agent_scenarios import ordinary_method_input_steps

    source = tmp_path / "source.xyz"
    source.write_text("2\nfixture\nH 0 0 0\nH 0 0 0.74\n")
    output = tmp_path / "ordinary.inp"
    provider = ScriptedProvider(default=ordinary_method_input_steps(source, output))
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    try:
        await harness.bus.execute(Command(type="project.update", target={"project_id": harness.project.id},
            payload={"settings": {"method_policy": {"allowed_methods": ["xtb"]}}}))
        agent = await harness.spawn("small_mol", protocol=InvocationProtocol.TRADITIONAL)
        await harness.wait_terminal(agent)
        assert agent.state == AgentState.SUCCEEDED
        assert output.is_file()
        assert "PBE0" in output.read_text() and "def2-TZVP" in output.read_text()
        scopes = []
        for _role, messages in provider.calls:
            for message in messages:
                content = message.get('content')
                if isinstance(content, str) and '[Current MethodPolicy scope]' in content:
                    payload = content.split('[Current MethodPolicy scope]', 1)[1]
                    scopes.append(json.loads(payload.strip().splitlines()[0]))
        assert scopes
        assert all(scope == {'project_id': harness.project.id, 'active': False, 'allowed_methods': []}
                   for scope in scopes)
        assert not any(e.type == "tool.blocked" and e.data.get("stage") == "method_policy" for e in harness.events(agent))
        assert any(e.type == "tool.result_recorded" for e in harness.events(agent))
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_tool_progress_persistence_failure_fails_run_without_retry(tmp_path, monkeypatch):
    """杠杆：真实工具适配器、进度事件落盘、Agent fail-fast 分类。"""
    provider = ScriptedProvider(default=[Step(tools=[("stop", {"reason": "done"})])])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    original = harness.store.append_event

    def append(event):
        if event.type == "tool.progress":
            raise OSError("fixture disk full")
        original(event)

    monkeypatch.setattr(harness.store, "append_event", append)
    try:
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(agent)
        rows = harness.run_rows(agent)
        assert len(rows) == 1
        assert rows[0]["outcome"] == "failed", harness.describe(agent)
        assert rows[0]["failure_kind"] == "event_persistence"
        events = harness.events(agent)
        assert len([e for e in events if e.type == "tool.requested"]) == 1
        assert not any(e.type == "run.retry" for e in events)
        assert not any(e.type == "tool.result_recorded" for e in events)
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_plain_qa_ends_with_declared_basis(tmp_path):
    """普通问答：纯文本收尾（**默认 invocation protocol**），完成依据 = declared。

    杠杆：默认协议 + 结束门禁。改默认 protocol 或收尾判定，这条会先红。
    """
    provider = ScriptedProvider(default=[Step(text="All done: nothing to compute.", stop=True)])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await harness.spawn("coordinator")  # 不固定协议：走默认
        await harness.wait_terminal(agent)

        from cloudra.services.api_v2.views import agent_dict

        rows = harness.run_rows(agent)
        assert [row["outcome"] for row in rows] == ["succeeded"]
        assert harness.provider.call_count() == 1
        completion = agent_dict(harness.core, agent)["completion"]
        assert completion is not None, harness.describe(agent)
        assert completion["completion_basis"] == "declared"
        # 设计口径：declared 只表示「模型自述结束」，不是已验证完成。
        assert completion["verification_label"] == "unverified"
    finally:
        await harness.aclose()


# -------------------------------------------------- DAG：候选、逐文件审查、门禁


def _seed_selected_step_endpoints(project_id: str) -> None:
    """只预置有结构支持的两端；步骤和交付范围仍由真实 proposal 工具创建。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import AddNode, GraphActor, MutationBatch, OccurrenceNode
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    store = DagStore(ConversationDB(project_id).init())
    store.ensure_bundle("scenario-endpoints")
    result = DagEngine(store).apply_batch(MutationBatch(
        session_id="scenario-endpoints", actor=GraphActor.HARNESS,
        actor_id="scenario-endpoints", base_revisions=store.load_bundle().revisions,
        rationale="the two endpoint structures are available",
        operations=[
            AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                node_id="r", label="R", role="reactant",
                evidence_level="structure_supported")),
            AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                node_id="p", label="P", role="product",
                evidence_level="structure_supported")),
        ],
    ))
    assert result.accepted


def _propose_selected_ab() -> Step:
    return Step(tools=[("dag_propose_mechanism", {
        "rationale": "selected R to P transformation",
        "steps": [{"name": "AB", "from": "R", "to": "P"}],
        "delivery_targets": ["AB"],
    })])


@pytest.mark.asyncio
async def test_guided_complete_waits_for_selected_step_review_and_evidence(tmp_path):
    """A selected step with a live pending draft and stages cannot claim complete."""
    attempt_complete = asyncio.Event()
    hold_after_gate = asyncio.Event()
    provider = ScriptedProvider(by_role={
        "coordinator": [
            _propose_selected_ab(),
            # Drain the Supervisor's earlier draft notification in a normal turn
            # before the explicit stop is audited.
            Step(wait_for=attempt_complete, tools=[('dag_delivery_report', {})]),
            Step(tools=[("stop", {
                "delivery_disposition": "complete",
            })]),
            Step(wait_for=hold_after_gate, text="continue work"),
        ],
        "supervisor": [Step(text="review pending", stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        await asyncio.to_thread(_seed_selected_step_endpoints, harness.project.id)
        agent = await harness.spawn(
            "coordinator", protocol="traditional", orchestration_mode="dag_guided"
        )
        await harness.wait_for(
            lambda: any(t["tool_name"] == "dag_propose_mechanism" and t["status"] == "completed"
                        for t in harness.tool_events(agent)),
            "selected AB proposal",
        )
        await harness.wait_for(
            lambda: any(a.role_id == "supervisor" and a.state.value == "succeeded"
                        for a in harness.core.agents.values()),
            "Supervisor idle after the proposal",
        )
        from cloudra.dag.controller import DagController
        from cloudra.persistence.database import ConversationDB

        db = await asyncio.to_thread(lambda: ConversationDB(harness.project.id).init())
        report = await asyncio.to_thread(
            DagController(db, agent.id, "dag_guided", conversation_id=harness.project.id).delivery_report
        )
        assert report.complete is False
        codes = {gap.code for gap in report.unresolved}
        assert {"pending_scope_review", "missing_stage_evidence"} <= codes

        attempt_complete.set()
        await harness.wait_for(
            lambda: any(e.type == "agent.completion_gate" and e.data.get("explicit_stop")
                        for e in harness.events(agent)),
            "explicit complete gate for selected AB",
        )
        gate = next(e.data for e in harness.events(agent)
                    if e.type == "agent.completion_gate" and e.data.get("explicit_stop"))
        assert gate["action"] == "continue_work", (gate, harness.describe(agent))
        assert gate["basis"] is None
        assert agent.state.value != "succeeded"
    finally:
        attempt_complete.set()
        hold_after_gate.set()
        await harness.aclose()


def _seed_synthetic_step_science(project_id: str) -> None:
    """Explicit parser/runtime fixtures, not captured quantum-calculation evidence."""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.models import AttachRef, GraphActor, MutationBatch, UpdateNode
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB
    from tests.test_irc_endpoint_optimization import write_lineage_bundle

    workspace = _workspace(project_id)
    # Reuse the strict-lineage tests' synthetic IRC -> Opt -> Freq geometry
    # chain. The captured NU3 archive has no endpoint Opt logs and cannot
    # establish this scenario's complete-evidence branch.
    bundle = write_lineage_bundle(workspace)
    store = DagStore(ConversationDB(project_id).init())
    operations = []
    for name, role in [('r', 'reactant'), ('p', 'product')]:
        operations.append(UpdateNode(op="update_node", graph="delivery", node_id=name,
            changes={"smiles": bundle[f'{role}_smiles']}))
        for stage in ('opt', 'freq'):
            snapshot = snapshot_evidence_file(bundle[f'{role}_{stage}'], workspace)
            ref = store.register_evidence("scenario-endpoints", f'{role}_{stage}',
                snapshot.model_dump(mode="json"), source_type="file")
            operations.append(AttachRef(op="attach_ref", graph="delivery", target_type="node", target_id=name, ref=ref))
    result = DagEngine(store).apply_batch(MutationBatch(
        session_id="scenario-endpoints", actor=GraphActor.HARNESS, actor_id="scenario-endpoints",
        base_revisions=store.load_bundle().revisions,
        rationale="bind synthetic parser-fixture endpoint Opt/Freq chains", operations=operations,
    ))
    assert result.accepted


@pytest.mark.asyncio
@pytest.mark.parametrize("complete_evidence", [False, True], ids=["missing-irc", "scientific-evidence"])
async def test_guided_file_verdict_wakes_coordinator_and_enforces_scientific_completion(
    tmp_path, monkeypatch, complete_evidence
):
    """A verdict wakes once; only scientifically supported files permit complete."""
    submit_evidence = asyncio.Event()
    attempt_partial = asyncio.Event()
    review_file = asyncio.Event()
    finish_supervisor = asyncio.Event()
    attempt_complete = asyncio.Event()
    hold_after_gate = asyncio.Event()
    review_final = asyncio.Event()
    final_verdict = Step(wait_for=review_final)
    ts = Path(__file__).parent / "fixtures" / "benchmark_synthetic" / "ts_freq.out"
    # The synthetic TS log contains both converged Opt and one-imaginary Freq
    # blocks; the real validators must still prove their geometry association.
    files = {"ts_file": "ts.out", "opt_file": "ts.out", "irc_file": "irc.out"} if complete_evidence else {"ts_file": ts.name}
    provider = ScriptedProvider(by_role={
        "coordinator": [
            _propose_selected_ab(),
            Step(wait_for=submit_evidence, tools=[("dag_submit_step_evidence", {
                "step_name": "AB", **files,
                "reaction_coordinate_description": "selected transition",
            })]),
            Step(wait_for=attempt_partial, tools=[("stop", {
                "delivery_disposition": "partial",
            })]),
            Step(wait_for=attempt_complete, tools=[("dag_delivery_report", {})]),
            Step(tools=[("stop", {"delivery_disposition": "complete"})]),
            *([Step(tools=[("stop", {"delivery_disposition": "complete"})])] if complete_evidence else [
                Step(tools=[("dag_delivery_report", {})]),
                Step(wait_for=hold_after_gate, text="collect missing IRC direction evidence"),
            ]),
        ],
        "supervisor": [
            Step(tools=[("dag_accept_mechanism", {"verdict": "accept"})]),
            Step(text="draft reviewed", stop=True),
            Step(text="file review queued", stop=True),
            Step(wait_for=review_file, tools=[("dag_review_step", {
                "step_name": "AB", "verdict": "supported",
                "rationale": "the submitted file supports the selected transition",
            })]),
            Step(wait_for=finish_supervisor, text="file reviewed", stop=True),
            *([final_verdict, Step(stop=True)] if complete_evidence else []),
        ],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        await _set_supervisor_traditional(harness)
        await asyncio.to_thread(_seed_selected_step_endpoints, harness.project.id)
        workspace = _workspace(harness.project.id)
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ts, workspace / ts.name)
        if complete_evidence:
            await asyncio.to_thread(_seed_synthetic_step_science, harness.project.id)
        coordinator = await harness.spawn(
            "coordinator", protocol="traditional", orchestration_mode="dag_guided"
        )
        await harness.wait_for(
            lambda: any(t["tool_name"] == "dag_accept_mechanism" and t["status"] == "completed"
                        for a in harness.core.agents.values() if a.role_id == "supervisor"
                        for t in harness.tool_events(a)),
            "Supervisor acceptance of the selected draft",
        )
        await harness.wait_for(
            lambda: any(a.role_id == "supervisor" and a.state.value == "succeeded"
                        for a in harness.core.agents.values()),
            "Supervisor idle after draft review",
        )
        submit_evidence.set()
        await harness.wait_for(
            lambda: any(t["tool_name"] == "dag_submit_step_evidence" and t["status"] == "completed"
                        for t in harness.tool_events(coordinator)),
            "AB evidence submission",
        )
        submitted = next(t for t in harness.tool_events(coordinator)
                         if t["tool_name"] == "dag_submit_step_evidence")
        assert submitted["is_success"], harness.describe(coordinator)
        checks = submitted["result_data"]["result"]["scientific_checks"]
        assert checks["ts_opt"]["status"] == checks["frequency"]["status"] == "passed"
        assert checks["short_irc"]["status"] == ("passed" if complete_evidence else "incomplete")
        review_id = submitted["result_data"]["result"]["review_id"]
        await harness.wait_for(
            lambda: any(a.role_id == "supervisor" and a.state.value == "succeeded"
                        and len(harness.run_rows(a)) >= 2
                        for a in harness.core.agents.values()),
            "Supervisor idle after file submission",
        )
        attempt_partial.set()
        await harness.wait_for(
            lambda: coordinator.state.value == "waiting_approval",
            "Coordinator parked on the partial exit request",
        )
        parked = [e for e in harness.events(coordinator) if e.type == "agent.state_changed"]
        assert parked[-1].data["reason"] == "wait_review"
        assert not any(row["outcome"] == "succeeded" for row in harness.run_rows(coordinator))
        child_reports_at_park = len(harness.child_reports(coordinator))

        from cloudra.runtime_v2 import supervision

        actual_flush = supervision.flush_review_notifications
        flush_counts: list[int] = []

        async def observed_flush(core, project_id, **kwargs):
            count = await actual_flush(core, project_id, **kwargs)
            flush_counts.append(count)
            return count

        monkeypatch.setattr(supervision, "flush_review_notifications", observed_flush)
        review_file.set()
        await harness.wait_for(
            lambda: any(t["tool_name"] == "dag_review_step" and t["status"] == "completed"
                        for a in harness.core.agents.values() if a.role_id == "supervisor"
                        for t in harness.tool_events(a)),
            "per-file Supervisor verdict",
        )
        await harness.wait_for(
            lambda: coordinator.state.value == "running" and provider.call_count("coordinator") >= 4,
            "Coordinator resumed on the verdict and entered a new provider turn",
        )
        from cloudra.dag.controller import DagController
        from cloudra.dag.store import DagStore
        from cloudra.persistence.database import ConversationDB
        db = await asyncio.to_thread(lambda: ConversationDB(harness.project.id).init())
        store = DagStore(db)
        request = await asyncio.to_thread(store.get_review_request, review_id)
        assert request is not None and request.state == "resolved"
        snapshot = await asyncio.to_thread(store.load_snapshot)
        edge = next(edge for edge in snapshot.delivery.edges if edge.name == "AB")
        assert {stage.kind.value for stage in edge.stages if stage.required} == {
            "ts_opt", "frequency", "short_irc",
        }
        decision = await asyncio.to_thread(store.get_review_decision_for_request, review_id)
        assert decision is not None and decision.verdict == "accept"
        assert flush_counts == [1]
        assert await actual_flush(harness.core, harness.project.id) == 0
        delivered = [data for data in harness.messages(coordinator)
                     if data.get("sender") == "supervisor"
                     and review_id in str(data.get("content") or "")]
        assert len(delivered) == 1, harness.describe(coordinator)
        def _notification_rows():
            with db.connect() as con:
                return con.execute(
                    "SELECT recipient_session_id, state FROM dag_review_notifications "
                    "WHERE request_id = ?", (review_id,),
                ).fetchall()

        assert await asyncio.to_thread(_notification_rows) == [(coordinator.id, "sent")]
        assert len(harness.child_reports(coordinator)) == child_reports_at_park
        states = [e.data.get("to") for e in harness.events(coordinator)
                  if e.type == "agent.state_changed"]
        assert "running" in states[states.index("waiting_approval") + 1:]
        report = await asyncio.to_thread(
            DagController(db, coordinator.id, "dag_guided", conversation_id=harness.project.id).delivery_report
        )
        assert report.complete is complete_evidence
        if complete_evidence:
            assert any(gate.code == "supervisor_evidence_accepted" for gate in report.satisfied)
        else:
            assert {"missing_stage_evidence", "scientific_check_incomplete"} <= {
                gap.code for gap in report.unresolved
            }
            assert any(gap.code == "scientific_check_incomplete" and gap.target_id == edge.edge_id
                       and gap.detail.startswith("short_irc:")
                       for gap in report.unresolved)
            accepted = next(gate for gate in report.satisfied
                            if gate.code == "supervisor_evidence_accepted"
                            and gate.target_id == edge.edge_id)
            assert "ts_opt" in accepted.detail and "frequency" in accepted.detail
            assert "short_irc" not in accepted.detail
            pending = next(gap for gap in report.unresolved
                           if gap.code == "missing_stage_evidence"
                           and gap.target_id == edge.edge_id)
            assert "short_irc" in pending.detail
            assert "ts_opt" not in pending.detail and "frequency" not in pending.detail
            assert decision.next_action

        finish_supervisor.set()
        await harness.wait_for(
            lambda: any(a.role_id == "supervisor" and a.state.value == "succeeded"
                        and len(harness.run_rows(a)) >= 3
                        for a in harness.core.agents.values()),
            "Supervisor idle before the final delivery attempt",
        )
        attempt_complete.set()
        from cloudra.runtime_v2.completion import completion_summary

        if complete_evidence:
            await harness.wait_for(lambda: coordinator.state.value == "waiting_approval",
                                   "whole complete delivery awaits final review")
            final_request = next(r for r in await asyncio.to_thread(store.list_review_requests, "queued")
                                 if r.kind == "exit" and r.proposal["disposition"] == "complete")
            final_verdict.tools = [("dag_review_evidence", {"request_id": final_request.request_id,
                "verdict": "accept", "reason": "the whole proposed complete delivery is supported"})]
            review_final.set()
            await harness.wait_terminal(coordinator)
            completion = completion_summary(harness.events(coordinator))
            assert completion["completion_basis"] == "scope_completed"
            assert completion["verification_label"] == "scope_completed"
        else:
            await harness.wait_for(
                lambda: any(e.type == "agent.completion_gate" and e.data.get("explicit_stop")
                            and e.data.get("action") == "continue_work" for e in harness.events(coordinator)),
                "scientific gap blocks explicit complete after Supervisor acceptance",
            )
            gate = next(e for e in harness.events(coordinator)
                        if e.type == "agent.completion_gate" and e.data.get("explicit_stop")
                        and e.data.get("action") == "continue_work")
            assert gate.data["basis"] is None
            await harness.wait_for(
                lambda: len([t for t in harness.tool_events(coordinator)
                             if t["tool_name"] == "dag_delivery_report" and t["status"] == "completed"]) == 2,
                "Coordinator rechecks scientific gaps after the rejected exit",
            )
            repair_request = [e for e in harness.events(coordinator)
                              if e.type == "tool.requested"
                              and e.data.get("tool_name") == "dag_delivery_report"][-1]
            assert repair_request.seq > gate.seq
            repair_report = [t for t in harness.tool_events(coordinator)
                             if t["tool_name"] == "dag_delivery_report"][-1]["result_data"]["result"]
            assert repair_report["complete"] is False
            assert any(gap["code"] == "scientific_check_incomplete" and "short_irc" in gap["detail"]
                       for gap in repair_report["unresolved"])
            assert coordinator.state.value == "running"
            assert not any(row["outcome"] == "succeeded" for row in harness.run_rows(coordinator))
            assert completion_summary(harness.events(coordinator)) is None
    finally:
        submit_evidence.set()
        attempt_partial.set()
        review_file.set()
        finish_supervisor.set()
        attempt_complete.set()
        hold_after_gate.set()
        review_final.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_guided_candidate_is_usable_while_review_is_open(tmp_path, monkeypatch):
    """真实 Coordinator 工具流水线：候选图可读，待审范围阻止完整交付。"""
    finish = asyncio.Event()
    supervisor_finish = asyncio.Event()
    provider = ScriptedProvider(by_role={
        "coordinator": [
            Step(tools=[("dag_propose_mechanism", {
                "rationale": "A to B hypothesis",
                "species": [{"name": "A"}, {"name": "B"}],
                "steps": [{"name": "AB", "from": "A", "to": "B"}],
                "delivery_targets": ["AB"],
            })]),
            Step(tools=[("submit_compute_job", {
                "input_file": "he.xyz", "job_type": "xtb", "cpus": 1,
                "is_async": True, "execution_backend": "local",
            })]),
            Step(tools=[("dag_delivery_report", {})]),
            Step(wait_for=finish, text="candidate recorded", stop=True),
        ],
        "supervisor": [Step(wait_for=supervisor_finish, text="review remains open", stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        fixture = Path(__file__).parent / "fixtures" / "compute_backends" / "xtb" / "he.xyz"
        workspace = _workspace(harness.project.id)
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture, workspace / fixture.name)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        xtb_probe = bin_dir / "xtb"
        xtb_probe.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        xtb_probe.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
        agent = await harness.spawn(
            "coordinator", protocol="traditional", orchestration_mode="dag_guided"
        )
        await harness.wait_for(
            lambda: any(t["tool_name"] == "dag_delivery_report" and t["status"] == "completed"
                        for t in harness.tool_events(agent)),
            "candidate proposal and delivery report tools",
        )
        tools = harness.tool_events(agent)
        assert [t["tool_name"] for t in tools[:3]] == [
            "dag_propose_mechanism", "submit_compute_job", "dag_delivery_report",
        ]
        assert all(t["started"] and not t["blocked"] and t["is_success"] for t in tools[:3]), harness.describe(agent)
        assert tools[0]["result_data"]["result"]["state"] == "open"
        assert tools[2]["result_data"]["result"]["complete"] is False
        assert any(g["code"] == "pending_scope_review"
                   for g in tools[2]["result_data"]["result"]["unresolved"])

        from cloudra.persistence.database import ComputeDB

        async with ComputeDB().aconnect() as con:
            jobs = (await (await con.execute(
                "SELECT jobtype, state FROM compute_jobs"
            )).fetchall())
        assert jobs == [("xtb", "ready")]

        from cloudra.dag.store import DagStore
        from cloudra.persistence.database import ConversationDB

        store = await asyncio.to_thread(lambda: DagStore(ConversationDB(harness.project.id).init()))
        graph = await asyncio.to_thread(store.load_snapshot)
        assert {edge.name for edge in graph.delivery.edges} == {"AB"}
        assert (await asyncio.to_thread(store.latest_open_draft)) is not None

        supervisor_finish.set()
        finish.set()
        await harness.wait_for(
            lambda: any(e.type == "agent.completion_gate" for e in harness.events(agent)),
            "pending guided completion gate",
        )
        gates = [e.data for e in harness.events(agent) if e.type == "agent.completion_gate"]
        assert all(g.get("basis") not in {"dag_verified", "supervisor_supported"} for g in gates)
    finally:
        finish.set()
        supervisor_finish.set()
        await harness.aclose()


def _seed_guided_step_for_file_review(project_id: str, *, complete: bool = False) -> None:
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ClaimSpec,
        ElementaryStepEdge,
        GraphActor,
        MechanismDraft,
        MutationBatch,
        OccurrenceNode,
        StageState,
    )
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    store = DagStore(ConversationDB(project_id).init())
    store.ensure_bundle("scenario-seed")
    result = DagEngine(store).apply_batch(MutationBatch(
        session_id="scenario-seed", actor=GraphActor.HARNESS,
        actor_id="scenario-seed", base_revisions=store.load_bundle().revisions,
        rationale="selected transformation awaiting TS file review",
        operations=[
            AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                node_id="r", label="R", role="reactant", evidence_level="structure_supported")),
            AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                node_id="p", label="P", role="product", evidence_level="structure_supported")),
            AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
                edge_id="step1", name="step1", source_node_id="r", target_node_id="p",
                evidence_level="endpoint_supported" if complete else "proposed",
                stages=[] if complete else [
                    StageState(kind="ts_opt"), StageState(kind="frequency")
                ],
            )),
        ],
    ))
    assert result.accepted
    store.save_draft(
        MechanismDraft(
            operations=[], rationale="selected step1", state="accepted",
            claim_spec=ClaimSpec(kind="mechanism", scope={"targets": ["step1"]}),
        ), actor_id="scenario-seed",
    )


@pytest.mark.asyncio
async def test_guided_expanded_scope_is_a_real_completion_debt(tmp_path):
    """真实工具调用：探索 BC 时 AB 可交付，明示纳入 BC 后门禁立即检查新范围。"""
    finish = asyncio.Event()
    supervisor_finish = asyncio.Event()
    provider = ScriptedProvider(by_role={
        "coordinator": [
            Step(tools=[("dag_propose_mechanism", {
                "rationale": "explore B to C without changing this delivery",
                "species": [{"name": "C"}],
                "steps": [{"name": "BC", "from": "P", "to": "C"}],
            })]),
            Step(tools=[("dag_delivery_report", {})]),
            Step(tools=[("dag_propose_mechanism", {
                "rationale": "include B to C in the selected conclusion",
                "delivery_targets": ["step1", "BC"],
            })]),
            Step(tools=[("dag_delivery_report", {})]),
            Step(wait_for=finish, tools=[("dag_delivery_report", {})]),
            Step(tools=[("stop", {"delivery_disposition": "complete"})]),
        ],
        "supervisor": [Step(wait_for=supervisor_finish, text="review pending", stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        await asyncio.to_thread(
            _seed_guided_step_for_file_review, harness.project.id, complete=True
        )
        agent = await harness.spawn(
            "coordinator", protocol="traditional", orchestration_mode="dag_guided"
        )
        await harness.wait_for(
            lambda: len([t for t in harness.tool_events(agent)
                         if t["tool_name"] == "dag_delivery_report" and t["status"] == "completed"]) == 2,
            "reports before and after scope declaration",
        )
        tools = harness.tool_events(agent)
        assert [t["tool_name"] for t in tools[:4]] == [
            "dag_propose_mechanism", "dag_delivery_report",
            "dag_propose_mechanism", "dag_delivery_report",
        ]
        assert all(t["started"] and not t["blocked"] and t["is_success"] for t in tools[:4]), harness.describe(agent)
        assert tools[0]["result_data"]["result"]["state"] == "open"
        assert tools[1]["result_data"]["result"]["complete"] is True
        assert tools[2]["result_data"]["result"]["state"] == "open"
        expanded = tools[3]["result_data"]["result"]
        assert expanded["complete"] is False
        assert any(g["code"] == "pending_scope_review" for g in expanded["unresolved"])

        from cloudra.dag.store import DagStore
        from cloudra.persistence.database import ConversationDB

        store = await asyncio.to_thread(lambda: DagStore(ConversationDB(harness.project.id).init()))
        graph = await asyncio.to_thread(store.load_snapshot)
        assert {edge.name for edge in graph.delivery.edges} == {"step1", "BC"}

        supervisor_finish.set()
        await harness.wait_for(
            lambda: any(
                a.role_id == "supervisor" and a.state.value == "succeeded"
                for a in harness.core.agents.values()
            ),
            "Supervisor idle before complete attempt",
        )
        assert not harness.child_reports(agent)
        finish.set()
        await harness.wait_for(
            lambda: any(e.type == "agent.completion_gate" and e.data.get("explicit_stop")
                        for e in harness.events(agent)),
            "explicit expanded-scope completion gate",
        )
        gate = next(e.data for e in harness.events(agent)
                    if e.type == "agent.completion_gate" and e.data.get("explicit_stop"))
        assert gate["action"] == "continue_work", (gate, harness.describe(agent))
        assert gate["explicit_stop"] is True
        assert gate["basis"] is None
        assert any(g["code"] == "pending_scope_review" for g in expanded["unresolved"])
    finally:
        finish.set()
        supervisor_finish.set()
        await harness.aclose()


async def _set_supervisor_traditional(harness: ScenarioHarness) -> None:
    from cloudra.runtime_v2.schemas import Command

    result = await harness.bus.execute(Command(
        type="role.update", target={"role_id": "supervisor"},
        payload={"default_settings": {
            "orchestration_mode": "dag_guided", "invocation_protocol": "traditional",
        }},
    ))
    assert result.accepted


@pytest.mark.asyncio
async def test_guided_real_file_review_finishes_with_supervisor_basis(tmp_path):
    """真实 runtime、逐文件工具和事件：接受只给 Supervisor 依据，不改机器阶段。"""
    review = asyncio.Event()
    finish = asyncio.Event()
    review_final = asyncio.Event()
    final_verdict = Step(wait_for=review_final)
    ts = Path(__file__).parent / "fixtures" / "benchmark_synthetic" / "ts_freq.out"
    provider = ScriptedProvider(by_role={
        "coordinator": [
            Step(tools=[("dag_submit_step_evidence", {
                "step_name": "step1", "ts_file": ts.name,
                "reaction_coordinate_description": "scripted selected transition",
            })]),
            Step(tools=[("dag_delivery_report", {})]),
            Step(wait_for=finish, text="submit the selected result", stop=True),
        ],
        "supervisor": [
            Step(wait_for=review, tools=[("dag_review_step", {
                "step_name": "step1", "verdict": "supported",
                "rationale": "the submitted TS file supports the selected step",
            })]),
            Step(text="review complete", stop=True),
            final_verdict, Step(stop=True),
        ],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        await _set_supervisor_traditional(harness)
        workspace = _workspace(harness.project.id)
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ts, workspace / ts.name)
        await asyncio.to_thread(_seed_guided_step_for_file_review, harness.project.id)
        agent = await harness.spawn(
            "coordinator", protocol="traditional", orchestration_mode="dag_guided"
        )
        await harness.wait_for(
            lambda: any(t["tool_name"] == "dag_delivery_report" and t["status"] == "completed"
                        for t in harness.tool_events(agent)),
            "file submission and pre-review report",
        )
        before = harness.tool_events(agent)
        assert [t["tool_name"] for t in before[:2]] == [
            "dag_submit_step_evidence", "dag_delivery_report",
        ]
        assert all(t["started"] and not t["blocked"] and t["is_success"] for t in before[:2]), harness.describe(agent)
        assert before[1]["result_data"]["result"]["complete"] is False

        review.set()
        await harness.wait_for(
            lambda: any(
                t["tool_name"] == "dag_review_step" and t["status"] == "completed"
                for supervisor in harness.core.agents.values()
                if supervisor.role_id == "supervisor"
                for t in harness.tool_events(supervisor)
            ),
            "Supervisor file verdict",
        )
        await harness.wait_for(
            lambda: all(a.state.value == "succeeded" for a in harness.core.agents.values()
                        if a.role_id == "supervisor"),
            "Supervisor run completion",
        )
        from cloudra.dag.controller import DagController
        from cloudra.dag.store import DagStore
        from cloudra.persistence.database import ConversationDB

        db = await asyncio.to_thread(lambda: ConversationDB(harness.project.id).init())
        store = DagStore(db)
        report = await asyncio.to_thread(
            DagController(db, agent.id, "dag_guided", conversation_id=harness.project.id).delivery_report
        )
        assert report.complete
        graph = await asyncio.to_thread(store.load_snapshot)
        assert [(s.kind.value, s.status.value) for s in graph.delivery.edges[0].stages] == [
            ("ts_opt", "pending"), ("frequency", "pending"),
        ]
        finish.set()
        await harness.wait_for(lambda: agent.state.value == "waiting_approval",
                               "whole final delivery awaits review")
        final_request = next(r for r in await asyncio.to_thread(store.list_review_requests, "queued") if r.kind == "exit")
        final_verdict.tools = [("dag_review_evidence", {"request_id": final_request.request_id,
            "verdict": "accept", "reason": "the whole proposed scoped delivery is supported"})]
        review_final.set()
        await harness.wait_terminal(agent)
        from cloudra.runtime_v2.completion import completion_summary

        completion = completion_summary(harness.events(agent))
        assert completion["completion_basis"] == "scope_completed"
        assert completion["verification_label"] == "scope_completed"
    finally:
        review.set()
        finish.set()
        review_final.set()
        await harness.aclose()


# ------------------------------------------------- 2. small_mol：技能 → 计算入口


@pytest.mark.parametrize(
    ("job_type", "required_bin", "input_name"),
    [
        ("gaussian", "g16", "he.gjf"),
        ("orca", "orca", "he.inp"),
        ("xtb", "xtb", "he.xyz"),
        ("cp2k", "cp2k", "he.inp"),
        ("vasp", "vasp_std", "INCAR"),
    ],
)
@pytest.mark.asyncio
async def test_small_mol_loads_skill_before_allowed_compute_entry(
    tmp_path, monkeypatch, job_type, required_bin, input_name
):
    """small_mol：先加载技能，再按各后端原生输入走异步计算入口。

    杠杆：角色权限矩阵 + 工具目录。权限收紧了这条会在「工具被拒」处红。
    PATH 中的空壳程序只供准入探测；``is_async`` 保证它们绝不会执行。
    """
    fixture_dir = Path(__file__).parent / "fixtures" / "compute_backends" / job_type
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    probe = bin_dir / required_bin
    probe.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    probe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    provider = ScriptedProvider(by_role={})
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        workspace = _workspace(harness.project.id)
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copytree(fixture_dir, workspace, dirs_exist_ok=True)
        provider.script(
            "small_mol",
            Step(tools=[("get_skill", {"skill_name": "dft-calculation"})]),
            Step(
                tools=[
                    (
                        "submit_compute_job",
                        {
                            "input_file": input_name,
                            "job_type": job_type,
                            "cpus": 1,
                            "is_async": True,
                            "execution_backend": "local",
                        },
                    )
                ]
            ),
            Step(text="Job submitted.", stop=True),
        )
        agent = await harness.spawn("small_mol", protocol="traditional")
        await harness.wait_terminal(agent)

        tools = harness.tool_events(agent)
        by_name = {tool["tool_name"]: tool for tool in tools}
        names = [tool["tool_name"] for tool in tools]
        assert names.index("get_skill") < names.index("submit_compute_job")
        # 技能确实读到了内容（权限 + 技能目录都没挡）。
        assert by_name["get_skill"]["is_success"] is True
        # 计算入口**被策略放行**：工具真的开始执行，没有被 permission/method 拦下。
        assert by_name["submit_compute_job"]["started"] is True
        assert by_name["submit_compute_job"]["blocked"] is False

        from cloudra.persistence.database import ComputeDB

        async with ComputeDB().aconnect() as con:
            cursor = await con.execute("SELECT jobtype, state, path FROM compute_jobs")
            jobs = await cursor.fetchall()
        assert len(jobs) == 1, f"expected exactly one compute job, got {jobs}"
        assert jobs[0][0] == job_type
        assert jobs[0][1] == "ready", jobs
        assert Path(jobs[0][2]).name == input_name
    finally:
        await harness.aclose()


# --------------------------------------------------- 3. 异步子 Agent：回传一次


@pytest.mark.asyncio
async def test_async_subagent_reports_once_and_wakes_parent(tmp_path):
    """异步子 Agent：parent 先收轮，child 完成后**恰好一次**回传并唤醒 parent。

    杠杆：消息投递/唤醒语义（dispatcher 的 WakePolicy）+ 子 Agent 回报 manifest。
    """
    release_child = asyncio.Event()
    provider = ScriptedProvider(
        by_role={
            "coordinator": [
                Step(tools=[("subagent_launcher", {"role_id": "explorer", "query": "look around", "is_wait": False})]),
                Step(text="continuing on the main line", stop=True),
            ],
            "explorer": [Step(text="explored the workspace", stop=True, wait_for=release_child)],
        }
    )
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        parent = await harness.spawn("coordinator", protocol="traditional")
        # 本场景验证停下后的唤醒；若 child 提前回报，parent 可在同一 run
        # 正常消费，不能依赖两次模型调用的相对速度来强求第二个 run。
        await harness.wait_terminal(parent)
        release_child.set()
        await harness.wait_for(
            lambda: len(harness.child_reports(parent)) == 1,
            "exactly one child completion report",
        )
        reports = harness.child_reports(parent)
        child_id = reports[0]["manifest"]["session_id"]
        assert reports[0]["manifest"]["role_id"] == "explorer"
        assert reports[0]["manifest"]["state"] == "succeeded"

        # 恰好一次：回传后 parent 被唤醒开新 run，且第二个 run 由这条消息驱动。
        await harness.wait_for(
            lambda: len(harness.run_rows(parent)) >= 2,
            "parent woke up for the child report",
        )
        assert [row["outcome"] for row in harness.run_rows(parent)][:2] == ["succeeded", "succeeded"]
        assert len([r for r in harness.child_reports(parent)]) == 1

        # child 侧：一次 spawn、一次终态（不重复派发）。
        children = harness.children_of(parent)
        assert [c.id for c in children] == [child_id]
        assert children[0].state.value == "succeeded"
    finally:
        await harness.aclose()


# ------------------------------------------------- 4. provider 故障：重试与 fail-fast


@pytest.mark.asyncio
async def test_provider_transient_retries_within_budget(tmp_path):
    """provider 暂态 5xx：按预算原地重试，恢复后同一个 run 正常收尾。

    杠杆：重试预算 + 可重试判定。
    """
    provider = ScriptedProvider(
        default=[
            Step(error=ProviderFault("gateway hiccup", status_code=502)),
            Step(error=ProviderFault("gateway hiccup again", status_code=503)),
            Step(text="recovered", stop=True),
        ]
    )
    harness = await ScenarioHarness.start(
        tmp_path, provider=provider, retry_backoff=(0.01,), max_turn_retries=3
    )
    try:
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(agent)
        assert harness.provider.call_count() == 3, "两次失败 + 一次成功"
        rows = harness.run_rows(agent)
        assert [row["outcome"] for row in rows] == ["succeeded"]
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_provider_permanent_4xx_fails_fast(tmp_path):
    """provider 永久 4xx：不重试、立即失败，并落结构化 failure_kind。

    杠杆：fail-fast 分类（failures.classify_failure）+ run.finished 载荷。
    """
    provider = ScriptedProvider(
        default=[Step(error=ProviderFault("invalid api key", status_code=401))]
    )
    harness = await ScenarioHarness.start(tmp_path, provider=provider, max_turn_retries=3)
    try:
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(agent)
        assert harness.provider.call_count() == 1, "4xx 不得重试"
        rows = harness.run_rows(agent)
        assert [row["outcome"] for row in rows] == ["failed"]
        assert rows[0]["failure_kind"] == "provider_permanent"
    finally:
        await harness.aclose()


# --------------------------------------------------------- 6. unattended 不等待


@pytest.mark.asyncio
async def test_unattended_never_enters_waiting_input(tmp_path):
    """unattended：破坏性工具不放行，但**绝不**进入 waiting_input 等人类。

    杠杆：unattended 策略 + 审批边界。
    """
    provider = ScriptedProvider(
        default=[
            Step(tools=[("ask_user", {"question": "Which conformer should I optimize?"})]),
            Step(text="proceeding with documented defaults", stop=True),
        ]
    )
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await harness.spawn("coordinator", protocol="traditional", unattended=True)
        await harness.wait_terminal(agent)

        states = [
            event.data.get("to")
            for event in harness.events(agent)
            if event.type == "agent.state_changed"
        ]
        assert "waiting_input" not in states, states
        # ask_user 被 unattended 策略拦下（结构化 blocked，而不是挂起等人）。
        tools = harness.tool_events(agent)
        assert [tool["tool_name"] for tool in tools] == ["ask_user"], harness.describe(agent)
        assert tools[0]["blocked"] is True and tools[0]["block_stage"] == "unattended"
        assert tools[0]["started"] is False, "被拦下的调用不得真的执行"
        assert agent.state.value == "succeeded"
    finally:
        await harness.aclose()


# --------------------------------------------------------------- 8. 重启语义


@pytest.mark.asyncio
async def test_restart_closes_old_local_lifecycles_when_user_message_resumes_agent(tmp_path):
    """恢复只终结旧 run；用户发消息后才收口旧工具/程序，且新回复正常完成。

    杠杆：持久化恢复、CommandBus 消息唤醒、旧工具/程序收口、真实 runner。
    """
    from cloudra.runtime_v2.schemas import AgentState, Command
    from tests.agent_scenarios import interrupted_program_fixture

    release_original_reply = asyncio.Event()
    harness = await ScenarioHarness.start(
        tmp_path, provider=ScriptedProvider(default=[Step(wait_for=release_original_reply, stop=True)]),
    )
    crash_store_name = "restart-crash.db"
    try:
        agent = await harness.spawn("coordinator")
        await harness.wait_for(lambda: harness.provider.call_count() == 1, "original run enters provider")
        old_run_id = agent.current_run.run_id
        for draft in interrupted_program_fixture(agent):
            await harness.core.event_writer.commit(draft)
        before_crash = await asyncio.to_thread(harness.events, agent)
        old_tool = next(e for e in before_crash if e.type == "tool.started")
        old_program = next(e for e in before_crash if e.type == "program.started")
        assert not any(e.type in {"tool.finished", "program.finished"} for e in before_crash)
        # Each event has finished its store write. Copy before graceful local
        # teardown, whose cancellation terminals must not repair the crash fixture.
        await harness.core.event_writer.flush()
        await asyncio.to_thread(shutil.copyfile, harness.store.path, tmp_path / crash_store_name)
    finally:
        await harness.aclose()

    reply_started = asyncio.Event()
    provider = ScriptedProvider(default=[Step(wait_for=reply_started, stop=True)])
    restored = await ScenarioHarness.restore(tmp_path, store_name=crash_store_name, provider=provider)
    try:
        agent = restored.core.agents[agent.id]
        assert agent.state == AgentState.FAILED
        assert await asyncio.to_thread(restored.run_rows, agent) == [{
            "run_id": old_run_id, "outcome": "failed", "basis": None,
            "failure_kind": "runtime_interrupted",
        }]
        assert not any(e.type in {"tool.finished", "program.finished"} for e in await asyncio.to_thread(restored.events, agent))
        assert provider.call_count() == 0

        await restored.bus.execute(Command(
            type="agent.message", target={"session_id": agent.id},
            payload={"content": "Continue with a reply."},
        ))
        await restored.wait_for(lambda: provider.call_count() == 1, "provider enters resumed reply")
        assert agent.state == AgentState.RUNNING
        events = await asyncio.to_thread(restored.events, agent)
        new_run = next(e for e in events if e.type == "run.started" and e.run_id != old_run_id)
        tool_finished = next(e for e in events if e.type == "tool.finished")
        program_finished = next(e for e in events if e.type == "program.finished")
        assert tool_finished.run_id == program_finished.run_id == old_run_id
        assert tool_finished.data["tool_call_id"] == old_tool.data["tool_call_id"]
        assert program_finished.data["execution_id"] == old_program.data["execution_id"]
        assert tool_finished.data["status"] == program_finished.data["status"] == "interrupted"
        assert tool_finished.data["effect_state"] == "unknown"
        assert tool_finished.seq < program_finished.seq < new_run.seq

        reply_started.set()
        await restored.wait_terminal(agent)
        assert agent.state == AgentState.SUCCEEDED
        rows = await asyncio.to_thread(restored.run_rows, agent)
        assert [row["outcome"] for row in rows] == ["failed", "succeeded"]
        types = await asyncio.to_thread(restored.types, agent)
        assert types.count("tool.finished") == 1
        assert types.count("program.finished") == 1
        assert provider.call_count() == 1
    finally:
        reply_started.set()
        await restored.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("delay_child_delivery", [False, True], ids=["normal", "late-child-wake"])
async def test_restart_repeats_no_side_effect_and_keeps_unconsumed_message(
    tmp_path, monkeypatch, delay_child_delivery
):
    """重启：不重复工具副作用、不重复 spawn、不丢已持久化但未消费的消息。

    杠杆：恢复语义（restore 只重建投影、不重放副作用）+ dispatcher 的落库先于可见。
    """
    provider = ScriptedProvider(
        by_role={
            "coordinator": [
                Step(
                    tools=[
                        # todo_write 的副作用是 per-agent 存储文件，不需要人工审批：
                        # 这样场景专测「重启是否重放副作用」，不掺审批状态机。
                        ("todo_write", {"todos": [{"content": "note once", "status": "in_progress"}]}),
                        ("subagent_launcher", {"role_id": "explorer", "query": "look", "is_wait": False}),
                    ]
                ),
                Step(text="did the work", stop=True),
            ],
            "explorer": [Step(text="exploring", stop=True)],
        }
    )
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    child_report_committed = asyncio.Event()
    release_child_delivery = asyncio.Event()
    if delay_child_delivery:
        commit = harness.core.event_writer.commit

        async def commit_with_delayed_child_delivery(draft):
            envelope = await commit(draft)
            if draft.type == "agent.message_injected" and draft.data.get("manifest"):
                # Force the event-visible but not-yet-enqueued child report window.
                child_report_committed.set()
                await release_child_delivery.wait()
            return envelope

        monkeypatch.setattr(harness.core.event_writer, "commit", commit_with_delayed_child_delivery)
    try:
        parent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_for(
            lambda: len(harness.child_reports(parent)) == 1, "child report before restart"
        )
        if delay_child_delivery:
            await harness.wait_for(child_report_committed.is_set, "child report delivery paused")
        children_before = [child.id for child in harness.children_of(parent)]
        effects_before = [
            tool for tool in harness.tool_events(parent) if tool["tool_name"] == "todo_write"
        ]
        assert len(effects_before) == 1
        assert effects_before[0]["is_success"] is True, harness.describe(parent)
        payload_before = _todo_store_file(harness.project.id, parent.id).read_text(
            encoding="utf-8"
        )

        # child_reports 只说明回传事件已追加，子任务仍可能在落库/入队/唤醒中。
        # 父任务结束也不能排除这次迟到的唤醒；先停准入并等全部任务收尾，再造
        # 「已落库但未消费」的消息（重启后必须仍在信箱里）。
        await harness.wait_terminal(parent)
        await harness.runner.cancel_all()
        notice = await harness.core.dispatcher.commit_and_deliver(
            to_session_id=parent.id,
            project_id=harness.project.id,
            content="unconsumed notice",
            sender="system",
            wake=WakePolicy.NEVER,
        )
        if delay_child_delivery:
            release_child_delivery.set()
            await harness.wait_for(
                lambda: all(harness.runner.task_for(agent.id) is None
                            for agent in harness.core.agents.values()),
                "delayed child delivery and any resulting parent wake finished",
            )
        assert await asyncio.to_thread(harness.store.has_event, notice.event_id)
        assert all(
            message.get("message_id") != notice.data["message_id"]
            for message in harness.core.contexts.current_messages(parent.id)
        ), "restart fixture notice was consumed before shutdown"
    finally:
        release_child_delivery.set()
        await harness.aclose()

    restored = await ScenarioHarness.restore(tmp_path, provider=provider)
    try:
        parent2 = restored.core.agents[parent.id]
        # 副作用只发生过一次：事件流里该工具只有一次，存储文件也没被重放改写。
        effects_after = [
            tool for tool in restored.tool_events(parent2) if tool["tool_name"] == "todo_write"
        ]
        assert len(effects_after) == 1
        payload_after = _todo_store_file(restored.project.id, parent2.id).read_text(
            encoding="utf-8"
        )
        assert payload_after == payload_before
        # 不重复 spawn：child 列表逐字相同，且没有新的派发尝试。
        assert [child.id for child in restored.children_of(parent2)] == children_before
        # 未消费消息仍在信箱里（重启不丢信）。
        inbox = restored.core.mailbox.inbox(parent2.id)
        pending = []
        while inbox is not None and not inbox.empty():
            pending.append(inbox.get_nowait()["content"])
        assert "unconsumed notice" in pending
    finally:
        await restored.aclose()
# ------------------------------------------------------- 5. context overflow 压缩


@pytest.mark.asyncio
async def test_context_budget_compacts_once_then_short_turns_continue(tmp_path, monkeypatch):
    """上下文超预算：压缩真实投影一次，随后短轮次继续原任务且不重复压缩。

    杠杆：容量口径 + 压缩触发（budget/overflow）+ 摘要替换。
    """
    from cloudra.runtime_v2 import compaction as compaction_module

    provider = ScriptedProvider(
        default=[
            Step(
                text="first turn with a long observation " + ("padding " * 4000),
                tools=[("todo_write", {"todos": [{"content": "keep going", "status": "in_progress"}]})],
            ),
            Step(
                text="second turn after compaction",
                tools=[("todo_write", {"todos": [{"content": "still going", "status": "in_progress"}]})],
            ),
            Step(text="finished after compaction", stop=True),
        ]
    )
    harness = await ScenarioHarness.start(tmp_path, provider=provider)

    async def fake_summarizer(agent, messages, *, event_log=None, run_id=None):
        # 真实 runner 的摘要调用面；转发到 scripted summarizer（零 API key）。
        return await provider.summarize(messages)

    # runner 在函数内从 compaction 模块取摘要器，故补丁打在它身上。
    monkeypatch.setattr(
        compaction_module, "summarize_with_agent_settings", fake_summarizer
    )

    try:
        # 极小上下文窗口 → 第一轮之后即超预算，压缩在轮次边界触发。
        agent = await harness.spawn(
            "coordinator",
            protocol="traditional",
            context_window=4000,
            max_tokens=32,
        )
        await harness.wait_terminal(agent)

        compacted = [e for e in harness.events(agent) if e.type == "context.compacted"]
        # 第一轮超过预算，压缩后的短轮次仍在预算内，不应重复安装摘要。
        # 新增长轨迹允许再次压缩；不能把“一次 run 只能压缩一次”当成契约。
        # 摘要调用次数本身会因分段/合并而 >1，故只要求发生了摘要调用。
        assert len(compacted) == 1, harness.describe(agent)
        assert provider.summary_calls >= 1, "压缩安装成功却没调用摘要器"
        # 压缩之后任务继续并正常收尾（不是靠压缩把 run 掐断）。
        assert [row["outcome"] for row in harness.run_rows(agent)] == ["succeeded"]
        assert provider.call_count() == 3, "压缩后仍要走完剩余轮次"
        # 投影确实被替换成摘要消息（压缩边界之后的内容仍在）。
        contexts = harness.core.session_contexts
        assert agent.id in contexts
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures('ts_producer_authority')
async def test_failed_ts_scan_unchanged_resume_keeps_failure_without_budget_exhaustion(tmp_path, monkeypatch):
    """Failed scans retry once; active retries retain that job and failed evidence."""
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core.ts_process import load_record
    from tests.test_ts_fixture_pipeline import finish, install_log, job_count, waiting_fixture_stage

    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',lambda **_:AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    ready=asyncio.Event()
    steps=[Step(wait_for=ready) for _ in range(3)]
    provider=ScriptedProvider(by_role={'small_mol':[*steps,Step(stop=True)]})
    harness=await ScenarioHarness.start(tmp_path,workspace_dir=tmp_path,provider=provider)
    try:
        agent=await harness.spawn('small_mol',protocol='traditional')
        db,record,step=await asyncio.to_thread(waiting_fixture_stage,tmp_path,purpose='scan',project_id=harness.project.id,owner_id=agent.id)
        log=await asyncio.to_thread(install_log,record,step,'orca/segfault_mid_opt/dvb_opt_truncated_no_termination.out')
        evidence=await asyncio.to_thread(log.read_bytes)
        await asyncio.to_thread(finish,db,step.job_id,'failed')
        before=await asyncio.to_thread(load_record,str(tmp_path),record.run_id)
        changes={'guess':before.input.guess.model_dump()}
        for item in steps:
            item.tools=[('ts_resume',{'run_id':record.run_id,'changes':changes,'reason':'retry accepted scan'})]
        ready.set()
        await harness.wait_terminal(agent)
        calls=harness.tool_events(agent)
        assert [call['tool_name'] for call in calls]==['ts_resume']*3
        assert all(call['is_success'] for call in calls),harness.describe(agent)
        new_job=calls[0]['result_data']['waiting_for'][0]['job_id']
        assert new_job!=step.job_id
        for call in calls:
            result=call['result_data']
            assert result['status']=='waiting' and result['blocked'] is None
            assert result['waiting_for'][0]['job_id']==new_job
            assert result['usage']['interventions']==before.intervention_count+1 and result['result'] is None
        after=await asyncio.to_thread(load_record,str(tmp_path),record.run_id)
        assert after.input.model_dump()==before.input.model_dump()
        assert after.declaration_revision==before.declaration_revision+1
        assert after.intervention_count==before.intervention_count+1
        assert len(after.attempt_history)==len(before.attempt_history)+1
        assert after.attempt_history[-1].blocked.model_dump()==before.blocked.model_dump()
        assert await asyncio.to_thread(log.read_bytes)==evidence
        assert await asyncio.to_thread(job_count,db)==2
    finally:
        ready.set()
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("ts_producer_authority")
async def test_ts_resume_repeated_irc_repairs_preserve_scientific_failure(tmp_path, monkeypatch):
    """Real Agent revisions keep one run, immutable failed evidence and one job per new input."""
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core.ts_inputs import TsExecutionLimits
    from cloudra.tools.core.ts_process import load_record
    from tests.agent_scenarios import queued_native_ts_optimization, ts_repeated_irc_input_repair_steps
    from tests.test_ts_fixture_pipeline import finish, install_log, job_count

    monkeypatch.setattr("cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"))
    frequency_ready, irc_ready = asyncio.Event(), asyncio.Event()
    provider = ScriptedProvider(by_role={"small_mol": ts_repeated_irc_input_repair_steps(
        "ts_0001", frequency_ready, irc_ready)})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    seed = (
        "5\nNative optimization seed\n"
        "C -0.423530 -0.004703 0.002036\n"
        "O 0.591597 -0.682213 -0.372134\n"
        "O 1.476819 0.188463 0.229121\n"
        "H -1.261767 -0.509001 0.485509\n"
        "H -0.434262 1.076129 -0.083405\n"
    )
    try:
        agent = await harness.spawn("small_mol", protocol="traditional")
        db, record, optimization = await asyncio.to_thread(queued_native_ts_optimization,
            tmp_path, seed, harness.project.id, agent.id)
        await asyncio.to_thread(install_log, record, optimization, "orca/ch2oo_optts_gfn2_orca611.out")
        await asyncio.to_thread(finish, db, optimization.job_id)
        current = await asyncio.to_thread(load_record, str(tmp_path), record.run_id)
        failed_frequency = current.job_steps[-1]
        failed_log = await asyncio.to_thread(install_log, current, failed_frequency, "orca/co2_freq_orca42.out")
        failed_bytes = await asyncio.to_thread(failed_log.read_bytes)
        await asyncio.to_thread(finish, db, failed_frequency.job_id)
        failed = await asyncio.to_thread(load_record, str(tmp_path), record.run_id)
        assert failed.blocked.failure_class == "wrong_mode"
        assert failed.terminal is None

        frequency_ready.set()
        await harness.wait_for(lambda: len(harness.tool_events(agent)) == 1
            and harness.tool_events(agent)[0]["status"] == "completed", "frequency repair accepted")
        repaired = await asyncio.to_thread(load_record, str(tmp_path), record.run_id)
        frequency = repaired.job_steps[-1]
        assert frequency.purpose == "frequency" and frequency.job_id != failed_frequency.job_id
        # This is contract data for the single-mode gate, never a claimed real saddle.
        await asyncio.to_thread(install_log, repaired, frequency, "benchmark_synthetic/ts_freq.out")
        await asyncio.to_thread(finish, db, frequency.job_id)
        before = await asyncio.to_thread(load_record, str(tmp_path), record.run_id)
        assert before.job_steps[-1].purpose == "irc"
        first_irc_job = before.job_steps[-1].job_id
        irc_ready.set()
        await harness.wait_terminal(agent)

        calls = harness.tool_events(agent)
        assert [call["tool_name"] for call in calls] == ["ts_resume"] * 5
        assert all(call["is_success"] for call in calls), harness.describe(agent)
        repairs = [call["result_data"] for call in calls[1:]]
        job_ids = [result["waiting_for"][0]["job_id"] for result in repairs]
        assert len(set([first_irc_job, *job_ids[:3]])) == 4
        assert job_ids[3] == job_ids[2]
        assert [result["usage"]["interventions"] for result in repairs] == [2, 3, 4, 4]
        for result in repairs:
            assert result["run_id"] == record.run_id
            assert result["status"] == "waiting" and result["stage"] == "refine"
            assert result["blocked"] is None and result["result"] is None
        saved = await asyncio.to_thread(load_record, str(tmp_path), record.run_id)
        assert saved.pipeline_id == record.pipeline_id and saved.terminal is None
        assert saved.declaration_revision == 5 and saved.intervention_count == 4
        assert len(saved.attempt_history) == 4
        assert saved.attempt_history[0].blocked.model_dump() == failed.blocked.model_dump()
        assert saved.attempt_history[0].job_steps[-1].job_id == failed_frequency.job_id
        assert saved.job_steps[0].job_id == optimization.job_id
        assert saved.job_steps[1].job_id == frequency.job_id
        assert await asyncio.to_thread(failed_log.read_bytes) == failed_bytes
        assert await asyncio.to_thread(job_count, db) == 7
        assert "max_interventions" not in TsExecutionLimits.model_json_schema()["properties"]
    finally:
        frequency_ready.set()
        irc_ready.set()
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("ts_producer_authority")
async def test_ts_resume_native_cclib_assertion_keeps_completed_ts(tmp_path, monkeypatch):
    """IA8 native ORCA log: real Agent/resume/parser/writer/ledger, no QM process."""
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
    from cloudra.tools.core.ts_process import load_record
    from tests.agent_scenarios import queued_native_ts_optimization, ts_completed_optimization_frequency_resume_steps
    from tests.test_ts_fixture_pipeline import install_log, job_count

    monkeypatch.setattr("cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"))
    ready = asyncio.Event()
    provider = ScriptedProvider(by_role={"small_mol": ts_completed_optimization_frequency_resume_steps("ts_0001", ready)})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    seed = (
        "5\nCandidate differs from the native optimized geometry\n"
        "C -0.500000 -0.004703 0.002036\n"
        "O 0.591597 -0.682213 -0.372134\n"
        "O 1.476819 0.188463 0.229121\n"
        "H -1.261767 -0.509001 0.485509\n"
        "H -0.434262 1.076129 -0.083405\n"
    )
    try:
        agent = await harness.spawn("small_mol", protocol="traditional")
        db, record, step = await asyncio.to_thread(queued_native_ts_optimization, tmp_path,
            seed, harness.project.id, agent.id)
        log = await asyncio.to_thread(install_log, record, step, "orca/ch2oo_optts_gfn2_orca611.out")
        native_log = await asyncio.to_thread(log.read_bytes)
        async with db.aconnect() as con:
            await con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (step.job_id,))
            await con.commit()
        ready.set()
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        assert [call["tool_name"] for call in calls] == ["ts_resume"]
        assert calls[0]["is_success"], harness.describe(agent)
        result = calls[0]["result_data"]
        assert result["receipt"] is not None
        assert result["status"] == "waiting" and result["stage"] == "refine"
        assert result["blocked"] is None and result["result"] is None
        saved = await asyncio.to_thread(load_record, str(tmp_path), record.run_id)
        assert [job.purpose for job in saved.job_steps] == ["ts_opt", "frequency"]
        assert saved.job_steps[0].job_id == step.job_id and saved.job_steps[0].state == "done"
        assert saved.terminal is None
        frequency = saved.job_steps[-1]
        frequency_input = await asyncio.to_thread(Path(frequency.input_path).read_text)
        assert "NumFreq" in frequency_input and "TightSCF" in frequency_input
        optimized_xyz = await asyncio.to_thread(Path(frequency.input_path).with_name("optimized.xyz").read_text)
        expected_geometry = [
            "C -0.423530 -0.004703 0.002036",
            "O 0.591597 -0.682213 -0.372134",
            "O 1.476819 0.188463 0.229121",
            "H -1.261767 -0.509001 0.485509",
            "H -0.434262 1.076129 -0.083405",
        ]
        actual_atoms = [line.split() for line in optimized_xyz.splitlines()[2:]]
        expected_atoms = [line.split() for line in expected_geometry]
        assert [atom[0] for atom in actual_atoms] == [atom[0] for atom in expected_atoms]
        assert [float(x) for atom in actual_atoms for x in atom[1:]] == pytest.approx(
            [float(x) for atom in expected_atoms for x in atom[1:]], abs=1e-8)
        assert await asyncio.to_thread(job_count, db) == 2
        for _ in range(2):
            await asyncio.to_thread(handle_process_job_terminal, db, step.job_id)
        assert await asyncio.to_thread(job_count, db) == 2
        assert await asyncio.to_thread(log.read_bytes) == native_log
    finally:
        ready.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_yolo_invalid_boolean_never_applies_agent_file_write(tmp_path, monkeypatch):
    """An invalid approval is rejected within the real Agent/tool/file mutation path."""
    from unittest.mock import AsyncMock

    from cloudra.infra.yolo_guard import YoloGuard
    from tests.test_yolo_guard import _approval_response

    monkeypatch.setenv("CLOUDRA_YOLO_MODE", "true")
    client = SimpleNamespace(create=AsyncMock(return_value=_approval_response({"approved": "false"})))
    monkeypatch.setattr(YoloGuard, "_client", lambda _: client)
    provider = ScriptedProvider(default=[
        Step(tools=[("write", {"path": "blocked.txt", "content": "must not be applied"})]),
        Step(stop=True),
    ])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        assert [call["tool_name"] for call in calls] == ["write"]
        assert calls[0]["started"] is True, harness.describe(agent)
        result = calls[0]["result_data"]
        assert result["status"] == "declined"
        assert result["is_written"] is False
        assert client.create.call_count == 3
        target = _workspace(harness.project.id) / "blocked.txt"
        assert not await asyncio.to_thread(target.exists)
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_yolo_reviews_ts_submission_and_python_switch_but_allows_diagnosis(tmp_path, monkeypatch):
    """真实工具链中，拒绝提交、拒绝 Python 换路、允许诊断，均在副作用之前裁决。"""
    from unittest.mock import AsyncMock

    from cloudra.infra.yolo_guard import YoloGuard
    from tests.agent_scenarios import ts_bypass_then_diagnostic_steps
    from tests.test_yolo_guard import _approval_response

    monkeypatch.setenv('CLOUDRA_YOLO_MODE', 'true')
    client = SimpleNamespace(create=AsyncMock(side_effect=[
        _approval_response({'approved': False, 'reason': 'Repair the existing TS workflow.'}),
        _approval_response({'approved': False, 'reason': 'Changing execution tools does not repair the missing verification.'}),
        _approval_response({'approved': True, 'reason': 'Diagnostic observation is allowed.'}),
    ]))
    monkeypatch.setattr(YoloGuard, '_client', lambda _: client)
    harness = await ScenarioHarness.start(tmp_path, provider=ScriptedProvider(default=ts_bypass_then_diagnostic_steps()))
    try:
        workspace = _workspace(harness.project.id)
        await asyncio.to_thread(workspace.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread((workspace / 'ts.inp').write_text, '! HF STO-3G OptTS Freq\n')
        task = 'Find and rigorously verify this reaction TS.'
        agent = await harness.spawn('coordinator', protocol='traditional', query=task)
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        assert [call['tool_name'] for call in calls] == ['submit_compute_job', 'bash', 'write'], harness.describe(agent)
        assert calls[0]['status'] == 'blocked'
        assert calls[1]['result_data']['exit_code'] == 126
        assert calls[2]['result_data']['is_written'] is True
        assert client.create.call_count == 3
        assert not await asyncio.to_thread((workspace / 'bypassed.txt').exists)
        assert await asyncio.to_thread((workspace / 'diagnostic.txt').read_text) == 'diagnostic observation'
        reviewed = [''.join(part['text'] for part in call.kwargs['messages'][1]['content'])
                    for call in client.create.call_args_list]
        assert all(task in content for content in reviewed), reviewed
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_old_launcher_role_field_is_rejected_without_orphan_child(tmp_path):
    provider = ScriptedProvider(by_role={
        "coordinator": [
            Step(tools=[("subagent_launcher", {"agent_id": "a-1", "query": "inspect workspace", "is_wait": False})]),
            Step(stop=True),
        ],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        parent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(parent)
        dispatched = [event for event in harness.tool_events(parent) if event["tool_name"] == "subagent_launcher"]
        assert len(dispatched) == 1
        assert dispatched[0]["is_success"] is False
        assert harness.children_of(parent) == []
        assert harness.child_reports(parent) == []
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_scope_only_reapproval_clears_stale_completion_debt(tmp_path):
    from cloudra.dag.drafts import MechanismDraft
    from cloudra.dag.models import AddEdge, ClaimSpec, ElementaryStepEdge
    from tests.agent_scenarios import scope_review_completion_steps
    from tests.test_dag_async_evidence_review import _seed_simple_complete_graph

    harness = await ScenarioHarness.start(tmp_path, provider=ScriptedProvider(by_role={
        "coordinator": scope_review_completion_steps(),
        "supervisor": [Step(stop=True)],
    }))
    def seed():
        _, _, store = _seed_simple_complete_graph(tmp_path, harness.project.id)
        store.save_draft(MechanismDraft(operations=[AddEdge(op="add_edge", graph="delivery",
            edge=ElementaryStepEdge(edge_id="step1", name="step1", source_node_id="r", target_node_id="p"))],
            rationale="initial reasoning rejected", state="rejected"), actor_id="coordinator")
        store.save_draft(MechanismDraft(operations=[], rationale="revised reasoning accepted",
            state="accepted", claim_spec=ClaimSpec(kind="mechanism", scope={"targets": ["r", "p", "step1"]})),
            actor_id="harness:auto")
    try:
        await asyncio.to_thread(seed)
        agent = await harness.spawn("coordinator", protocol="traditional", orchestration_mode="dag_guided")
        await harness.wait_for(lambda: agent.state.value == "waiting_approval", "scope final review")
        # This regression isolates cleared scope debt; final review is covered by the full tool scenario.
        from cloudra.dag.review_requests import ReviewDecision
        from cloudra.dag.store import DagStore
        from cloudra.persistence.database import ConversationDB
        from cloudra.runtime_v2.supervision import flush_review_notifications
        store = DagStore(ConversationDB(harness.project.id))
        request = next(r for r in await asyncio.to_thread(store.list_review_requests, "queued") if r.kind == "exit")
        assert (await asyncio.to_thread(store.resolve_review, ReviewDecision(
            request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
            verdict="accept", reason="the revised scope final delivery is acceptable"),
            expected_basis=request.basis_fingerprint))["accepted"]
        await flush_review_notifications(harness.core, harness.project.id)
        await harness.wait_terminal(agent)
        reports = [call for call in harness.tool_events(agent) if call["tool_name"] == "dag_delivery_report"]
        assert reports and reports[0]["result_data"]["result"]["complete"] is True
        assert agent.state.value == "succeeded", harness.describe(agent)
        assert any(event.type == "agent.completion_gate" and event.data.get("explicit_stop")
                   for event in harness.events(agent))
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_supervisor_feedback_resumes_background_waiting_coordinator(tmp_path):
    """Permission + mailbox + completion gate: review feedback must start a new run."""
    from cloudra.runtime_v2.hub_bridge import handle_hub_tool
    from cloudra.runtime_v2.policies.base import ToolCall
    from cloudra.runtime_v2.supervision import _spawn_supervisor
    from tests.agent_scenarios import supervisor_feedback_recovery_steps
    from tests.test_runtime_v2_compute_notify import _insert_terminal_job

    release = asyncio.Event()
    provider = ScriptedProvider(by_role={"coordinator": [Step(wait_for=release, stop=True)]})
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        coordinator = await harness.spawn("coordinator", protocol="traditional", orchestration_mode="dag_guided")
        await asyncio.to_thread(
            _insert_terminal_job, harness.project.id, session_id=coordinator.id, state="running", path="",
        )
        release.set()
        await harness.wait_terminal(coordinator)
        gates = [e for e in harness.events(coordinator) if e.type == "agent.completion_gate"]
        assert gates[-1].data["action"] == "wait_background"
        supervisor = await _spawn_supervisor(harness.core, harness.project.id)
        assert supervisor is not None
        provider.script("coordinator", *supervisor_feedback_recovery_steps())
        result = await handle_hub_tool(harness.core, supervisor, ToolCall(
            id="review-feedback", name="agent_hub", arguments={
                "action": "post", "topic": "review", "content": "Revise the pending evidence",
                "to_agent": coordinator.id,
            },
        ))
        assert result.is_success
        await harness.wait_for(
            lambda: harness.types(coordinator).count("run.started") == 2, "feedback recovery run",
        )
        await harness.wait_terminal(coordinator)
        events = harness.events(coordinator)
        injected = next(e for e in events if e.type == "agent.message_injected"
                        and e.data.get("post_id") == result.data["post_id"])
        resumed = [e for e in events if e.type == "run.started"][-1]
        consumed = next(e for e in events if e.type == "hub.notification_consumed"
                        and e.data.get("post_id") == result.data["post_id"])
        assert gates[-1].seq < injected.seq < resumed.seq < consumed.seq
        assert [e for e in events if e.type == "agent.completion_gate"][-1].data["action"] == "wait_background"
        assert any(e["tool_name"] == "agent_hub" and e["is_success"] for e in harness.tool_events(coordinator))
        saved = await asyncio.to_thread(harness.store.events_after, {})
        assert any(e["event_id"] == injected.event_id for e in saved)
    finally:
        release.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_reused_child_completes_new_task_after_compute_notice_and_wakes_parent(tmp_path):
    from cloudra.runtime_v2.hub_bridge import handle_hub_tool
    from cloudra.runtime_v2.policies.base import ToolCall

    calculation_done = asyncio.Event()
    provider = ScriptedProvider(by_role={
        "coordinator": [Step(stop=True)],
        "explorer": [Step(stop=True), Step(stop=True, wait_for=calculation_done)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        parent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(parent)
        child = await harness.spawn("explorer", query="task A", parent=parent, protocol="traditional")
        await harness.wait_for(lambda: len(harness.child_reports(parent)) == 1, "task A report")
        await harness.wait_terminal(parent)
        first_terminal = harness.child_reports(parent)[0]["manifest"]["terminal_event_id"]
        parent_runs = len(harness.run_rows(parent))
        called = await handle_hub_tool(harness.core, parent, ToolCall(
            id="assign-B", name="agent_hub", arguments={"action": "call", "to": child.id, "message": "task B"},
        ))
        assert called.is_success
        await harness.wait_for(lambda: provider.call_count("explorer") >= 2, "task B waiting for calculation")
        assert len(harness.child_reports(parent)) == 1
        await harness.core.dispatcher.commit_and_deliver(
            to_session_id=child.id, project_id=harness.project.id, sender="system", content="[Compute job] done",
        )
        calculation_done.set()
        await harness.wait_for(lambda: len(harness.child_reports(parent)) == 2, "task B report")
        await harness.wait_for(lambda: len(harness.run_rows(parent)) > parent_runs, "parent resumed for task B")
        await harness.wait_terminal(parent)
        reports = harness.child_reports(parent)
        assert reports[1]["manifest"]["terminal_event_id"] != first_terminal
        assert reports[1]["manifest"]["session_id"] == child.id
        assert reports[1]["manifest"]["last_run"]["run_id"] == harness.run_rows(child)[-1]["run_id"]
    finally:
        calculation_done.set()
        await harness.aclose()
    restored = await ScenarioHarness.restore(tmp_path)
    try:
        assert len(restored.child_reports(restored.core.agents[parent.id])) == 2
    finally:
        await restored.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("ts_producer_authority")
async def test_budgeted_ts_terminal_notice_resumes_background_wait_and_persists(tmp_path, monkeypatch):
    """Real budget + native frequency gate + notification + runner; no engine or API."""
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.services.compute_admission import AdmissionOutcome
    from tests.agent_scenarios import budgeted_ts_result_recovery_steps
    from tests.test_ts_fixture_pipeline import install_log, waiting_fixture_stage

    monkeypatch.setattr("cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"))
    release = asyncio.Event()
    provider = ScriptedProvider(default=[Step(wait_for=release, stop=True)])
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        agent = await harness.spawn("small_mol", protocol="traditional")
        db, record, step = await asyncio.to_thread(waiting_fixture_stage, tmp_path,
            project_id=harness.project.id, owner_id=agent.id,
            limits={"source": "explicit_user", "max_compute_actions": 4, "max_model_calls": 4})
        await asyncio.to_thread(install_log, record, step, "orca/co2_freq_orca42.out")
        release.set()
        await harness.wait_terminal(agent)
        gates = [event for event in harness.events(agent) if event.type == "agent.completion_gate"]
        assert gates[-1].data["action"] == "wait_background"
        provider.script_default(*budgeted_ts_result_recovery_steps(record.run_id))
        async with db.aconnect() as con:
            await con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (step.job_id,))
            await con.commit()
        broker = ComputeNotifyBroker(harness.core)
        await broker._poll_project(harness.project.id)
        assert await asyncio.to_thread(broker._pending_terminal_jobs, harness.project.id) == []
        await harness.wait_for(lambda: len(harness.run_rows(agent)) == 2, "TS result processing run")
        await harness.wait_terminal(agent)
        calls = [call for call in harness.tool_events(agent) if call["tool_name"] == "ts_inspect"]
        assert len(calls) == 1 and calls[0]["is_success"], harness.describe(agent)
        usage = calls[0]["result_data"]["usage"]
        assert usage["model_calls"] == 0 and usage["reserved_compute_actions"] == 1
        assert calls[0]["result_data"]["blocked"]["failure_class"] == "wrong_mode"
        notices = [event for event in harness.events(agent) if event.type == "agent.message_injected"
            and (event.data.get("manifest") or {}).get("kind") == "compute_completion"]
        assert [task_id for event in notices for task_id in event.data["manifest"]["task_ids"]] == [step.job_id]
        saved = await asyncio.to_thread(harness.store.events_after, {})
        assert any(row["event_id"] == notices[0].event_id for row in saved)
        resumed = [event for event in harness.events(agent) if event.type == "run.started"][-1]
        assert notices[0].seq < resumed.seq
        async with db.aconnect() as con:
            row = await (await con.execute("SELECT notified_at FROM compute_jobs WHERE id=?", (step.job_id,))).fetchone()
        assert row[0] is not None
    finally:
        release.set()
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["accept", "reject", "needs_evidence"])
async def test_complete_final_supervisor_review_controls_delivery(tmp_path, verdict):
    """真实工具/默认策略/持久化：完整覆盖仍须审稿，非接受裁决阻止交付。"""
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB
    from tests.agent_scenarios import final_delivery_review_steps
    from tests.test_runtime_v2_completion_gate import _seed_complete_delivery

    review_ready, resume, park = [asyncio.Event() for _ in range(3)]
    review = Step(wait_for=review_ready)
    provider = ScriptedProvider(by_role=final_delivery_review_steps(review, resume, park))
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    try:
        await _set_supervisor_traditional(harness)
        await _seed_complete_delivery(harness.project.id)
        agent = await harness.spawn("coordinator", protocol="traditional", orchestration_mode="dag_guided")
        await harness.wait_for(lambda: agent.state.value in {"waiting_approval", "succeeded"},
                               "first final-delivery attempt")
        assert agent.state.value == "waiting_approval"
        db = await asyncio.to_thread(lambda: ConversationDB(harness.project.id).init())
        store = DagStore(db)
        requests = await asyncio.to_thread(store.list_review_requests, None)
        assert len(requests) == 1
        request = requests[0]
        assert request.kind == "exit" and request.proposal["disposition"] == "complete"
        args = {"request_id": request.request_id, "verdict": verdict,
                "reason": "independent review of the original submitted evidence"}
        if verdict != "accept":
            args["next_action"] = "Inspect the original IRC endpoint geometry"
        review.tools = [("dag_view_evidence", {"review_id": request.request_id}),
                        ("dag_review_evidence", args)]
        review_ready.set()
        await harness.wait_for(lambda: any(t["tool_name"] == "dag_review_evidence" and t["status"] == "completed"
            for a in harness.core.agents.values() if a.role_id == "supervisor"
            for t in harness.tool_events(a)), "real Supervisor final verdict")
        supervisor = next(a for a in harness.core.agents.values() if a.role_id == "supervisor")
        await harness.wait_terminal(supervisor)
        tools = harness.tool_events(supervisor)
        viewed = next(t for t in tools if t["tool_name"] == "dag_view_evidence")
        assert viewed["is_success"] and viewed["result_data"]["result"]["proposal"] == request.proposal
        decision = await asyncio.to_thread(store.get_review_decision_for_request, request.request_id)
        assert decision.verdict == verdict
        resume.set()
        await harness.wait_for(lambda: len([e for e in harness.events(agent)
            if e.type == "agent.completion_gate" and e.data.get("explicit_stop")]) == 2,
            "same complete declaration after the final verdict")
        gates = [e for e in harness.events(agent) if e.type == "agent.completion_gate" and e.data.get("explicit_stop")]
        assert gates[0].data["action"] == "wait_review"
        assert gates[1].data["action"] == ("allow_final" if verdict == "accept" else "continue_work")
        assert len(await asyncio.to_thread(store.list_review_requests, None)) == 1
        assert await asyncio.to_thread(store.list_review_requests, "queued") == []
        def dispositions():
            with db.connect() as con:
                return con.execute("SELECT disposition FROM dag_delivery_dispositions").fetchall()
        if verdict == "accept":
            await harness.wait_terminal(agent)
            assert agent.state.value == "succeeded"
            assert provider.call_count("coordinator") == 1
            assert gates[1].data["basis"] == "supervisor_supported"
            assert await asyncio.to_thread(dispositions) == [("complete",)]
        else:
            assert agent.state.value == "running"
            assert provider.call_count("coordinator") >= 2
            assert await asyncio.to_thread(dispositions) == []
            assert not any(e.type == "agent.message_emitted" for e in harness.events(agent))
        assert not any(t["tool_name"] == "submit_compute_job" for a in harness.core.agents.values()
                       for t in harness.tool_events(a))
    finally:
        for event in (review_ready, resume, park):
            event.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_named_agent_communication_addresses_only_the_launched_instance(tmp_path):
    """Launcher names survive storage and Hub addressing with another same-role peer present."""
    from tests.agent_scenarios import named_agent_communication_steps

    release_child = asyncio.Event()
    provider = ScriptedProvider(by_role={
        "coordinator": named_agent_communication_steps(),
        "explorer": [Step(stop=True), Step(wait_for=release_child, stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        other = await harness.spawn("explorer", protocol="traditional")
        await harness.wait_terminal(other)
        parent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(parent)
        calls = harness.tool_events(parent)
        assert [call["tool_name"] for call in calls] == ["subagent_launcher", "agent_hub"]
        assert all(call["is_success"] for call in calls), harness.describe(parent)
        child = harness.core.agents[calls[0]["result_data"]["session_id"]]
        assert child.parent_session_id == parent.id
        assert child.display_name == "lane_ts_scout"
        assert {agent.id for agent in harness.core.agents.values() if agent.role_id == "explorer"} == {
            other.id, child.id,
        }
        result = calls[1]["result_data"]
        assert result["session_id"] == child.id
        assert [notice["session_id"] for notice in result["notifications"]] == [child.id]
        message_id = result["notifications"][0]["message_event_id"]
        deliveries = await asyncio.to_thread(
            harness.store.read_events, project_id=harness.project.id, types={"agent.message_injected"},
        )
        assert [event.session_id for event in deliveries if event.event_id == message_id] == [child.id]
        assert not any(event.event_id == message_id for event in harness.events(other))
        spawned = await asyncio.to_thread(
            harness.store.read_events, session_id=child.id, types={"agent.spawned"},
        )
        assert len(spawned) == 1
        assert spawned[0].data["display_name"] == "lane_ts_scout"
    finally:
        release_child.set()
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures('ts_producer_authority', 'rdkit_chemistry')
async def test_ts_separated_product_component_evidence_recovers_candidate_without_new_jobs(tmp_path):
    """Real Agent/resume/ledger/classifier replay; native NU3 artifacts, no QM launch.

    The fixture starts at the completed-output import boundary. Independent
    component frequency logs exercise the native parser contract; the scientific
    direction classifier and source-side interval proof are not substituted.
    """
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.molecule import read_molecule
    from tests.agent_scenarios import ts_separated_product_recovery_steps
    from tests.test_ts_separated_products import separated_record

    ready = asyncio.Event()
    component_logs = [str(tmp_path / 'native' / f'component_{index}.out') for index in range(2)]
    provider = ScriptedProvider(by_role={'small_mol': ts_separated_product_recovery_steps(
        'separated', component_logs, ready,
    )})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)

    def seed_completed_outputs(owner_id):
        db = ComputeDB().init()
        record = separated_record(tmp_path)
        record.input.verification.product_endpoint.component_logs = []
        record.owner_conversation_id = harness.project.id
        record.owner_session_id = owner_id
        record.run_dir = str(tmp_path / 'ts' / record.run_id)
        Path(record.run_dir).mkdir(parents=True)
        state = create_process(db, request_key='separated-product-recovery', payload={
            'project_id': harness.project.id, 'owner_id': owner_id,
            'workspace_dir': str(tmp_path), 'input': record.input.model_dump(mode='json'),
        })
        record.pipeline_id = state['process_id']
        for step in record.job_steps:
            source = Path(step.input_path)
            calculation = step.actual_calculation
            task = 'irc' if step.purpose == 'irc' else 'opt' if step.purpose.endswith('_opt') else 'freq'
            request = QmInputWriter_input_schema(
                engine='orca', method=calculation.method, basis_set=calculation.basis_set,
                keywords=calculation.keywords, task_type=[{task: None}],
                source_type='xyz_file', source_value=str(source.with_name('optimized.xyz')),
                output_path=str(source),
            )
            molecule = read_molecule(str(source.with_name('optimized.xyz')))
            source.write_text(QmInputWriter._build_orca_input(request, molecule))
            step.stage_key = step.purpose
            step.job_id = bind_stage_job(db, process_id=record.pipeline_id, declaration_revision=1,
                stage_key=step.stage_key, attempt=1, job_payload={
                    'conversation_id': harness.project.id, 'session_id': owner_id,
                    'path': str(source), 'jobtype': 'orca', 'node_id': 'offline-fixture',
                })
            step.external_source['source_job_id'] = step.job_id
            with db.connect() as con:
                con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (step.job_id,))
        with use_pipeline_database(db):
            record = ts_process._verdict(record)
            assert record.terminal == 'candidate_only'
            ts_process.save_record(record)
        return db, record

    def job_ids(db):
        with db.connect() as con:
            return [row[0] for row in con.execute('SELECT id FROM compute_jobs ORDER BY id')]

    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        db, initial = await asyncio.to_thread(seed_completed_outputs, agent.id)
        original_jobs = {step.purpose: step.job_id for step in initial.job_steps}
        before = await asyncio.to_thread(job_ids, db)
        ready.set()
        await harness.wait_terminal(agent)

        calls = harness.tool_events(agent)
        assert [call['tool_name'] for call in calls] == ['ts_inspect', 'ts_resume', 'ts_inspect']
        assert all(call['is_success'] for call in calls), harness.describe(agent)
        assert calls[0]['result_data']['result']['outcome'] == 'candidate_only'
        for call in calls[1:]:
            assert call['result_data']['result']['outcome'] == 'verified'
            assert call['result_data']['result']['verified'] is True
        receipt = calls[1]['result_data']['receipt']
        assert receipt['invalidated'] == []
        assert {ref['job_id'] for ref in receipt['retained']} == set(before)
        saved = await asyncio.to_thread(ts_process.load_record, str(tmp_path), initial.run_id)
        assert saved.pipeline_id == initial.pipeline_id
        assert saved.terminal == 'verified'
        assert saved.input.verification.product_endpoint.component_logs == component_logs
        assert {step.purpose: step.job_id for step in saved.job_steps} == original_jobs
        assert not any(step.purpose.startswith('product_') for step in saved.job_steps)
        assert saved.attempt_history[-1].terminal == 'candidate_only'
        assert await asyncio.to_thread(job_ids, db) == before
        assert (await asyncio.to_thread(ts_process._validated_endpoint_minimum, saved, 'product'))[0] is None
    finally:
        ready.set()
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('job_type', [[], {}, 'orca'])
async def test_compute_job_type_feedback_without_runtime_retry(tmp_path, job_type):
    from tests.agent_scenarios import invalid_compute_job_type_steps

    harness = await ScenarioHarness.start(tmp_path, provider=ScriptedProvider(
        default=invalid_compute_job_type_steps(job_type)))
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        assert len(calls) == 1, harness.describe(agent)
        assert calls[0]['is_success'] is False
        assert calls[0]['status'] == 'failed'
        if not isinstance(job_type, str):
            assert 'Invalid tool arguments' in calls[0]['result_summary']
        assert not any(event.type == 'run.retry' for event in harness.events(agent))
        assert agent.state.value == 'succeeded', harness.describe(agent)
    finally:
        await harness.aclose()
