"""Supervisor notification triggers (event-driven, non-blocking).

本模块只做一件事：生产端把待办持久化之后，按状态表通知项目的真实
Supervisor agent（runtime_v2/supervision.py 的 notify_supervisor）。
督导是项目内唯一的普通 runtime_v2 agent，其生命周期就是自身事件流，
裁决反馈经普通子 agent 完成回传（parent=Coordinator）到达。
"""

from __future__ import annotations

import logging
from typing import Any

from cloudra.dag.models import OrchestrationMode

logger = logging.getLogger(__name__)


class SupervisionMixin:
    """督导通知收口（持久化 + notify，不等待裁决）；由 DagController 组合。"""

    async def _notify_supervisor(self, reason: str) -> None:
        """持久化待办就位后的非阻塞通知。

        通知失败不回滚已落库的待办（reconcile_supervision 会在项目装载时
        补通知）；没有 core 句柄的调用方（直连 DagController 的测试）只记
        debug。
        """
        core = self._core
        if core is None:
            logger.debug(
                "[DagController] backlog persisted (%s); no runtime core handle, "
                "supervisor notification deferred to reconcile",
                reason,
            )
            return
        try:
            from cloudra.runtime_v2.supervision import notify_supervisor

            await notify_supervisor(core, self.conversation_id, reason=reason)
        except Exception:
            logger.warning(
                "[DagController] supervisor notification failed (%s); the "
                "persisted backlog remains for reconcile",
                reason,
                exc_info=True,
            )

    async def _trigger_supervisor_after_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        success: bool,
    ) -> None:
        """非观察工具（dag_* 编排面）结束后的 Supervisor 通知口。

        触发口（按 tool_name 映射，不嗅探 action）：
        1. dag_propose_mechanism 草稿落库 → 通知（草稿即持久化待办
           dag_drafts open； guided 模式提案返回 accepted=False，判据是内层
           result.draft_id，不是科学接受）；
        2. dag_message_supervisor 成功 → 通知（纯文本与结构化请求都已落
           dag_review_requests，见 dag_message_supervisor 工具）。

        delivery_updated 不再是触发口（计划 §1/§5）：图变更本身已在 store
        变更日志里持久化，督导信箱只含显式送审/草稿/结构化请求三类；督导
        每次苏醒经 dag_view 投影总能看到最新图。观察类工具只登记证据
        （见 on_tool_finished），不产生通知。
        """
        if self.mode is not OrchestrationMode.DAG_GUIDED:
            return
        accepted = bool(result.get("accepted"))
        inner = result.get("result")
        draft_recorded = accepted or (
            isinstance(inner, dict) and bool(inner.get("draft_id"))
        )
        if tool_name == "dag_propose_mechanism" and success and draft_recorded:
            await self._notify_supervisor("mechanism draft proposed")
            return
        if tool_name == "dag_message_supervisor" and success:
            request_persisted = isinstance(inner, dict) and bool(inner.get("request_id"))
            if request_persisted or str(arguments.get("message") or "").strip():
                await self._notify_supervisor("coordinator message or review request")
            return
