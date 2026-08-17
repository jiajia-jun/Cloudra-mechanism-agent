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

    def summary_line(self) -> str | None:
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
