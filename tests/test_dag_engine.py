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


def test_delivery_only_batch_ignores_stale_process_revision(tmp_path):
    """delivery-only 批次不校验 process base。

    harness 观察每次工具调用都会抬高 process revision；若要求 delivery-only
    批次携带最新 process 版本，Coordinator 的机理变更永远无法通过（线上复现：
    mutate 连续 stale 被拒，delivery_updated 从未触发，Supervisor 没有激活）。
    """
    api, _db, store, engine = _new_engine(tmp_path, "stale-per-graph")
    bumped = engine.apply_batch(
        _batch(
            api,
            store,
            [_op(api, "add_node", "process", node_id="w1", node_type="work", label="W1")],
        )
    )
    assert bumped.accepted

    # 旧 view 拿到的版本（process 已过时）也能提交 delivery-only 批次
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
            base_revisions={"process": 0, "delivery": 0},
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
                    "process",
                    node_id="root",
                    node_type="calculation",
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
        api["parse_graph_operation"](
            {"op": "delete_node", "graph": "delivery", "data": {"node_id": "n1"}}
        )


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


def test_remove_edge_open_with_rationale_and_supervisor_gate(tmp_path):
    """remove_edge 新规则：两张图都可删、不限端点状态，但必须带 rationale；
    agent 对 process 图的删边请求被记录并转交 Supervisor 复核。"""
    api, _db, store, engine = _new_engine(tmp_path, "remove-edge")
    seeded = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(api, "add_node", "process", node_id="a", node_type="calculation",
                    label="A", payload={"status": "proposed"}),
                _op(api, "add_node", "process", node_id="b", node_type="calculation",
                    label="B", payload={"status": "ready"}),
                _op(api, "add_node", "process", node_id="c", node_type="calculation",
                    label="C", payload={"status": "running"}),
                _op(api, "add_edge", "process", edge_id="ab",
                    source_node_id="a", target_node_id="b", edge_type="dependency"),
                _op(api, "add_edge", "process", edge_id="cb",
                    source_node_id="c", target_node_id="b", edge_type="dependency"),
                _op(api, "add_node", "delivery", node_id="r",
                    node_type="intermediate_occurrence", label="R",
                    payload={"evidence_level": "proposed"}),
                _op(api, "add_node", "delivery", node_id="p",
                    node_type="intermediate_occurrence", label="P",
                    payload={"evidence_level": "proposed"}),
                _op(api, "add_edge", "delivery", edge_id="step",
                    source_node_id="r", target_node_id="p",
                    edge_type="elementary_step"),
            ],
        )
    )
    assert seeded.accepted

    # 空 rationale 的删边批次：拒绝
    no_reason = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "process", edge_id="ab")],
               actor="supervisor", rationale="  ")
    )
    assert not no_reason.accepted
    assert no_reason.rejection_code == "rationale_required"

    # supervisor 可删未执行依赖（带理由）
    removed = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "process", edge_id="ab")],
               actor="supervisor", rationale="B 不再依赖 A 的映射结果")
    )
    assert removed.accepted
    snapshot = engine.snapshot()
    assert "ab" not in {edge.edge_id for edge in snapshot.process.edges}

    # 端点已 running 的依赖也可删（删除留在变更日志里供审计）
    removed_running = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "process", edge_id="cb")],
               actor="supervisor", rationale="C 已改为直接喂给 B，依赖过时")
    )
    assert removed_running.accepted
    assert "cb" not in {edge.edge_id for edge in engine.snapshot().process.edges}

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

    # agent 对 process 图的删边请求：记录并转交 Supervisor
    forwarded = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "process", edge_id="ab")],
               actor="agent", rationale="A 的结果已经手工并入 B")
    )
    assert not forwarded.accepted
    assert forwarded.rejection_code == "edge_removal_requires_supervisor"

    # 不存在的边
    missing = engine.apply_batch(
        _batch(api, store, [_op(api, "remove_edge", "process", edge_id="nope")],
               actor="supervisor", rationale="清理")
    )
    assert not missing.accepted
    assert missing.rejection_code == "missing_target"


def test_agent_manages_only_own_assigned_process_nodes(tmp_path):
    """子 agent 可回报指派给自己的 process 节点（状态/备注/挂证据），
    不能动别人的节点，也不能写调度字段。"""
    api, _db, store, engine = _new_engine(tmp_path, "assignee-self-service")
    seeded = engine.apply_batch(
        _batch(
            api,
            store,
            [
                _op(api, "add_node", "process", node_id="mine", node_type="calculation",
                    label="TS opt", payload={"status": "ready", "assignee": "a-4"}),
                _op(api, "add_node", "process", node_id="theirs", node_type="calculation",
                    label="IRC", payload={"status": "ready", "assignee": "a-5"}),
            ],
            actor="supervisor",
        )
    )
    assert seeded.accepted

    own = engine.apply_batch(
        _batch(api, store, [
            _op(api, "update_node", "process", node_id="mine",
                changes={"status": "succeeded", "reason": "opt converged"}),
        ], actor="agent", actor_id="a-4")
    )
    assert own.accepted

    forbidden_field = engine.apply_batch(
        _batch(api, store, [
            _op(api, "update_node", "process", node_id="mine",
                changes={"priority": 99}),
        ], actor="agent", actor_id="a-4")
    )
    assert not forbidden_field.accepted
    assert forbidden_field.rejection_code == "actor_forbidden"

    not_mine = engine.apply_batch(
        _batch(api, store, [
            _op(api, "update_node", "process", node_id="theirs",
                changes={"status": "failed", "reason": "x"}),
        ], actor="agent", actor_id="a-4")
    )
    assert not not_mine.accepted
    assert not_mine.rejection_code == "actor_forbidden"

    structure = engine.apply_batch(
        _batch(api, store, [
            _op(api, "add_node", "process", node_id="sneak", node_type="calculation",
                label="X", payload={"status": "proposed"}),
        ], actor="agent", actor_id="a-4")
    )
    assert not structure.accepted
    assert structure.rejection_code == "actor_forbidden"


def test_process_status_out_of_vocabulary_rejected_with_wordlist(tmp_path):
    """回归：Supervisor 写 status="pending" 的 planned 节点既不进 frontier 也不进
    blockers，从排产视野消失（executor 只能自由发挥）。词表由类型系统把守：
    add 路径 schema Literal 直接拒绝（不再做同义词归一化，迁就错误拼写只会让
    它继续扩散）；update 路径引擎拒绝并在 reason 里报出词表，让模型一步自纠。"""
    from pydantic import ValidationError

    api, _db, store, engine = _new_engine(tmp_path, "status-vocab")

    # add 路径：词表外的 status 在构造节点时被 schema 拒绝
    with pytest.raises(ValidationError):
        api["PlannedNode"](node_id="w1", label="optfreq", status="pending")

    added = engine.apply_batch(
        _batch(api, store, [
            _op(api, "add_node", "process", node_id="w1", node_type="calculation",
                label="optfreq", payload={"status": "proposed"}),
        ], actor="supervisor")
    )
    assert added.accepted
    node = engine.snapshot().process.nodes[0]
    assert node.status == "proposed"

    updated = engine.apply_batch(
        _batch(api, store, [
            _op(api, "update_node", "process", node_id="w1",
                changes={"status": "succeeded"}),
        ], actor="supervisor")
    )
    assert updated.accepted
    node = engine.snapshot().process.nodes[0]
    assert node.status == "succeeded"

    rejected = engine.apply_batch(
        _batch(api, store, [
            _op(api, "update_node", "process", node_id="w1",
                changes={"status": "kind-of-done"}),
        ], actor="supervisor")
    )
    assert not rejected.accepted
    assert rejected.rejection_code == "invalid_status"
    assert "proposed" in (rejected.rejection_reason or "")
    node = engine.snapshot().process.nodes[0]
    assert node.status == "succeeded"


def test_model_update_rejection_names_offending_fields(tmp_path):
    """回归：changes 带白名单外字段（如 note）被整批拒时，reason 必须点名违规
    字段并给出白名单——否则模型只能盲目重试烧掉轮次预算。"""
    api, _db, store, engine = _new_engine(tmp_path, "mutable-fields")

    engine.apply_batch(
        _batch(api, store, [
            _op(api, "add_node", "process", node_id="w1", node_type="calculation",
                label="optfreq", payload={"status": "proposed"}),
        ], actor="supervisor")
    )
    rejected = engine.apply_batch(
        _batch(api, store, [
            _op(api, "update_node", "process", node_id="w1",
                changes={"status": "ready", "note": "解锁为可执行"}),
        ], actor="supervisor")
    )

    assert not rejected.accepted
    assert rejected.rejection_code == "actor_forbidden"
    reason = rejected.rejection_reason or ""
    assert "note" in reason
    assert "annotations" in reason

