"""DAG computation classification.

Draft review is asynchronous: a pending or rejected hypothesis never blocks
exploration.  The registry classification remains available to callers that
need to label compute entry tools, but it is not a substantive gate.
"""

from __future__ import annotations

from typing import Any

from cloudra.tools.capabilities import is_dag_compute_entry as _capability_is_compute_entry

GUIDED_BLOCK_MESSAGE = (
    "[DAG review] The mechanism draft is still under review; computation may "
    "continue while the working hypothesis is revised."
)

RECORD_BLOCK_MESSAGE = GUIDED_BLOCK_MESSAGE


def is_compute_entry_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    """该工具调用是否属于「计算入口」（开算或写计算输入）。词表在 registry。"""
    return _capability_is_compute_entry(tool_name, arguments)
