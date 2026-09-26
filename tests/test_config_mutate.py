"""mutate_config 单一写入口：磁盘 YAML 是唯一事实源，内存单例只是其缓存。

旧实现（整文件内存快照重写 + plugins 磁盘优先合并 hack）下：
- 两个进程/线程并发写会互相抹键（后写者用旧快照覆盖先写者）；
- save() 永远无法删除 plugins 条目。
本文件是这两类竞态被根治后的常驻守卫。
"""

from __future__ import annotations

import threading
import time

import pytest
import yaml


def _read_yaml(cfg_path) -> dict:
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


@pytest.fixture
def cfg_env(tmp_path, monkeypatch):
    """把全局单例的 config_file 指到本测试临时文件，plugins 清空。"""
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg, "plugins", [])
    return cfg


def test_mutate_persists_and_refreshes_singleton(cfg_env, monkeypatch):
    """经 mutate 改 coordinator.model 后，磁盘 YAML 与 get_config() 单例一致。"""
    from cloudra.infra.config import get_config, mutate_config

    monkeypatch.setattr(cfg_env.coordinator, "model", "pre-mutate")  # teardown 复位
    mutate_config(lambda work: setattr(work.coordinator, "model", "mutated-model"))

    assert _read_yaml(cfg_env.config_file)["llm"]["coordinator"]["model"] == "mutated-model"
    assert get_config().coordinator.model == "mutated-model"


def test_mutate_empty_string_clears_value(cfg_env, monkeypatch):
    """key 清空（""）经 mutate 同样生效：磁盘与单例都回到空。"""
    from cloudra.infra.config import get_config, mutate_config

    monkeypatch.setattr(cfg_env.coordinator, "key", "to-be-cleared")  # teardown 复位
    mutate_config(lambda work: setattr(work.coordinator, "key", ""))

    assert _read_yaml(cfg_env.config_file)["llm"]["coordinator"]["key"] == ""
    assert get_config().coordinator.key == ""


def test_mutate_fn_error_leaves_disk_untouched(cfg_env):
    """fn 抛错时不写盘、不动单例。"""
    from cloudra.infra.config import mutate_config

    def _boom(work):
        work.coordinator.model = "should-not-persist"
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        mutate_config(_boom)

    assert not cfg_env.config_file.exists()


def test_concurrent_mutations_do_not_lose_updates(cfg_env, monkeypatch):
    """两个线程同时 mutate 不同键：flock 串行化读-改-写，最终磁盘两个键都是最新值。"""
    from cloudra.infra.config import get_config, mutate_config

    monkeypatch.setattr(cfg_env.coordinator, "model", "pre")  # teardown 复位
    monkeypatch.setattr(cfg_env.email, "user", "pre")

    rounds = 10
    barrier = threading.Barrier(2)
    errors = []

    def _write_model(work, i):
        time.sleep(0.005)  # 驻留临界区，放大旧实现的交错窗口
        work.coordinator.model = f"model-{i}"

    def _write_email(work, i):
        time.sleep(0.005)
        work.email.user = f"user-{i}@example.edu"

    def run(fn):
        try:
            barrier.wait(timeout=10)
            for i in range(rounds):
                mutate_config(lambda work, i=i: fn(work, i))
        except Exception as exc:  # pragma: no cover - 收集后统一断言
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(fn,)) for fn in (_write_model, _write_email)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors
    data = _read_yaml(cfg_env.config_file)
    assert data["llm"]["coordinator"]["model"] == f"model-{rounds - 1}"
    assert data["email"]["user"] == f"user-{rounds - 1}@example.edu"
    cfg = get_config()
    assert cfg.coordinator.model == f"model-{rounds - 1}"
    assert cfg.email.user == f"user-{rounds - 1}@example.edu"


def test_reasoning_effort_yaml_round_trip(cfg_env, monkeypatch, tmp_path):
    """reasoning_effort 经 mutate 落盘后可从 YAML 原样读回，且出现在
    to_display_dict 手抄清单里；默认 None 即"不传"。"""
    from cloudra.infra.config import CloudraConfig, get_config, mutate_config

    monkeypatch.setattr(cfg_env.coordinator, "reasoning_effort", None)  # teardown 复位
    assert cfg_env.coordinator.reasoning_effort is None

    mutate_config(lambda work: setattr(work.coordinator, "reasoning_effort", "high"))

    assert _read_yaml(cfg_env.config_file)["llm"]["coordinator"]["reasoning_effort"] == "high"
    assert get_config().coordinator.reasoning_effort == "high"

    # 磁盘是事实源：从 YAML 重建的实例同样读到 high
    reloaded = CloudraConfig(config_file=cfg_env.config_file, data_dir=tmp_path / "data")
    assert reloaded.coordinator.reasoning_effort == "high"
    display = reloaded.to_display_dict()
    assert display["llm"]["coordinator"]["reasoning_effort"] == "high"
    assert display["llm"]["follower"]["reasoning_effort"] is None


def test_compute_allow_local_calculator_yaml_round_trip(cfg_env, tmp_path):
    """compute.allow_local_calculator 默认关；经 mutate 落盘后从 YAML 原样读回。"""
    from cloudra.infra.config import CloudraConfig, get_config, mutate_config

    assert get_config().compute.allow_local_calculator is False

    mutate_config(lambda work: setattr(work.compute, "allow_local_calculator", True))

    assert _read_yaml(cfg_env.config_file)["compute"]["allow_local_calculator"] is True
    reloaded = CloudraConfig(config_file=cfg_env.config_file, data_dir=tmp_path / "data")
    assert reloaded.compute.allow_local_calculator is True


def test_add_plugin_idempotent(cfg_env):
    from cloudra.infra.config import add_plugin, get_config

    assert add_plugin("pkg.mod:plugin") is True
    assert add_plugin("pkg.mod:plugin") is False  # 幂等：不重复追加

    assert _read_yaml(cfg_env.config_file)["plugins"] == ["pkg.mod:plugin"]
    assert get_config().plugins == ["pkg.mod:plugin"]


def test_remove_plugin_roundtrip(cfg_env):
    """add→磁盘有→remove→磁盘无→再 remove 幂等不炸。"""
    from cloudra.infra.config import add_plugin, get_config, remove_plugin

    assert add_plugin("pkg.mod:plugin") is True
    assert remove_plugin("pkg.mod:plugin") is True
    assert _read_yaml(cfg_env.config_file).get("plugins", []) == []
    assert get_config().plugins == []
    assert remove_plugin("pkg.mod:plugin") is False  # 幂等：不存在不炸

    # 删完还能再装
    assert add_plugin("pkg.mod:plugin") is True
    assert _read_yaml(cfg_env.config_file)["plugins"] == ["pkg.mod:plugin"]


def test_knowledge_install_uninstall_roundtrip(cfg_env):
    """knowledge install/uninstall 经插件 API 幂等改写磁盘。"""
    from cloudra.knowledge.installer import (
        PLUGIN_SPEC,
        install_plugin_spec,
        uninstall_plugin_spec,
    )

    cfg_path, added = install_plugin_spec()
    assert added is True
    assert PLUGIN_SPEC in _read_yaml(cfg_path).get("plugins", [])

    _, added_again = install_plugin_spec()
    assert added_again is False
    assert _read_yaml(cfg_path)["plugins"].count(PLUGIN_SPEC) == 1

    _, removed = uninstall_plugin_spec()
    assert removed is True
    assert PLUGIN_SPEC not in _read_yaml(cfg_path).get("plugins", [])

    _, removed_again = uninstall_plugin_spec()
    assert removed_again is False


def test_method_policy_yaml_round_trip(cfg_env, tmp_path):
    """method_policy 四档默认 xtb+pm7+b3lyp/def2svp；
    经 mutate 落盘后从 YAML 原样读回。"""
    from cloudra.infra.config import CloudraConfig, get_config, mutate_config

    assert get_config().method_policy.allowed_methods == ["xtb", "pm7", "b3lyp/def2svp"]
    assert get_config().method_policy.allowed_methods_impossible == ["xtb", "pm7", "b3lyp/def2svp"]

    mutate_config(lambda work: setattr(work.method_policy, "allowed_methods", ["xtb"]))

    assert _read_yaml(cfg_env.config_file)["method_policy"]["allowed_methods"] == ["xtb"]
    reloaded = CloudraConfig(config_file=cfg_env.config_file, data_dir=tmp_path / "data")
    assert reloaded.method_policy.allowed_methods == ["xtb"]
    assert reloaded.method_policy.allowed_methods_impossible == ["xtb", "pm7", "b3lyp/def2svp"]
