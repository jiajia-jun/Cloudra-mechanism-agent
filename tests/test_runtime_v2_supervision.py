"""事件驱动 Supervisor 的接口与生命周期回归（Task 1 锁定，Task 3 转绿）。

目标架构（计划 2026-09-05-event-driven-supervisor，2026-09-06 修订 §5）：
Supervisor 是项目内唯一的普通 runtime_v2 agent（role_id="supervisor"），
由 AgentRunner / TurnPipeline / InvocationService 驱动；研究工具完成只登记
证据不送审，显式送审（持久化入箱 + notify_supervisor）才按状态表通知。

覆盖：门闩/取消/并发唯一性/failed 不复活/succeeded 唤醒/reconcile 补通知
（Task 1 六条）+ Task 3 增量：waiting 不被通知绕过、显式送审后 24 次研究
解析端到端不阻塞不新增 review、退出审批全环（真实 Supervisor agent 裁决
驱动 Coordinator 从 wait_review 走到批准 partial）、裁决通知的持久化投递
与恢复、legacy 库 schema 补齐守卫。

测试确定性约定：asyncio.Event 门闩控制时序，wait_for/轮询只作失败上限；
每个用例 finally 释放门闩并收束 runner task，不留悬挂。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest

from cloudra.dag.models import CallReview
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.failures import RunFailureKind
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentState, Command, InvocationProtocol
from cloudra.runtime_v2.supervision import (
    TERMINAL_SUPERVISOR_PIN_KEY,
    find_project_supervisor,
    flush_review_notifications,
    notify_supervisor,
    reconcile_supervision,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

SUPERVISOR_ROLE_ID = "supervisor"


class _LatchedSupervisorLLM:
    """按角色路由的 fake LLM：supervisor 轮次挂门闩，研究轮次走脚本。

    门闩语义照抄计划 Task 1 代码块：``entered`` 在 supervisor 首次进入 LLM
    时 set，``release`` 放开后返回一条 stop 响应。``fail_supervisor`` 用于
    构造 failed 终态。fake supervisor 从不发业务工具调用（裁决工具投影是
    Task 2 的范围），只验证生命周期与通知边界。
    """

    def __init__(self, *, fail_supervisor: bool = False) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.fail_supervisor = fail_supervisor
        self.supervisor_calls = 0
        self.research_responses: list[LLMResponse] = []

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id == SUPERVISOR_ROLE_ID:
            self.supervisor_calls += 1
            if self.fail_supervisor:
                raise RuntimeError("supervisor LLM down")
            self.entered.set()
            await self.release.wait()
            return LLMResponse(content="mailbox drained; stop", stop_requested=True)
        assert self.research_responses, "no scripted research response left"
        return self.research_responses.pop(0)


class _ResearchTools:
    """记录已完成工具调用的执行替身（签名对齐真实 executor，带 **_kwargs）。"""

    def __init__(self) -> None:
        self.finished: list[str] = []

    async def execute(self, agent, call: ToolCall, **_kwargs) -> ToolResult:
        self.finished.append(call.name)
        return ToolResult(is_success=True, summary=f"ok:{call.name}", data={})


async def _setup(llm) -> tuple[RuntimeCore, CommandBus, object]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=_ResearchTools(),
    )
    # 小退避让 failed 用例确定性快速到位（默认 (2.0, 4.0) 是纯耗时）。
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    bus = CommandBus(core)
    project = (
        await bus.execute(Command(type="project.create", payload={"name": "supervision"}))
    ).data
    return core, bus, project


async def _seed_pending_review(project_id: str) -> str:
    """显式送审的持久化等价物：直接入箱一条 pending CallReview。

    生产路径是 dag_bind_evidence → submit_evidence_for_review → 持久化 →
    notify_supervisor；本测试只需锁定"持久化待办 + notify"的后半段契约。
    conftest 已把 data_dir 隔离到 tmp_path，ConversationDB 落在临时目录。
    """
    review_id = "rev_" + uuid.uuid4().hex

    def _write() -> None:
        store = DagStore(ConversationDB(project_id).init())
        store.enqueue_call_review(
            CallReview(
                review_id=review_id,
                tool_call_id="tc_seed",
                tool_name="log_parser",
                is_success=True,
                caller_session_id="s_research",
                caller_role_id="coordinator",
                caller_legacy_id="a-0",
                arguments_digest="sha256:seed",
                result_summary="{}",
                source_path="",
                result_kind="ok",
                state="pending",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    await asyncio.to_thread(_write)
    return review_id


async def _pending_review_ids(project_id: str) -> list[str]:
    def _read() -> list[str]:
        store = DagStore(ConversationDB(project_id))
        return [row.review_id for row in store.list_call_reviews("pending")]

    return await asyncio.to_thread(_read)


async def _wait_state(agent, state: str, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


async def _wait_run_count(core, agent, count: int, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        runs = [
            e for e in core.event_log.query_session(agent.id) if e.type == "run.started"
        ]
        if len(runs) >= count:
            return runs
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"expected {count} runs, got {len(runs)}")
        await asyncio.sleep(0.01)


async def _teardown(core, *agents) -> None:
    """释放门闩后的收束：取消仍活跃的 agent，等 runner task 全部落地。"""
    bus = CommandBus(core)
    for agent in agents:
        if agent is None:
            continue
        if agent.state.value in {"queued", "running", "waiting"}:
            await bus.execute(
                Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
            )
    tasks = [t for t in core.runner._tasks.values() if not t.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    # detached run finalize（stub summarizer）收尾拍。
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_explicit_review_notification_does_not_block_research_tools():
    """门闩回归。

    显式送审（持久化 CallReview + notify_supervisor）使项目唯一 Supervisor
    agent 开跑；其 LLM 被门闩挂起期间，研究 agent 的后续 log_parser 调用
    必须完成返回（不等待督导裁决）；门闩释放前不发生真实裁决（review 保持
    pending）。
    """
    llm = _LatchedSupervisorLLM()
    llm.research_responses = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="tc1", name="log_parser", arguments={"log_path": "a.log"})],
        ),
        LLMResponse(content="parsed a", stop_requested=True),
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="tc2", name="log_parser", arguments={"log_path": "b.log"})],
        ),
        LLMResponse(content="parsed b", stop_requested=True),
    ]
    core, bus, project = await _setup(llm)
    tools = core.runner.pipeline.tools
    research = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": "parse logs"},
            )
        )
    ).data
    # ScriptedLLM 直接发业务工具调用，固定传统协议（默认 javascript 只放
    # js_exec + 直接控制类）。
    research.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    await _wait_state(research, "succeeded")

    supervisor = None
    try:
        review_id = await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None, "notify must ensure the supervisor identity"
        await asyncio.wait_for(llm.entered.wait(), timeout=5)

        # 生产端在督导 LLM 挂起期间继续工作：唤醒研究 agent 跑第二个
        # log_parser，必须能完成返回（不串进督导耗时）。
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": research.id},
                payload={"content": "parse the next log"},
            )
        )
        await _wait_state(research, "succeeded")
        assert tools.finished == ["log_parser", "log_parser"]

        # 门闩释放前不发生真实裁决：送审的 review 仍是 pending。
        assert await _pending_review_ids(project.id) == [review_id]
    finally:
        llm.release.set()
        await _teardown(core, research, supervisor)


@pytest.mark.asyncio
async def test_cancelled_supervisor_is_not_resurrected_by_release_or_new_reviews():
    """取消回归。

    对照故障基线（计划"已验证的故障基线"：壳 23:36:27 被用户取消，
    23:36:34 仍输出，23:36:35 被自动重启）：用户取消 Supervisor 后，释放
    fake LLM 门闩或再送新 review 都不能生成新 run/继续裁决。
    """
    llm = _LatchedSupervisorLLM()
    core, bus, project = await _setup(llm)
    supervisor = None
    try:
        await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await asyncio.wait_for(llm.entered.wait(), timeout=5)

        result = await bus.execute(
            Command(type="agent.cancel", target={"session_id": supervisor.id}, payload={})
        )
        assert result.data.state == "cancelled"

        # 释放门闩：挂起的 LLM 调用已被取消语义收束，不得生成新 run。
        llm.release.set()
        await asyncio.sleep(0.05)
        assert supervisor.state.value == "cancelled"
        runs = [
            e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
        ]
        assert len(runs) == 1

        # 再送新 review：系统通知不复活用户取消的 Supervisor（状态表：
        # cancelled 驻留信箱 parked，不自动复活）。
        await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="second explicit submission")
        await asyncio.sleep(0.05)
        assert supervisor.state.value == "cancelled"
        runs = [
            e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
        ]
        assert len(runs) == 1
        # 取消收尾扫描复用原版本；只有新增待办另驻留通知，不复活 Supervisor。
        inbox = core.mailbox.inbox(supervisor.id)
        assert inbox is not None and inbox.qsize() == 1
    finally:
        llm.release.set()
        await _teardown(core, supervisor)


@pytest.mark.asyncio
async def test_concurrent_first_notifications_create_single_supervisor():
    """项目唯一性。

    并发两次首次 notify_supervisor 只产生一个 supervisor agent（身份由
    core.agents 的 项目+角色 投影确定，复用 CommandBus 序列化边界）。
    """
    llm = _LatchedSupervisorLLM()
    core, _bus, project = await _setup(llm)
    supervisor = None
    try:
        await _seed_pending_review(project.id)
        await asyncio.gather(
            notify_supervisor(core, project.id, reason="first"),
            notify_supervisor(core, project.id, reason="second"),
        )
        supervisors = [
            agent
            for agent in core.agents.values()
            if agent.project_id == project.id and agent.role_id == SUPERVISOR_ROLE_ID
        ]
        assert len(supervisors) == 1
        supervisor = supervisors[0]
        assert find_project_supervisor(core, project.id).id == supervisor.id
    finally:
        llm.release.set()
        await _teardown(core, supervisor)


@pytest.mark.asyncio
async def test_failed_supervisor_is_not_resurrected_by_notification():
    """状态表：failed 不复活。

    Supervisor run 失败（fake LLM 持续抛错，重试耗尽落 failed）后，新的
    系统通知保留待办但不再 reopen/开新 run；显式恢复后继续（恢复路径本身
    由 Task 4 覆盖）。
    """
    llm = _LatchedSupervisorLLM(fail_supervisor=True)
    core, _bus, project = await _setup(llm)
    supervisor = None
    try:
        await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await _wait_state(supervisor, "failed")
        calls_at_failure = llm.supervisor_calls
        assert calls_at_failure >= 1

        await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="notification after failure")
        await asyncio.sleep(0.05)
        assert supervisor.state.value == "failed"
        assert llm.supervisor_calls == calls_at_failure
        runs = [
            e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
        ]
        assert len(runs) == 1
        # parked：失败时复用已消费的版本；新增待办只驻留一条，不唤醒。
        inbox = core.mailbox.inbox(supervisor.id)
        assert inbox is not None and inbox.qsize() == 1
        # 待办保留：两条送审 review 都还在信箱里等显式恢复。
        assert len(await _pending_review_ids(project.id)) == 2
    finally:
        llm.release.set()
        await _teardown(core, supervisor)


@pytest.mark.asyncio
@pytest.mark.parametrize("scientific_pending", [True, False])
async def test_supervisor_failure_alerts_only_for_pending_scientific_work(tmp_path, scientific_pending):
    """A single notification must surface a failed scientific review, without notebook noise."""
    from tests.agent_scenarios import ProviderFault, ScenarioHarness, ScriptedProvider, Step

    coordinator_wait = asyncio.Event()
    provider = ScriptedProvider(by_role={
        "supervisor": [Step(error=ProviderFault("scripted provider failure", status_code=400))],
        "coordinator": [Step(wait_for=coordinator_wait)],
    })
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    supervisor = None
    try:
        coordinator = await harness.spawn("coordinator", query="", orchestration_mode="dag_guided")
        if scientific_pending:
            review_id = await _seed_pending_review(harness.project.id)
        else:
            await asyncio.to_thread((tmp_path / "PROCESS.md").write_text, "Provisional hypothesis\n")

        await notify_supervisor(
            harness.core, harness.project.id, reason="single project update",
            changed_note=None if scientific_pending else ("PROCESS.md", "fixture-note-version"),
        )
        supervisor = find_project_supervisor(harness.core, harness.project.id)
        assert supervisor is not None
        await harness.wait_for(lambda: supervisor.state is AgentState.FAILED, "Supervisor LLM failure")
        if scientific_pending:
            await harness.wait_for(
                lambda: len(_injections(harness.core, coordinator.id, "[Supervision] ALERT")) == 1
                and coordinator.state is AgentState.RUNNING,
                "failure itself delivers the scientific backlog alert", timeout=2,
            )
            assert len(_pin_events(harness.core, coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY)) == 1
            assert await _pending_review_ids(harness.project.id) == [review_id]
            assert coordinator.state is AgentState.RUNNING
        else:
            await harness.settle()
            assert _injections(harness.core, coordinator.id, "[Supervision] ALERT") == []
            assert _pin_events(harness.core, coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY) == []
            assert coordinator.state is AgentState.QUEUED

        await harness.settle()
        assert supervisor.state is AgentState.FAILED
        assert provider.call_count("supervisor") == 1
        assert harness.types(supervisor).count("run.started") == 1
        assert _injections(harness.core, coordinator.id, "[Sub-agent finished]") == []
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_succeeded_supervisor_wakes_with_new_run_on_notification():
    """状态表：succeeded 唤醒。

    Supervisor 正常休眠（succeeded）后，新待办通知经正常 wake 开新 run
    并重读持久化信箱；run 身份必须换新。
    """
    llm = _LatchedSupervisorLLM()
    llm.release.set()  # 本用例不挂门闩：supervisor 每轮读信箱后立即 stop
    core, _bus, project = await _setup(llm)
    supervisor = None
    try:
        await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await _wait_state(supervisor, "succeeded")
        first_runs = await _wait_run_count(core, supervisor, 1)

        await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="second explicit submission")
        await _wait_state(supervisor, "succeeded")
        runs = await _wait_run_count(core, supervisor, 2)
        assert runs[1].run_id != runs[0].run_id
        assert len(first_runs) == 1
    finally:
        llm.release.set()
        await _teardown(core, supervisor)


class _ScriptedResearchLLM:
    """研究 agent 的顺序脚本 fake LLM（带 **_kwargs，对齐真实 provider）。"""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls += 1
        assert self.responses, "no scripted research response left"
        return self.responses.pop(0)


class _ParseTools:
    """研究侧解析类工具的执行替身：任何调用都成功返回（带 **_kwargs）。

    dag_bind_evidence 例外委派给真实 LegacyToolExecutor：显式送审必须经
    真实工具入口持久化，不由替身伪造回执。
    """

    def __init__(self, bind_executor=None) -> None:
        self.finished: list[str] = []
        self._bind_executor = bind_executor

    async def execute(self, agent, call: ToolCall, **_kwargs) -> ToolResult:
        if call.name == "dag_bind_evidence" and self._bind_executor is not None:
            return await self._bind_executor.execute(agent, call)
        self.finished.append(call.name)
        return ToolResult(is_success=True, summary=f"ok:{call.name}", data={})


async def _approve_final_delivery(project_id: str, session_id: str) -> None:
    """督导生命周期测试已通过最终审查的交付种子；不启动运行时督导。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.review_requests import ReviewDecision

    db = await asyncio.to_thread(lambda: ConversationDB(project_id).init())
    controller = DagController(db, session_id, "dag_guided", conversation_id=project_id)
    gate = await controller.audit_stop("complete")
    assert gate.action == "wait_review"
    request = await asyncio.to_thread(controller.store.get_review_request, gate.request_id)
    assert (await asyncio.to_thread(controller.store.resolve_review, ReviewDecision(
        request_id=request.request_id, basis_fingerprint=request.basis_fingerprint,
        verdict="accept", reason="fixture final-delivery review accepted"),
        expected_basis=request.basis_fingerprint))["accepted"]


@pytest.mark.asyncio
async def test_research_tool_completions_create_no_reviews_and_no_supervisor():
    """§5 核心语义：24 次研究侧工具完成不创建任何 review、不启动 Supervisor。

    覆盖 registry 原自动入箱的四类工具（log_parser/reaction_mapping/
    thermo_analysis/ts_guess，各 6 次）：完成后只登记证据与事实（dag_evidence
    行在），CallReview 信箱保持为空，项目里不出现 supervisor agent
    （最终交付已在种子中获得一次督导接受，研究工具完成不触发额外审查）。
    """
    tools_of_interest = ("log_parser", "reaction_mapping", "thermo_analysis", "ts_guess")
    responses = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id=f"tc{i}",
                    name=tools_of_interest[i % len(tools_of_interest)],
                    arguments={"log_path": f"log{i}.out"},
                )
            ],
        )
        for i in range(24)
    ]
    responses.append(LLMResponse(content="all parsed", stop_requested=True))
    llm = _ScriptedResearchLLM(responses)

    core = RuntimeCore(strict_events=True)
    executor = _ParseTools()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=llm,
        tools=executor,
        notices=core.notices,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={
                    "name": "explicit-only",
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    research = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},  # no query → stays queued
            )
        )
    ).data
    research.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    from cloudra.runtime_v2.schemas import OrchestrationMode

    research.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    # 本用例只守研究工具完成的通知边界，最终交付审查先作为种子接受。
    await _seed_complete_delivery(project.id)
    await _approve_final_delivery(project.id, research.id)
    try:
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": research.id},
                payload={"content": "parse the 24 logs"},
            )
        )
        await _wait_state(research, "succeeded")
        assert executor.finished == [
            tools_of_interest[i % len(tools_of_interest)] for i in range(24)
        ]

        def _read_back() -> tuple[int, int]:
            db = ConversationDB(project.id)
            db.migrate_if_needed()
            store = DagStore(db)
            reviews = store.list_call_reviews(None)
            with db.connect() as con:
                evidence_rows = con.execute(
                    "SELECT COUNT(*) FROM dag_evidence"
                ).fetchone()[0]
            return len(reviews), evidence_rows

        n_reviews, n_evidence = await asyncio.to_thread(_read_back)
        # 证据登记保留（24 份全部入库），review 信箱为零。
        assert n_evidence == 24
        assert n_reviews == 0
        # 不启动 Supervisor：项目里没有 supervisor agent。
        assert find_project_supervisor(core, project.id) is None
    finally:
        await _teardown(core, research)


@pytest.mark.asyncio
async def test_reconcile_supervision_notifies_on_persisted_backlog():
    """恢复回归。

    项目装载/显式恢复后读取持久化待办（证据已落库、通知前崩溃的窗口），
    非空则按同一状态表补通知：无 agent 则创建并启动；信箱为空则 no-op。
    """
    llm = _LatchedSupervisorLLM()
    core, _bus, project = await _setup(llm)
    supervisor = None
    try:
        # 空信箱：reconcile 不得创建 supervisor。
        await reconcile_supervision(core, project.id)
        assert find_project_supervisor(core, project.id) is None

        # 落库后通知前崩溃的恢复：补通知让 supervisor 开跑。
        await _seed_pending_review(project.id)
        await reconcile_supervision(core, project.id)
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await asyncio.wait_for(llm.entered.wait(), timeout=5)
    finally:
        llm.release.set()
        await _teardown(core, supervisor)


@pytest.mark.asyncio
async def test_waiting_supervisor_keeps_notification_without_bypassing_wait():
    """状态表：waiting 不被普通通知绕过，消息保留投递到信箱。

    督导挂在审批/输入等待时，新增待办的系统通知只进信箱队列——不 resume、
    不开新 run；恢复后由信箱驱动继续。
    """
    llm = _LatchedSupervisorLLM()
    core, _bus, project = await _setup(llm)
    supervisor = None
    try:
        await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await asyncio.wait_for(llm.entered.wait(), timeout=5)

        # 进入等待态（agent_host 是非命令路径的命令式壳，runner 内部同款）。
        await core.agent_host.transition(
            supervisor,
            AgentState.WAITING_APPROVAL,
            reason="wait_approval",
            run_id=supervisor.current_run.run_id,
        )

        await _seed_pending_review(project.id)
        await notify_supervisor(core, project.id, reason="second submission while waiting")

        assert supervisor.state.value == "waiting_approval"
        inbox = core.mailbox.inbox(supervisor.id)
        assert inbox is not None and inbox.qsize() == 1
        runs = [
            e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
        ]
        assert len(runs) == 1
    finally:
        llm.release.set()
        await _teardown(core, supervisor)


class _RoutingLLM:
    """按角色分派的 fake LLM：coordinator 走脚本、子 agent 立即收尾、
    supervisor 挂门闩（释放后 stop）。带 **_kwargs 对齐真实 provider。"""

    def __init__(self, research_responses: list[LLMResponse]) -> None:
        self.research_responses = list(research_responses)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.supervisor_calls = 0
        self.seen_child_completion = False

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id == SUPERVISOR_ROLE_ID:
            self.supervisor_calls += 1
            self.entered.set()
            await self.release.wait()
            return LLMResponse(content="mailbox drained; stop", stop_requested=True)
        if agent.role_id != "coordinator":
            return LLMResponse(content="child task done", stop_requested=True)
        if any(
            isinstance(m.get("content"), str) and "[Sub-agent finished]" in m["content"]
            for m in messages
        ):
            self.seen_child_completion = True
        assert self.research_responses, "no scripted research response left"
        return self.research_responses.pop(0)


async def _seed_complete_delivery(project_id: str, *, supported_step_contract: bool = False) -> None:
    """覆盖通过的交付图种子：r/p 节点（structure_supported）+ step1 边。

    Task 4A 统一结束门禁后，guided Coordinator 的 run 收尾（显式 stop 与纯
    文本最终回复同边界）要过交付覆盖审计：覆盖不通过会进入 wait_review /
    continue_work 而不是 succeeded。本文件这些用例的焦点是督导/反馈机制
    本身，用覆盖通过的交付图让门禁透明放行。``supported_step_contract=True``
    时 step1 携带 ts_opt/frequency 阶段契约且均已 supported（显式送审的
    绑定目标要求阶段在契约中存在）。"""

    def _write() -> None:
        from cloudra.dag.engine import DagEngine
        from cloudra.dag.models import (
            AddEdge,
            AddNode,
            ElementaryStepEdge,
            GraphActor,
            MutationBatch,
            OccurrenceNode,
            StageState,
            StageStatus,
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
        edge_kwargs: dict = {"evidence_level": "endpoint_supported"}
        if supported_step_contract:
            edge_kwargs = {
                "stages": [
                    StageState(kind="ts_opt", status=StageStatus.SUPPORTED),
                    StageState(kind="frequency", status=StageStatus.SUPPORTED),
                ]
            }
        result = engine.apply_batch(
            MutationBatch(
                session_id="s1",
                actor=GraphActor.HARNESS,
                actor_id="test-harness",
                base_revisions=store.load_bundle().revisions,
                rationale="seed step1 (coverage-complete)",
                operations=[
                    AddEdge(
                        op="add_edge",
                        graph="delivery",
                        edge=ElementaryStepEdge(
                            edge_id="step1",
                            source_node_id="r",
                            target_node_id="p",
                            label="step 1",
                            **edge_kwargs,
                        ),
                    )
                ],
            )
        )
        assert result.accepted

    await asyncio.to_thread(_write)


@pytest.mark.asyncio
async def test_explicit_submission_latches_supervisor_then_24_parses_and_peer_message():
    """端到端（24 解析场景）：显式送审一条证据 → Supervisor 进入门闩挂起；
    另外 24 次研究解析全部完成返回、不新增 review、不重启督导；最后主
    agent 的下一轮收到已投递的子 agent 完成消息（mailbox 投递语义——不
    承诺长 JS 程序中途抢占）。
    """
    tools_of_interest = ("log_parser", "reaction_mapping", "thermo_analysis", "ts_guess")
    responses = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="tc0", name="log_parser", arguments={"log_path": "seed.log"})],
        ),
        LLMResponse(content="seed parsed", stop_requested=True),
    ]
    responses += [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id=f"tcp{i}",
                    name=tools_of_interest[i % len(tools_of_interest)],
                    arguments={"log_path": f"log{i}.out"},
                )
            ],
        )
        for i in range(24)
    ]
    responses.append(LLMResponse(content="24 parsed", stop_requested=True))
    # run3：子 agent 完成消息投递后的下一轮。
    responses.append(LLMResponse(content="noted the child report", stop_requested=True))
    llm = _RoutingLLM(responses)

    core = RuntimeCore(strict_events=True)
    from cloudra.runtime_v2.adapters import LegacyToolExecutor

    executor = _ParseTools(bind_executor=LegacyToolExecutor(core))
    stages = default_stages(core)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=executor,
        notices=core.notices,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={
                    "name": "e2e-24",
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    research = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    research.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    from cloudra.runtime_v2.schemas import OrchestrationMode

    research.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    # 最终交付已审查；显式送审阶段契约仍保留，普通解析不另起审查。
    await _seed_complete_delivery(project.id, supported_step_contract=True)
    await _approve_final_delivery(project.id, research.id)

    supervisor = None
    child = None
    try:
        # run1：一次 log_parser（登记证据），随后显式送审这条证据。
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": research.id},
                payload={"content": "parse the seed log"},
            )
        )
        await _wait_state(research, "succeeded")
        # 显式送审走真实工具入口：dag_bind_evidence → InvocationService →
        # LegacyToolExecutor → submit_evidence_for_review 持久化 →
        # DagPolicyStage.after_tool 完成钩子按回执通知 Supervisor。
        # 不补调 _notify_supervisor——通知只能来自运行时完成钩子。
        from cloudra.runtime_v2.policies.base import PipelineContext

        ctx = PipelineContext(
            agent=research,
            run_id="submission",
            settings_snapshot=research.settings.model_copy(deep=True),
            capabilities=research.capabilities,
            inbox_messages=[],
            emit=lambda *args: None,
            workspace_dir=project.workspace_dir,
            notices=core.notices,
        )
        outcome = await pipeline.invocations.invoke(
            ctx,
            ToolCall(
                id="submit-seed",
                name="dag_bind_evidence",
                arguments={
                    "attachments": [
                        {
                            "tool_call_id": "tc0",
                            "bind_target": "step1",
                            "stage_kind": "ts_opt",
                            "claim": "seed parse supports the ts_opt stage",
                        }
                    ]
                },
            ),
        )
        assert outcome.result is not None and outcome.result.is_success
        submitted = (outcome.result.data or {}).get("result") or {}
        assert submitted["attachments"][0]["enqueued"] is True

        # 送审通知 spawn 项目唯一 Supervisor 并挂起其首轮 LLM（门闩）。
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await asyncio.wait_for(llm.entered.wait(), timeout=5)

        # run2：督导挂起期间，另外 24 次研究解析全部完成返回。
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": research.id},
                payload={"content": "parse the other 24 logs"},
            )
        )
        await _wait_state(research, "succeeded")
        assert executor.finished == ["log_parser"] + [
            tools_of_interest[i % len(tools_of_interest)] for i in range(24)
        ]

        def _counts() -> tuple[int, int]:
            db = ConversationDB(project.id)
            store = DagStore(db)
            reviews = store.list_call_reviews(None)
            with db.connect() as con:
                evidence_rows = con.execute(
                    "SELECT COUNT(*) FROM dag_evidence"
                ).fetchone()[0]
            return len(reviews), evidence_rows

        n_reviews, n_evidence = await asyncio.to_thread(_counts)
        assert n_reviews == 1  # 只有显式送审那一条；24 次解析不新增 review
        assert n_evidence == 25
        runs = [
            e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
        ]
        assert len(runs) == 1  # 运行中的督导不被重启、不新建 runner

        # 子 agent 完成 → 完成消息投递到主 agent 信箱并唤醒其下一轮。
        child = (
            await bus.execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={
                        "role_id": "researcher",
                        "parent_session_id": research.id,
                        "query": "do a small side task",
                    },
                )
            )
        ).data
        await _wait_state(child, "succeeded")
        # Child state commits before its completion message wakes the parent.
        # Do not mistake the parent's previous succeeded state for run 3.
        await _wait_run_count(core, research, 3)
        await _wait_state(research, "succeeded")  # run3 结束
        assert llm.seen_child_completion, (
            "the parent's next turn must see the delivered child-completion message"
        )
    finally:
        llm.release.set()
        await _teardown(core, research, supervisor, child)


class _ExitReviewLLM:
    """退出审批全环的 fake LLM。

    coordinator：提交冻结的 partial 答复；接受裁决后程序直接复用旧门禁结题。
    supervisor：读出 queued 退出请求，dag_review_evidence 接受后 stop。
    """

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.coordinator_calls = 0
        self.supervisor_calls = 0

    def _queued_exit_request_id(self) -> str:
        store = DagStore(ConversationDB(self.project_id))
        queued = store.list_review_requests("queued")
        assert len(queued) == 1, f"expected one queued request, got {len(queued)}"
        return queued[0].request_id

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id == SUPERVISOR_ROLE_ID:
            self.supervisor_calls += 1
            if self.supervisor_calls > 1:
                return LLMResponse(
                    content="exit request accepted; mailbox drained", stop_requested=True
                )
            request_id = await asyncio.to_thread(self._queued_exit_request_id)
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="sv-review",
                        name="dag_review_evidence",
                        arguments={
                            "request_id": request_id,
                            "verdict": "accept",
                            "reason": "scoped partial is acceptable under the declared method limits",
                        },
                    )
                ],
            )
        self.coordinator_calls += 1
        if self.coordinator_calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="stop-1",
                        name="stop",
                        arguments={"delivery_disposition": "partial", "reason": "partial",
                                   "final_answer": "frozen-roundtrip-answer"},
                    )
                ],
            )
        return LLMResponse(
            content="unreviewed-roundtrip-confirmation", stop_requested=True,
        )


@pytest.mark.asyncio
async def test_exit_review_roundtrip_drives_coordinator_to_approved_partial(tmp_path):
    """退出审批全环（迁移自 review_worker 的 real-runner 用例）：

    coordinator stop partial → 持久化退出请求 + 通知 Supervisor（不再轮询
    daemon）→ 真实 Supervisor agent 经 dag_review_evidence 裁决接受 →
    裁决通知非轮询投递（pin + mailbox + wake）→ runner 复查同一版本，
    无第二轮模型或 stop 工具就将冻结答复交付为 allow_final。
    """
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.invocation import InvocationService

    core = RuntimeCore(strict_events=True)
    stages = default_stages(core)
    executor = LegacyToolExecutor(core)
    invocations = InvocationService(
        event_writer=core.event_writer, stages=stages, tools=executor, agents=core.agents
    )
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={
                    "name": "exit-roundtrip",
                    "workspace_dir": str(tmp_path),
                    "settings": {
                        "orchestration_mode": "dag_guided",
                        # scripted LLM 直接发业务工具调用，走传统协议（默认
                        # javascript 只放 js_exec + 直接控制类）。
                        "defaults": {"invocation_protocol": "traditional"},
                    },
                },
            )
        )
    ).data
    llm = _ExitReviewLLM(project.id)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=executor,
        notices=core.notices,
        invocations=invocations,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    # 事件驱动同步点（CI flake 根治，run 34014279374）：旧实现"5 秒轮询持久
    # 化请求 + 轮询退出后一次性 find_project_supervisor"有真实竞态——退出请
    # 求经 to_thread 提交对轮询连接可见时，audit_stop 里的 _notify_supervisor
    # 尚未跑完 spawn，core.agents 投影里还没有 supervisor，慢环境（CI +
    # coverage）下必踩。agent.completion_gate 事件在 audit_stop 返回后才追加：
    # wait_review 动作同时保证①退出请求已持久化（_enqueue_exit_review 先提交）
    # ②Supervisor 已按状态表创建（_notify_supervisor await 完 spawn 才返回）。
    # 订阅必须先于 spawn（spawn 带 query 立即开跑）；项目内只有 coordinator 的
    # partial stop 能产生 wait_review 判定，按项目+动作匹配即可。
    gate_seen = asyncio.Event()

    async def _on_gate(envelope) -> None:
        if (
            envelope.type == "agent.completion_gate"
            and envelope.project_id == project.id
            and envelope.data.get("action") == "wait_review"
            and envelope.data.get("request_id")
        ):
            gate_seen.set()

    core.event_hub.subscribe(_on_gate)
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "coordinator",
                    "query": "deliver partial",
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    supervisor = None
    try:
        # 第一拍 stop → wait_review：退出请求持久化 + 通知 Supervisor。
        # 超时只是失败上限（事件驱动，正常毫秒级返回）。
        # 挂起语义本身由 test_runtime_v2_completion_gate.py 的 wait_review
        # 用例（不配裁决的 supervisor）稳定锁定。
        await asyncio.wait_for(gate_seen.wait(), timeout=30)

        def _request_ids():
            # 任意状态：快速 fake 督导可能在 gate 事件前就已裁决（queued→resolved）。
            store = DagStore(ConversationDB(project.id).init())
            return [row.request_id for row in store.list_review_requests(None)]

        assert await asyncio.to_thread(_request_ids), (
            "wait_review gate fired without a persisted exit review request"
        )
        from cloudra.runtime_v2.supervision import find_final_review_supervisor

        request_ids = await asyncio.to_thread(_request_ids)
        supervisor = find_final_review_supervisor(core, project.id, request_ids[0])
        assert supervisor is not None

        # Supervisor 裁决 → 通知投递 → coordinator 恢复 → 批准结束。
        await _wait_state(coordinator, "succeeded")
        assert llm.coordinator_calls == 1
        emitted = [event.data.get("content") for event in core.event_log.query_session(
            coordinator.id, types={"agent.message_emitted"})]
        assert "frozen-roundtrip-answer" in emitted
        assert "unreviewed-roundtrip-confirmation" not in emitted

        def _read_back():
            db = ConversationDB(project.id)
            store = DagStore(db)
            requests = store.list_review_requests(None)
            notifications = store.pending_review_notifications()
            with db.connect() as con:
                dispositions = con.execute(
                    "SELECT disposition FROM dag_delivery_dispositions"
                ).fetchall()
            return requests, notifications, dispositions

        requests, notifications, dispositions = await asyncio.to_thread(_read_back)
        assert [r.state for r in requests] == ["resolved"]
        assert requests[0].kind == "exit"
        assert notifications == []  # 通知已投递并闭环标记
        assert dispositions
        assert set(dispositions) == {("partial",)}
        # 裁决通知确实进了 coordinator 的上下文通道（pin）。
        pinned = core.notices.collect_batch(coordinator.id, fresh=True)
        assert any("verdict=accept" in m["content"] for m in pinned)
    finally:
        core.event_hub.unsubscribe(_on_gate)
        await _teardown(core, coordinator, supervisor)


@pytest.mark.asyncio
async def test_flush_review_notifications_delivers_persists_and_marks_sent(tmp_path):
    """裁决通知投递（迁移自 review_worker 的恢复用例）：裁决落库、投递前
    崩溃的窗口由 flush 补投——事件先持久化再标记 sent；收件人已 cancelled
    时不复活、通知行照样闭环。
    """
    from cloudra.dag.review_requests import ReviewDecision, ReviewRequest
    from cloudra.runtime_v2.persistence import RuntimeStore

    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={"name": "notify-recovery", "workspace_dir": str(tmp_path)},
            )
        )
    ).data
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data

    def _enqueue_and_resolve(request_id: str, recipient: str, verdict: str) -> str:
        store = DagStore(ConversationDB(project.id).init())
        store.enqueue_review(
            ReviewRequest(
                request_id=request_id,
                kind="evidence",
                requester=recipient,
                target_ids=["step1"],
                question=f"question for {request_id}",
                basis_fingerprint=f"basis-{request_id}",
            )
        )
        decision = ReviewDecision(
            request_id=request_id,
            basis_fingerprint=f"basis-{request_id}",
            verdict=verdict,
            reason="Missing evidence" if verdict == "reject" else "sufficient",
            next_action="Inspect existing log" if verdict == "reject" else None,
        )
        out = store.resolve_review(decision, expected_basis=f"basis-{request_id}")
        assert out["accepted"]
        return out["decision_id"]

    await asyncio.to_thread(
        _enqueue_and_resolve, "req-live", coordinator.id, "reject"
    )

    import json as _json

    handled = await flush_review_notifications(core, project.id)
    assert handled == 1

    def _pending():
        return DagStore(ConversationDB(project.id)).pending_review_notifications()

    assert await asyncio.to_thread(_pending) == []
    # 唤醒握手落盘（事件持久化先于标记 sent）。
    persisted = core.store.query_project_events(project.id)
    assert any(
        row["type"] == "agent.message_injected"
        and "verdict=reject" in _json.loads(row["data"])["content"]
        and "next_action=Inspect existing log" in _json.loads(row["data"])["content"]
        for row in persisted
    )
    inbox = core.mailbox.inbox(coordinator.id)
    assert inbox is not None and inbox.qsize() == 1
    # coordinator 是 queued（spawn 无 query）：wake 开新 run（无 runner 时只落事件）。
    assert coordinator.state.value == "running"

    # 收件人已 cancelled：不复活，但迟到裁决照常驻留信箱（parked），通知行闭环。
    await bus.execute(
        Command(type="agent.cancel", target={"session_id": coordinator.id}, payload={})
    )
    await asyncio.to_thread(
        _enqueue_and_resolve, "req-cancelled", coordinator.id, "accept"
    )
    handled = await flush_review_notifications(core, project.id)
    assert handled == 1
    assert await asyncio.to_thread(_pending) == []
    assert coordinator.state.value == "cancelled"
    assert inbox.qsize() == 2  # parked：迟到裁决投递驻留，不唤醒


@pytest.mark.asyncio
async def test_flush_store_factory_ensures_schema_on_legacy_db(tmp_path):
    """flush 的 store 工厂把旧库补到最新 schema（迁移自 review_worker 守卫）。

    回归：早于 dag_review_* 表族建库的会话库缺
    dag_review_notifications/schema_migrations，读路径每趟抛 "no such
    table"。建/升级统一走 ConversationDB.ensure_schema()（幂等）。
    """
    from cloudra.persistence.database import ConversationDB

    project_id = "prj_legacy_schema_test"

    def _make_legacy() -> ConversationDB:
        db = ConversationDB(project_id).init()
        with db.connect() as con:
            con.execute("DROP TABLE dag_review_notifications")
            con.execute("DROP TABLE dag_review_requests")
            con.execute("DROP TABLE dag_review_decisions")
            con.execute("DROP TABLE schema_migrations")
        return db

    db = _make_legacy()

    def tables() -> set[str]:
        with db.connect() as con:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        return {row[0] for row in rows}

    assert "dag_review_notifications" not in tables()

    handled = await flush_review_notifications(RuntimeCore(strict_events=True), project_id)
    assert handled == 0
    assert "dag_review_notifications" in tables()
    assert "schema_migrations" in tables()


@pytest.mark.asyncio
async def test_flush_does_not_mark_sent_when_recipient_is_empty(tmp_path):
    """收件人解析为空时不得 mark sent——否则裁决通知静默丢失。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={"name": "empty-recipient", "workspace_dir": str(tmp_path)},
            )
        )
    ).data

    def _seed_empty_recipient() -> None:
        db = ConversationDB(project.id).init()
        with db.connect() as con:
            DagStore._insert_notification(
                con,
                kind="call_verdict",
                subject_id="review_empty",
                recipient_session_id="",
                payload={"verdict": "agree", "reason": "ok"},
            )
            con.commit()

    await asyncio.to_thread(_seed_empty_recipient)
    handled = await flush_review_notifications(core, project.id)
    assert handled == 0

    def _pending():
        return DagStore(ConversationDB(project.id)).pending_review_notifications()

    pending = await asyncio.to_thread(_pending)
    assert pending
    assert pending[0]["recipient_session_id"] == ""


# --------------------------------------------------------------------- Task 4
# 反馈矩阵、结束竞态（lost wakeup）与模式切换。
#
# 反馈唯一投递口契约：裁决通知 = flush_review_notifications 的 pin（按
# decision_id key 去重）+ mailbox + 条件 wake。Supervisor 不额外投递
# 普通子 agent 完成回报；其科学待办失败由既有 D2 告警通道报告。


async def _seed_review_request(project_id: str, requester: str, *, question: str) -> str:
    """结构化督导请求（ReviewRequest）的持久化等价物。

    basis_fingerprint 必须与 store.review_basis 对齐——dag_review_evidence
    裁决时以当前 basis 复核，随手填的 basis 会被 stale_basis 拒掉。
    """
    from cloudra.dag.review_requests import ReviewRequest

    def _write() -> str:
        store = DagStore(ConversationDB(project_id).init())
        store.ensure_bundle("s1")
        draft = ReviewRequest(
            kind="evidence",
            requester=requester,
            question=question,
            basis_fingerprint="placeholder",
        )
        basis = store.review_basis(draft)
        return store.enqueue_review(draft.model_copy(update={"basis_fingerprint": basis}))

    return await asyncio.to_thread(_write)


def _queued_request_ids(project_id: str) -> list[str]:
    store = DagStore(ConversationDB(project_id))
    return [row.request_id for row in store.list_review_requests("queued")]


def _decision_for(project_id: str, request_id: str):
    store = DagStore(ConversationDB(project_id))
    return store.get_review_decision_for_request(request_id)


class _MailboxAdjudicatorLLM:
    """裁决型 fake LLM：supervisor 每轮自读持久信箱（to_thread 读 DAG store），
    有 queued 请求就经 dag_review_evidence 裁决一个，信箱空则 stop。

    - ``latch=True``：首轮 supervisor 调用挂门闩（entered/release），用于在
      督导 LLM 挂起期间注入新送审/取消/模式切换，精确构造竞态窗口。
    - ``adjudicate_once=True``：最多发起一次裁决调用（裁决被模式门禁拒绝后
      下一轮直接 stop，避免无限重试）。
    其它角色（coordinator 等）：``coord_latch=True`` 时首轮挂门闩；随后按
    ``coordinator_responses`` 脚本或默认 stop。每次调用的消息快照记入
    ``seen[agent.id]`` 供上下文断言。带 **_kwargs 对齐真实 provider。
    """

    def __init__(
        self,
        project_id: str,
        *,
        latch: bool = False,
        adjudicate_once: bool = False,
        coord_latch: bool = False,
        coordinator_responses: list[LLMResponse] | None = None,
    ) -> None:
        self.project_id = project_id
        self.coordinator_responses = list(coordinator_responses or [])
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.coord_entered = asyncio.Event()
        self.coord_release = asyncio.Event()
        self._latch = latch
        self._latched = False
        self._adjudicate_once = adjudicate_once
        self._adjudicated = 0
        self._coord_latch = coord_latch
        self._coord_latched = False
        self.supervisor_calls = 0
        self.seen: dict[str, list[list[dict]]] = {}

    def _next_queued(self):
        db = ConversationDB(self.project_id)
        if not os.path.isfile(db.path):
            return None  # 信箱尚未建库 = 空信箱
        store = DagStore(db)
        queued = store.list_review_requests("queued")
        return queued[0] if queued else None

    async def complete(self, agent, messages, tools, **_kwargs):
        self.seen.setdefault(agent.id, []).append(
            [m for m in messages if isinstance(m, dict)]
        )
        if agent.role_id == SUPERVISOR_ROLE_ID:
            self.supervisor_calls += 1
            if self._latch and not self._latched:
                self._latched = True
                self.entered.set()
                await self.release.wait()
            request = await asyncio.to_thread(self._next_queued)
            if request is None or (self._adjudicate_once and self._adjudicated):
                return LLMResponse(content="mailbox drained; stop", stop_requested=True)
            self._adjudicated += 1
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id=f"sv-adj-{self._adjudicated}",
                        name="dag_review_evidence",
                        arguments={
                            "request_id": request.request_id,
                            "verdict": "accept",
                            "reason": "submitted evidence snapshot supports the claim",
                        },
                    )
                ],
            )
        if self._coord_latch and not self._coord_latched:
            self._coord_latched = True
            self.coord_entered.set()
            await self.coord_release.wait()
        if self.coordinator_responses:
            return self.coordinator_responses.pop(0)
        return LLMResponse(content="noted", stop_requested=True)


def _full_wiring(llm, *, extra_stages=()):
    """反馈/竞态用例的全栈装配：真实 InvocationService + LegacyToolExecutor
    （supervisor 的 dag_review_evidence 走 SupervisorToolExecutor 路径）。
    llm 先装配、project_id 在项目创建后回填（裁决读取发生得更晚）。"""
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.invocation import InvocationService

    core = RuntimeCore(strict_events=True)
    stages = [*default_stages(core), *extra_stages]
    executor = LegacyToolExecutor(core)
    invocations = InvocationService(
        event_writer=core.event_writer, stages=stages, tools=executor, agents=core.agents
    )
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=executor,
        notices=core.notices,
        invocations=invocations,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    bus = CommandBus(core)
    return core, bus, stages


async def _guided_project(bus, tmp_path, name: str):
    return (
        await bus.execute(
            Command(
                type="project.create",
                payload={
                    "name": name,
                    "workspace_dir": str(tmp_path),
                    "settings": {
                        "orchestration_mode": "dag_guided",
                        "defaults": {"invocation_protocol": "traditional"},
                    },
                },
            )
        )
    ).data


async def _spawn_guided_coordinator(bus, project, *, query: str | None = None):
    payload = {
        "role_id": "coordinator",
        "settings": {"orchestration_mode": "dag_guided"},
    }
    if query:
        payload["query"] = query
    return (
        await bus.execute(
            Command(type="agent.spawn", target={"project_id": project.id}, payload=payload)
        )
    ).data


def _injections(core, session_id: str, needle: str):
    return [
        e
        for e in core.event_log.query_session(session_id, types={"agent.message_injected"})
        if needle in str(e.data.get("content", ""))
    ]


def _pin_events(core, session_id: str, key: str):
    return [
        e
        for e in core.event_log
        if e.type == "context.pin_set"
        and e.session_id == session_id
        and e.data.get("key") == key
    ]


def _supervisor_tool_calls(core, supervisor_id: str, tool_name: str):
    return [
        e
        for e in core.event_log.query_session(supervisor_id, types={"tool.requested"})
        if e.data.get("tool_name") == tool_name
    ]


@pytest.mark.asyncio
async def test_feedback_delivered_once_to_running_coordinator_without_restart(tmp_path):
    """反馈矩阵·running：裁决落在正在运行的 Coordinator 身上——不重启
    （run 不换），裁决通知唯一投递并进入下一轮上下文，不附加普通完成回报。"""
    llm = _MailboxAdjudicatorLLM("", coord_latch=True)
    core, bus, _stages = _full_wiring(llm)
    project = await _guided_project(bus, tmp_path, "feedback-running")
    llm.project_id = project.id
    # Task 4A：覆盖通过的交付图让统一结束门禁透明（本用例测反馈投递，
    # 不测退出门禁；否则 coordinator 的纯文本收尾会进入 wait_review）。
    await _seed_complete_delivery(project.id)
    coordinator = await _spawn_guided_coordinator(bus, project, query="coordinate")
    supervisor = None
    try:
        await asyncio.wait_for(llm.coord_entered.wait(), timeout=5)
        assert coordinator.state.value == "running"
        runs_before = await _wait_run_count(core, coordinator, 1)

        # Coordinator 运行中：送审 → Supervisor 裁决 → 反馈投递。
        request_id = await _seed_review_request(
            project.id, coordinator.id, question="does the log support ts_opt?"
        )
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        assert supervisor.parent_session_id == coordinator.id
        await _wait_state(supervisor, "succeeded")

        # 运行中不重启：仍停在第一个 run。
        assert coordinator.state.value == "running"
        runs = [e for e in core.event_log.query_session(coordinator.id) if e.type == "run.started"]
        assert len(runs) == 1 and runs[0].run_id == runs_before[0].run_id

        llm.coord_release.set()
        await _wait_state(coordinator, "succeeded")

        decision = await asyncio.to_thread(_decision_for, project.id, request_id)
        assert decision is not None and decision.verdict == "accept"
        # 唯一反馈：裁决通知消息与裁决 pin，不重复发普通完成回报。
        assert len(_injections(core, coordinator.id, decision.decision_id)) == 1
        assert len(_pin_events(core, coordinator.id, f"review-{decision.decision_id}")) == 1
        reports = [
            e
            for e in _injections(core, coordinator.id, "[Sub-agent finished]")
            if supervisor.id in str(e.data.get("content", ""))
        ]
        assert reports == []
        # 最新裁决进入下一轮上下文（第二轮 call 的消息快照）。
        followup = llm.seen[coordinator.id][1]
        flat = "\n".join(str(m.get("content", "")) for m in followup)
        assert decision.decision_id in flat and "verdict=accept" in flat
        assert "[Sub-agent finished]" not in flat
    finally:
        llm.release.set()
        llm.coord_release.set()
        await _teardown(core, coordinator, supervisor)


@pytest.mark.asyncio
async def test_feedback_wakes_succeeded_coordinator_into_new_run(tmp_path):
    """反馈矩阵·succeeded：休眠的 Coordinator 被裁决通知正常 wake 开新
    run，裁决内容进入新 run 的上下文；不额外投递普通完成回报。"""
    llm = _MailboxAdjudicatorLLM("")
    core, bus, _stages = _full_wiring(llm)
    project = await _guided_project(bus, tmp_path, "feedback-succeeded")
    llm.project_id = project.id
    # Task 4A：同 feedback-running——覆盖通过的交付图让结束门禁透明。
    await _seed_complete_delivery(project.id)
    coordinator = await _spawn_guided_coordinator(bus, project, query="coordinate")
    supervisor = None
    try:
        await _wait_state(coordinator, "succeeded")
        request_id = await _seed_review_request(
            project.id, coordinator.id, question="frequency evidence sufficient?"
        )
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await _wait_state(supervisor, "succeeded")
        await _wait_state(coordinator, "succeeded")  # 被唤醒的 run 2 收尾

        decision = await asyncio.to_thread(_decision_for, project.id, request_id)
        assert decision is not None
        # 正常休眠可唤醒：run 身份换新。
        runs = await _wait_run_count(core, coordinator, 2)
        assert runs[1].run_id != runs[0].run_id
        assert len(_injections(core, coordinator.id, decision.decision_id)) == 1
        assert len(_pin_events(core, coordinator.id, f"review-{decision.decision_id}")) == 1
        reports = [
            e
            for e in _injections(core, coordinator.id, "[Sub-agent finished]")
            if supervisor.id in str(e.data.get("content", ""))
        ]
        assert reports == []
        # run 2 起的某一轮上下文只带裁决反馈。
        later = llm.seen[coordinator.id][1:]
        flat = "\n".join(
            str(m.get("content", "")) for call in later for m in call
        )
        assert decision.decision_id in flat
        assert "[Sub-agent finished]" not in flat
    finally:
        llm.release.set()
        await _teardown(core, coordinator, supervisor)


@pytest.mark.asyncio
async def test_feedback_marks_sent_without_resurrecting_cancelled_coordinator(tmp_path):
    """反馈矩阵·cancelled：裁决通知驻留信箱、不复活 Coordinator；没有普通
    完成回报，通知行闭环标记 sent，全程零新 run。"""
    llm = _MailboxAdjudicatorLLM("")
    core, bus, _stages = _full_wiring(llm)
    project = await _guided_project(bus, tmp_path, "feedback-cancelled")
    llm.project_id = project.id
    coordinator = await _spawn_guided_coordinator(bus, project)  # queued
    supervisor = None
    try:
        await bus.execute(
            Command(type="agent.cancel", target={"session_id": coordinator.id}, payload={})
        )
        assert coordinator.state.value == "cancelled"

        request_id = await _seed_review_request(
            project.id, coordinator.id, question="belated review for a cancelled coordinator"
        )
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await _wait_state(supervisor, "succeeded")

        decision = await asyncio.to_thread(_decision_for, project.id, request_id)
        assert decision is not None  # 裁决本身落库
        assert coordinator.state.value == "cancelled"
        # parked：裁决消息与 pin 驻留，但不唤醒、不附加普通完成回报。
        assert len(_injections(core, coordinator.id, decision.decision_id)) == 1
        assert len(_pin_events(core, coordinator.id, f"review-{decision.decision_id}")) == 1
        assert _injections(core, coordinator.id, "[Sub-agent finished]") == []
        runs = [
            e for e in core.event_log.query_session(coordinator.id) if e.type == "run.started"
        ]
        assert runs == []
        # 通知行照样闭环（不滞留 pending 等重投）。
        def _pending():
            return DagStore(ConversationDB(project.id)).pending_review_notifications()

        assert await asyncio.to_thread(_pending) == []
    finally:
        llm.release.set()
        await _teardown(core, coordinator, supervisor)


@pytest.mark.asyncio
async def test_supervisor_parent_is_coordinator_not_submitting_researcher(tmp_path):
    """Supervisor 的 parent 保持 Coordinator 身份；裁决反馈按 requester
    投递给提交者，不因父子关系重复发普通完成回报。"""
    llm = _MailboxAdjudicatorLLM("")
    core, bus, _stages = _full_wiring(llm)
    project = await _guided_project(bus, tmp_path, "parent-identity")
    llm.project_id = project.id
    # Task 4A：覆盖通过的交付图让统一结束门禁对 coordinator 的收尾透明
    # （本用例测 parent 身份与投递路由，不测退出门禁）。
    await _seed_complete_delivery(project.id)
    coordinator = await _spawn_guided_coordinator(bus, project)
    researcher = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "researcher",
                    "parent_session_id": coordinator.id,
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    supervisor = None
    try:
        # 送审来自研究子 agent；supervisor 在此之后才首次被通知创建。
        request_id = await _seed_review_request(
            project.id, researcher.id, question="researcher's evidence"
        )
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        assert supervisor.parent_session_id == coordinator.id
        assert supervisor.parent_session_id != researcher.id

        await _wait_state(supervisor, "succeeded")
        await _wait_state(researcher, "succeeded")  # 裁决通知 wake 开的 run
        decision = await asyncio.to_thread(_decision_for, project.id, request_id)
        assert decision is not None
        # 裁决通知按 requester 投递给提交者；Supervisor 无普通完成回报。
        assert len(_injections(core, researcher.id, decision.decision_id)) == 1
        assert _injections(core, coordinator.id, decision.decision_id) == []
        reports = [
            e
            for e in _injections(core, coordinator.id, "[Sub-agent finished]")
            if supervisor.id in str(e.data.get("content", ""))
        ]
        assert reports == []
    finally:
        llm.release.set()
        await _teardown(core, coordinator, supervisor, researcher)


@pytest.mark.asyncio
async def test_new_review_arriving_mid_turn_is_consumed_in_same_run(tmp_path):
    """结束竞态（窗口 a：轮次中途到达）。

    督导 LLM 首轮挂门闩期间新送审到达：notify 的 deliver 撞 RUNNING（wake
    no-op）。现有握手（stop 前 inbox 复查，agent_runner 的不变量"stop 收尾
    前收件箱非空必须续跑一轮"）必须让同一 run 的后续轮次消费掉它——
    不丢唤醒、不开第二个 run、不出现第二个 supervisor runner。
    """
    llm = _MailboxAdjudicatorLLM("", latch=True)
    core, bus, _stages = _full_wiring(llm)
    project = await _guided_project(bus, tmp_path, "race-mid-turn")
    llm.project_id = project.id
    # Task 4A：覆盖通过的交付图让结束门禁透明——否则 supervisor 完成回传唤醒
    # coordinator 后其纯文本收尾会创建退出审批并再次通知 supervisor（多一个
    # run），干扰"同一 run 消费中途待办"的断言。
    await _seed_complete_delivery(project.id)
    coordinator = await _spawn_guided_coordinator(bus, project)
    supervisor = None
    try:
        request_1 = await _seed_review_request(
            project.id, coordinator.id, question="first submission"
        )
        await notify_supervisor(core, project.id, reason="first submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await asyncio.wait_for(llm.entered.wait(), timeout=5)

        # 督导 LLM 挂起期间：新 review 落库 + 通知（deliver 撞 RUNNING）。
        request_2 = await _seed_review_request(
            project.id, coordinator.id, question="second submission during adjudication"
        )
        await notify_supervisor(core, project.id, reason="second submission mid-turn")

        llm.release.set()
        await _wait_state(supervisor, "succeeded")

        # 两条都已裁决（第二轮读持久信箱消费了中途到达的待办）。
        assert await asyncio.to_thread(_queued_request_ids, project.id) == []
        for rid in (request_1, request_2):
            decision = await asyncio.to_thread(_decision_for, project.id, rid)
            assert decision is not None, f"{rid} was lost"
        # 最多一个 runner：同一个 run 内消费，不开新 run。
        runs = [
            e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
        ]
        assert len(runs) == 1
        supervisors = [
            a
            for a in core.agents.values()
            if a.project_id == project.id and a.role_id == SUPERVISOR_ROLE_ID
        ]
        assert len(supervisors) == 1
    finally:
        llm.release.set()
        await _teardown(core, coordinator, supervisor)


class _StopWindowTrap:
    """PolicyStage 钩子：在 supervisor 的结束审计（LLM stop 决策之后、
    最终收件锁之前）注入一条新送审——确定性命中"信箱判空与正常结束之间"
    的竞态窗口（计划 §4）。before/after 钩子全是 no-op。"""

    name = "stop_window_trap"

    def __init__(self, core, project_id: str, requester: str) -> None:
        self._core = core
        self._project_id = project_id
        self._requester = requester
        self.fired = asyncio.Event()
        self._armed = True

    async def before_tool(self, ctx, call, **_kwargs):
        from cloudra.runtime_v2.policies.base import PolicyResult

        return PolicyResult.allow()

    async def after_tool(self, ctx, call, result, **_kwargs) -> None:
        return None

    async def before_llm(self, ctx, messages, **_kwargs) -> None:
        return None

    async def audit_run_end(self, ctx, *, explicit_stop: bool, **_kwargs) -> None:
        # on_run_end runs under the recipient lock. A test trap cannot post to
        # that same recipient there; use the real pre-lock audit boundary.
        if not self._armed or ctx.agent.role_id != SUPERVISOR_ROLE_ID:
            return
        self._armed = False
        await _seed_review_request(
            self._project_id, self._requester, question="late submission at stop boundary"
        )
        await notify_supervisor(
            self._core, self._project_id, reason="late submission at stop boundary"
        )
        self.fired.set()


@pytest.mark.asyncio
async def test_new_review_arriving_between_stop_decision_and_finish_is_consumed_before_completion(tmp_path):
    """结束竞态（窗口 b：stop 裁决后、finish_run 前到达）。

    督导读到空信箱决定 stop；trap 在 on_run_end 注入新送审（deliver 撞
    RUNNING，wake no-op）。子 Agent 在 finish_run 前复查并继续当前 run，
    新送审必须先消费完才能向父 Agent 报终态，不由下一次偶然调用救活。
    """
    core = RuntimeCore(strict_events=True)
    bus_probe = CommandBus(core)
    project = (
        await bus_probe.execute(
            Command(
                type="project.create",
                payload={
                    "name": "race-stop-window",
                    "workspace_dir": str(tmp_path),
                    "settings": {
                        "orchestration_mode": "dag_guided",
                        "defaults": {"invocation_protocol": "traditional"},
                    },
                },
            )
        )
    ).data
    coordinator = (
        await bus_probe.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "coordinator",
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    # Task 4A：覆盖通过的交付图让结束门禁对 coordinator 透明——否则督导完成
    # 回传唤醒 coordinator 后其纯文本收尾会创建退出审批请求，在第二 run 收尾
    # 后残留 queued 待办，干扰"新送审被消费完"的断言。
    await _seed_complete_delivery(project.id)
    llm = _MailboxAdjudicatorLLM(project.id)
    trap = _StopWindowTrap(core, project.id, coordinator.id)
    # 重建带 trap 的管线（复用同一 core，保证事件流连续）。
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.invocation import InvocationService

    stages = [*default_stages(core), trap]
    executor = LegacyToolExecutor(core)
    invocations = InvocationService(
        event_writer=core.event_writer, stages=stages, tools=executor, agents=core.agents
    )
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=executor,
        notices=core.notices,
        invocations=invocations,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    bus = CommandBus(core)
    supervisor = None
    try:
        # 手动 spawn 督导（信箱为空），用一条消息让它开跑：读空信箱 → stop。
        supervisor = (
            await bus.execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={
                        "role_id": "supervisor",
                        "parent_session_id": coordinator.id,
                        "settings": {"orchestration_mode": "dag_guided"},
                    },
                )
            )
        ).data
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": supervisor.id},
                payload={"content": "check your supervision mailbox"},
            )
        )
        # 第一 run 读空信箱 → stop；trap 在收尾窗口注入新送审。
        await asyncio.wait_for(trap.fired.wait(), timeout=5)
        # 等当前 run 消费完新送审（轮询只作失败上限）。
        deadline = asyncio.get_running_loop().time() + 5.0
        while await asyncio.to_thread(_queued_request_ids, project.id):
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("late submission was never adjudicated (lost wakeup)")
            await asyncio.sleep(0.01)
        await _wait_state(supervisor, "succeeded")
        runs = await _wait_run_count(core, supervisor, 1)
        assert len(runs) == 1
        # 新送审在首次终态回报前处理完；不能先报完成再依赖二次唤醒。
        events = core.event_log.query_session(supervisor.id)
        finished = [event for event in events if event.type == "run.finished"]
        reviewed = [
            event for event in events
            if event.type == "tool.finished"
            and event.data.get("tool_name") == "dag_review_evidence"
            and event.data.get("is_success") is True
        ]
        assert len(finished) == len(reviewed) == 1
        assert reviewed[0].seq < finished[0].seq

        # 新送审最终被同一 run 的消费者处理，不丢唤醒。
        assert await asyncio.to_thread(_queued_request_ids, project.id) == []
        supervisors = [
            a
            for a in core.agents.values()
            if a.project_id == project.id and a.role_id == SUPERVISOR_ROLE_ID
        ]
        assert len(supervisors) == 1
    finally:
        llm.release.set()
        await _teardown(core, coordinator, supervisor)


@pytest.mark.asyncio
async def test_exiting_guided_blocks_in_flight_adjudication_and_keeps_backlog(tmp_path):
    """模式切换·退出 guided：已在飞的 supervisor 不新增裁决（其
    dag_review_evidence 被 dag_record 门禁拒绝），生产端通知口（草稿/
    督导消息）也不再 notify；持久化未决事项保留不清空。"""
    llm = _MailboxAdjudicatorLLM("", latch=True, adjudicate_once=True)
    core, bus, stages = _full_wiring(llm)
    project = await _guided_project(bus, tmp_path, "mode-exit")
    llm.project_id = project.id
    coordinator = await _spawn_guided_coordinator(bus, project)
    supervisor = None
    try:
        request_id = await _seed_review_request(
            project.id, coordinator.id, question="pending while mode flips"
        )
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await asyncio.wait_for(llm.entered.wait(), timeout=5)

        # 督导 LLM 挂起期间退出 guided（前端模式下拉：项目 + 全部 agent）。
        await bus.execute(
            Command(
                type="project.update",
                target={"project_id": project.id},
                payload={"settings": {"orchestration_mode": "dag_record"}},
            )
        )
        for agent in (coordinator, supervisor):
            await bus.execute(
                Command(
                    type="agent.settings_update",
                    target={"session_id": agent.id},
                    payload={"orchestration_mode": "dag_record"},
                )
            )

        llm.release.set()
        await _wait_state(supervisor, "succeeded")

        # 在飞裁决被模式门禁拒绝：无决定、无通知行；待办保留。
        assert await asyncio.to_thread(_decision_for, project.id, request_id) is None
        assert await asyncio.to_thread(_queued_request_ids, project.id) == [request_id]

        def _notifications():
            return DagStore(ConversationDB(project.id)).pending_review_notifications()

        assert await asyncio.to_thread(_notifications) == []
        calls = _supervisor_tool_calls(core, supervisor.id, "dag_review_evidence")
        assert len(calls) == 1  # 尝试过一次，被拒绝，未重试
        runs = [
            e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
        ]
        assert len(runs) == 1

        # 生产端通知口在 dag_record 下不再 notify（草稿/督导消息两类触发口）。
        from cloudra.dag.controller import DagController

        controller = DagController(
            ConversationDB(project.id),
            coordinator.id,
            "dag_record",
            conversation_id=project.id,
            core=core,
        )
        await controller._trigger_supervisor_after_tool(
            "dag_message_supervisor",
            {"message": "please review"},
            {"accepted": True, "result": {"request_id": "rq_extra"}},
            True,
        )
        await controller._trigger_supervisor_after_tool(
            "dag_propose_mechanism",
            {},
            {"accepted": False, "result": {"draft_id": "draft_extra"}},
            True,
        )
        inbox = core.mailbox.inbox(supervisor.id)
        assert inbox is None or inbox.empty()
        runs = [
            e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
        ]
        assert len(runs) == 1
    finally:
        llm.release.set()
        await _teardown(core, coordinator, supervisor)


async def _supervisor_in_state(bus, core, project, coordinator, target_state: str):
    """spawn 项目督导并用手动 host 原语驱动到目标状态（runner-less 确定
    性构造；notify/wake 的状态表断言只关心投影状态与信箱）。"""
    supervisor = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "supervisor",
                    "parent_session_id": coordinator.id,
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    host = core.agent_host
    if target_state == "running":
        await host.start_run(supervisor)
    elif target_state == "waiting":
        await host.start_run(supervisor)
        await host.transition(
            supervisor,
            AgentState.WAITING_APPROVAL,
            reason="wait_approval",
            run_id=supervisor.current_run.run_id,
        )
    elif target_state == "succeeded":
        await host.start_run(supervisor)
        await host.finish_run(supervisor, outcome="succeeded")
    elif target_state == "failed":
        await host.start_run(supervisor)
        await host.finish_run(
            supervisor,
            outcome="failed",
            error="boom",
            failure_kind=RunFailureKind.PIPELINE_INTERNAL,
        )
    elif target_state == "cancelled":
        await bus.execute(
            Command(type="agent.cancel", target={"session_id": supervisor.id}, payload={})
        )
    assert supervisor.state.value == {"waiting": "waiting_approval"}.get(
        target_state, target_state
    )
    return supervisor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_state", ["queued", "running", "waiting", "succeeded", "failed", "cancelled"]
)
async def test_returning_to_guided_notifies_only_runnable_supervisors(target_state):
    """模式切换·返回 guided：project.update 把编排模式切回 dag_guided 时按
    状态表补一次通知——所有状态都投递信箱变更消息（failed/cancelled 驻留
    parked 不唤醒）；仅 queued/succeeded 另 wake 开新 run。退出 guided 与
    guided→guided 重发都不触发。持久化未决事项全程不清空。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={
                    "name": f"mode-return-{target_state}",
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    supervisor = await _supervisor_in_state(bus, core, project, coordinator, target_state)
    request_id = await _seed_review_request(
        project.id, coordinator.id, question="backlog survives mode flips"
    )

    def _inbox_size() -> int:
        inbox = core.mailbox.inbox(supervisor.id)
        return inbox.qsize() if inbox is not None else 0

    def _run_count() -> int:
        return len(
            [
                e
                for e in core.event_log.query_session(supervisor.id)
                if e.type == "run.started"
            ]
        )

    inbox_before, runs_before = _inbox_size(), _run_count()

    # 退出 guided：不触发补通知。
    await bus.execute(
        Command(
            type="project.update",
            target={"project_id": project.id},
            payload={"settings": {"orchestration_mode": "standard"}},
        )
    )
    assert _inbox_size() == inbox_before
    assert _run_count() == runs_before

    # 返回 guided：按状态表补通知——所有状态都投递（failed/cancelled 驻留
    # parked），只有 queued/succeeded 另 wake 开新 run。
    await bus.execute(
        Command(
            type="project.update",
            target={"project_id": project.id},
            payload={"settings": {"orchestration_mode": "dag_guided"}},
        )
    )
    assert _inbox_size() == inbox_before + 1
    if target_state in {"failed", "cancelled"}:
        assert supervisor.state.value == target_state  # parked：不唤醒不复活
    if target_state in {"queued", "succeeded"}:
        assert _run_count() == runs_before + 1  # wake 开新 run（无 runner：只落事件）
        assert supervisor.state.value == "running"
    else:
        assert _run_count() == runs_before
    if target_state == "waiting":
        assert supervisor.state.value == "waiting_approval"  # 等待不被绕过

    # 持久化未决事项不清空。
    assert await asyncio.to_thread(_queued_request_ids, project.id) == [request_id]

    # guided→guided 重发不重复补通知（钩子是迁移沿，不是每次 settings 写）。
    await bus.execute(
        Command(
            type="project.update",
            target={"project_id": project.id},
            payload={"settings": {"orchestration_mode": "dag_guided"}},
        )
    )
    assert _inbox_size() == inbox_before + 1


# ------------------------------------------------------------- Task 4 · 恢复矩阵
# （需要 runner/LLM 的用例在本文件；纯投影/重放用例在
# tests/test_runtime_v2_persistence.py。）


@pytest.mark.asyncio
async def test_interrupted_supervisor_explicit_recovery_reads_full_backlog(tmp_path):
    """恢复矩阵·待办处理前中断。

    通知已让 supervisor 开跑（run 只活在内存）→ 进程重启 → restore 把僵尸
    running 落 failed → reconcile 不自动复活（failed 不是正常休眠）→
    显式恢复（agent.restart）后新 run 重读持久信箱，两条积压请求都被裁决。
    """
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    store = RuntimeStore(tmp_path / "runtime.db")
    # 旧进程：无 runner——通知只落到"supervisor 已开跑"的事件层即"崩溃"。
    core1 = RuntimeCore(strict_events=True)
    core1.store = store
    bus1 = CommandBus(core1)
    project = (
        await bus1.execute(
            Command(
                type="project.create",
                payload={
                    "name": "recover-interrupted",
                    "workspace_dir": str(tmp_path),
                    "settings": {
                        "orchestration_mode": "dag_guided",
                        # scripted LLM 直发业务工具调用，走传统协议（默认
                        # javascript 的线缆只放 js_exec + 直接控制类）。
                        "defaults": {"invocation_protocol": "traditional"},
                    },
                },
            )
        )
    ).data
    coordinator = (
        await bus1.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "coordinator",
                    "settings": {"orchestration_mode": "dag_guided"},
                },
            )
        )
    ).data
    # Task 4A：覆盖通过的交付图（随项目库跨重启存续）让结束门禁对
    # coordinator 透明——否则恢复后督导完成回传唤醒 coordinator，其纯文本
    # 收尾会创建退出审批请求并再次通知 supervisor，干扰 run 数断言。
    await _seed_complete_delivery(project.id)
    request_1 = await _seed_review_request(project.id, coordinator.id, question="backlog one")
    request_2 = await _seed_review_request(project.id, coordinator.id, question="backlog two")
    await notify_supervisor(core1, project.id, reason="explicit evidence submission")
    supervisor1 = find_project_supervisor(core1, project.id)
    assert supervisor1 is not None and supervisor1.state.value == "running"

    # 进程重启：restore 把 running 尸体落 failed，不发普通子 agent 回报。
    # 科学待办告警留给后面的 reconcile，装载路径不 wake Coordinator。
    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    restore_core(core2, store)
    supervisor2 = core2.agents[supervisor1.id]
    assert supervisor2.state is AgentState.FAILED
    reports = [
        e
        for e in core2.event_log.query_session(coordinator.id, types={"agent.message_injected"})
        if "[Sub-agent finished]" in str(e.data.get("content", ""))
        and supervisor1.id in str(e.data.get("content", ""))
    ]
    assert reports == []

    # reconcile 不自动复活 failed：restore 重建原通知，同版本不再重复补投。
    # 装载路径 auto_wake=False：D2 告警仍 pin + mailbox，但不把 Coordinator 打进 LLM。
    events_before = len(core2.event_log)
    await reconcile_supervision(core2, project.id, auto_wake=False)
    new_events = list(core2.event_log)[events_before:]
    supervisor_events = [
        e for e in new_events if e.session_id == supervisor2.id
    ]
    assert supervisor_events == []
    assert supervisor2.state is AgentState.FAILED
    inbox = core2.mailbox.inbox(supervisor2.id)
    assert inbox is not None and inbox.qsize() == 1
    # D2 告警：Coordinator 收到 pin + 投递（点名终态/不复活/恢复入口）。
    assert any(
        e.type == "context.pin_set"
        and e.session_id == coordinator.id
        and e.data.get("key") == TERMINAL_SUPERVISOR_PIN_KEY
        for e in new_events
    )
    alerts = [
        e
        for e in new_events
        if e.type == "agent.message_injected"
        and e.session_id == coordinator.id
        and "[Supervision] ALERT" in str(e.data.get("content", ""))
    ]
    assert len(alerts) == 1
    assert "will not auto-revive" in alerts[0].data["content"]

    # 显式恢复（用户/指令级入口 agent.restart）：重读全部待办。
    llm = _MailboxAdjudicatorLLM(project.id)
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.invocation import InvocationService

    stages = default_stages(core2)
    executor = LegacyToolExecutor(core2)
    invocations = InvocationService(
        event_writer=core2.event_writer, stages=stages, tools=executor, agents=core2.agents
    )
    pipeline = TurnPipeline(
        event_log=core2.event_log,
        stages=stages,
        llm=llm,
        tools=executor,
        notices=core2.notices,
        invocations=invocations,
    )
    core2.runner = AgentRunner(
        core2, pipeline, retry_backoff=(0.01, 0.01)
    )
    bus2 = CommandBus(core2)
    try:
        await bus2.execute(
            Command(
                type="agent.restart",
                target={"session_id": supervisor2.id},
                payload={"message": "resume supervision"},
            )
        )
        deadline = asyncio.get_running_loop().time() + 5.0
        while await asyncio.to_thread(_queued_request_ids, project.id):
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("recovered supervisor did not drain the backlog")
            await asyncio.sleep(0.01)
        await _wait_state(supervisor2, "succeeded")
        for rid in (request_1, request_2):
            decision = await asyncio.to_thread(_decision_for, project.id, rid)
            assert decision is not None, f"{rid} lost across restart"
        runs = [
            e for e in core2.event_log.query_session(supervisor2.id) if e.type == "run.started"
        ]
        assert len(runs) == 2  # 旧进程尸体 run + 显式恢复 run
    finally:
        llm.release.set()
        await _teardown(core2, supervisor2, core2.agents[coordinator.id])


@pytest.mark.asyncio
async def test_duplicate_notification_after_decision_does_not_rerun_review(tmp_path):
    """恢复矩阵·裁决后重复通知幂等。

    已裁决的请求（resolved + 通知闭环）之后：reconcile 因无可消费待办而
    no-op；即便再来一次裸 notify，也不重开空 run；
    裁决工具调用数不增长（dag_review_evidence 只被请求一次，
    resolve_review 的 duplicate_decision 守卫兜底）。"""
    llm = _MailboxAdjudicatorLLM("")
    core, bus, _stages = _full_wiring(llm)
    project = await _guided_project(bus, tmp_path, "recover-idempotent")
    llm.project_id = project.id
    # 最终交付预先通过审查，本用例只守这一份咨询裁决的重复通知。
    await _seed_complete_delivery(project.id)
    coordinator = await _spawn_guided_coordinator(bus, project)
    await _approve_final_delivery(project.id, coordinator.id)
    supervisor = None
    try:
        request_id = await _seed_review_request(
            project.id, coordinator.id, question="adjudicated once"
        )
        await notify_supervisor(core, project.id, reason="explicit evidence submission")
        supervisor = find_project_supervisor(core, project.id)
        assert supervisor is not None
        await _wait_state(supervisor, "succeeded")
        decision = await asyncio.to_thread(_decision_for, project.id, request_id)
        assert decision is not None
        assert len(_supervisor_tool_calls(core, supervisor.id, "dag_review_evidence")) == 1
        # 通知已闭环：重投为零。
        assert await flush_review_notifications(core, project.id) == 0
        runs_before = len(
            [e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"]
        )

        # reconcile：可消费待办为零 → no-op（不再唤醒）。
        await reconcile_supervision(core, project.id)
        await asyncio.sleep(0.05)
        assert (
            len([e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"])
            == runs_before
        )

        # 裸 notify（迟到重复通知）：同一已完成版本不重开空 run。
        await notify_supervisor(core, project.id, reason="stale duplicate nudge")
        await _wait_state(supervisor, "succeeded")
        assert len(await _wait_run_count(core, supervisor, runs_before)) == runs_before
        assert len(_supervisor_tool_calls(core, supervisor.id, "dag_review_evidence")) == 1
        # 决定仍只有一份；请求保持 resolved。
        later = await asyncio.to_thread(_decision_for, project.id, request_id)
        assert later is not None and later.decision_id == decision.decision_id
        assert await flush_review_notifications(core, project.id) == 0
    finally:
        llm.release.set()
        await _teardown(core, coordinator, supervisor)


@pytest.mark.asyncio
async def test_reconcile_without_auto_wake_parks_succeeded_supervisor():
    """API 装载：休眠督导只收信箱通知，不开新 LLM run（issue #35）。"""
    llm = _LatchedSupervisorLLM()
    core, bus, project = await _setup(llm)
    supervisor = None
    try:
        await _seed_pending_review(project.id)
        supervisor = (
            await bus.execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={
                        "role_id": SUPERVISOR_ROLE_ID,
                        "settings": {"orchestration_mode": "dag_guided"},
                    },
                )
            )
        ).data
        await core.agent_host.start_run(supervisor)
        await core.agent_host.finish_run(supervisor, outcome="succeeded")
        assert supervisor.state.value == "succeeded"
        calls_before = llm.supervisor_calls

        await reconcile_supervision(core, project.id, auto_wake=False)
        await asyncio.sleep(0.05)
        assert supervisor.state.value == "succeeded"
        assert llm.supervisor_calls == calls_before
        inbox = core.mailbox.inbox(supervisor.id)
        assert inbox is not None and inbox.qsize() == 1
        injected = [
            e
            for e in core.event_log.query_session(supervisor.id)
            if e.type == "agent.message_injected"
        ]
        assert injected
        assert "persisted backlog found on project load" in str(
            injected[-1].data.get("content", "")
        )
    finally:
        llm.release.set()
        await _teardown(core, supervisor)


@pytest.mark.asyncio
async def test_reconcile_without_auto_wake_does_not_spawn_supervisor():
    """API 装载：有待办但还没有督导时不 spawn（等显式 resume / 在线 notify）。"""
    llm = _LatchedSupervisorLLM()
    core, _bus, project = await _setup(llm)
    try:
        await _seed_pending_review(project.id)
        await reconcile_supervision(core, project.id, auto_wake=False)
        assert find_project_supervisor(core, project.id) is None
        assert llm.supervisor_calls == 0
    finally:
        llm.release.set()
        await _teardown(core)


@pytest.mark.asyncio
async def test_find_project_supervisor_prefers_non_terminal_when_duplicate():
    """身份不变量破坏时优先用还活着的督导，避免把 failed 尸体当成身份。"""
    llm = _LatchedSupervisorLLM()
    core, bus, project = await _setup(llm)
    try:
        first = (
            await bus.execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={
                        "role_id": SUPERVISOR_ROLE_ID,
                        "settings": {"orchestration_mode": "dag_guided"},
                    },
                )
            )
        ).data
        second = (
            await bus.execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": project.id},
                    payload={
                        "role_id": SUPERVISOR_ROLE_ID,
                        "settings": {"orchestration_mode": "dag_guided"},
                    },
                )
            )
        ).data
        await core.agent_host.start_run(first)
        await core.agent_host.finish_run(
            first,
            outcome="failed",
            error="old",
            failure_kind=RunFailureKind.PIPELINE_INTERNAL,
        )
        found = find_project_supervisor(core, project.id)
        assert found is not None
        assert found.id == second.id
        assert first.state.value == "failed"
        assert second.state.value == "queued"
    finally:
        llm.release.set()
        await _teardown(core, first, second)
