import pytest

from cloudra.persistence.database import ConversationDB


def _load_engine_api():
    try:
        from cloudra.dag.engine import DagEngine
        from cloudra.dag.models import (
            AddEdge,
            AddLink,
            AddNode,
            AttachRef,
            CoverageContract,
            CoverageWaiver,
            DependencyEdge,
            ElementaryStepEdge,
            GraphActor,
            GraphRef,
            MutationBatch,
            ObservedNode,
            OccurrenceNode,
            PlannedNode,
            RemoveEdge,
            SetCoverageContract,
            UpdateEdge,
            UpdateNode,
            WaiveGate,
            parse_graph_operation,
        )
        from cloudra.dag.store import DagStore
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"DAG mutation API is missing: {exc}")
    return {
        "DagEngine": DagEngine,
        "DagStore": DagStore,
        "GraphActor": GraphActor,
        "GraphRef": GraphRef,
        "MutationBatch": MutationBatch,
        "AddNode": AddNode,
        "AddEdge": AddEdge,
        "RemoveEdge": RemoveEdge,
        "UpdateNode": UpdateNode,
        "UpdateEdge": UpdateEdge,
        "AttachRef": AttachRef,
        "AddLink": AddLink,
        "SetCoverageContract": SetCoverageContract,
        "WaiveGate": WaiveGate,
        "PlannedNode": PlannedNode,
        "ObservedNode": ObservedNode,
        "OccurrenceNode": OccurrenceNode,
        "DependencyEdge": DependencyEdge,
        "ElementaryStepEdge": ElementaryStepEdge,
        "CoverageContract": CoverageContract,
        "CoverageWaiver": CoverageWaiver,
        "parse_graph_operation": parse_graph_operation,
    }


def _new_engine(tmp_path, conversation_id="dag-engine"):
    api = _load_engine_api()
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    store = api["DagStore"](db)
    store.ensure_bundle("s1")
    return api, db, store, api["DagEngine"](store)


_PROCESS_NODE_TYPES = {"work", "calculation", "workflow", "planned_tool_call", "planned"}
_DELIVERY_NODE_TYPES = {"occurrence", "intermediate_occurrence", "deliverable"}


def _element(cls, kwargs):
    """旧 payload 自由字典 → 显式字段 kwargs；非字段键归入 metadata。"""
    kwargs = dict(kwargs)
    payload = kwargs.pop("payload", None) or {}
    merged = {**payload, **kwargs}
    fields = set(cls.model_fields)
    known = {key: value for key, value in merged.items() if key in fields}
    extras = {key: value for key, value in merged.items() if key not in fields}
    if extras:
        known["metadata"] = {**extras, **known.get("metadata", {})}
    return cls(**known)


def _node(api, node_type, **kwargs):
    if node_type in _PROCESS_NODE_TYPES:
        cls = api["PlannedNode"]
    elif node_type == "observed_tool_call":
        cls = api["ObservedNode"]
    elif node_type in _DELIVERY_NODE_TYPES:
        cls = api["OccurrenceNode"]
    else:
        raise ValueError(f"unknown node_type {node_type!r}")
    return _element(cls, kwargs)


def _edge(api, edge_type, **kwargs):
    if edge_type in ("depends_on", "dependency"):
        cls = api["DependencyEdge"]
    elif edge_type == "elementary_step":
        cls = api["ElementaryStepEdge"]
    else:
        raise ValueError(f"unknown edge_type {edge_type!r}")
    return _element(cls, kwargs)


def _op(api, name, graph=None, **data):
    if name == "add_node":
        data = dict(data)
        node_type = data.pop("node_type")
        return api["AddNode"](op="add_node", graph=graph, node=_node(api, node_type, **data))
    if name == "add_edge":
        data = dict(data)
        edge_type = data.pop("edge_type")
        return api["AddEdge"](op="add_edge", graph=graph, edge=_edge(api, edge_type, **data))
    if name == "remove_edge":
        return api["RemoveEdge"](op="remove_edge", graph=graph, edge_id=data["edge_id"])
    if name == "update_node":
        return api["UpdateNode"](
            op="update_node", graph=graph, node_id=data["node_id"], changes=data["changes"]
        )
    if name == "update_edge":
        return api["UpdateEdge"](
            op="update_edge", graph=graph, edge_id=data["edge_id"], changes=data["changes"]
        )
    if name == "attach_ref":
        return api["AttachRef"](
            op="attach_ref",
            graph=graph,
            target_type=data["target_type"],
            target_id=data["target_id"],
            ref=api["GraphRef"](**data["ref"]),
            evidence_role=data.get("evidence_role"),
        )
    if name == "add_link":
        return api["AddLink"](op="add_link", graph=None, **data)
    if name == "set_coverage_contract":
        contract = data["contract"]
        if isinstance(contract, dict):
            contract = api["CoverageContract"](**contract)
        return api["SetCoverageContract"](
            op="set_coverage_contract", graph=None, contract=contract
        )
    if name == "waive_gate":
        waiver = data["waiver"]
        if isinstance(waiver, dict):
            waiver = api["CoverageWaiver"](**waiver)
        return api["WaiveGate"](op="waive_gate", graph=None, waiver=waiver)
    raise ValueError(f"unknown op {name!r}")


def _batch(api, store, operations, *, actor="harness", base_revisions=None,
           rationale="focused test", actor_id=None):
    return api["MutationBatch"](
        session_id="s1",
        actor=api["GraphActor"](actor),
        actor_id=actor_id or f"test-{actor}",
        base_revisions=base_revisions or store.load_bundle().revisions,
        operations=operations,
        rationale=rationale,
    )


def test_cycle_rejects_entire_batch(tmp_path):
    api, _db, store, engine = _new_engine(tmp_path, "cycle")
    result = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(api, "add_node", "delivery", node_id="a", node_type="occurrence", label="A"),
                _op(api, "add_node", "delivery", node_id="b", node_type="occurrence", label="B"),
                _op(
                    api,
                    "add_edge",
                    "delivery",
                    edge_id="ab",
                    source_node_id="a",
                    target_node_id="b",
                    edge_type="elementary_step",
                ),
                _op(
                    api,
                    "add_edge",
                    "delivery",
                    edge_id="ba",
                    source_node_id="b",
                    target_node_id="a",
                    edge_type="elementary_step",
                ),
            ],
        )
    )

    assert not result.accepted
    assert result.rejection_code == "cycle"
    assert engine.snapshot().delivery.nodes == []
    assert engine.snapshot().delivery.edges == []


def test_stale_revision_rejects_without_last_write_wins(tmp_path):
    api, _db, store, engine = _new_engine(tmp_path, "stale")
    stale = dict(store.load_bundle().revisions)
    accepted = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "add_node", "delivery", node_id="first", node_type="occurrence", label="first")],
        )
    )
    rejected = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "add_node", "delivery", node_id="second", node_type="occurrence", label="second")],
            base_revisions=stale,
        )
    )

    assert accepted.accepted
    assert not rejected.accepted
    assert rejected.rejection_code == "stale_revision"
    assert [node.node_id for node in engine.snapshot().delivery.nodes] == ["first"]


def test_delivery_only_batch_ignores_stale_process_revision(tmp_path):
    """delivery-only 批次不校验 process base；process 写在 Phase 4 后整体被拒。"""
    api, _db, store, engine = _new_engine(tmp_path, "stale-per-graph")
    process_write = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "add_node", "process", node_id="w1", node_type="work", label="W1")],
        )
    )
    assert not process_write.accepted
    assert process_write.rejection_code == "process_graph_removed"

    bumped = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "add_node", "delivery", node_id="int0", node_type="occurrence", label="INT0")],
            actor="agent",
        )
    )
    assert bumped.accepted

    # 旧 view 拿到的版本（process 键过时/缺失）也能提交 delivery-only 批次
    result = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "delivery",
                    node_id="int1",
                    node_type="intermediate_occurrence",
                    label="INT1",
                )
            ],
            actor="agent",
            base_revisions={"process": 0, "delivery": bumped.revisions["delivery"]},
        )
    )
    assert result.accepted

    # delivery-only 批次也允许直接省略 process 键
    result2 = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "delivery",
                    node_id="int2",
                    node_type="intermediate_occurrence",
                    label="INT2",
                )
            ],
            actor="agent",
            base_revisions={"delivery": result.revisions["delivery"]},
        )
    )
    assert result2.accepted


def test_stale_base_on_touched_graph_still_rejected(tmp_path):
    """按图校验不等于放松：触及 delivery 的批次仍需最新 delivery base。"""
    api, _db, store, engine = _new_engine(tmp_path, "stale-delivery")
    first = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "delivery",
                    node_id="int1",
                    node_type="intermediate_occurrence",
                    label="INT1",
                )
            ],
            actor="agent",
        )
    )
    assert first.accepted

    rejected = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(
                    api,
                    "add_node",
                    "delivery",
                    node_id="int2",
                    node_type="intermediate_occurrence",
                    label="INT2",
                )
            ],
            actor="agent",
            base_revisions={"delivery": 0},
        )
    )
    assert not rejected.accepted
    assert rejected.rejection_code == "stale_revision"


@pytest.mark.parametrize(
    ("operations", "code"),
    [
        (
            [
                ("add_node", "delivery", {"node_id": "a", "node_type": "occurrence", "label": "A"}),
                ("add_node", "delivery", {"node_id": "a", "node_type": "occurrence", "label": "again"}),
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
            [
                _op(
                    api,
                    "waive_gate",
                    waiver={
                        "gate_code": "endpoint",
                        "target_type": "graph",
                        "target_id": "delivery",
                        "user_id": "test-user",
                        "session_id": "s1",
                        "rationale": "looks fine",
                    },
                )
            ],
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
                    "delivery",
                    node_id="root",
                    node_type="occurrence",
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
    assert edge.evidence_level == "proposed"

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
                    "delivery",
                    node_id="mapping",
                    node_type="occurrence",
                    label="mapping",
                    refs=[missing.model_dump()],
                )
            ],
        )
    )

    assert not result.accepted
    assert result.rejection_code == "invalid_reference"
    assert engine.snapshot().delivery.nodes == []


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
                    "delivery",
                    node_id="mapping",
                    node_type="occurrence",
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
                    "delivery",
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
    assert engine.snapshot().delivery.nodes[0].refs == [evidence]


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
        api["parse_graph_operation"](
            {"op": "delete_node", "graph": "delivery", "data": {"node_id": "n1"}}
        )


def test_supervisor_is_read_only_on_delivery_and_links_are_gone(tmp_path):
    """Supervisor 对 delivery 只读；add_link 与 process 写随 process 图一并删除。"""
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
                    api, "add_link", None,
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
    assert not linked.accepted
    assert linked.rejection_code == "process_graph_removed"

    # process 写已整体移除
    process_write = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "add_node", "process", node_id="ts-search",
                 node_type="calculation", label="TS search",
                 payload={"status": "ready"})],
            actor="supervisor",
        )
    )
    assert not process_write.accepted
    assert process_write.rejection_code == "process_graph_removed"


def test_coordinator_designs_delivery_but_process_writes_are_rejected(tmp_path):
    """Coordinator（actor=agent）设计机理 DAG；process 任何写操作
    process_graph_removed。"""
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
    assert not seeded.accepted
    assert seeded.rejection_code == "process_graph_removed"

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
        assert result.rejection_code == "process_graph_removed"

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


def test_remove_edge_open_with_rationale(tmp_path):
    """remove_edge：不限端点状态，但必须带 rationale；supervisor 对 delivery
    只读；设计者 agent 带理由可删；process 边已随图删除。"""
    api, _db, store, engine = _new_engine(tmp_path, "remove-edge")
    seeded = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(api, "add_node", "delivery", node_id="r",
                    node_type="intermediate_occurrence", label="R",
                    payload={"evidence_level": "proposed"}),
                _op(api, "add_node", "delivery", node_id="p",
                    node_type="intermediate_occurrence", label="P",
                    payload={"evidence_level": "proposed"}),
                _op(api, "add_node", "delivery", node_id="q",
                    node_type="intermediate_occurrence", label="Q",
                    payload={"evidence_level": "proposed"}),
                _op(api, "add_edge", "delivery", edge_id="step",
                    source_node_id="r", target_node_id="p",
                    edge_type="elementary_step"),
                _op(api, "add_edge", "delivery", edge_id="side",
                    source_node_id="q", target_node_id="p",
                    edge_type="elementary_step"),
            ],
        )
    )
    assert seeded.accepted

    # 空 rationale 的删边批次：拒绝
    no_reason = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "delivery", edge_id="side")],
               actor="agent", rationale="  ")
    )
    assert not no_reason.accepted
    assert no_reason.rejection_code == "rationale_required"

    # delivery 边：supervisor 只读被拒；设计者 agent 带理由可删
    sup_blocked = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "delivery", edge_id="step")],
               actor="supervisor", rationale="假设作废")
    )
    assert not sup_blocked.accepted
    assert sup_blocked.rejection_code == "actor_forbidden"
    designer_removed = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "delivery", edge_id="step")],
               actor="agent", rationale="该基元步假设被文献否定，改走另一通道")
    )
    assert designer_removed.accepted
    assert "step" not in {edge.edge_id for edge in engine.snapshot().delivery.edges}

    # process 删边：随 process 图一并移除
    process_edge = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "process", edge_id="side")],
               actor="agent", rationale="cleanup")
    )
    assert not process_edge.accepted
    assert process_edge.rejection_code == "process_graph_removed"

    # 不存在的边
    missing = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "delivery", edge_id="nope")],
               actor="agent", rationale="清理")
    )
    assert not missing.accepted
    assert missing.rejection_code == "missing_target"


def test_process_writes_are_rejected_for_every_actor(tmp_path):
    """Phase 4：process 图写路径整体移除——任何 actor 的 process 写都拒。"""
    api, _db, store, engine = _new_engine(tmp_path, "process-gone")
    for actor in ("harness", "supervisor", "agent"):
        result = engine.apply_batch(
            _batch(api, store, [
                _op(api, "add_node", "process", node_id=f"w-{actor}",
                    node_type="calculation", label="X", payload={"status": "proposed"}),
            ], actor=actor)
        )
        assert not result.accepted
        assert result.rejection_code == "process_graph_removed"
    assert engine.snapshot().process.nodes == []
def test_model_update_rejection_names_offending_fields(tmp_path):
    """回归：changes 带白名单外字段（如 note）被整批拒时，reason 必须点名违规
    字段并给出白名单——否则模型只能盲目重试烧掉轮次预算。"""
    api, _db, store, engine = _new_engine(tmp_path, "mutable-fields")

    engine.apply_batch(
        _batch(api, store, [
            _op(api, "add_node", "delivery", node_id="w1", node_type="occurrence",
                label="int1"),
        ], actor="agent")
    )
    rejected = engine.apply_batch(
        _batch(api, store, [
            _op(api, "update_node", "delivery", node_id="w1",
                changes={"label": "renamed", "note": "顺手记一笔"}),
        ], actor="agent")
    )

    assert not rejected.accepted
    assert rejected.rejection_code == "actor_forbidden"
    reason = rejected.rejection_reason or ""
    assert "note" in reason
    assert "annotations" in reason


def test_model_cannot_self_certify_stage_statuses(tmp_path):
    """阶段契约守卫：模型（agent/supervisor）只能声明 pending 阶段；
    supported/skipped/rejected 或带 ref 的阶段只能由 harness 阶段绑定推进。"""
    api, _db, store, engine = _new_engine(tmp_path, "stage-guard")
    from cloudra.dag.models import StageState

    for actor in ("agent", "supervisor"):
        seeded = engine.apply_batch(
            _batch(api, store, [
                _op(api, "add_node", "delivery", node_id=f"r-{actor}",
                    node_type="occurrence", label=f"R-{actor}", role="reactant"),
            ], actor="harness")
        )
        assert seeded.accepted
        rejected = engine.apply_batch(
            _batch(api, store, [
                api["AddNode"](
                    op="add_node",
                    graph="delivery",
                    node=api["OccurrenceNode"](
                        node_id=f"p-{actor}",
                        label=f"P-{actor}",
                        role="product",
                        stages=[StageState(kind="geometry", status="supported")],
                    ),
                ),
            ], actor=actor)
        )
        assert not rejected.accepted
        assert rejected.rejection_code == "actor_forbidden"

    declared = engine.apply_batch(
        _batch(api, store, [
            api["AddNode"](
                op="add_node",
                graph="delivery",
                node=api["OccurrenceNode"](
                    node_id="p-pending",
                    label="P",
                    role="product",
                    stages=[StageState(kind="geometry")],
                ),
            ),
        ], actor="agent")
    )
    assert declared.accepted
    node = next(
        n for n in engine.snapshot().delivery.nodes if n.node_id == "p-pending"
    )
    assert [(s.kind.value, s.status.value) for s in node.stages] == [
        ("geometry", "pending")
    ]


def test_engine_rejects_duplicate_node_name_in_delivery_graph(tmp_path):
    """Task 1: 同批或增量写入相同体系名称时拒绝（精确匹配、去前后空白）。"""
    api, db, store, engine = _new_engine(tmp_path, "dup-node-name")
    from cloudra.dag.models import SpeciesNode

    # 批次内同名
    batch = _batch(
        api, store,
        [
            api["AddNode"](
                op="add_node",
                graph="delivery",
                node=SpeciesNode(node_id="sp1", name="体系状态A"),
            ),
            api["AddNode"](
                op="add_node",
                graph="delivery",
                node=SpeciesNode(node_id="sp2", name=" 体系状态A "),
            ),
        ],
        actor="harness",
    )
    res = engine.apply_batch(batch)
    assert not res.accepted
    assert res.rejection_code in ("duplicate_name", "duplicate_id", "invalid_operation")


def test_engine_rejects_duplicate_step_name_in_delivery_graph(tmp_path):
    """Task 1: 同批或增量写入相同步骤名称时拒绝。"""
    api, db, store, engine = _new_engine(tmp_path, "dup-step-name")
    from cloudra.dag.models import ElementaryStepEdge, SpeciesNode

    batch1 = _batch(
        api, store,
        [
            api["AddNode"](op="add_node", graph="delivery", node=SpeciesNode(node_id="sp1", name="A")),
            api["AddNode"](op="add_node", graph="delivery", node=SpeciesNode(node_id="sp2", name="B")),
            api["AddNode"](op="add_node", graph="delivery", node=SpeciesNode(node_id="sp3", name="C")),
            api["AddEdge"](op="add_edge", graph="delivery", edge=ElementaryStepEdge(edge_id="e1", name="步骤一", source_node_id="sp1", target_node_id="sp2")),
            api["AddEdge"](op="add_edge", graph="delivery", edge=ElementaryStepEdge(edge_id="e2", name="步骤一", source_node_id="sp2", target_node_id="sp3")),
        ],
        actor="harness",
    )
    res = engine.apply_batch(batch1)
    assert not res.accepted
    assert res.rejection_code in ("duplicate_name", "duplicate_id", "invalid_operation")


def test_engine_remove_edge_without_rationale_rejected(tmp_path):
    """Task 1: 删边必须有理由，否则事务拒绝。"""
    api, db, store, engine = _new_engine(tmp_path, "rm-edge-no-rat")
    from cloudra.dag.models import ElementaryStepEdge, SpeciesNode

    # 先加节点和边
    engine.apply_batch(
        _batch(
            api, store,
            [
                api["AddNode"](op="add_node", graph="delivery", node=SpeciesNode(node_id="sp1", name="A")),
                api["AddNode"](op="add_node", graph="delivery", node=SpeciesNode(node_id="sp2", name="B")),
                api["AddEdge"](op="add_edge", graph="delivery", edge=ElementaryStepEdge(edge_id="e1", name="步骤一", source_node_id="sp1", target_node_id="sp2")),
            ],
            actor="harness",
        )
    )

    # 空 rationale 删边
    rm_batch = _batch(
        api, store,
        [api["RemoveEdge"](op="remove_edge", graph="delivery", edge_id="e1")],
        actor="agent",
        rationale="",
    )
    res = engine.apply_batch(rm_batch)
    assert not res.accepted
    assert res.rejection_code == "rationale_required"


def test_engine_batch_failure_atomic_rollback(tmp_path):
    """Task 1: 批次中只要有一项失败，整批零部分写入。"""
    api, db, store, engine = _new_engine(tmp_path, "atomic-rollback")
    from cloudra.dag.models import SpeciesNode

    batch = _batch(
        api, store,
        [
            api["AddNode"](op="add_node", graph="delivery", node=SpeciesNode(node_id="sp1", name="有效体系")),
            # 第二项同名导致失败
            api["AddNode"](op="add_node", graph="delivery", node=SpeciesNode(node_id="sp2", name="有效体系")),
        ],
        actor="harness",
    )
    res = engine.apply_batch(batch)
    assert not res.accepted
    snapshot = engine.snapshot()
    assert len(snapshot.delivery.nodes) == 0

