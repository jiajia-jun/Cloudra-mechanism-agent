"""search (source=openalex)：可选 API key / 礼貌池邮箱进配置，缺省时降级。"""

import pytest

from cloudra.infra.config import _reset_for_tests, get_config, set_config_value
from cloudra.tools.Searchtool.search import Search, Search_input_schema

SAMPLE_WORKS = {
    "results": [
        {
            "display_name": "A paper",
            "doi": "https://doi.org/10.1/x",
            "publication_date": "2024-01-01",
            "abstract_inverted_index": {"hello": [0], "world": [1]},
        }
    ]
}


class FakeResponse:
    def __init__(self, json_data=None, text="", status=200):
        self._json = json_data
        self.text = text
        self.status_code = status

    def json(self):
        return self._json


class RecordingClient:
    def __init__(self, response, calls):
        self._response = response
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self._calls.append({"url": url, **kwargs})
        return self._response


def _install_client(monkeypatch, calls, json_data=SAMPLE_WORKS, status=200):
    import httpx

    response = FakeResponse(json_data=json_data, status=status)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **kw: RecordingClient(response, calls)
    )


class TestOpenAlexConfig:
    def test_save_roundtrip_openalex_api_key(self, tmp_path, monkeypatch):
        cfg = get_config()
        monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
        monkeypatch.setattr(cfg, "openalex_api_key", "")
        set_config_value("openalex_api_key", "oa-test-key")
        text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "oa-test-key" in text
        assert "openalex_api_key" in text
        assert get_config().openalex_api_key == "oa-test-key"  # 单例与磁盘一致

    def test_display_masks_openalex_api_key(self, monkeypatch):
        cfg = get_config()
        monkeypatch.setattr(cfg, "openalex_api_key", "oa-secret")
        display = cfg.to_display_dict()
        assert display["openalex_api_key"] == "***"
        assert "oa-secret" not in str(display)

    def test_display_unset_when_empty(self, monkeypatch):
        cfg = get_config()
        monkeypatch.setattr(cfg, "openalex_api_key", "")
        assert get_config().to_display_dict()["openalex_api_key"] == "(not set)"

    def test_yaml_load_openalex_api_key(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("openalex_api_key: from-yaml\n", encoding="utf-8")
        monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(cfg_path))
        monkeypatch.delenv("CLOUDRA_OPENALEX_API_KEY", raising=False)
        monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
        cfg = _reset_for_tests()
        assert cfg.openalex_api_key == "from-yaml"

    def test_openalex_env_fallback_when_yaml_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(tmp_path / "missing.yaml"))
        monkeypatch.delenv("CLOUDRA_OPENALEX_API_KEY", raising=False)
        monkeypatch.setenv("OPENALEX_API_KEY", "from-env")
        cfg = _reset_for_tests()
        assert cfg.openalex_api_key == "from-env"

    def test_save_roundtrip_openalex_mailto(self, tmp_path, monkeypatch):
        cfg = get_config()
        monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
        monkeypatch.setattr(cfg, "openalex_mailto", "")
        set_config_value("openalex_mailto", "lab@example.edu")
        text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "lab@example.edu" in text
        assert "openalex_mailto" in text
        assert get_config().openalex_mailto == "lab@example.edu"  # 单例与磁盘一致

    def test_display_shows_openalex_mailto(self, monkeypatch):
        cfg = get_config()
        monkeypatch.setattr(cfg, "openalex_mailto", "lab@example.edu")
        display = cfg.to_display_dict()
        assert display["openalex_mailto"] == "lab@example.edu"

    def test_display_mailto_unset_when_empty(self, monkeypatch):
        cfg = get_config()
        monkeypatch.setattr(cfg, "openalex_mailto", "")
        assert get_config().to_display_dict()["openalex_mailto"] == "(not set)"

    def test_yaml_load_openalex_mailto(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("openalex_mailto: yaml@example.edu\n", encoding="utf-8")
        monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(cfg_path))
        monkeypatch.delenv("CLOUDRA_OPENALEX_MAILTO", raising=False)
        monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
        cfg = _reset_for_tests()
        assert cfg.openalex_mailto == "yaml@example.edu"

    def test_openalex_mailto_env_fallback_when_yaml_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(tmp_path / "missing.yaml"))
        monkeypatch.delenv("CLOUDRA_OPENALEX_MAILTO", raising=False)
        monkeypatch.setenv("OPENALEX_MAILTO", "env@example.edu")
        cfg = _reset_for_tests()
        assert cfg.openalex_mailto == "env@example.edu"


@pytest.mark.asyncio
class TestOpenAlexAuth:
    async def test_sends_api_key_when_configured(self, mock_session, monkeypatch):
        monkeypatch.setattr(get_config(), "openalex_api_key", "oa-live-key")
        monkeypatch.setattr(get_config(), "openalex_mailto", "")
        calls = []
        _install_client(monkeypatch, calls)
        out = await Search().tool_call(
            Search_input_schema(query="dft", source="openalex"), mock_session
        )
        assert out.content[0]["title"] == "A paper"
        assert calls[0]["params"]["api_key"] == "oa-live-key"

    async def test_omits_api_key_when_unset(self, mock_session, monkeypatch):
        monkeypatch.setattr(get_config(), "openalex_api_key", "")
        monkeypatch.setattr(get_config(), "openalex_mailto", "")
        calls = []
        _install_client(monkeypatch, calls)
        out = await Search().tool_call(
            Search_input_schema(query="dft", source="openalex"), mock_session
        )
        assert out.content[0]["title"] == "A paper"
        assert "api_key" not in calls[0]["params"]

    async def test_user_agent_includes_mailto_when_configured(self, mock_session, monkeypatch):
        monkeypatch.setattr(get_config(), "openalex_api_key", "")
        monkeypatch.setattr(get_config(), "openalex_mailto", "lab@example.edu")
        calls = []
        _install_client(monkeypatch, calls)
        await Search().tool_call(
            Search_input_schema(query="dft", source="openalex"), mock_session
        )
        ua = calls[0]["headers"]["User-Agent"]
        assert "mailto:lab@example.edu" in ua
        assert ua.startswith("Cloudra/")

    async def test_user_agent_omits_mailto_when_unset(self, mock_session, monkeypatch):
        monkeypatch.setattr(get_config(), "openalex_api_key", "")
        monkeypatch.setattr(get_config(), "openalex_mailto", "")
        calls = []
        _install_client(monkeypatch, calls)
        await Search().tool_call(
            Search_input_schema(query="dft", source="openalex"), mock_session
        )
        ua = calls[0]["headers"]["User-Agent"]
        assert "mailto:" not in ua
        assert ua.startswith("Cloudra/")
