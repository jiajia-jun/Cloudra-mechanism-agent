"""Cloudra - AI Agent collaboration framework for chemical research."""

from importlib import import_module

__version__ = "2.0.0-beta"

_LAZY_EXPORTS = {
    "Agent": ("cloudra.agent", "Agent"),
    "Coordinator": ("cloudra.agent", "Coordinator"),
    "Color": ("cloudra.presentation", "Color"),
    "Coordinator_reAct": ("cloudra.react", "Coordinator_reAct"),
    "reAct": ("cloudra.react", "reAct"),
}
_LAZY_MODULES = {
    "conversation_repo",
    "events",
    "paths",
    "session_store",
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
    if name in _LAZY_MODULES:
        value = import_module(f"cloudra.{name}")
        globals()[name] = value
        return value
    raise AttributeError(f"module 'cloudra' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
