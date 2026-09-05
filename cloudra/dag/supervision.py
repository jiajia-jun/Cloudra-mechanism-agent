"""Supervisor trigger coalescing, run lifecycle, and report delivery."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from cloudra.dag.models import OrchestrationMode
from cloudra.services import session_store

logger = logging.getLogger(__name__)


def _short_tool_rationale(tool_name: str, arguments: dict[str, Any]) -> str:
    """Wake-payload snippet from a delivery-write tool's arguments."""
    bits = [tool_name]
    for key in (
        "rationale", "label", "node_id", "element_id", "edge_id",
        "role", "source_node_id", "target_node_id",
    ):
        value = arguments.get(key)
        if value:
            bits.append(f"{key}={value}")
    return " ".join(bits)


class SupervisionMixin:
    """督导触发收口（D14 合并唤醒）与督导运行生命周期；由 DagController 组合。"""

    async def _trigger_supervisor_after_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        success: bool,
    ) -> None:
        """非观察工具（dag_* 编排面）结束后的 Supervisor 唤醒口，按优先级取一。

        触发口（按 tool_name 映射，不嗅探 action）：
        1. dag_propose_mechanism 被接受/落草稿 → mechanism_proposed（附 rationale）；
        2. Coordinator 的机理图变更被接受 → delivery_updated（附 arguments 摘要）；
        3. dag_message_supervisor 成功 → coordinator_message。
        观察类工具的唤醒走收件箱（tool_call_review，见 on_tool_finished）。
        """
        if self.supervisor is None:
            return
        accepted = bool(result.get("accepted"))
        # guided 模式下提案成功也返回 accepted=False（草稿落 open 等督导裁决），
        # 唤醒判据是"草稿已落库"（内层 result.draft_id），不是科学接受。
        inner = result.get("result")
        draft_recorded = accepted or (
            isinstance(inner, dict) and bool(inner.get("draft_id"))
        )
        if tool_name == "dag_propose_mechanism" and success and draft_recorded:
            await self.maybe_supervise(
                "mechanism_proposed",
                coordinator_request=str(arguments.get("rationale") or ""),
            )
            return
        if (
            tool_name in {
                "dag_add_species",
                "dag_add_step",
                "dag_update_delivery_element",
            }
            and accepted
        ):
            await self.maybe_supervise(
                "delivery_updated",
                coordinator_request=_short_tool_rationale(tool_name, arguments),
            )
            return
        if tool_name == "dag_message_supervisor" and success:
            msg = str(arguments.get("message") or "").strip()
            if msg:
                await self.maybe_supervise(
                    "coordinator_message", coordinator_request=msg
                )
            return

    async def _wake_supervisor_for_reviews(self) -> None:
        """D5/D14：入箱才唤醒，唤醒按 conversation 合并；附待审清单让
        Supervisor 不用猜 review_id。"""
        pending = await asyncio.to_thread(self.store.list_call_reviews)
        lines = [
            f"- {row.review_id}: {row.tool_name} "
            f"({'ok' if row.is_success else 'FAILED'}) "
            f"by {row.caller_legacy_id or row.caller_role_id or 'unknown'}"
            + (f" [job {row.compute_job_id}]" if row.compute_job_id else "")
            + (f" source={row.source_path}" if row.source_path else "")
            + (f" kind={row.result_kind}" if row.result_kind and row.result_kind != "ok" else "")
            + (f" → {row.suggested_target_id}.{row.suggested_stage}" if row.suggested_target_id and row.suggested_stage else "")
            for row in pending[:12]
        ]
        await self.maybe_supervise(
            "tool_call_review",
            coordinator_request="Pending call reviews:\n" + "\n".join(lines),
        )

    # D14 唤醒合并：按 conversation 共享的督导状态——运行中或已有排队触发的
    # 事件折叠进下一次运行，不再一个事件拉起一整轮 LLM 督导（证据 g）。
    _SUPERVISION_STATES: dict[str, dict[str, Any]] = {}

    @classmethod
    def _supervision_state(cls, conversation_id: str) -> dict[str, Any]:
        state = cls._SUPERVISION_STATES.get(conversation_id)
        if state is None:
            state = {"lock": asyncio.Lock(), "pending": []}
            cls._SUPERVISION_STATES[conversation_id] = state
        return state

    async def maybe_supervise(
        self, trigger: str, coordinator_request: str | None = None
    ):
        allowed_triggers = {
            "tool_call_review",
            "mechanism_proposed",
            "delivery_updated",
            "coordinator_message",
            "user_replan",
            "pre_delivery",
        }
        if (
            self.mode is not OrchestrationMode.DAG_GUIDED
            or self.supervisor is None
            or trigger not in allowed_triggers
        ):
            return None
        await self.initialize()
        state = self._supervision_state(self.conversation_id)
        if state["lock"].locked():
            # 督导运行中：触发折叠进紧随其后的合并运行
            state["pending"].append(trigger)
            return None
        async with state["lock"]:
            result = await self._run_supervision(trigger, coordinator_request)
            while state["pending"]:
                folded = sorted(set(state["pending"]))
                state["pending"].clear()
                note = (
                    "coalesced triggers: " + ", ".join(folded)
                    if len(folded) > 1
                    else None
                )
                result = await self._run_supervision(folded[0], note)
            return result

    async def _run_supervision(
        self, trigger: str, coordinator_request: str | None = None
    ):
        # UI 投影回调永远 best-effort：投影故障（如壳会话 spawn 被拒）不能
        # 杀死督导本身，更不能连带打崩父 agent 的 turn。
        if self.on_supervision is not None:
            try:
                await self.on_supervision("start", trigger, None, None)
            except Exception as exc:
                logger.warning("[DagController] on_supervision(start) failed: %s", exc)
        run_session_id = await asyncio.to_thread(
            self._register_supervisor_session, trigger, coordinator_request
        )
        event_sink = None
        if run_session_id is not None:
            # 运行过程写进 supervisor 自己的 session 事件流：
            # TUI 选中它的 session 行即可看到推理与 dag_* 工具调用。
            async def event_sink(event_type: str, data: dict) -> None:
                await session_store.arecord_event(self.db, run_session_id, event_type, data)

        error_note: str | None = None
        result = None
        try:
            result = await self.supervisor.run(
                trigger,
                coordinator_request=coordinator_request,
                session_id=self.session_id,
                event_sink=event_sink,
            )
            # Supervisor 可能经工具加严过 coverage contract，重新载入。
            # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
            self.contract = await asyncio.to_thread(self.store.load_coverage_contract)
        except Exception as exc:  # Supervisor 是顾问角色：故障不炸 Coordinator 循环
            error_note = str(exc)
            logger.warning("[DagController] supervisor run failed (%s): %s", trigger, exc)
        if result is not None:
            try:  # 投递失败不炸督导：报告仍在 result/会话记录里
                await self._deliver_supervisor_report(trigger, result.report)
            except Exception as exc:
                logger.warning("[DagController] supervisor report delivery failed: %s", exc)
        await asyncio.to_thread(
            self._finalize_supervisor_session, run_session_id, trigger, result, error_note
        )
        if self.on_supervision is not None:
            try:
                await self.on_supervision("finish", trigger, result, error_note)
            except Exception as exc:
                logger.warning("[DagController] on_supervision(finish) failed: %s", exc)
        return result

    async def _deliver_supervisor_report(self, trigger: str, report: str) -> None:
        """督导结论回投 Coordinator（v2 反馈环的唯一投递口）。

        报告 pin 进 ``core.notices``（key="supervisor"，常驻且覆盖旧建议），
        下一轮 turn_pipeline collect pins 时注入 Coordinator 的 LLM 上下文。
        触发方不是 Coordinator 自己（子 Agent / API user_replan，legacy
        agent_id 非 a-0）时 Coordinator 可能在休眠，再经 ``agent.message``
        投递同一文本唤醒（与 ReminderBroker 同一模式，终态 agent 自动
        reopen）；Coordinator 自己的工具循环同步 await 督导，下轮自然读到
        pin，重复发消息只会在时间线上多一条冗余行。

        没有 core 句柄的调用方（api_v2 的 user_replan 直连 DagController）
        触达不到内存 notices——其驳回理由仍经 DAG 投影的 rejected_draft
        在下轮可见，HTTP 响应也已把督导摘要回给用户。
        """
        text = (report or "").strip()
        if not text:
            return
        core = self._core
        if core is None:
            logger.info(
                "[DagController] no runtime core handle; supervisor report (%s) "
                "reaches the Coordinator via the DAG projection instead",
                trigger,
            )
            return
        coordinator = next(
            (
                agent
                for agent in core.agents.values()
                if agent.project_id == self.conversation_id
                and agent.role_id == "coordinator"
            ),
            None,
        )
        if coordinator is None:
            logger.info(
                "[DagController] no coordinator agent in project %s; "
                "supervisor report not delivered",
                self.conversation_id,
            )
            return
        content = f"[Supervisor] ({trigger}) {text}"
        core.notices.pin(coordinator.id, "supervisor", content)
        if self.agent_id == "a-0":
            return
        try:
            from cloudra.runtime_v2.commands import CommandBus
            from cloudra.runtime_v2.schemas import Command

            await CommandBus(core).execute(
                Command(
                    type="agent.message",
                    target={"session_id": coordinator.id},
                    payload={"content": content},
                    actor="system",
                )
            )
        except Exception as exc:  # 唤醒失败不炸督导：pin 已在，下轮仍可读
            logger.warning("[DagController] supervisor wake message failed: %s", exc)

    def _register_supervisor_session(
        self, trigger: str, coordinator_request: str | None
    ) -> str | None:
        """把一次 Supervisor 触发登记为子 Agent 会话：侧栏可见、状态实时流转。

        上下文文件本身由 SupervisorAgent 的 JSONL 消息历史持久化（会话级），
        这里只补 session 记录让 UI 能列出它；登记失败不影响督导本身。
        """
        session_id = f"supervisor_{datetime.now(timezone.utc).isoformat()}"
        query = trigger
        if coordinator_request:
            query = f"{trigger}: {coordinator_request.splitlines()[0]}"
        try:
            session_store.create_session_record(
                self.db,
                session_id=session_id,
                agent_id="supervisor",
                agent_type="supervisor",
                parent_session_id=self.session_id,
                query=query,
                created_at=datetime.now(timezone.utc).isoformat(),
                orchestration_mode=self.mode.value,
            )
        except Exception as exc:
            logger.warning("[DagController] supervisor session 登记失败（已忽略）: %s", exc)
            return None
        return session_id

    def _finalize_supervisor_session(
        self,
        session_id: str | None,
        trigger: str,
        result,
        error_note: str | None,
    ) -> None:
        if not session_id:
            return
        state = "failed" if error_note else "finished"
        summary = error_note or ""
        if result is not None:
            accepted = sum(1 for m in result.mutations if m.get("accepted"))
            summary = (
                f"trigger={trigger} rounds={result.rounds} "
                f"mutations={accepted}/{len(result.mutations)}"
            )
            if result.note:
                summary += f" note={result.note}"
            report = getattr(result, "report", "") or ""
            if report.strip():
                summary += f" | {report.strip()}"
        try:
            session_store.finalize_session(
                self.db,
                session_id,
                state,
                result=summary or None,
                error=error_note,
            )
        except Exception as exc:
            logger.warning("[DagController] supervisor session 终态落库失败（已忽略）: %s", exc)
