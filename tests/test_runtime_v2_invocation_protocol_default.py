"""跨层契约：`invocation_protocol` 的默认值必须处处一致（评审 5.1）。

代码层的默认值是 `javascript`（`RuntimeSettings` 与 `CurrentRun` 的 schema
默认值由 `tests/test_public_tool_contracts.py` 钉住）；本文件覆盖剩下几层：
schema 默认值、项目默认值、新建 agent、`run.started` 事件、`CurrentRun` 冻结
值，以及 README / README_CN / 设计说明的同一口径。

口径只有一条：**新建的 run 默认用 `javascript`**；`traditional` 是 per-agent
可选设置。协议不可用时继续 fail-loud（`runtime_unavailable`），不得引入按
provider 静默回退协议的逻辑。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import (
    AgentSession,
    Command,
    CurrentRun,
    InvocationProtocol,
    RuntimeSettings,
    utc_now,
)

_ROOT = Path(__file__).resolve().parents[1]

_DESIGN_SPEC = _ROOT / "docs" / "superpowers" / "specs" / "2026-09-05-event-driven-js-runtime-design.md"

# 文档里声明默认值的句子（改动措辞必须同步本测试）；旧口径的原文一并钉住，
# 防止 traditional 默认的说法回流。
_DOC_DEFAULT_SENTENCES = (
    (
        _ROOT / "README.md",
        "The default protocol is `javascript`; `traditional` is a per-agent opt-in.",
        "By default agents issue one tool call per wire exchange (`invocation_protocol: traditional`).",
    ),
    (
        _ROOT / "README_CN.md",
        "默认协议是 `javascript`；`traditional` 是 per-agent 可选设置。",
        "默认情况下，Agent 每次有线交换发起一个工具调用（`invocation_protocol: traditional`）。",
    ),
    (
        _DESIGN_SPEC,
        "Two invocation protocols: `javascript` (default) and `traditional`.",
        "Two invocation protocols: `traditional` (default) and `javascript`.",
    ),
)


def test_schema_defaults_agree_on_javascript():
    assert RuntimeSettings().invocation_protocol is InvocationProtocol.JAVASCRIPT
    assert CurrentRun(run_id="run_test", started_at=utc_now()).invocation_protocol is InvocationProtocol.JAVASCRIPT


@pytest.mark.asyncio
async def test_new_project_agent_and_run_default_to_javascript():
    """项目默认值缺席时，新建 agent 与其首个 run 都冻结 `javascript`。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "protocol default"}))
    project = next(iter(core.projects.values()))
    assert project.settings.defaults.invocation_protocol is None

    spawned = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "hello"},
        )
    )
    agent = spawned.data
    assert agent.settings.invocation_protocol is InvocationProtocol.JAVASCRIPT

    await core.agent_host.start_run(agent)
    started = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    assert len(started) == 1
    assert started[0].data["invocation_protocol"] == "javascript"
    assert started[0].data["settings_summary"]["invocation_protocol"] == "javascript"
    assert agent.current_run is not None
    assert agent.current_run.invocation_protocol is InvocationProtocol.JAVASCRIPT


@pytest.mark.asyncio
async def test_explicit_project_default_protocol_is_honoured_end_to_end():
    """显式项目默认值（traditional）必须一路传到 agent、事件与 CurrentRun。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="project.create",
            payload={
                "name": "explicit traditional",
                "settings": {"defaults": {"invocation_protocol": "traditional"}},
            },
        )
    )
    project = next(iter(core.projects.values()))

    spawned = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    agent = spawned.data
    assert agent.settings.invocation_protocol is InvocationProtocol.TRADITIONAL

    await core.agent_host.start_run(agent)
    started = [e for e in core.event_log.query_session(agent.id) if e.type == "run.started"]
    assert started[0].data["invocation_protocol"] == "traditional"
    assert agent.current_run.invocation_protocol is InvocationProtocol.TRADITIONAL

    # run 级冻结：中途改设置只影响下一个 run，当前 run 的协议不变。
    agent.settings.invocation_protocol = InvocationProtocol.JAVASCRIPT
    assert agent.current_run.invocation_protocol is InvocationProtocol.TRADITIONAL


def test_default_protocol_wire_projection_is_js_exec_plus_direct_controls():
    """默认协议的线缆投影只放 js_exec + 直接控制类工具；traditional 才回到逐调用面。"""
    from cloudra.runtime_v2.tool_catalog import wire_tool_schemas

    agent = AgentSession(id="s1", project_id="p1", role_id="coordinator", display_name="c")
    assert agent.settings.invocation_protocol is InvocationProtocol.JAVASCRIPT

    names = ["bash", "stop"]
    wire = {(s.get("function") or {}).get("name") for s in wire_tool_schemas(agent, names)}
    assert "js_exec" in wire
    assert "bash" not in wire

    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    traditional = {(s.get("function") or {}).get("name") for s in wire_tool_schemas(agent, names)}
    assert "bash" in traditional
    assert "js_exec" not in traditional


def test_docs_declare_javascript_as_the_only_default():
    for path, sentence, stale in _DOC_DEFAULT_SENTENCES:
        text = path.read_text(encoding="utf-8")
        assert sentence in text, f"{path.name} must state the javascript default verbatim"
        assert stale not in text, f"{path.name} still carries the traditional-default wording"
