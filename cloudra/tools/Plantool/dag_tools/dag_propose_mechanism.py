"""dag_propose_mechanism: Coordinator submits a mechanism draft + stage contracts."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import input_schema
from cloudra.dag.controller import DagController
from cloudra.dag.models import OrchestrationMode
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail
from cloudra.tools.Plantool.dag_tools.proposal_inputs import (
    ProposalSpeciesInput,
    ProposalStepInput,
)


class DagProposeMechanismInput(input_schema):
    rationale: str = Field(
        min_length=1,
        description="Mechanism hypothesis reasoning (literature/mapping basis).",
    )
    species: list[ProposalSpeciesInput] = Field(
        default_factory=list,
        description="Declarative list of system state species: [{'name': '...', 'smiles': '...'}].",
    )
    steps: list[ProposalStepInput] = Field(
        default_factory=list,
        description="Declarative list of transformation steps: [{'name': '...', 'from': '...', 'to': '...'}].",
    )
    delivery_targets: list[str] | None = Field(
        default=None,
        description=(
            "Species or step names/IDs included in this delivery. Selected step "
            "endpoints are included automatically. Omit for exploratory proposals "
            "that leave the accepted delivery scope unchanged. In dag_guided, "
            "newly declared targets already count at the final gate while review is open."
        ),
    )


class DagProposeMechanism(DagToolBase):
    tool_id: str = "t-dag-propose"
    tool_name: str = "dag_propose_mechanism"
    tool_description: str = (
        "Propose the mechanism: declarative species states and transformation steps "
        "(Coordinator in dag_record or dag_guided). "
        "Use for: the first delivery artifact of a mechanism study. "
        "The proposed graph is available for computation before Supervisor "
        "acceptance; acceptance records the working hypothesis (Supervisor in "
        "dag_guided; auto-accepted in dag_record). "
        "Input shape: {rationale, species: [{name, smiles}], steps: [{name, from, to}], "
        "delivery_targets?: [species or step name/ID]}. Existing species may be "
        "named in new steps; delivery_targets alone updates the selected scope. "
        "In dag_guided, pending scope expansion blocks final delivery against "
        "the old scope until reviewed; exploration without targets does not. "
        "Names must resolve uniquely within the delivery graph."
    )
    input_schema: Any = DagProposeMechanismInput
    output_schema: Any = DagToolOutput
    subagent: ToolActorContext | None = None

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
                rationale=user_input.rationale,
                species=[s.model_dump(mode="json", exclude_unset=True) for s in user_input.species],
                steps=[st.model_dump(mode="json", by_alias=True, exclude_unset=True) for st in user_input.steps],
                delivery_targets=user_input.delivery_targets,
                actor_id=self._actor_id(),
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception("Mechanism proposal failed")
            return fail("dag_propose_mechanism", str(exc), accepted=False)
        return DagToolOutput(
            is_success=True,
            action="dag_propose_mechanism",
            # ``accepted`` is the draft review state. It does not assert that
            # the mechanism is scientifically correct.
            accepted=bool(proposed.get("accepted")),
            result=proposed,
        )


def get_class():
    return DagProposeMechanism
