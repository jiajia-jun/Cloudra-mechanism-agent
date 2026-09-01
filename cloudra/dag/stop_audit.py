"""Stop-time delivery coverage audit and partial-disposition recording."""

from __future__ import annotations

import asyncio

from cloudra.dag.models import OrchestrationMode


class StopAuditMixin:
    """stop 交付门禁（audit_stop）与未审计 partial 落账；由 DagController 组合。"""

    async def _has_pending_background(self) -> bool:
        """会话级后台是否还有未竟工作（子任务/计算/定时提醒）。

        与 runner._count_pending_tasks 同一判定口径：只要后台未排空，
        stop 就是"挂起等唤醒"而不是交付。D8.2：子 agent 与提醒读
        v2-native 信号（core.agents 投影 + ReminderBroker 事件投影）——
        旧 scheduled_reminders/subagent_requests 表已删除，不存在遗留盲区；
        compute_jobs 仍是权威，但已迁到中央 compute.db（按 conversation_id 过滤本会话）。
        """
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.compute_store import acount_pending_compute_jobs

        if await acount_pending_compute_jobs(
            ComputeDB(data_dir=self.db.data_dir), self.conversation_id
        ):
            return True
        core = self._core
        if core is None:
            return False
        terminal = {"succeeded", "failed", "cancelled"}
        if any(
            agent.id != self.session_id
            and agent.project_id == self.conversation_id
            and agent.state.value not in terminal
            for agent in core.agents.values()
        ):
            return True
        return bool(core.reminders.pending(self.session_id))

    async def record_unaudited_partial(self) -> None:
        """D8.3：非 stop 的运行结束（最终消息路径）自动落 partial。

        complete 只能来自被审计的显式 stop；只对 Coordinator（a-0）记录，
        子 agent 的运行结束不构成交付。
        """
        if not self.enabled or self.agent_id != "a-0":
            return
        await self.initialize()
        report = await asyncio.to_thread(self.delivery_report)
        await asyncio.to_thread(
            self.store.record_delivery_disposition,
            self.session_id,
            "partial",
            report,
        )

    async def audit_stop(self, disposition: str):
        if not self.enabled:
            return True, None
        await self.initialize()
        if await self._has_pending_background():
            # 挂起而非交付：后台还有计算/提醒/子任务在跑，stop 只是休眠等唤醒。
            # 不做交付审计、不记录 disposition——否则 agent 会把 partial 当
            # "暂停"用，污染交付审计轨迹；真正的交付审计发生在后台排空后的
            # 最终 stop。
            return True, None
        report = self.delivery_report()
        if disposition == "complete" and not report.complete:
            if self.mode is OrchestrationMode.DAG_GUIDED:
                await self.maybe_supervise("pre_delivery")
                report = self.delivery_report()
            if not report.complete:
                return False, report
        # 同步写 dag_delivery_dispositions 不能在事件循环线程上执行，offload 到 worker 线程
        await asyncio.to_thread(
            self.store.record_delivery_disposition,
            self.session_id,
            disposition,
            report,
        )
        return True, report
