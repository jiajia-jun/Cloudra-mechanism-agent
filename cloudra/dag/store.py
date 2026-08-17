"""Durable storage for the process and delivery DAG pair."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from cloudra.dag.models import (
    CallReview,
    CoverageContract,
    GraphBundle,
    GraphData,
    GraphKind,
    GraphRef,
    GraphSnapshot,
    MechanismDraft,
    SpeciesRecord,
    StageContract,
    StageState,
    map_legacy_stages,
    parse_dag_edge,
    parse_dag_node,
    parse_graph_operation,
)
from cloudra.persistence.database import ConversationDB, retry_on_locked


class EvidencePayloadError(ValueError):
    pass


class InvalidGraphReference(ValueError):
    pass


class SpeciesConflictError(ValueError):
    pass


class GraphBundleNotFound(LookupError):
    pass


class DagCorruptionError(RuntimeError):
    pass


def _canonical_json(value: Any, *, error_type: type[ValueError] = ValueError) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise error_type(f"value is not finite canonical JSON: {exc}") from exc


def _load_graph_bindings(
    con: sqlite3.Connection, graph_id: str
) -> dict[tuple[str, str], list[tuple[str, "str | None"]]]:
    """按插入序读关联表：``(target_type, target_id) -> [(evidence_id, content_hash|None)]``。

    content_hash 取自 dag_evidence 左连接；为 None 表示绑定指向证据库之外的
    目标（artifact/species/compute_job 引用），重建 GraphRef 时回退内联列。
    """
    rows = con.execute(
        """
        SELECT b.target_type, b.target_id, b.evidence_id, e.content_hash
        FROM dag_evidence_bindings b
        LEFT JOIN dag_evidence e ON e.evidence_id = b.evidence_id
        WHERE b.graph_id = ? ORDER BY b.rowid
        """,
        (graph_id,),
    ).fetchall()
    bindings: dict[tuple[str, str], list[tuple[str, str | None]]] = {}
    for target_type, target_id, evidence_id, content_hash in rows:
        bindings.setdefault((target_type, target_id), []).append(
            (evidence_id, content_hash)
        )
    return bindings


def _assemble_refs(
    inline_refs: list[dict[str, Any]],
    bindings: list[tuple[str, "str | None"]],
) -> list[dict[str, Any]]:
    """以关联表为准组装元素 refs；关联表无记录时回退内联 refs 列（未迁移兜底）。

    写路径上内联列与关联表同步维护，因此优先取内联条目的完整 GraphRef
    载荷（保留 ref_type/revision，覆盖 artifact/species/compute_job 引用）；
    仅当内联缺失时（例如内联列被旧版本写坏）用 dag_evidence 行重建
    tool_result 引用。两边都没有的悬挂绑定跳过。
    """
    if not bindings:
        return list(inline_refs)
    inline_by_id: dict[str, list[dict[str, Any]]] = {}
    for ref in inline_refs:
        if isinstance(ref, dict) and ref.get("ref_id"):
            inline_by_id.setdefault(str(ref["ref_id"]), []).append(ref)
    out: list[dict[str, Any]] = []
    for evidence_id, content_hash in bindings:
        queued = inline_by_id.get(evidence_id)
        if queued:
            out.append(queued.pop(0))
        elif content_hash is not None:
            out.append(
                {
                    "ref_type": "tool_result",
                    "ref_id": evidence_id,
                    "content_hash": content_hash,
                }
            )
    return out


def _read_element_stages(
    payload: dict[str, Any], column_json: Any, *, is_edge: bool
) -> list[dict[str, Any]]:
    """元素 stages 读取：stages 专列优先，空则回退 payload 内联，再空按
    存储的 evidence_level 做旧行一次性映射（models.map_legacy_stages）。"""
    stored = json.loads(column_json) if column_json else []
    if stored:
        return stored
    inline = payload.get("stages") if isinstance(payload, dict) else None
    if inline:
        return inline
    level = payload.get("evidence_level", "proposed") if isinstance(payload, dict) else "proposed"
    reason = payload.get("reason", "") if isinstance(payload, dict) else ""
    return [
        stage.model_dump(mode="json")
        for stage in map_legacy_stages(level, reason, is_edge=is_edge)
    ]


class DagStore:
    """Materialized DAG state plus immutable canonical evidence records."""

    _GRAPH_IDS = {
        GraphKind.PROCESS: "dag_process",
        GraphKind.DELIVERY: "dag_delivery",
    }

    def __init__(self, db: ConversationDB):
        self.db = db

    def ensure_bundle(self, session_id: str) -> GraphBundle:
        metadata = _canonical_json({"initialized_by_session": session_id})

        def operation() -> None:
            with self.db.connect() as con:
                for kind, graph_id in self._GRAPH_IDS.items():
                    con.execute(
                        """
                        INSERT OR IGNORE INTO dag_graphs(
                            graph_id, graph_kind, revision, metadata, created_at, updated_at
                        ) VALUES (?, ?, 0, ?, datetime('now'), datetime('now'))
                        """,
                        (graph_id, kind.value, metadata),
                    )
                con.execute(
                    """
                    INSERT OR IGNORE INTO dag_coverage(
                        graph_id, revision, coverage, updated_at
                    ) VALUES (?, 0, '{}', datetime('now'))
                    """,
                    (self._GRAPH_IDS[GraphKind.DELIVERY],),
                )

        retry_on_locked(operation)
        return self.load_bundle()

    def load_bundle(self) -> GraphBundle:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT graph_id, graph_kind, revision FROM dag_graphs"
            ).fetchall()
        by_kind = {row[1]: row for row in rows}
        required = {GraphKind.PROCESS.value, GraphKind.DELIVERY.value}
        if set(by_kind) != required:
            raise GraphBundleNotFound("the conversation does not have exactly two DAGs")
        return GraphBundle(
            process_graph_id=by_kind[GraphKind.PROCESS.value][0],
            delivery_graph_id=by_kind[GraphKind.DELIVERY.value][0],
            revisions={
                GraphKind.PROCESS.value: by_kind[GraphKind.PROCESS.value][2],
                GraphKind.DELIVERY.value: by_kind[GraphKind.DELIVERY.value][2],
            },
        )

    def load_snapshot(self) -> GraphSnapshot:
        bundle = self.load_bundle()
        return GraphSnapshot(
            bundle=bundle,
            process=self._load_graph(bundle.process_graph_id, GraphKind.PROCESS),
            delivery=self._load_graph(bundle.delivery_graph_id, GraphKind.DELIVERY),
        )

    def rebuild_materialized(self) -> GraphSnapshot:
        """Rebuild graph rows from the accepted journal or fail without mutation."""
        from cloudra.dag.engine import DagEngine

        return DagEngine(self).rebuild_materialized()

    def load_coverage_contract(self) -> CoverageContract:
        bundle = self.load_bundle()
        with self.db.connect() as con:
            row = con.execute(
                "SELECT coverage FROM dag_coverage WHERE graph_id = ?",
                (bundle.delivery_graph_id,),
            ).fetchone()
        if row is None or not row[0] or json.loads(row[0]) == {}:
            return CoverageContract.mechanism_default()
        return CoverageContract.model_validate_json(row[0])

    def record_delivery_disposition(
        self,
        session_id: str,
        disposition: str,
        report: Any,
    ) -> str:
        if disposition not in {"complete", "partial", "user_terminated"}:
            raise ValueError("invalid delivery disposition")
        bundle = self.load_bundle()
        encoded = _canonical_json(
            report.model_dump(mode="json") if hasattr(report, "model_dump") else report
        )
        disposition_id = "disp_" + uuid.uuid4().hex

        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    """
                    INSERT INTO dag_delivery_dispositions(
                        disposition_id, session_id, disposition, graph_revision,
                        report, created_at
                    ) VALUES (?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        disposition_id,
                        session_id,
                        disposition,
                        bundle.revisions["delivery"],
                        encoded,
                    ),
                )

        retry_on_locked(operation)
        return disposition_id

    def _load_graph(self, graph_id: str, kind: GraphKind) -> GraphData:
        with self.db.connect() as con:
            graph = con.execute(
                "SELECT revision, metadata FROM dag_graphs WHERE graph_id = ? AND graph_kind = ?",
                (graph_id, kind.value),
            ).fetchone()
            if graph is None:
                raise GraphBundleNotFound(f"missing {kind.value} DAG")
            node_rows = con.execute(
                """
                SELECT node_id, node_type, label, refs, payload, stages
                FROM dag_nodes WHERE graph_id = ? ORDER BY node_id
                """,
                (graph_id,),
            ).fetchall()
            edge_rows = con.execute(
                """
                SELECT edge_id, source_node_id, target_node_id, edge_type, label, refs, payload, stages
                FROM dag_edges WHERE graph_id = ? ORDER BY edge_id
                """,
                (graph_id,),
            ).fetchall()
            bindings = _load_graph_bindings(con, graph_id)
        nodes = []
        for row in node_rows:
            payload = json.loads(row[4])
            data = {
                "node_id": row[0],
                "node_type": row[1],
                "label": row[2],
                "refs": _assemble_refs(
                    json.loads(row[3]), bindings.get(("node", row[0]), [])
                ),
                **payload,
            }
            if kind is GraphKind.DELIVERY:
                data["stages"] = _read_element_stages(payload, row[5], is_edge=False)
            nodes.append(parse_dag_node(data))
        edges = []
        for row in edge_rows:
            payload = json.loads(row[6])
            data = {
                "edge_id": row[0],
                "source_node_id": row[1],
                "target_node_id": row[2],
                "edge_type": row[3],
                "label": row[4],
                "refs": _assemble_refs(
                    json.loads(row[5]), bindings.get(("edge", row[0]), [])
                ),
                **payload,
            }
            if kind is GraphKind.DELIVERY:
                data["stages"] = _read_element_stages(payload, row[7], is_edge=True)
            edges.append(parse_dag_edge(data))
        return GraphData(
            graph_id=graph_id,
            graph_kind=kind,
            revision=graph[0],
            metadata=json.loads(graph[1]),
            nodes=nodes,
            edges=edges,
        )

    def register_evidence(
        self,
        session_id: str,
        source_name: str,
        payload: Any,
        *,
        source_type: str = "tool_result",
    ) -> GraphRef:
        if source_type != "tool_result":
            raise InvalidGraphReference(
                "only durable tool_result evidence can be registered here"
            )
        encoded = _canonical_json(payload, error_type=EvidencePayloadError)
        content_hash = "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        identity = _canonical_json(
            {
                "source_type": source_type,
                "source_name": source_name,
                "content_hash": content_hash,
            }
        )
        evidence_id = "ev_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()

        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    """
                    INSERT OR IGNORE INTO dag_evidence(
                        evidence_id, session_id, source_type, source_name,
                        content_hash, payload, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        evidence_id,
                        session_id,
                        source_type,
                        source_name,
                        content_hash,
                        encoded,
                    ),
                )

        retry_on_locked(operation)
        return GraphRef(
            ref_type="tool_result",
            ref_id=evidence_id,
            content_hash=content_hash,
        )

    def resolve_evidence(self, ref: GraphRef) -> Any:
        if ref.ref_type != "tool_result":
            raise InvalidGraphReference("reference does not point to tool-result evidence")
        with self.db.connect() as con:
            row = con.execute(
                "SELECT content_hash, payload FROM dag_evidence WHERE evidence_id = ?",
                (ref.ref_id,),
            ).fetchone()
        if row is None or (ref.content_hash is not None and ref.content_hash != row[0]):
            raise InvalidGraphReference("evidence reference is missing or has the wrong hash")
        return json.loads(row[1])

    def resolve_evidence_with_source(self, ref: GraphRef) -> tuple[str, Any]:
        """返回 (source_name, payload)；缺失或哈希不符抛 InvalidGraphReference。

        事后认领通道用：模型把已登记的证据补挂到 delivery 元素时，需要
        知道产生它的工具名才能重跑确定性派生。
        """
        if ref.ref_type != "tool_result":
            raise InvalidGraphReference("reference does not point to tool-result evidence")
        with self.db.connect() as con:
            row = con.execute(
                "SELECT content_hash, source_name, payload FROM dag_evidence "
                "WHERE evidence_id = ?",
                (ref.ref_id,),
            ).fetchone()
        if row is None or (ref.content_hash is not None and ref.content_hash != row[0]):
            raise InvalidGraphReference("evidence reference is missing or has the wrong hash")
        return row[1], json.loads(row[2])

    def resolve_evidence_for_call(self, tool_call_id: str) -> GraphRef | None:
        """按 tool_call_id 反查已登记的 tool_result 证据（payload 内嵌）；无则 None。

        process 遥测节点删除后（D12），tool_call_id → 证据的解析走证据库
        本身，不再经过图上的 observed 节点。
        """
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT evidence_id, content_hash, payload FROM dag_evidence"
            ).fetchall()
        for evidence_id, content_hash, payload in rows:
            try:
                data = json.loads(payload)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("tool_call_id") == tool_call_id:
                return GraphRef(
                    ref_type="tool_result",
                    ref_id=evidence_id,
                    content_hash=content_hash,
                )
        return None

    # --- CallReview 收件箱（D12：append-only，不经 DagEngine 版本化 mutation） ---

    def enqueue_call_review(self, review: CallReview) -> None:
        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    """
                    INSERT OR IGNORE INTO dag_call_reviews(
                        review_id, tool_call_id, tool_name, is_success,
                        caller_session_id, caller_role_id, caller_legacy_id,
                        arguments_digest, result_summary, compute_job_id,
                        suggested_target_id, state, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review.review_id,
                        review.tool_call_id,
                        review.tool_name,
                        int(review.is_success),
                        review.caller_session_id,
                        review.caller_role_id,
                        review.caller_legacy_id,
                        review.arguments_digest,
                        review.result_summary,
                        review.compute_job_id,
                        review.suggested_target_id,
                        review.state,
                        review.created_at,
                    ),
                )

        retry_on_locked(operation)

    @staticmethod
    def _review_from_row(row) -> CallReview:
        return CallReview(
            review_id=row[0],
            tool_call_id=row[1],
            tool_name=row[2],
            is_success=bool(row[3]),
            caller_session_id=row[4],
            caller_role_id=row[5],
            caller_legacy_id=row[6],
            arguments_digest=row[7],
            result_summary=row[8],
            compute_job_id=row[9],
            suggested_target_id=row[10],
            state=row[11],
            created_at=row[12],
        )

    _REVIEW_COLUMNS = (
        "review_id, tool_call_id, tool_name, is_success, caller_session_id, "
        "caller_role_id, caller_legacy_id, arguments_digest, result_summary, "
        "compute_job_id, suggested_target_id, state, created_at"
    )

    def list_call_reviews(self, state: str | None = "pending") -> list[CallReview]:
        query = f"SELECT {self._REVIEW_COLUMNS} FROM dag_call_reviews"
        params: tuple = ()
        if state is not None:
            query += " WHERE state = ?"
            params = (state,)
        query += " ORDER BY created_at, rowid"
        with self.db.connect() as con:
            rows = con.execute(query, params).fetchall()
        return [self._review_from_row(row) for row in rows]

    def get_call_review(self, review_id: str) -> CallReview | None:
        with self.db.connect() as con:
            row = con.execute(
                f"SELECT {self._REVIEW_COLUMNS} FROM dag_call_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        return self._review_from_row(row) if row else None

    def mark_call_review(self, review_id: str, state: str) -> None:
        if state not in ("pending", "reviewed", "ignored"):
            raise ValueError(f"invalid review state {state!r}")

        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    "UPDATE dag_call_reviews SET state = ? WHERE review_id = ?",
                    (state, review_id),
                )

        retry_on_locked(operation)

    # --- 机理草稿（D1/D4）：mechanism_accepted = EXISTS(state='accepted') ---

    def save_draft(self, draft: MechanismDraft, *, actor_id: str) -> str:
        draft_id = "draft_" + uuid.uuid4().hex
        operations = _canonical_json([
            op.model_dump(mode="json", exclude={"node": {"payload"}, "edge": {"payload"}})
            for op in draft.operations
        ])
        contracts = _canonical_json(
            {key: contract.model_dump(mode="json")
             for key, contract in draft.stage_contracts.items()}
        )

        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    """
                    INSERT INTO dag_drafts(
                        draft_id, state, rationale, operations, stage_contracts,
                        actor_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        draft_id,
                        draft.state,
                        draft.rationale,
                        operations,
                        contracts,
                        actor_id,
                    ),
                )

        retry_on_locked(operation)
        return draft_id

    @staticmethod
    def _draft_from_row(row) -> MechanismDraft:
        return MechanismDraft(
            operations=[parse_graph_operation(op) for op in json.loads(row[0])],
            stage_contracts={
                key: StageContract(
                    stages=[StageState.model_validate(s) for s in value.get("stages", [])]
                )
                for key, value in json.loads(row[1]).items()
            },
            rationale=row[2],
            state=row[3],
        )

    def get_draft(self, draft_id: str) -> MechanismDraft | None:
        with self.db.connect() as con:
            row = con.execute(
                "SELECT operations, stage_contracts, rationale, state "
                "FROM dag_drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
        return self._draft_from_row(row) if row else None

    def latest_open_draft(self) -> tuple[str, MechanismDraft] | None:
        with self.db.connect() as con:
            row = con.execute(
                "SELECT draft_id, operations, stage_contracts, rationale, state "
                "FROM dag_drafts WHERE state = 'open' ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return row[0], self._draft_from_row(row[1:])

    def set_draft_state(
        self, draft_id: str, state: str, *, reject_reason: str = ""
    ) -> None:
        if state not in ("accepted", "rejected"):
            raise ValueError(f"invalid draft state {state!r}")

        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    "UPDATE dag_drafts SET state = ?, reject_reason = ?, "
                    "decided_at = datetime('now') WHERE draft_id = ?",
                    (state, reject_reason, draft_id),
                )

        retry_on_locked(operation)

    def has_accepted_draft(self) -> bool:
        """D4：mechanism_accepted 的唯一判据。"""
        with self.db.connect() as con:
            row = con.execute(
                "SELECT 1 FROM dag_drafts WHERE state = 'accepted' LIMIT 1"
            ).fetchone()
        return row is not None

    def latest_draft(self) -> dict[str, Any] | None:
        """最新草稿（open 优先，其次最近裁决）+ 元信息，供 /dag/draft 投影。"""
        with self.db.connect() as con:
            row = con.execute(
                """
                SELECT draft_id, state, rationale, operations, stage_contracts,
                       actor_id, reject_reason, created_at
                FROM dag_drafts
                ORDER BY (state = 'open') DESC, rowid DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return {
            "draft_id": row[0],
            "state": row[1],
            "rationale": row[2],
            "operations": json.loads(row[3]),
            "stage_contracts": json.loads(row[4]),
            "actor_id": row[5],
            "reject_reason": row[6],
            "created_at": row[7],
        }

    def upsert_species(
        self,
        *,
        canonical_key: str,
        identifiers: dict[str, str],
        charge: int,
        multiplicity: int,
        metadata: dict | None = None,
    ) -> SpeciesRecord:
        if not canonical_key:
            raise ValueError("canonical_key cannot be empty")
        metadata = metadata or {}
        identifiers_json = _canonical_json(identifiers)
        metadata_json = _canonical_json(metadata)
        species_id = "sp_" + hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()
        record = SpeciesRecord(
            species_id=species_id,
            canonical_key=canonical_key,
            identifiers=identifiers,
            charge=charge,
            multiplicity=multiplicity,
            metadata=metadata,
        )

        def operation() -> None:
            with self.db.connect() as con:
                existing = con.execute(
                    """
                    SELECT species_id, charge, multiplicity, identifiers, metadata
                    FROM dag_species WHERE canonical_key = ?
                    """,
                    (canonical_key,),
                ).fetchone()
                if existing is not None:
                    expected = (
                        species_id,
                        charge,
                        multiplicity,
                        identifiers_json,
                        metadata_json,
                    )
                    if existing != expected:
                        raise SpeciesConflictError(
                            "canonical species records are immutable once created"
                        )
                    return
                try:
                    con.execute(
                        """
                        INSERT INTO dag_species(
                            species_id, canonical_key, charge, multiplicity,
                            identifiers, metadata, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (
                            species_id,
                            canonical_key,
                            charge,
                            multiplicity,
                            identifiers_json,
                            metadata_json,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise SpeciesConflictError(str(exc)) from exc

        retry_on_locked(operation)
        return record

    def get_species(self, species_id: str) -> SpeciesRecord:
        with self.db.connect() as con:
            row = con.execute(
                """
                SELECT species_id, canonical_key, charge, multiplicity, identifiers, metadata
                FROM dag_species WHERE species_id = ?
                """,
                (species_id,),
            ).fetchone()
        if row is None:
            raise InvalidGraphReference("species record does not exist")
        return SpeciesRecord(
            species_id=row[0],
            canonical_key=row[1],
            charge=row[2],
            multiplicity=row[3],
            identifiers=json.loads(row[4]),
            metadata=json.loads(row[5]),
        )
