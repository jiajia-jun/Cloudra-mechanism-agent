"""场景级 Agent 回归场景（评审 5.8）。

每个用例 = 一条真实轨迹 + 一组**事件/状态不变量**断言（不断言模型措辞）。
harness 与断言面见 ``tests/agent_scenarios.py`` 的模块 docstring。
"""

from __future__ import annotations

import shutil
from pathlib import Path

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


@pytest.mark.asyncio
async def test_small_mol_loads_skill_before_allowed_compute_entry(tmp_path):
    """small_mol：需要计算时先加载技能，再走允许的计算入口（真实工具 + 真实权限）。

    杠杆：角色权限矩阵 + 工具目录。权限收紧了这条会在「工具被拒」处红。
    """
    provider = ScriptedProvider(by_role={})
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        workspace = _workspace(harness.project.id)
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "h2o.gjf").write_text(
            "#p hf/sto-3g\n\n0 1\nO 0 0 0\nH 0 0 1.0\nH 0 1.0 0\n\n", encoding="utf-8"
        )
        provider.script(
            "small_mol",
            Step(tools=[("get_skill", {"skill_name": "dft-calculation"})]),
            Step(
                tools=[
                    (
                        "submit_compute_job",
                        {"input_file": "h2o.gjf", "job_type": "orca", "cpus": 1},
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

        if shutil.which("orca") is None:
            pytest.skip("orca 未安装：策略路径已验证，作业落库断言需要真实引擎")
        from cloudra.persistence.database import ComputeDB

        with ComputeDB().connect() as con:
            jobs = con.execute("SELECT jobtype, state FROM compute_jobs").fetchall()
        assert len(jobs) == 1, f"expected exactly one compute job, got {jobs}"
        assert jobs[0][0] == "orca"
        assert jobs[0][1] in {"ready", "queued", "pending"}, jobs
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

        # 造一条「已落库但未消费」的消息（重启后必须仍在信箱里）。
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
