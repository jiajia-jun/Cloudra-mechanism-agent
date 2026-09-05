"""Visual mode: settings merge chain, dual tool gating, and config round-trip."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.adapters import LegacyLLMProvider
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall
from cloudra.runtime_v2.policies.permission import PermissionStage
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    Command,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.tools.capabilities import visual_tools

# --- settings merge chain ---------------------------------------------------


async def _spawn(bus: CommandBus, project_id: str, **payload):
    result = await bus.execute(
        Command(type="agent.spawn", target={"project_id": project_id}, payload=payload)
    )
    return result.data


@pytest.mark.asyncio
async def test_visual_mode_defaults_on_and_merges_through_spawn_chain():
    """Default is on; project defaults flow into spawn; per-agent patch wins."""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))

    agent = await _spawn(bus, project.id, role_id="coordinator")
    assert agent.settings.visual_mode is True

    await bus.execute(
        Command(
            type="project.update",
            target={"project_id": project.id},
            payload={"settings": {"defaults": {"visual_mode": False}}},
        )
    )
    agent = await _spawn(bus, project.id, role_id="coordinator")
    assert agent.settings.visual_mode is False

    agent = await _spawn(
        bus, project.id, role_id="coordinator", settings={"visual_mode": True}
    )
    assert agent.settings.visual_mode is True


# --- registry projection ----------------------------------------------------


def test_visual_tools_projection_reads_registry_metadata():
    # Metadata-only: no tool modules are imported (pymol_render may still be
    # in flight from a parallel change).
    assert visual_tools() == frozenset({"pymol_render"})


# --- LLM-side gate: strip visual tool schemas --------------------------------


def _chunk(content=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=None, reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


class _FakeStream:
    def __init__(self, chunks):
        self._iter = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeClient:
    def __init__(self, sent):
        self._sent = sent
        self.last_usage = {}

    async def create_with_retry(self, **kwargs):
        self._sent.update(kwargs)
        return _FakeStream([_chunk(content="ok", finish_reason="stop")])


def _visual_agent(visual_mode: bool):
    return SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(
            model="m",
            base_url="https://api.example/",
            api_key="sk-x",
            visual_mode=visual_mode,
        ),
    )


_FAKE_SCHEMAS = [
    {"type": "function", "function": {"name": "read"}},
    {"type": "function", "function": {"name": "pymol_render"}},
    {"type": "function", "function": {"name": "stop"}},
]


@pytest.mark.asyncio
async def test_complete_strips_visual_tool_schemas_when_visual_mode_off(monkeypatch):
    sent = {}
    # Stub the schema source so the test does not load the full tool registry
    # (pymol_render's module may still be in flight).
    monkeypatch.setattr(
        "cloudra.runtime_v2.adapters.legacy_tool_schemas",
        lambda tools: [dict(s) for s in _FAKE_SCHEMAS],
    )
    provider = LegacyLLMProvider(client_factory=lambda settings: _FakeClient(sent))
    await provider.complete(
        _visual_agent(False),
        [{"role": "user", "content": "hi"}],
        ["read", "pymol_render", "stop"],
    )
    names = [t["function"]["name"] for t in sent["tools"]]
    assert names == ["read", "stop"]


@pytest.mark.asyncio
async def test_complete_keeps_visual_tool_schemas_when_visual_mode_on(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        "cloudra.runtime_v2.adapters.legacy_tool_schemas",
        lambda tools: [dict(s) for s in _FAKE_SCHEMAS],
    )
    provider = LegacyLLMProvider(client_factory=lambda settings: _FakeClient(sent))
    await provider.complete(
        _visual_agent(True),
        [{"role": "user", "content": "hi"}],
        ["read", "pymol_render", "stop"],
    )
    names = [t["function"]["name"] for t in sent["tools"]]
    assert names == ["read", "pymol_render", "stop"]


def test_supports_vision_reads_resolved_legacy_slot(monkeypatch):
    """supports_vision(agent) resolves the legacy slot by role id, like
    legacy_default_settings: coordinator slot for coordinators, follower
    slot for everything else."""
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg.coordinator, "supports_vision", False)
    monkeypatch.setattr(cfg.follower, "supports_vision", True)
    provider = LegacyLLMProvider()
    assert provider.supports_vision(SimpleNamespace(role_id="coordinator")) is False
    assert provider.supports_vision(SimpleNamespace(role_id="researcher")) is True


# --- permission-stage gate ---------------------------------------------------


def _ctx(settings: RuntimeSettings) -> PipelineContext:
    return PipelineContext(
        agent=SimpleNamespace(id="as_x"),
        run_id="run_1",
        settings_snapshot=settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        emit=lambda *_args, **_kwargs: None,
    )


@pytest.mark.asyncio
async def test_permission_stage_blocks_visual_tools_when_visual_mode_off():
    stage = PermissionStage()
    ctx = _ctx(RuntimeSettings(visual_mode=False))
    result = await stage.before_tool(ctx, ToolCall(id="tc1", name="pymol_render"))
    assert result.outcome == "block"
    assert "/visual" in result.message
    # read is not visual-gated; it stays available when visual mode is off.
    allowed = await stage.before_tool(ctx, ToolCall(id="tc2", name="read"))
    assert allowed.outcome == "allow"


@pytest.mark.asyncio
async def test_permission_stage_allows_visual_tools_when_visual_mode_on():
    stage = PermissionStage()
    ctx = _ctx(RuntimeSettings())  # visual_mode defaults to True
    result = await stage.before_tool(ctx, ToolCall(id="tc1", name="pymol_render"))
    assert result.outcome == "allow"


# --- config round-trip -------------------------------------------------------


def test_supports_vision_yaml_round_trip(tmp_path, monkeypatch):
    """supports_vision 经 mutate 落盘后可从 YAML 原样读回（含 False）。"""
    from cloudra.infra.config import CloudraConfig, get_config, mutate_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    # teardown 复位到改前默认值 True
    monkeypatch.setattr(cfg.coordinator, "supports_vision", True)
    monkeypatch.setattr(cfg.follower, "supports_vision", True)
    assert cfg.coordinator.supports_vision is True  # default on

    def _turn_off(work):
        work.coordinator.supports_vision = False
        work.follower.supports_vision = False

    mutate_config(_turn_off)
    assert cfg.coordinator.supports_vision is False
    assert cfg.follower.supports_vision is False

    # 磁盘是事实源：从 YAML 重建的实例同样读到 False
    reloaded = CloudraConfig(config_file=tmp_path / "config.yaml", data_dir=tmp_path / "data")
    assert reloaded.coordinator.supports_vision is False
    assert reloaded.follower.supports_vision is False
    display = reloaded.to_display_dict()
    assert display["llm"]["coordinator"]["supports_vision"] is False
    assert display["llm"]["follower"]["supports_vision"] is False


# --- tool-result visual injection --------------------------------------------


@pytest.mark.asyncio
async def test_tool_result_injects_all_image_paths(tmp_path):
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.policies.base import ToolResult
    pngs = []
    for i in range(3):
        p = tmp_path / f"{i}.png"
        p.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        pngs.append(str(p))
    runner = AgentRunner(
        core=SimpleNamespace(),
        pipeline=SimpleNamespace(llm=SimpleNamespace(supports_vision=lambda _a: True)),
    )
    agent = _visual_agent(True)
    content = await runner._tool_result_content(
        agent,
        ToolResult(is_success=True, summary="scan", data={"image_paths": pngs, "image_path": pngs[0]}),
    )
    assert isinstance(content, list)
    urls = [p for p in content if p.get("type") == "image_url"]
    assert len(urls) == 3


@pytest.mark.asyncio
async def test_runner_history_includes_javascript_outputs_in_order():
    from cloudra.runtime_v2.js_runtime import _summary_with_program_outputs
    from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
    from cloudra.runtime_v2.turn_pipeline import TurnOutcome

    runner = _injection_runner()
    history = []
    outputs = ["hello-orient-53", {"answer": 42}]
    result = ToolResult(
        is_success=False,
        summary=_summary_with_program_outputs(
            "JavaScript program failed: 2 output(s), 0 tool call(s); error: late boom",
            outputs,
        ),
        data={"outputs": outputs, "status": "failed"},
    )
    outcome = TurnOutcome(
        decision="continue",
        tool_exchanges=((ToolCall("js-1", "js_exec", {"code": "..."}), result),),
    )

    await runner._append_history(_visual_agent(False), history, [], outcome)

    content = history[-1]["content"]
    assert "hello-orient-53" in content
    assert '{"answer": 42}' in content
    assert content.index("hello-orient-53") < content.index('{"answer": 42}')
    assert "late boom" in content


@pytest.mark.asyncio
async def test_runner_history_does_not_project_traditional_tool_data():
    from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
    from cloudra.runtime_v2.turn_pipeline import TurnOutcome

    runner = _injection_runner()
    history = []
    result = ToolResult(
        is_success=True,
        summary="traditional summary",
        data={"outputs": ["internal payload"], "value": 7},
    )
    outcome = TurnOutcome(
        decision="continue",
        tool_exchanges=((ToolCall("tool-1", "echo", {}), result),),
    )

    await runner._append_history(_visual_agent(False), history, [], outcome)

    assert history[-1]["content"] == "traditional summary"


@pytest.mark.asyncio
async def test_runner_history_keeps_no_output_javascript_summary_unchanged():
    from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
    from cloudra.runtime_v2.turn_pipeline import TurnOutcome

    runner = _injection_runner()
    history = []
    result = ToolResult(
        is_success=True,
        summary="JavaScript program completed: 0 output(s), 1 tool call(s)",
        data={"outputs": [], "status": "completed"},
    )
    outcome = TurnOutcome(
        decision="continue",
        tool_exchanges=((ToolCall("js-2", "js_exec", {"code": "..."}), result),),
    )

    await runner._append_history(_visual_agent(False), history, [], outcome)

    assert history[-1]["content"] == result.summary


_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_pngs(directory, n=3):
    pngs = []
    for i in range(n):
        p = directory / f"{i}.png"
        p.write_bytes(_TINY_PNG)
        pngs.append(str(p))
    return pngs


def _injection_runner(*, supports_vision=True):
    from cloudra.runtime_v2.agent_runner import AgentRunner

    return AgentRunner(
        core=SimpleNamespace(),
        pipeline=SimpleNamespace(
            llm=SimpleNamespace(supports_vision=lambda _a: supports_vision)
        ),
    )


@pytest.mark.asyncio
async def test_tool_result_fallback_line_per_path_when_visual_off(tmp_path):
    from cloudra.runtime_v2.policies.base import ToolResult

    pngs = _write_pngs(tmp_path)
    content = await _injection_runner()._tool_result_content(
        _visual_agent(False),
        ToolResult(is_success=True, summary="scan", data={"image_paths": pngs, "image_path": pngs[0]}),
    )
    assert isinstance(content, str)
    assert content.startswith("scan")
    assert content.count("Image rendered at:") == 3
    for path in pngs:
        assert path in content


@pytest.mark.asyncio
async def test_tool_result_fallback_line_per_path_when_no_vision(tmp_path):
    from cloudra.runtime_v2.policies.base import ToolResult

    pngs = _write_pngs(tmp_path)
    content = await _injection_runner(supports_vision=False)._tool_result_content(
        _visual_agent(True),
        ToolResult(is_success=True, summary="scan", data={"image_paths": pngs, "image_path": pngs[0]}),
    )
    assert isinstance(content, str)
    assert content.count("Image rendered at:") == 3
    for path in pngs:
        assert path in content


@pytest.mark.asyncio
async def test_register_tool_image_registers_every_path(tmp_path):
    from cloudra.infra.config import get_config
    from cloudra.persistence.artifacts import ArtifactService
    from cloudra.runtime_v2.events import EventLog
    from cloudra.runtime_v2.policies.base import PipelineContext, ToolResult
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    workspace = tmp_path / "ws"
    workspace.mkdir()
    pngs = _write_pngs(workspace)
    pipeline = TurnPipeline(
        event_log=EventLog(),
        stages=[],
        llm=SimpleNamespace(),
        tools=SimpleNamespace(),
    )
    ctx = PipelineContext(
        agent=SimpleNamespace(project_id="proj_images", id="sess_images", role_id="coordinator"),
        run_id="run_1",
        settings_snapshot=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        emit=lambda *_args, **_kwargs: None,
        workspace_dir=str(workspace),
    )
    # The helper moved with the tool lifecycle into the InvocationService.
    last_id = await pipeline.invocations._register_tool_image(
        ctx,
        ToolResult(is_success=True, summary="scan", data={"image_paths": pngs, "image_path": pngs[0]}),
    )
    assert last_id
    artifacts = await asyncio.to_thread(ArtifactService(get_config().data_dir).list, "proj_images")
    assert [a.artifact_id for a in artifacts]
    assert len(artifacts) == 3
    names = {a.name for a in artifacts}
    assert names == {"0.png", "1.png", "2.png"}
