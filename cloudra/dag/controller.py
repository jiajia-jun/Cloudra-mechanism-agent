"""Mode-aware harness integration for durable tool evidence and DAG prompts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cloudra.dag.completion import build_projection, evaluate_delivery
from cloudra.dag.drafts import DraftsMixin
from cloudra.dag.engine import DagEngine
from cloudra.dag.evidence_inbox import EvidenceInboxMixin, enqueue_compute_review
from cloudra.dag.models import (
    CoverageContract,
    OrchestrationMode,
    normalize_orchestration_mode,
)
from cloudra.dag.stop_audit import StopAuditMixin
from cloudra.dag.store import DagStore
from cloudra.dag.supervision import SupervisionMixin
from cloudra.persistence.database import ConversationDB

__all__ = ["DagController", "enqueue_compute_review"]


class DagController(SupervisionMixin, StopAuditMixin, EvidenceInboxMixin, DraftsMixin):
    """Deterministic harness writer. Chemistry tools themselves remain stateless."""

    def __init__(
        self,
        db: ConversationDB,
        session_id: str,
        mode: str | OrchestrationMode,
        *,
        conversation_id: str | None = None,
        working_directory: str | Path | None = None,
        agent_id: str | None = None,
        role_id: str | None = None,
        core=None,
    ):
        self.db = db
        self.session_id = session_id
        self.mode = normalize_orchestration_mode(mode)
        self.conversation_id = conversation_id or db.conversation_id or "default"
        # 变更日志与 CallReview sidecar 使用的 actor id（legacy a-N 词表）
        self.agent_id = agent_id
        # v2 role_id（CallReview sidecar 用；legacy a-N 由单一映射推出，D13）
        self.role_id = role_id
        # runtime_v2 RuntimeCore 句柄（可选）：_has_pending_background 的
        # v2-native 信号（core.agents 投影 + ReminderBroker 投影，D8.2）
        self._core = core
        self.working_directory = (
            Path(working_directory).expanduser().resolve()
            if working_directory is not None
            else None
        )
        self.store = DagStore(db)
        self.engine = DagEngine(self.store)
        self.contract = CoverageContract.mechanism_default()
        self._initialized = False

    @property
    def enabled(self) -> bool:
        return self.mode is not OrchestrationMode.STANDARD

    async def initialize(self) -> None:
        """加载图存储与覆盖契约；不自动拉起 Supervisor。

        用户追加消息/唤醒会重开 agent run，轮管道经 DagPolicyStage 再次调到
        ``initialize()``。督导通知全部由 ``_trigger_supervisor_after_tool``
        （提案/显式送审/督导消息的完成钩子）/ 退出审查请求 /
        ``user_replan`` 在持久化后发出。
        """
        if not self.enabled or self._initialized:
            return
        await asyncio.to_thread(self.store.ensure_bundle, self.session_id)
        self.contract = await asyncio.to_thread(self.store.load_coverage_contract)
        self._initialized = True

    async def mechanism_accepted(self) -> bool:
        """D4：是否存在已接受的机理草稿（唯一判据，随库存续）。"""
        if not self.enabled:
            return True
        await self.initialize()
        # 同步 sqlite 读走 worker 线程，busy 等待不占事件循环
        return await asyncio.to_thread(self.store.has_accepted_draft)

    async def check_substantive_gate(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[str, str] | None:
        """实质性计算前的 DAG 门槛（Phase 3：唯一门槛 = mechanism_accepted）。

        返回 ``None`` 表示放行；``("block", msg)`` 硬拒绝。机理草稿被接受
        之前拦截计算入口（submit_compute_job/qm_input_writer/ts_guess 计算型
        mode 等，词表在 registry 的 dag_compute_entry）；检索/读取/机理
        提案工具始终放行；standard 模式无门槛。
        """
        from cloudra.dag.substantive_gate import (
            GUIDED_BLOCK_MESSAGE,
            RECORD_BLOCK_MESSAGE,
            is_compute_entry_tool,
        )

        if not self.enabled or not is_compute_entry_tool(tool_name, arguments):
            return None
        if await self.mechanism_accepted():
            return None
        if self.mode is OrchestrationMode.DAG_GUIDED:
            return "block", GUIDED_BLOCK_MESSAGE
        return "block", RECORD_BLOCK_MESSAGE

    async def prompt_projection(self) -> str:
        if not self.enabled:
            return ""
        await self.initialize()
        self.contract = await asyncio.to_thread(self.store.load_coverage_contract)
        # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        history = await asyncio.to_thread(self.engine.history, limit=8)
        # 与 dag_view 同一口径：只有 source="explicit" 的显式送审行是可消费
        # 待办；legacy_auto/auto 行保留审计但永不可消费，不能投成"pending"。
        reviews = await asyncio.to_thread(
            self.store.list_call_reviews, "pending", source="explicit"
        )
        pending = [
            {
                "review_id": row.review_id,
                "tool_name": row.tool_name,
                "is_success": row.is_success,
                "caller": row.caller_legacy_id or row.caller_role_id,
                "source_path": row.source_path,
                "result_kind": row.result_kind,
                # §5：送审主张随投影给 Coordinator/Supervisor——裁决围绕 claim，
                # 撤销/重提也要对着它说。
                "claim": row.claim,
                **(
                    {"target": f"{row.suggested_target_id}.{row.suggested_stage}"}
                    if row.suggested_target_id
                    else {}
                ),
                **(
                    {"compute_job_id": row.compute_job_id}
                    if row.compute_job_id
                    else {}
                ),
            }
            for row in reviews
        ]
        # 最近被驳回的机理草稿：驳回理由随投影回给 Coordinator（open 草稿
        # 优先于已裁决草稿——有新草稿在审时驳回即已被修订响应）。
        rejected_draft = None
        draft = await asyncio.to_thread(self.store.latest_draft)
        if draft and draft["state"] == "rejected" and (draft["reject_reason"] or "").strip():
            rejected_draft = {
                "draft_id": draft["draft_id"],
                "rationale": draft["rationale"],
                "reject_reason": draft["reject_reason"],
            }
        projection = build_projection(
            snapshot,
            mode=self.mode,
            contract=self.contract,
            history=history,
            pending_reviews=pending,
            rejected_draft=rejected_draft,
        )
        return projection.to_prompt_text(actor_id=self.agent_id)

    def delivery_report(self):
        if not self.enabled:
            return None
        # store 是权威：督导中途收紧契约后，stop 不得继续吃 initialize 缓存。
        self.contract = self.store.load_coverage_contract()
        claim = self.store.accepted_claim_spec()
        facts = {
            target: self.store.facts_for_target(target)
            for target in (
                set(claim.scope.get("targets", [])) | set(claim.reference.get("targets", []))
                if claim is not None else set()
            )
        }
        return evaluate_delivery(
            self.engine.snapshot().delivery,
            self.contract,
            claim_kind=claim.kind.value if claim is not None else None,
            claim_spec=claim,
            evidence_facts=facts,
        )
