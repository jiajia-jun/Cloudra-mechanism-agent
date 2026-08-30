"""激活 chem-kb 混合 provider：把插件 spec 幂等写进 config.yaml 的 plugins 列表。

不走 ``CloudraConfig.save()``（那是全文件重写，且 plugins 键经磁盘优先合并
语义保命）；这里直接编辑 YAML：safe_load → 幂等追加 → atomic_write_text。
路径取 ``get_config().config_file``（尊重 ``CLOUDRA_CONFIG_FILE``）。
移除请手改 YAML（save() 无法删 plugins，见 config.save 的 docstring）。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from cloudra.knowledge.plugin import PLUGIN_SPEC
from cloudra.persistence.fs_utils import atomic_write_text


def install_plugin_spec() -> tuple[Path, bool]:
    """把 PLUGIN_SPEC 追加进 plugins 列表。返回 (config_path, added)。"""
    from cloudra.infra.config import get_config

    cfg_path = Path(get_config().config_file)
    data: dict = {}
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    plugins = [str(s) for s in (data.get("plugins") or [])]
    if PLUGIN_SPEC in plugins:
        return cfg_path, False
    plugins.append(PLUGIN_SPEC)
    data["plugins"] = plugins
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(str(cfg_path), yaml.dump(
        data, allow_unicode=True, default_flow_style=False, sort_keys=False))
    return cfg_path, True
