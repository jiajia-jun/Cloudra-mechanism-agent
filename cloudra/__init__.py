"""Cloudra - AI Agent collaboration framework for chemical research."""

from importlib import import_module

__version__ = "0.1.0rc1"

# 兼容垫片：包结构重排（core/services/persistence/base/infra）前的
# `from cloudra import X` 老路径全部继续可用（惰性加载，不提前拉起重依赖）。
# 执行栈（cloudra.core.agent / message_history）已删除，不再留入口。
_LAZY_MODULES = {
    # services
    "session_store": "cloudra.services.session_store",
    "nodes": "cloudra.services.nodes",
    # persistence
    "database": "cloudra.persistence.database",
    "artifacts": "cloudra.persistence.artifacts",
    "memory": "cloudra.persistence.memory",
    "paths": "cloudra.persistence.paths",
    "fs_utils": "cloudra.persistence.fs_utils",
    "workspace": "cloudra.persistence.workspace",
    # base
    "session_class": "cloudra.base.session_class",
    "skill_class": "cloudra.base.skill_class",
    "tools_class": "cloudra.base.tools_class",
    # infra
    "config": "cloudra.infra.config",
    "llm_client": "cloudra.infra.llm_client",
    "streaming": "cloudra.infra.streaming",
    "token_estimator": "cloudra.infra.token_estimator",
    "web_search_native": "cloudra.infra.web_search_native",
    "slurm": "cloudra.infra.slurm",
    "compute_utils": "cloudra.infra.compute_utils",
    "operations": "cloudra.infra.operations",
    "yolo_guard": "cloudra.infra.yolo_guard",
    "platform_utils": "cloudra.infra.platform_utils",
    "runtime_profile": "cloudra.infra.runtime_profile",
}

__all__ = [*_LAZY_MODULES, "__version__"]


def __getattr__(name: str):
    """Keep legacy package module paths without importing heavy deps eagerly."""
    module_path = _LAZY_MODULES.get(name)
    if module_path is not None:
        value = import_module(module_path)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'cloudra' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
