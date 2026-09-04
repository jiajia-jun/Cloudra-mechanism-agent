"""dag_propose_mechanism: Coordinator submits a mechanism draft + stage contracts."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.controller import DagController
from cloudra.dag.models import OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagProposeMechanismInput(input_schema):
    operations: list[dict[str, Any]] = Field(
        min_length=1,
        description=(
            "Delivery-only graph operations (add_node occurrence / add_edge "
            "elementary_step / update_node / update_edge) describing the "
            "mechanism hypothesis. Each operation is a plain object like "
            '{"op": "add_node", "graph": "delivery", "node": {"node_id": ..., '
            '"node_type": "occurrence", "label": ..., "role": ...}}.'
        ),
    )
    stage_contracts: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Element id → ordered stage kinds the element needs. Occurrence "
            "stages: geometry, frequency, single_point. Elementary-step stages: "
            "ts_guess (advisory), ts_opt, frequency, short_irc, endpoint_a, "
            "endpoint_b, direction, identity, thermochemistry. List order IS "
            "the allowed bind order; every id must be added by this draft."
        ),
    )
    rationale: str = Field(
        min_length=1,
        description="Mechanism hypothesis reasoning (literature/mapping basis).",
    )
    claim_spec: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional v2 scientific claim contract: kind, quantity, unit, "
            "reference/scope, required_checks and optional_checks."
        ),
    )
    contract_version: int = Field(default=1, ge=1)


class DagProposeMechanism(DagToolBase):
    tool_id: str = "t-dag-propose"
    tool_name: str = "dag_propose_mechanism"
    tool_description: str = (
        "Propose the mechanism: a delivery-graph draft plus per-element stage "
        "contracts (Coordinator in dag_record or dag_guided). "
        "Use for: the first delivery artifact of a mechanism study — no "
        "compute is unlocked until the draft is accepted (Supervisor in "
        "dag_guided; auto-accepted in dag_record). "
        "Do not use for: process/scheduling writes; pre-declaring stage "
        "states (all stages start pending and are bound by the harness). "
        "Key discipline: you choose which stages each element needs; binds "
        "are sequential in contract order."
    )
    input_schema: Any = DagProposeMechanismInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagProposeMechanismInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        if self._actor_id() != "a-0":
            return fail(
                "dag_propose_mechanism",
                "only the Coordinator proposes mechanisms; sub-agents report "
                "results and let the Coordinator design the graph",
                accepted=False,
            )
        ctx = await self._prepare(session)
        controller = DagController(
            ctx.db, session.id, ctx.mode, conversation_id=ctx.conversation_id
        )
        try:
            proposed = await controller.propose_mechanism(
                operations=user_input.operations,
                stage_contracts=user_input.stage_contracts,
                rationale=user_input.rationale,
                actor_id=self._actor_id(),
                claim_spec=user_input.claim_spec,
                contract_version=user_input.contract_version,
            )
        except Exception as exc:
            # 契约引用不完整/词表不符/落图被拒等确定性拒绝，原文回报给模型自纠
            return fail("dag_propose_mechanism", str(exc), accepted=False)
        return DagToolOutput(
            is_success=True,
            action="dag_propose_mechanism",
            accepted=True,
            result=proposed,
        )


def get_class():
    return DagProposeMechanism
