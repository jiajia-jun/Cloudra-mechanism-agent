"""dag_set_coverage_contract: SetCoverageContract or WaiveGate (supervisor-gated)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import (
    CoverageContract,
    CoverageWaiver,
    GraphActor,
    OrchestrationMode,
    SetCoverageContract,
    WaiveGate,
)
from cloudra.tools.Plantool.dag_tools._common import (
    DagToolBase,
    DagToolOutput,
    fail,
    mutation_output,
)


class DagSetCoverageContractInput(input_schema):
    contract: dict[str, Any] | None = Field(
        default=None,
        description="Nested CoverageContract dict. Ignored when a waiver/gate_code is present.",
    )
    required_node_level: str | None = Field(
        default=None, description="CoverageContract.required_node_level override."
    )
    required_edge_level: str | None = Field(
        default=None, description="CoverageContract.required_edge_level override."
    )
    require_branch_disposition: bool | None = Field(
        default=None, description="CoverageContract.require_branch_disposition override."
    )
    require_thermochemistry: bool | None = Field(
        default=None,
        description="CoverageContract.mechanism_default require_thermochemistry flag.",
    )
    waiver: dict[str, Any] | None = Field(
        default=None,
        description="Nested CoverageWaiver dict. Presence (or gate_code) selects WaiveGate.",
    )
    gate_code: str | None = Field(
        default=None, description="Waiver gate code (selects WaiveGate when set)."
    )
    target_type: Literal["graph", "node", "edge"] | None = Field(
        default=None, description="Waiver target_type."
    )
    target_id: str | None = Field(default=None, description="Waiver target_id.")
    rationale: str | None = Field(
        default=None, description="Waiver rationale (required for WaiveGate)."
    )


class DagSetCoverageContract(DagToolBase):
    tool_id: str = "t-dag-contract"
    tool_name: str = "dag_set_coverage_contract"
    tool_description: str = (
        "Set or strengthen the delivery coverage contract via flat fields or a contract dict "
        "(Supervisor only in dag_record or dag_guided). "
        "Use for: raising required evidence levels or mechanism defaults. "
        "Do not use for: waiving or lowering gates — USER-only and engine rejects Supervisor waive; "
        "Coordinator or sub-agent calls. "
        "Key discipline: coverage can only be strengthened here; weakening requires explicit user action."
    )
    input_schema: Any = DagSetCoverageContractInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    async def tool_call(
        self, user_input: DagSetCoverageContractInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        ctx = await self._prepare(session)
        if ctx.actor is not GraphActor.SUPERVISOR:
            return fail(
                "dag_set_coverage_contract",
                "dag_set_coverage_contract is supervisor-only",
            )
        waive = user_input.waiver is not None or bool(user_input.gate_code)
        has_contract = (
            user_input.contract is not None
            or user_input.require_thermochemistry is not None
            or user_input.required_node_level is not None
            or user_input.required_edge_level is not None
            or user_input.require_branch_disposition is not None
        )
        if not waive and not has_contract:
            return fail(
                "dag_set_coverage_contract",
                "dag_set_coverage_contract requires contract fields or a waiver/gate_code",
            )
        if waive:
            raw = dict(user_input.waiver or {})
            gate_code = user_input.gate_code or raw.get("gate_code")
            target_type = user_input.target_type or raw.get("target_type")
            target_id = user_input.target_id or raw.get("target_id")
            rationale = user_input.rationale or raw.get("rationale") or ""
            missing = [
                name
                for name, value in (
                    ("gate_code", gate_code),
                    ("target_type", target_type),
                    ("target_id", target_id),
                    ("rationale", rationale),
                )
                if not value
            ]
            if missing:
                return fail(
                    "dag_set_coverage_contract",
                    f"waive_gate requires: {', '.join(missing)}",
                )
            op = WaiveGate(
                op="waive_gate",
                waiver=CoverageWaiver(
                    gate_code=str(gate_code),
                    target_type=target_type,
                    target_id=str(target_id),
                    user_id=self._actor_id(),
                    session_id=session.id,
                    rationale=str(rationale),
                ),
            )
        else:
            contract = _build_contract(user_input)
            op = SetCoverageContract(op="set_coverage_contract", contract=contract)
        _, mutation = await self._apply(
            session,
            [op],
            rationale=user_input.rationale or "update coverage contract",
            prepared=ctx,
        )
        return mutation_output("dag_set_coverage_contract", mutation)


def _build_contract(user_input: DagSetCoverageContractInput) -> CoverageContract:
    if user_input.contract:
        return CoverageContract.model_validate(user_input.contract)
    fields: dict[str, Any] = {}
    if user_input.require_thermochemistry is not None:
        fields["require_thermochemistry"] = user_input.require_thermochemistry
    if user_input.required_node_level is not None:
        fields["required_node_level"] = user_input.required_node_level
    if user_input.required_edge_level is not None:
        fields["required_edge_level"] = user_input.required_edge_level
    if user_input.require_branch_disposition is not None:
        fields["require_branch_disposition"] = user_input.require_branch_disposition
    base = CoverageContract.mechanism_default(
        require_thermochemistry=bool(fields.get("require_thermochemistry", False)),
    )
    extra = {k: v for k, v in fields.items() if k != "require_thermochemistry"}
    return base.model_copy(update=extra) if extra else base


def get_class():
    return DagSetCoverageContract
