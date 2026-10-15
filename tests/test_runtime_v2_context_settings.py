"""Context-window settings keep global inheritance and explicit overrides distinct."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.adapters import LegacyLLMProvider
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2 import create_v2_app
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step


@pytest.mark.asyncio
async def test_agent_context_window_can_return_to_live_global_inheritance(tmp_path, monkeypatch):
    """An explicit window must be clearable through the same settings API."""
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg.coordinator, "context_window", 200_000)
    core = RuntimeCore(strict_events=True)
    app = create_v2_app(core)
    provider = LegacyLLMProvider()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        project = (await client.post("/api/v2/projects", json={"name": "context-settings"})).json()["data"]
        spawned = await client.post(
            f"/api/v2/projects/{project['id']}/agents",
            json={"role_id": "coordinator", "settings": {"context_window": 120_000}},
        )
        agent = core.agents[spawned.json()["data"]["id"]]
        assert provider.resolve_effective_settings(agent).context_window == 120_000

        changed = await client.patch(
            "/api/v2/runtime/config",
            json={"slot": "coordinator", "changes": {"context_window": 300_000}},
        )
        assert changed.status_code == 200
        assert provider.resolve_effective_settings(agent).context_window == 120_000

        cleared = await client.patch(
            f"/api/v2/agents/{agent.id}/settings", json={"context_window": 0}
        )
        assert cleared.status_code == 200
        assert agent.settings.context_window == 0
        assert provider.resolve_effective_settings(agent).context_window == 300_000

        await client.patch(
            "/api/v2/runtime/config",
            json={"slot": "coordinator", "changes": {"context_window": 400_000}},
        )
        assert provider.resolve_effective_settings(agent).context_window == 400_000


@pytest.mark.asyncio
async def test_project_context_default_applies_to_new_agents_without_rewriting_existing_ones():
    core = RuntimeCore(strict_events=True)
    app = create_v2_app(core)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        project = (await client.post(
            "/api/v2/projects",
            json={"name": "context-defaults", "settings": {"defaults": {"context_window": 160_000}}},
        )).json()["data"]
        first = (await client.post(
            f"/api/v2/projects/{project['id']}/agents", json={"role_id": "coordinator"}
        )).json()["data"]
        assert first["settings"]["context_window"] == 160_000

        changed = await client.patch(
            f"/api/v2/projects/{project['id']}",
            json={"settings": {"defaults": {"context_window": 240_000}}},
        )
        assert changed.status_code == 200
        second = (await client.post(
            f"/api/v2/projects/{project['id']}/agents", json={"role_id": "coordinator"}
        )).json()["data"]
        assert core.agents[first["id"]].settings.context_window == 160_000
        assert second["settings"]["context_window"] == 240_000

        await client.patch(
            f"/api/v2/projects/{project['id']}",
            json={"settings": {"defaults": {"context_window": 0}}},
        )
        third = (await client.post(
            f"/api/v2/projects/{project['id']}/agents", json={"role_id": "coordinator"}
        )).json()["data"]
        assert third["settings"]["context_window"] == 0
        assert core.agents[first["id"]].settings.context_window == 160_000


@pytest.mark.asyncio
async def test_global_context_window_change_compacts_existing_inheriting_agent_before_send(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config
    from cloudra.runtime_v2.compaction import context_over_budget

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg.coordinator, "context_window", 12_000)
    provider = ScriptedProvider(default=[Step(stop=True)])
    monkeypatch.setattr(
        provider, "resolve_effective_settings", LegacyLLMProvider().resolve_effective_settings,
        raising=False,
    )

    async def summarize(agent, messages, **kwargs):
        return await provider.summarize(messages)

    monkeypatch.setattr("cloudra.runtime_v2.compaction.summarize_with_agent_settings", summarize)
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        agent = (await harness.bus.execute(Command(
            type="agent.spawn", target={"project_id": harness.project.id},
            payload={"role_id": "coordinator", "settings": {
                "model": "budget-test", "max_tokens": 256, "invocation_protocol": "traditional",
            }},
        ))).data
        history = [{"role": "assistant", "content": "previous " * 4000}]
        await harness.core.contexts.append_output(agent=agent, run_id="old-run", messages=history)
        assert agent.settings.context_window == 0
        assert not context_over_budget(history, context_window=12_000, max_output=256)

        app = create_v2_app(harness.core)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            changed = await client.patch(
                "/api/v2/runtime/config",
                json={"slot": "coordinator", "changes": {"context_window": 4000}},
            )
        assert changed.status_code == 200
        assert provider.resolve_effective_settings(agent).context_window == 4000
        assert agent.settings.context_window == 0

        current_request = "Continue with the current instruction."
        await harness.bus.execute(Command(
            type="agent.message", target={"session_id": agent.id},
            payload={"content": current_request},
        ))
        await harness.wait_terminal(agent)
        assert agent.state.value == "succeeded", harness.describe(agent)
        types = harness.types(agent)
        assert types.index("context.compacted") < types.index("llm.request_started")
        assert sum(m.get("content") == current_request for m in provider.calls[0][1]) == 1
    finally:
        await harness.aclose()
