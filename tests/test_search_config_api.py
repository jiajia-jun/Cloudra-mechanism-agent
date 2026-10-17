"""Search/Fetch settings use the existing config writer without exposing keys."""

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from cloudra.services.api_v2 import create_v2_app


@pytest.mark.asyncio
async def test_search_config_api_updates_provider_and_preserves_write_only_key(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    async with AsyncClient(transport=ASGITransport(app=create_v2_app()), base_url="http://testserver") as client:
        initial = await client.get("/api/v2/runtime/config")
        assert initial.json()["search_provider"] == "deepseek"
        assert initial.json()["deepseek_api_key_set"] is False

        updated = await client.patch("/api/v2/runtime/config/search", json={
            "search_provider": "deepseek", "deepseek_api_key": "search-fetch-secret",
        })
        assert updated.status_code == 200
        assert updated.json()["deepseek_api_key_set"] is True
        assert "search-fetch-secret" not in updated.text
        assert yaml.safe_load(cfg.config_file.read_text())["deepseek_api_key"] == "search-fetch-secret"

        preserved = await client.patch("/api/v2/runtime/config/search", json={"search_provider": "auto"})
        assert preserved.status_code == 200
        assert preserved.json()["search_provider"] == "auto"
        assert cfg.deepseek_api_key == "search-fetch-secret"
        loaded = await client.get("/api/v2/runtime/config")
        assert "search-fetch-secret" not in loaded.text
        assert "deepseek_api_key" not in loaded.json()

        saved = cfg.config_file.read_text()
        invalid = await client.patch("/api/v2/runtime/config/search", json={"search_provider": "unsupported"})
        assert invalid.status_code == 422
        assert cfg.config_file.read_text() == saved

        cleared = await client.patch("/api/v2/runtime/config/search", json={"deepseek_api_key": ""})
        assert cleared.status_code == 200
        assert cleared.json()["search_provider"] == "auto"
        assert cleared.json()["deepseek_api_key_set"] is False
        assert cfg.deepseek_api_key == ""
