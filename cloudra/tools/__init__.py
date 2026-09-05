"""工具注册表：从显式 manifest 加载工具类，按调用方实例化。

每个条目是 ``ToolEntry(cls, tool_name, tool_id, input_schema)``，
包装原始 Pydantic 类并提供预解析的属性，避免在类级别直接访问
Pydantic v2 model_fields（类属性访问被 pydantic 拦截导致 AttributeError）。
"""

import importlib
import sys
from dataclasses import dataclass
from typing import Any

from cloudra.tools.registry import TOOL_REGISTRY

_TOOL_ENTRIES_CACHE: list | None = None
_EXTRA_ENTRIES: list = []
_TOOL_LOAD_ERRORS: dict[str, str] = {}


@dataclass
class ToolEntry:
    cls: type
    tool_name: str
    tool_id: str
    input_schema: Any = None
    output_schema: Any = None

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
        output_schema=_get_default(tool_cls, "output_schema"),
    )


def _assert_unique_tool_ids(entries: list[ToolEntry]) -> None:
    """tool_id 全局唯一：重复 id 直接 raise，防止注册表静默撞号。"""
    seen: dict[str, str] = {}
    for entry in entries:
        if not entry.tool_id:
            continue
        owner = f"{entry.cls.__module__}:{entry.cls.__name__}"
        if entry.tool_id in seen:
            raise RuntimeError(
                f"工具 tool_id 重复: {entry.tool_id!r} ({seen[entry.tool_id]} 与 {owner})"
            )
        seen[entry.tool_id] = owner


def get_tools_lst() -> list[ToolEntry]:
    """返回显式注册且在当前依赖环境中可导入的工具，进程内缓存。"""
    global _TOOL_ENTRIES_CACHE
    if _TOOL_ENTRIES_CACHE is not None:
        return _TOOL_ENTRIES_CACHE

    entries = []
    _TOOL_LOAD_ERRORS.clear()
    for registration in TOOL_REGISTRY:
        try:
            module = importlib.import_module(registration.module)
        except ModuleNotFoundError as e:
            if e.name == registration.module or registration.module.startswith(f"{e.name}."):
                raise RuntimeError(f"显式工具注册模块不存在: {registration.module}") from e
            error = f"{type(e).__name__}: {e}"
            _TOOL_LOAD_ERRORS[registration.module] = error
            print(f"警告: 加载显式工具 {registration.module}:{registration.class_name} 失败: {error}", file=sys.stderr)
            continue
        except ImportError as e:
            error = f"{type(e).__name__}: {e}"
            _TOOL_LOAD_ERRORS[registration.module] = error
            print(f"警告: 加载显式工具 {registration.module}:{registration.class_name} 失败: {error}", file=sys.stderr)
            continue
        except Exception as e:
            raise RuntimeError(
                f"显式工具模块加载异常: {registration.module}:{registration.class_name}"
            ) from e

        try:
            tool_cls = getattr(module, registration.class_name)
        except AttributeError as e:
            raise RuntimeError(
                f"显式工具注册类不存在: {registration.module}:{registration.class_name}"
            ) from e
        entries.append(_make_entry(tool_cls))

    if _EXTRA_ENTRIES:
        entries.extend(_EXTRA_ENTRIES)
        _EXTRA_ENTRIES.clear()
    _assert_unique_tool_ids(entries)
    _TOOL_ENTRIES_CACHE = entries
    return entries


def get_tool_load_errors() -> dict[str, str]:
    """返回当前依赖环境中显式工具的导入失败诊断。"""
    get_tools_lst()
    return dict(_TOOL_LOAD_ERRORS)


def register_tool_class(tool_cls) -> None:
    """向全局工具注册表追加一个额外工具类（例如 benchmark 专用工具）。"""
    entry = _make_entry(tool_cls)
    if _TOOL_ENTRIES_CACHE is not None:
        _assert_unique_tool_ids([*_TOOL_ENTRIES_CACHE, entry])
        _TOOL_ENTRIES_CACHE.append(entry)
    else:
        _EXTRA_ENTRIES.append(entry)
