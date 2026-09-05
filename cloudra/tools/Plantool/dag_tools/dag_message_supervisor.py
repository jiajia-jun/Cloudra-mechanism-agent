"""dag_message_supervisor: structured review request or plain Coordinator note."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema
from cloudra.core.agent import Agent
from cloudra.dag.models import GraphRef, OrchestrationMode
from cloudra.dag.review_requests import ReviewRequest
from cloudra.tools.Plantool.dag_tools._common import DagToolBase, DagToolOutput, fail


class DagMessageSupervisorInput(input_schema):
    message: str = Field(
        default="",
        description=(
            "Plain-text note to the Supervisor (Coordinator only), persisted as "
            "a queued exception review request. Use for simple appeals/blockers; "
            "for structured review requests provide kind/question/target_ids instead."
        ),
    )
    kind: Literal["draft", "evidence", "exception", "exit"] | None = Field(
        default=None,
        description=(
            "Structured request kind. evidence/exception may be sent by "
            "research Agents; draft/exit require the Coordinator."
        ),
    )
    question: str = Field(
        default="",
        description="Question the Supervisor should answer for a structured request.",
    )
    target_ids: list[str] = Field(
        default_factory=list,
        description="Delivery target node/edge ids this request concerns.",
    )
    evidence_refs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence GraphRef dicts supporting this request.",
    )
    counterevidence_refs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence GraphRef dicts that may contradict the request's claim.",
    )
    proposal: dict[str, Any] = Field(
        default_factory=dict,
        description="Proposal payload, required for exit requests.",
    )


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class DagMessageSupervisor(DagToolBase):
    tool_id: str = "t-dag-message"
    tool_name: str = "dag_message_supervisor"
    tool_description: str = (
        "Send a structured review request or a plain-text note to the "
        "Supervisor without changing the graph. Structured evidence/exception "
        "requests may be sent by any research Agent; draft/exit requests and "
        "legacy plain-text notes are Coordinator-only. "
        "Use for: requesting scientific review of a contradiction/exception, "
        "asking whether a method-limited result is acceptable, or reporting a "
        "blocker. "
        "Do not use for: binding stage evidence or resolving requests (Supervisor "
        "uses dag_review_evidence for that)."
    )
    input_schema: Any = DagMessageSupervisorInput
    output_schema: Any = DagToolOutput
    subagent: Agent = None

    @staticmethod
    def _is_coordinator(caller_type: str, caller_id: str) -> bool:
        return caller_type == "coordinator" or caller_id in ("a-0", "coordinator")

    async def tool_call(
        self, user_input: DagMessageSupervisorInput, session: Session
    ) -> DagToolOutput:
        if self._mode() is OrchestrationMode.STANDARD:
            return self._standard_disabled()
        caller_type = getattr(self.subagent, "type", "")
        caller_id = getattr(self.subagent, "id", "")
        if caller_type == "supervisor":
            return fail(
                "dag_message_supervisor",
                "message_supervisor is for research Agents/Coordinator; "
                "the Supervisor resolves requests with dag_review_evidence.",
            )
        is_coordinator = self._is_coordinator(caller_type, caller_id)
        kind = user_input.kind
        if kind is None:
            # Legacy plain-text path remains Coordinator-only.  §4 持久性契约：
            # 纯文本消息有正文、无法从 draft/review 推导，必须落持久化请求
            # （复用 ReviewRequest，kind="exception"），禁止只放内存消息。
            if not is_coordinator:
                return fail(
                    "dag_message_supervisor",
                    "plain message_supervisor is Coordinator-only; "
                    "structured evidence/exception requests can be sent with "
                    "kind='evidence' or kind='exception'.",
                )
            msg = (user_input.message or "").strip()
            if not msg:
                return fail(
                    "dag_message_supervisor",
                    "message_supervisor requires a non-empty message.",
                )
            try:
                ctx = await self._prepare(session)
                store = ctx.store
                request = ReviewRequest(
                    kind="exception",
                    requester=session.id,
                    target_ids=[],
                    question=msg,
                    basis_fingerprint="sha256:pending",
                )
                basis = await asyncio.to_thread(store.review_basis, request)
                request = request.model_copy(update={"basis_fingerprint": basis})
                request_id = await asyncio.to_thread(store.enqueue_review, request)
            except Exception as exc:
                return fail("dag_message_supervisor", str(exc), accepted=False)
            return DagToolOutput(
                is_success=True,
                action="dag_message_supervisor",
                accepted=True,
                # queued 语义：请求已持久化并排队等 Supervisor 裁决；本调用
                # 返回不代表裁决完成。
                result={
                    "request_id": request_id,
                    "kind": "exception",
                    "question": msg,
                    "basis_fingerprint": basis,
                    "enqueued": True,
                    "message": msg,
                },
            )
        # Structured request path.
        if kind in ("draft", "exit") and not is_coordinator:
            return fail(
                "dag_message_supervisor",
                f"{kind} review requests are Coordinator-only.",
            )
        question = (user_input.question or "").strip()
        if not question:
            return fail(
                "dag_message_supervisor",
                "a structured review request requires a non-empty question.",
            )
        if kind == "exit" and not {
            "disposition", "scope", "remaining_gaps", "method_limits"
        } <= set(user_input.proposal):
            return fail(
                "dag_message_supervisor",
                "exit requests require proposal.disposition/scope/remaining_gaps/method_limits",
            )
        try:
            ctx = await self._prepare(session)
            store = ctx.store
            supporting_refs = [
                GraphRef(**item) if isinstance(item, dict) else item
                for item in user_input.evidence_refs
            ]
            counter_refs = [
                GraphRef(**item) if isinstance(item, dict) else item
                for item in user_input.counterevidence_refs
            ]
            request = ReviewRequest(
                kind=kind,
                # Notifications must address the actual v2 session, not the
                # legacy role id; this is what lets a waiting runner wake.
                requester=session.id,
                target_ids=list(user_input.target_ids or []),
                question=question,
                supporting_refs=supporting_refs,
                counterevidence_refs=counter_refs,
                proposal=user_input.proposal,
                # The store adds the current graph/contract snapshot to the
                # fingerprint.  A request must not be resolvable after its
                # scoped evidence changes.
                basis_fingerprint="sha256:pending",
            )
            basis = await asyncio.to_thread(store.review_basis, request)
            request = request.model_copy(update={"basis_fingerprint": basis})
            request_id = await asyncio.to_thread(store.enqueue_review, request)
        except Exception as exc:
            return fail("dag_message_supervisor", str(exc), accepted=False)
        return DagToolOutput(
            is_success=True,
            action="dag_message_supervisor",
            accepted=True,
            result={
                "request_id": request_id,
                "kind": kind,
                "question": question,
                "basis_fingerprint": basis,
                "enqueued": True,
            },
        )


def get_class():
    return DagMessageSupervisor
