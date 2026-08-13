"""实质性操作前的 DAG 门槛测试。"""

from __future__ import annotations

import pytest

from cloudra.dag.substantive_gate import (
    EARLY_RESEARCH_SUBAGENT_IDS,
    is_early_research_subagent_call,
    is_substantive_tool,
)
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store


def _db(tmp_path, conversation_id, mode):
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    session_store.create_session_record(
        db,
        session_id="s1",
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="mechanism",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode=mode,
    )
    return db


def test_smiles_tools_are_not_substantive():
    for name in (
        "smiles_to_mol",
        "image_to_smiles",
        "name_to_structure",
        "molecule_drawer",
        "reaction_mapping",
        "format_converter",
        "dag_graph",
        "getskill",
        "text_reader",
    ):
        assert not is_substantive_tool(name)


def test_substantive_tools_listed():
    for name in (
        "SubAgentLauncher",
        "text_writer",
        "submit_compute_job",
        "gaussian_log_parser",
        "gjf_writer",
    ):
        assert is_substantive_tool(name)


def test_bashtools_substantive_only_for_write_or_compute():
    assert not is_substantive_tool("bashtools", {"command": "ls -la"})
    assert is_substantive_tool("bashtools", {"command": "echo hi > out.txt"})
    assert is_substantive_tool("bashtools", {"command": "g16 job.gjf"})


def test_early_research_subagent_ids_are_explorer_and_researcher():
    assert EARLY_RESEARCH_SUBAGENT_IDS == frozenset({"a-1", "a-3"})
    assert is_early_research_subagent_call(
        "SubAgentLauncher", {"agent_id": "a-1"}
    )
    assert is_early_research_subagent_call(
        "SubAgentSwarm", {"agent_id": "a-3"}
    )
    assert not is_early_research_subagent_call(
        "SubAgentLauncher", {"agent_id": "a-4"}
    )
    assert not is_early_research_subagent_call("text_writer", {})


@pytest.mark.asyncio
async def test_guided_blocks_substantive_until_graph_has_nodes(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import OrchestrationMode

    db = _db(tmp_path, "gate-guided", "dag_guided")
    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED)
    await controller.initialize()

    gate = await controller.check_substantive_gate("SubAgentLauncher", {})
    assert gate is not None
    assert gate[0] == "block"
    assert "DAG gate" in gate[1]

    assert await controller.check_substantive_gate(
        "smiles_to_mol", {"smiles": "CCO"}
    ) is None


@pytest.mark.asyncio
async def test_guided_template_allows_researcher_blocks_edit_and_dft(tmp_path):
    """模板骨架 alone：可派 explorer/researcher；写文件与计算子 Agent 仍拦。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        DependencyEdge,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        OrchestrationMode,
        PlannedNode,
    )
    from cloudra.dag.store import DagStore
    from cloudra.tools.Plantool.dag_graph import (
        _TEMPLATE_DELIVERY_NODES,
        _TEMPLATE_PROCESS_EDGES,
        _TEMPLATE_PROCESS_NODES,
    )

    db = _db(tmp_path, "gate-template", "dag_guided")
    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED)
    await controller.initialize()

    store = DagStore(db)
    engine = DagEngine(store)
    operations = []
    for node_id, label in _TEMPLATE_PROCESS_NODES:
        operations.append(
            AddNode(
                op="add_node",
                graph="process",
                node=PlannedNode(node_id=node_id, label=label),
            )
        )
    for edge_id, source, target in _TEMPLATE_PROCESS_EDGES:
        operations.append(
            AddEdge(
                op="add_edge",
                graph="process",
                edge=DependencyEdge(
                    edge_id=edge_id,
                    source_node_id=source,
                    target_node_id=target,
                ),
            )
        )
    for node_id, role, label in _TEMPLATE_DELIVERY_NODES:
        operations.append(
            AddNode(
                op="add_node",
                graph="delivery",
                node=OccurrenceNode(node_id=node_id, label=label, role=role),
            )
        )
    result = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="dag-template",
            base_revisions=store.load_bundle().revisions,
            operations=operations,
            rationale="seed template",
        )
    )
    assert result.accepted
    assert await controller.has_graph_content()

    assert (
        await controller.check_substantive_gate(
            "SubAgentLauncher", {"agent_id": "a-3"}
        )
        is None
    )
    assert (
        await controller.check_substantive_gate(
            "SubAgentSwarm", {"agent_id": "a-1"}
        )
        is None
    )

    for tool, args in (
        ("text_writer", {}),
        ("edit_file", {}),
        ("submit_compute_job", {}),
        ("SubAgentLauncher", {"agent_id": "a-4"}),
        ("SubAgentSwarm", {"agent_id": "a-6"}),
    ):
        gate = await controller.check_substantive_gate(tool, args)
        assert gate is not None, tool
        assert gate[0] == "block", tool
        assert "mechanism" in gate[1] or "planned" in gate[1] or "Supervisor" in gate[1]


@pytest.mark.asyncio
async def test_guided_allows_after_mechanism_and_supervisor_plan(tmp_path):
    """delivery 实质机理 + process 非模板排产 → 写文件与计算子 Agent 放行。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ElementaryStepEdge,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        OrchestrationMode,
        PlannedNode,
    )
    from cloudra.dag.store import DagStore

    db = _db(tmp_path, "gate-ready", "dag_guided")
    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED)
    await controller.initialize()

    store = DagStore(db)
    engine = DagEngine(store)
    result = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="seed",
            base_revisions=store.load_bundle().revisions,
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="occ_r",
                        label="reactant EtOH",
                        role="reactant",
                        smiles="CCO",
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="occ_p",
                        label="product AcH",
                        role="product",
                        smiles="CC=O",
                    ),
                ),
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(
                        edge_id="e1",
                        source_node_id="occ_r",
                        target_node_id="occ_p",
                        label="oxidation",
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="p_opt_r",
                        label="optimize reactant",
                        tool_name="submit_compute_job",
                        assignee="a-4",
                    ),
                ),
            ],
            rationale="mechanism + supervisor plan",
        )
    )
    assert result.accepted

    assert await controller.check_substantive_gate("text_writer", {}) is None
    assert (
        await controller.check_substantive_gate(
            "SubAgentLauncher", {"agent_id": "a-4"}
        )
        is None
    )


@pytest.mark.asyncio
async def test_delivery_alone_still_blocks_edit(tmp_path):
    """仅有实质 delivery、尚无 Supervisor 排产时，写文件仍拦。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddNode,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        OrchestrationMode,
    )
    from cloudra.dag.store import DagStore

    db = _db(tmp_path, "gate-delivery-only", "dag_guided")
    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED)
    await controller.initialize()

    store = DagStore(db)
    engine = DagEngine(store)
    result = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="seed",
            base_revisions=store.load_bundle().revisions,
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="n1", label="seed", smiles="CCO"
                    ),
                )
            ],
            rationale="delivery only",
        )
    )
    assert result.accepted
    assert await controller.has_graph_content()
    gate = await controller.check_substantive_gate("text_writer", {})
    assert gate is not None
    assert gate[0] == "block"


@pytest.mark.asyncio
async def test_record_warns_then_allows(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import OrchestrationMode

    db = _db(tmp_path, "gate-record", "dag_record")
    controller = DagController(db, "s1", OrchestrationMode.DAG_RECORD)
    await controller.initialize()

    gate = await controller.check_substantive_gate("submit_compute_job", {})
    assert gate is not None
    assert gate[0] == "warn"


@pytest.mark.asyncio
async def test_standard_never_gates(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import OrchestrationMode

    db = _db(tmp_path, "gate-std", "standard")
    controller = DagController(db, "s1", OrchestrationMode.STANDARD)
    await controller.initialize()
    assert await controller.check_substantive_gate("SubAgentLauncher", {}) is None
