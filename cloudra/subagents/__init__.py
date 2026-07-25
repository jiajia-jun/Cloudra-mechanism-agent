"""子 Agent 注册表：按 agent_id 返回 Agent **类**，不含实例。

注册表保存类而非模板实例，调用方通过 ``AgentClass(query=..., conversation_id=...)``
创建独立实例，取代原先的深拷贝全局模板。
"""

import importlib.util
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).parent

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
    project_root = str(CURRENT_DIR.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    for py_file in CURRENT_DIR.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        rel_path = py_file.relative_to(CURRENT_DIR.parent)
        module_name = ".".join(rel_path.with_suffix("").parts)

        if module_name in sys.modules:
            module = sys.modules[module_name]
        else:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        get_class = getattr(module, "get_class", None)
        if get_class is not None:
            agent_cls = get_class()
            agent_id = _get_model_default(agent_cls, "id") or _get_model_default(agent_cls, "agent_id")
            if agent_id is None:
                agent_id = module_name.split(".")[-1]
            classes[agent_id] = agent_cls

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
