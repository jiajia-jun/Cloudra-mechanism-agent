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

    @staticmethod
    def _delivery_state_fingerprint(con) -> str:
        """Read audit inputs on one SQLite transaction, preserving latest-row order."""
        state = {}
        for table in ('dag_graphs', 'dag_nodes', 'dag_edges', 'dag_coverage'):
            state[table] = [tuple(row) for row in con.execute(
                f'SELECT rowid, * FROM {table} WHERE graph_id = ? ORDER BY rowid',
                ('dag_delivery',)).fetchall()]
        for table in ('dag_evidence_bindings', 'dag_evidence', 'dag_evidence_facts',
                      'dag_drafts', 'dag_review_requests', 'dag_review_decisions', 'dag_call_reviews'):
            state[table] = [tuple(row) for row in con.execute(
                f'SELECT rowid, * FROM {table} ORDER BY rowid').fetchall()]
        state['call_verdicts'] = [tuple(row) for row in con.execute(
            "SELECT rowid, decision_id, payload FROM dag_review_notifications "
            "WHERE kind = 'call_verdict' ORDER BY rowid").fetchall()]
        return hashlib.sha256(_canonical_json(state).encode()).hexdigest()

    def delivery_state_fingerprint(self) -> str:
        with self.db.connect() as con:
            con.execute('BEGIN')
            return self._delivery_state_fingerprint(con)

    def record_delivery_disposition(
        self,
        session_id: str,
        disposition: str,
        report: Any,
        *,
        expected_state: str | None = None,
    ) -> str:
        if disposition not in {"complete", "partial", "user_terminated"}:
            raise ValueError("invalid delivery disposition")
        encoded = _canonical_json(
            report.model_dump(mode="json") if hasattr(report, "model_dump") else report
        )
        disposition_id = "disp_" + uuid.uuid4().hex

        def operation() -> None:
            with self.db.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                if expected_state is not None and self._delivery_state_fingerprint(con) != expected_state:
                    raise RuntimeError('DAG evidence or review state changed after audit; re-audit the delivery.')
                revision = con.execute(
                    "SELECT revision FROM dag_graphs WHERE graph_kind = 'delivery'").fetchone()[0]
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
                        revision,
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
                "name": row[2],
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
                "name": row[4],
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
        if source_type not in ("tool_result", "file"):
            raise InvalidGraphReference(
                "only durable tool_result or file evidence can be registered here"
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
                keys = ConversationDB.evidence_source_keys(encoded) or ("", "")
                con.execute(
                    """
                    INSERT OR IGNORE INTO dag_evidence(
                        evidence_id, session_id, source_type, source_name,
                        content_hash, payload, created_at,
                        tool_call_id, compute_job_id
                    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
                    """,
                    (
                        evidence_id,
                        session_id,
                        source_type,
                        source_name,
                        content_hash,
                        encoded,
                        keys[0],
                        keys[1],
                    ),
                )

        retry_on_locked(operation)
        return GraphRef(
            ref_type="file" if source_type == "file" else "tool_result",
            ref_id=evidence_id,
            content_hash=content_hash,
        )

    def resolve_evidence(self, ref: GraphRef) -> Any:
        if ref.ref_type not in ("tool_result", "file"):
            raise InvalidGraphReference("reference does not point to tool-result or file evidence")
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
        本身，不再经过图上的 observed 节点。索引列命中优先；NULL 行是
        迁移前不可解析/未回填的 legacy 行，回退 payload 扫描。
        """
        with self.db.connect() as con:
            row = con.execute(
                "SELECT evidence_id, content_hash FROM dag_evidence "
                "WHERE tool_call_id = ?",
                (tool_call_id,),
            ).fetchone()
            if row is not None:
                return GraphRef(
                    ref_type="tool_result",
                    ref_id=row[0],
                    content_hash=row[1],
                )
            rows = con.execute(
                "SELECT evidence_id, content_hash, payload FROM dag_evidence "
                "WHERE tool_call_id IS NULL"
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

    # --- 类型化证据事实（contract_version=2；dag_evidence_facts 不可变） ---

    def record_facts(self, facts: list) -> list[str]:
        """登记 EvidenceFact 列表，按 dedup_key 幂等；返回 fact_id 列表
        （与输入同序；重复解析命中既有行时返回原 fact_id）。

        dedup_key 覆盖来源引用（含 content_hash）、实际尝试内容与解析版本：
        同一文件的重复解析去重，一次真实重算（新来源或新 hash）绝不合并。
        """
        from cloudra.dag.evidence_facts import fact_dedup_key

        ids: list[str] = []

        def operation() -> None:
            with self.db.connect() as con:
                for fact in facts:
                    key = fact_dedup_key(fact)
                    con.execute(
                        """
                        INSERT OR IGNORE INTO dag_evidence_facts(
                            fact_id, check_name, outcome, subject, source_refs,
                            details, adapter_version, dedup_key, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (
                            fact.fact_id,
                            fact.check,
                            fact.outcome,
                            _canonical_json(fact.subject.model_dump()),
                            _canonical_json(
                                [ref.model_dump() for ref in fact.source_refs]
                            ),
                            _canonical_json(fact.details),
                            fact.adapter_version,
                            key,
                        ),
                    )
                    row = con.execute(
                        "SELECT fact_id FROM dag_evidence_facts WHERE dedup_key = ?",
                        (key,),
                    ).fetchone()
                    ids.append(row[0])

        if facts:
            retry_on_locked(operation)
        return ids

    def facts_for_target(self, target_id: str) -> list:
        """目标可归属的事实：经 bindings 表绑定到该 target 的证据来源，
        或 subject.target_hint 直接指向该 target。"""
        from cloudra.dag.evidence_facts import EvidenceFact

        with self.db.connect() as con:
            rows = con.execute(
                "SELECT fact_id, check_name, outcome, subject, source_refs, "
                "details, adapter_version FROM dag_evidence_facts"
            ).fetchall()
            bound_evidence = {
                row[0]
                for row in con.execute(
                    "SELECT DISTINCT evidence_id FROM dag_evidence_bindings "
                    "WHERE target_id = ?",
                    (target_id,),
                ).fetchall()
            }
        facts: list = []
        for fact_id, check, outcome, subject, source_refs, details, adapter_version in rows:
            subject_data = json.loads(subject)
            refs = [GraphRef(**item) for item in json.loads(source_refs)]
            if subject_data.get("target_hint") != target_id and not (
                bound_evidence & {ref.ref_id for ref in refs}
            ):
                continue
            facts.append(
                EvidenceFact(
                    fact_id=fact_id,
                    check=check,
                    outcome=outcome,
                    subject=subject_data,
                    source_refs=refs,
                    details=json.loads(details),
                    adapter_version=adapter_version,
                )
            )
        return facts

    # --- 结构化审查请求/裁决（contract_version=2） ---

    def enqueue_review(self, request) -> str:
        """持久化一个 ReviewRequest；同 kind+scope+basis 仍 queued 时去重合并。

        New contradictions/evidence produce a new basis_fingerprint, so they
        enqueue a new request even if the question text is identical.
        """
        request_id, _created = self.enqueue_review_with_status(request)
        return request_id

    def enqueue_review_with_status(self, request) -> tuple[str, bool]:
        """enqueue_review 的等价入口，额外返回是否真正新建（dedup 命中为
        False）。退出审批流程据此只在新建时通知 Supervisor——同一交付版本
        反复退出不得重复叫醒督导（计划 §6 wait_review 复用契约）。"""
        from cloudra.dag.review_requests import ReviewRequest, scope_key

        if not isinstance(request, ReviewRequest):
            request = ReviewRequest.model_validate(request)
        if not request.request_id:
            request = request.model_copy(
                update={"request_id": "req_" + uuid.uuid4().hex}
            )
        kind, targets = scope_key(request)
        request_json = request.model_dump(mode="json")
        del request_json["request_id"]
        request_json.pop("state", None)
        request_json.pop("created_at", None)
        request_json.pop("updated_at", None)
        def operation() -> tuple[str, bool]:
            with self.db.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                # All evidence refs are project-local: they must resolve in this
                # conversation's evidence store. Cross-project ids are rejected.
                for ref in [*request.supporting_refs, *request.counterevidence_refs]:
                    if ref.ref_type != "tool_result":
                        continue
                    evidence_row = con.execute(
                        "SELECT content_hash FROM dag_evidence WHERE evidence_id = ?",
                        (ref.ref_id,),
                    ).fetchone()
                    if evidence_row is None or (
                        ref.content_hash is not None
                        and ref.content_hash != evidence_row[0]
                    ):
                        raise InvalidGraphReference(
                            f"evidence reference {ref.ref_id!r} does not resolve "
                            "in this conversation's evidence store"
                        )
                if kind == 'exit':
                    rows = con.execute('''SELECT request_id, basis_fingerprint, state, target_ids, proposal
                        FROM dag_review_requests WHERE kind='exit' AND requester=? ORDER BY rowid DESC''',
                        (request.requester,)).fetchall()
                    previous = [row for row in rows if tuple(sorted(json.loads(row[3]))) == targets
                        and json.loads(row[4]).get('disposition') == request.proposal.get('disposition')]
                    if previous and previous[0][2] != 'superseded' and previous[0][1] == request.basis_fingerprint:
                        return previous[0][0], False
                    # New exit material replaces earlier submissions. Keep their
                    # verdicts for audit, but never revive a superseded approval.
                    con.executemany("UPDATE dag_review_requests SET state='superseded', updated_at=datetime('now') WHERE request_id=?",
                        [(row[0],) for row in previous if row[2] != 'superseded'])
                else:
                    row = con.execute(
                        """
                        SELECT request_id FROM dag_review_requests
                        WHERE kind = ? AND target_ids = ? AND basis_fingerprint = ?
                          AND state != 'superseded' ORDER BY rowid LIMIT 1
                        """,
                        (kind, _canonical_json(list(targets)), request.basis_fingerprint),
                    ).fetchone()
                    if row is not None:
                        return row[0], False
                con.execute(
                    """
                    INSERT INTO dag_review_requests(
                        request_id, kind, requester, target_ids, question,
                        supporting_refs, counterevidence_refs, proposal,
                        basis_fingerprint, state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', datetime('now'), datetime('now'))
                    """,
                    (
                        request.request_id,
                        request.kind,
                        request.requester,
                        _canonical_json(request.target_ids),
                        request.question,
                        _canonical_json(
                            [ref.model_dump(mode="json") for ref in request.supporting_refs]
                        ),
                        _canonical_json(
                            [ref.model_dump(mode="json") for ref in request.counterevidence_refs]
                        ),
                        _canonical_json(request.proposal),
                        request.basis_fingerprint,
                    ),
                )
                return request.request_id, True

        return retry_on_locked(operation)

    @staticmethod
    def _review_request_from_row(row) -> Any:
        from cloudra.dag.review_requests import ReviewRequest

        return ReviewRequest(
            request_id=row[0],
            kind=row[1],
            requester=row[2],
            target_ids=json.loads(row[3]),
            question=row[4],
            supporting_refs=[GraphRef(**item) for item in json.loads(row[5])],
            counterevidence_refs=[GraphRef(**item) for item in json.loads(row[6])],
            proposal=json.loads(row[7]),
            basis_fingerprint=row[8],
            state=row[9],
            created_at=row[10],
            updated_at=row[11],
        )

    _REVIEW_REQUEST_COLUMNS = (
        "request_id, kind, requester, target_ids, question, supporting_refs, "
        "counterevidence_refs, proposal, basis_fingerprint, state, created_at, updated_at"
    )

    def get_review_request(self, request_id: str):
        with self.db.connect() as con:
            row = con.execute(
                f"SELECT {self._REVIEW_REQUEST_COLUMNS} FROM dag_review_requests "
                "WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return self._review_request_from_row(row)

    def get_review_decision(self, decision_id: str):
        """Load one durable decision for stop-gate validation."""
        from cloudra.dag.review_requests import ReviewDecision

        with self.db.connect() as con:
            row = con.execute(
                "SELECT decision_id, request_id, basis_fingerprint, verdict, reason, "
                "evidence_refs, findings, next_action FROM dag_review_decisions "
                "WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        if row is None:
            return None
        return ReviewDecision(
            decision_id=row[0], request_id=row[1], basis_fingerprint=row[2],
            verdict=row[3], reason=row[4],
            evidence_refs=[GraphRef(**item) for item in json.loads(row[5])],
            findings=json.loads(row[6]), next_action=row[7],
        )

    def get_review_decision_for_request(self, request_id: str):
        """Load the durable decision for a request, if it has been resolved."""
        with self.db.connect() as con:
            row = con.execute(
                "SELECT decision_id FROM dag_review_decisions "
                "WHERE request_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (request_id,),
            ).fetchone()
        return self.get_review_decision(row[0]) if row is not None else None

    def review_basis(self, request) -> str:
        """Fingerprint the current scoped evidence, graph and contract.

        A decision is valid only for the same target snapshot and contract;
        unrelated project changes therefore do not invalidate it.
        """
        snapshot = self.load_snapshot()
        contract = self.load_coverage_contract()
        accepted_claim = self.accepted_claim_spec()
        target_ids = set(request.target_ids)
        delivery = snapshot.delivery.model_dump(mode="json")
        scoped = [
            item for item in [*delivery.get("nodes", []), *delivery.get("edges", [])]
            if item.get("node_id", item.get("edge_id")) in target_ids
        ]
        from cloudra.dag.review_context import review_target_identity

        payload = {
            "kind": request.kind,
            "targets": sorted(target_ids),
            "target_identities": [
                review_target_identity(
                    snapshot.delivery, "species" if "node_id" in item else "step",
                    item.get("node_id", item.get("edge_id")),
                )
                for item in scoped
            ],
            "question": request.question,
            "proposal": request.proposal,
            "supporting_refs": [ref.model_dump(mode="json") for ref in request.supporting_refs],
            "counterevidence_refs": [ref.model_dump(mode="json") for ref in request.counterevidence_refs],
            "delivery": scoped,
            "contract": contract.model_dump(mode="json"),
            "accepted_claim_spec": (
                accepted_claim.model_dump(mode="json") if accepted_claim is not None else None
            ),
            "exceptions": [item for item in self.collect_review_exceptions(sorted(target_ids))
                           if item.get('target_id') in target_ids] if target_ids else [],
        }
        if request.kind == 'exit':
            artifact = request.proposal.get('delivery_artifact')
            if isinstance(artifact, dict) and isinstance(artifact.get('path'), str):
                from cloudra.dag.delivery_artifact import current_artifact_digest
                payload['current_delivery_artifact_sha256'] = current_artifact_digest(artifact['path'])
        encoded = _canonical_json(payload)
        return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def list_review_requests(self, state: str = "queued"):
        query = (
            f"SELECT {self._REVIEW_REQUEST_COLUMNS} FROM dag_review_requests"
        )
        params: tuple = ()
        if state is not None:
            query += " WHERE state = ?"
            params = (state,)
        query += " ORDER BY created_at, rowid"
        with self.db.connect() as con:
            rows = con.execute(query, params).fetchall()
        return [self._review_request_from_row(row) for row in rows]

    def pending_review_notifications(self) -> list[dict[str, Any]]:
        """Pending verdict notifications (notification_id idempotent).

        三类裁决共用：``kind`` ∈ review_decision / call_verdict /
        draft_verdict；``decision_id`` 是各类的主体 id（decision_id /
        review_id / draft_id），``payload`` 是后两类的渲染材料 JSON
        （review_decision 的渲染材料在 dag_review_decisions 查得）。
        """
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT notification_id, kind, decision_id, request_id, "
                "recipient_session_id, payload, state, created_at "
                "FROM dag_review_notifications WHERE state = 'pending' "
                "ORDER BY created_at, rowid"
            ).fetchall()
        return [
            {
                "notification_id": row[0],
                "kind": row[1],
                "decision_id": row[2],
                "request_id": row[3],
                "recipient_session_id": row[4],
                "payload": row[5],
                "state": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]

    @staticmethod
    def _insert_notification(
        con,
        *,
        kind: str,
        subject_id: str,
        recipient_session_id: str,
        payload: dict[str, Any],
    ) -> None:
        """在同一事务内落一条 pending 裁决通知（调用方持有连接/事务）。

        必须与裁决状态变更同事务（mark_call_review / set_draft_state），
        否则崩溃窗口会出现"裁决已落、通知行丢失"——恢复路径只补投通知行，
        不重推裁决。
        """
        con.execute(
            "INSERT INTO dag_review_notifications("
            "notification_id, kind, decision_id, request_id, "
            "recipient_session_id, payload, state, created_at"
            ") VALUES (?, ?, ?, '', ?, ?, 'pending', datetime('now'))",
            (
                "notif_" + uuid.uuid4().hex,
                kind,
                subject_id,
                recipient_session_id,
                _canonical_json(payload),
            ),
        )

    def mark_review_notification_sent(self, decision_id: str) -> None:
        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    "UPDATE dag_review_notifications SET state='sent' "
                    "WHERE decision_id = ?",
                    (decision_id,),
                )

        retry_on_locked(operation)

    def resolve_review(
        self,
        decision,
        *,
        expected_basis: str,
        current_basis: str | None = None,
    ) -> dict[str, Any]:
        """Atomic resolve of a ReviewDecision.

        The request's stored basis must equal ``expected_basis``; a stale basis
        means the decision cannot be applied (superseded request).  Consumer
        uniqueness comes from the runtime: the project's single Supervisor
        agent resolves queued requests through the serialized
        InvocationService path, and the duplicate_decision guard rejects a
        second resolve of the same request+basis (idempotency).
        """
        from cloudra.dag.review_requests import ReviewDecision

        if not isinstance(decision, ReviewDecision):
            decision = ReviewDecision.model_validate(decision)
        if not decision.decision_id:
            decision = decision.model_copy(
                update={"decision_id": "dec_" + uuid.uuid4().hex}
            )

        def operation() -> dict[str, Any]:
            with self.db.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                row = con.execute(
                    f"SELECT {self._REVIEW_REQUEST_COLUMNS} FROM dag_review_requests "
                    "WHERE request_id = ?",
                    (decision.request_id,),
                ).fetchone()
                if row is None:
                    return {
                        "accepted": False,
                        "rejection_code": "missing_request",
                        "rejection_reason": f"review request {decision.request_id!r} does not exist",
                        "request_id": decision.request_id,
                    }
                request = self._review_request_from_row(row)
                if request.state == 'superseded':
                    return {'accepted': False, 'rejection_code': 'stale_basis',
                            'rejection_reason': 'This request was replaced; review the current submission.',
                            'request_id': request.request_id, 'request_state': request.state}
                if request.basis_fingerprint != expected_basis:
                    return {
                        "accepted": False,
                        "rejection_code": "stale_basis",
                        "rejection_reason": (
                            "the decision basis no longer matches the request; "
                            "a related target/evidence changed after the request was created"
                        ),
                        "request_id": decision.request_id,
                    }
                if current_basis is not None and request.basis_fingerprint != current_basis:
                    return {
                        "accepted": False,
                        "rejection_code": "stale_basis",
                        "rejection_reason": "the scoped graph, contract, or evidence changed",
                        "request_id": decision.request_id,
                    }
                if decision.basis_fingerprint != request.basis_fingerprint:
                    return {
                        "accepted": False,
                        "rejection_code": "stale_basis",
                        "rejection_reason": "decision basis does not match the request basis",
                        "request_id": decision.request_id,
                    }
                for ref in decision.evidence_refs:
                    if ref.ref_type != "tool_result":
                        continue
                    evidence_row = con.execute(
                        "SELECT content_hash FROM dag_evidence WHERE evidence_id = ?",
                        (ref.ref_id,),
                    ).fetchone()
                    if evidence_row is None or (
                        ref.content_hash is not None
                        and ref.content_hash != evidence_row[0]
                    ):
                        return {
                            "accepted": False,
                            "rejection_code": "invalid_evidence_ref",
                            "rejection_reason": (
                                f"decision evidence reference {ref.ref_id!r} does not "
                                "resolve in this conversation"
                            ),
                            "request_id": decision.request_id,
                        }
                existing = con.execute(
                    "SELECT 1 FROM dag_review_decisions WHERE request_id = ? "
                    "AND basis_fingerprint = ? LIMIT 1",
                    (decision.request_id, decision.basis_fingerprint),
                ).fetchone()
                if existing is not None:
                    return {
                        "accepted": False,
                        "rejection_code": "duplicate_decision",
                        "rejection_reason": (
                            "a decision for this request+basis already exists; "
                            "do not resolve the same basis twice"
                        ),
                        "request_id": decision.request_id,
                    }
                con.execute(
                    """
                    INSERT INTO dag_review_decisions(
                        decision_id, request_id, basis_fingerprint, verdict,
                        reason, evidence_refs, findings, next_action, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        decision.decision_id,
                        decision.request_id,
                        decision.basis_fingerprint,
                        decision.verdict,
                        decision.reason,
                        _canonical_json(
                            [ref.model_dump(mode="json") for ref in decision.evidence_refs]
                        ),
                        _canonical_json(decision.findings),
                        decision.next_action,
                    ),
                )
                con.execute(
                    "UPDATE dag_review_requests SET state='resolved', updated_at=datetime('now') "
                    "WHERE request_id = ?",
                    (decision.request_id,),
                )
                con.execute(
                    "INSERT INTO dag_review_notifications("
                    "notification_id, decision_id, request_id, recipient_session_id, "
                    "state, created_at) VALUES (?, ?, ?, ?, 'pending', datetime('now'))",
                    (
                        "notif_" + uuid.uuid4().hex,
                        decision.decision_id,
                        decision.request_id,
                        request.requester,
                    ),
                )
                return {
                    "accepted": True,
                    "decision_id": decision.decision_id,
                    "request_id": decision.request_id,
                    "basis_fingerprint": decision.basis_fingerprint,
                }

        return retry_on_locked(operation)

    def collect_review_exceptions(self, target_ids: list[str]) -> list[dict[str, Any]]:
        """Return stable exceptions relevant to the given delivery targets.

        Categories:
        - ``coverage_gap``: required stage/check evidence is still missing.
        - ``contradiction``: a registered refutes fact targets this target.
        - ``known_target_unbound_fact``: a target-hinted fact is not yet bound.
        - ``untargeted_key_fact``: a key fact has no target hint and is not bound.
        """
        from cloudra.dag.completion import evaluate_delivery
        from cloudra.dag.evidence_facts import EvidenceFact, FactSubject

        snapshot = self.load_snapshot()
        contract = self.load_coverage_contract()
        exceptions: list[dict[str, Any]] = []

        with self.db.connect() as con:
            all_facts = con.execute(
                "SELECT fact_id, check_name, outcome, subject, source_refs, "
                "details, adapter_version FROM dag_evidence_facts"
            ).fetchall()
            bound_by_target: dict[str, set[str]] = {}
            for target_id, evidence_id in con.execute(
                "SELECT target_id, evidence_id FROM dag_evidence_bindings"
            ).fetchall():
                bound_by_target.setdefault(target_id, set()).add(evidence_id)
        # Load all facts once.
        facts_by_id: dict[str, EvidenceFact] = {}
        for fact_id, check, outcome, subject, source_refs, details, adapter_version in all_facts:
            subj = FactSubject.model_validate(json.loads(subject))
            refs = [GraphRef(**item) for item in json.loads(source_refs)]
            facts_by_id[fact_id] = EvidenceFact(
                fact_id=fact_id,
                check=check,
                outcome=outcome,
                subject=subj,
                source_refs=refs,
                details=json.loads(details),
                adapter_version=adapter_version,
            )

        report = evaluate_delivery(snapshot.delivery, contract)
        target_gaps: dict[str, list[str]] = {}
        for gate in [*report.unresolved, *report.inconclusive]:
            target_gaps.setdefault(gate.target_id, []).append(gate.code)

        for target_id in target_ids:
            if target_id in target_gaps:
                for code in target_gaps[target_id]:
                    key = f"{target_id}:coverage_gap:{code}"
                    if not any(item.get("exception_key") == key for item in exceptions):
                        exceptions.append({
                            "exception_key": key,
                            "category": "coverage_gap",
                            "target_id": target_id,
                            "code": code,
                            "detail": "required coverage evidence is missing or inconclusive",
                        })
            bound_ids = bound_by_target.get(target_id, set())
            for fact_id, fact in facts_by_id.items():
                if fact.outcome != "refutes":
                    continue
                fact_targets = {ref.ref_id for ref in fact.source_refs} & bound_ids
                hint = fact.subject.target_hint
                if fact_targets or hint == target_id:
                    key = f"{target_id}:contradiction:{fact.check}:{fact.fact_id}"
                    if not any(item.get("exception_key") == key for item in exceptions):
                        exceptions.append({
                            "exception_key": key,
                            "category": "contradiction",
                            "target_id": target_id,
                            "check": fact.check,
                            "fact_id": fact.fact_id,
                            "detail": "registered evidence refutes this target",
                        })
            # Target-hinted facts not yet bound to this target.
            for fact_id, fact in facts_by_id.items():
                if fact.subject.target_hint == target_id and not (bound_ids & {ref.ref_id for ref in fact.source_refs}):
                    key = f"{target_id}:known_target_unbound_fact:{fact.fact_id}"
                    if not any(item.get("exception_key") == key for item in exceptions):
                        exceptions.append({
                            "exception_key": key,
                            "category": "known_target_unbound_fact",
                            "target_id": target_id,
                            "fact_id": fact.fact_id,
                            "check": fact.check,
                            "detail": "evidence targets this element but is not yet bound",
                        })

        # Untargeted key facts: no target hint, not bound to any target.
        bound_anywhere = {eid for ids in bound_by_target.values() for eid in ids}
        for fact_id, fact in facts_by_id.items():
            if fact.subject.target_hint:
                continue
            if any(ref.ref_id in bound_anywhere for ref in fact.source_refs):
                continue
            key = f"untargeted:{fact.check}:{fact.fact_id}"
            if not any(item.get("exception_key") == key for item in exceptions):
                exceptions.append({
                    "exception_key": key,
                    "category": "untargeted_key_fact",
                    "target_id": None,
                    "fact_id": fact.fact_id,
                    "check": fact.check,
                    "outcome": fact.outcome,
                    "source_refs": [ref.model_dump(mode='json') for ref in fact.source_refs],
                    "detail": "key evidence has no target binding or target hint",
                })
        return exceptions

    # --- CallReview 收件箱（D12：append-only，不经 DagEngine 版本化 mutation） ---

    def enqueue_call_review(self, review: CallReview) -> None:
        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    """
                    INSERT OR IGNORE INTO dag_call_reviews(
                        review_id, tool_call_id, tool_name, is_success,
                        caller_session_id, caller_role_id, caller_legacy_id,
                        arguments_digest, result_summary, source_path, result_kind,
                        compute_job_id, suggested_target_id, suggested_stage, state,
                        created_at, claim, rationale, submitter, evidence_id, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        review.source_path,
                        review.result_kind,
                        review.compute_job_id,
                        review.suggested_target_id,
                        review.suggested_stage,
                        review.state,
                        review.created_at,
                        review.claim,
                        review.rationale,
                        review.submitter,
                        review.evidence_id,
                        review.source,
                    ),
                )

        retry_on_locked(operation)

    def submit_call_reviews(
        self, reviews: list[CallReview]
    ) -> list[tuple[str, bool]]:
        """原子批量入箱（§5 显式送审）：同一事务内逐条按 pending 幂等键
        (evidence_id, suggested_target_id, suggested_stage, 规范化 claim) 去重——
        相同 pending 声明返回既有 review_id（created=False），不重复入箱；
        这是低层阶段绑定入口；逐文件审查走 dag_review_requests，不拆阶段。
        此处不能合并不同阶段，否则单阶段裁决会丢掉其余绑定。

        校验（目标/阶段存在、调用已结束、证据可解析、项目归属）由调用方在
        提交前全部完成：本函数只做去重 + 写入，不在中途失败。已裁决的同构
        重提照常生成新 review（既有产品语义）。
        返回与输入同序的 (review_id, created) 列表。
        """
        from cloudra.dag.models import normalize_claim

        outcomes: list[tuple[str, bool]] = []

        def operation() -> None:
            with self.db.connect() as con:
                for review in reviews:
                    rows = con.execute(
                        "SELECT review_id, claim FROM dag_call_reviews "
                        "WHERE evidence_id = ? AND suggested_target_id IS ? "
                        "AND suggested_stage = ? AND state = 'pending'",
                        (
                            review.evidence_id,
                            review.suggested_target_id,
                            review.suggested_stage,
                        ),
                    ).fetchall()
                    duplicate = next(
                        (
                            review_id
                            for review_id, stored_claim in rows
                            if normalize_claim(stored_claim)
                            == normalize_claim(review.claim)
                        ),
                        None,
                    )
                    if duplicate is not None:
                        outcomes.append((duplicate, False))
                        continue
                    con.execute(
                        """
                        INSERT INTO dag_call_reviews(
                            review_id, tool_call_id, tool_name, is_success,
                            caller_session_id, caller_role_id, caller_legacy_id,
                            arguments_digest, result_summary, source_path,
                            result_kind, compute_job_id, suggested_target_id,
                            suggested_stage, state, created_at,
                            claim, rationale, submitter, evidence_id, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            review.source_path,
                            review.result_kind,
                            review.compute_job_id,
                            review.suggested_target_id,
                            review.suggested_stage,
                            review.state,
                            review.created_at,
                            review.claim,
                            review.rationale,
                            review.submitter,
                            review.evidence_id,
                            review.source,
                        ),
                    )
                    outcomes.append((review.review_id, True))

        if reviews:
            retry_on_locked(operation)
        return outcomes

    @staticmethod
    def _review_from_row(row) -> CallReview:
        # 新列（claim/rationale/submitter/evidence_id/source，§5）由
        # _RELATED_EXTRA_COLUMNS 补在末尾；旧库升级前的行由迁移默认值兜底，
        # 这里再宽容一次列数（与 _draft_from_row 的 len 检查同款）。
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
            source_path=row[9],
            result_kind=row[10],
            compute_job_id=row[11],
            suggested_target_id=row[12],
            suggested_stage=row[13],
            state=row[14],
            created_at=row[15],
            claim=row[16] if len(row) > 16 else "",
            rationale=row[17] if len(row) > 17 else "",
            submitter=row[18] if len(row) > 18 else "",
            evidence_id=row[19] if len(row) > 19 else "",
            source=row[20] if len(row) > 20 and row[20] else "legacy_auto",
        )

    _REVIEW_COLUMNS = (
        "review_id, tool_call_id, tool_name, is_success, caller_session_id, "
        "caller_role_id, caller_legacy_id, arguments_digest, result_summary, "
        "source_path, result_kind, compute_job_id, suggested_target_id, suggested_stage, "
        "state, created_at, claim, rationale, submitter, evidence_id, source"
    )

    def list_call_reviews(
        self, state: str | None = "pending", *, source: str | None = None
    ) -> list[CallReview]:
        """收件箱读取；``source="explicit"`` 只取可消费的显式送审行（§5：
        legacy_auto/auto 的 pending 行保留审计但不进督导待办）。"""
        query = f"SELECT {self._REVIEW_COLUMNS} FROM dag_call_reviews"
        clauses: list[str] = []
        params: list = []
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, rowid"
        with self.db.connect() as con:
            rows = con.execute(query, params).fetchall()
        return [self._review_from_row(row) for row in rows]

    def list_call_verdicts(self) -> list[dict[str, Any]]:
        """Return durable Supervisor verdict payloads for call reviews."""
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT decision_id, payload FROM dag_review_notifications "
                "WHERE kind = 'call_verdict' ORDER BY created_at, rowid"
            ).fetchall()
        return [
            {"review_id": row[0], **(json.loads(row[1]) if row[1] else {})}
            for row in rows
        ]

    def get_call_review(self, review_id: str) -> CallReview | None:
        with self.db.connect() as con:
            row = con.execute(
                f"SELECT {self._REVIEW_COLUMNS} FROM dag_call_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        return self._review_from_row(row) if row else None

    def mark_call_review(
        self,
        review_id: str,
        state: str,
        *,
        notification: dict[str, Any] | None = None,
    ) -> None:
        """裁决落态；``notification`` 携带的裁决通知同事务入表（call_verdict）。

        notification = {"recipient_session_id": ..., "payload": {...}}——
        裁决行本身不落 verdict 列，渲染材料全在 payload。
        """
        if state not in ("pending", "reviewed", "ignored"):
            raise ValueError(f"invalid review state {state!r}")

        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    "UPDATE dag_call_reviews SET state = ? WHERE review_id = ?",
                    (state, review_id),
                )
                if notification is not None:
                    self._insert_notification(
                        con,
                        kind="call_verdict",
                        subject_id=review_id,
                        recipient_session_id=str(
                            notification.get("recipient_session_id") or ""
                        ),
                        payload=notification.get("payload") or {},
                    )

        retry_on_locked(operation)

    # --- 机理草稿（D1/D4）：mechanism_accepted = EXISTS(state='accepted') ---

    def save_draft(self, draft: MechanismDraft, *, actor_id: str) -> str:
        draft_id = "draft_" + uuid.uuid4().hex

        def operation() -> None:
            with self.db.connect() as con:
                self._insert_draft(con, draft_id, draft, actor_id)

        retry_on_locked(operation)
        return draft_id

    @staticmethod
    def _insert_draft(
        con: sqlite3.Connection, draft_id: str, draft: MechanismDraft, actor_id: str
    ) -> None:
        """Insert a draft on the caller's transaction when graph ops accompany it."""
        operations = _canonical_json([
            op.model_dump(mode="json", exclude={"node": {"payload"}, "edge": {"payload"}})
            for op in draft.operations
        ])
        contracts = _canonical_json(
            {key: contract.model_dump(mode="json")
             for key, contract in draft.stage_contracts.items()}
        )
        claim_spec = (
            _canonical_json(draft.claim_spec.model_dump(mode="json"))
            if draft.claim_spec is not None
            else ""
        )
        con.execute(
            """
            INSERT INTO dag_drafts(
                draft_id, state, rationale, operations, stage_contracts,
                actor_id, claim_spec, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                draft_id, draft.state, draft.rationale, operations,
                contracts, actor_id, claim_spec,
            ),
        )

    @staticmethod
    def _draft_from_row(row) -> MechanismDraft:
        from cloudra.dag.models import ClaimSpec

        claim_spec = None
        contract_version = 1
        if len(row) > 4 and row[4]:
            claim_spec = ClaimSpec.model_validate(json.loads(row[4]))
            contract_version = 2
        return MechanismDraft(
            operations=[parse_graph_operation(op) for op in json.loads(row[0])],
            stage_contracts={
                key: StageContract.model_validate(value)
                for key, value in json.loads(row[1]).items()
            },
            rationale=row[2],
            state=row[3],
            contract_version=contract_version,
            claim_spec=claim_spec,
        )

    def get_draft(self, draft_id: str) -> MechanismDraft | None:
        with self.db.connect() as con:
            row = con.execute(
                "SELECT operations, stage_contracts, rationale, state, claim_spec "
                "FROM dag_drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
        return self._draft_from_row(row) if row else None

    def list_open_drafts(self) -> list[tuple[str, MechanismDraft]]:
        """Read every undecided draft for the persistent supervision inbox."""
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT draft_id, operations, stage_contracts, rationale, state, claim_spec "
                "FROM dag_drafts WHERE state = 'open' ORDER BY rowid"
            ).fetchall()
        return [(row[0], self._draft_from_row(row[1:])) for row in rows]

    def list_delivery_drafts(self) -> list[tuple[str, MechanismDraft, str]]:
        """Read draft review history in creation order for final delivery audit."""
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT draft_id, operations, stage_contracts, rationale, state, "
                "claim_spec, reject_reason FROM dag_drafts ORDER BY rowid"
            ).fetchall()
        return [
            (row[0], self._draft_from_row(row[1:6]), row[6] or "")
            for row in rows
        ]

    def latest_open_draft(self) -> tuple[str, MechanismDraft] | None:
        with self.db.connect() as con:
            row = con.execute(
                "SELECT draft_id, operations, stage_contracts, rationale, state, claim_spec "
                "FROM dag_drafts WHERE state = 'open' ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return row[0], self._draft_from_row(row[1:])

    def set_draft_state(
        self,
        draft_id: str,
        state: str,
        *,
        reject_reason: str = "",
        notification: dict[str, Any] | None = None,
    ) -> None:
        """草稿裁决落态；``notification`` 携带的裁决通知同事务入表（draft_verdict）。"""
        if state not in ("accepted", "rejected"):
            raise ValueError(f"invalid draft state {state!r}")

        def operation() -> None:
            with self.db.connect() as con:
                con.execute(
                    "UPDATE dag_drafts SET state = ?, reject_reason = ?, "
                    "decided_at = datetime('now') WHERE draft_id = ?",
                    (state, reject_reason, draft_id),
                )
                if notification is not None:
                    self._insert_notification(
                        con,
                        kind="draft_verdict",
                        subject_id=draft_id,
                        recipient_session_id=str(
                            notification.get("recipient_session_id") or ""
                        ),
                        payload=notification.get("payload") or {},
                    )

        retry_on_locked(operation)

    def draft_actor_id(self, draft_id: str) -> str:
        """草稿的 proposer（legacy a-N actor 词表）；缺失返回空串。"""
        with self.db.connect() as con:
            row = con.execute(
                "SELECT actor_id FROM dag_drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
        return row[0] if row else ""

    def has_accepted_draft(self) -> bool:
        """D4：mechanism_accepted 的唯一判据。"""
        with self.db.connect() as con:
            row = con.execute(
                "SELECT 1 FROM dag_drafts WHERE state = 'accepted' LIMIT 1"
            ).fetchone()
        return row is not None

    def accepted_claim_spec(self):
        """当前已接受的交付契约（contract_version=2）；无则 None。"""
        from cloudra.dag.models import ClaimSpec

        with self.db.connect() as con:
            row = con.execute(
                "SELECT claim_spec FROM dag_drafts "
                "WHERE state = 'accepted' AND claim_spec != '' "
                "ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return ClaimSpec.model_validate(json.loads(row[0]))

    def latest_draft(self) -> dict[str, Any] | None:
        """最新草稿（open 优先，其次最近裁决）+ 元信息，供 /dag/draft 投影。"""
        with self.db.connect() as con:
            row = con.execute(
                """
                SELECT draft_id, state, rationale, operations, stage_contracts,
                       actor_id, reject_reason, created_at, claim_spec
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
            "claim_spec": json.loads(row[8]) if row[8] else None,
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
