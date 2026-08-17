"""dag_remove_edge: RemoveEdge (rationale required)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import GraphKind, OrchestrationMode, RemoveEdge
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, mutation_output


class DagRemoveEdgeInput(input_schema):
    graph: Literal["process", "delivery"] = Field(
        description="Which DAG the edge belongs to."
    )
    edge_id: str = Field(description="Edge id to delete.")
    rationale: str = Field(
        min_length=1,
        description="Scientific or workflow reason for the deletion (mandatory; stays in the change log).",
    )


class DagRemoveEdge(DagToolBase):
    tool_id: str = "t-dag-rm-edge"
    tool_name: str = "dag_remove_edge"
    tool_description: str = (
        "Delete one edge from process or delivery with a mandatory rationale "
        "(Supervisor executes; Coordinator or sub-agents may request on delivery). "
        "Use for: scientifically justified edge removal with a logged reason. "
        "Do not use for: omitting rationale; expecting immediate agent deletion on process edges. "
        "Key discipline: agent process-edge removal is journaled and forwarded to Supervisor, not executed."
    )
    input_schema: Any = DagRemoveEdgeInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagRemoveEdgeInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        _, mutation = await self._apply(
            session,
            [
                RemoveEdge(
                    op="remove_edge",
                    graph=GraphKind(user_input.graph),
                    edge_id=user_input.edge_id,
                )
            ],
            rationale=user_input.rationale,
        )
        return mutation_output("dag_remove_edge", mutation)


def get_class():
    return DagRemoveEdge
