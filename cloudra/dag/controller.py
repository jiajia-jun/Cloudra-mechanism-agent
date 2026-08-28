"""Mode-aware harness integration for durable tool evidence and DAG prompts."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cloudra.dag.completion import build_projection, evaluate_delivery
from cloudra.dag.delta import DeliveryDelta
from cloudra.dag.engine import (
    DagEngine,
    _Rejected,
    apply_stage_verdict,
)
from cloudra.dag.models import (
    ELEMENTARY_STEP_STAGE_KINDS,
    OCCURRENCE_STAGE_KINDS,
    AddEdge,
    AddNode,
    AttachRef,
    CallReview,
    CoverageContract,
    GraphActor,
    GraphKind,
    GraphOperation,
    GraphRef,
    MechanismDraft,
    MutationBatch,
    MutationResult,
    OrchestrationMode,
    StageContract,
    StageKind,
    StageState,
    StageStatus,
    UpdateEdge,
    UpdateNode,
    derive_evidence_level,
    normalize_orchestration_mode,
    parse_graph_operation,
)
from cloudra.dag.store import DagStore, InvalidGraphReference, _canonical_json
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.tools.capabilities import (
    evidence_deriver_for,
    is_dag_observable,
    is_dag_reviewed,
)

logger = logging.getLogger("DagController")

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


class DagController:
    """Deterministic harness writer. Chemistry tools themselves remain stateless."""

    def __init__(
        self,
        db: ConversationDB,
        session_id: str,
        mode: str | OrchestrationMode,
        *,
        conversation_id: str | None = None,
        working_directory: str | Path | None = None,
        supervisor=None,
        agent_id: str | None = None,
        role_id: str | None = None,
        on_supervision=None,
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
        self.supervisor = supervisor
        # 可选观察钩子：async (phase, trigger, result, error_note)；
        # runtime_v2 的 dag_stage 用它把督导运行投影成一个壳 agent 会话。
        self.on_supervision = on_supervision
        self._initialized = False

    @property
    def enabled(self) -> bool:
        return self.mode is not OrchestrationMode.STANDARD

    async def initialize(self) -> None:
        """加载图存储与覆盖契约；不自动拉起 Supervisor。

        用户追加消息/唤醒会重开 agent run，轮管道经 DagPolicyStage 再次调到
        ``initialize()``。督导唤醒全部由 ``_trigger_supervisor_after_tool`` /
        收件箱 / ``user_replan`` / ``pre_delivery`` 显式触发。
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
        # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        history = await asyncio.to_thread(self.engine.history, limit=8)
        reviews = await asyncio.to_thread(self.store.list_call_reviews)
        pending = [
            {
                "review_id": row.review_id,
                "tool_name": row.tool_name,
                "is_success": row.is_success,
                "caller": row.caller_legacy_id or row.caller_role_id,
                "source_path": row.source_path,
                "result_kind": row.result_kind,
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
        return evaluate_delivery(self.engine.snapshot().delivery, self.contract)

    async def _has_pending_background(self) -> bool:
        """会话级后台是否还有未竟工作（子任务/计算/定时提醒）。

        与 runner._count_pending_tasks 同一判定口径：只要后台未排空，
        stop 就是"挂起等唤醒"而不是交付。D8.2：子 agent 与提醒读
        v2-native 信号（core.agents 投影 + ReminderBroker 事件投影）——
        旧的 scheduled_reminders/subagent_requests 表在 v2 下恒为空，
        挂起判定对它们永远失明（证据 e）；compute_jobs 表仍是权威。
        """
        from cloudra.persistence.database import aretry_on_locked

        async def query():
            async with self.db.aconnect() as con:
                cur = await con.execute(
                    "SELECT COUNT(*) FROM compute_jobs "
                    "WHERE state IN ('ready', 'running') AND conversation_id = ?",
                    (self.conversation_id,),
                )
                return await cur.fetchone()

        row = await aretry_on_locked(query)
        if row and any(row):
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

    _SOURCE_PATH_KEYS = (
        "log_path",
        "freq_log",
        "input_path",
        "input_file_path",
        "log_file",
        "source_path",
        "output_path",
        "ts_candidate_path",
    )

    @staticmethod
    def _source_path_from(arguments: dict[str, Any]) -> str:
        for key in DagController._SOURCE_PATH_KEYS:
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _result_kind(result: dict[str, Any], success: bool) -> str:
        """机器可读的失败判别：区分证据坏 / 解析管线坏 / 环境问题。

        只作 sidecar 提示，不构成绑定权威；完整 message 仍在 result_summary。
        """
        if success:
            return "ok"
        message = str(result.get("message") or "").lower()
        if "not found" in message:
            return "source_missing"
        if "not installed" in message or "no module" in message or "importerror" in message:
            return "environment"
        if "parse" in message or "failed to" in message:
            return "parse_failed"
        return "failed"

    async def _enqueue_call_review(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        success: bool,
        *,
        compute_job_id: str | None = None,
        suggested_target_id: str | None = None,
        suggested_stage: str = "",
        force: bool = False,
    ) -> tuple[bool, str | None]:
        """CallReview 收件箱 enqueue（D5 节流、D12 仅追加直连 INSERT）。

        只有 registry 声明 dag_review=True 的工具入箱（计算作业终态走
        enqueue_compute_review）；普通工具调用不入箱也不唤醒 Supervisor。
        ``force=True`` 时跳过白名单（显式证据通交）。返回 (是否入新箱, 同构
        重复的既有 review_id 或 None)。
        """
        if not force and not is_dag_reviewed(tool_name):
            return False, None
        from cloudra.subagents.registry import legacy_agent_id_for_role

        role_id = self.role_id or ""
        arguments_digest = "sha256:" + hashlib.sha256(
            _canonical_json(arguments).encode("utf-8")
        ).hexdigest()[:16]
        result_summary = _canonical_json(result)
        # 同构去重（仅 pending）：内容完全相同的 artifact 且已有排队中的 review
        # 时不重复入箱——返回既有 review id 让 Coordinator 收到提示。已裁决的
        # 同构重提照常生成新 review 周期。
        duplicate = await asyncio.to_thread(
            self.store.find_duplicate_review, tool_name, arguments_digest, result_summary
        )
        if duplicate is not None:
            return False, duplicate
        review = CallReview(
            review_id="rev_" + uuid.uuid4().hex,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            is_success=success,
            caller_session_id=self.session_id,
            caller_role_id=role_id,
            caller_legacy_id=(
                legacy_agent_id_for_role(role_id) if role_id else (self.agent_id or "")
            ),
            arguments_digest=arguments_digest,
            result_summary=result_summary,
            source_path=self._source_path_from(arguments),
            result_kind=self._result_kind(result, success),
            compute_job_id=compute_job_id,
            suggested_target_id=suggested_target_id,
            suggested_stage=suggested_stage,
            state="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await asyncio.to_thread(self.store.enqueue_call_review, review)
        return True, None

    async def on_tool_finished(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> DeliveryDelta | None:
        if not self.enabled:
            return None
        if not is_dag_observable(tool_name):
            # 不记录编排平面调用本身，但 Coordinator 的机理变更仍要唤醒 Supervisor。
            if self.mode is OrchestrationMode.DAG_GUIDED:
                await self._trigger_supervisor_after_tool(
                    tool_name, arguments, result, self._result_succeeded(result)
                )
            return None
        await self.initialize()
        evidence_ref = await asyncio.to_thread(
            self.store.register_evidence,
            self.session_id,
            tool_name,
            {
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "result": result,
            },
        )
        success = self._result_succeeded(result)
        # 不再有图上遥测（observed 节点/自动认领/自动绑定，证据 b/i-1）：
        # 只登记证据 + 收件箱 enqueue；绑定一律走显式阶段绑定。
        enqueued, duplicate = await self._enqueue_call_review(
            tool_call_id, tool_name, arguments, result, success
        )
        if self.mode is OrchestrationMode.DAG_GUIDED and enqueued:
            await self._wake_supervisor_for_reviews()
        return DeliveryDelta(
            evidence_ref=evidence_ref,
            tool_name=tool_name,
            dedup_review_id=duplicate,
        )

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

    async def submit_evidence_for_review(
        self,
        tool_call_id: str,
        target_id: str,
        stage_kind: str,
    ) -> dict[str, Any]:
        """Coordinator 把任意已完成工具调用的产物显式提交进 review 收件箱。

        这是白名单（dag_review）之外的证据通交通道：format_converter /
        internal_coordinates 等产出证据但不会自动入箱的工具，由 Coordinator
        声明"此调用支撑 target 的 stage"后进箱，Supervisor 照常复核裁决。
        """
        if not self.enabled:
            raise RuntimeError(
                "evidence submission is disabled in standard orchestration mode"
            )
        await self.initialize()
        ref = await asyncio.to_thread(self._evidence_for_call, tool_call_id)
        source_name, payload = await asyncio.to_thread(
            self.store.resolve_evidence_with_source, ref
        )
        result = payload.get("result") or {} if isinstance(payload, dict) else {}
        arguments = payload.get("arguments") or {} if isinstance(payload, dict) else {}
        if not self._result_succeeded(result):
            raise RuntimeError(
                f"tool call {tool_call_id!r} did not succeed; a failed computation "
                "cannot be submitted as evidence"
            )
        enqueued, duplicate = await self._enqueue_call_review(
            tool_call_id,
            source_name,
            arguments,
            result,
            True,
            suggested_target_id=target_id,
            suggested_stage=stage_kind,
            force=True,
        )
        if self.mode is OrchestrationMode.DAG_GUIDED and enqueued:
            await self._wake_supervisor_for_reviews()
        return {
            "tool_call_id": tool_call_id,
            "target_id": target_id,
            "stage_kind": stage_kind,
            "enqueued": enqueued,
            "duplicate_review_id": duplicate,
        }

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
        if tool_name == "dag_propose_mechanism" and accepted:
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

    def _evidence_for_call(self, tool_call_id: str) -> GraphRef:
        """tool_call_id → 已登记的 tool_result 证据引用（证据库反查）。

        process 遥测节点已删除（D12）：解析走 dag_evidence 的 payload，
        不再经过图上的 observed 节点。
        """
        ref = self.store.resolve_evidence_for_call(tool_call_id)
        if ref is None:
            raise RuntimeError(
                f"tool call {tool_call_id!r} has no registered evidence; only a "
                "finished tool call with a recorded tool_result can be bound"
            )
        return ref

    def _apply_harness(
        self,
        operations: list[GraphOperation],
        rationale: str,
    ) -> MutationResult:
        # Concurrent children (swarm) bump process revision on every observed
        # tool-call; two attempts is not enough when three opts finish together.
        last: MutationResult | None = None
        for attempt in range(8):
            last = self.engine.apply_batch(
                MutationBatch(
                    session_id=self.session_id,
                    actor=GraphActor.HARNESS,
                    actor_id="dag-controller",
                    base_revisions=self.store.load_bundle().revisions,
                    operations=operations,
                    rationale=rationale,
                )
            )
            if last.accepted:
                return last
            if last.rejection_code != "stale_revision":
                break
        assert last is not None
        raise RuntimeError(
            f"deterministic DAG mutation rejected: {last.rejection_code}: "
            f"{last.rejection_reason}"
        )

    @staticmethod
    def _result_succeeded(result: dict[str, Any]) -> bool:
        for key in ("is_success", "success", "is_written"):
            if key in result:
                return bool(result[key])
        return "error" not in result

    @staticmethod
    def _delivery_target(graph, target_id: str):
        """在 delivery 图上定位节点或边，返回 (target_type, element)；缺失抛错。"""
        node = next((n for n in graph.nodes if n.node_id == target_id), None)
        if node is not None:
            return "node", node
        edge = next((e for e in graph.edges if e.edge_id == target_id), None)
        if edge is not None:
            return "edge", edge
        raise RuntimeError(f"delivery target {target_id!r} does not exist")

    def _passes_saddle_check(self, ref: GraphRef | None) -> bool:
        """TS frequency 阶段绑定的 harness 检查（D7）：证据必须能被其工具的
        deriver 推出 n_imag==1（saddle_supported），否则 bind 被拒。"""
        if ref is None:
            return False
        try:
            tool_name, payload = self.store.resolve_evidence_with_source(ref)
        except InvalidGraphReference:
            return False
        deriver = evidence_deriver_for(tool_name)
        if deriver is None:
            return False
        changes = deriver(
            current={},
            role="ts_optimization_frequency",
            arguments=payload.get("arguments") or {},
            result=payload.get("result") or {},
        )
        return bool((changes or {}).get("saddle_supported"))

    async def apply_stage_bind(
        self,
        *,
        element_id: str,
        stage_kind: str,
        ref: GraphRef | None,
        verdict: str,
        reason: str = "",
        tool_succeeded: bool,
    ) -> MutationResult:
        """阶段绑定的唯一 harness 入口（agree/disagree/skip）。

        守卫确定性（engine.apply_stage_verdict）：顺序（前面的必需阶段须
        supported/skipped；rejected 可重绑，D2）、理由（disagree/skip 必填）、
        工具成败；TS frequency 另有 n_imag==1 检查（D7，不过 ⇒
        saddle_check_failed，阶段保持 pending）。守卫拒绝不落地；通过后
        attach ref + 更新 stages，并由阶段重派生 evidence_level（D7）。
        """
        if not self.enabled:
            raise RuntimeError(
                "stage binds are disabled in standard orchestration mode"
            )
        await self.initialize()
        try:
            kind = StageKind(stage_kind)
        except ValueError:
            raise RuntimeError(
                f"unknown stage_kind {stage_kind!r}; "
                f"allowed: {sorted(item.value for item in StageKind)}"
            ) from None
        if verdict not in ("agree", "disagree", "skip"):
            raise RuntimeError(
                f"unknown verdict {verdict!r}; allowed: agree/disagree/skip"
            )

        def _guarded_stages():
            # snapshot 是同步 sqlite 读，连同守卫一起放进 worker 线程
            snapshot = self.engine.snapshot()
            target_type, element = self._delivery_target(
                snapshot.delivery, element_id
            )
            new_stages = apply_stage_verdict(
                list(element.stages),
                stage_kind=kind,
                verdict=verdict,  # type: ignore[arg-type]
                reason=reason,
                ref=ref,
                tool_succeeded=tool_succeeded,
            )
            if verdict == "agree" and ref is not None:
                # D11：submit_compute_job 的调用永远不是阶段证据——计算阶段
                # 证据只能来自作业终态后的产物（parser 输出）。
                try:
                    source_name, _ = self.store.resolve_evidence_with_source(ref)
                except InvalidGraphReference:
                    raise _Rejected(
                        "invalid_reference",
                        f"evidence reference {ref.ref_id!r} does not resolve",
                    ) from None
                if source_name == "submit_compute_job":
                    raise _Rejected(
                        "bind_target_is_submit",
                        "a submit_compute_job call is never stage evidence; bind "
                        "the parser output of the finished compute job instead",
                    )
            if (
                verdict == "agree"
                and target_type == "edge"
                and kind is StageKind.FREQUENCY
                and not self._passes_saddle_check(ref)
            ):
                raise _Rejected(
                    "saddle_check_failed",
                    "TS frequency evidence must show exactly one imaginary "
                    "frequency (n_imag == 1); the stage stays pending",
                )
            return target_type, element, new_stages

        try:
            target_type, element, new_stages = await asyncio.to_thread(
                _guarded_stages
            )
        except _Rejected as exc:
            rejection = exc  # except 块退出后 exc 会被删除，先绑定到普通局部变量
            revisions = await asyncio.to_thread(
                lambda: dict(self.store.load_bundle().revisions)
            )
            return MutationResult(
                accepted=False,
                mutation_id="mut_" + uuid.uuid4().hex,
                revisions=revisions,
                rejection_code=rejection.code,
                rejection_reason=rejection.reason,
            )

        operations: list[GraphOperation] = []
        if verdict == "agree" and ref is not None and ref not in element.refs:
            operations.append(
                AttachRef(
                    op="attach_ref",
                    graph="delivery",
                    target_type=target_type,  # type: ignore[arg-type]
                    target_id=element_id,
                    ref=ref,
                )
            )
        changes = {
            "stages": [stage.model_dump(mode="json") for stage in new_stages],
            "evidence_level": derive_evidence_level(
                new_stages, is_edge=target_type == "edge"
            ),
        }
        operations.append(
            UpdateNode(
                op="update_node",
                graph="delivery",
                node_id=element_id,
                changes=changes,
            )
            if target_type == "node"
            else UpdateEdge(
                op="update_edge",
                graph="delivery",
                edge_id=element_id,
                changes=changes,
            )
        )
        return await asyncio.to_thread(
            self._apply_harness,
            operations,
            f"stage bind {verdict}: {element_id}.{kind.value}",
        )

    async def bind_stage_for_call(
        self,
        tool_call_id: str,
        target_id: str,
        stage_kind: str,
    ) -> dict[str, Any]:
        """dag_bind_evidence 的阶段形态：tool_call_id → 已登记证据 → agree 绑定。

        确定性校验与 bind_evidence_for_call 同构（证据已登记、该次调用确实
        成功），随后走 apply_stage_bind 的顺序/检查守卫。
        """
        if not self.enabled:
            raise RuntimeError(
                "bind_evidence is disabled in standard orchestration mode"
            )
        await self.initialize()
        ref = await asyncio.to_thread(self._evidence_for_call, tool_call_id)
        _, payload = await asyncio.to_thread(
            self.store.resolve_evidence_with_source, ref
        )
        if not self._result_succeeded(payload.get("result") or {}):
            raise RuntimeError(
                f"tool call {tool_call_id!r} did not succeed; a failed or "
                "unsuccessful computation cannot be bound as evidence"
            )
        mutation = await self.apply_stage_bind(
            element_id=target_id,
            stage_kind=stage_kind,
            ref=ref,
            verdict="agree",
            tool_succeeded=True,
        )
        return {
            "target_id": target_id,
            "stage_kind": stage_kind,
            "ref_id": ref.ref_id,
            "accepted": mutation.accepted,
            "rejection_code": mutation.rejection_code,
            "rejection_reason": mutation.rejection_reason,
            "mutation_id": mutation.mutation_id,
            "revisions": mutation.revisions,
        }

    async def review_call(
        self,
        *,
        review_id: str,
        target_id: str,
        stage_kind: str,
        verdict: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Supervisor 的 per-call 复核（D3）：dag_review_call 的 controller 面。

        review 行不携带 ref——harness 从 review.tool_call_id 重解析证据
        （已登记、调用成功、目标存在、非 submit 调用 D11），阶段绑定守卫与
        dag_bind_evidence 完全同构。ignore = 不是 delivery 证据，不改阶段。
        """
        if not self.enabled:
            raise RuntimeError(
                "review_call is disabled in standard orchestration mode"
            )
        await self.initialize()
        review = await asyncio.to_thread(self.store.get_call_review, review_id)
        if review is None:
            raise RuntimeError(f"call review {review_id!r} does not exist")
        if review.state == "ignored":
            raise RuntimeError(
                f"call review {review_id!r} is already ignored"
            )
        # 一条 review 可依次支撑多个阶段（一次 opt+freq 解析同时供 ts_opt 与
        # frequency），因此 reviewed 不阻止后续 verdict；state 只是簿记。
        if verdict == "ignore":
            await asyncio.to_thread(
                self.store.mark_call_review, review_id, "ignored"
            )
            return {
                "review_id": review_id,
                "verdict": "ignore",
                "accepted": True,
                "stage_changed": False,
            }
        ref = None
        tool_succeeded = False
        if verdict == "agree":
            # D3：ref 由 harness 从 tool_call_id 确定性解析（含 D11 检查，
            # 在 apply_stage_bind 内）
            ref = await asyncio.to_thread(
                self._evidence_for_call, review.tool_call_id
            )
            _, payload = await asyncio.to_thread(
                self.store.resolve_evidence_with_source, ref
            )
            tool_succeeded = self._result_succeeded(payload.get("result") or {})
        mutation = await self.apply_stage_bind(
            element_id=target_id,
            stage_kind=stage_kind,
            ref=ref,
            verdict=verdict,
            reason=reason,
            tool_succeeded=tool_succeeded,
        )
        if mutation.accepted:
            await asyncio.to_thread(
                self.store.mark_call_review, review_id, "reviewed"
            )
        return {
            "review_id": review_id,
            "verdict": verdict,
            "target_id": target_id,
            "stage_kind": stage_kind,
            "accepted": mutation.accepted,
            "rejection_code": mutation.rejection_code,
            "rejection_reason": mutation.rejection_reason,
            "mutation_id": mutation.mutation_id,
            "stage_changed": mutation.accepted,
        }

    # --- 机理草稿（Phase 3：propose → accept → 解锁计算） ---

    @staticmethod
    def _validate_draft(
        operations_raw: list[dict[str, Any]],
        stage_contracts_raw: dict[str, list[str]],
        rationale: str,
    ) -> MechanismDraft:
        """校验草稿：delivery-only add/update ops；阶段全部 pending（阶段状态
        只由 harness 推进）；stage_contracts 的键必须解析到草稿自身 add 的
        元素，且阶段词表与元素种类匹配。"""
        operations: list[GraphOperation] = []
        for raw in operations_raw:
            try:
                op = parse_graph_operation(raw)
            except ValueError as exc:
                raise RuntimeError(f"invalid draft operation: {exc}") from exc
            if (
                not isinstance(op, (AddNode, AddEdge, UpdateNode, UpdateEdge))
                or op.graph is not GraphKind.DELIVERY
            ):
                raise RuntimeError(
                    "draft operations must be delivery-only "
                    "add_node/add_edge/update_node/update_edge"
                )
            if isinstance(op, (AddNode, AddEdge)):
                element = op.node if isinstance(op, AddNode) else op.edge
                if any(
                    stage.status is not StageStatus.PENDING or stage.ref is not None
                    for stage in getattr(element, "stages", [])
                ):
                    raise RuntimeError(
                        "draft stages must all be pending; stage states are "
                        "advanced by harness stage binds only"
                    )
            else:
                extras = set(op.changes) - {
                    "status", "priority", "label", "annotations",
                    "reason", "blocked_reason", "evidence_level",
                    "supersedes", "required",
                }
                if extras:
                    raise RuntimeError(
                        f"draft update changes exceed mutable fields: {sorted(extras)}"
                    )
                if op.changes.get("evidence_level") not in (
                    None, "proposed", "rejected", "inconclusive"
                ):
                    raise RuntimeError(
                        "a draft cannot promote evidence levels; evidence is "
                        "derived by the harness from stage binds"
                    )
            operations.append(op)
        added: dict[str, str] = {}
        for op in operations:
            if isinstance(op, AddNode):
                added[op.node.node_id] = "node"
            elif isinstance(op, AddEdge):
                added[op.edge.edge_id] = "edge"
        contracts: dict[str, StageContract] = {}
        for element_id, kinds in (stage_contracts_raw or {}).items():
            if element_id not in added:
                raise RuntimeError(
                    f"stage contract for {element_id!r} does not resolve to an "
                    "element added by this draft"
                )
            allowed = (
                OCCURRENCE_STAGE_KINDS
                if added[element_id] == "node"
                else ELEMENTARY_STEP_STAGE_KINDS
            )
            stages: list[StageState] = []
            for raw_kind in kinds:
                try:
                    kind = StageKind(raw_kind)
                except ValueError:
                    raise RuntimeError(
                        f"unknown stage kind {raw_kind!r}; "
                        f"allowed: {sorted(item.value for item in StageKind)}"
                    ) from None
                if kind not in allowed:
                    raise RuntimeError(
                        f"stage {kind.value!r} does not apply to "
                        f"{'occurrence nodes' if added[element_id] == 'node' else 'elementary-step edges'}; "
                        f"allowed here: {sorted(item.value for item in allowed)}"
                    )
                if kind in {stage.kind for stage in stages}:
                    raise RuntimeError(f"duplicate stage {kind.value!r} for {element_id!r}")
                stages.append(StageState(kind=kind))
            contracts[element_id] = StageContract(stages=stages)
        return MechanismDraft(
            operations=operations,
            stage_contracts=contracts,
            rationale=rationale,
        )

    @staticmethod
    def _draft_operations(draft: MechanismDraft) -> list[GraphOperation]:
        """把阶段契约并进 add ops（元素 stages 随 add 落图，全 pending）。"""
        operations: list[GraphOperation] = []
        for op in draft.operations:
            if isinstance(op, AddNode) and op.node.node_id in draft.stage_contracts:
                op = op.model_copy(update={
                    "node": op.node.model_copy(update={
                        "stages": list(draft.stage_contracts[op.node.node_id].stages)
                    })
                })
            elif isinstance(op, AddEdge) and op.edge.edge_id in draft.stage_contracts:
                op = op.model_copy(update={
                    "edge": op.edge.model_copy(update={
                        "stages": list(draft.stage_contracts[op.edge.edge_id].stages)
                    })
                })
            operations.append(op)
        return operations

    def _apply_draft(self, draft: MechanismDraft, actor_id: str) -> MutationResult:
        operations = self._draft_operations(draft)
        last: MutationResult | None = None
        for _attempt in range(8):
            last = self.engine.apply_batch(
                MutationBatch(
                    session_id=self.session_id,
                    actor=GraphActor.HARNESS,
                    actor_id=actor_id,
                    base_revisions=self.store.load_bundle().revisions,
                    operations=operations,
                    rationale=draft.rationale,
                )
            )
            if last.accepted or last.rejection_code != "stale_revision":
                return last
        assert last is not None
        return last

    async def propose_mechanism(
        self,
        *,
        operations: list[dict[str, Any]],
        stage_contracts: dict[str, list[str]],
        rationale: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Coordinator 的机理草稿（D1）：guided 落 open 草稿等 Supervisor
        接受；record 由 harness 立即自动接受（actor="harness:auto"）。"""
        if not self.enabled:
            raise RuntimeError(
                "propose_mechanism is disabled in standard orchestration mode"
            )
        if not rationale.strip():
            raise RuntimeError("a mechanism proposal requires a non-empty rationale")
        await self.initialize()
        draft = self._validate_draft(operations, stage_contracts, rationale)
        if self.mode is OrchestrationMode.DAG_RECORD:
            mutation = await asyncio.to_thread(
                self._apply_draft, draft, "harness:auto"
            )
            if not mutation.accepted:
                raise RuntimeError(
                    f"mechanism draft failed to apply: {mutation.rejection_code}: "
                    f"{mutation.rejection_reason}"
                )
            accepted = draft.model_copy(update={"state": "accepted"})
            draft_id = await asyncio.to_thread(
                self.store.save_draft, accepted, actor_id="harness:auto"
            )
            return {
                "draft_id": draft_id,
                "state": "accepted",
                "accepted": True,
                "revisions": mutation.revisions,
            }
        draft_id = await asyncio.to_thread(
            self.store.save_draft, draft, actor_id=actor_id
        )
        return {"draft_id": draft_id, "state": "open", "accepted": False}

    async def accept_mechanism(
        self,
        *,
        verdict: str,
        rationale: str = "",
        draft_id: str | None = None,
    ) -> dict[str, Any]:
        """Supervisor 的草稿裁决（guided only）：accept 落图（契约并入
        add ops）；reject 退回草稿并附理由。"""
        if not self.enabled:
            raise RuntimeError(
                "accept_mechanism is disabled in standard orchestration mode"
            )
        if self.mode is not OrchestrationMode.DAG_GUIDED:
            raise RuntimeError(
                "dag_accept_mechanism is guided-only; dag_record auto-accepts proposals"
            )
        await self.initialize()
        if draft_id:
            draft = await asyncio.to_thread(self.store.get_draft, draft_id)
            if draft is None:
                raise RuntimeError(f"mechanism draft {draft_id!r} does not exist")
            if draft.state != "open":
                raise RuntimeError(
                    f"mechanism draft {draft_id!r} is already {draft.state}"
                )
            resolved_id = draft_id
        else:
            found = await asyncio.to_thread(self.store.latest_open_draft)
            if found is None:
                raise RuntimeError("no open mechanism draft to review")
            resolved_id, draft = found
        if verdict == "reject":
            if not rationale.strip():
                raise RuntimeError(
                    "rejecting a mechanism draft requires a non-empty rationale"
                )
            await asyncio.to_thread(
                self.store.set_draft_state,
                resolved_id,
                "rejected",
                reject_reason=rationale,
            )
            return {
                "draft_id": resolved_id,
                "state": "rejected",
                "accepted": False,
                "reason": rationale,
            }
        mutation = await asyncio.to_thread(
            self._apply_draft, draft, "harness:supervisor-accept"
        )
        if not mutation.accepted:
            raise RuntimeError(
                f"mechanism draft failed to apply: {mutation.rejection_code}: "
                f"{mutation.rejection_reason}"
            )
        await asyncio.to_thread(
            self.store.set_draft_state, resolved_id, "accepted"
        )
        return {
            "draft_id": resolved_id,
            "state": "accepted",
            "accepted": True,
            "revisions": mutation.revisions,
        }


async def enqueue_compute_review(
    db: ConversationDB, taskid: int, terminal_state: str
) -> None:
    """计算作业终态入 CallReview 收件箱（D5/D11）：带作业的终态
    （done/failed），与 submit 调用的成败无关。

    非 dag 模式或无 session 记录时跳过。review_id 按作业确定
    （rev_compute_<id>），重复终态回调由 INSERT OR IGNORE 去重。
    guard/executor 进程内调用：不直接唤醒 Supervisor——提交者已被
    compute_job 事件唤醒，后续 parser 调用会把证据带进复核流。
    """
    async with db.aconnect() as con:
        cur = await con.execute(
            "SELECT session_id FROM compute_jobs WHERE id=?", (taskid,)
        )
        row = await cur.fetchone()
        session_id = (row[0] or "") if row else ""
        mode, role_id = "standard", ""
        if session_id:
            cur = await con.execute(
                "SELECT orchestration_mode, agent_id FROM session WHERE session_id=?",
                (session_id,),
            )
            row = await cur.fetchone()
            if row:
                mode = row[0] or "standard"
                role_id = row[1] or ""
    if mode not in ("dag_record", "dag_guided"):
        return
    from cloudra.subagents.registry import legacy_agent_id_for_role

    review = CallReview(
        review_id=f"rev_compute_{taskid}",
        tool_call_id="",
        tool_name="compute_job",
        is_success=terminal_state == "done",
        caller_session_id=session_id,
        caller_role_id=role_id,
        caller_legacy_id=legacy_agent_id_for_role(role_id) if role_id else "",
        result_summary=f"compute job {taskid} terminal state: {terminal_state}",
        compute_job_id=str(taskid),
        state="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    await asyncio.to_thread(DagStore(db).enqueue_call_review, review)
