"""dag_propose_mechanism: Coordinator submits a mechanism draft + stage contracts."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.controller import DagController
from cloudra.dag.models import OrchestrationMode, StageKind
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail
from cloudra.tools.Plantool.dag_tools.proposal_inputs import (
    ProposalOperation,
    ProposalSpeciesInput,
    ProposalStepInput,
)


class DagProposeMechanismInput(input_schema):
    rationale: str = Field(
        min_length=1,
        description="Mechanism hypothesis reasoning (literature/mapping basis).",
    )
    species: list[ProposalSpeciesInput] | None = Field(
        default=None,
        description="Declarative list of system state species: [{'name': '...', 'smiles': '...'}].",
    )
    steps: list[ProposalStepInput] | None = Field(
        default=None,
        description="Declarative list of transformation steps: [{'name': '...', 'from': '...', 'to': '...'}].",
    )
    operations: list[ProposalOperation] | None = Field(
        default=None,
        description="Delivery-only graph operations (legacy).",
    )
    stage_contracts: dict[str, list[StageKind]] = Field(
        default_factory=dict,
        description="Element id → ordered stage kinds (legacy).",
    )
    claim_spec: dict[str, Any] | None = Field(
        default=None,
        description="Optional scientific claim contract.",
    )
    contract_version: int = Field(default=1, ge=1)


class DagProposeMechanism(DagToolBase):
    tool_id: str = "t-dag-propose"
    tool_name: str = "dag_propose_mechanism"
    tool_description: str = (
        "Propose the mechanism: declarative species states and transformation steps "
        "(Coordinator in dag_record or dag_guided). "
        "Use for: the first delivery artifact of a mechanism study — no "
        "compute is unlocked until the draft is accepted (Supervisor in "
        "dag_guided; auto-accepted in dag_record). "
        "Input shape: {rationale: str, species: [{name, smiles}], steps: [{name, from, to}]}. "
        "Key discipline: species names and step names must be unique within the delivery graph."
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
            if user_input.species is not None or user_input.steps is not None:
                proposed = await controller.propose_mechanism(
                    rationale=user_input.rationale,
                    species=[s.model_dump(mode="json", exclude_unset=True) for s in (user_input.species or [])],
                    steps=[st.model_dump(mode="json", by_alias=True, exclude_unset=True) for st in (user_input.steps or [])],
                    actor_id=self._actor_id(),
                    claim_spec=user_input.claim_spec,
                    contract_version=user_input.contract_version,
                )
            else:
                proposed = await controller.propose_mechanism(
                    operations=[op.model_dump(mode="json", exclude_unset=True) for op in (user_input.operations or [])],
                    stage_contracts={key: [kind.value for kind in kinds] for key, kinds in user_input.stage_contracts.items()},
                    rationale=user_input.rationale,
                    actor_id=self._actor_id(),
                    claim_spec=user_input.claim_spec,
                    contract_version=user_input.contract_version,
                )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception("Mechanism proposal failed")
            return fail("dag_propose_mechanism", str(exc), accepted=False)
        return DagToolOutput(
            is_success=True,
            action="dag_propose_mechanism",
            # ``accepted`` describes the scientific draft admission result.
            # In guided mode a successful submission is still ``open`` until
            # the Supervisor accepts it; do not report transport success as
            # scientific acceptance.
            accepted=bool(proposed.get("accepted")),
            result=proposed,
        )


def get_class():
    return DagProposeMechanism
