import pytest
from click.testing import CliRunner

from cloudra.cli import cli
from cloudra.infra.config import get_config, resolve_config_attr


@pytest.mark.parametrize(
    ("key", "secret"),
    [
        ("coordinator.key", "coordinator-secret"),
        ("follower.key", "follower-secret"),
        ("openalex_api_key", "openalex-secret"),
        ("deepseek_api_key", "deepseek-search-secret"),
        ("email.password", "email-secret"),
    ],
)
def test_config_set_masks_sensitive_values(key, secret):
    result = CliRunner().invoke(cli, ["config", "set", key, secret])

    assert result.exit_code == 0
    assert secret not in result.output
    assert f"已设置 {key} = ***" in result.output
    target, final_key = resolve_config_attr(get_config(), key)
    assert getattr(target, final_key) == secret


def test_config_set_still_displays_non_sensitive_values():
    result = CliRunner().invoke(cli, ["config", "set", "coordinator.model", "test-model"])

    assert result.exit_code == 0
    assert "已设置 coordinator.model = test-model" in result.output


def test_config_get_masks_passwords():
    get_config().email.password = "email-secret"

    result = CliRunner().invoke(cli, ["config", "get", "email.password"])

    assert result.exit_code == 0
    assert "email-secret" not in result.output
    assert "***" in result.output


def test_config_get_masks_deepseek_search_key():
    get_config().deepseek_api_key = "deepseek-search-secret"

    result = CliRunner().invoke(cli, ["config", "get", "deepseek_api_key"])

    assert result.exit_code == 0
    assert "deepseek-search-secret" not in result.output


def test_mcp_connection_credentials_are_hidden_on_get_and_set():
    import json

    connection = json.dumps({"lab": {"url": "https://example.org/mcp?token=private-url",
        "headers": {"Authorization": "Bearer private-header"}}})
    runner = CliRunner()
    for command in (["config", "set", "mcp_servers", connection], ["config", "get", "mcp_servers"]):
        result = runner.invoke(cli, command)
        assert result.exit_code == 0, result.output
        assert "private-url" not in result.output
        assert "private-header" not in result.output
        assert "***" in result.output
    assert "***" in result.output


def test_config_set_search_provider():
    result = CliRunner().invoke(cli, ["config", "set", "search_provider", "duckduckgo"])

    assert result.exit_code == 0
    assert get_config().search_provider == "duckduckgo"


def test_config_set_rejects_unknown_search_provider():
    result = CliRunner().invoke(cli, ["config", "set", "search_provider", "unknown"])

    assert result.exit_code == 1
    assert get_config().search_provider == "deepseek"
