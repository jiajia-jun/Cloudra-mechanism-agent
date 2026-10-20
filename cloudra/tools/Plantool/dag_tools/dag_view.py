"""dag_view: read a bounded DAG projection or compact delivery subgraph."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.controller import DagController
from cloudra.dag.models import GraphActor, GraphKind, OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    final_review_request_id,
    render_subgraph_view,
    review_scope_allows,
)


class DagViewInput(input_schema):
    graph_kind: Literal["both", "process", "delivery"] = Field(
        default="both",
        description=(
            "both (default) returns the compact mechanism view: species, steps, "
            "unresolved gaps, and draft/review summaries. "
            "delivery returns a paginated subgraph view. "
            "process is deprecated."
        ),
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Delivery view: skip this many nodes. Compact view: skip this many unassigned evidence summaries.",
    )
    node_ids: list[str] | None = Field(
        default=None,
        description="For the delivery subgraph: return only these node_ids.",
    )
    status_filter: str | None = Field(
        default=None,
        description="For the delivery subgraph: return only nodes with this status.",
    )


class DagView(DagToolBase):
    def is_manage(self) -> bool:
        return False

    tool_id: str = "t-dag-view"
    tool_name: str = "dag_view"
    tool_description: str = (
        "Read the persistent delivery/mechanism DAG (dag_record or dag_guided; any actor; read-only). "
        "Returns the declarative mechanism view: species (name and status), "
        "elementary steps (name, endpoints, and status), unresolved gaps, and summaries "
        "of pending drafts or reviews. For the Supervisor this also lists queued structured "
        "review requests (`queued_requests`, each with its `request_id` for dag_review_evidence)."
    )
    input_schema: Any = DagViewInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

    async def tool_call(self, user_input: DagViewInput, session: Session) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        ctx = await self._prepare(session)
        snapshot = await asyncio.to_thread(ctx.engine.snapshot)
        if user_input.graph_kind == "both":
            final_review = ctx.actor is GraphActor.SUPERVISOR and final_review_request_id(self.subagent) is not None
            delivery = snapshot.delivery
            controller = DagController(ctx.db, session.id, ctx.mode,
                conversation_id=ctx.conversation_id,
                working_directory=getattr(self.subagent, "working_directory", None))
            report = await asyncio.to_thread(controller.delivery_report)
            unresolved_ids = {gate.target_id for gate in [*report.unresolved, *report.inconclusive]}
            reviewed_ids = {gate.target_id for gate in report.satisfied
                            if gate.code == "supervisor_evidence_accepted"} - unresolved_ids
            node_map: dict[str, str] = {}
            species_list: list[dict[str, Any]] = []
            for node in delivery.nodes:
                name = getattr(node, "name", "") or getattr(node, "label", "") or node.node_id
                node_map[node.node_id] = name
                item: dict[str, Any] = {
                    "name": name,
                    "status": "supported" if node.node_id in reviewed_ids else getattr(node, "status", "pending") or "pending",
                }
                if getattr(node, "reason", ""):
                    item["reason"] = node.reason
                species_list.append(item)

            name_map = dict(node_map)
            step_list: list[dict[str, Any]] = []
            for edge in delivery.edges:
                name = getattr(edge, "name", "") or getattr(edge, "label", "") or edge.edge_id
                name_map[edge.edge_id] = name
                item = {
                    "name": name,
                    "from": node_map.get(edge.source_node_id, edge.source_node_id),
                    "to": node_map.get(edge.target_node_id, edge.target_node_id),
                    "status": "supported" if edge.edge_id in reviewed_ids else getattr(edge, "status", "pending") or "pending",
                }
                if getattr(edge, "reason", ""):
                    item["reason"] = edge.reason
                step_list.append(item)

            unresolved_gaps = [
                {
                    "target": name_map.get(gate.target_id, gate.target_id),
                    "reason": gate.detail,
                }
                for gate in [*report.unresolved, *report.inconclusive]
            ]

            open_drafts = await asyncio.to_thread(
                lambda: [
                    {
                        "draft_id": draft_id,
                        "rationale": draft.rationale,
                        "species_count": len([op for op in draft.operations if getattr(op, "op", "") == "add_node"]),
                        "step_count": len([op for op in draft.operations if getattr(op, "op", "") == "add_edge"]),
                        "status": draft.state,
                    }
                    for draft_id, draft in ([] if final_review else ctx.store.list_open_drafts())
                ]
            )

            pending_reviews = await asyncio.to_thread(
                lambda: [
                    {
                        "review_id": review.review_id,
                        "target": name_map.get(
                            getattr(review, "suggested_target_id", getattr(review, "target_id", "")) or "",
                            getattr(review, "suggested_target_id", getattr(review, "target_id", "")) or "",
                        ),
                        "claim": review.claim,
                        "status": getattr(review, "state", getattr(review, "status", "pending")),
                    }
                    for review in ([] if final_review else ctx.store.list_call_reviews("pending", source="explicit"))
                ]
            )

            # 结构化送审请求（dag_message_supervisor 入箱）：supervision 唤醒通知
            # 点名"queued review requests"，本视图是 Supervisor 唯一能读到它们的
            # 入口——不投影出来，被唤醒的 Supervisor 会在 DAG store 里找不到它。
            queued_requests = await asyncio.to_thread(
                lambda: [
                    {
                        "request_id": req.request_id,
                        "kind": str(req.kind),
                        "requester": req.requester,
                        "target_ids": [name_map.get(t, t) for t in req.target_ids],
                        "question": req.question,
                        "scientific_checks": req.proposal.get("scientific_checks", {}),
                        "evidence_view": f"dag_view_evidence(review_id={req.request_id!r})",
                        "created_at": req.created_at,
                    }
                    for req in ctx.store.list_review_requests("queued")
                    if review_scope_allows(self.subagent, req.kind, req.request_id)
                ]
            )

            unassigned = await asyncio.to_thread(ctx.store.collect_review_exceptions, [])
            start = user_input.offset
            evidence_page = []
            for item in unassigned[start:start + 20]:
                summary = {key: item.get(key) for key in
                           ("category", "target_id", "fact_id", "check", "outcome")}
                summary["source_refs"] = [{"ref_type": ref.get("ref_type"), "ref_id": ref.get("ref_id")}
                                          for ref in item.get("source_refs", [])]
                evidence_page.append(summary)

            result: dict[str, Any] = {
                "species": species_list,
                "steps": step_list,
                "unresolved_gaps": unresolved_gaps,
                "open_drafts": open_drafts,
                "pending_reviews": pending_reviews,
                "queued_requests": queued_requests,
                "unassigned_evidence": evidence_page,
                "unassigned_evidence_count": len(unassigned),
                "unassigned_evidence_next_offset": start + 20 if start + 20 < len(unassigned) else None,
                "revisions": dict(snapshot.bundle.revisions),
            }
            return DagToolOutput(is_success=True, action="dag_view", result=result)

        wanted = list(user_input.node_ids or [])
        result = render_subgraph_view(
            snapshot,
            graph_kind=GraphKind(user_input.graph_kind),
            offset=user_input.offset,
            node_ids=wanted or None,
            status_filter=user_input.status_filter,
        )
        return DagToolOutput(is_success=True, action="dag_view", result=result)
