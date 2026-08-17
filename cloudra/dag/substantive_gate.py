"""实质性计算前的 DAG 门槛：mechanism 未被接受前禁止开算（dag 模式）。

唯一门槛（D4）：``mechanism_accepted = EXISTS(dag_drafts WHERE
state='accepted')``。接受前拦截计算入口——submit_compute_job、gjf_writer、
ts_guess 的计算型 mode（interpolate/scan_prepare）、conformer_search、
electronic_analysis、计算/写文件型 bash；检索/读取/reaction_mapping/
dag_view/dag_propose_mechanism/dag_message_supervisor 等一律放行。
standard 模式无门槛。计算入口词表在 tools/registry.py 声明
（dag_compute_entry / dag_compute_predicate），这里只做投影查询。
"""

from __future__ import annotations

from typing import Any

from cloudra.tools.capabilities import is_dag_compute_entry as _capability_is_compute_entry

GUIDED_BLOCK_MESSAGE = (
    "[DAG gate] In dag_guided mode, no compute before the mechanism is accepted: "
    "submit the mechanism with dag_propose_mechanism (draft + per-element stage "
    "contracts) and wait for the Supervisor to accept it with dag_accept_mechanism. "
    "Search/read/reaction_mapping/dag_view/dag_message_supervisor stay available."
)

RECORD_BLOCK_MESSAGE = (
    "[DAG gate] In dag_record mode, no compute before the mechanism is accepted: "
    "submit the mechanism with dag_propose_mechanism first (the harness "
    "auto-accepts it immediately). Search/read/reaction_mapping/dag_view stay available."
)


def is_compute_entry_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    """该工具调用是否属于「计算入口」（开算或写计算输入）。词表在 registry。"""
    return _capability_is_compute_entry(tool_name, arguments)
