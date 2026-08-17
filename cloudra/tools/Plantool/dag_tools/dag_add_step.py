"""dag_add_step: AddEdge(delivery ElementaryStepEdge)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import AddEdge, ElementaryStepEdge, OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, mutation_output


class DagAddStepInput(input_schema):
    edge_id: str = Field(description="New elementary-step edge id.")
    source_node_id: str = Field(description="Source occurrence node id.")
    target_node_id: str = Field(description="Target occurrence node id.")
    label: str | None = Field(default=None, description="Optional step label.")


class DagAddStep(DagToolBase):
    tool_id: str = "t-dag-step"
    tool_name: str = "dag_add_step"
    tool_description: str = (
        "Add one elementary-step edge between existing delivery occurrence nodes "
        "(Coordinator in dag_record or dag_guided). "
        "Use for: connecting species you created with dag_add_species. "
        "Do not use for: Supervisor writes; inventing endpoints; batch operations arrays or extra arguments wrappers. "
        "Key discipline: both node ids must already exist on the delivery graph."
    )
    input_schema: Any = DagAddStepInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagAddStepInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        edge_kwargs: dict[str, Any] = {
            "edge_id": user_input.edge_id,
            "source_node_id": user_input.source_node_id,
            "target_node_id": user_input.target_node_id,
        }
        if user_input.label:
            edge_kwargs["label"] = user_input.label
        _, mutation = await self._apply(
            session,
            [
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(**edge_kwargs),
                )
            ],
            rationale=f"add step {user_input.edge_id}",
        )
        return mutation_output("dag_add_step", mutation)


def get_class():
    return DagAddStep
