"""dag_view: read a bounded DAG projection or compact delivery subgraph."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import GraphKind, OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    render_projection_view,
    render_subgraph_view,
)


class DagViewInput(input_schema):
    graph_kind: Literal["both", "process", "delivery"] = Field(
        default="both",
        description=(
            "both (default) returns the projection: delivery gaps, pending call "
            "reviews, recent mutations. delivery returns a compact paginated "
            "subgraph. process is deprecated (the process graph was removed) "
            "and returns an explanatory note."
        ),
    )
    node_id: str | None = Field(
        default=None,
        description="Optional single node_id to inspect (merged into node_ids).",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="For the delivery subgraph: skip this many nodes.",
    )
    node_ids: list[str] | None = Field(
        default=None,
        description=(
            "For the delivery subgraph: return only these node_ids "
            "(plus edges among them). Prefer this over paging the whole graph."
        ),
    )
    status_filter: str | None = Field(
        default=None,
        description=(
            "For the delivery subgraph: return only nodes whose "
            "payload.status equals this value."
        ),
    )


class DagView(DagToolBase):
    tool_id: str = "t-dag-view"
    tool_name: str = "dag_view"
    tool_description: str = (
        "Read the persistent delivery/mechanism DAG (dag_record or dag_guided; any actor). "
        "Use for: default graph_kind=both to see delivery gaps, pending call reviews, and recent mutations; "
        "graph_kind=delivery with node_ids/status_filter to inspect specific elements and their stages. "
        "Do not use for: graph mutations; graph_kind=process (removed — returns a deprecation note). "
        "Key discipline: prefer the default both projection over paging an entire subgraph."
    )
    input_schema: Any = DagViewInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(self, user_input: DagViewInput, session: Session) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        ctx = await self._prepare(session)
        snapshot = await asyncio.to_thread(ctx.engine.snapshot)
        if user_input.graph_kind == "both":
            history = await asyncio.to_thread(lambda: ctx.engine.history(limit=8))
            result = render_projection_view(
                snapshot, mode=ctx.mode, contract=ctx.contract, history=history
            )
            return DagToolOutput(is_success=True, action="dag_view", result=result)

        wanted = list(user_input.node_ids or [])
        if user_input.node_id:
            wanted.append(user_input.node_id)
        result = render_subgraph_view(
            snapshot,
            graph_kind=GraphKind(user_input.graph_kind),
            offset=user_input.offset,
            node_ids=wanted or None,
            status_filter=user_input.status_filter,
        )
        return DagToolOutput(is_success=True, action="dag_view", result=result)


def get_class():
    return DagView
