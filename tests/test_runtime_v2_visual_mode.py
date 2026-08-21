"""Visual mode: settings merge chain, dual tool gating, and config round-trip."""

from __future__ import annotations

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
    assert visual_tools() == frozenset({"image_reader", "pymol_render"})


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
    {"type": "function", "function": {"name": "image_reader"}},
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
        ["image_reader", "pymol_render", "stop"],
    )
    names = [t["function"]["name"] for t in sent["tools"]]
    assert names == ["stop"]


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
        ["image_reader", "pymol_render", "stop"],
    )
    names = [t["function"]["name"] for t in sent["tools"]]
    assert names == ["image_reader", "pymol_render", "stop"]


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
    result = await stage.before_tool(ctx, ToolCall(id="tc1", name="image_reader"))
    assert result.outcome == "block"
    assert "/visual" in result.message
    # Non-visual tools are unaffected.
    allowed = await stage.before_tool(ctx, ToolCall(id="tc2", name="stop"))
    assert allowed.outcome == "allow"


@pytest.mark.asyncio
async def test_permission_stage_allows_visual_tools_when_visual_mode_on():
    stage = PermissionStage()
    ctx = _ctx(RuntimeSettings())  # visual_mode defaults to True
    result = await stage.before_tool(ctx, ToolCall(id="tc1", name="image_reader"))
    assert result.outcome == "allow"


# --- config round-trip -------------------------------------------------------


def test_supports_vision_yaml_round_trip(tmp_path):
    from cloudra.infra.config import CloudraConfig

    cfg_file = tmp_path / "config.yaml"
    cfg = CloudraConfig(config_file=cfg_file, data_dir=tmp_path / "data")
    assert cfg.coordinator.supports_vision is True  # default on
    cfg.coordinator.supports_vision = False
    cfg.follower.supports_vision = False
    cfg.save()

    reloaded = CloudraConfig(config_file=cfg_file, data_dir=tmp_path / "data")
    assert reloaded.coordinator.supports_vision is False
    assert reloaded.follower.supports_vision is False
    display = reloaded.to_display_dict()
    assert display["llm"]["coordinator"]["supports_vision"] is False
    assert display["llm"]["follower"]["supports_vision"] is False
