"""Codex account integration: presets, protected endpoints and CLI flows."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from cloudra.cli import cli
from cloudra.infra.config import LLMConfig, get_config, set_config_value
from cloudra.infra.providers import (
    apply_provider_preset,
    detect_provider_from_url,
    get_provider_preset,
    list_provider_presets,
)
from cloudra.services.api_v2.app import create_v2_app

CODEX_URL = "https://chatgpt.com/backend-api/codex"


@pytest.fixture
def fake_auth(monkeypatch):
    """Replace external device authorization, keeping config/routes/CLI real."""
    from cloudra.infra import codex_auth as auth

    state = {"authenticated": False, "polls": 0, "thread_ids": []}

    def start():
        state["thread_ids"].append(threading.get_ident())
        return {
            "login_id": "login-local-1",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://auth.openai.com/codex/device",
            "interval": 0,
            "expires_at": 9_999_999_999,
            "access_token": "must-not-escape",
        }

    def poll(login_id):
        state["thread_ids"].append(threading.get_ident())
        if login_id != "login-local-1":
            raise auth.CodexAuthError("Unknown Codex login", code="login_not_found")
        state["polls"] += 1
        state["authenticated"] = True
        return {"status": "authorized", "refresh_token": "must-not-escape"}

    def status():
        state["thread_ids"].append(threading.get_ident())
        return {
            "authenticated": state["authenticated"],
            "expires_at": 9_999_999_999 if state["authenticated"] else None,
            "account_id": "acct-test" if state["authenticated"] else None,
            "access_token": "must-not-escape",
        }

    def logout():
        state["thread_ids"].append(threading.get_ident())
        state["authenticated"] = False

    monkeypatch.setattr(auth, "start_device_login", start)
    monkeypatch.setattr(auth, "poll_device_login", poll)
    monkeypatch.setattr(auth, "codex_auth_status", status)
    monkeypatch.setattr(auth, "logout_codex", logout)
    return state


def test_codex_provider_selection_clears_old_api_key_and_keeps_model_override():
    cfg = LLMConfig(model="my-codex-model", key="old-provider-key")
    assert apply_provider_preset(cfg, "codex") is True
    assert cfg.provider == "openai-codex"
    assert cfg.url == CODEX_URL
    assert cfg.model == "my-codex-model"
    assert cfg.key == ""

    cfg.key = "explicit-key"
    assert apply_provider_preset(cfg, "openai-codex") is True
    assert cfg.key == "explicit-key", "a reload of the same provider must not clear a field"


def test_codex_provider_aliases_and_listing():
    assert get_provider_preset("openai_codex").id == "openai-codex"
    assert any(p.id == "openai-codex" for p in list_provider_presets())
    cfg = LLMConfig(key="old-key")
    apply_provider_preset(cfg, "codex")
    assert cfg.model == "gpt-6-sol"


@pytest.mark.parametrize("url", [CODEX_URL, CODEX_URL + "/"])
def test_codex_url_detection(url):
    assert detect_provider_from_url(url).id == "openai-codex"


@pytest.mark.parametrize("url", [
    "http://chatgpt.com/backend-api/codex",
    "https://chatgpt.com.evil.invalid/backend-api/codex",
    "https://chatgpt.com/backend-api/codex-evil",
    "https://evil.invalid/?url=https://chatgpt.com/backend-api/codex",
])
def test_codex_url_lookalikes_do_not_select_oauth(url):
    assert detect_provider_from_url(url) is None


def test_codex_config_selection_persists_no_unrelated_key():
    cfg = get_config()
    cfg.coordinator.key = "old-provider-key"
    set_config_value("coordinator.provider", "codex")
    assert cfg.coordinator.provider == "openai-codex"
    assert cfg.coordinator.key == ""
    assert "old-provider-key" not in cfg.config_file.read_text()


def test_codex_api_authentication_endpoints_are_protected(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "integration-secret")
    client = TestClient(create_v2_app())
    requests = [
        ("get", "/status", None),
        ("post", "/device-login", None),
        ("post", "/device-poll", {"login_id": "login-local-1"}),
        ("delete", "/auth", None),
    ]
    for method, suffix, body in requests:
        kwargs = {"json": body} if body is not None else {}
        response = getattr(client, method)("/api/v2/runtime/providers/codex" + suffix, **kwargs)
        assert response.status_code == 401


def test_codex_api_device_flow_exposes_public_fields_without_mutating_slots(fake_auth):
    cfg = get_config()
    before = cfg.coordinator.model_dump()
    client = TestClient(create_v2_app())
    base = "/api/v2/runtime/providers/codex"
    started = client.post(base + "/device-login")
    assert started.status_code == 200
    assert started.json() == {
        "login_id": "login-local-1",
        "user_code": "ABCD-EFGH",
        "verification_uri": "https://auth.openai.com/codex/device",
        "interval": 0,
        "expires_at": 9_999_999_999,
    }
    polled = client.post(base + "/device-poll", json={"login_id": "login-local-1"})
    assert polled.status_code == 200
    assert polled.json() == {"status": "authorized"}
    status = client.get(base + "/status")
    assert status.status_code == 200
    assert status.json() == {
        "authenticated": True, "expires_at": 9_999_999_999, "account_id": "acct-test",
    }
    assert cfg.coordinator.model_dump() == before
    assert "must-not-escape" not in started.text + polled.text + status.text
    assert client.delete(base + "/auth").json() == {"status": "logged_out"}
    assert client.get(base + "/status").json()["authenticated"] is False


def test_codex_api_poll_rejects_empty_and_unknown_login(fake_auth):
    client = TestClient(create_v2_app())
    endpoint = "/api/v2/runtime/providers/codex/device-poll"
    assert client.post(endpoint, json={"login_id": ""}).status_code == 422
    assert client.post(endpoint, json={"login_id": "unknown"}).status_code == 400


@pytest.mark.asyncio
async def test_codex_api_auth_work_runs_off_event_loop(fake_auth):
    from httpx import ASGITransport, AsyncClient

    loop_thread = threading.get_ident()
    app = create_v2_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v2/runtime/providers/codex/status")
    assert response.status_code == 200
    assert fake_auth["thread_ids"] and all(tid != loop_thread for tid in fake_auth["thread_ids"])


def test_codex_cli_login_status_and_logout_do_not_change_provider(fake_auth, monkeypatch):
    cfg = get_config()
    before = cfg.coordinator.model_dump()
    monkeypatch.setattr("cloudra.cli.click.launch", lambda url: None)
    runner = CliRunner()
    login = runner.invoke(cli, ["auth", "codex", "login"])
    assert login.exit_code == 0, login.output
    assert "ABCD-EFGH" in login.output
    assert "https://auth.openai.com/codex/device" in login.output
    assert fake_auth["authenticated"] is True
    status = runner.invoke(cli, ["auth", "codex", "status"])
    assert status.exit_code == 0, status.output
    assert "acct-test" in status.output
    assert "must-not-escape" not in login.output + status.output
    assert cfg.coordinator.model_dump() == before
    logout = runner.invoke(cli, ["auth", "codex", "logout"])
    assert logout.exit_code == 0, logout.output
    assert fake_auth["authenticated"] is False


def test_codex_config_init_uses_account_login_without_api_key_prompt(fake_auth, monkeypatch):
    presets = list_provider_presets()
    index = next((i for i, p in enumerate(presets, 1) if p.id == "openai-codex"), 0)
    assert index > 0
    monkeypatch.setattr("cloudra.cli.click.launch", lambda url: None)
    result = CliRunner().invoke(cli, ["config", "init"], input=f"{index}\n\n\n0\n\n\n")
    assert result.exit_code == 0, result.output
    cfg = get_config()
    assert cfg.coordinator.provider == "openai-codex"
    assert cfg.follower.provider == "openai-codex"
    assert cfg.coordinator.key == cfg.follower.key == ""
    assert "Coordinator API Key" not in result.output


def test_codex_yolo_guard_can_construct_client_without_api_key(fake_auth):
    from cloudra.infra.yolo_guard import YoloGuard

    cfg = get_config().follower
    cfg.model, cfg.url, cfg.key = "gpt-6-sol", CODEX_URL, ""
    client = YoloGuard()._client()
    assert client.base_url == CODEX_URL
    assert client.api_key == ""


def test_yolo_guard_without_api_key_rejects_codex_lookalike(fake_auth):
    from cloudra.infra.yolo_guard import YoloGuard

    cfg = get_config().follower
    cfg.model = "gpt-6-sol"
    cfg.url = "https://chatgpt.com.evil.invalid/backend-api/codex"
    cfg.key = ""
    with pytest.raises(RuntimeError):
        YoloGuard()._client()


@pytest.mark.asyncio
async def test_codex_task_description_reaches_model_without_api_key(fake_auth, monkeypatch):
    from cloudra.infra.llm_client import LLMClient, ResponseDictWrapper
    from cloudra.runtime_v2.schemas import RuntimeSettings
    from cloudra.runtime_v2.task_describer import generate_task_description

    cfg = get_config().coordinator
    cfg.model, cfg.url, cfg.key = "gpt-6-sol", CODEX_URL, ""
    agent = SimpleNamespace(role_id="coordinator", settings=RuntimeSettings())

    async def create(client, **kwargs):
        return ResponseDictWrapper({"choices": [{"message": {"content": "Summarizing mechanism"}}]})

    monkeypatch.setattr(LLMClient, "create_with_retry", create)
    result = await generate_task_description(agent, "Check the reaction pathway", language="en")
    assert result == "Summarizing mechanism"


@pytest.mark.asyncio
async def test_codex_memory_compression_reaches_model_without_api_key(fake_auth, monkeypatch):
    from cloudra.infra.llm_client import LLMClient, ResponseDictWrapper
    from cloudra.persistence.memory import MemoryManager

    cfg = get_config().follower
    cfg.model, cfg.url, cfg.key = "gpt-6-sol", CODEX_URL, ""

    async def create(client, **kwargs):
        return ResponseDictWrapper({"choices": [{"message": {"content": "Core lessons"}}]})

    monkeypatch.setattr(LLMClient, "create", create)
    result = await MemoryManager()._llm_compress("A long piece of remembered context")
    assert result == "Core lessons"


def test_codex_tagging_cli_accepts_account_endpoint_without_key(fake_auth, monkeypatch):
    cfg = get_config().coordinator
    cfg.model, cfg.url, cfg.key = "gpt-6-sol", CODEX_URL, ""
    from cloudra.knowledge import tagging

    monkeypatch.setattr(tagging, "tag_cards", lambda **kwargs: {
        "cards_total": 0, "cards_with_tags": 0,
        "from_cache": 0, "llm_batches": 0, "llm_called": 0, "seconds": 0,
        "llm_errors": [], "pending": [], "write": None,
    })
    result = CliRunner().invoke(cli, ["knowledge", "tag", "build", "--dry-run"])
    assert result.exit_code == 0, result.output
