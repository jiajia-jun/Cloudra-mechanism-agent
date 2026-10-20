"""Shared mode gate, mutation apply, view compaction, and template helpers."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from cloudra.base.role_identity import legacy_agent_id_for_role
from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, output_schema
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    CoverageContract,
    GraphActor,
    GraphKind,
    GraphOperation,
    MutationBatch,
    MutationResult,
    OrchestrationMode,
    normalize_orchestration_mode,
)
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB

# graph_kind 子图视图只保留交付审计需要的字段。完整 refs/hash 对 Supervisor
# 几乎无用（attach_ref 时另用证据库），却把单页 view 撑到 20k+ 字符。
# 旧库的派生旗标（saddle_supported 等）仍可能出现在 legacy 元素上，保留展示。
_VIEW_PAYLOAD_KEYS = (
    "status",
    "evidence_level",
    "reason",
    "required",
)
_ANNOTATION_VIEW_CHARS = 240


def _compact_view_node(node: dict[str, Any]) -> dict[str, Any]:
    payload = node.get("payload") or {}
    compact_payload = {
        key: payload[key] for key in _VIEW_PAYLOAD_KEYS if key in payload
    }
    annotations = payload.get("annotations")
    if annotations is not None:
        text = annotations if isinstance(annotations, str) else json.dumps(
            annotations, ensure_ascii=False, default=str
        )
        compact_payload["annotations"] = text[:_ANNOTATION_VIEW_CHARS]
    refs = node.get("refs") or []
    return {
        "node_id": node.get("node_id"),
        "node_type": node.get("node_type"),
        "label": node.get("label"),
        "payload": compact_payload,
        "n_refs": len(refs),
    }


def _compact_view_edge(edge: dict[str, Any]) -> dict[str, Any]:
    payload = edge.get("payload") or {}
    compact_payload = {
        key: payload[key] for key in _VIEW_PAYLOAD_KEYS if key in payload
    }
    return {
        "edge_id": edge.get("edge_id"),
        "source_node_id": edge.get("source_node_id"),
        "target_node_id": edge.get("target_node_id"),
        "edge_type": edge.get("edge_type"),
        "label": edge.get("label", ""),
        "payload": compact_payload,
        "n_refs": len(edge.get("refs") or []),
    }


def render_subgraph_view(
    snapshot: Any,
    *,
    graph_kind: GraphKind,
    offset: int = 0,
    node_ids: list[str] | None = None,
    status_filter: str | None = None,
) -> dict[str, Any]:
    """Compact paginated subgraph. Phase 4 起只剩 delivery 图：process 请求
    返回明确的弃用说明（旧库的行仍可读，但不再有新的 process 写入）。"""
    if graph_kind is GraphKind.PROCESS:
        return {
            "graph_kind": "process",
            "deprecated": True,
            "note": (
                "the process graph was removed (delivery-only orchestration); "
                "use graph_kind=delivery or the default projection"
            ),
            "nodes": [],
            "edges": [],
            "total_nodes": 0,
            "offset": 0,
        }
    graph = snapshot.delivery
    raw = graph.model_dump(mode="json")
    nodes = list(raw["nodes"])
    if node_ids:
        wanted = set(node_ids)
        nodes = [node for node in nodes if node["node_id"] in wanted]
    if status_filter:
        nodes = [
            node
            for node in nodes
            if (node.get("payload") or {}).get("status") == status_filter
        ]
    total_nodes = len(nodes)
    page = nodes[offset : offset + 50]
    allowed = {node["node_id"] for node in page}
    edges = [
        _compact_view_edge(edge)
        for edge in raw["edges"]
        if edge["source_node_id"] in allowed
        and edge["target_node_id"] in allowed
    ][:100]
    result: dict[str, Any] = {
        "graph_id": raw.get("graph_id"),
        "graph_kind": raw.get("graph_kind"),
        "revision": raw.get("revision"),
        "nodes": [_compact_view_node(node) for node in page],
        "edges": edges,
        "total_nodes": total_nodes,
        "offset": offset,
    }
    if node_ids or status_filter:
        result["filters"] = {
            **({"node_ids": node_ids} if node_ids else {}),
            **({"status": status_filter} if status_filter else {}),
        }
    return result


def resolve_delivery_target(
    snapshot: Any,
    kind: str,
    name: str,
) -> tuple[Any, str | None]:
    """在 delivery 图上按"精确 ID 优先、否则唯一名称"解析节点/边。

    ``kind`` ∈ {"node", "edge"}；``name`` 是用户输入（先 trim）。
    返回 ``(element, None)`` 命中、``(None, "not_found")`` 未命中、
    ``(None, "ambiguous")`` 名称命中多个元素（ID 唯一、名称可能因旧数据
    重复，故只在名称路径上歧义防护）。两个删除工具共用本规则。
    """
    name = name.strip()
    elements = snapshot.delivery.nodes if kind == "node" else snapshot.delivery.edges
    id_attr = "node_id" if kind == "node" else "edge_id"
    exact = next((item for item in elements if getattr(item, id_attr) == name), None)
    if exact is not None:
        return exact, None
    matches = [
        item
        for item in elements
        if getattr(item, "name", getattr(item, "label", "")).strip() == name
    ]
    if len(matches) > 1:
        return None, "ambiguous"
    if matches:
        return matches[0], None
    return None, "not_found"


class DagToolOutput(output_schema):
    is_success: bool
    action: str
    result: dict[str, Any] = Field(default_factory=dict)
    accepted: bool | None = None
    rejection_code: str | None = None
    error: str = ""


def mutation_output(action: str, mutation: MutationResult, extra: dict[str, Any] | None = None) -> DagToolOutput:
    result: dict[str, Any] = {
        "mutation_id": mutation.mutation_id,
        "revisions": mutation.revisions,
    }
    if extra:
        result.update(extra)
    return DagToolOutput(
        is_success=mutation.accepted,
        action=action,
        accepted=mutation.accepted,
        rejection_code=mutation.rejection_code,
        error=mutation.rejection_reason or "",
        result=result,
    )


def fail(action: str, error: str, *, accepted: bool | None = None) -> DagToolOutput:
    return DagToolOutput(
        is_success=False,
        action=action,
        accepted=accepted,
        error=error,
    )


def final_review_request_id(actor: Any) -> str | None:
    """Read the runtime-owned assignment, including the existing tool bridge."""
    return getattr(actor, "final_review_request_id", None) or getattr(
        getattr(actor, "_runtime_agent", None), "final_review_request_id", None
    )


def review_scope_allows(actor: Any, kind: str, request_id: str) -> bool:
    """Research agents can inspect all requests; each reviewer has one inbox."""
    if getattr(actor, "type", None) != "supervisor":
        return True
    assigned = final_review_request_id(actor)
    return kind != "exit" if assigned is None else kind == "exit" and request_id == assigned


@dataclass
class PreparedDag:
    db: ConversationDB
    store: DagStore
    engine: DagEngine
    actor: GraphActor
    mode: OrchestrationMode
    conversation_id: str
    contract: CoverageContract


def _prepare_db_and_store(conversation_id: str, session_id: str):
    # 工具调用路径上不做 init() 的 schema 写，版本落后才迁移；
    # 全新库 migrate_if_needed 不建表，仍需 init() 兜底。
    # 同步 sqlite 调用统一 offload 到 worker 线程，busy 等待不占事件循环
    db = ConversationDB(conversation_id)
    if not db.migrate_if_needed():
        db.init()
    store = DagStore(db)
    store.ensure_bundle(session_id)
    return db, store, store.load_coverage_contract()


def apply_mutation(
    store: DagStore,
    engine: DagEngine,
    *,
    session_id: str,
    actor: GraphActor,
    actor_id: str,
    operations: list[GraphOperation],
    rationale: str = "",
) -> MutationResult:
    """Pin current revisions and retry once on stale_revision (harness-owned)."""
    revisions = store.load_bundle().revisions
    result: MutationResult | None = None
    for _attempt in range(8):
        result = engine.apply_batch(
            MutationBatch(
                session_id=session_id,
                actor=actor,
                actor_id=actor_id,
                base_revisions=revisions,
                operations=operations,
                rationale=rationale,
            ),
        )
        if result.accepted or result.rejection_code != "stale_revision":
            return result
        revisions = store.load_bundle().revisions
    assert result is not None
    return result


class DagToolBase(Tool):
    """Mode gate, actor, mutation apply, and MANAGE permission flags."""

    def is_read(self) -> bool:
        return True

    def is_write(self) -> bool:
        # 权限类别为 MANAGE（编排管理类工具）；写安全由 DAG engine 按 actor 强制分图。
        return False

    def is_manage(self) -> bool:
        return True

    def _mode(self) -> OrchestrationMode:
        return normalize_orchestration_mode(
            getattr(self.subagent, "orchestration_mode", OrchestrationMode.STANDARD)
        )

    def _action_name(self) -> str:
        return self.tool_name

    def _standard_disabled(self) -> DagToolOutput:
        return fail(self._action_name(), "disabled in standard orchestration mode")

    def _actor(self) -> GraphActor:
        caller_type = getattr(self.subagent, "type", "")
        return (
            GraphActor.SUPERVISOR
            if caller_type == "supervisor"
            else GraphActor.AGENT
        )

    def _actor_id(self) -> str:
        # v2 bridge: ``name`` is role_id, ``id`` is the session uuid (as_*).
        # DAG assignee / actor_id vocabulary is legacy a-N (a-0 = Coordinator).
        # Prefer the role name so a-4 children can report on nodes assigned a-4.

        name = getattr(self.subagent, "name", "") or ""
        if name:
            return legacy_agent_id_for_role(name)
        raw = getattr(self.subagent, "id", "agent")
        return legacy_agent_id_for_role(raw) if raw else "agent"

    def _conversation_id(self) -> str:
        return getattr(self.subagent, "conversation_id", "default")

    async def _prepare(self, session: Session) -> PreparedDag:
        conversation_id = self._conversation_id()
        db, store, contract = await asyncio.to_thread(
            _prepare_db_and_store, conversation_id, session.id
        )
        return PreparedDag(
            db=db,
            store=store,
            engine=DagEngine(store),
            actor=self._actor(),
            mode=self._mode(),
            conversation_id=conversation_id,
            contract=contract,
        )

    async def _apply(
        self,
        session: Session,
        operations: list[GraphOperation],
        rationale: str = "",
        *,
        actor: GraphActor | None = None,
        actor_id: str | None = None,
        prepared: PreparedDag | None = None,
    ) -> tuple[PreparedDag, MutationResult]:
        ctx = prepared or await self._prepare(session)
        mutation = await asyncio.to_thread(
            apply_mutation,
            ctx.store,
            ctx.engine,
            session_id=session.id,
            actor=actor if actor is not None else ctx.actor,
            actor_id=actor_id if actor_id is not None else self._actor_id(),
            operations=operations,
            rationale=rationale,
        )
        return ctx, mutation
