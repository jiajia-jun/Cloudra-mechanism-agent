"""通用网页搜索设置：YAML、环境变量与脱敏显示使用同一配置。"""

import pytest
import yaml

from cloudra.infra.config import CloudraConfig, get_config, set_config_value


def test_search_defaults_and_display(tmp_path):
    cfg = CloudraConfig(config_file=tmp_path / "absent.yaml", data_dir=tmp_path / "data")

    assert cfg.search_provider == "deepseek"
    assert cfg.deepseek_api_key == ""
    assert cfg.to_display_dict()["search_provider"] == "deepseek"
    assert cfg.to_display_dict()["deepseek_api_key"] == "(not set)"


def test_search_config_reads_standard_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDRA_SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("CLOUDRA_DEEPSEEK_API_KEY", "environment-secret")

    cfg = CloudraConfig(config_file=tmp_path / "absent.yaml", data_dir=tmp_path / "data")

    assert cfg.search_provider == "brave"
    assert cfg.deepseek_api_key == "environment-secret"


def test_search_yaml_overrides_environment_and_masks_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDRA_SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("CLOUDRA_DEEPSEEK_API_KEY", "environment-secret")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("search_provider: deepseek\ndeepseek_api_key: yaml-secret\n")

    cfg = CloudraConfig(config_file=config_file, data_dir=tmp_path / "data")

    assert cfg.search_provider == "deepseek"
    assert cfg.deepseek_api_key == "yaml-secret"
    assert cfg.to_display_dict()["deepseek_api_key"] == "***"


def test_search_config_set_round_trip_and_clear(tmp_path, monkeypatch):
    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    set_config_value("search_provider", "tavily")
    set_config_value("deepseek_api_key", "search-secret")

    saved = yaml.safe_load(cfg.config_file.read_text())
    assert saved["search_provider"] == "tavily"
    assert saved["deepseek_api_key"] == "search-secret"
    reloaded = CloudraConfig(config_file=cfg.config_file, data_dir=tmp_path / "data")
    assert reloaded.search_provider == "tavily"
    assert reloaded.deepseek_api_key == "search-secret"

    set_config_value("deepseek_api_key", "")

    assert cfg.deepseek_api_key == ""
    assert yaml.safe_load(cfg.config_file.read_text())["deepseek_api_key"] == ""


def test_search_yaml_rejects_unknown_provider(tmp_path):
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("search_provider: unknown\n")

    with pytest.raises(ValueError, match="search_provider"):
        CloudraConfig(config_file=config_file, data_dir=tmp_path / "data")
