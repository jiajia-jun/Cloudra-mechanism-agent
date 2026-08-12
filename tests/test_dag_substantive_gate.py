"""实质性操作前的 DAG 门槛测试。"""

from __future__ import annotations

import pytest

from cloudra.dag.substantive_gate import is_substantive_tool
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


@pytest.mark.asyncio
async def test_guided_blocks_substantive_until_graph_has_nodes(tmp_path):
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

    db = _db(tmp_path, "gate-guided", "dag_guided")
    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED)
    await controller.initialize()

    gate = await controller.check_substantive_gate("SubAgentLauncher", {})
    assert gate is not None
    assert gate[0] == "block"
    assert "DAG 门槛" in gate[1]

    assert await controller.check_substantive_gate("smiles_to_mol", {"smiles": "CCO"}) is None

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
                    node=OccurrenceNode(node_id="n1", label="seed"),
                )
            ],
            rationale="seed for gate test",
        )
    )
    assert result.accepted
    assert await controller.has_graph_content()
    assert await controller.check_substantive_gate("text_writer", {}) is None


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
