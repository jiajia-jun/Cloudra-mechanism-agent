"""Mode-aware harness integration for durable tool evidence and DAG prompts."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cloudra.dag.completion import build_projection, evaluate_delivery
from cloudra.dag.engine import _DERIVED_EVIDENCE_FIELDS, DagEngine
from cloudra.dag.models import (
    AddNode,
    AttachRef,
    CoverageContract,
    GraphActor,
    GraphOperation,
    GraphRef,
    MutationBatch,
    MutationResult,
    ObservedNode,
    OrchestrationMode,
    UpdateEdge,
    UpdateNode,
    normalize_orchestration_mode,
)
from cloudra.dag.store import DagStore, InvalidGraphReference, _canonical_json
from cloudra.persistence.artifacts import ArtifactDownloadDenied, ArtifactService
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.tools.capabilities import (
    evidence_deriver_for,
    is_dag_observable,
    supervisor_evidence_tools,
)

logger = logging.getLogger("DagController")

# 工具侧 evidence deriver 可写出的字段白名单：派生证据位由 engine 定义，
# 另加 evidence_level 与 advisory_sources 两个 harness 约定字段。
_DERIVER_ALLOWED_FIELDS = _DERIVED_EVIDENCE_FIELDS | {"advisory_sources", "evidence_level"}

# bind_evidence 的 evidence_role 词表：与 _derive_delivery_changes 的派生分支一一对应。
EVIDENCE_ROLES = frozenset({
    "intermediate_optimization",
    "ts_optimization_frequency",
    "short_irc",
    "endpoint_a_optimization",
    "endpoint_b_optimization",
    "endpoint_direction_check",
    "endpoint_identity_match",
    "thermochemistry",
})

# Supervisor 复核下调（downgraded）：沿证据等级阶梯降一级；
# proposed 及更低（含 rejected/inconclusive 处置级）只能落到 inconclusive。
_EVIDENCE_LEVEL_DOWNGRADE = {
    "thermo_annotated": "endpoint_supported",
    "endpoint_supported": "saddle_supported",
    "saddle_supported": "structure_supported",
    "structure_supported": "proposed",
}


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
        agent_id: str | None = None,
    ):
        self.db = db
        self.session_id = session_id
        self.mode = normalize_orchestration_mode(mode)
        self.conversation_id = conversation_id or db.conversation_id or "default"
        # 投影 assigned_to_me 区块按此 id 过滤（缺省则不输出该区块）
        self.agent_id = agent_id
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
        self._substantive_gate_warned = False

    @property
    def enabled(self) -> bool:
        return self.mode is not OrchestrationMode.STANDARD

    async def initialize(self) -> None:
        """加载图存储与覆盖契约；不自动拉起 Supervisor。

        用户追加/唤醒会再次进入 ``Coordinator.run()`` → ``initialize()``。
        若此处因 delivery 非空自动 ``graph_initialization``，会与首轮用户要求
        抢拍，模型常在 goal/stop 复核提示下空转。排产改由
        ``delivery_updated`` / ``user_replan`` / ``pre_delivery`` 显式触发。
        """
        if not self.enabled or self._initialized:
            return
        await asyncio.to_thread(self.store.ensure_bundle, self.session_id)
        self.contract = await asyncio.to_thread(self.store.load_coverage_contract)
        self._initialized = True

    async def has_graph_content(self) -> bool:
        """process 或 delivery 至少一侧已有节点（空 bundle 不算建图）。"""
        if not self.enabled:
            return True
        # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        return bool(snapshot.process.nodes or snapshot.delivery.nodes)

    async def check_substantive_gate(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[str, str] | None:
        """实质性操作前的 DAG 门槛。

        返回 ``None`` 表示放行；``("block", msg)`` 硬拒绝；``("warn", msg)`` 软警告。

        guided：空图硬拦 → 图非空后，写文件/开算/非调研子 Agent 还须工作流就绪
        （实质机理 + Supervisor 非模板排产）；explorer/researcher 在图非空后放行。
        record：仅空图软警告一次。
        """
        from cloudra.dag.substantive_gate import (
            GUIDED_BLOCK_MESSAGE,
            GUIDED_WORKFLOW_BLOCK_MESSAGE,
            RECORD_WARN_MESSAGE,
            is_early_research_subagent_call,
            is_substantive_tool,
            workflow_ready,
        )

        if not self.enabled or not is_substantive_tool(tool_name, arguments):
            return None
        has_content = await self.has_graph_content()
        if not has_content:
            if self.mode is OrchestrationMode.DAG_GUIDED:
                return "block", GUIDED_BLOCK_MESSAGE
            if self.mode is OrchestrationMode.DAG_RECORD:
                return "warn", RECORD_WARN_MESSAGE
            return None
        if self.mode is not OrchestrationMode.DAG_GUIDED:
            return None
        if is_early_research_subagent_call(tool_name, arguments):
            return None
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        if workflow_ready(snapshot):
            return None
        return "block", GUIDED_WORKFLOW_BLOCK_MESSAGE

    async def prompt_projection(self) -> str:
        if not self.enabled:
            return ""
        await self.initialize()
        # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        history = await asyncio.to_thread(self.engine.history, limit=8)
        projection = build_projection(
            snapshot,
            mode=self.mode,
            contract=self.contract,
            history=history,
            actor_id=self.agent_id,
        )
        return projection.to_prompt_text(actor_id=self.agent_id)

    def delivery_report(self):
        if not self.enabled:
            return None
        return evaluate_delivery(self.engine.snapshot().delivery, self.contract)

    async def _has_pending_background(self) -> bool:
        """会话级后台是否还有未竟工作（子任务/计算/定时提醒）。

        与 runner._count_pending_tasks 同一判定口径：只要后台未排空，
        stop 就是"挂起等唤醒"而不是交付。
        """
        from cloudra.persistence.database import aretry_on_locked

        async def query():
            async with self.db.aconnect() as con:
                cur = await con.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM subagent_requests WHERE state IN ('ready', 'running') AND conversation_id = ?),
                        (SELECT COUNT(*) FROM compute_jobs WHERE state IN ('ready', 'running') AND conversation_id = ?),
                        (SELECT COUNT(*) FROM scheduled_reminders WHERE state = 'pending' AND conversation_id = ?)
                    """,
                    (self.conversation_id, self.conversation_id, self.conversation_id),
                )
                return await cur.fetchone()

        row = await aretry_on_locked(query)
        return bool(row and any(row))

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

    async def on_tool_started(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        if not self.enabled or not is_dag_observable(tool_name):
            return None
        await self.initialize()
        # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
        snapshot = await asyncio.to_thread(self.engine.snapshot)
        existing = next(
            (
                node
                for node in snapshot.process.nodes
                if node.tool_call_id == tool_call_id
            ),
            None,
        )
        if existing is not None:
            return existing.node_id
        candidates = [
            node
            for node in snapshot.process.nodes
            if node.tool_name == tool_name
            and node.status in {"proposed", "ready"}
            and not node.tool_call_id
        ]
        args_hash = "sha256:" + hashlib.sha256(
            _canonical_json(arguments).encode("utf-8")
        ).hexdigest()
        if len(candidates) == 1:
            node_id = candidates[0].node_id
            operations = [
                UpdateNode(
                    op="update_node",
                    graph="process",
                    node_id=node_id,
                    changes={
                        "status": "running",
                        "tool_call_id": tool_call_id,
                        "arguments_hash": args_hash,
                    },
                )
            ]
        else:
            node_id = "observed_" + hashlib.sha256(
                tool_call_id.encode("utf-8")
            ).hexdigest()[:20]
            operations = [
                AddNode(
                    op="add_node",
                    graph="process",
                    node=ObservedNode(
                        node_id=node_id,
                        label=tool_name,
                        status="running",
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        arguments_hash=args_hash,
                        unplanned=True,
                    ),
                )
            ]
        # 同步 SQLite 写不能在事件循环线程上执行：busy 等待会冻结整个循环，
        # 使同进程 aiosqlite 连接无法提交，形成跨进程 5 分钟级自死锁
        # （"database is locked" 根因）。一律 offload 到 worker 线程。
        await asyncio.to_thread(
            self._apply_harness, operations, f"tool started: {tool_name}"
        )
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
        if not is_dag_observable(tool_name):
            # 不记录编排平面调用本身，但 Coordinator 的机理变更仍要唤醒 Supervisor。
            if self.mode is OrchestrationMode.DAG_GUIDED:
                await self._trigger_supervisor_after_tool(
                    tool_name, arguments, result, self._result_succeeded(result)
                )
            return None
        await self.initialize()
        await self.on_tool_started(tool_call_id, tool_name, arguments)
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
        node = await asyncio.to_thread(self._process_node_for_call, tool_call_id)
        refs = [
            evidence_ref,
            *await asyncio.to_thread(self._snapshot_output_artifacts, result),
        ]
        success = self._result_succeeded(result)
        operations = [
            AttachRef(
                op="attach_ref",
                graph="process",
                target_type="node",
                target_id=node.node_id,
                ref=ref,
            )
            for ref in refs
        ]
        operations.append(
            UpdateNode(
                op="update_node",
                graph="process",
                node_id=node.node_id,
                changes={
                    "status": "succeeded" if success else "failed",
                    "evidence_source": tool_name,
                },
            )
        )
        await asyncio.to_thread(
            self._apply_harness, operations, f"tool finished: {tool_name}"
        )
        await asyncio.to_thread(
            self._adapt_delivery, node, tool_name, arguments, result, refs
        )
        if self.mode is OrchestrationMode.DAG_GUIDED:
            bound = bool(
                node.delivery_target_id
                and node.delivery_target_type in {"node", "edge"}
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
            # Coordinator → Supervisor 留言：不改图，只唤醒督导
            if (
                arguments.get("action") == "message_supervisor"
                and result.get("is_success")
            ):
                msg = str(arguments.get("message") or "").strip()
                if msg:
                    await self.maybe_supervise(
                        "coordinator_message", coordinator_request=msg
                    )
                return
            # bind_evidence 成功挂载即新证据落地（等级已由 harness 派生），复核它
            # 消除了哪些 delivery 缺口、挂载是否张冠李戴。
            if arguments.get("action") == "bind_evidence" and result.get("accepted"):
                await self.maybe_supervise("new_evidence")
                return
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
            if bound_to_delivery or tool_name in supervisor_evidence_tools():
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
        # op 可能是新具名形状（edge_id 顶层）或旧 data 形状，摘要两种都认
        summary = ", ".join(
            f"{op.get('op')}:{op.get('graph')}:{op.get('edge_id') or (op.get('data') or {}).get('edge_id')}"
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
            "coordinator_message",
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
        run_session_id = await asyncio.to_thread(
            self._register_supervisor_session, trigger, coordinator_request
        )
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
                # a-0 自己的工具循环里 Supervisor 是同步 await，钉建议即可；
                # 子 Agent / API（agent_id 不是 a-0）时 Coordinator 可能 waiting。
                wake_coordinator=self.agent_id != "a-0",
            )
            # Supervisor 可能经工具加严过 coverage contract，重新载入。
            # 同步 sqlite 读也走 worker 线程，busy 等待不能占用事件循环
            self.contract = await asyncio.to_thread(self.store.load_coverage_contract)
        except Exception as exc:  # Supervisor 是顾问角色：故障不炸 Coordinator 循环
            error_note = str(exc)
            logger.warning("[DagController] supervisor run failed (%s): %s", trigger, exc)
        await asyncio.to_thread(
            self._finalize_supervisor_session, run_session_id, trigger, result, error_note
        )
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
            report = getattr(result, "report", "") or ""
            if report.strip():
                summary += f" | {report.strip()[:200]}"
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
        nodes = self.engine.snapshot().process.nodes
        matches = [
            node for node in nodes if node.tool_call_id == tool_call_id
        ]
        if not matches:
            # 兜底：上下文压缩后 tool_call_id 可能丢失，允许直接传
            # observed_<hex> 节点 id 作为别名（bind_evidence 高层动作用）。
            matches = [node for node in nodes if node.node_id == tool_call_id]
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
        target_type = process_node.delivery_target_type
        target_id = process_node.delivery_target_id
        if target_type not in {"node", "edge"} or not target_id:
            return
        graph = self.engine.snapshot().delivery
        collection = graph.nodes if target_type == "node" else graph.edges
        target = next((item for item in collection if getattr(item, f"{target_type}_id") == target_id), None)
        if target is None:
            raise RuntimeError(f"planned delivery target {target_type}:{target_id} is missing")

        operations = [
            AttachRef(
                op="attach_ref",
                graph="delivery",
                target_type=target_type,
                target_id=target_id,
                ref=ref,
            )
            for ref in refs
        ]
        changes = self._derive_delivery_changes(
            target.payload,
            process_node.evidence_role or "",
            tool_name,
            arguments,
            result,
        )
        if changes:
            operations.append(
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
        deriver = evidence_deriver_for(tool_name)
        if deriver is None:
            return {}
        raw_changes = deriver(current=current, role=role, arguments=arguments, result=result)
        changes = {
            key: value
            for key, value in (raw_changes or {}).items()
            if key in _DERIVER_ALLOWED_FIELDS
        }
        if not changes:
            return {}
        # 通用提升逻辑仍由 harness 持有：endpoint 证据位齐了升级为
        # endpoint_supported；再叠加 thermochemistry 则升级为 thermo_annotated。
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
            ],
            f"re-derive {target_type} {target_id} from retro-attached {tool_name} evidence",
        )
        return changes

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

    async def bind_evidence_for_call(
        self,
        tool_call_id: str,
        target_id: str,
        evidence_role: str,
    ) -> dict[str, Any]:
        """agent 高层挂证据：tool_call_id → 已登记证据 → attach + 确定性派生。

        agent 不需要看见 ev_ id：只要给出自己发起的工具调用（或 observed 节点 id
        别名）、delivery 目标和证据角色。三道确定性校验：证据已登记（
        on_tool_finished 已把 tool_result ref 挂到 process 节点）、该次计算确实
        成功、目标元素存在；attach 与等级派生都走 _apply_harness（自带 stale 重试）。
        """
        if not self.enabled:
            raise RuntimeError(
                "bind_evidence is disabled in standard orchestration mode"
            )
        if evidence_role not in EVIDENCE_ROLES:
            raise RuntimeError(
                f"unknown evidence_role {evidence_role!r}; allowed: {sorted(EVIDENCE_ROLES)}"
            )
        await self.initialize()
        node = await asyncio.to_thread(self._process_node_for_call, tool_call_id)
        ref = next((r for r in node.refs if r.ref_type == "tool_result"), None)
        if ref is None:
            raise RuntimeError(
                f"tool call {tool_call_id!r} has no registered evidence; only a "
                "finished tool call with a recorded tool_result can be bound"
            )
        _, payload = await asyncio.to_thread(
            self.store.resolve_evidence_with_source, ref
        )
        if not self._result_succeeded(payload.get("result") or {}):
            raise RuntimeError(
                f"tool call {tool_call_id!r} did not succeed; a failed or "
                "unsuccessful computation cannot be bound as evidence"
            )
        def _locate_target():
            # snapshot 是同步 sqlite 读，连同定位一起放进 worker 线程
            return self._delivery_target(self.engine.snapshot().delivery, target_id)

        target_type, _ = await asyncio.to_thread(_locate_target)
        await asyncio.to_thread(
            self._apply_harness,
            [
                AttachRef(
                    op="attach_ref",
                    graph="delivery",
                    target_type=target_type,
                    target_id=target_id,
                    ref=ref,
                )
            ],
            f"bind evidence of {tool_call_id} to delivery {target_type} {target_id}",
        )
        changes = await asyncio.to_thread(
            self.rederive_delivery_element, target_type, target_id, ref, evidence_role
        )
        return {
            "target_type": target_type,
            "target_id": target_id,
            "ref_id": ref.ref_id,
            "evidence_role": evidence_role,
            "changes": changes or {},
            "derived": bool(changes),
        }

    async def review_evidence(
        self,
        target_id: str,
        verdict: str,
        rationale: str,
        reviewer: str = "supervisor",
    ) -> dict[str, Any]:
        """Supervisor 证据复核：delivery 对 Supervisor 只读，下调由 harness 代写。

        confirmed 不改图（无需动作）；downgraded 沿等级阶梯降一级；rejected 落到
        inconclusive 并标记否决。journal 以 actor=HARNESS 记录 Supervisor 的
        verdict 与理由；否决/下调后向挂载者 session 与 Coordinator 各投一条
        evidence_vetoed 事件。
        """
        if not self.enabled:
            raise RuntimeError(
                "review_evidence is disabled in standard orchestration mode"
            )
        await self.initialize()
        def _locate_target():
            # snapshot 是同步 sqlite 读，连同定位一起放进 worker 线程
            return self._delivery_target(self.engine.snapshot().delivery, target_id)

        target_type, target = await asyncio.to_thread(_locate_target)
        old_level = target.evidence_level
        if verdict == "confirmed":
            # 确认无需动作：等级维持，图与 journal 都不动。
            return {
                "target_type": target_type,
                "target_id": target_id,
                "verdict": verdict,
                "evidence_level": old_level,
                "changed": False,
            }
        if verdict == "downgraded":
            new_level = _EVIDENCE_LEVEL_DOWNGRADE.get(old_level, "inconclusive")
            changes = {
                "evidence_level": new_level,
                "reason": f"{verdict} by {reviewer}: {rationale}",
            }
        else:  # rejected：证据不被认可，落 inconclusive 并显式标记否决
            new_level = "inconclusive"
            changes = {
                "evidence_level": new_level,
                "reason": f"{verdict} by {reviewer}: {rationale}",
                "evidence_vetoed": True,
            }
        await asyncio.to_thread(
            self._apply_harness,
            [
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
            ],
            f"supervisor evidence review ({verdict}) by {reviewer}: {rationale}",
        )
        await self._notify_evidence_vetoed(
            target_type, target_id, old_level, new_level, verdict, rationale,
            list(target.refs),
        )
        return {
            "target_type": target_type,
            "target_id": target_id,
            "verdict": verdict,
            "evidence_level": new_level,
            "previous_evidence_level": old_level,
            "changed": True,
        }

    def _resolve_evidence_binder(self, refs: list[GraphRef]):
        """反查挂载者：tool_result ref → dag_evidence.session_id → session.agent_id。

        查不到（证据来自别的会话、老记录缺 session）时返回 (None, None)，
        调用方只通知 Coordinator。
        """
        for ref in refs:
            if ref.ref_type != "tool_result":
                continue
            with self.db.connect() as con:
                row = con.execute(
                    "SELECT session_id FROM dag_evidence WHERE evidence_id = ?",
                    (ref.ref_id,),
                ).fetchone()
                if not row or not row[0]:
                    continue
                agent_row = con.execute(
                    "SELECT agent_id FROM session WHERE session_id = ?", (row[0],)
                ).fetchone()
            if agent_row and agent_row[0]:
                return agent_row[0], row[0]
        return None, None

    async def _notify_evidence_vetoed(
        self,
        target_type: str,
        target_id: str,
        old_level: str,
        new_level: str,
        verdict: str,
        rationale: str,
        refs: list[GraphRef],
    ) -> None:
        """否决/下调通知：挂载者 session 跟进补救，Coordinator 保有全局视野。"""
        from cloudra.persistence.context_manager import ContextManager

        binder_agent, binder_session = await asyncio.to_thread(
            self._resolve_evidence_binder, refs
        )
        guidance = (
            "Suggested next step: recompute after the fix, then bind_evidence to reattach "
            "the new evidence to this element; if you believe the review is wrong, explain your basis in the reply."
            if verdict == "rejected"
            else "Suggested next step: add the missing compute evidence to restore the level, "
            "or explain in the reply why the current evidence is sufficient."
        )
        content = (
            f"Supervisor evidence review ({verdict}): delivery {target_type} {target_id} "
            f"evidence level {old_level} → {new_level}.\n"
            f"Rationale: {rationale}\n"
            f"{guidance}"
        )
        # 与 monitor 计算终态事件同一路由：提交者定向到其 session，Coordinator 广播。
        targets = {binder_agent: binder_session, "a-0": None} if binder_agent else {"a-0": None}
        for agent_id, session_id in targets.items():
            try:
                await ContextManager.inject_event(
                    conversation_id=self.conversation_id,
                    agent_id=agent_id,
                    event_type="evidence_vetoed",
                    content=content,
                    db_path=self.db.path,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.warning(
                    "[DagController] evidence_vetoed 事件注入失败 (%s，已忽略): %s",
                    agent_id, exc,
                )
