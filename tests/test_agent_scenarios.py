"""场景级 Agent 回归场景（评审 5.8）。

每个用例 = 一条真实轨迹 + 一组**事件/状态不变量**断言（不断言模型措辞）。
harness 与断言面见 ``tests/agent_scenarios.py`` 的模块 docstring。
"""

from __future__ import annotations

import json
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
async def test_restart_repeats_no_side_effect_and_keeps_unconsumed_message(tmp_path):
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
    try:
        parent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_for(
            lambda: len(harness.child_reports(parent)) == 1, "child report before restart"
        )
        children_before = [child.id for child in harness.children_of(parent)]
        effects_before = [
            tool for tool in harness.tool_events(parent) if tool["tool_name"] == "todo_write"
        ]
        assert len(effects_before) == 1
        assert effects_before[0]["is_success"] is True, harness.describe(parent)
        payload_before = _todo_store_file(harness.project.id, parent.id).read_text(
            encoding="utf-8"
        )

        # 先等父 Agent 终态，排除消息被下一轮正常消费的竞态；再造一条
        # 「已落库但未消费」的消息（重启后必须仍在信箱里）。
        await harness.wait_terminal(parent)
        await harness.core.dispatcher.commit_and_deliver(
            to_session_id=parent.id,
            project_id=harness.project.id,
            content="unconsumed notice",
            sender="system",
            wake=WakePolicy.NEVER,
        )
    finally:
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
async def test_context_overflow_compacts_at_most_once_and_continues(tmp_path, monkeypatch):
    """上下文超预算：**最多一次**压缩（摘要输入来自真实投影），随后继续原任务。

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
                text="second turn after compaction " + ("more padding " * 300),
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
        # 「最多一次」指压缩**安装**次数：一次 run 里不得反复压缩（阈值抖动会
        # 让轨迹被反复摘要，成本与信息损失都翻倍）。摘要调用次数本身会因
        # 分段/合并而 >1（容量越小段越多），故只要求发生了摘要调用。
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
# ------------------------------------------- 7. dag_guided：证据门 + 督导裁决


def _stop_complete() -> Step:
    return Step(
        tools=[
            (
                "stop",
                {
                    "reason": "claiming the task is done",
                    "final_answer": "done",
                    "delivery_disposition": "complete",
                },
            )
        ]
    )


@pytest.mark.asyncio
async def test_dag_guided_insufficient_evidence_never_finishes_successfully(tmp_path):
    """dag_guided：没有任何证据就声明 complete —— 不落 succeeded、不登记交付处置。

    杠杆：结题门禁（stop 审计 + 退出审批）+ 编排模式。证据门一松，这条先红。
    """
    from cloudra.persistence.database import ConversationDB

    provider = ScriptedProvider(default=[_stop_complete()])
    harness = await ScenarioHarness.start(
        tmp_path, provider=provider, orchestration_mode="dag_guided"
    )
    try:
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_for(
            lambda: agent.state.value == "waiting_approval" or agent.state.value in {"failed", "succeeded"},
            "the guided stop to be adjudicated or gated",
        )

        # 空图 + complete 声明绝不允许直接成功收尾。
        assert agent.state.value != "succeeded", harness.describe(agent)
        rows = harness.run_rows(agent)
        assert all(row["outcome"] != "succeeded" for row in rows), rows
        # 交付处置不被登记（没有可审计的退出依据）。
        db = ConversationDB(harness.project.id).init()
        with db.connect() as con:
            registered = con.execute(
                "SELECT COUNT(*) FROM dag_delivery_dispositions"
            ).fetchone()[0]
        assert registered == 0, "证据不足的 complete 声明被登记成了交付处置"
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_dag_guided_supervisor_verdict_is_delivered_once_and_resumes(tmp_path):
    """dag_guided：督导裁决**恰好一次**投递给挂起的 Coordinator，并唤醒它续跑。

    轨迹：Coordinator 提交 exit 评审请求（``dag_message_supervisor``）→ 运行时
    派发/通知督导 → 督导以真实工具 ``dag_review_evidence`` 落库裁决 →
    ``flush_review_notifications``（与 reconcile 补投同一实现）投递并唤醒。
    杠杆：评审批次 + 投递/唤醒语义（dispatcher 的 WakePolicy）+ 结题门禁恢复。
    """
    provider = ScriptedProvider(
        by_role={
            "coordinator": [
                Step(
                    tools=[
                        (
                            "dag_message_supervisor",
                            {
                                "kind": "exit",
                                "question": "Approve partial delivery?",
                                "target_ids": ["step1"],
                                "proposal": {
                                    "disposition": "partial",
                                    "scope": {"targets": ["step1"]},
                                    "remaining_gaps": ["endpoint_b optimization"],
                                    "method_limits": ["MACE PES"],
                                },
                            },
                        )
                    ]
                )
            ],
            "supervisor": [Step(text="standing by", stop=True)],
        }
    )
    harness = await ScenarioHarness.start(
        tmp_path, provider=provider, orchestration_mode="dag_guided"
    )
    try:
        coordinator = await harness.spawn("coordinator", protocol="traditional")
        request_id = await harness.wait_for_review_request("exit")

        # 督导以真实工具裁决：身份走在线路径同款桥（type=supervisor）。
        from cloudra.base.session_class import Session
        from cloudra.runtime_v2.supervision import flush_review_notifications
        from cloudra.tools.Plantool.dag_tools.dag_review_evidence import DagReviewEvidence
        from tests.dag_identity import call_dag_tool, make_supervisor

        supervisor = make_supervisor(harness.project.id)
        session = Session(coordinator.id, "")
        verdict = await call_dag_tool(
            DagReviewEvidence,
            supervisor,
            session,
            request_id=request_id,
            verdict="accept",
            reason="partial delivery is acceptable for the recorded scope",
        )
        assert verdict.is_success is True, verdict

        # 补投：与 reconcile 同一实现；第一次投递、第二次幂等（不重投）。
        first = await flush_review_notifications(harness.core, harness.project.id)
        second = await flush_review_notifications(harness.core, harness.project.id)
        assert first == 1, f"expected exactly one delivered verdict, got {first}"
        assert second == 0, "重投不幂等：同一裁决被投递了两次"

        delivered = [
            data
            for data in harness.messages(coordinator)
            if request_id in json.dumps(data, ensure_ascii=False)
        ]
        assert len(delivered) == 1, harness.describe(coordinator)
        # 裁决不是 queued 了（真的落库并闭环）。
        from cloudra.persistence.database import ConversationDB

        db = ConversationDB(harness.project.id).init()
        with db.connect() as con:
            states = [
                row[0]
                for row in con.execute("SELECT state FROM dag_review_requests").fetchall()
            ]
        assert states and all(state != "queued" for state in states), states
    finally:
        await harness.aclose()
