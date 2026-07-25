"""工具注册表：加载所有工具类，按调用方实例化。

每个条目是 ``ToolEntry(cls, tool_name, tool_id, input_schema)``，
包装原始 Pydantic 类并提供预解析的属性，避免在类级别直接访问
Pydantic v2 model_fields（类属性访问被 pydantic 拦截导致 AttributeError）。
"""

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).parent

_TOOL_ENTRIES_CACHE: list | None = None
_EXTRA_ENTRIES: list = []


@dataclass
class ToolEntry:
    cls: type
    tool_name: str
    tool_id: str
    input_schema: Any = None

    def instantiate(self, **kwargs):
        return self.cls(**kwargs)


def _get_default(tool_cls: type, field_name: str):
    """从 Pydantic 类的 model_fields 读取字段默认值。"""
    fields = getattr(tool_cls, "model_fields", {})
    field_info = fields.get(field_name)
    if field_info is not None and field_info.default is not ...:
        return field_info.default
    return None


def _make_entry(tool_cls: type) -> ToolEntry:
    return ToolEntry(
        cls=tool_cls,
        tool_name=_get_default(tool_cls, "tool_name") or "",
        tool_id=_get_default(tool_cls, "tool_id") or "",
        input_schema=_get_default(tool_cls, "input_schema"),
    )


def get_tools_lst() -> list[ToolEntry]:
    """返回所有已发现的工具条目列表，进程内缓存。"""
    global _TOOL_ENTRIES_CACHE
    if _TOOL_ENTRIES_CACHE is not None:
        return _TOOL_ENTRIES_CACHE

    entries = []
    project_root = str(CURRENT_DIR.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    for py_file in CURRENT_DIR.rglob("*.py"):
        if py_file.name == "__init__.py" or "__pycache__" in str(py_file) or "core" in py_file.parts:
            continue

        try:
            rel_path = py_file.relative_to(CURRENT_DIR.parent)
            module_name = ".".join(rel_path.with_suffix("").parts)

            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            if module_name not in sys.modules:
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            else:
                module = sys.modules[module_name]

            get_class_func = getattr(module, "get_class", None)
            if get_class_func is not None:
                entries.append(_make_entry(get_class_func()))
        except Exception as e:
            print(f"警告: 加载工具 {py_file} 失败: {e}")

    _TOOL_ENTRIES_CACHE = entries
    if _EXTRA_ENTRIES:
        _TOOL_ENTRIES_CACHE.extend(_EXTRA_ENTRIES)
        _EXTRA_ENTRIES.clear()
    return entries


def register_tool_class(tool_cls) -> None:
    """向全局工具注册表追加一个额外工具类（例如 benchmark 专用工具）。"""
    entry = _make_entry(tool_cls)
    if _TOOL_ENTRIES_CACHE is not None:
        _TOOL_ENTRIES_CACHE.append(entry)
    else:
        _EXTRA_ENTRIES.append(entry)
