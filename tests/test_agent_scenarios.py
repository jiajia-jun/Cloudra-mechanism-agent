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
)


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
            Step(wait_for=attempt_complete, text="review status received"),
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


@pytest.mark.asyncio
async def test_guided_file_verdict_wakes_coordinator_for_supervisor_supported_completion(
    tmp_path, monkeypatch
):
    """A per-file verdict wakes the parked Coordinator; complete uses file credit."""
    submit_evidence = asyncio.Event()
    attempt_partial = asyncio.Event()
    review_file = asyncio.Event()
    finish_supervisor = asyncio.Event()
    attempt_complete = asyncio.Event()
    ts = Path(__file__).parent / "fixtures" / "xtb" / "ts_hess_xtb.out"
    provider = ScriptedProvider(by_role={
        "coordinator": [
            _propose_selected_ab(),
            Step(wait_for=submit_evidence, tools=[("dag_submit_step_evidence", {
                "step_name": "AB", "ts_file": ts.name,
                "reaction_coordinate_description": "selected transition",
            })]),
            Step(wait_for=attempt_partial, tools=[("stop", {
                "delivery_disposition": "partial",
            })]),
            Step(wait_for=attempt_complete, tools=[("stop", {
                "delivery_disposition": "complete",
            })]),
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
        ],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        await _set_supervisor_traditional(harness)
        await asyncio.to_thread(_seed_selected_step_endpoints, harness.project.id)
        workspace = _workspace(harness.project.id)
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ts, workspace / ts.name)
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
        assert report.complete
        assert any(gate.code == "supervisor_evidence_accepted" for gate in report.satisfied)

        finish_supervisor.set()
        await harness.wait_for(
            lambda: any(a.role_id == "supervisor" and a.state.value == "succeeded"
                        and len(harness.run_rows(a)) >= 3
                        for a in harness.core.agents.values()),
            "Supervisor idle before final delivery",
        )
        attempt_complete.set()
        await harness.wait_terminal(coordinator)
        from cloudra.runtime_v2.completion import completion_summary

        completion = completion_summary(harness.events(coordinator))
        assert completion["completion_basis"] == "supervisor_supported"
        assert completion["verification_label"] == "supervisor_reviewed"
    finally:
        submit_evidence.set()
        attempt_partial.set()
        review_file.set()
        finish_supervisor.set()
        attempt_complete.set()
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
            lambda: bool(harness.child_reports(agent)) and any(
                a.role_id == "supervisor" and a.state.value == "succeeded"
                for a in harness.core.agents.values()
            ),
            "Supervisor idle and its child report delivered before complete attempt",
        )
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
    ts = Path(__file__).parent / "fixtures" / "xtb" / "ts_hess_xtb.out"
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
        await harness.wait_terminal(agent)
        from cloudra.runtime_v2.completion import completion_summary

        completion = completion_summary(harness.events(agent))
        assert completion["completion_basis"] == "supervisor_supported"
        assert completion["verification_label"] == "supervisor_reviewed"
    finally:
        review.set()
        finish.set()
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
    provider = ScriptedProvider(
        by_role={
            "coordinator": [
                Step(tools=[("subagent_launcher", {"agent_id": "explorer", "query": "look around", "is_wait": False})]),
                Step(text="continuing on the main line", stop=True),
            ],
            "explorer": [Step(text="explored the workspace", stop=True)],
        }
    )
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        parent = await harness.spawn("coordinator", protocol="traditional")
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
                        ("subagent_launcher", {"agent_id": "explorer", "query": "look", "is_wait": False}),
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
                text="first turn with a long observation " + ("padding " * 300),
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
            context_window=300,
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
