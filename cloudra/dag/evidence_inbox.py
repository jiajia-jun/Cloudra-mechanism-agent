"""CallReview inbox (tool calls and compute terminal states) and stage binding."""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from cloudra.dag.delta import DeliveryDelta
from cloudra.dag.engine import (
    _Rejected,
    apply_stage_verdict,
)
from cloudra.dag.models import (
    AttachRef,
    CallReview,
    GraphActor,
    GraphOperation,
    GraphRef,
    MutationBatch,
    MutationResult,
    OrchestrationMode,
    StageKind,
    UpdateEdge,
    UpdateNode,
    derive_evidence_level,
)
from cloudra.dag.store import DagStore, InvalidGraphReference, _canonical_json
from cloudra.persistence.database import ConversationDB
from cloudra.tools.capabilities import (
    evidence_deriver_for,
    is_dag_observable,
    is_dag_reviewed,
)


class EvidenceInboxMixin:
    """工具证据持久化、CallReview 入箱与阶段绑定；由 DagController 组合。"""

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
        for key in EvidenceInboxMixin._SOURCE_PATH_KEYS:
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
        """阶段绑定的唯一 harness 入口（agree/disagree/skip/not_applicable）。

        守卫确定性（engine.apply_stage_verdict）：顺序（前面的必需阶段须
        supported/skipped/not_applicable；rejected 可重绑，D2）、理由
        （disagree/skip/not_applicable 必填）、工具成败；TS frequency
        另有 n_imag==1 检查（D7，不过 ⇒ saddle_check_failed，阶段保持
        pending）。守卫拒绝不落地；通过后 attach ref + 更新 stages，并由
        阶段重派生 evidence_level（D7）。
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
        if verdict not in ("agree", "disagree", "skip", "not_applicable"):
            raise RuntimeError(
                f"unknown verdict {verdict!r}; "
                "allowed: agree/disagree/skip/not_applicable"
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
        dag_bind_evidence 完全同构。ignore = 不是 delivery 证据，不改阶段；
        disagree/skip/not_applicable 不解析 ref、reason 必填（not_applicable
        表示该槽位对此元素不成立，如无能垒步无 ts_opt）。
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


async def enqueue_compute_review(taskid: int, terminal_state: str) -> None:
    """计算作业终态入 CallReview 收件箱（D5/D11）：带作业的终态
    （done/failed），与 submit 调用的成败无关。

    作业归属从中央 compute.db 读回（session_id/conversation_id），再开
    对应会话库读 session 的编排模式（CallReview 仍属会话库）。非 dag 模式、
    无 session 记录或会话库不存在时跳过。review_id 按作业确定
    （rev_compute_<id>），重复终态回调由 INSERT OR IGNORE 去重。
    guard/executor 进程内调用：不直接唤醒 Supervisor——提交者已被
    compute_job 事件唤醒，后续 parser 调用会把证据带进复核流。
    """
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import aget_compute_job

    job = await aget_compute_job(ComputeDB(), taskid)
    session_id = (job or {}).get("session_id") or ""
    conversation_id = (job or {}).get("conversation_id") or ""
    if not session_id or not conversation_id:
        return
    conv_db = ConversationDB(conversation_id)
    if not os.path.isfile(conv_db.path):
        return  # 会话库不存在：无从判定编排模式，按 standard 跳过
    async with conv_db.aconnect() as con:
        cur = await con.execute(
            "SELECT orchestration_mode, agent_id FROM session WHERE session_id=?",
            (session_id,),
        )
        row = await cur.fetchone()
    mode, role_id = "standard", ""
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
    await asyncio.to_thread(DagStore(conv_db).enqueue_call_review, review)
