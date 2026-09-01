"""激活/停用 chem-kb 混合 provider：经 config 插件 API 幂等改写 config.yaml。

装/卸都走 ``cloudra.infra.config`` 的 add_plugin/remove_plugin（内部经
mutate_config 落盘，与所有其他配置写路径共享同一把 flock，互不丢更新）。
路径取 ``get_config().config_file``（尊重 ``CLOUDRA_CONFIG_FILE``）。
"""

from __future__ import annotations

from pathlib import Path

from cloudra.knowledge.plugin import PLUGIN_SPEC

__all__ = ["PLUGIN_SPEC", "install_plugin_spec", "uninstall_plugin_spec"]


def install_plugin_spec() -> tuple[Path, bool]:
    """把 PLUGIN_SPEC 追加进 plugins 列表。返回 (config_path, added)。"""
    from cloudra.infra.config import add_plugin, get_config

    added = add_plugin(PLUGIN_SPEC)
    return Path(get_config().config_file), added


def uninstall_plugin_spec() -> tuple[Path, bool]:
    """把 PLUGIN_SPEC 从 plugins 列表移除。返回 (config_path, removed)。"""
    from cloudra.infra.config import get_config, remove_plugin

    removed = remove_plugin(PLUGIN_SPEC)
    return Path(get_config().config_file), removed
