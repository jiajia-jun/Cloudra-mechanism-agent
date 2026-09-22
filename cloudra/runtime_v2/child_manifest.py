"""子 Agent 完成回报的结构化 manifest（评审 5.5 后半）。

此前父 Agent 只能读自然语言（`[Sub-agent finished] role=... state=...` + 最后一条
消息），要自己从散文里抠状态 / 产物 / 错误。这里把完成回报拆成两半：**结构化
manifest** 与**由它确定性渲染的文本**——事件与工具结果保留结构化数据，父上下文
只注入简洁文本。

manifest 只取具名字段（事件枚举、结构化 data 键），不解析散文、不做字符串猜测：

- session / role / parent / 终态；
- runs 计数 + 最后一条 `run.finished` 的 `outcome` 与 `failure_kind`（旧库里
  没有 failure_kind 时为 None，不猜；取消的 run 没有 run.finished，按终态记
  cancelled）；
- `final_summary` 与它的来源（message / run_error / state_only）——child 无最终
  文本、failed、cancelled 三种情形都有稳定形状；
- `gate`：最后一条 `agent.completion_gate` 的 action / reason；`continue_work`
  的 reason 即「未解决项」的权威表述；
- `unresolved` / `next_steps`：前者来自门禁与失败分类，后者是终态 + 失败分类的
  确定性映射（不是模型生成的建议）。

汇报内容只含摘要与结构化字段：绝不塞 API key、完整原始日志或超大工具输出。
"""

from __future__ import annotations

from typing import Any

from cloudra.runtime_v2.schemas import AgentSession, AgentState

_TERMINAL_STATES = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}

#: 失败分类 → 下一步（键与 `runtime_v2.failures.RunFailureKind` 对齐；未知分类
#: 只给「看审计日志」这一条通用指引，不编造原因）。
_NEXT_STEPS: dict[str, str] = {
    "provider_permanent": "check this role's model / base_url / API key, then re-dispatch",
    "provider_transient_exhausted": (
        "provider kept failing until the retry budget ran out; check availability and "
        "rate limits, then re-dispatch"
    ),
    "event_persistence": (
        "a durable event write failed; check the data directory before re-dispatching"
    ),
    "pipeline_internal": "harness error; inspect the audit log before re-dispatching",
    "completion_no_progress": (
        "the completion gate rejected repeated exits; resolve the reported gap or narrow the task"
    ),
    "runtime_interrupted": (
        "interrupted by a process restart; re-dispatch with explicit instructions"
    ),
}


def _run_rows(core, child: AgentSession) -> list[dict[str, Any]]:
    """按事件序排出该 session 的 run 行（run.finished 缺失 = 取消或仍在跑）。"""
    rows: list[dict[str, Any]] = []
    for envelope in core.event_log.query_session(
        child.id, types={"run.started", "run.finished"}
    ):
        run_id = envelope.run_id
        row = next((r for r in reversed(rows) if r["run_id"] == run_id), None)
        if row is None:
            row = {"run_id": run_id, "outcome": None, "failure_kind": None}
            rows.append(row)
        if envelope.type == "run.finished":
            outcome = envelope.data.get("outcome")
            row["outcome"] = outcome if isinstance(outcome, str) else None
            kind = envelope.data.get("failure_kind")
            row["failure_kind"] = kind if isinstance(kind, str) else None
    if rows and rows[-1]["outcome"] is None and child.state is AgentState.CANCELLED:
        # 取消的 run 不落 run.finished：终态就是事实，统一标在最后一行上。
        rows[-1] = {**rows[-1], "outcome": "cancelled"}
    return rows


def _final_summary(core, child: AgentSession) -> tuple[str, str]:
    """(文本, 来源)：消息 → 失败原因 → 仅终态说明（顺序固定，不猜）。"""
    emitted = core.event_log.query_session(
        child.id, types={"agent.message_emitted"}, limit=1
    )
    if emitted:
        content = str(emitted[-1].data.get("content") or "")
        if content.strip():
            return content, "message"
    if child.state is AgentState.FAILED:
        for envelope in reversed(
            core.event_log.query_session(child.id, types={"run.finished"}, limit=20)
        ):
            if envelope.data.get("outcome") != "failed":
                continue
            error = envelope.data.get("error")
            return (
                f"Sub-agent failed: {error}" if error else "Sub-agent failed (no error recorded).",
                "run_error",
            )
        return "Sub-agent failed (no run record).", "run_error"
    return f"Sub-agent ended with state {child.state.value} and no final message.", "state_only"


def _last_gate(core, child: AgentSession) -> dict[str, Any] | None:
    gates = core.event_log.query_session(child.id, types={"agent.completion_gate"}, limit=1)
    if not gates:
        return None
    data = gates[-1].data
    return {
        "action": str(data.get("action") or "unknown"),
        "reason": str(data.get("reason") or ""),
        "source": str(data.get("source") or ""),
        "run_id": gates[-1].run_id,
    }


def build_child_manifest(core, child: AgentSession) -> dict[str, Any]:
    """子 Agent 终态的结构化 manifest（只用既有事件，纯读）。"""
    runs = _run_rows(core, child)
    last = runs[-1] if runs else None
    if last is None and child.state is AgentState.CANCELLED:
        last = {"run_id": None, "outcome": "cancelled", "failure_kind": None}
    summary_text, summary_source = _final_summary(core, child)
    gate = _last_gate(core, child)
    unresolved: list[str] = []
    if gate is not None and gate["action"] == "continue_work" and gate["reason"]:
        unresolved.append(gate["reason"])
    if last is not None and last["outcome"] == "failed":
        unresolved.append(f"last run failed ({last['failure_kind'] or 'unclassified'})")
    return {
        "session_id": child.id,
        "role_id": child.role_id,
        "parent_session_id": child.parent_session_id,
        "state": child.state.value,
        "terminal": child.state in _TERMINAL_STATES,
        "runs": {
            "total": len(runs),
            "succeeded": sum(1 for row in runs if row["outcome"] == "succeeded"),
            "failed": sum(1 for row in runs if row["outcome"] == "failed"),
            "cancelled": sum(1 for row in runs if row["outcome"] == "cancelled"),
        },
        "last_run": last,
        "final_summary": summary_text,
        "final_summary_source": summary_source,
        "gate": gate,
        "unresolved": unresolved,
        "next_steps": _next_steps(child.state, last),
    }


def _next_steps(state: AgentState, last: dict[str, Any] | None) -> list[str]:
    if state is AgentState.CANCELLED:
        return ["cancelled: re-dispatch only if the work is still needed"]
    if last is None or last["outcome"] is None:
        return []
    if last["outcome"] != "failed":
        return []
    kind = last["failure_kind"]
    step = _NEXT_STEPS.get(kind or "")
    if step is None:
        return ["last run failed; inspect the audit log before re-dispatching"]
    return [step]


def render_child_report(manifest: dict[str, Any]) -> str:
    """由 manifest 确定性渲染人类可读文本（唯一渲染点）。"""
    runs = manifest["runs"]
    last = manifest["last_run"]
    last_line = (
        f"last run: outcome={last['outcome']} failure_kind={last['failure_kind']}"
        if last is not None and last["outcome"]
        else "last run: (none recorded)"
    )
    lines = [
        f"[Sub-agent finished] role={manifest['role_id']} session_id={manifest['session_id']} "
        f"state={manifest['state']}",
        f"runs: total={runs['total']} succeeded={runs['succeeded']} "
        f"failed={runs['failed']} cancelled={runs['cancelled']}; {last_line}",
        "unresolved: " + ("; ".join(manifest["unresolved"]) if manifest["unresolved"] else "none"),
        "next steps: " + ("; ".join(manifest["next_steps"]) if manifest["next_steps"] else "none"),
        "summary:",
        manifest["final_summary"],
    ]
    return "\n".join(lines)
