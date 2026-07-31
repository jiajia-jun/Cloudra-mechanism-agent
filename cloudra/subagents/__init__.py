"""子 Agent 注册表：从显式 manifest 按 agent_id 返回 Agent **类**。

注册表保存类而非模板实例，调用方通过 ``AgentClass(query=..., conversation_id=...)``
创建独立实例，取代原先的深拷贝全局模板。
"""

import importlib

from cloudra.subagents.registry import SUBAGENT_REGISTRY

_SUBAGENT_CLASSES_CACHE: dict | None = None


def _get_model_default(cls, field_name: str):
    """从 Pydantic 类读取字段默认值（兼容 v2 model_fields）。"""
    fields = getattr(cls, "model_fields", {})
    field_info = fields.get(field_name)
    if field_info is not None and field_info.default is not ...:
        return field_info.default
    return None


def get_subagent_classes() -> dict:
    """返回 ``{agent_id: AgentClass}`` 映射表，进程内缓存。"""
    global _SUBAGENT_CLASSES_CACHE
    if _SUBAGENT_CLASSES_CACHE is not None:
        return _SUBAGENT_CLASSES_CACHE

    classes = {}
    for registration in SUBAGENT_REGISTRY:
        module = importlib.import_module(registration.module)
        agent_cls = getattr(module, registration.class_name)
        declared_id = _get_model_default(agent_cls, "id") or _get_model_default(agent_cls, "agent_id")
        if declared_id != registration.agent_id:
            raise RuntimeError(
                f"子 Agent 注册 ID 不一致: manifest={registration.agent_id}, "
                f"class={declared_id}, target={registration.module}:{registration.class_name}"
            )
        classes[registration.agent_id] = agent_cls

    _SUBAGENT_CLASSES_CACHE = classes
    return classes


class Subagent_hash:
    """子 Agent 类注册表的外观包装，维持 dict-like 访问。

    原先使用 ``setattr(self, id, template_instance)`` 动态注入属性；
    现在内部是一个 ``{agent_id: AgentClass}`` 的普通字典。
    """

    def __init__(self):
        self._classes = get_subagent_classes()

    @property
    def subagents_dict(self) -> dict:
        return self._classes

    def get(self, agent_id: str):
        """按 agent_id 获取 Agent **类**。"""
        return self._classes.get(agent_id)

    def __getitem__(self, agent_id: str):
        cls = self._classes.get(agent_id)
        if cls is None:
            raise KeyError(agent_id)
        return cls

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._classes

    def __getattr__(self, name: str):
        """保留对 ``agent_hash.a-1`` 的兼容访问（测试与旧调用方使用）。"""
        if name.startswith("_") or name in ("subagents_dict", "get"):
            raise AttributeError(name)
        if name in self._classes:
            return self._classes[name]
        raise AttributeError(name)
