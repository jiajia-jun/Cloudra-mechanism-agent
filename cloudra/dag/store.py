"""Durable storage for the process and delivery DAG pair."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from cloudra.dag.models import (
    CoverageContract,
    DagEdge,
    DagNode,
    GraphBundle,
    GraphData,
    GraphKind,
    GraphRef,
    GraphSnapshot,
    SpeciesRecord,
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
                SELECT node_id, node_type, label, refs, payload
                FROM dag_nodes WHERE graph_id = ? ORDER BY node_id
                """,
                (graph_id,),
            ).fetchall()
            edge_rows = con.execute(
                """
                SELECT edge_id, source_node_id, target_node_id, edge_type, label, refs, payload
                FROM dag_edges WHERE graph_id = ? ORDER BY edge_id
                """,
                (graph_id,),
            ).fetchall()
        nodes = [
            DagNode(
                node_id=row[0],
                node_type=row[1],
                label=row[2],
                refs=json.loads(row[3]),
                payload=json.loads(row[4]),
            )
            for row in node_rows
        ]
        edges = [
            DagEdge(
                edge_id=row[0],
                source_node_id=row[1],
                target_node_id=row[2],
                edge_type=row[3],
                label=row[4],
                refs=json.loads(row[5]),
                payload=json.loads(row[6]),
            )
            for row in edge_rows
        ]
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
