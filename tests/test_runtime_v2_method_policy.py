"""per-project 方法白名单 stage：live pipeline 拦截（GH #25）。

此前 MethodPolicyStage 只由 benchmark 后端注入；本文件守 live 路径：
项目 settings 带 method_policy 时 `default_stages(core)` 即按白名单拦截，
未设置（None）则完全不拦，行为与修复前一致。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    InvocationProtocol,
    PermissionSet,
    ProjectSettings,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

_POLICY = {
    "allowed_methods": ["mace-omol25", "xtb"],
    "intercept_layers": ["bash", "submit_compute_job", "qm_input_writer"],
}
_BASH_B3LYP = "cat > ts.gjf <<'EOF'\n#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\nEOF\n"
_BASH_MACE = 'cat > ts.gjf <<\'EOF\'\n#p external="mace" opt freq\n\nt\n\n0 1\nC 0 0 0\nEOF\n'


def test_project_settings_method_policy_field():
    # 缺省不启用（live 侧绝不默认塞白名单）
    assert ProjectSettings().method_policy is None
    settings = ProjectSettings.model_validate({"method_policy": _POLICY})
    assert settings.method_policy is not None
    assert settings.method_policy.allowed_methods == ["mace-omol25", "xtb"]
    # extra="forbid" 仍然成立
    with pytest.raises(ValidationError):
        ProjectSettings.model_validate({"no_such_field": 1})


class _FakeLLM:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response

    async def complete(self, agent, messages, tools, **_kwargs):
        return self.response


class _RecordingTools:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, agent, call: ToolCall) -> ToolResult:
        self.calls.append(call.name)
        return ToolResult(is_success=True, summary="ok")


async def _spawn(core: RuntimeCore, tmp_path, settings: dict | None = None):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    payload: dict = {"name": "p", "workspace_dir": str(tmp_path)}
    if settings:
        payload["settings"] = settings
    await CommandBus(core).execute(Command(type="project.create", payload=payload))
    project = next(iter(core.projects.values()))
    await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    agent = next(iter(core.agents.values()))
    # 本文件测试用 FakeLLM 直接发业务工具调用，固定传统协议；
    # 默认 javascript 协议只放 js_exec + 直接控制类。
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return project, agent


async def _run_tool_turn(core: RuntimeCore, agent, tmp_path, call: ToolCall, run_id: str = "run_t"):
    tools = _RecordingTools()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=_FakeLLM(LLMResponse(content="", tool_calls=[call], stop_requested=False)),
        tools=tools,
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id=run_id,
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[{"content": "go"}],
        workspace_dir=str(tmp_path),
    )
    return outcome, tools


def _blocked_events(core: RuntimeCore, session_id: str):
    return [
        e
        for e in core.event_log.query_session(session_id)
        if e.type == "tool.blocked" and e.data.get("stage") == "method_policy"
    ]


@pytest.mark.asyncio
async def test_policy_project_blocks_non_whitelisted_bash(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"method_policy": _POLICY})
    outcome, tools = await _run_tool_turn(
        core, agent, tmp_path, ToolCall(id="t1", name="bash", arguments={"command": _BASH_B3LYP})
    )
    # 拦截不罚分：原因作为工具反馈回投，turn 继续
    assert outcome.decision == "continue"
    assert tools.calls == []
    blocked = _blocked_events(core, agent.id)
    assert blocked and "b3lyp" in blocked[0].data.get("message", "")


@pytest.mark.asyncio
async def test_policy_project_allows_whitelisted_bash(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"method_policy": _POLICY})
    outcome, tools = await _run_tool_turn(
        core, agent, tmp_path, ToolCall(id="t1", name="bash", arguments={"command": _BASH_MACE})
    )
    assert outcome.decision == "continue"
    assert tools.calls == ["bash"]
    assert _blocked_events(core, agent.id) == []


@pytest.mark.asyncio
async def test_policy_project_submit_compute_job_layer(tmp_path):
    (tmp_path / "evil.gjf").write_text("#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\n")
    (tmp_path / "ok.gjf").write_text('#p external="mace" opt\n\nt\n\n0 1\nC 0 0 0\n')
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"method_policy": _POLICY})

    _, tools = await _run_tool_turn(
        core, agent, tmp_path,
        ToolCall(id="t1", name="submit_compute_job", arguments={"input_file": "evil.gjf"}),
        run_id="run_evil",
    )
    assert tools.calls == []
    assert _blocked_events(core, agent.id)

    _, tools = await _run_tool_turn(
        core, agent, tmp_path,
        ToolCall(id="t2", name="submit_compute_job", arguments={"input_file": "ok.gjf"}),
        run_id="run_ok",
    )
    assert tools.calls == ["submit_compute_job"]


@pytest.mark.asyncio
async def test_policy_project_bash_referencing_disk_input(tmp_path):
    """bash 层引用磁盘已有 QM 输入（`g16 foo.gjf`）走 referenced_input_paths +
    check_input_files 接线（stage 侧；纯函数覆盖在 test_benchmark.py）。"""
    (tmp_path / "evil.gjf").write_text("#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\n")
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"method_policy": _POLICY})

    _, tools = await _run_tool_turn(
        core, agent, tmp_path,
        ToolCall(id="t1", name="bash", arguments={"command": "g16 evil.gjf"}),
        run_id="run_evil",
    )
    assert tools.calls == []
    blocked = _blocked_events(core, agent.id)
    assert blocked and "b3lyp" in blocked[0].data.get("message", "")


@pytest.mark.asyncio
async def test_project_without_policy_unaffected(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path)
    outcome, tools = await _run_tool_turn(
        core, agent, tmp_path, ToolCall(id="t1", name="bash", arguments={"command": _BASH_B3LYP})
    )
    assert outcome.decision == "continue"
    assert tools.calls == ["bash"]
    assert _blocked_events(core, agent.id) == []
