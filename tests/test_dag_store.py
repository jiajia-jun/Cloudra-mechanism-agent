import math

import pytest

from cloudra.persistence.database import ConversationDB


def _load_store_api():
    try:
        from cloudra.dag.models import GraphKind, GraphRef
        from cloudra.dag.store import (
            DagCorruptionError,
            DagStore,
            EvidencePayloadError,
            InvalidGraphReference,
            SpeciesConflictError,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"DAG store API is missing: {exc}")
    return {
        "DagStore": DagStore,
        "DagCorruptionError": DagCorruptionError,
        "GraphKind": GraphKind,
        "GraphRef": GraphRef,
        "EvidencePayloadError": EvidencePayloadError,
        "InvalidGraphReference": InvalidGraphReference,
        "SpeciesConflictError": SpeciesConflictError,
    }


def _new_store(tmp_path, conversation_id="dag-store"):
    api = _load_store_api()
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    return api, db, api["DagStore"](db)


def test_database_schema_does_not_create_graph_rows_until_dag_mode_initializes(tmp_path):
    api, db, store = _new_store(tmp_path, "lazy-graphs")

    with db.connect() as con:
        before = con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone()[0]
    bundle = store.ensure_bundle(session_id="s1")
    with db.connect() as con:
        after = con.execute("SELECT graph_kind FROM dag_graphs ORDER BY graph_kind").fetchall()

    assert before == 0
    assert after == [("delivery",), ("process",)]
    assert bundle.process_graph_id != bundle.delivery_graph_id
    assert bundle.revisions == {"process": 0, "delivery": 0}


def test_graph_pair_survives_new_store_instance(tmp_path):
    api, db, store = _new_store(tmp_path, "restart-graphs")
    first = store.ensure_bundle(session_id="s1")

    restarted = api["DagStore"](ConversationDB.from_path(db.path))
    second = restarted.load_bundle()
    snapshot = restarted.load_snapshot()

    assert second == first
    assert snapshot.bundle == first
    assert snapshot.process.nodes == []
    assert snapshot.delivery.edges == []


def test_tool_result_evidence_is_content_addressed_and_resolvable(tmp_path):
    api, db, store = _new_store(tmp_path, "evidence")
    payload = {
        "mapping_status": "unique",
        "heavy_atom_map": [1, 2, 3, 4, 5, 6],
    }

    first = store.register_evidence("s1", "reaction_mapping", payload)
    second = store.register_evidence("s2", "reaction_mapping", payload)

    assert first.ref_type == "tool_result"
    assert first.ref_id == second.ref_id
    assert first.content_hash == second.content_hash
    assert store.resolve_evidence(first) == payload
    with db.connect() as con:
        rows = con.execute("SELECT COUNT(*) FROM dag_evidence").fetchone()[0]
    assert rows == 1


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_evidence_rejects_non_finite_json_numbers(tmp_path, bad_value):
    api, _db, store = _new_store(tmp_path, f"nonfinite-{repr(bad_value)}".replace("-", "n"))

    with pytest.raises(api["EvidencePayloadError"]):
        store.register_evidence("s1", "thermo_analysis", {"delta_g": bad_value})


def test_session_event_cannot_be_constructed_as_graph_evidence(tmp_path):
    api, _db, _store = _new_store(tmp_path, "bad-ref")

    with pytest.raises((ValueError, api["InvalidGraphReference"])):
        api["GraphRef"](ref_type="session_event", ref_id="event-1")


def test_species_records_are_stable_and_immutable(tmp_path):
    api, _db, store = _new_store(tmp_path, "species")
    first = store.upsert_species(
        canonical_key="smiles:C=COCC=C|charge:0|multiplicity:1",
        identifiers={"smiles": "C=COCC=C"},
        charge=0,
        multiplicity=1,
    )
    second = store.upsert_species(
        canonical_key="smiles:C=COCC=C|charge:0|multiplicity:1",
        identifiers={"smiles": "C=COCC=C"},
        charge=0,
        multiplicity=1,
    )

    assert first == second
    assert first.species_id.startswith("sp_")
    assert store.get_species(first.species_id) == first
    with pytest.raises(api["SpeciesConflictError"]):
        store.upsert_species(
            canonical_key=first.canonical_key,
            identifiers={"smiles": "C=COCC=C"},
            charge=1,
            multiplicity=2,
        )


def _seed_delivery_path(store):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ElementaryStepEdge,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
    )

    engine = DagEngine(store)
    result = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="replay-test",
            base_revisions=store.load_bundle().revisions,
            rationale="seed replay state",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="r", label="R", role="reactant"),
                ),
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="p", label="P", role="product"),
                ),
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(
                        edge_id="step",
                        source_node_id="r",
                        target_node_id="p",
                    ),
                ),
            ],
        )
    )
    assert result.accepted
    return engine


def test_materialized_graph_can_be_rebuilt_from_accepted_journal(tmp_path):
    _api, db, store = _new_store(tmp_path, "rebuild")
    store.ensure_bundle("s1")
    engine = _seed_delivery_path(store)
    expected = engine.snapshot()
    with db.connect() as con:
        con.execute("DELETE FROM dag_nodes WHERE node_id = 'r'")

    rebuilt = store.rebuild_materialized()

    assert rebuilt == expected


def test_invalid_journal_raises_without_inventing_an_empty_graph(tmp_path):
    api, db, store = _new_store(tmp_path, "bad-journal")
    store.ensure_bundle("s1")
    _seed_delivery_path(store)
    with db.connect() as con:
        con.execute(
            "UPDATE dag_mutations SET resulting_revisions = ? WHERE accepted = 1",
            ('{"delivery":99,"process":0}',),
        )
        con.execute("DELETE FROM dag_nodes WHERE node_id = 'r'")

    with pytest.raises(api["DagCorruptionError"]):
        store.rebuild_materialized()
    with db.connect() as con:
        remaining = con.execute("SELECT node_id FROM dag_nodes ORDER BY node_id").fetchall()
    assert remaining == [("p",)]


def test_legacy_rows_without_stages_map_from_evidence_level(tmp_path):
    """旧物化行（stages 列为空）读取时按 evidence_level 一次性映射出阶段。"""
    api, db, store = _new_store(tmp_path, "legacy-stage-map")
    store.ensure_bundle(session_id="s1")
    with db.connect() as con:
        con.execute(
            """
            INSERT INTO dag_nodes(
                graph_id, node_id, node_type, label, refs, payload,
                created_revision, updated_revision
            ) VALUES (
                'dag_delivery', 'i0', 'occurrence', 'int', '[]',
                '{"evidence_level": "structure_supported"}', 0, 0
            )
            """
        )
        con.execute(
            """
            INSERT INTO dag_nodes(
                graph_id, node_id, node_type, label, refs, payload,
                created_revision, updated_revision
            ) VALUES (
                'dag_delivery', 'i1', 'occurrence', 'int2', '[]',
                '{"evidence_level": "inconclusive", "reason": "only a scan exists"}', 0, 0
            )
            """
        )
        con.execute(
            """
            INSERT INTO dag_edges(
                graph_id, edge_id, source_node_id, target_node_id, edge_type,
                label, refs, payload, created_revision, updated_revision
            ) VALUES (
                'dag_delivery', 'e0', 'i0', 'i1', 'elementary_step', 'step', '[]',
                '{"evidence_level": "saddle_supported"}', 0, 0
            )
            """
        )

    snapshot = store.load_snapshot()
    node = next(n for n in snapshot.delivery.nodes if n.node_id == "i0")
    inconclusive = next(n for n in snapshot.delivery.nodes if n.node_id == "i1")
    edge = snapshot.delivery.edges[0]

    assert [(s.kind.value, s.status.value) for s in node.stages] == [("geometry", "supported")]
    assert [(s.kind.value, s.status.value, s.reason) for s in inconclusive.stages] == [
        ("geometry", "skipped", "only a scan exists")
    ]
    assert [(s.kind.value, s.status.value) for s in edge.stages] == [
        ("ts_opt", "supported"),
        ("frequency", "supported"),
    ]


def test_store_persists_and_loads_species_node_and_step_edge(tmp_path):
    """Task 1: 持久化与加载 SpeciesNode 与 ElementaryStepEdge（无 occurrence/role）。"""
    api, db, store = _new_store(tmp_path, "store-species")
    from cloudra.dag.models import ElementaryStepEdge, SpeciesNode

    store.ensure_bundle("s1")
    with db.connect() as con:
        con.execute(
            """
            INSERT INTO dag_nodes(
                graph_id, node_id, node_type, label, refs, payload, created_revision, updated_revision
            ) VALUES (
                'dag_delivery', 'sp_01', 'species', '初始络合物体系', '[]',
                '{"name": "初始络合物体系", "smiles": "CCO"}', 0, 0
            )
            """
        )
        con.execute(
            """
            INSERT INTO dag_nodes(
                graph_id, node_id, node_type, label, refs, payload, created_revision, updated_revision
            ) VALUES (
                'dag_delivery', 'sp_02', 'species', '产物络合物体系', '[]',
                '{"name": "产物络合物体系", "smiles": "CC=O"}', 0, 0
            )
            """
        )
        con.execute(
            """
            INSERT INTO dag_edges(
                graph_id, edge_id, source_node_id, target_node_id, edge_type,
                label, refs, payload, created_revision, updated_revision
            ) VALUES (
                'dag_delivery', 'step_01', 'sp_01', 'sp_02', 'elementary_step',
                '脱氢转化', '[]', '{"name": "脱氢转化"}', 0, 0
            )
            """
        )

    snapshot = store.load_snapshot()
    assert len(snapshot.delivery.nodes) == 2
    assert len(snapshot.delivery.edges) == 1
    node1 = next(n for n in snapshot.delivery.nodes if n.node_id == "sp_01")
    assert isinstance(node1, SpeciesNode)
    assert node1.name == "初始络合物体系"
    assert node1.smiles == "CCO"
    assert not hasattr(node1, "role") or node1.role is None
    edge1 = snapshot.delivery.edges[0]
    assert isinstance(edge1, ElementaryStepEdge)
    assert edge1.name == "脱氢转化"
    assert edge1.source_node_id == "sp_01"
    assert edge1.target_node_id == "sp_02"
