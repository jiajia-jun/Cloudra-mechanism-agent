"""dag_delivery_report: evaluate delivery coverage."""

from __future__ import annotations

import asyncio
from typing import Any

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.controller import DagController
from cloudra.dag.models import OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput


class DagDeliveryReportInput(input_schema):
    pass


class DagDeliveryReport(DagToolBase):
    def is_manage(self) -> bool:
        return False

    tool_id: str = "t-dag-report"
    tool_name: str = "dag_delivery_report"
    tool_description: str = (
        "Evaluate delivery/mechanism coverage against the persisted coverage contract "
        "(dag_record or dag_guided; any actor; read-only). "
        "Use for: checking complete, unresolved, inconclusive, and waived gates before stopping. "
        "Do not use for: declaring delivery complete in prose or setting structure/saddle/endpoint "
        "evidence levels — those are harness-derived. "
        "Key discipline: trust this report, not your own completion claim."
    )
    input_schema: Any = DagDeliveryReportInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(
        self, user_input: DagDeliveryReportInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        ctx = await self._prepare(session)
        controller = DagController(
            ctx.db, session.id, ctx.mode, conversation_id=ctx.conversation_id,
            working_directory=getattr(self.subagent, "working_directory", None),
        )
        report = await asyncio.to_thread(controller.delivery_report)
        return DagToolOutput(
            is_success=True,
            action="dag_delivery_report",
            result=report.model_dump(mode="json"),
        )
