"""工具注册表：从显式 manifest 加载工具类，按调用方实例化。

每个条目是 ``ToolEntry(cls, tool_name, tool_id, input_schema)``，
包装原始 Pydantic 类并提供预解析的属性，避免在类级别直接访问
Pydantic v2 model_fields（类属性访问被 pydantic 拦截导致 AttributeError）。
"""

import importlib
import sys
from dataclasses import dataclass
from typing import Any

from pydantic_core import PydanticUndefined

from cloudra.tools.registry import TOOL_REGISTRY

_TOOL_ENTRIES_CACHE: list | None = None


@dataclass
class ToolEntry:
    cls: type
    tool_name: str
    tool_id: str
    input_schema: Any = None
    output_schema: Any = None
    # Keep the model-facing workflow description in every protocol projection.
    # It is declared on the tool class alongside the schemas, so do not make
    # JS callers reconstruct it from an input model docstring.
    tool_description: str = ""
    summary: str = ""
    skill_references: tuple[tuple[str, str], ...] = ()

    def instantiate(self, **kwargs):
        return self.cls(**kwargs)


def _make_entry(tool_cls: type) -> ToolEntry:
    from cloudra.base.tools_class import Tool, input_schema, output_schema

    if not isinstance(tool_cls, type) or not issubclass(tool_cls, Tool):
        raise RuntimeError(f"注册工具必须是 Tool 子类: {tool_cls!r}")
    entry = ToolEntry(
        cls=tool_cls,
        tool_name=_get_default(tool_cls, "tool_name") or "",
        tool_id=_get_default(tool_cls, "tool_id") or "",
        input_schema=_get_default(tool_cls, "input_schema"),
        output_schema=_get_default(tool_cls, "output_schema"),
        tool_description=_get_default(tool_cls, "tool_description") or "",
    )
    owner = f"{tool_cls.__module__}:{tool_cls.__name__}"
    for field in ("tool_name", "tool_id"):
        value = getattr(entry, field)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"工具 {owner} 的 {field} 必须有非空字符串默认值")
    for field, base in (("input_schema", input_schema), ("output_schema", output_schema)):
        schema = getattr(entry, field)
        if not isinstance(schema, type) or not issubclass(schema, base):
            raise RuntimeError(f"工具 {owner} 的 {field} 必须是 {base.__name__} 子类")
    return entry


def _get_default(tool_cls: type, field_name: str):
    """Read declared schema metadata without constructing the tool."""
    field = tool_cls.model_fields.get(field_name)
    if field is not None and field.default is not PydanticUndefined:
        return field.default
    return None


def _assert_unique_tool_identities(entries: list[ToolEntry]) -> None:
    """tool_id 和 wire tool_name 都必须唯一，防止声明与执行指向不同工具。"""
    seen: dict[str, dict[str, str]] = {"tool_id": {}, "tool_name": {}}
    for entry in entries:
        owner = f"{entry.cls.__module__}:{entry.cls.__name__}"
        for field, owners in seen.items():
            value = getattr(entry, field)
            if value in owners:
                raise RuntimeError(
                    f"工具 {field} 重复: {value!r} ({owners[value]} 与 {owner})"
                )
            owners[value] = owner


def get_tools_lst() -> list[ToolEntry]:
    """返回显式注册且在当前依赖环境中可导入的工具，进程内缓存。"""
    global _TOOL_ENTRIES_CACHE
    if _TOOL_ENTRIES_CACHE is not None:
        return _TOOL_ENTRIES_CACHE

    entries = []
    for registration in TOOL_REGISTRY:
        try:
            module = importlib.import_module(registration.module)
        except ModuleNotFoundError as e:
            if e.name == registration.module or registration.module.startswith(f"{e.name}."):
                raise RuntimeError(f"显式工具注册模块不存在: {registration.module}") from e
            error = f"{type(e).__name__}: {e}"
            print(f"警告: 加载显式工具 {registration.module}:{registration.class_name} 失败: {error}", file=sys.stderr)
            continue
        except ImportError as e:
            error = f"{type(e).__name__}: {e}"
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
        entry = _make_entry(tool_cls)
        entry.summary = registration.summary
        entry.skill_references = registration.skill_references
        if registration.tool_name and registration.tool_name != entry.tool_name:
            raise RuntimeError(
                f"显式工具名称不一致: {registration.module}:{registration.class_name} "
                f"声明 {registration.tool_name!r}，实现 {entry.tool_name!r}"
            )
        entries.append(entry)

    _assert_unique_tool_identities(entries)
    _TOOL_ENTRIES_CACHE = entries
    return entries
