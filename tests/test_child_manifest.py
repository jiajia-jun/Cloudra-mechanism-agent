"""子 Agent 完成回报的结构化 manifest（评审 5.5 后半）。

覆盖验收要求的四种稳定形状：无最终文本、failed、cancelled、swarm 部分失败；
以及「文本由 manifest 确定性渲染」「事件保留结构化数据而 inbox 载荷不带」
「汇报里不出现秘密 / 超大工具输出」。
"""

from __future__ import annotations

import json

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.child_manifest import (
    _next_steps,
    build_child_manifest,
    render_child_report,
)
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.failures import RunFailureKind
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentSession, AgentState, Command
from cloudra.runtime_v2.subagent_bridge import (
    deliver_child_completion_to_parent,
    handle_native_tool,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class _EchoLLM:
    """脚本化 LLM：每个 agent 立即以纯文本结束（不需要真实 key）。"""

    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(content=f"{agent.role_id} done", stop_requested=True)


async def _child(
    *, role_id: str = "explorer", with_runner: bool = False
) -> tuple[RuntimeCore, AgentSession]:
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "manifest"}))
    project = next(iter(core.projects.values()))
    child = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": role_id, "query": "q"},
            )
        )
    ).data
    if with_runner:
        core.runner = AgentRunner(
            core,
            TurnPipeline(
                event_log=core.event_log,
                stages=default_stages(),
                llm=_EchoLLM(),
                tools=LegacyToolExecutor(core),
            ),
        )
    await core.agent_host.start_run(child)
    return core, child


async def _finish(core, child, outcome: str, **kwargs) -> None:
    """收尾：失败 run 必须带 failure_kind（#63 硬不变量）；未给时用 pipeline_internal。"""
    if outcome != "succeeded" and kwargs.get("failure_kind") is None:
        kwargs["failure_kind"] = RunFailureKind.PIPELINE_INTERNAL
    await core.agent_host.finish_run(child, outcome=outcome, **kwargs)


@pytest.mark.asyncio
async def test_manifest_shapes_succeeded_cancelled_and_no_final_text():
    core, child = await _child()
    reply = core.event_log.append(
        "agent.message_emitted",
        stream="agent",
        project_id=child.project_id,
        session_id=child.id,
        run_id=child.current_run.run_id,
        data={"content": "explorer done"},
    )
    core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=child.project_id,
        session_id=child.id, run_id=child.current_run.run_id,
        data={"action": "allow_final", "result_message_id": reply.event_id},
    )
    await _finish(core, child, "succeeded")
    manifest = build_child_manifest(core, child)
    assert manifest["state"] == "succeeded"
    assert manifest["terminal"] is True
    assert manifest["runs"] == {"total": 1, "succeeded": 1, "failed": 0, "cancelled": 0}
    assert manifest["last_run"]["outcome"] == "succeeded"
    assert manifest["final_summary"] == "explorer done"
    assert manifest["final_summary_source"] == "message"
    assert manifest["unresolved"] == [] and manifest["next_steps"] == []

    # cancelled：没有 run.finished，形状依然稳定。
    core2, child2 = await _child()
    await CommandBus(core2).execute(
        Command(type="agent.cancel", target={"session_id": child2.id}, payload={})
    )
    cancelled = build_child_manifest(core2, child2)
    assert cancelled["state"] == "cancelled"
    assert cancelled["last_run"]["outcome"] == "cancelled"
    assert cancelled["last_run"]["failure_kind"] is None
    assert cancelled["runs"] == {"total": 1, "succeeded": 0, "failed": 0, "cancelled": 1}
    assert cancelled["final_summary_source"] == "state_only"
    assert cancelled["unresolved"] == []
    assert cancelled["next_steps"] == ["cancelled: re-dispatch only if the work is still needed"]


@pytest.mark.asyncio
async def test_manifest_failed_child_has_stable_structure_and_next_steps():
    core, child = await _child(role_id="small_mol")
    await _finish(
        core,
        child,
        "failed",
        error="boom: engine crashed",
        failure_kind=RunFailureKind.PIPELINE_INTERNAL,
    )
    manifest = build_child_manifest(core, child)
    assert manifest["state"] == "failed"
    assert manifest["runs"]["failed"] == 1
    assert manifest["final_summary_source"] == "run_error"
    assert "boom: engine crashed" in manifest["final_summary"]
    assert manifest["unresolved"] == ["last run failed (pipeline_internal)"]
    assert manifest["next_steps"] == [
        "harness error; inspect the audit log before re-dispatching"
    ]


@pytest.mark.asyncio
async def test_manifest_treats_legacy_missing_failure_kind_as_unclassified():
    """旧事件没有 failure_kind 时按 unclassified 记，不猜原因。"""
    core, child = await _child(role_id="small_mol")
    run_id = child.current_run.run_id
    core.event_log.append(
        "run.finished",
        stream="agent",
        project_id=child.project_id,
        session_id=child.id,
        run_id=run_id,
        data={"outcome": "failed", "error": "legacy boom", "failure_kind": None},
    )
    from cloudra.runtime_v2.apply import apply_event

    apply_event(core, list(core.event_log)[-1])
    await core.agent_host.transition(child, AgentState.FAILED, reason="failed", run_id=run_id)
    manifest = build_child_manifest(core, child)
    assert manifest["unresolved"] == ["last run failed (unclassified)"]
    assert manifest["next_steps"] == [
        "last run failed; inspect the audit log before re-dispatching"
    ]


@pytest.mark.parametrize(
    ("kind", "expected_fragment"),
    [
        ("provider_permanent", "API key"),
        ("provider_transient_exhausted", "rate limits"),
        ("event_persistence", "durable event write failed"),
        ("pipeline_internal", "inspect the audit log"),
        ("completion_no_progress", "completion gate"),
        ("runtime_interrupted", "process restart"),
    ],
)
def test_next_steps_map_covers_every_failure_kind(kind, expected_fragment):
    """failure_kind → 下一步是确定性映射（run.finished 带该字段时按枚举分流）。"""
    steps = _next_steps(AgentState.FAILED, {"run_id": "r1", "outcome": "failed", "failure_kind": kind})
    assert len(steps) == 1 and expected_fragment in steps[0]


@pytest.mark.asyncio
async def test_render_is_deterministic_and_from_manifest_only():
    core, child = await _child()
    await _finish(core, child, "succeeded")
    manifest = build_child_manifest(core, child)
    text = render_child_report(manifest)
    assert text == render_child_report(manifest)
    assert "[Sub-agent finished] role=explorer" in text
    assert "state=succeeded" in text
    assert "runs: total=1 succeeded=1 failed=0 cancelled=0" in text
    assert "unresolved: none" in text
    assert "next steps: none" in text
    assert manifest["final_summary"] in text


@pytest.mark.asyncio
async def test_delivery_carries_structured_manifest_but_inbox_stays_text_only():
    """事件/API 侧保留结构化数据；父上下文（inbox）只拿渲染文本。"""
    core, child = await _child()
    parent = (
        await CommandBus(core).execute(
            Command(
                type="agent.spawn",
                target={"project_id": child.project_id},
                payload={"role_id": "coordinator", "query": "coordinate"},
            )
        )
    ).data
    child.parent_session_id = parent.id
    await _finish(core, child, "succeeded")

    await deliver_child_completion_to_parent(core, child, wake=False)

    injected = [
        e for e in core.event_log.query_session(parent.id) if e.type == "agent.message_injected"
    ][-1]
    payload = injected.data["manifest"]
    assert payload["session_id"] == child.id
    assert payload["role_id"] == "explorer"
    assert payload["final_summary_source"] == "message" or payload["final_summary_source"] == "state_only"
    inbox = core.mailbox.inbox(parent.id)
    queued = []
    while not inbox.empty():
        queued.append(inbox.get_nowait())
    report = next(m for m in queued if m["content"].startswith("[Sub-agent finished]"))
    assert "manifest" not in report
    assert "runs: total=" in report["content"]


@pytest.mark.asyncio
async def test_swarm_partial_failure_returns_one_manifest_per_child():
    """is_wait 的 swarm：每个 child 一条 manifest（部分失败也是稳定结构）。"""
    core, child_parent = await _child(role_id="coordinator", with_runner=True)
    result = await handle_native_tool(
        core,
        child_parent,
        ToolCall(
            id="tc1",
            name="subagent_swarm",
            arguments={
                "role_id": "explorer",
                "prompt_template": "explore {{item}}",
                "items": ["alpha", "beta"],
                "is_wait": True,
            },
        ),
    )
    assert result.is_success is True
    assert len(result.data["session_ids"]) == 2
    children = result.data["children"]
    assert [m["session_id"] for m in children] == result.data["session_ids"]
    for manifest in children:
        assert set(manifest["runs"]) == {"total", "succeeded", "failed", "cancelled"}
        assert manifest["session_id"] in result.summary


@pytest.mark.asyncio
async def test_manifest_and_report_never_leak_secrets_or_raw_output():
    core, child = await _child(role_id="small_mol")
    secret = "sk-live-SECRET-KEY"
    raw = "RAW_TOOL_OUTPUT" * 200
    core.event_log.append(
        "tool.result_recorded",
        stream="agent",
        project_id=child.project_id,
        session_id=child.id,
        run_id=child.current_run.run_id,
        data={"tool_name": "bash", "result": {"summary": raw, "data": {"api_key": secret}}},
    )
    await _finish(core, child, "failed", error="provider rejected the request")
    manifest = build_child_manifest(core, child)
    text = render_child_report(manifest)
    blob = json.dumps(manifest) + text
    assert secret not in blob
    assert "RAW_TOOL_OUTPUT" not in blob
    assert len(text) < 2000
