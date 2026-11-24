"""Regression tests for GH #305: cross-provider model switching and startup restore."""

from __future__ import annotations

import json
import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.adapters import LegacyLLMProvider
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import RuntimeSettings
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.api_v2.app import _build_default_v2_app


@pytest.mark.asyncio
async def test_patch_runtime_config_preserves_explicit_agent_overrides_and_refreshes_runtime_defaults(
    tmp_path, monkeypatch
):
    """Global slot save refreshes runtime_defaults without silently overwriting existing agents."""
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg.coordinator, "provider", "deepseek")
    monkeypatch.setattr(cfg.coordinator, "model", "deepseek-v4-flash")
    monkeypatch.setattr(cfg.coordinator, "url", "https://api.deepseek.com")
    monkeypatch.setattr(cfg.coordinator, "key", "sk-deepseek-old")
    monkeypatch.setattr(cfg.coordinator, "context_window", 128_000)

    core = RuntimeCore(strict_events=True)
    app = create_v2_app(core)
    provider = LegacyLLMProvider()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        project = (
            await client.post("/api/v2/projects", json={"name": "provider-switch"})
        ).json()["data"]
        # Agent A: inheriting global slot completely
        inheriting_id = (
            await client.post(
                f"/api/v2/projects/{project['id']}/agents",
                json={"role_id": "coordinator"},
            )
        ).json()["data"]["id"]
        # Agent B: explicit per-agent override
        custom_id = (
            await client.post(
                f"/api/v2/projects/{project['id']}/agents",
                json={
                    "role_id": "coordinator",
                    "settings": {
                        "model": "deepseek-v4-pro",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-agent-override",
                    },
                },
            )
        ).json()["data"]["id"]

        resp = await client.patch(
            "/api/v2/runtime/config",
            json={
                "slot": "coordinator",
                "changes": {
                    "provider": "zhipu",
                    "model": "glm-5.3",
                    "url": "https://open.bigmodel.cn/api/coding/paas/v4",
                    "key": "zhipu-key-new",
                    "context_window": 500_000,
                },
            },
        )
        assert resp.status_code == 200
        assert core.runtime_defaults.model == "glm-5.3"
        assert core.runtime_defaults.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"

        # Inheriting agent immediately uses the new global slot.
        inh_effective = provider.resolve_effective_settings(core.agents[inheriting_id])
        assert inh_effective.model == "glm-5.3"
        assert inh_effective.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
        assert inh_effective.api_key == "zhipu-key-new"

        # Agent with explicit override stays untouched until user explicitly changes it.
        custom_effective = provider.resolve_effective_settings(core.agents[custom_id])
        assert custom_effective.model == "deepseek-v4-pro"
        assert custom_effective.base_url == "https://api.deepseek.com"
        assert custom_effective.api_key == "sk-agent-override"

        # User can clear per-agent override via PATCH /agents/{id}/settings to inherit new global.
        cleared = await client.patch(
            f"/api/v2/agents/{custom_id}/settings",
            json={"model": "", "base_url": "", "api_key": "", "context_window": 0},
        )
        assert cleared.status_code == 200
        after_clear = provider.resolve_effective_settings(core.agents[custom_id])
        assert after_clear.model == "glm-5.3"
        assert after_clear.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
        assert after_clear.api_key == "zhipu-key-new"


def test_startup_restore_keeps_config_yaml_over_stale_snapshot_runtime_defaults(
    tmp_path, monkeypatch
):
    """Startup must prefer config.yaml over stale snapshot runtime_defaults and tolerate null api_key."""
    from cloudra.infra.config import get_config

    store_path = tmp_path / "runtime.db"
    store = RuntimeStore(store_path)
    store.save_snapshot(
        projects={},
        agents={},
        roles={},
        runtime_defaults=RuntimeSettings(
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            context_window=128_000,
        ),
        last_seqs={},
    )
    # Simulate a snapshot whose runtime_defaults contains an explicit null api_key.
    with sqlite3.connect(store_path) as conn:
        row = conn.execute(
            "SELECT data FROM objects WHERE kind = 'snapshot' AND obj_id = 'state'"
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["runtime_defaults"]["api_key"] = None
        conn.execute(
            "UPDATE objects SET data = ? WHERE kind = 'snapshot' AND obj_id = 'state'",
            (json.dumps(payload),),
        )
        conn.commit()

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg.coordinator, "model", "glm-5.3")
    monkeypatch.setattr(cfg.coordinator, "url", "https://open.bigmodel.cn/api/coding/paas/v4")
    monkeypatch.setattr(cfg.coordinator, "key", "zhipu-key")
    monkeypatch.setattr(cfg.coordinator, "context_window", 500_000)

    app = _build_default_v2_app(store_path=str(store_path))
    core = app.state.runtime_core
    assert core.runtime_defaults.model == "glm-5.3"
    assert core.runtime_defaults.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert core.runtime_defaults.context_window == 500_000
