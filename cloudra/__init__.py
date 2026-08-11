"""Cloudra - AI Agent collaboration framework for chemical research."""

from importlib import import_module

__version__ = "2.0.0-beta"

_LAZY_EXPORTS = {
    "Agent": ("cloudra.core.agent", "Agent"),
    "Coordinator": ("cloudra.core.agent", "Coordinator"),
    "Color": ("cloudra.infra.presentation", "Color"),
    "Coordinator_reAct": ("cloudra.core.react", "Coordinator_reAct"),
    "reAct": ("cloudra.core.react", "reAct"),
}
# 兼容垫片：重排前 `from cloudra import X` 的老路径继续可用（惰性加载）。
_LAZY_MODULES = {
    "conversation_repo": "cloudra.persistence.conversation_repo",
    "events": "cloudra.infra.events",
    "paths": "cloudra.persistence.paths",
    "session_store": "cloudra.services.session_store",
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
