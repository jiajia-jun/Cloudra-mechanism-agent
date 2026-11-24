"""Regression tests for GH #305: cross-provider model switching and config sync."""

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
async def test_patch_runtime_config_sync_existing_agents_clears_stale_provider_overrides(
    tmp_path, monkeypatch
):
    """Saving global slot with sync_existing_agents clears stale LLM overrides in that slot."""
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg.coordinator, "provider", "deepseek")
    monkeypatch.setattr(cfg.coordinator, "model", "deepseek-v4-flash")
    monkeypatch.setattr(cfg.coordinator, "url", "https://api.deepseek.com")
    monkeypatch.setattr(cfg.coordinator, "key", "sk-deepseek-old")
    monkeypatch.setattr(cfg.coordinator, "context_window", 128_000)
    monkeypatch.setattr(cfg.follower, "provider", "deepseek")
    monkeypatch.setattr(cfg.follower, "model", "deepseek-chat")
    monkeypatch.setattr(cfg.follower, "url", "https://api.deepseek.com")
    monkeypatch.setattr(cfg.follower, "key", "sk-deepseek-follower")

    core = RuntimeCore(strict_events=True)
    app = create_v2_app(core)
    provider = LegacyLLMProvider()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        project = (
            await client.post(
                "/api/v2/projects",
                json={
                    "name": "provider-switch",
                    "settings": {
                        "defaults": {
                            "model": "deepseek-v4-flash",
                            "base_url": "https://api.deepseek.com",
                            "yolo": True,
                        }
                    },
                },
            )
        ).json()["data"]
        coord_id = (
            await client.post(
                f"/api/v2/projects/{project['id']}/agents",
                json={
                    "role_id": "coordinator",
                    "settings": {
                        "model": "deepseek-v4-pro",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-agent-override",
                        "context_window": 120_000,
                        "yolo": True,
                    },
                },
            )
        ).json()["data"]["id"]
        follower_id = (
            await client.post(
                f"/api/v2/projects/{project['id']}/agents",
                json={
                    "role_id": "researcher",
                    "settings": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com"},
                },
            )
        ).json()["data"]["id"]

        resp = await client.patch(
            "/api/v2/runtime/config",
            json={
                "slot": "coordinator",
                "sync_existing_agents": True,
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
        body = resp.json()
        assert body["synced_agents"] == 1
        assert body["coordinator"]["model"] == "glm-5.3"
        assert core.runtime_defaults.model == "glm-5.3"
        assert core.runtime_defaults.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"

        coord = core.agents[coord_id]
        assert coord.settings.model == ""
        assert coord.settings.base_url == ""
        assert coord.settings.api_key_set is False
        assert coord.settings.context_window == 0
        assert coord.settings.yolo is True

        effective = provider.resolve_effective_settings(coord)
        assert effective.model == "glm-5.3"
        assert effective.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
        assert effective.api_key == "zhipu-key-new"
        assert effective.context_window == 500_000

        # Follower slot agent must remain untouched when syncing coordinator slot.
        follower = core.agents[follower_id]
        assert follower.settings.model == "deepseek-chat"
        assert follower.settings.base_url == "https://api.deepseek.com"

        # Project defaults must clear stale model/base_url while preserving unrelated flags.
        updated_project = core.projects[project["id"]]
        assert updated_project.settings.defaults.model is None
        assert updated_project.settings.defaults.base_url is None
        assert updated_project.settings.defaults.yolo is True

        # Newly spawned coordinator in the same project inherits the new global config.
        fresh_id = (
            await client.post(
                f"/api/v2/projects/{project['id']}/agents",
                json={"role_id": "coordinator"},
            )
        ).json()["data"]["id"]
        fresh_effective = provider.resolve_effective_settings(core.agents[fresh_id])
        assert fresh_effective.model == "glm-5.3"
        assert fresh_effective.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
        assert fresh_effective.api_key == "zhipu-key-new"


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
