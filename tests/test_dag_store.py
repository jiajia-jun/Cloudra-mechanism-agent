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


def _seed_process_path(store):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, GraphOperation, MutationBatch

    engine = DagEngine(store)
    result = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="replay-test",
            base_revisions=store.load_bundle().revisions,
            rationale="seed replay state",
            operations=[
                GraphOperation(
                    op="add_node",
                    graph="process",
                    data={"node_id": "map", "node_type": "work", "label": "map"},
                ),
                GraphOperation(
                    op="add_node",
                    graph="process",
                    data={"node_id": "ts", "node_type": "work", "label": "TS"},
                ),
                GraphOperation(
                    op="add_edge",
                    graph="process",
                    data={
                        "edge_id": "map-before-ts",
                        "source_node_id": "map",
                        "target_node_id": "ts",
                        "edge_type": "depends_on",
                    },
                ),
            ],
        )
    )
    assert result.accepted
    return engine


def test_materialized_graph_can_be_rebuilt_from_accepted_journal(tmp_path):
    _api, db, store = _new_store(tmp_path, "rebuild")
    store.ensure_bundle("s1")
    engine = _seed_process_path(store)
    expected = engine.snapshot()
    with db.connect() as con:
        con.execute("DELETE FROM dag_nodes WHERE node_id = 'map'")

    rebuilt = store.rebuild_materialized()

    assert rebuilt == expected


def test_invalid_journal_raises_without_inventing_an_empty_graph(tmp_path):
    api, db, store = _new_store(tmp_path, "bad-journal")
    store.ensure_bundle("s1")
    _seed_process_path(store)
    with db.connect() as con:
        con.execute(
            "UPDATE dag_mutations SET resulting_revisions = ? WHERE accepted = 1",
            ('{"delivery":0,"process":99}',),
        )
        con.execute("DELETE FROM dag_nodes WHERE node_id = 'map'")

    with pytest.raises(api["DagCorruptionError"]):
        store.rebuild_materialized()
    with db.connect() as con:
        remaining = con.execute("SELECT node_id FROM dag_nodes ORDER BY node_id").fetchall()
    assert remaining == [("ts",)]
