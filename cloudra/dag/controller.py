"""Mode-aware harness integration for durable tool evidence and DAG prompts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cloudra.artifacts import ArtifactDownloadDenied, ArtifactService
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
from cloudra.dag.store import DagStore, _canonical_json
from cloudra.database import ConversationDB


class DagController:
    """Deterministic harness writer. Chemistry tools themselves remain stateless."""

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
        if not self.enabled:
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
            await self._trigger_supervisor_after_tool(tool_name, arguments, result, success)
        return evidence_ref

    async def _trigger_supervisor_after_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        success: bool,
    ) -> None:
        """每次工具结束 guided 下最多唤醒一次 Supervisor，按优先级取一。"""
        if self.supervisor is None:
            return
        # 1. Coordinator 的机理图变更被接受 → delivery_updated，
        #    并把它的 rationale 与操作摘要传给 Supervisor 安排计算。
        if tool_name == "dag_graph":
            request = self._coordinator_request(arguments, result)
            if request is not None:
                await self.maybe_supervise("delivery_updated", coordinator_request=request)
            return
        # 2. 普通工具失败 → process_failed。
        if not success:
            await self.maybe_supervise("process_failed")
            return
        # 3. 成功但流程前沿已空且交付未完成 → empty_frontier（比 new_evidence 更紧迫）。
        projection = build_projection(
            self.engine.snapshot(),
            mode=self.mode,
            contract=self.contract,
            history=self.engine.history(limit=8),
        )
        if not projection.frontier and not self.delivery_report().complete:
            await self.maybe_supervise("empty_frontier")
            return
        # 4. 常规新证据。
        await self.maybe_supervise("new_evidence")

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
            "process_failed",
            "process_retried",
            "empty_frontier",
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
        result = await self.supervisor.run(
            trigger,
            coordinator_request=coordinator_request,
            session_id=self.session_id,
        )
        # Supervisor 可能经工具加严过 coverage contract，重新载入。
        self.contract = self.store.load_coverage_contract()
        return result

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
