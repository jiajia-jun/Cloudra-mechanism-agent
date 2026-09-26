"""CallReview inbox (explicit evidence submissions) and stage binding.

§5 显式送审契约：研究工具完成只登记证据/事实（register_evidence +
_derive_facts），不创建 review、不通知 Supervisor；计算作业终态只在
dag_record 留审计行。唯一入箱路径是 agent 筛选后经 dag_bind_evidence →
submit_evidence_for_review 的显式送审（带 claim/rationale，围绕不可变
快照裁决）。

通知所有权：``submit_evidence_for_review`` 只验证并持久化 explicit
review；真实 ``dag_bind_evidence`` 成功返回后，由运行时 DAG policy 的
完成钩子（``_trigger_supervisor_after_tool``）按新建 review 回执通知
Supervisor。直接存储调用不启动督导；中断窗口由 reconcile 扫持久信箱
恢复。工具完成本身不自动筛选研究证据。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from cloudra.base.role_identity import legacy_agent_id_for_role
from cloudra.dag.delta import DeliveryDelta
from cloudra.dag.engine import (
    _Rejected,
    apply_stage_verdict,
)
from cloudra.dag.evidence_ingest import validate_species_minimum
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
    StageStatus,
    UpdateEdge,
    UpdateNode,
    derive_evidence_level,
)
from cloudra.dag.store import DagStore, InvalidGraphReference, _canonical_json
from cloudra.persistence.database import ConversationDB
from cloudra.persistence.workspace import resolve_existing_tool_path
from cloudra.tools.capabilities import (
    evidence_deriver_for,
    is_dag_observable,
)
from cloudra.tools.core.irc_evidence import verify_short_irc_direction

logger = logging.getLogger(__name__)


class EvidenceInboxMixin:
    """工具证据持久化、显式送审入箱与阶段绑定；由 DagController 组合。"""

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
        message = str(result.get("message") or result.get("error") or "").lower()
        if "not found" in message:
            return "source_missing"
        if "not installed" in message or "no module" in message or "importerror" in message:
            return "environment"
        if "parse" in message or "failed to" in message:
            return "parse_failed"
        return "failed"

    def _build_review(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        success: bool,
        *,
        claim: str,
        rationale: str,
        evidence_id: str,
        suggested_target_id: str,
        suggested_stage: str,
    ) -> CallReview:
        role_id = self.role_id or ""
        return CallReview(
            review_id="rev_" + uuid.uuid4().hex,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            is_success=success,
            caller_session_id=self.session_id,
            caller_role_id=role_id,
            caller_legacy_id=(
                legacy_agent_id_for_role(role_id) if role_id else (self.agent_id or "")
            ),
            arguments_digest="sha256:" + hashlib.sha256(
                _canonical_json(arguments).encode("utf-8")
            ).hexdigest()[:16],
            result_summary=_canonical_json(result),
            source_path=self._source_path_from(arguments),
            result_kind=self._result_kind(result, success),
            suggested_target_id=suggested_target_id,
            suggested_stage=suggested_stage,
            claim=claim,
            rationale=rationale,
            submitter=self.agent_id or role_id,
            evidence_id=evidence_id,
            source="explicit",
            state="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

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
        # §5：工具完成只登记证据（不可变快照）与派生事实；不创建 review、
        # 不唤醒 Supervisor——送审是 agent 筛选后的显式动作
        # （dag_bind_evidence → submit_evidence_for_review）。
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
        await self._derive_facts(tool_name, {"tool_call_id": tool_call_id,
                                             "arguments": arguments,
                                             "result": result}, evidence_ref)
        return DeliveryDelta(
            evidence_ref=evidence_ref,
            tool_name=tool_name,
        )

    async def _derive_facts(
        self,
        tool_name: str,
        payload: dict[str, Any],
        evidence_ref: GraphRef,
    ) -> None:
        """声明了事实适配器的工具：从已登记证据抽类型化事实并幂等落库。

        适配器是纯函数；异常不阻断证据登记主路径（事实可离线重派生补齐）。
        """
        from cloudra.tools.capabilities import fact_adapter_for

        adapter = fact_adapter_for(tool_name)
        if adapter is None:
            return
        try:
            facts = adapter(payload, evidence_ref)
        except Exception:
            logger.warning("fact adapter failed for %s", tool_name, exc_info=True)
            return
        if facts:
            await asyncio.to_thread(self.store.record_facts, facts)

    async def submit_evidence_for_review(
        self,
        attachments: list[dict[str, str]],
    ) -> dict[str, Any]:
        """显式送审的唯一入箱口（§5）：agent 筛选后把已完成调用的证据快照
        连同主张（claim/rationale）提交为 pending CallReview，Supervisor 围绕
        明确 claim 与提交时的不可变快照裁决。

        每条 attachment：tool_call_id / bind_target / stage_kind / claim（必填）
        / rationale（可选）。先对同一快照**全部校验**（claim 非空、目标存在、
        阶段在该元素的契约内、调用已结束且证据已登记、证据可解析——证据库是
        会话级的，跨项目引用在此处天然不可解析而被拒），再经
        ``store.submit_call_reviews`` 单事务原子提交；任何一项非法则全部不
        提交。相同 pending 声明（同证据+目标+阶段+规范化 claim）幂等返回既有
        review_id；失败结果允许作为负证据送审（is_success 如实记录，绑定阶段
        仍被 engine 的 tool_not_succeeded 拦截）。
        """
        if not self.enabled:
            raise RuntimeError(
                "evidence submission is disabled in standard orchestration mode"
            )
        if not attachments:
            raise RuntimeError(
                "submit_evidence_for_review requires at least one attachment"
            )
        await self.initialize()

        def _validate_all() -> list[CallReview]:
            snapshot = self.engine.snapshot()
            prepared: list[CallReview] = []
            for index, item in enumerate(attachments):
                label = f"attachment #{index}"
                tool_call_id = str(item.get("tool_call_id") or "").strip()
                target_id = str(item.get("bind_target") or "").strip()
                stage_kind = str(item.get("stage_kind") or "").strip()
                claim = str(item.get("claim") or "").strip()
                rationale = str(item.get("rationale") or "").strip()
                if not claim:
                    raise RuntimeError(
                        f"{label}: a non-empty claim is required — state what "
                        "this evidence is supposed to prove"
                    )
                try:
                    kind = StageKind(stage_kind)
                except ValueError:
                    raise RuntimeError(
                        f"{label}: unknown stage_kind {stage_kind!r}; allowed: "
                        f"{sorted(item.value for item in StageKind)}"
                    ) from None
                _target_type, element = self._delivery_target(
                    snapshot.delivery, target_id
                )
                if not any(stage.kind == kind for stage in element.stages):
                    raise RuntimeError(
                        f"{label}: stage {kind.value!r} is not declared in the "
                        f"stage contract of {target_id!r}; declare the stage "
                        "first or fix the submission"
                    )
                # 已结束 + 已登记 + 本项目内可解析（证据库会话级，跨项目
                # tool_call_id 在此不可解析 ⇒ 拒绝）。
                ref = self._evidence_for_call(tool_call_id)
                try:
                    source_name, payload = self.store.resolve_evidence_with_source(ref)
                except InvalidGraphReference:
                    raise RuntimeError(
                        f"{label}: evidence reference {ref.ref_id!r} does not resolve"
                    ) from None
                result_payload = payload.get("result") or {}
                arguments = payload.get("arguments") or {}
                prepared.append(
                    self._build_review(
                        tool_call_id,
                        source_name,
                        arguments if isinstance(arguments, dict) else {},
                        result_payload if isinstance(result_payload, dict) else {},
                        self._result_succeeded(
                            result_payload if isinstance(result_payload, dict) else {}
                        ),
                        claim=claim,
                        rationale=rationale,
                        evidence_id=ref.ref_id,
                        suggested_target_id=target_id,
                        suggested_stage=kind.value,
                    )
                )
            return prepared

        prepared = await asyncio.to_thread(_validate_all)
        outcomes = await asyncio.to_thread(self.store.submit_call_reviews, prepared)
        results = [
            {
                "tool_call_id": review.tool_call_id,
                "target_id": review.suggested_target_id,
                "stage_kind": review.suggested_stage,
                "claim": review.claim,
                "review_id": review_id,
                "enqueued": created,
            }
            for review, (review_id, created) in zip(prepared, outcomes)
        ]
        return {"attachments": results}

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

    def _ref_for_evidence_id(self, evidence_id: str) -> GraphRef:
        """送审快照身份 → 带 content_hash 的 GraphRef（engine 校验要求 hash）。"""
        with self.db.connect() as con:
            row = con.execute(
                "SELECT content_hash FROM dag_evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(
                f"the submitted evidence snapshot {evidence_id!r} is missing "
                "from the evidence store"
            )
        return GraphRef(
            ref_type="tool_result", ref_id=evidence_id, content_hash=row[0]
        )

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
        import difflib
        all_ids = [n.node_id for n in graph.nodes] + [e.edge_id for e in graph.edges]
        matches = difflib.get_close_matches(target_id, all_ids, n=2, cutoff=0.35)
        suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
        raise RuntimeError(
            f"delivery target {target_id!r} does not exist.{suggestion} "
            f"Available targets: {sorted(all_ids)}"
        )

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

    @staticmethod
    def _frequency_fields(payload: dict[str, Any]) -> tuple[Any, Any]:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        freqs = result.get("frequencies_cm") or result.get("frequencies")
        imag = result.get("imaginary_frequencies")
        if freqs is None:
            freqs = payload.get("frequencies")
        if imag is None:
            imag = payload.get("imaginary_frequencies")
        return freqs, imag

    @staticmethod
    def _normal_termination(payload: dict[str, Any]) -> bool:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        return result.get("normal_termination") is True

    def _passes_minimum_check(self, ref: GraphRef | None) -> bool:
        """物种 geometry / 边端点绑定：必须是有频率支撑的极小值（0 虚频）。"""
        if ref is None:
            return False
        try:
            _name, payload = self.store.resolve_evidence_with_source(ref)
        except InvalidGraphReference:
            return False
        if not isinstance(payload, dict):
            return False
        if not self._normal_termination(payload):
            return False
        freqs, imag = self._frequency_fields(payload)
        res = validate_species_minimum(freqs, imaginary_freqs=imag)
        return res.verified and res.is_valid

    def _passes_ts_opt_check(self, ref: GraphRef | None) -> bool:
        """ts_opt 必须来自正常结束的引擎日志；若带频率则须是一阶鞍点。"""
        if ref is None:
            return False
        try:
            source_name, payload = self.store.resolve_evidence_with_source(ref)
        except InvalidGraphReference:
            return False
        if source_name == "submit_compute_job" or not isinstance(payload, dict):
            return False
        if not self._normal_termination(payload):
            return False
        freqs, imag = self._frequency_fields(payload)
        if freqs is None and imag is None:
            return True
        return self._passes_saddle_check(ref)

    def _resolve_evidence_path(self, raw: str) -> str:
        """证据 payload 记录的日志路径 → 现存文件。

        resolve_existing_tool_path 候选语义（工作目录优先、进程 cwd 兜底）；
        controller 没有工具 subagent 桥，用 working_directory 构造最小上下文。
        """
        context = SimpleNamespace(
            subagent=SimpleNamespace(
                working_directory=(
                    str(self.working_directory) if self.working_directory else None
                )
            )
        )
        return resolve_existing_tool_path(context, raw)

    def _bound_stage_logs(
        self, stages, kinds: set[StageKind]
    ) -> tuple[list[str], list[str]]:
        """已 supported 阶段的绑定 ref → 日志路径；(解析出的路径, 逐槽问题文案)。

        材料只认证据 payload 的 arguments.log_path（agent 原始填写的路径），
        ref 不可解析 / 无 log_path / 文件已不存在都记入 problems（fail-loud）。
        """
        logs: list[str] = []
        problems: list[str] = []
        for stage in stages:
            if stage.kind not in kinds or stage.status is not StageStatus.SUPPORTED:
                continue
            if stage.ref is None:
                problems.append(
                    f"the {stage.kind.value} stage is supported but carries no evidence ref"
                )
                continue
            try:
                _name, payload = self.store.resolve_evidence_with_source(stage.ref)
            except InvalidGraphReference:
                problems.append(
                    f"the {stage.kind.value} evidence ref {stage.ref.ref_id!r} does not resolve"
                )
                continue
            arguments = payload.get("arguments") if isinstance(payload, dict) else None
            raw = arguments.get("log_path") if isinstance(arguments, dict) else None
            if not isinstance(raw, str) or not raw.strip():
                problems.append(
                    f"the {stage.kind.value} evidence does not record arguments.log_path"
                )
                continue
            try:
                logs.append(self._resolve_evidence_path(raw))
            except FileNotFoundError:
                problems.append(
                    f"the {stage.kind.value} log {raw.strip()!r} no longer exists "
                    "on disk (overwritten or moved since the call was recorded)"
                )
        return logs, problems

    def _species_geometry_logs(self, graph, node_id: str) -> list[str]:
        """端点阶段的回退材料：物种节点的 geometry 阶段（验证极小值）日志。"""
        node = next((n for n in graph.nodes if n.node_id == node_id), None)
        if node is None:
            return []
        logs, _problems = self._bound_stage_logs(node.stages, {StageKind.GEOMETRY})
        return logs

    def _passes_short_irc_check(
        self, ref: GraphRef | None, edge, stages, graph
    ) -> tuple[bool, str]:
        """short_irc 的几何方向区间证明（与 ts_guess verify strict / benchmark
        自洽性同一判据）：双侧 IRC 端点几何须各自位于 TS 与对应端点验证极小值
        之间；IRC 收敛与否不做闸门，点数不再构成判据。

        材料全部来自同一条边已 supported 阶段的证据 payload
        （arguments.log_path 指向的日志文件）：TS 几何 ← ts_opt/frequency
        阶段；端点验证极小值 ← endpoint_a/b 阶段（缺绑定日志时回退目标/源
        物种节点的 geometry 阶段）。返回 (通过, 拒绝理由)：任一材料缺失、
        日志被覆盖或证明不成立 ⇒ (False, 写明缺哪份材料的理由)，fail-loud，
        绝不静默降级为收敛/点数判据。
        """
        prefix = (
            "short_irc requires a geometric direction proof (the ts_guess "
            "verify strict / benchmark criterion): both IRC endpoint geometries "
            "must lie between the TS and the corresponding verified endpoint "
            "minima. "
        )
        if ref is None:
            return False, prefix + "no evidence ref was bound."
        try:
            _name, payload = self.store.resolve_evidence_with_source(ref)
        except InvalidGraphReference:
            return False, prefix + f"evidence reference {ref.ref_id!r} does not resolve."
        arguments = payload.get("arguments") if isinstance(payload, dict) else {}
        raw = arguments.get("log_path") if isinstance(arguments, dict) else None
        if not isinstance(raw, str) or not raw.strip():
            return False, prefix + (
                "the bound evidence does not record arguments.log_path; bind the "
                "log_parser output of the finished IRC job."
            )
        try:
            irc_log = self._resolve_evidence_path(raw)
        except FileNotFoundError as exc:
            return False, prefix + f"the IRC log is not readable: {exc}"
        ts_logs, problems = self._bound_stage_logs(
            stages, {StageKind.TS_OPT, StageKind.FREQUENCY}
        )
        endpoint_a_logs, ea_problems = self._bound_stage_logs(
            stages, {StageKind.ENDPOINT_A}
        )
        endpoint_b_logs, eb_problems = self._bound_stage_logs(
            stages, {StageKind.ENDPOINT_B}
        )
        problems += ea_problems + eb_problems
        if not endpoint_a_logs:
            endpoint_a_logs = self._species_geometry_logs(graph, edge.target_node_id)
        if not endpoint_b_logs:
            endpoint_b_logs = self._species_geometry_logs(graph, edge.source_node_id)
        try:
            passed, details = verify_short_irc_direction(
                irc_log, ts_logs, endpoint_a_logs, endpoint_b_logs
            )
        except Exception as exc:  # 解析依赖缺失等：拒绑并写明，绝不静默通过
            logger.warning("short_irc direction proof evaluation failed", exc_info=True)
            return False, prefix + f"the direction proof could not be evaluated: {exc}"
        if passed:
            return True, ""
        return False, prefix + " ".join(details + problems)

    def _passes_thermochemistry_check(self, ref: GraphRef | None) -> bool:
        """thermochemistry 只认 thermo_analysis 的 complete 结果。"""
        if ref is None:
            return False
        try:
            source_name, payload = self.store.resolve_evidence_with_source(ref)
        except InvalidGraphReference:
            return False
        if source_name != "thermo_analysis" or not isinstance(payload, dict):
            return False
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        return result.get("status") == "complete"

    async def apply_stage_bind(
        self,
        *,
        element_id: str,
        stage_kind: str,
        ref: GraphRef | None,
        verdict: str,
        reason: str = "",
        tool_succeeded: bool,
        expected_revision: int | None = None,
    ) -> MutationResult:
        """阶段绑定的唯一 harness 入口（agree/disagree/skip/not_applicable）。

        守卫确定性（engine.apply_stage_verdict）：contract_version=1 保持
        顺序门禁（前面的必需阶段须 supported/skipped/not_applicable；
        rejected 可重绑，D2）；已接受 v2 ClaimSpec 后允许证据乱序绑定，
        缺失依赖由 requirements 层汇总。其他守卫包括理由
        （disagree/skip/not_applicable 必填）、工具成败；TS frequency
        另有 n_imag==1 检查（D7，不过 ⇒ saddle_check_failed，阶段保持
        pending）；物种 geometry 和边的 endpoint_a/b 另有 n_imag==0 检查（不过 ⇒
        minimum_check_failed）；short_irc 另有几何方向区间证明（与 ts_guess
        verify strict / benchmark 自洽性同一判据：双侧 IRC 端点几何各自位于
        TS 与对应端点验证极小值之间，材料取自同边 ts_opt/frequency 与
        endpoint_a/b 或物种 geometry 阶段的已绑证据；缺材料或证明不成立 ⇒
        short_irc_check_failed，理由写明缺哪份材料）。守卫拒绝不落地；
        通过后 attach ref + 更新 stages，并由阶段重派生 evidence_level（D7）。
        """
        if not self.enabled:
            raise RuntimeError(
                "stage binds are disabled in standard orchestration mode"
            )
        await self.initialize()
        try:
            kind = StageKind(stage_kind)
        except ValueError:
            import difflib
            allowed = sorted(item.value for item in StageKind)
            matches = difflib.get_close_matches(stage_kind, allowed, n=2, cutoff=0.35)
            suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
            raise RuntimeError(
                f"unknown stage_kind {stage_kind!r}.{suggestion} "
                f"allowed: {allowed}"
            ) from None
        if verdict not in ("agree", "disagree", "skip", "not_applicable"):
            import difflib
            allowed_v = ["agree", "disagree", "skip", "not_applicable"]
            matches = difflib.get_close_matches(verdict, allowed_v, n=1, cutoff=0.35)
            suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
            raise RuntimeError(
                f"unknown verdict {verdict!r}.{suggestion} "
                f"allowed: {allowed_v}"
            )

        def _guarded_stages():
            # snapshot 是同步 sqlite 读，连同守卫一起放进 worker 线程
            snapshot = self.engine.snapshot()
            # v2 is per-project: an accepted ClaimSpec activates the new
            # evidence protocol. Legacy projects remain v1/strict-order.
            accepted_spec = self.store.accepted_claim_spec()
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
                allow_out_of_order=accepted_spec is not None,
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
            if (
                verdict == "agree"
                and target_type == "edge"
                and kind is StageKind.TS_OPT
                and not self._passes_ts_opt_check(ref)
            ):
                raise _Rejected(
                    "ts_opt_check_failed",
                    "ts_opt evidence must be a normally terminated engine log "
                    "(and a first-order saddle if frequencies are present)",
                )
            if (
                verdict == "agree"
                and (
                    (target_type == "node" and kind is StageKind.GEOMETRY)
                    or (target_type == "edge" and kind in {StageKind.ENDPOINT_A, StageKind.ENDPOINT_B})
                )
                and not self._passes_minimum_check(ref)
            ):
                raise _Rejected(
                    "minimum_check_failed",
                    "species geometry and step endpoint evidence must be a verified minimum "
                    "(n_imag == 0); the stage stays pending",
                )
            if (
                verdict == "agree"
                and target_type == "edge"
                and kind is StageKind.SHORT_IRC
            ):
                irc_ok, irc_reason = self._passes_short_irc_check(
                    ref, element, element.stages, snapshot.delivery
                )
                if not irc_ok:
                    raise _Rejected("short_irc_check_failed", irc_reason)
            if (
                verdict == "agree"
                and target_type == "edge"
                and kind is StageKind.THERMOCHEMISTRY
                and not self._passes_thermochemistry_check(ref)
            ):
                raise _Rejected(
                    "thermochemistry_check_failed",
                    "thermochemistry evidence must be a complete thermo_analysis "
                    "result; the stage stays pending",
                )
            return target_type, element, new_stages, dict(snapshot.bundle.revisions)

        def _reject(rejection: _Rejected) -> MutationResult:
            revisions = dict(self.store.load_bundle().revisions)
            return MutationResult(
                accepted=False,
                mutation_id="mut_" + uuid.uuid4().hex,
                revisions=revisions,
                rejection_code=rejection.code,
                rejection_reason=rejection.reason,
            )

        try:
            target_type, element, new_stages, seen_revisions = await asyncio.to_thread(
                _guarded_stages
            )
        except _Rejected as exc:
            return await asyncio.to_thread(_reject, exc)

        rationale = f"stage bind {verdict}: {element_id}.{kind.value}"
        last: MutationResult | None = None
        for _attempt in range(8):
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
            if expected_revision is not None:
                return await asyncio.to_thread(
                    self._apply_harness_once,
                    operations,
                    rationale,
                    expected_revision=expected_revision,
                )
            last = await asyncio.to_thread(
                self._apply_with_revisions,
                operations,
                rationale,
                seen_revisions,
            )
            if last.accepted or last.rejection_code != "stale_revision":
                return last
            try:
                target_type, element, new_stages, seen_revisions = (
                    await asyncio.to_thread(_guarded_stages)
                )
            except _Rejected as exc:
                return await asyncio.to_thread(_reject, exc)
        assert last is not None
        raise RuntimeError(
            f"deterministic DAG mutation rejected: {last.rejection_code}: "
            f"{last.rejection_reason}"
        )

    def _apply_with_revisions(
        self,
        operations: list[GraphOperation],
        rationale: str,
        revisions: dict[str, int],
    ) -> MutationResult:
        """用守卫读到的 revision 做 base，并发写入才会 stale 并触发重算。"""
        return self.engine.apply_batch(
            MutationBatch(
                session_id=self.session_id,
                actor=GraphActor.HARNESS,
                actor_id="dag-controller",
                base_revisions=revisions,
                operations=operations,
                rationale=rationale,
            )
        )

    def _apply_harness_once(
        self,
        operations: list[GraphOperation],
        rationale: str,
        *,
        expected_revision: int | None,
    ) -> MutationResult:
        """Apply exactly one batch at the caller's expected delivery revision.

        If the caller supplied ``expected_revision``, a concurrent update is
        surfaced as ``revision_conflict`` instead of being silently retried.
        Without expected_revision callers use the auto-retry path.
        """
        bundle = self.store.load_bundle()
        if (
            expected_revision is not None
            and bundle.revisions["delivery"] != expected_revision
        ):
            return MutationResult(
                accepted=False,
                mutation_id="mut_" + uuid.uuid4().hex,
                revisions=dict(bundle.revisions),
                rejection_code="revision_conflict",
                rejection_reason=(
                    f"expected delivery revision {expected_revision}, "
                    f"current is {bundle.revisions['delivery']}; the graph moved "
                    "so this batch was not applied"
                ),
            )
        return self.engine.apply_batch(
            MutationBatch(
                session_id=self.session_id,
                actor=GraphActor.HARNESS,
                actor_id="dag-controller",
                base_revisions=bundle.revisions,
                operations=operations,
                rationale=rationale,
            )
        )

    async def bind_stage_for_call(
        self,
        tool_call_id: str,
        target_id: str,
        stage_kind: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """dag_bind_evidence 的阶段形态：tool_call_id → 已登记证据 → agree 绑定。

        确定性校验与 bind_evidence_for_call 同构（证据已登记、该次调用确实
        成功），随后走 apply_stage_bind 的顺序/检查守卫。expected_revision
        用于单条绑定的 revision 冲突保护。
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
            expected_revision=expected_revision,
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

    async def bind_stage_attachments(
        self,
        attachments: list[dict[str, str]],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Atomically bind several evidence attachments to delivery stages.

        Each attachment has tool_call_id/bind_target/stage_kind.  The batch is
        validated against one snapshot and applied in one DAG mutation when no
        per-attachment guard rejects it.  If ``expected_revision`` is supplied,
        the whole batch is refused with ``revision_conflict`` when the graph has
        moved.
        """
        if not self.enabled:
            raise RuntimeError(
                "bind_evidence is disabled in standard orchestration mode"
            )
        if not attachments:
            raise RuntimeError("bind_stage_attachments requires at least one attachment")
        await self.initialize()

        def _guarded_batch():
            snapshot = self.engine.snapshot()
            accepted_spec = self.store.accepted_claim_spec()
            allow_out_of_order = accepted_spec is not None
            if (
                expected_revision is not None
                and snapshot.bundle.revisions["delivery"] != expected_revision
            ):
                raise _Rejected(
                    "revision_conflict",
                    f"expected delivery revision {expected_revision}, current is "
                    f"{snapshot.bundle.revisions['delivery']}",
                )
            # Per-target mutable state in memory. Graph objects are frozen, so
            # we hold the current stage/ref lists and build one final mutation.
            target_types: dict[str, str] = {}
            originals: dict[str, Any] = {}
            final_stages: dict[str, list[Any]] = {}
            queued_refs: dict[str, set[str]] = {}
            all_ops: list[GraphOperation] = []
            for item in attachments:
                tool_call_id = item["tool_call_id"]
                target_id = item["bind_target"]
                stage_kind = item["stage_kind"]
                try:
                    kind = StageKind(stage_kind)
                except ValueError:
                    raise _Rejected(
                        "unknown_stage",
                        f"unknown stage_kind {stage_kind!r}; allowed: "
                        f"{sorted(item.value for item in StageKind)}",
                    ) from None
                target_type, element = self._delivery_target(
                    snapshot.delivery, target_id
                )
                target_types[target_id] = target_type
                originals.setdefault(target_id, element)
                current_stages = list(
                    final_stages.get(target_id, element.stages)
                )
                # A repeated stage inside one batch should not silently replace
                # an earlier successful binding with a second, unrelated one.
                if any(stage.kind == kind for stage in current_stages):
                    idx = next(i for i, stage in enumerate(current_stages) if stage.kind == kind)
                    if current_stages[idx].status.value != "pending":
                        raise _Rejected(
                            "stage_already_bound",
                            f"stage {kind.value} on {target_id} is already bound "
                            "within this batch; split unrelated attempts into separate batches",
                        )
                ref = self._evidence_for_call(tool_call_id)
                try:
                    source_name, payload = self.store.resolve_evidence_with_source(ref)
                except InvalidGraphReference:
                    raise _Rejected(
                        "invalid_reference",
                        f"evidence reference {ref.ref_id!r} does not resolve",
                    ) from None
                if not self._result_succeeded(payload.get("result") or {}):
                    raise _Rejected(
                        "tool_not_succeeded",
                        f"tool call {tool_call_id!r} did not succeed; a failed or "
                        "unsuccessful computation cannot be bound as evidence",
                    )
                if source_name == "submit_compute_job":
                    raise _Rejected(
                        "bind_target_is_submit",
                        "a submit_compute_job call is never stage evidence; bind "
                        "the parser output of the finished compute job instead",
                    )
                if (
                    target_type == "edge"
                    and kind is StageKind.FREQUENCY
                    and not self._passes_saddle_check(ref)
                ):
                    raise _Rejected(
                        "saddle_check_failed",
                        "TS frequency evidence must show exactly one imaginary "
                        "frequency (n_imag == 1); the stage stays pending",
                    )
                if (
                    target_type == "edge"
                    and kind is StageKind.TS_OPT
                    and not self._passes_ts_opt_check(ref)
                ):
                    raise _Rejected(
                        "ts_opt_check_failed",
                        "ts_opt evidence must be a normally terminated engine log "
                        "(and a first-order saddle if frequencies are present)",
                    )
                if (
                    (
                        (target_type == "node" and kind is StageKind.GEOMETRY)
                        or (target_type == "edge" and kind in {StageKind.ENDPOINT_A, StageKind.ENDPOINT_B})
                    )
                    and not self._passes_minimum_check(ref)
                ):
                    raise _Rejected(
                        "minimum_check_failed",
                        "species geometry and step endpoint evidence must be a verified minimum "
                        "(n_imag == 0); the stage stays pending",
                    )
                if (
                    target_type == "edge"
                    and kind is StageKind.SHORT_IRC
                ):
                    # 批量内同边先绑的 ts_opt/frequency/endpoint 材料可见
                    # （current_stages 含本批次此前的更新）。
                    irc_ok, irc_reason = self._passes_short_irc_check(
                        ref, element, current_stages, snapshot.delivery
                    )
                    if not irc_ok:
                        raise _Rejected("short_irc_check_failed", irc_reason)
                if (
                    target_type == "edge"
                    and kind is StageKind.THERMOCHEMISTRY
                    and not self._passes_thermochemistry_check(ref)
                ):
                    raise _Rejected(
                        "thermochemistry_check_failed",
                        "thermochemistry evidence must be a complete thermo_analysis "
                        "result; the stage stays pending",
                    )
                updated_stages = apply_stage_verdict(
                    current_stages,
                    stage_kind=kind,
                    verdict="agree",
                    ref=ref,
                    tool_succeeded=True,
                    allow_out_of_order=allow_out_of_order,
                )
                final_stages[target_id] = updated_stages
                seen = queued_refs.setdefault(target_id, set())
                if ref.ref_id not in seen:
                    seen.add(ref.ref_id)
                    all_ops.append(
                        AttachRef(
                            op="attach_ref",
                            graph="delivery",
                            target_type=target_type,  # type: ignore[arg-type]
                            target_id=target_id,
                            ref=ref,
                        )
                    )
            for target_id, target_type in target_types.items():
                stages = final_stages[target_id]
                changes = {
                    "stages": [stage.model_dump(mode="json") for stage in stages],
                    "evidence_level": derive_evidence_level(
                        stages, is_edge=target_type == "edge"
                    ),
                }
                all_ops.append(
                    UpdateNode(
                        op="update_node",
                        graph="delivery",
                        node_id=target_id,
                        changes=changes,
                    )
                    if target_type == "node"
                    else UpdateEdge(
                        op="update_edge",
                        graph="delivery",
                        edge_id=target_id,
                        changes=changes,
                    )
                )
            return all_ops, dict(snapshot.bundle.revisions)

        def _reject(rejection: _Rejected) -> dict[str, Any]:
            revisions = dict(self.store.load_bundle().revisions)
            return {
                "attachments": attachments,
                "accepted": False,
                "rejection_code": rejection.code,
                "rejection_reason": rejection.reason,
                "mutation_id": "mut_" + uuid.uuid4().hex,
                "revisions": revisions,
            }

        try:
            operations, seen_revisions = await asyncio.to_thread(_guarded_batch)
        except _Rejected as exc:
            return await asyncio.to_thread(_reject, exc)
        rationale = "stage bind attachments: " + ", ".join(
            f"{item['bind_target']}.{item['stage_kind']}" for item in attachments
        )
        if expected_revision is not None:
            mutation = await asyncio.to_thread(
                self._apply_harness_once,
                operations,
                rationale,
                expected_revision=expected_revision,
            )
            return {
                "attachments": attachments,
                "accepted": mutation.accepted,
                "rejection_code": mutation.rejection_code,
                "rejection_reason": mutation.rejection_reason,
                "mutation_id": mutation.mutation_id,
                "revisions": mutation.revisions,
            }
        last: MutationResult | None = None
        for _attempt in range(8):
            last = await asyncio.to_thread(
                self._apply_with_revisions,
                operations,
                rationale,
                seen_revisions,
            )
            if last.accepted or last.rejection_code != "stale_revision":
                return {
                    "attachments": attachments,
                    "accepted": last.accepted,
                    "rejection_code": last.rejection_code,
                    "rejection_reason": last.rejection_reason,
                    "mutation_id": last.mutation_id,
                    "revisions": last.revisions,
                }
            try:
                operations, seen_revisions = await asyncio.to_thread(_guarded_batch)
            except _Rejected as exc:
                return await asyncio.to_thread(_reject, exc)
        assert last is not None
        raise RuntimeError(
            f"deterministic DAG mutation rejected: {last.rejection_code}: "
            f"{last.rejection_reason}"
        )

    async def _call_verdict_notification(
        self,
        review: CallReview,
        verdict: str,
        target_id: str,
        stage_kind: str,
        reason: str,
    ) -> dict[str, Any]:
        """终态裁决的 durable 通知材料（与 mark_call_review 同事务落表）。

        所有六种终态裁决都通知提交者：每条显式送审恰好一条裁决反馈，
        disagree/needs_evidence 要求行动，agree/skip/not_applicable/ignore
        闭环等待。渲染材料（verdict/target/stage/reason）全在 payload——
        裁决行本身不落 verdict 列，flush 不再回查图存储。
        """
        target = review.suggested_target_id or target_id
        stage = review.suggested_stage or stage_kind
        target_type = ""
        try:
            snapshot = await asyncio.to_thread(self.engine.snapshot)
            target_type, _ = self._delivery_target(snapshot.delivery, target)
        except Exception:  # 目标已被带理由删除等：通知照常落，target 无前缀
            logger.debug(
                "[DagController] verdict notification target %r unresolved", target
            )
        return {
            "recipient_session_id": review.caller_session_id,
            "payload": {
                "verdict": verdict,
                "target_id": target,
                "target_type": target_type,
                "stage_kind": stage,
                "reason": reason.strip(),
                "claim": review.claim,
            },
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
        """Supervisor 的 per-call 复核（D3 + §5）：dag_review_call 的 controller 面。

        §5 起裁决围绕送审的明确 claim：verdict 的目标/阶段必须与送审声明
        （suggested_target_id/suggested_stage）一致，否则 claim_mismatch
        （要改目标/阶段就重新送审）。裁决的证据是送审时的不可变快照——
        agree 时 ref 直接取 review.evidence_id（内容寻址，同名文件被覆盖也
        不改变快照；旧行无 evidence_id 时回退按 tool_call_id 重解析）。
        阶段绑定守卫与 dag_bind_evidence 完全同构（含 D11 submit 检查、
        D7 鞍点检查、tool_not_succeeded）。ignore = 不是 delivery 证据，
        不改阶段；disagree/skip/not_applicable 不解析 ref、reason 必填；
        needs_evidence = 缺证据（reason 必填，列出具体缺失），本轮不再审——
        review 离开 pending 信箱、阶段不动，补充材料后重新送审产生新 review。
        每种终态裁决都与落态同事务写一条 durable 裁决通知（call_verdict），
        由 flush_review_notifications 投递给提交者（dag_stage 的 after_tool
        触发；恢复路径 reconcile 补投）。
        """
        if not self.enabled:
            raise RuntimeError(
                "review_call is disabled in standard orchestration mode"
            )
        await self.initialize()
        review = await asyncio.to_thread(self.store.get_call_review, review_id)
        if review is None:
            raise RuntimeError(f"call review {review_id!r} does not exist")
        if review.source != "explicit":
            raise RuntimeError(
                f"call review {review_id!r} is a {review.source} audit record, "
                "not a consumable submission — only explicit re-submission "
                "(dag_bind_evidence with a claim) enters the reviewable inbox"
            )
        if review.state != "pending":
            raise RuntimeError(
                f"call review {review_id!r} is already {review.state}"
            )
        claim_context = {
            "claim": review.claim,
            "rationale": review.rationale,
            "submitter": review.submitter,
            "is_success": review.is_success,
        }
        if verdict == "ignore":
            await asyncio.to_thread(
                self.store.mark_call_review,
                review_id,
                "ignored",
                notification=await self._call_verdict_notification(
                    review, "ignore", target_id, stage_kind, reason
                ),
            )
            return {
                "review_id": review_id,
                "verdict": "ignore",
                "accepted": True,
                "stage_changed": False,
                **claim_context,
            }
        # §5：裁决必须落在送审声明的目标/阶段上（显式送审的行总带声明）。
        if review.suggested_target_id and (
            target_id != review.suggested_target_id
            or stage_kind != review.suggested_stage
        ):
            raise RuntimeError(
                f"verdict must answer the submitted claim: review {review_id!r} "
                f"claims {review.suggested_target_id}.{review.suggested_stage} "
                f"({review.claim!r}), got {target_id}.{stage_kind} — re-submit "
                "with a new claim to change the target or stage"
            )
        if verdict == "needs_evidence":
            if not reason.strip():
                raise RuntimeError(
                    "needs_evidence requires a reason listing exactly which "
                    "evidence is missing"
                )
            # 本轮不再审：离开 pending 信箱（不 busy-loop），阶段保持不动；
            # 补齐材料后显式重提产生新 review（已裁决同构重提的既有语义）。
            await asyncio.to_thread(
                self.store.mark_call_review,
                review_id,
                "reviewed",
                notification=await self._call_verdict_notification(
                    review, "needs_evidence", target_id, stage_kind, reason
                ),
            )
            return {
                "review_id": review_id,
                "verdict": "needs_evidence",
                "accepted": True,
                "stage_changed": False,
                "missing_evidence": reason.strip(),
                **claim_context,
            }
        ref = None
        tool_succeeded = False
        if verdict == "agree":
            # §5 快照裁决：优先取送审时的 evidence_id（不可变快照）。
            if review.evidence_id:
                ref = await asyncio.to_thread(
                    self._ref_for_evidence_id, review.evidence_id
                )
            else:
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
                self.store.mark_call_review,
                review_id,
                "reviewed",
                notification=await self._call_verdict_notification(
                    review, verdict, target_id, stage_kind, reason
                ),
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
            **claim_context,
        }


async def enqueue_compute_review(taskid: int, terminal_state: str) -> None:
    """计算作业终态的 CallReview 登记（D11）：带作业的终态（done/failed），
    与 submit 调用的成败无关。

    §5 起只在 dag_record 登记（纯审计行，source="auto"，无 Supervisor 消费）；
    dag_guided 不再自动入箱——研究 agent 被 compute_job 事件唤醒后自行解析、
    筛选，经显式送审（dag_bind_evidence with claim）才产生督导待办。
    standard / 无 session 记录 / 会话库不存在时跳过。review_id 按作业确定
    （rev_compute_<id>），重复终态回调由 INSERT OR IGNORE 去重。
    guard/executor 进程内调用：不直接唤醒 Supervisor。
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
    if mode != "dag_record":
        return
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
        source="auto",
        state="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    await asyncio.to_thread(DagStore(conv_db).enqueue_call_review, review)
