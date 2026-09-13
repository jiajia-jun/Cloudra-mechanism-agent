"""DAG stage delivery delta on tool results."""

from __future__ import annotations

import pytest

from cloudra.dag.delta import DeliveryDelta
from cloudra.dag.models import OrchestrationMode
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
from cloudra.runtime_v2.policies.dag_stage import DagPolicyStage
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    PermissionSet,
    RuntimeSettings,
)


class _FakeController:
    def __init__(self) -> None:
        self.mode = OrchestrationMode.DAG_GUIDED
        self.enabled = True
        self.finished_return: object = None

    async def initialize(self) -> None:
        return None

    async def check_substantive_gate(self, tool_name, arguments):
        return None

    async def on_tool_finished(self, *args, **kwargs):
        return self.finished_return


def _ctx(notices=None) -> PipelineContext:
    agent = AgentSession(
        id="as_parent",
        project_id="prj",
        role_id="coordinator",
        display_name="c",
        settings=RuntimeSettings(orchestration_mode="dag_guided"),
    )
    return PipelineContext(
        agent=agent,
        run_id="run1",
        settings_snapshot=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        emit=lambda *a, **k: None,
        notices=notices,
    )


@pytest.mark.asyncio
async def test_delivery_delta_appended_to_tool_result_and_pushed():
    stage = DagPolicyStage()
    controller = _FakeController()
    controller.finished_return = DeliveryDelta(
        tool_name="log_parser",
        bound_target="e_da_step",
        level_from="proposed",
        level_to="computed",
    )
    ctx = _ctx(NoticeManager())
    stage._controllers[ctx.agent.id] = controller
    result = ToolResult(is_success=True, summary='{"is_success": true}')
    await stage.after_tool(
        ctx,
        ToolCall(id="tc1", name="log_parser", arguments={}),
        result,
    )
    assert "[DAG] evidence bound: log_parser → e_da_step (proposed→computed)" in result.summary
    pushed = ctx.notices.collect_batch(ctx.agent.id, fresh=False)
    assert any("[DAG] evidence bound" in m["content"] for m in pushed)


@pytest.mark.asyncio
async def test_no_delta_adds_no_noise():
    stage = DagPolicyStage()
    controller = _FakeController()
    controller.finished_return = DeliveryDelta(tool_name="bash")
    ctx = _ctx(NoticeManager())
    stage._controllers[ctx.agent.id] = controller
    result = ToolResult(is_success=True, summary="ok")
    await stage.after_tool(ctx, ToolCall(id="tc1", name="bash", arguments={}), result)
    assert result.summary == "ok"
    assert ctx.notices.collect_batch(ctx.agent.id, fresh=False) == []
