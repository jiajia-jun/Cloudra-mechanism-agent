"""
Shared utilities for ChemBench benchmark runners.

Provides field extraction helpers used across both the internal Cloudra runner
and the comparison runners.
"""

from __future__ import annotations

from typing import Any


def get_field(obj: Any, field: str, default: Any) -> Any:
    """
    从 dict 或 object 上取字段值，兼容内部带下划线的属性（如 _examples）。

    ChemBench 的 Task 对象把字段存为私有属性（_uuid、_examples 等），
    此函数统一处理两种形态。
    """
    if isinstance(obj, dict):
        if field in obj:
            return obj[field]
        if f"_{field}" in obj:
            return obj[f"_{field}"]
        return default

    if hasattr(obj, field):
        return getattr(obj, field)
    if hasattr(obj, f"_{field}"):
        return getattr(obj, f"_{field}")
    return default
