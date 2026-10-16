"""统一运行结束门禁（Task 4A）：显式 stop 与无 tool_calls 的纯文本最终回复
必须到达同一个运行结束判定边界（runner 收尾前的 completion gate）。

计划 docs/superpowers/plans/2026-09-05-event-driven-supervisor.md §6：
- 四态判定：continue_work / wait_background / wait_review / allow_final；
- DAG Coordinator 完整交付门禁：guided partial 无批准进 wait_review（同一
  交付版本只创建一份退出请求），有效批准才放行；dag_record partial 经判定
  并明确记录后可结束；standard 普通问答可结束（标为 agent 声明，不假称验证）；
- schedule 模式的纯文本退出经过同一结束策略：有可核实未完成后台工作时，
  连续两次 stop 也不算完成；有可核实唤醒来源（有效 reminder）时是
  wait_background 挂起，后台完成消息到达后继续；
- 无进展退出有界：同一缺口状态反复退出耗尽上限后落 failed（可恢复非成功
  状态）并提示用户，不无限循环、不伪报完成；
- 门禁判定期间到达的消息不丢；用户取消优先；取消后迟到的批准/检查不启动
  新 run 或 LLM 请求。

测试确定性约定同 test_runtime_v2_supervision.py：asyncio.Event 门闩控制
时序，轮询/wait_for 只作失败上限；每个用例 finally 收束 runner task 与
reminder 定时器。
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.dag.review_requests import ReviewDecision, ReviewRequest
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import PolicyResult, ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentState, Command
from cloudra.runtime_v2.supervision import flush_review_notifications
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class _OkTools:
    """全成功执行替身（签名对齐真实 executor，带 **_kwargs）。"""

    async def execute(self, agent, call: ToolCall, **_kwargs) -> ToolResult:
        data = {"stopped": True, "message": "Task stopped."} if call.name == "stop" else {}
        return ToolResult(is_success=True, summary=f"ok:{call.name}", data=data)


class _RoutingLLM:
    """按角色路由的脚本化 LLM。

    supervisor 一律纯文本 stop（信箱已排空）；coordinator 顺序消费脚本，
    耗尽后重复最后一条响应——收尾竞态产生的额外唤醒轮次不会把测试打崩，
    无进展反复退出由门禁计数器有界兜底（这正是被测行为）。
    """

    def __init__(self, coordinator_script: list[LLMResponse]) -> None:
        assert coordinator_script, "script must not be empty"
        self._script = list(coordinator_script)
        self._fallback = coordinator_script[-1]
        self.coordinator_calls = 0
        self.supervisor_calls = 0
        self.coordinator_messages: list[list[dict]] = []

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id == "supervisor":
            self.supervisor_calls += 1
            return LLMResponse(content="mailbox drained; stop", stop_requested=True)
        self.coordinator_calls += 1
        self.coordinator_messages.append(list(messages))
        if self._script:
            return self._script.pop(0)
        return self._fallback


def _stop_call(call_id: str = "tc-stop", **arguments) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[ToolCall(id=call_id, name="stop", arguments=arguments)],
    )


async def _new_core(llm, *, workspace_dir=None, extra_stages=(), **runner_kwargs):
    core = RuntimeCore(strict_events=True)
    stages = [*extra_stages, *default_stages(core)]
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=_OkTools(),
        notices=core.notices,
    )
    core.runner = AgentRunner(
        core,
        pipeline,
        retry_backoff=(0.01, 0.01),
        **runner_kwargs,
    )
    bus = CommandBus(core)
    payload = {
        "name": "completion-gate",
        # 脚本化 LLM 直接发业务工具调用，固定传统协议（默认 javascript 只放
        # js_exec + 直接控制类）。
        "settings": {"defaults": {"invocation_protocol": "traditional"}},
    }
    if workspace_dir is not None:
        payload["workspace_dir"] = str(workspace_dir)
    project = (await bus.execute(Command(type="project.create", payload=payload))).data
    return core, bus, project


async def _spawn_coordinator(
    bus, project, *, mode: str | None = None, schedule_mode: bool = False, query="do the task"
):
    settings: dict = {}
    if mode:
        settings["orchestration_mode"] = mode
    if schedule_mode:
        settings["schedule_mode"] = True
    payload: dict = {"role_id": "coordinator", "settings": settings}
    if query is not None:
        payload["query"] = query
    result = await bus.execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload=payload)
    )
    return result.data


async def _teardown(core) -> None:
    if core.runner is not None:
        for session_id in list(core.runner._tasks):
            await core.runner.cancel(session_id)
    await core.reminders.close()


async def _wait_until(predicate, timeout: float = 5.0, what: str = "condition"):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.01)


async def _wait_state(agent, state: str, timeout: float = 5.0):
    await _wait_until(lambda: agent.state.value == state, timeout=timeout, what=f"state {state}")


async def _wait_parked(agent, llm: _RoutingLLM, timeout: float = 5.0):
    """等到系统停稳在 wait_review 挂起：状态为 waiting_approval 且两个采样
    窗内 LLM 请求数不再增长（证明等待裁决期间没有空转）。"""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        await _wait_state(agent, "waiting_approval", timeout=timeout)
        before = (llm.coordinator_calls, llm.supervisor_calls)
        await asyncio.sleep(0.1)
        after = (llm.coordinator_calls, llm.supervisor_calls)
        if agent.state.value == "waiting_approval" and before == after:
            return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(
                f"agent did not settle into wait_review: state={agent.state.value}, "
                f"llm calls {before} -> {after}"
            )


def _gate_events(core, session_id) -> list:
    return [
        e
        for e in core.event_log.query_session(session_id, types={"agent.completion_gate"})
    ]


async def _review_requests(project_id: str, state: str | None = "queued"):
    def _read():
        store = DagStore(ConversationDB(project_id).init())
        return store.list_review_requests(state)

    return await asyncio.to_thread(_read)


async def _dispositions(project_id: str) -> list[str]:
    def _read() -> list[str]:
        db = ConversationDB(project_id).init()
        with db.connect() as con:
            return [
                row[0]
                for row in con.execute(
                    "SELECT disposition FROM dag_delivery_dispositions ORDER BY rowid"
                )
            ]

    return await asyncio.to_thread(_read)


async def _seed_complete_delivery(project_id: str) -> None:
    """交付图种子：r/p 节点（structure_supported）+ step1 边（endpoint_supported，
    无阶段契约）——默认 mechanism 契约下 coverage 通过（判据同
    test_dag_completion.py::test_endpoint_supported_path_satisfies_default_contract）。"""

    def _write() -> None:
        from cloudra.dag.engine import DagEngine
        from cloudra.dag.models import (
            AddEdge,
            AddNode,
            ElementaryStepEdge,
            GraphActor,
            MutationBatch,
            OccurrenceNode,
        )

        db = ConversationDB(project_id).init()
        store = DagStore(db)
        store.ensure_bundle("s1")
        engine = DagEngine(store)
        for node_id, label, role in (("r", "R", "reactant"), ("p", "P", "product")):
            result = engine.apply_batch(
                MutationBatch(
                    session_id="s1",
                    actor=GraphActor.HARNESS,
                    actor_id="test-harness",
                    base_revisions=store.load_bundle().revisions,
                    rationale=f"seed {role}",
                    operations=[
                        AddNode(
                            op="add_node",
                            graph="delivery",
                            node=OccurrenceNode(
                                node_id=node_id,
                                label=label,
                                role=role,
                                evidence_level="structure_supported",
                            ),
                        )
                    ],
                )
            )
            assert result.accepted
        result = engine.apply_batch(
            MutationBatch(
                session_id="s1",
                actor=GraphActor.HARNESS,
                actor_id="test-harness",
                base_revisions=store.load_bundle().revisions,
                rationale="seed step1",
                operations=[
                    AddEdge(
                        op="add_edge",
                        graph="delivery",
                        edge=ElementaryStepEdge(
                            edge_id="step1",
                            source_node_id="r",
                            target_node_id="p",
                            label="step 1",
                            evidence_level="endpoint_supported",
                        ),
                    )
                ],
            )
        )
        assert result.accepted

    await asyncio.to_thread(_write)


async def _resolve_exit_request(project_id: str, request_id: str, *, verdict: str, reason: str, next_action: str | None = None) -> None:
    """裁决落库的 store 级等价物（真实 Supervisor agent 全环由
    test_runtime_v2_supervision.py::test_exit_review_roundtrip_drives_coordinator_to_approved_partial
    锁定）。"""

    def _write() -> None:
        store = DagStore(ConversationDB(project_id).init())
        request = store.get_review_request(request_id)
        assert request is not None
        decision = ReviewDecision(
            request_id=request.request_id,
            basis_fingerprint=request.basis_fingerprint,
            verdict=verdict,
            reason=reason,
            next_action=next_action,
        )
        result = store.resolve_review(decision, expected_basis=request.basis_fingerprint)
        assert result["accepted"], result

    await asyncio.to_thread(_write)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "script",
    [
        pytest.param([LLMResponse(content="final answer, no stop call")], id="plain_text"),
        pytest.param(
            [_stop_call(delivery_disposition="partial", reason="partial")], id="explicit_stop"
        ),
    ],
)
async def test_plain_text_and_explicit_stop_face_the_same_gate(tmp_path, script):
    """同一不完整 guided delivery：纯文本最终回复与显式 stop(partial) 得到
    相同的 wait_review 处置——不 finish_run(succeeded)、不登记未批准 partial、
    只创建一份退出审批请求。"""
    llm = _RoutingLLM(script)
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_parked(coordinator, llm)
        gates = _gate_events(core, coordinator.id)
        assert gates and all(e.data["action"] == "wait_review" for e in gates)
        # 被拦的判定不产生收尾依据（basis 保持 None，不冒充任何验证等级）。
        assert all(e.data["basis"] is None for e in gates)
        requests = await _review_requests(project.id)
        assert len(requests) == 1 and requests[0].kind == "exit"
        assert await _dispositions(project.id) == []
        assert not [
            e
            for e in core.event_log.query_session(coordinator.id)
            if e.type == "run.finished"
        ]
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_wait_review_parks_with_exit_review_feedback(tmp_path):
    """guided partial stop 进入 wait_review 时必须给 agent 一条讲清退出审批回路
    的反馈（诚实回执）：退出审查已提交 Supervisor（带 request_id）、run 挂起
    等裁决、批准后仅声明 partial 再调用 stop，由程序关联批准。批准到达后
    同一交付版本复用裁决放行，partial 处置落库一次。"""
    llm = _RoutingLLM([_stop_call(delivery_disposition="partial", reason="partial")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_parked(coordinator, llm)
        requests = await _review_requests(project.id)
        assert len(requests) == 1
        injected = [
            e
            for e in core.event_log.query_session(coordinator.id)
            if e.type == "agent.message_injected"
            and e.data.get("sender") == "completion_gate"
        ]
        assert injected, "wait_review must leave exit-review-loop feedback for the agent"
        content = str(injected[-1].data["content"])
        assert requests[0].request_id in content
        assert "suspended" in content
        assert "approval_id" not in content
        # 批准到达：挂起期间没有空转，裁决唤醒后复用同一请求放行。
        await _resolve_exit_request(
            project.id, requests[0].request_id, verdict="accept", reason="scoped partial is acceptable"
        )
        await flush_review_notifications(core, project.id)
        await _wait_state(coordinator, "succeeded")
        assert await _dispositions(project.id) == ["partial"]
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_complete_delivery_plain_text_requires_final_supervisor_review(tmp_path):
    """完整覆盖只允许提交最终审查，接受后同一 complete 声明才落库。"""
    llm = _RoutingLLM([LLMResponse(content="mechanism fully supported")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    await _seed_complete_delivery(project.id)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_parked(coordinator, llm)
        requests = await _review_requests(project.id)
        assert len(requests) == 1 and requests[0].proposal["disposition"] == "complete"
        assert await _dispositions(project.id) == []
        injected = [e for e in core.event_log.query_session(coordinator.id)
                    if e.type == "agent.message_injected" and e.data.get("sender") == "completion_gate"]
        assert injected and requests[0].request_id in injected[-1].data["content"]
        await _resolve_exit_request(project.id, requests[0].request_id,
                                   verdict="accept", reason="the proposed full delivery is supported")
        await flush_review_notifications(core, project.id)
        await _wait_state(coordinator, "succeeded")
        assert await _dispositions(project.id) == ["complete"]
        gates = _gate_events(core, coordinator.id)
        assert [gate.data["action"] for gate in gates] == ["wait_review", "allow_final"]
        assert gates[-1].data["basis"] == "supervisor_supported"
        assert len(await _review_requests(project.id, state=None)) == 1
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_valid_exit_approval_allows_finish(tmp_path):
    """guided partial：退出请求被接受后，coordinator 被裁决通知唤醒，同一
    交付版本复用已接受裁决放行，partial 处置明确落库一次。"""
    llm = _RoutingLLM([_stop_call(delivery_disposition="partial", reason="partial")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_parked(coordinator, llm)
        requests = await _review_requests(project.id)
        assert len(requests) == 1
        await _resolve_exit_request(
            project.id, requests[0].request_id, verdict="accept", reason="scoped partial is acceptable"
        )
        await flush_review_notifications(core, project.id)
        await _wait_state(coordinator, "succeeded")
        assert await _dispositions(project.id) == ["partial"]
        # 收尾依据是 Supervisor 的接受裁决（不是模型自述）。
        assert _gate_events(core, coordinator.id)[-1].data["basis"] == "supervisor_approved"
        assert await _review_requests(project.id) == []
        # 同一交付版本没有创建第二份退出请求。
        all_requests = await _review_requests(project.id, state=None)
        assert len(all_requests) == 1
        # 裁决通知确实进了 coordinator 的上下文通道（pin）。
        pinned = core.notices.collect_batch(coordinator.id, fresh=True)
        assert any("verdict=accept" in m["content"] for m in pinned)
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_rejected_exit_review_feeds_reason_and_next_action(tmp_path):
    """退出请求被拒绝：coordinator 唤醒后再次退出进入 continue_work，
    反馈带拒绝理由与下一步；不收敛的重复退出由计数器有界终止（failed）。"""
    llm = _RoutingLLM([_stop_call(delivery_disposition="partial", reason="partial")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_parked(coordinator, llm)
        requests = await _review_requests(project.id)
        await _resolve_exit_request(
            project.id,
            requests[0].request_id,
            verdict="reject",
            reason="Missing TS frequency evidence",
            next_action="run a frequency calculation",
        )
        await flush_review_notifications(core, project.id)
        # fallback 脚本反复 stop(partial)：拒绝理由不变 → 计数器耗尽 → failed。
        await _wait_state(coordinator, "failed")
        texts = [
            str(m.get("content"))
            for messages in llm.coordinator_messages
            for m in messages
        ]
        assert any(
            "Missing TS frequency evidence" in text and "run a frequency calculation" in text
            for text in texts
        ), "rejection feedback must carry the Supervisor's reason and next action"
        gates = _gate_events(core, coordinator.id)
        actions = [e.data["action"] for e in gates]
        # 首次退出是 wait_review（其后的挂起轮次数取决于督导回传唤醒时序，
        # 不作为契约）；拒绝后恰好 3 次 continue_work，第三次耗尽计数器。
        assert actions[0] == "wait_review"
        assert actions[-3:] == ["continue_work"] * 3
        assert actions.count("continue_work") == 3
        finished = [
            e
            for e in core.event_log.query_session(coordinator.id)
            if e.type == "run.finished"
        ]
        assert finished and finished[-1].data["outcome"] == "failed"
        # 耗尽提示对用户可见，且不伪报完成。
        emitted = [
            e
            for e in core.event_log.query_session(coordinator.id)
            if e.type == "agent.message_emitted"
        ]
        assert any("Completion gate" in str(e.data["content"]) for e in emitted)
        # 拒绝不登记交付处置。
        assert await _dispositions(project.id) == []
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_stale_approval_is_rejected_after_basis_change(tmp_path):
    """批准 basis 过期（交付图在裁决后变更）→ 旧批准失效，重新进入
    wait_review 并按新 basis 创建新请求。"""
    llm = _RoutingLLM([_stop_call(delivery_disposition="partial", reason="partial")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_parked(coordinator, llm)
        requests = await _review_requests(project.id)
        assert len(requests) == 1
        await _resolve_exit_request(
            project.id, requests[0].request_id, verdict="accept", reason="acceptable"
        )
        # 裁决后交付图变更（新增中间体节点）→ basis 与 target 集合都过期。
        await _seed_complete_delivery(project.id)
        await flush_review_notifications(core, project.id)
        await _wait_parked(coordinator, llm)
        gates = _gate_events(core, coordinator.id)
        assert gates[-1].data["action"] == "wait_review"
        all_requests = await _review_requests(project.id, state=None)
        assert len(all_requests) == 2
        assert [r.state for r in all_requests] == ["resolved", "queued"]
        assert await _dispositions(project.id) == []
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_dag_record_partial_plain_text_is_recorded_and_finishes(tmp_path):
    """dag_record 保留允许 partial 的既有语义，但纯文本退出同样经过判定：
    隐式 partial 明确记录后放行，不创建退出审批。"""
    llm = _RoutingLLM([LLMResponse(content="partial results summary")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_record")
    try:
        await _wait_state(coordinator, "succeeded")
        assert await _dispositions(project.id) == ["partial"]
        gates = _gate_events(core, coordinator.id)
        assert len(gates) == 1 and gates[0].data["action"] == "allow_final"
        assert gates[0].data["explicit_stop"] is False
        assert gates[0].data["basis"] == "partial_recorded"
        assert await _review_requests(project.id, state=None) == []
        assert llm.supervisor_calls == 0
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_standard_mode_plain_qa_finishes_as_declared(tmp_path):
    """standard 普通问答可结束：门禁无 DAG 意见，按 agent 声明放行并如实标注。"""
    llm = _RoutingLLM([LLMResponse(content="42")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project)
    try:
        await _wait_state(coordinator, "succeeded")
        gates = _gate_events(core, coordinator.id)
        assert len(gates) == 1
        assert gates[0].data["action"] == "allow_final"
        assert gates[0].data["source"] == "declared"
        assert gates[0].data["basis"] == "declared"
        assert "not independently verified" in gates[0].data["reason"]
        assert await _dispositions(project.id) == []
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_repeated_exit_same_version_creates_one_request_and_no_llm_spin(tmp_path):
    """同一交付版本反复退出只生成一份退出审批；复用既有请求时不再重复
    通知 Supervisor；挂起等待裁决期间 LLM 请求数不增长。"""
    llm = _RoutingLLM([_stop_call(delivery_disposition="partial", reason="partial")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_parked(coordinator, llm)
        first_requests = await _review_requests(project.id)
        assert len(first_requests) == 1
        first_id = first_requests[0].request_id
        assert llm.supervisor_calls == 1  # 只在创建请求时通知一次

        # 用户消息唤醒 → 同一版本再次退出 → 复用既有请求（不新建、不重复通知）。
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": coordinator.id},
                payload={"content": "still waiting on the review?"},
            )
        )
        await _wait_parked(coordinator, llm)
        second_requests = await _review_requests(project.id)
        assert [r.request_id for r in second_requests] == [first_id]
        assert llm.supervisor_calls == 1

        # 等待裁决期间：两个采样窗内任何 LLM 请求数都不增长。
        before = (llm.coordinator_calls, llm.supervisor_calls)
        await asyncio.sleep(0.15)
        assert (llm.coordinator_calls, llm.supervisor_calls) == before
        assert coordinator.state.value == "waiting_approval"
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_no_progress_exit_exhaustion_fails_with_structured_kind(tmp_path):
    """同一缺口反复退出耗尽预算：run 落 failed，分类是 completion_no_progress
    ——独立的失败桶，不与 provider/科学失败混在一起（评审 5.10）。"""
    llm = _RoutingLLM([_stop_call(delivery_disposition="complete", reason="done")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path, max_exit_strikes=2)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_state(coordinator, "failed")
        gates = _gate_events(core, coordinator.id)
        assert gates and all(e.data["action"] == "continue_work" for e in gates)
        finished = [
            e
            for e in core.event_log.query_session(coordinator.id)
            if e.type == "run.finished"
        ]
        assert finished[-1].data["outcome"] == "failed"
        assert finished[-1].data["failure_kind"] == "completion_no_progress"
        assert "without progress" in (finished[-1].data["error"] or "")
        assert await _dispositions(project.id) == []
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_schedule_plain_text_exit_goes_through_gate(tmp_path):
    """schedule 模式纯文本退出经同一结束策略：无可核实后台工作时按
    agent 声明放行（不假称已验证完成）。"""
    llm = _RoutingLLM([LLMResponse(content="task done")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, schedule_mode=True)
    try:
        await _wait_state(coordinator, "succeeded")
        gates = _gate_events(core, coordinator.id)
        assert len(gates) == 1
        assert gates[0].data["action"] == "allow_final"
        assert gates[0].data["source"] == "schedule"
        assert "agent-declared" in gates[0].data["reason"]
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_schedule_background_without_wakeup_source_is_not_completed(tmp_path):
    """有可核实未完成后台工作（未终态兄弟 agent）且无唤醒来源时，连续
    stop（含第二次自我确认）不代表完成：continue_work 反馈要求先 schedule，
    反复无进展退出有界耗尽落 failed。"""
    llm = _RoutingLLM([_stop_call(reason="confirm done")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    # 兄弟 agent：无 query 保持 queued（非终态）——可核实的未完成后台。
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "explorer"},
        )
    )
    coordinator = await _spawn_coordinator(bus, project, schedule_mode=True)
    try:
        await _wait_state(coordinator, "failed")
        gates = _gate_events(core, coordinator.id)
        assert gates and all(e.data["action"] == "continue_work" for e in gates)
        texts = [
            str(m.get("content"))
            for messages in llm.coordinator_messages
            for m in messages
        ]
        assert any("schedule" in text and "wake" in text for text in texts)
        finished = [
            e
            for e in core.event_log.query_session(coordinator.id)
            if e.type == "run.finished"
        ]
        assert finished[-1].data["outcome"] == "failed"
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_schedule_wait_background_then_reminder_fire_continues(tmp_path, monkeypatch):
    """有效 reminder 是可核实唤醒来源：纯文本退出判 wait_background 挂起
    （succeeded 但无完成处置）；reminder 到点触发后台完成消息，agent 继续
    处理并在下一轮正常结束。"""

    async def fake_summarize(agent, messages, **_kwargs):
        return "POLL TAIL SUMMARY"

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", fake_summarize
    )
    llm = _RoutingLLM(
        [
            LLMResponse(content="waiting for the job to finish"),
            LLMResponse(content="job verified done"),
        ]
    )
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, schedule_mode=True, query=None)
    # 先创建 reminder 再开跑，消除"首轮结束早于 reminder 创建"的竞态。
    reminder = await core.reminders.handle(
        coordinator,
        ToolCall(
            id="t-rem",
            name="schedule",
            arguments={
                "action": "create",
                "message": "check the compute job",
                "delay_seconds": 0.2,
            },
        ),
    )
    assert reminder.is_success
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": coordinator.id},
            payload={"content": "watch the job"},
        )
    )
    try:
        # 第一 run：reminder pending → wait_background 挂起（succeeded 非交付）。
        await _wait_until(lambda: llm.coordinator_calls == 1, what="first turn")
        await _wait_state(coordinator, "succeeded")
        gates = _gate_events(core, coordinator.id)
        assert [e.data["action"] for e in gates] == ["wait_background"]
        # reminder 到点 → [Reminder] 消息唤醒 → 第二 run 正常结束。
        await _wait_until(lambda: llm.coordinator_calls == 2, what="reminder wake turn")
        await _wait_state(coordinator, "succeeded")
        gates = _gate_events(core, coordinator.id)
        assert [e.data["action"] for e in gates] == ["wait_background", "allow_final"]
        second_run_messages = llm.coordinator_messages[1]
        assert any("[Reminder]" in str(m.get("content")) for m in second_run_messages)
        runs = [
            e for e in core.event_log.query_session(coordinator.id) if e.type == "run.started"
        ]
        assert len(runs) == 2
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_terminal_notice_during_gate_is_read_before_child_reports(tmp_path):
    """A compute notice can be marked delivered while the stop gate is running."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.runtime_v2.failures import RunFailureKind
    from cloudra.runtime_v2.policies.schedule_stage import ScheduleStage
    from cloudra.services.compute_store import ainsert_compute_job

    llm = _RoutingLLM([_stop_call(reason="waiting"), LLMResponse(content="verified result")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    parent = await _spawn_coordinator(bus, project, query=None)
    await core.agent_host.start_run(parent)
    await core.agent_host.finish_run(
        parent, outcome="failed", error="park parent", failure_kind=RunFailureKind.PIPELINE_INTERNAL
    )
    child = (
        await bus.execute(Command(
            type="agent.spawn", target={"project_id": project.id},
            payload={"role_id": "small_mol", "parent_session_id": parent.id},
        ))
    ).data
    await ainsert_compute_job(
        await ComputeDB().ainit(), conversation_id=project.id, session_id=child.id,
        path=str(tmp_path / "job.gjf"), state="done", jobtype="gaussian", node_id="local",
    )
    stage = next(s for s in core.runner.pipeline.stages if isinstance(s, ScheduleStage))
    entered = asyncio.Event()
    release = asyncio.Event()
    original = stage._owned_compute_pending

    async def paused_owned_check(ctx):
        if ctx.agent.id == child.id and not entered.is_set():
            entered.set()
            await release.wait()
        return await original(ctx)

    stage._owned_compute_pending = paused_owned_check
    try:
        await bus.execute(Command(
            type="agent.message", target={"session_id": child.id},
            payload={"content": "review the job"},
        ))
        await asyncio.wait_for(entered.wait(), timeout=5)
        await ComputeNotifyBroker(core)._poll_project(project.id)
        release.set()
        await _wait_state(child, "succeeded")
        await _wait_until(
            lambda: bool([
                e for e in core.event_log.query_session(parent.id, types={"agent.message_injected"})
                if (e.data.get("manifest") or {}).get("kind") == "child_completion"
            ]),
            what="child result",
        )
        reports = [
            e.data["manifest"]
            for e in core.event_log.query_session(parent.id, types={"agent.message_injected"})
            if (e.data.get("manifest") or {}).get("kind") == "child_completion"
        ]
        assert len(reports) == 1
        assert reports[0]["final_summary"] == "verified result"
        assert llm.coordinator_calls == 2
    finally:
        release.set()
        await _teardown(core)


@pytest.mark.asyncio
async def test_message_arriving_during_gate_evaluation_is_not_lost(tmp_path):
    """门禁判定期间投递给顶层 agent 的消息由新 run 消费。"""

    class _GateTrap:
        """在统一门禁判定期间注入一条用户消息（deliver 撞 RUNNING）。"""

        name = "gate_trap"

        def __init__(self, core, project_id: str, session_id: str) -> None:
            self._core = core
            self._project_id = project_id
            self._session_id = session_id
            self._armed = True

        async def before_tool(self, ctx, call, **_kwargs):
            return PolicyResult.allow()

        async def after_tool(self, ctx, call, result, **_kwargs) -> None:
            return None

        async def before_llm(self, ctx, messages, **_kwargs) -> None:
            return None

        async def audit_run_end(self, ctx, *, explicit_stop, stop_arguments=None, **_kwargs):
            if not self._armed or ctx.agent.id != self._session_id:
                return None
            self._armed = False
            await self._core.dispatcher.commit_and_deliver(
                to_session_id=self._session_id,
                project_id=self._project_id,
                content="late user input",
                sender="user",
                wake=WakePolicy.NEVER,
            )
            return None

    llm = _RoutingLLM(
        [LLMResponse(content="first answer"), LLMResponse(content="second answer")]
    )
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    # spawn 无 query → queued；先装上带 trap 的管线再发消息开跑。
    coordinator = await _spawn_coordinator(bus, project, query=None)
    trap = _GateTrap(core, project.id, coordinator.id)
    # 重建带 trap 的管线（复用同一 core，事件流连续）。
    stages = [trap, *default_stages(core)]
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=_OkTools(),
        notices=core.notices,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    try:
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": coordinator.id},
                payload={"content": "start"},
            )
        )
        await _wait_until(lambda: llm.coordinator_calls == 2, what="second run")
        await _wait_state(coordinator, "succeeded")
        runs = [
            e for e in core.event_log.query_session(coordinator.id) if e.type == "run.started"
        ]
        assert len(runs) == 2
        # 迟到消息进入第二 run 的模型上下文，没丢。
        assert any(
            "late user input" in str(m.get("content")) for m in llm.coordinator_messages[1]
        )
    finally:
        await _teardown(core)


@pytest.mark.asyncio
async def test_cancel_during_gate_evaluation_wins_and_late_approval_does_not_revive(tmp_path):
    """竞态（Event 门闩）：门禁判定期间用户取消优先——取消后不落
    finish_run、不创建退出审批；迟到的批准 flush 不启动新 run 或 LLM 请求。"""

    entered = asyncio.Event()
    release = asyncio.Event()

    class _LatchedGateTrap:
        name = "latched_gate_trap"

        def __init__(self, session_id: str) -> None:
            self._session_id = session_id

        async def before_tool(self, ctx, call, **_kwargs):
            return PolicyResult.allow()

        async def after_tool(self, ctx, call, result, **_kwargs) -> None:
            return None

        async def before_llm(self, ctx, messages, **_kwargs) -> None:
            return None

        async def audit_run_end(self, ctx, *, explicit_stop, stop_arguments=None, **_kwargs):
            if ctx.agent.id != self._session_id:
                return None
            entered.set()
            await release.wait()
            return None

    llm = _RoutingLLM([_stop_call(delivery_disposition="partial", reason="partial")])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided", query=None)
    trap = _LatchedGateTrap(coordinator.id)
    stages = [trap, *default_stages(core)]
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=_OkTools(),
        notices=core.notices,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    try:
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": coordinator.id},
                payload={"content": "start"},
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=5)
        # 门禁判定挂起期间取消：取消优先，收尾判定被 CancelledError 中断。
        await bus.execute(Command(type="agent.cancel", target={"session_id": coordinator.id}, payload={}))
        assert coordinator.state is AgentState.CANCELLED
        assert llm.coordinator_calls == 1
        assert _gate_events(core, coordinator.id) == []
        assert not [
            e
            for e in core.event_log.query_session(coordinator.id)
            if e.type == "run.finished"
        ]
        # 取消路径不触发退出审批：没有创建任何 review 请求。
        assert await _review_requests(project.id, state=None) == []

        # 迟到批准：裁决落库 + flush——recipient 已取消，不启动新 run/LLM。
        def _late_approval() -> None:
            store = DagStore(ConversationDB(project.id).init())
            store.ensure_bundle(coordinator.id)
            request = ReviewRequest(
                kind="exit",
                requester=coordinator.id,
                target_ids=["dag_delivery"],
                question="May this delivery finish as a partial result?",
                proposal={"disposition": "partial", "scope": ["dag_delivery"]},
                basis_fingerprint="sha256:pending",
            )
            basis = store.review_basis(request)
            request = request.model_copy(update={"basis_fingerprint": basis})
            request_id = store.enqueue_review(request)
            decision = ReviewDecision(
                request_id=request_id,
                basis_fingerprint=basis,
                verdict="accept",
                reason="late accept after cancel",
            )
            result = store.resolve_review(decision, expected_basis=basis)
            assert result["accepted"], result

        await asyncio.to_thread(_late_approval)
        await flush_review_notifications(core, project.id)
        await asyncio.sleep(0.1)
        assert coordinator.state is AgentState.CANCELLED
        assert llm.coordinator_calls == 1
        runs = [
            e for e in core.event_log.query_session(coordinator.id) if e.type == "run.started"
        ]
        assert len(runs) == 1
    finally:
        release.set()
        await _teardown(core)


@pytest.mark.asyncio
@pytest.mark.parametrize("source,candidate", [
    ("plain_text", "initial-reviewed-candidate-marker"),
    ("stop_omitted", "initial-reviewed-candidate-marker"),
    ("stop_empty", "initial-reviewed-candidate-marker"),
    ("stop_empty", ""),
])
async def test_review_binds_actual_candidate_when_stop_final_answer_is_omitted(tmp_path, source, candidate):
    arguments = {"delivery_disposition": "partial", "reason": "Scope exhausted"}
    if source == "stop_empty":
        arguments["final_answer"] = ""
    request = LLMResponse(content=candidate, tool_calls=[ToolCall(
        id="first-stop", name="stop", arguments=arguments
    )] if source != "plain_text" else [])
    llm = _RoutingLLM([request])
    core, bus, project = await _new_core(llm, workspace_dir=tmp_path)
    coordinator = await _spawn_coordinator(bus, project, mode="dag_guided")
    try:
        await _wait_parked(coordinator, llm)
        requests = await _review_requests(project.id)
        assert len(requests) == 1
        assert requests[0].proposal["final_answer"] == candidate
        assert not any(event.type == "agent.message_emitted" and event.data.get("content") == candidate
            for event in core.event_log.query_session(coordinator.id))
        confirmation = LLMResponse(content="unreviewed-confirmation-marker", tool_calls=[ToolCall(
            id="confirm-stop", name="stop", arguments={"delivery_disposition": "partial", "reason": "", "final_answer": ""}
        )])
        llm._script = [confirmation]
        llm._fallback = confirmation
        await _resolve_exit_request(project.id, requests[0].request_id,
            verdict="accept", reason="Approved the stored candidate")
        await flush_review_notifications(core, project.id)
        await _wait_state(coordinator, "succeeded")
        emitted = [event.data.get("content") for event in core.event_log.query_session(coordinator.id)
            if event.type == "agent.message_emitted"]
        if candidate:
            assert candidate in emitted
        assert "unreviewed-confirmation-marker" not in emitted
        saved = await asyncio.to_thread(lambda: DagStore(ConversationDB(project.id)).list_review_requests(None))
        assert [item.request_id for item in saved] == [requests[0].request_id]
    finally:
        await _teardown(core)
