"""Delivery-side change summary returned from DagController.on_tool_finished."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeliveryDelta:
    """What changed on the delivery graph after one tool call.

    Empty bound_target means "no model-visible delta" — callers must not
    inject noise into the tool result or notice queue.
    """

    evidence_ref: Any = None
    tool_name: str = ""
    bound_target: str | None = None
    level_from: str | None = None
    level_to: str | None = None
    new_gaps: tuple[str, ...] = field(default_factory=tuple)
    # 同构重提被去重时带上既有 review id；summary_line 会给 Coordinator 一个
    # 可执行的提示（重提须说明变更），而不是静默吞掉。
    dedup_review_id: str | None = None

    def summary_line(self) -> str | None:
        if self.dedup_review_id:
            return (
                f"[DAG] duplicate artifact: this {self.tool_name or 'tool'} result is "
                f"identical to an already-queued review (review {self.dedup_review_id}), so "
                "it was NOT re-queued. If you are re-submitting on purpose, state what "
                "changed (new source log, re-run job, different file) — otherwise wait for "
                "or read that review's verdict."
            )
        if not self.bound_target:
            return None
        change = ""
        if (
            self.level_from is not None
            and self.level_to is not None
            and self.level_from != self.level_to
        ):
            change = f" ({self.level_from}→{self.level_to})"
        line = f"[DAG] evidence bound: {self.tool_name} → {self.bound_target}{change}"
        if self.new_gaps:
            line += "; new gaps: " + ", ".join(self.new_gaps[:6])
        return line
