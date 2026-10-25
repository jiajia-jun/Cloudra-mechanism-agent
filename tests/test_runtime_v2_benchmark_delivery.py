"""基础交付与科学验收分开：Benchmark 根任务漏图时必须反馈，挂起不催交。"""

from __future__ import annotations

import asyncio
import json

import pytest

from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentSession, AgentState, Command, OrchestrationMode, Project, ProjectSettings
from cloudra.runtime_v2.turn_pipeline import TurnPipeline
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, benchmark_delivery_recovery_steps


def runtime(tmp_path, *, mode="standard", role="coordinator", benchmark=True):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="delivery", workspace_dir=str(tmp_path),
        settings=ProjectSettings(benchmark_task_id="T1" if benchmark else None,
            orchestration_mode=mode))
    agent = AgentSession(id="a", project_id="p", role_id=role, display_name=role)
    agent.settings.orchestration_mode = OrchestrationMode(mode)
    core.agents[agent.id] = agent
    # 此处只验证共用收尾边界，科学策略各自有既有回归；下方场景走默认全链路。
    pipeline = TurnPipeline(event_log=core.event_log, stages=[], llm=None, tools=None)
    runner = AgentRunner(core, pipeline)
    core.runner = runner
    return core, runner, agent


async def evaluate(runner, agent, *, explicit_stop=False):
    return await runner._evaluate_completion_gate(agent, "run", explicit_stop=explicit_stop,
        stop_arguments={} if explicit_stop else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["standard", "dag_record", "dag_guided"])
@pytest.mark.parametrize("explicit_stop", [False, True])
async def test_missing_benchmark_graph_blocks_root_completion(tmp_path, mode, explicit_stop):
    core, runner, agent = runtime(tmp_path, mode=mode)
    gate, source = await evaluate(runner, agent, explicit_stop=explicit_stop)
    assert gate.action == "continue_work"
    assert source == "benchmark_delivery"
    assert "mechanism_graph.json" in gate.reason
    assert core.event_log.query_session(agent.id)[-1].data["action"] == "continue_work"


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["broken json", "{}", '{"nodes":{}}',
    '{"nodes":[{"id":"R","role":"unrecognised"}]}',
    '{"nodes":[{"id":"R","type":"reactant","role":[]}]}'])
async def test_invalid_graph_returns_repair_feedback(tmp_path, content):
    await asyncio.to_thread((tmp_path / "mechanism_graph.json").write_text, content)
    _core, runner, agent = runtime(tmp_path)
    gate, _source = await evaluate(runner, agent)
    assert gate.action == "continue_work"
    assert "mechanism_graph.json" in gate.reason


@pytest.mark.asyncio
async def test_valid_graph_without_scientific_evidence_remains_declared(tmp_path):
    document = {"nodes": [{"id": "R", "role": "reactant", "smiles": ["O"]}], "edges": []}
    path = tmp_path / "mechanism_graph.json"
    await asyncio.to_thread(path.write_text, json.dumps(document))
    _core, runner, agent = runtime(tmp_path)
    gate, source = await evaluate(runner, agent)
    assert gate.action == "allow_final"
    assert gate.basis == "declared"
    assert source == "declared"
    assert json.loads(await asyncio.to_thread(path.read_text)) == document


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["ordinary", "child", "peer", "supervisor"])
async def test_only_benchmark_root_researcher_requires_project_graph(tmp_path, scope):
    _core, runner, agent = runtime(tmp_path, benchmark=scope != "ordinary",
        role="supervisor" if scope == "supervisor" else "coordinator")
    if scope == "child":
        agent.parent_session_id = "parent"
    elif scope == "peer":
        agent.requested_by_session_id = "requester"
    gate, _source = await evaluate(runner, agent)
    assert gate.action == "allow_final"


@pytest.mark.asyncio
async def test_noncoordinator_benchmark_root_still_requires_delivery(tmp_path):
    _core, runner, agent = runtime(tmp_path, role="small_mol")
    gate, _source = await evaluate(runner, agent)
    assert gate.action == "continue_work"


@pytest.mark.asyncio
async def test_active_child_preserves_existing_background_wait(tmp_path):
    core, runner, agent = runtime(tmp_path)
    core.agents["child"] = AgentSession(id="child", project_id="p", role_id="small_mol",
        display_name="child", parent_session_id=agent.id, state=AgentState.RUNNING)
    gate, _source = await evaluate(runner, agent)
    assert gate.action == "allow_final"  # Benchmark watcher 继续负责已有的后台等待。
    core.agents["child"].state = AgentState.SUCCEEDED
    gate, _source = await evaluate(runner, agent)
    assert gate.action == "continue_work"


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_stop", [False, True])
async def test_standard_agent_recovers_missing_delivery_in_same_run(tmp_path, monkeypatch, explicit_stop):
    from cloudra.infra.yolo_guard import YoloGuard

    async def approve_write(self, task, tool_name, tool_args, actor_name, **kwargs):
        return True, "scripted approval"

    # 只替换审批模型的网络调用；文件工具、版本登记和结束反馈都走真实实现。
    monkeypatch.setattr(YoloGuard, "judge", approve_write)
    provider = ScriptedProvider(by_role={"coordinator": benchmark_delivery_recovery_steps(
        tmp_path / "mechanism_graph.json", explicit_stop=explicit_stop)})
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    try:
        await harness.bus.execute(Command(type="project.update", target={"project_id": harness.project.id},
            payload={"settings": {"benchmark_task_id": "T1", "method_policy": {
                "allowed_methods": ["xtb"]}, "defaults": {"yolo": True}}}))
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(agent)
        assert agent.state is AgentState.SUCCEEDED, harness.describe(agent)
        gates = [event.data for event in harness.events(agent) if event.type == "agent.completion_gate"]
        assert [gate["action"] for gate in gates] == ["continue_work", "allow_final"]
        assert gates[0]["source"] == "benchmark_delivery"
        assert gates[-1]["basis"] == "declared"
        assert [row["outcome"] for row in harness.run_rows(agent)] == ["succeeded"]
        assert provider.call_count("coordinator") == 3
        assert (await asyncio.to_thread((tmp_path / "mechanism_graph.json").read_text)).startswith('{"nodes"')
    finally:
        await harness.aclose()
