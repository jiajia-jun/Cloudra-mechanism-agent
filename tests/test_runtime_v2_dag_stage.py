"""DAG harness as a policy stage: gate blocks before graph exists."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    OrchestrationMode,
    PermissionSet,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class FakeLLM:
    async def complete(self, agent, messages, tools):
        return LLMResponse(
            content="",
            tool_calls=[ToolCall(id="tc1", name="text_writer", arguments={"path": "out.md", "content": "x"})],
        )


class FakeTools:
    async def execute(self, agent, call: ToolCall) -> ToolResult:
        return ToolResult(is_success=True, summary="written")


async def _agent(core):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    await CommandBus(core).execute(
        Command(
            type="project.create",
            payload={"name": "dag project", "settings": {"orchestration_mode": "dag_guided"}},
        )
    )
    project = next(iter(core.projects.values()))
    result = await CommandBus(core).execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    return project, result.data


@pytest.mark.asyncio
async def test_dag_stage_blocks_substantive_tool_on_empty_graph(tmp_path):
    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    project.workspace_dir = str(tmp_path)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(),
        tools=FakeTools(),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_dag",
        settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        workspace_dir=str(tmp_path),
    )
    assert outcome.message.startswith("blocked by dag")
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "dag.gate_blocked" in types


@pytest.mark.asyncio
async def test_dag_stage_noop_in_standard_mode(tmp_path):
    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    agent.settings.orchestration_mode = OrchestrationMode.STANDARD
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(),
        tools=FakeTools(),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_std",
        settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        workspace_dir=str(tmp_path),
    )
    assert outcome.decision == "continue"
    assert "dag.gate_blocked" not in [e.type for e in core.event_log.query_session(agent.id)]
