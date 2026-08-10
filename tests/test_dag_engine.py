import pytest

from cloudra.database import ConversationDB


def _load_engine_api():
    try:
        from cloudra.dag.engine import DagEngine
        from cloudra.dag.models import (
            GraphActor,
            GraphOperation,
            GraphRef,
            MutationBatch,
        )
        from cloudra.dag.store import DagStore
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"DAG mutation API is missing: {exc}")
    return {
        "DagEngine": DagEngine,
        "DagStore": DagStore,
        "GraphActor": GraphActor,
        "GraphOperation": GraphOperation,
        "GraphRef": GraphRef,
        "MutationBatch": MutationBatch,
    }


def _new_engine(tmp_path, conversation_id="dag-engine"):
    api = _load_engine_api()
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    store = api["DagStore"](db)
    store.ensure_bundle("s1")
    return api, db, store, api["DagEngine"](store)


def _op(api, name, graph=None, **data):
    return api["GraphOperation"](op=name, graph=graph, data=data)


def _batch(api, store, operations, *, actor="harness", base_revisions=None):
    return api["MutationBatch"](
        session_id="s1",
        actor=api["GraphActor"](actor),
        actor_id=f"test-{actor}",
        base_revisions=base_revisions or store.load_bundle().revisions,
        operations=operations,
        rationale="focused test",
    )


def test_cycle_rejects_entire_batch(tmp_path):
    api, _db, store, engine = _new_engine(tmp_path, "cycle")
    result = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(api, "add_node", "process", node_id="a", node_type="work", label="A"),
                _op(api, "add_node", "process", node_id="b", node_type="work", label="B"),
                _op(
                    api,
                    "add_edge",
                    "process",
                    edge_id="ab",
                    source_node_id="a",
                    target_node_id="b",
                    edge_type="depends_on",
                ),
                _op(
                    api,
                    "add_edge",
                    "process",
                    edge_id="ba",
                    source_node_id="b",
                    target_node_id="a",
                    edge_type="depends_on",
                ),
            ],
        )
    )

    assert not result.accepted
    assert result.rejection_code == "cycle"
    assert engine.snapshot().process.nodes == []
    assert engine.snapshot().process.edges == []


def test_stale_revision_rejects_without_last_write_wins(tmp_path):
    api, _db, store, engine = _new_engine(tmp_path, "stale")
    stale = dict(store.load_bundle().revisions)
    accepted = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "add_node", "process", node_id="first", node_type="work", label="first")],
        )
    )
    rejected = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "add_node", "process", node_id="second", node_type="work", label="second")],
            base_revisions=stale,
        )
    )

    assert accepted.accepted
    assert not rejected.accepted
    assert rejected.rejection_code == "stale_revision"
    assert [node.node_id for node in engine.snapshot().process.nodes] == ["first"]


@pytest.mark.parametrize(
    ("operations", "code"),
    [
        (
            [
                ("add_node", "process", {"node_id": "a", "node_type": "work", "label": "A"}),
                ("add_node", "process", {"node_id": "a", "node_type": "work", "label": "again"}),
            ],
            "duplicate_id",
        ),
        (
            [
                (
                    "add_edge",
                    "delivery",
                    {
                        "edge_id": "ghost",
                        "source_node_id": "missing-a",
                        "target_node_id": "missing-b",
                        "edge_type": "elementary_step",
                    },
                )
            ],
            "dangling_edge",
        ),
    ],
)
def test_invalid_structure_rejects_entire_batch(tmp_path, operations, code):
    api, _db, store, engine = _new_engine(tmp_path, f"invalid-{code}")
    typed = [_op(api, name, graph, **data) for name, graph, data in operations]

    result = engine.apply_batch(_batch(api, store, typed))

    assert not result.accepted
    assert result.rejection_code == code
    assert engine.snapshot().bundle.revisions == {"process": 0, "delivery": 0}


def test_supervisor_cannot_waive_gate_or_claim_overall_completion(tmp_path):
    api, _db, store, engine = _new_engine(tmp_path, "supervisor-policy")
    waive = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "waive_gate", None, gate_id="endpoint", rationale="looks fine")],
            actor="supervisor",
        )
    )
    complete = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "process",
                    node_id="root",
                    node_type="deliverable",
                    label="mechanism",
                    payload={"overall_complete": True},
                )
            ],
            actor="supervisor",
        )
    )

    assert not waive.accepted
    assert waive.rejection_code == "actor_forbidden"
    assert not complete.accepted
    assert complete.rejection_code == "actor_forbidden"


def test_agent_cannot_lower_a_persisted_coverage_requirement(tmp_path):
    from cloudra.dag.models import CoverageContract

    api, _db, store, engine = _new_engine(tmp_path, "agent-coverage-policy")
    stronger = CoverageContract.mechanism_default(require_thermochemistry=True)
    strengthened = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "set_coverage_contract",
                    None,
                    contract=stronger.model_dump(mode="json"),
                )
            ],
            actor="user",
        )
    )
    assert strengthened.accepted

    lowered = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "set_coverage_contract",
                    None,
                    contract=CoverageContract.mechanism_default().model_dump(
                        mode="json"
                    ),
                )
            ],
            actor="agent",
        )
    )

    assert not lowered.accepted
    assert lowered.rejection_code == "actor_forbidden"
    assert store.load_coverage_contract() == stronger
    assert engine.snapshot().process.nodes == []


@pytest.mark.parametrize("actor", ["agent", "supervisor"])
def test_model_actors_cannot_forge_evidence_derived_levels(tmp_path, actor):
    api, _db, store, engine = _new_engine(tmp_path, f"{actor}-evidence-policy")
    seeded = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "delivery",
                    node_id="r",
                    node_type="intermediate_occurrence",
                    label="R",
                ),
                _op(
                    api,
                    "add_node",
                    "delivery",
                    node_id="p",
                    node_type="intermediate_occurrence",
                    label="P",
                ),
                _op(
                    api,
                    "add_edge",
                    "delivery",
                    edge_id="step",
                    source_node_id="r",
                    target_node_id="p",
                    edge_type="elementary_step",
                    payload={"evidence_level": "proposed"},
                ),
            ],
        )
    )
    assert seeded.accepted

    forged = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "update_edge",
                    "delivery",
                    edge_id="step",
                    changes={
                        "saddle_supported": True,
                        "evidence_level": "endpoint_supported",
                    },
                )
            ],
            actor=actor,
        )
    )

    assert not forged.accepted
    assert forged.rejection_code == "actor_forbidden"
    edge = engine.snapshot().delivery.edges[0]
    assert edge.payload == {"evidence_level": "proposed"}

    prevalidated = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_edge",
                    "delivery",
                    edge_id="forged-step",
                    source_node_id="r",
                    target_node_id="p",
                    edge_type="elementary_step",
                    payload={"evidence_level": "endpoint_supported"},
                )
            ],
            actor=actor,
        )
    )

    assert not prevalidated.accepted
    assert prevalidated.rejection_code == "actor_forbidden"
    assert [item.edge_id for item in engine.snapshot().delivery.edges] == ["step"]


def test_graph_references_must_resolve_in_the_conversation(tmp_path):
    api, _db, store, engine = _new_engine(tmp_path, "reference-validation")
    missing = api["GraphRef"](
        ref_type="tool_result",
        ref_id="ev_missing",
        content_hash="sha256:missing",
    )

    result = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "process",
                    node_id="mapping",
                    node_type="calculation",
                    label="mapping",
                    refs=[missing.model_dump()],
                )
            ],
        )
    )

    assert not result.accepted
    assert result.rejection_code == "invalid_reference"
    assert engine.snapshot().process.nodes == []


def test_attached_evidence_is_additive_and_cannot_be_rewritten(tmp_path):
    api, _db, store, engine = _new_engine(tmp_path, "immutable-evidence")
    evidence = store.register_evidence("s1", "reaction_mapping", {"mapping_status": "unique"})
    created = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "process",
                    node_id="mapping",
                    node_type="calculation",
                    label="mapping",
                    refs=[evidence.model_dump()],
                )
            ],
        )
    )
    rewrite = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "update_node",
                    "process",
                    node_id="mapping",
                    changes={"refs": []},
                )
            ],
            actor="supervisor",
        )
    )

    assert created.accepted
    assert not rewrite.accepted
    assert rewrite.rejection_code == "actor_forbidden"
    assert engine.snapshot().process.nodes[0].refs == [evidence]


def test_catalytic_return_is_an_acyclic_occurrence_of_the_same_species(tmp_path):
    api, _db, store, engine = _new_engine(tmp_path, "catalytic-occurrences")
    catalyst = store.upsert_species(
        canonical_key="smiles:[Pd]|charge:0|multiplicity:1",
        identifiers={"smiles": "[Pd]"},
        charge=0,
        multiplicity=1,
    )
    species_ref = api["GraphRef"](ref_type="species", ref_id=catalyst.species_id)

    result = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "delivery",
                    node_id="Cat@entry",
                    node_type="intermediate_occurrence",
                    label="catalyst entry",
                    refs=[species_ref.model_dump()],
                ),
                _op(
                    api,
                    "add_node",
                    "delivery",
                    node_id="Cat@return",
                    node_type="intermediate_occurrence",
                    label="catalyst return",
                    refs=[species_ref.model_dump()],
                ),
                _op(
                    api,
                    "add_edge",
                    "delivery",
                    edge_id="turnover",
                    source_node_id="Cat@entry",
                    target_node_id="Cat@return",
                    edge_type="elementary_step",
                    payload={"reversible": True},
                ),
            ],
        )
    )

    assert result.accepted
    nodes = engine.snapshot().delivery.nodes
    assert nodes[0].node_id != nodes[1].node_id
    assert nodes[0].refs[0].ref_id == nodes[1].refs[0].ref_id == catalyst.species_id


def test_operation_vocabulary_has_no_delete(tmp_path):
    api, _db, _store, _engine = _new_engine(tmp_path, "no-delete")

    with pytest.raises(ValueError):
        api["GraphOperation"](op="delete_node", graph="delivery", data={"node_id": "n1"})


def test_supervisor_is_read_only_on_delivery_but_may_link(tmp_path):
    """Supervisor 拥有 process DAG；delivery 任何写操作 actor_forbidden；add_link 例外。"""
    api, _db, store, engine = _new_engine(tmp_path, "supervisor-delivery-readonly")
    seeded = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api, "add_node", "delivery",
                    node_id="r", node_type="intermediate_occurrence", label="R",
                    payload={"evidence_level": "proposed"},
                ),
                _op(
                    api, "add_node", "process",
                    node_id="ts-search", node_type="calculation", label="TS search",
                    payload={"status": "ready"},
                ),
            ],
        )
    )
    assert seeded.accepted

    forbidden_ops = [
        _op(api, "add_node", "delivery", node_id="p",
            node_type="intermediate_occurrence", label="P",
            payload={"evidence_level": "proposed"}),
        _op(api, "update_node", "delivery", node_id="r",
            changes={"evidence_level": "rejected", "reason": "stale"}),
        _op(api, "update_node", "delivery", node_id="r", changes={"label": "X"}),
    ]
    for op in forbidden_ops:
        result = engine.apply_batch(_batch(api, store, [op], actor="supervisor"))
        assert not result.accepted
        assert result.rejection_code == "actor_forbidden"

    linked = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api, "add_link", "process",
                    link_id="lk-1",
                    process_node_id="ts-search",
                    delivery_element_type="node",
                    delivery_element_id="r",
                    payload={"relation": "produces_evidence_for"},
                )
            ],
            actor="supervisor",
        )
    )
    assert linked.accepted
    # process 写权限保留
    reprioritized = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "update_node", "process", node_id="ts-search",
                 changes={"priority": 42})],
            actor="supervisor",
        )
    )
    assert reprioritized.accepted


def test_coordinator_is_read_only_on_process_but_designs_delivery(tmp_path):
    """Coordinator（actor=agent）设计机理 DAG；process 任何写操作 actor_forbidden。"""
    api, _db, store, engine = _new_engine(tmp_path, "agent-process-readonly")
    seeded = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api, "add_node", "process",
                    node_id="mapping", node_type="calculation", label="mapping",
                    payload={"status": "ready"},
                )
            ],
        )
    )
    assert seeded.accepted

    forbidden_ops = [
        _op(api, "add_node", "process", node_id="w", node_type="calculation",
            label="W", payload={"status": "proposed"}),
        _op(api, "update_node", "process", node_id="mapping",
            changes={"priority": 99}),
        _op(api, "add_edge", "process", edge_id="dep",
            source_node_id="mapping", target_node_id="mapping",
            edge_type="dependency"),
    ]
    for op in forbidden_ops:
        result = engine.apply_batch(_batch(api, store, [op], actor="agent"))
        assert not result.accepted
        assert result.rejection_code == "actor_forbidden"

    designed = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(api, "add_node", "delivery", node_id="r",
                    node_type="intermediate_occurrence", label="C=COCC=C",
                    payload={"evidence_level": "proposed"}),
                _op(api, "add_node", "delivery", node_id="p",
                    node_type="intermediate_occurrence", label="C=CCCC=O",
                    payload={"evidence_level": "proposed"}),
                _op(api, "add_edge", "delivery", edge_id="chair",
                    source_node_id="r", target_node_id="p",
                    edge_type="elementary_step", label="chair [3,3]",
                    payload={"evidence_level": "proposed"}),
            ],
            actor="agent",
        )
    )
    assert designed.accepted
    disposed = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "update_edge", "delivery", edge_id="chair",
                 changes={"evidence_level": "inconclusive",
                          "reason": "IRC endpoints do not match"})],
            actor="agent",
        )
    )
    assert disposed.accepted
