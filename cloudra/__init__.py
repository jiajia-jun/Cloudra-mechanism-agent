"""Cloudra - AI Agent collaboration framework for chemical research."""

from importlib import import_module

__version__ = "2.0.0-beta"

_LAZY_EXPORTS = {
    "Agent": ("cloudra.core.agent", "Agent"),
    "Coordinator": ("cloudra.core.agent", "Coordinator"),
}
# 兼容垫片：包结构重排（core/services/persistence/base/infra）前的
# `from cloudra import X` 老路径全部继续可用（惰性加载，不提前拉起重依赖）。
_LAZY_MODULES = {
    # core
    "agent": "cloudra.core.agent",
    "supervisor": "cloudra.core.supervisor",
    # services
    "session_store": "cloudra.services.session_store",
    "nodes": "cloudra.services.nodes",
    # persistence
    "database": "cloudra.persistence.database",
    "artifacts": "cloudra.persistence.artifacts",
    "memory": "cloudra.persistence.memory",
    "message_history": "cloudra.core.message_history",
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
    "events": "cloudra.infra.events",
    "ipc": "cloudra.infra.ipc",
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

__all__ = [*_LAZY_EXPORTS, *_LAZY_MODULES, "__version__"]


def __getattr__(name: str):
    """Keep legacy package exports without importing the Agent runtime eagerly."""
    target = _LAZY_EXPORTS.get(name)
    if target is not None:
        module_name, attribute = target
        value = getattr(import_module(module_name), attribute)
        globals()[name] = value
        return value
    module_path = _LAZY_MODULES.get(name)
    if module_path is not None:
        value = import_module(module_path)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'cloudra' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
