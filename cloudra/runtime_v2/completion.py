"""完成依据投影：区分「运行结束」与「目标已验证完成」（评审 5.3）。

数据来源只有既有事件，不新增 AgentState、不改 DAG 完成算法：

- ``agent.completion_gate``：统一结束门禁的裁决，带结构化 ``basis``（收尾依据）；
- ``run.finished`` / ``agent.cancelled``：run 的终态。

纯函数吃事件列表、出投影字典，API 与前端共用同一口径。verification_label
**只由 basis 决定，绝不解析 reason 文本**：未声明的 basis（含被拦的判定）一律
``unverified``——只有证据门禁确认过的结题才配得上 ``verified``。
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, Optional

from cloudra.runtime_v2.schemas import EventEnvelope

RunOutcome = Literal["succeeded", "failed", "cancelled"]
VerificationLabel = Literal["verified", "partial", "unverified"]

# 完成依据投影只读这三类事件（API 查询的 types 过滤也用同一集合）。
COMPLETION_EVENT_TYPES = frozenset({"agent.completion_gate", "run.finished", "agent.cancelled"})

# 单个 session 只要事件流的尾部：门禁与终态相邻写入，取最后几条就足以覆盖最后
# 一个 [某 run 的门禁, 该 run 的终态] 对（同一 run 内多次 continue_work 只保留
# 最后一次）。
COMPLETION_TAIL = 8

# basis → 验证等级。未列出的 basis（含缺失/None）一律 unverified。
_BASIS_LABELS: dict[str, VerificationLabel] = {
    "dag_verified": "verified",
    "supervisor_approved": "partial",
    "partial_recorded": "partial",
}


def _reduce(entry: Optional[dict[str, Any]], event: EventEnvelope) -> dict[str, Any]:
    state = entry if entry is not None else {"gates": {}, "terminal": None}
    if event.type == "agent.completion_gate":
        state["gates"][event.run_id] = event.data
    elif event.type == "run.finished":
        state["terminal"] = {
            "run_id": event.run_id,
            "run_outcome": _outcome(event.data.get("outcome")),
        }
    elif event.type == "agent.cancelled":
        # 取消不落 run.finished（agent.cancelled 就是终态标记）。
        state["terminal"] = {"run_id": event.run_id, "run_outcome": "cancelled"}
    return state


def _outcome(value: Any) -> RunOutcome | None:
    return value if value in ("succeeded", "failed", "cancelled") else None


def _finalize(entry: dict[str, Any]) -> dict[str, Any] | None:
    terminal = entry["terminal"]
    if terminal is None:
        # 只有门禁事件、没有终态（run 还在跑）：没有完成依据可言。
        return None
    run_id = terminal.get("run_id")
    gate = entry["gates"].get(run_id) if run_id is not None else None
    basis = (gate or {}).get("basis")
    basis = basis if isinstance(basis, str) and basis else None
    outcome = terminal.get("run_outcome")
    label: VerificationLabel = "unverified"
    if outcome == "succeeded" and basis is not None:
        label = _BASIS_LABELS.get(basis, "unverified")
    return {
        "run_id": run_id,
        "run_outcome": outcome,
        "completion_basis": basis,
        "verification_label": label,
    }


def completion_state(events: Iterable[EventEnvelope]) -> dict[str, dict[str, Any]]:
    """一次遍历算出所有 session 最近一次已结束 run 的完成依据，按 session_id 索引。

    列表端点（一个项目的全部 agent）用这个入口：只扫一遍事件，不逐 agent 重查。
    没有任何终态事件的 session 不会出现在结果里。
    """
    entries: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.session_id is None or event.type not in COMPLETION_EVENT_TYPES:
            continue
        entries[event.session_id] = _reduce(entries.get(event.session_id), event)
    finalized = {session_id: _finalize(entry) for session_id, entry in entries.items()}
    return {session_id: summary for session_id, summary in finalized.items() if summary is not None}


def completion_summary(events: Iterable[EventEnvelope]) -> dict[str, Any] | None:
    """单个 session（``query_session`` 的结果）的完成依据；没有终态时返回 None。

    调用方负责判断该 run 是否仍在进行：任务在跑/挂起时尚未有结论，此时不应把
    上一次 run 的结果当成当前状态展示。
    """
    entry: Optional[dict[str, Any]] = None
    for event in events:
        if event.type in COMPLETION_EVENT_TYPES:
            entry = _reduce(entry, event)
    if entry is None:
        return None
    return _finalize(entry)
