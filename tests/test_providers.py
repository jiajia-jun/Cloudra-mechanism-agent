import pytest
from click.testing import CliRunner

from cloudra.cli import cli
from cloudra.infra.config import LLMConfig, get_config, set_config_value
from cloudra.infra.llm_client import _default_headers_for_url
from cloudra.infra.providers import (
    apply_provider_preset,
    detect_provider_from_url,
    get_provider_preset,
    list_provider_presets,
)


def test_list_provider_presets():
    presets = list_provider_presets()
    ids = {p.id for p in presets}
    expected = {
        "openrouter",
        "opencode_go",
        "deepseek",
        "openai",
        "gemini",
        "dashscope",
        "siliconflow",
        "moonshot",
        "kimi_coding",
        "zhipu",
        "minimax",
        "ollama",
        "custom",
    }
    assert expected.issubset(ids)


def test_get_provider_preset_aliases():
    assert get_provider_preset("openrouter").id == "openrouter"
    assert get_provider_preset("opencode_go").id == "opencode_go"
    assert get_provider_preset("opencode").id == "opencode_go"
    assert get_provider_preset("opencode-go").id == "opencode_go"
    assert get_provider_preset("qwen").id == "dashscope"
    assert get_provider_preset("kimi").id == "moonshot"
    assert get_provider_preset("kimi_coding").id == "kimi_coding"
    assert get_provider_preset("codingplan").id == "kimi_coding"
    assert get_provider_preset("kimi-coding").id == "kimi_coding"
    assert get_provider_preset("glm").id == "zhipu"
    assert get_provider_preset("minimax").id == "minimax"
    assert get_provider_preset("nonexistent") is None


def test_detect_provider_from_url():
    assert detect_provider_from_url("https://openrouter.ai/api/v1").id == "openrouter"
    assert detect_provider_from_url("https://opencode.ai/zen/go/v1").id == "opencode_go"
    assert detect_provider_from_url("https://api.deepseek.com/").id == "deepseek"
    assert detect_provider_from_url("https://api.openai.com/v1").id == "openai"
    assert detect_provider_from_url("https://dashscope.aliyuncs.com/compatible-mode/v1").id == "dashscope"
    assert detect_provider_from_url("https://api.siliconflow.cn/v1").id == "siliconflow"
    assert detect_provider_from_url("https://api.moonshot.cn/v1").id == "moonshot"
    assert detect_provider_from_url("https://api.kimi.com/coding/v1").id == "kimi_coding"
    assert detect_provider_from_url("http://localhost:11434/v1").id == "ollama"
    assert detect_provider_from_url("https://unknown-proxy.com/v1") is None


def test_apply_provider_preset():
    cfg = LLMConfig()
    ok = apply_provider_preset(cfg, "openrouter")
    assert ok is True
    assert cfg.provider == "openrouter"
    assert cfg.url == "https://openrouter.ai/api/v1"
    assert cfg.model == "anthropic/claude-sonnet-5"
    assert cfg.context_window == 1000000
    assert cfg.native_search == "openrouter"

    # Testing opencode_go
    ok2 = apply_provider_preset(cfg, "opencode_go", overwrite_model=True)
    assert ok2 is True
    assert cfg.provider == "opencode_go"
    assert cfg.url == "https://opencode.ai/zen/go/v1"
    assert cfg.model == "deepseek-v4-pro"

    # Testing kimi_coding
    ok3 = apply_provider_preset(cfg, "kimi_coding", overwrite_model=True)
    assert ok3 is True
    assert cfg.provider == "kimi_coding"
    assert cfg.url == "https://api.kimi.com/coding/v1"
    assert cfg.model == "kimi-for-coding"


def test_headers_requirement():
    # OpenRouter headers
    or_headers = _default_headers_for_url("https://openrouter.ai/api/v1")
    assert "HTTP-Referer" in or_headers
    assert "X-Title" in or_headers
    assert or_headers["X-Title"] == "Cloudra"

    # Kimi Coding Plan headers (whitelisted agent User-Agent required)
    kc_headers = _default_headers_for_url("https://api.kimi.com/coding/v1")
    assert "User-Agent" in kc_headers
    assert kc_headers["User-Agent"] == "Roo-Code/3.45.0"

    normal_headers = _default_headers_for_url("https://api.openai.com/v1")
    assert normal_headers == {}


def test_set_config_value_provider(monkeypatch, tmp_path):
    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")

    set_config_value("coordinator.provider", "openrouter")
    assert cfg.coordinator.provider == "openrouter"
    assert cfg.coordinator.url == "https://openrouter.ai/api/v1"
    assert cfg.coordinator.model == "anthropic/claude-sonnet-5"

    display = cfg.to_display_dict()
    assert display["llm"]["coordinator"]["provider"] == "openrouter"


def test_cli_config_show_includes_provider():
    result = CliRunner().invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "供应商" in result.output


@pytest.mark.asyncio
async def test_runtime_providers_endpoint():
    from httpx import ASGITransport, AsyncClient

    from cloudra.services.api_v2.app import create_v2_app

    app = create_v2_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v2/runtime/providers")
        assert resp.status_code == 200
        providers = resp.json()
        ids = {p["id"] for p in providers}
        assert "openrouter" in ids
        assert "opencode_go" in ids

        config_resp = await client.get("/api/v2/runtime/config")
        assert config_resp.status_code == 200
        assert "provider" in config_resp.json()["coordinator"]

        patch_resp = await client.patch(
            "/api/v2/runtime/config",
            json={"slot": "coordinator", "changes": {"provider": "openrouter"}},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["coordinator"]["provider"] == "openrouter"
        assert patch_resp.json()["coordinator"]["url"] == "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
async def test_openrouter_pkce_and_callback_endpoints(monkeypatch):
    import urllib.request

    from httpx import ASGITransport, AsyncClient

    from cloudra.infra.providers import (
        generate_pkce_pair,
        get_openrouter_auth_url,
        run_local_auth_listener,
    )
    from cloudra.services.api_v2.app import create_v2_app

    # 1. Test generate_pkce_pair and get_openrouter_auth_url
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    auth_url, v, c = get_openrouter_auth_url("http://127.0.0.1:8000/cb")
    assert "https://openrouter.ai/auth?" in auth_url
    assert "code_challenge=" in auth_url
    assert "callback_url=" in auth_url

    # 2. Test local auth listener
    cb_url, wait_fn = run_local_auth_listener(timeout=5.0)
    assert cb_url.startswith("http://127.0.0.1:")
    # Simulate browser redirecting to cb_url
    req = urllib.request.Request(f"{cb_url}?code=test_local_code_123")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "OpenRouter 授权成功" in content
    captured = wait_fn(2.0)
    assert captured == "test_local_code_123"

    # 3. Test API endpoints
    app = create_v2_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # GET PKCE
        pkce_resp = await client.get("/api/v2/runtime/providers/openrouter/pkce")
        assert pkce_resp.status_code == 200
        pkce_data = pkce_resp.json()
        assert "auth_url" in pkce_data
        assert "code_verifier" in pkce_data

        # GET Callback
        cb_resp = await client.get("/api/v2/runtime/providers/openrouter/callback?code=mock_code_abc")
        assert cb_resp.status_code == 200
        assert "text/html" in cb_resp.headers["content-type"]
        assert "mock_code_abc" in cb_resp.text
        assert "postMessage" in cb_resp.text

        # Mock exchange_openrouter_code for code-exchange
        monkeypatch.setattr(
            "cloudra.infra.providers.exchange_openrouter_code",
            lambda code, verifier: "sk-or-v1-mock-exchanged-key-999",
        )

        ex_resp = await client.post(
            "/api/v2/runtime/providers/openrouter/code-exchange",
            json={
                "code": "mock_code_abc",
                "code_verifier": pkce_data["code_verifier"],
                "slot": "coordinator",
            },
        )
        assert ex_resp.status_code == 200
        ex_data = ex_resp.json()
        assert ex_data["key"] == "sk-or-v1-mock-exchanged-key-999"
        assert ex_data["saved"] is True

        # Verify coordinator key in runtime config
        cfg_resp = await client.get("/api/v2/runtime/config")
        assert cfg_resp.json()["coordinator"]["key_set"] is True
        assert get_config().coordinator.key == "sk-or-v1-mock-exchanged-key-999"

