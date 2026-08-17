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


def test_legacy_journal_operations_replay_into_typed_graph(tmp_path):
    """旧格式兼容：手工构造 data-dict 形状 + 旧词表的 journal 记录可重放；
    process op 在 Phase 4 后重放为 no-op（revision 照原口径推进），
    并在 journal 里留 ignored_legacy_process_op 记录。"""
    import json

    _api, db, store = _new_store(tmp_path, "legacy-journal")
    store.ensure_bundle("s1")
    revisions = store.load_bundle().revisions
    legacy_operations = [
        {
            "op": "add_node",
            "graph": "process",
            "data": {
                "node_id": "legacy",
                "node_type": "workflow",
                "label": "legacy step",
                "payload": {"status": "pending", "priority": 5, "custom": "kept"},
            },
        },
        {
            "op": "update_node",
            "graph": "process",
            "data": {"node_id": "legacy", "changes": {"status": "in_progress"}},
        },
        {
            "op": "add_link",
            "graph": None,
            "data": {
                "link_id": "lk-legacy",
                "process_node_id": "legacy",
                "delivery_element_type": "node",
                "delivery_element_id": "r",
            },
        },
        {
            "op": "add_node",
            "graph": "delivery",
            "data": {
                "node_id": "r",
                "node_type": "intermediate_occurrence",
                "label": "R",
                "payload": {"role": "reactant", "evidence_level": "proposed"},
            },
        },
    ]
    # touch 口径与写入时一致：每 mutation 按图推进一次——本行 4 个 op
    # 触及 process（含 add_link 双图）与 delivery，各 +1
    resulting = {"process": revisions["process"] + 1, "delivery": revisions["delivery"] + 1}
    with db.connect() as con:
        con.execute(
            """
            INSERT INTO dag_mutations(
                mutation_id, graph_id, base_revision, resulting_revision,
                actor_type, actor_id, session_id, rationale, base_revisions,
                resulting_revisions, operations, accepted, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
            """,
            (
                "mut_legacy",
                "dag_process",
                revisions["process"],
                resulting["process"],
                "harness",
                "legacy-test",
                "s1",
                "hand-written legacy journal row",
                json.dumps(revisions),
                json.dumps(resulting),
                json.dumps(legacy_operations),
            ),
        )

    rebuilt = store.rebuild_materialized()

    assert rebuilt.bundle.revisions == resulting
    # process op 全部 no-op：不物化任何 process 节点/边
    assert rebuilt.process.nodes == []
    assert rebuilt.process.edges == []
    occurrence = rebuilt.delivery.nodes[0]
    assert occurrence.node_type == "occurrence"
    assert occurrence.role == "reactant"
    assert occurrence.evidence_level == "proposed"
    with db.connect() as con:
        ignored = con.execute(
            "SELECT rationale FROM dag_mutations WHERE rationale LIKE 'ignored_legacy_process_op%'"
        ).fetchall()
    assert ignored and "3 legacy process operations" in ignored[0][0]
    # 二次重放（幂等）仍一致
    assert store.rebuild_materialized() == rebuilt


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

    assert [(s.kind.value, s.status.value) for s in node.stages] == [
        ("geometry", "supported")
    ]
    assert [(s.kind.value, s.status.value, s.reason) for s in inconclusive.stages] == [
        ("geometry", "skipped", "only a scan exists")
    ]
    assert [(s.kind.value, s.status.value) for s in edge.stages] == [
        ("ts_opt", "supported"),
        ("frequency", "supported"),
    ]
