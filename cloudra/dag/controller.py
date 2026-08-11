"""Mode-aware harness integration for durable tool evidence and DAG prompts."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cloudra.dag.completion import build_projection, evaluate_delivery
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    CoverageContract,
    GraphActor,
    GraphOperation,
    GraphRef,
    MutationBatch,
    MutationResult,
    OrchestrationMode,
    normalize_orchestration_mode,
)
from cloudra.dag.store import DagStore, InvalidGraphReference, _canonical_json
from cloudra.persistence.artifacts import ArtifactDownloadDenied, ArtifactService
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store

logger = logging.getLogger("DagController")


class DagController:
    """Deterministic harness writer. Chemistry tools themselves remain stateless."""

    # 编排平面自身的工具不作为化学工作记录：dag_graph 的每次 view/mutate 若
    # 被观察，会产生自引用噪声——失败的 mutate 变成 blocker、process revision
    # 空转，进一步加剧版本竞争。Supervisor 触发（delivery_updated）仍保留。
    _OBSERVATION_EXEMPT_TOOLS = frozenset({"dag_graph"})

    _OUTPUT_PATH_KEYS = {
        "output_path",
        "output_file",
        "input_file_path",
        "image_path",
        "ts_candidate_path",
        "irc_end_a_path",
        "irc_end_b_path",
    }

    def __init__(
        self,
        db: ConversationDB,
        session_id: str,
        mode: str | OrchestrationMode,
        *,
        conversation_id: str | None = None,
        working_directory: str | Path | None = None,
        artifact_data_dir: str | Path | None = None,
        supervisor=None,
    ):
        self.db = db
        self.session_id = session_id
        self.mode = normalize_orchestration_mode(mode)
        self.conversation_id = conversation_id or db.conversation_id or "default"
        self.working_directory = (
            Path(working_directory).expanduser().resolve()
            if working_directory is not None
            else None
        )
        self.store = DagStore(db)
        self.engine = DagEngine(self.store)
        self.contract = CoverageContract.mechanism_default()
        self.artifacts = ArtifactService(
            Path(artifact_data_dir) if artifact_data_dir is not None else None
        )
        self.supervisor = supervisor
        self._initialized = False

    @property
    def enabled(self) -> bool:
        return self.mode is not OrchestrationMode.STANDARD

    async def initialize(self) -> None:
        if not self.enabled or self._initialized:
            return
        self.store.ensure_bundle(self.session_id)
        self.contract = self.store.load_coverage_contract()
        self._initialized = True
        if (
            self.mode is OrchestrationMode.DAG_GUIDED
            and self.supervisor is not None
            # fresh 会话两张图都是空的，无事可规划；仅恢复会话（delivery
            # 已有 Coordinator 设计的机理假设）时唤醒 Supervisor 补齐流程工作。
            and self.engine.snapshot().delivery.nodes
        ):
            await self.maybe_supervise("graph_initialization")

    async def prompt_projection(self) -> str:
        if not self.enabled:
            return ""
        await self.initialize()
        projection = build_projection(
            self.engine.snapshot(),
            mode=self.mode,
            contract=self.contract,
            history=self.engine.history(limit=8),
        )
        return projection.to_prompt_text()

    def delivery_report(self):
        if not self.enabled:
            return None
        return evaluate_delivery(self.engine.snapshot().delivery, self.contract)

    async def audit_stop(self, disposition: str):
        if not self.enabled:
            return True, None
        await self.initialize()
        report = self.delivery_report()
        if disposition == "complete" and not report.complete:
            if self.mode is OrchestrationMode.DAG_GUIDED:
                await self.maybe_supervise("pre_delivery")
                report = self.delivery_report()
            if not report.complete:
                return False, report
        self.store.record_delivery_disposition(
            self.session_id,
            disposition,
            report,
        )
        return True, report

    async def on_tool_started(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        if not self.enabled or tool_name in self._OBSERVATION_EXEMPT_TOOLS:
            return None
        await self.initialize()
        snapshot = self.engine.snapshot()
        existing = next(
            (
                node
                for node in snapshot.process.nodes
                if node.payload.get("tool_call_id") == tool_call_id
            ),
            None,
        )
        if existing is not None:
            return existing.node_id
        candidates = [
            node
            for node in snapshot.process.nodes
            if node.payload.get("tool_name") == tool_name
            and node.payload.get("status", "proposed") in {"proposed", "ready"}
            and not node.payload.get("tool_call_id")
        ]
        args_hash = "sha256:" + hashlib.sha256(
            _canonical_json(arguments).encode("utf-8")
        ).hexdigest()
        if len(candidates) == 1:
            node_id = candidates[0].node_id
            operations = [
                GraphOperation(
                    op="update_node",
                    graph="process",
                    data={
                        "node_id": node_id,
                        "changes": {
                            "status": "running",
                            "tool_call_id": tool_call_id,
                            "arguments_hash": args_hash,
                        },
                    },
                )
            ]
        else:
            node_id = "observed_" + hashlib.sha256(
                tool_call_id.encode("utf-8")
            ).hexdigest()[:20]
            operations = [
                GraphOperation(
                    op="add_node",
                    graph="process",
                    data={
                        "node_id": node_id,
                        "node_type": "observed_tool_call",
                        "label": tool_name,
                        "payload": {
                            "status": "running",
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "arguments_hash": args_hash,
                            "unplanned": True,
                        },
                    },
                )
            ]
        self._apply_harness(operations, f"tool started: {tool_name}")
        return node_id

    async def on_tool_finished(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> GraphRef | None:
        if not self.enabled:
            return None
        if tool_name in self._OBSERVATION_EXEMPT_TOOLS:
            # 不记录编排平面调用本身，但 Coordinator 的机理变更仍要唤醒 Supervisor。
            if self.mode is OrchestrationMode.DAG_GUIDED:
                await self._trigger_supervisor_after_tool(
                    tool_name, arguments, result, self._result_succeeded(result)
                )
            return None
        await self.initialize()
        await self.on_tool_started(tool_call_id, tool_name, arguments)
        evidence_ref = self.store.register_evidence(
            self.session_id,
            tool_name,
            {
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "result": result,
            },
        )
        node = self._process_node_for_call(tool_call_id)
        refs = [evidence_ref, *self._snapshot_output_artifacts(result)]
        success = self._result_succeeded(result)
        operations = [
            GraphOperation(
                op="attach_ref",
                graph="process",
                data={
                    "target_type": "node",
                    "target_id": node.node_id,
                    "ref": ref.model_dump(mode="json"),
                },
            )
            for ref in refs
        ]
        operations.append(
            GraphOperation(
                op="update_node",
                graph="process",
                data={
                    "node_id": node.node_id,
                    "changes": {
                        "status": "succeeded" if success else "failed",
                        "evidence_source": tool_name,
                    },
                },
            )
        )
        self._apply_harness(operations, f"tool finished: {tool_name}")
        self._adapt_delivery(node, tool_name, arguments, result, refs)
        if self.mode is OrchestrationMode.DAG_GUIDED:
            bound = bool(
                node.payload.get("delivery_target_id")
                and node.payload.get("delivery_target_type") in {"node", "edge"}
            )
            await self._trigger_supervisor_after_tool(
                tool_name, arguments, result, success, bound_to_delivery=bound
            )
        return evidence_ref

    async def _trigger_supervisor_after_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        success: bool,
        bound_to_delivery: bool = False,
    ) -> None:
        """每次工具结束 guided 下最多唤醒一次 Supervisor，按优先级取一。

        触发口：
        1. Coordinator 的机理图变更被接受 → delivery_updated（附 rationale 摘要）；
        2. dag_graph 的删边请求被转交 → edge_removal_requested（Supervisor 复核）；
        3. 绑定到 delivery 目标的工具成功落地新证据 → new_evidence；
           未绑定但 gaussian_log_parser 成功也按新证据处理；
        4. 绑定到 delivery 目标的工具失败 → process_node_failed。
        """
        if self.supervisor is None:
            return
        # 1/2. dag_graph 调用：区分接受的机理变更与被转交的删边请求。
        if tool_name == "dag_graph":
            request = self._coordinator_request(arguments, result)
            if request is not None:
                await self.maybe_supervise("delivery_updated", coordinator_request=request)
                return
            removal = self._edge_removal_request(arguments, result)
            if removal is not None:
                await self.maybe_supervise(
                    "edge_removal_requested", coordinator_request=removal
                )
            return
        # 3/4. 证据类工具：绑定到 delivery 目标的成败都要复核；
        # 未绑定的只保留 gaussian_log_parser 成功这一个口。
        if success:
            if bound_to_delivery or tool_name == "gaussian_log_parser":
                await self.maybe_supervise("new_evidence")
        elif bound_to_delivery:
            await self.maybe_supervise("process_node_failed")

    @staticmethod
    def _edge_removal_request(
        arguments: dict[str, Any], result: dict[str, Any]
    ) -> str | None:
        """从一次被拒的 dag_graph mutate 中提取删边复核请求。"""
        if arguments.get("action") != "mutate" or result.get("accepted") is not False:
            return None
        if result.get("rejection_code") != "edge_removal_requires_supervisor":
            return None
        operations = arguments.get("operations") or []
        summary = ", ".join(
            f"{op.get('op')}:{op.get('graph')}:{(op.get('data') or {}).get('edge_id')}"
            for op in operations
            if isinstance(op, dict)
        )
        rationale = arguments.get("rationale") or ""
        return f"edge removal requested — rationale: {rationale}\noperations: {summary}"

    @staticmethod
    def _coordinator_request(
        arguments: dict[str, Any], result: dict[str, Any]
    ) -> str | None:
        """从一次 dag_graph 调用中提取 Coordinator 的机理变更说明。"""
        if arguments.get("action") != "mutate" or not result.get("accepted"):
            return None
        operations = arguments.get("operations") or []
        touches_delivery = any(
            op.get("graph") == "delivery" or op.get("op") == "add_link"
            for op in operations
            if isinstance(op, dict)
        )
        if not touches_delivery:
            return None
        summary = ", ".join(
            f"{op.get('op')}:{op.get('graph')}"
            for op in operations
            if isinstance(op, dict)
        )
        rationale = arguments.get("rationale") or ""
        return f"rationale: {rationale}\noperations: {summary}"

    async def maybe_supervise(
        self, trigger: str, coordinator_request: str | None = None
    ):
        allowed_triggers = {
            "graph_initialization",
            "delivery_updated",
            "new_evidence",
            "user_replan",
            "pre_delivery",
            "edge_removal_requested",
            "process_node_failed",
        }
        if (
            self.mode is not OrchestrationMode.DAG_GUIDED
            or self.supervisor is None
            or trigger not in allowed_triggers
        ):
            return None
        await self.initialize()
        run_session_id = self._register_supervisor_session(trigger, coordinator_request)
        event_sink = None
        if run_session_id is not None:
            # 运行过程写进 supervisor 自己的 session 事件流：
            # TUI 选中它的 session 行即可看到推理与 dag_graph 调用。
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
            self.contract = self.store.load_coverage_contract()
        except Exception as exc:  # Supervisor 是顾问角色：故障不炸 Coordinator 循环
            error_note = str(exc)
            logger.warning("[DagController] supervisor run failed (%s): %s", trigger, exc)
        self._finalize_supervisor_session(run_session_id, trigger, result, error_note)
        return result

    def _register_supervisor_session(
        self, trigger: str, coordinator_request: str | None
    ) -> str | None:
        """把一次 Supervisor 触发登记为子 Agent 会话：侧栏可见、状态实时流转。

        上下文文件本身由 SupervisorAgent 的 ContextManager 持久化（会话级），
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
                query=query[:200],
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
        try:
            session_store.finalize_session(
                self.db,
                session_id,
                state,
                result=summary[:500] or None,
                error=error_note,
            )
        except Exception as exc:
            logger.warning("[DagController] supervisor session 终态落库失败（已忽略）: %s", exc)

    def _process_node_for_call(self, tool_call_id: str):
        matches = [
            node
            for node in self.engine.snapshot().process.nodes
            if node.payload.get("tool_call_id") == tool_call_id
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"tool call {tool_call_id!r} does not resolve to exactly one process node"
            )
        return matches[0]

    def _apply_harness(
        self,
        operations: list[GraphOperation],
        rationale: str,
    ) -> MutationResult:
        for attempt in range(2):
            result = self.engine.apply_batch(
                MutationBatch(
                    session_id=self.session_id,
                    actor=GraphActor.HARNESS,
                    actor_id="dag-controller",
                    base_revisions=self.store.load_bundle().revisions,
                    operations=operations,
                    rationale=rationale,
                )
            )
            if result.accepted:
                return result
            if result.rejection_code != "stale_revision" or attempt == 1:
                raise RuntimeError(
                    f"deterministic DAG mutation rejected: {result.rejection_code}: "
                    f"{result.rejection_reason}"
                )
        raise RuntimeError("unreachable")

    @staticmethod
    def _result_succeeded(result: dict[str, Any]) -> bool:
        for key in ("is_success", "success", "is_written"):
            if key in result:
                return bool(result[key])
        return "error" not in result

    def _snapshot_output_artifacts(self, result: dict[str, Any]) -> list[GraphRef]:
        if self.working_directory is None:
            return []
        refs: list[GraphRef] = []
        seen: set[Path] = set()
        for key, raw_value in result.items():
            if key not in self._OUTPUT_PATH_KEYS or not raw_value:
                continue
            path = Path(str(raw_value)).expanduser()
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                continue
            if resolved in seen or not resolved.is_file():
                continue
            try:
                artifact = self.artifacts.register_file(
                    conversation_id=self.conversation_id,
                    session_id=self.session_id,
                    source=resolved,
                    allowed_root=self.working_directory,
                )
            except (ArtifactDownloadDenied, OSError):
                continue
            seen.add(resolved)
            refs.append(
                GraphRef(
                    ref_type="artifact",
                    ref_id=artifact.artifact_id,
                    content_hash=f"sha256:{artifact.sha256}",
                )
            )
        return refs

    def _adapt_delivery(
        self,
        process_node,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        refs: list[GraphRef],
    ) -> None:
        target_type = process_node.payload.get("delivery_target_type")
        target_id = process_node.payload.get("delivery_target_id")
        if target_type not in {"node", "edge"} or not target_id:
            return
        graph = self.engine.snapshot().delivery
        collection = graph.nodes if target_type == "node" else graph.edges
        target = next((item for item in collection if getattr(item, f"{target_type}_id") == target_id), None)
        if target is None:
            raise RuntimeError(f"planned delivery target {target_type}:{target_id} is missing")

        operations = [
            GraphOperation(
                op="attach_ref",
                graph="delivery",
                data={
                    "target_type": target_type,
                    "target_id": target_id,
                    "ref": ref.model_dump(mode="json"),
                },
            )
            for ref in refs
        ]
        changes = self._derive_delivery_changes(
            target.payload,
            process_node.payload.get("evidence_role", ""),
            tool_name,
            arguments,
            result,
        )
        if changes:
            operations.append(
                GraphOperation(
                    op="update_node" if target_type == "node" else "update_edge",
                    graph="delivery",
                    data={
                        f"{target_type}_id": target_id,
                        "changes": changes,
                    },
                )
            )
        if operations:
            self._apply_harness(
                operations,
                f"attach {tool_name} evidence to delivery {target_type} {target_id}",
            )

    @staticmethod
    def _derive_delivery_changes(
        current: dict[str, Any],
        role: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        if not DagController._result_succeeded(result):
            return {}
        changes: dict[str, Any] = {}
        if tool_name in {"ts_guess", "scan_parse"}:
            advisory = list(current.get("advisory_sources", []))
            if tool_name not in advisory:
                advisory.append(tool_name)
            changes["advisory_sources"] = advisory
            if (
                tool_name == "ts_guess"
                and role == "endpoint_direction_check"
                and arguments.get("strict") is True
                and result.get("verdict") == "pass"
            ):
                changes["endpoint_direction_consistent"] = True
        elif tool_name == "gaussian_log_parser":
            imaginary = result.get("imaginary_frequencies") or []
            normal = result.get("normal_termination") is not False
            if role == "intermediate_optimization" and normal and len(imaginary) == 0:
                changes["evidence_level"] = "structure_supported"
            elif role == "ts_optimization_frequency" and normal and len(imaginary) == 1:
                changes.update(
                    saddle_supported=True,
                    evidence_level="saddle_supported",
                )
            elif role == "short_irc" and (
                result.get("irc_both_directions_converged") is True
                or (
                    int(result.get("irc_num_points_forward") or 0) > 0
                    and int(result.get("irc_num_points_backward") or 0) > 0
                )
            ):
                changes["short_irc_supported"] = True
            elif role == "endpoint_a_optimization" and normal and len(imaginary) == 0:
                changes["endpoint_a_minimum_supported"] = True
            elif role == "endpoint_b_optimization" and normal and len(imaginary) == 0:
                changes["endpoint_b_minimum_supported"] = True
        elif tool_name == "reaction_mapping" and role == "endpoint_identity_match":
            if (
                result.get("binding_status") == "complete"
                and result.get("reactant_identity") == "match"
                and result.get("product_identity") == "match"
            ):
                changes["endpoint_identity_matched"] = True
        elif tool_name == "thermo_analysis" and role == "thermochemistry":
            changes["thermochemistry_supported"] = True

        combined = {**current, **changes}
        endpoint_flags = {
            "saddle_supported",
            "short_irc_supported",
            "endpoint_a_minimum_supported",
            "endpoint_b_minimum_supported",
            "endpoint_direction_consistent",
            "endpoint_identity_matched",
        }
        if endpoint_flags <= {key for key, value in combined.items() if value is True}:
            changes["evidence_level"] = "endpoint_supported"
        if combined.get("evidence_level") == "endpoint_supported" and changes.get(
            "thermochemistry_supported"
        ):
            changes["evidence_level"] = "thermo_annotated"
        return changes

    def rederive_delivery_element(
        self,
        target_type: str,
        target_id: str,
        ref: GraphRef,
        evidence_role: str,
    ) -> dict[str, Any] | None:
        """事后认领：把一条已登记的 tool_result 证据按指定 role 补挂到
        delivery 元素后，重跑确定性派生，升级该元素的证据等级。

        正常路径是「Supervisor 排产 → 绑定工具调用 → 完成时自动派生」；
        先算后建图的场景下模型用 attach_ref（带 evidence_role）补挂证据，
        由这里补齐派生。返回应用的 changes，无法派生时返回 None。
        """
        if target_type not in {"node", "edge"} or not evidence_role:
            return None
        try:
            tool_name, payload = self.store.resolve_evidence_with_source(ref)
        except InvalidGraphReference:
            return None
        arguments = payload.get("arguments") or {}
        result = payload.get("result") or {}
        graph = self.engine.snapshot().delivery
        collection = graph.nodes if target_type == "node" else graph.edges
        target = next(
            (item for item in collection if getattr(item, f"{target_type}_id") == target_id),
            None,
        )
        if target is None:
            return None
        changes = self._derive_delivery_changes(
            target.payload, evidence_role, tool_name, arguments, result
        )
        if not changes:
            return None
        self._apply_harness(
            [
                GraphOperation(
                    op="update_node" if target_type == "node" else "update_edge",
                    graph="delivery",
                    data={f"{target_type}_id": target_id, "changes": changes},
                )
            ],
            f"re-derive {target_type} {target_id} from retro-attached {tool_name} evidence",
        )
        return changes
