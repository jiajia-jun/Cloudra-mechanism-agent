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
# 兼容垫片：包结构重排（core/services/persistence/base/infra）前的
# `from cloudra import X` 老路径全部继续可用（惰性加载，不提前拉起重依赖）。
_LAZY_MODULES = {
    # core
    "agent": "cloudra.core.agent",
    "react": "cloudra.core.react",
    "supervisor": "cloudra.core.supervisor",
    "main": "cloudra.core.main",
    # services
    "service": "cloudra.services.service",
    "api": "cloudra.services.api",
    "api_v1": "cloudra.services.api_v1",
    "backends": "cloudra.services.backends",
    "session_store": "cloudra.services.session_store",
    "control_store": "cloudra.services.control_store",
    "interactions": "cloudra.services.interactions",
    "nodes": "cloudra.services.nodes",
    "device_broker": "cloudra.services.device_broker",
    # persistence
    "database": "cloudra.persistence.database",
    "conversation_repo": "cloudra.persistence.conversation_repo",
    "artifacts": "cloudra.persistence.artifacts",
    "memory": "cloudra.persistence.memory",
    "case_bank": "cloudra.persistence.case_bank",
    "context_manager": "cloudra.persistence.context_manager",
    "paths": "cloudra.persistence.paths",
    "fs_utils": "cloudra.persistence.fs_utils",
    "workspace": "cloudra.persistence.workspace",
    # base
    "session_class": "cloudra.base.session_class",
    "conversation_class": "cloudra.base.conversation_class",
    "log_class": "cloudra.base.log_class",
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
    "presentation": "cloudra.infra.presentation",
    "tool_presentation": "cloudra.infra.tool_presentation",
    "platform_utils": "cloudra.infra.platform_utils",
    "runtime_profile": "cloudra.infra.runtime_profile",
    "email_listener": "cloudra.infra.email_listener",
    "mobile_storage": "cloudra.infra.mobile_storage",
    "native_bridge": "cloudra.infra.native_bridge",
    "android_build": "cloudra.infra.android_build",
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
