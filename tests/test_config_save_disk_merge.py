"""config.save() 的 plugins 磁盘优先合并 + knowledge install 幂等。"""

from __future__ import annotations

import yaml

from cloudra.knowledge.installer import PLUGIN_SPEC, install_plugin_spec


def _read_plugins(cfg_path) -> list:
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return data.get("plugins") or []


def test_save_preserves_disk_plugins(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config

    cfg = get_config()
    # config 单例可能诞生于其他测试的 tmp——显式指到本测试的临时文件。
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")

    cfg_path, added = install_plugin_spec()
    assert added is True
    assert str(cfg_path).startswith(str(tmp_path))
    assert PLUGIN_SPEC in _read_plugins(cfg_path)

    # 模拟运行中服务：内存里没有 plugins（旧快照），改 llm 后 save()。
    cfg.plugins = []
    cfg.coordinator.model = "test-model-xyz"
    cfg.save()

    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    assert data["llm"]["coordinator"]["model"] == "test-model-xyz"
    assert PLUGIN_SPEC in data.get("plugins") or []  # 磁盘 plugins 存活


def test_save_in_memory_plugins_when_no_disk_value(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    cfg_path = cfg.config_file
    if cfg_path.exists():
        cfg_path.unlink()  # 干净盘
    cfg.plugins = ["some.other:plugin"]
    cfg.save()
    assert _read_plugins(cfg_path) == ["some.other:plugin"]


def test_install_idempotent(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config

    monkeypatch.setattr(get_config(), "config_file", tmp_path / "config.yaml")
    path1, added1 = install_plugin_spec()
    path2, added2 = install_plugin_spec()
    assert added1 is True
    assert added2 is False  # 幂等：不重复追加
    assert path1 == path2
    assert _read_plugins(path1).count(PLUGIN_SPEC) == 1
