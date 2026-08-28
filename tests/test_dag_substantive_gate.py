"""实质性计算前的 DAG 门槛测试（Phase 3：唯一门槛 = mechanism_accepted, D4）。"""

from __future__ import annotations

import pytest

from cloudra.dag.substantive_gate import is_compute_entry_tool
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


def _accept_draft(db):
    """直接落一条 accepted 草稿（mechanism_accepted 的唯一判据，D4）。"""
    from cloudra.dag.models import AddNode, MechanismDraft, OccurrenceNode
    from cloudra.dag.store import DagStore

    store = DagStore(db)
    store.ensure_bundle("s1")
    draft = MechanismDraft(
        operations=[
            AddNode(
                op="add_node",
                graph="delivery",
                node=OccurrenceNode(node_id="r", label="R", role="reactant"),
            )
        ],
        rationale="accepted hypothesis",
        state="accepted",
    )
    store.save_draft(draft, actor_id="harness:auto")


def test_compute_entry_vocabulary():
    for name in (
        "submit_compute_job",
        "qm_input_writer",
        "conformer_search",
        "electronic_analysis",
    ):
        assert is_compute_entry_tool(name), name
    # ts_guess 按 mode 区分：计算型 mode 拦截，读日志型放行
    assert is_compute_entry_tool("ts_guess", {"mode": "interpolate"})
    assert is_compute_entry_tool("ts_guess", {"mode": "scan_prepare"})
    assert not is_compute_entry_tool("ts_guess", {"mode": "scan_parse"})
    assert not is_compute_entry_tool("ts_guess", {"mode": "verify"})
    # 计算/写文件型 bash 拦截，只读 bash 放行
    assert is_compute_entry_tool("bashtools", {"command": "g16 job.gjf"})
    assert is_compute_entry_tool("bashtools", {"command": "echo hi > out.txt"})
    assert not is_compute_entry_tool("bashtools", {"command": "ls -la"})
    # 检索/读取/映射/编排面始终放行
    for name in (
        "log_parser",
        "reaction_mapping",
        "text_writer",
        "web_search",
        "text_reader",
        "smiles_to_mol",
        "SubAgentLauncher",
        "dag_view",
        "dag_propose_mechanism",
        "dag_message_supervisor",
    ):
        assert not is_compute_entry_tool(name), name


@pytest.mark.asyncio
async def test_guided_blocks_compute_until_draft_accepted(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import OrchestrationMode

    db = _db(tmp_path, "gate-guided", "dag_guided")
    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED)
    await controller.initialize()

    gate = await controller.check_substantive_gate("submit_compute_job", {})
    assert gate is not None
    assert gate[0] == "block"
    assert "dag_propose_mechanism" in gate[1]
    gate = await controller.check_substantive_gate(
        "ts_guess", {"mode": "scan_prepare"}
    )
    assert gate is not None and gate[0] == "block"

    # 非计算入口不受门槛约束
    assert await controller.check_substantive_gate("text_writer", {}) is None
    assert await controller.check_substantive_gate(
        "smiles_to_mol", {"smiles": "CCO"}
    ) is None

    _accept_draft(db)
    assert await controller.check_substantive_gate("submit_compute_job", {}) is None
    assert (
        await controller.check_substantive_gate("ts_guess", {"mode": "interpolate"})
        is None
    )


@pytest.mark.asyncio
async def test_record_blocks_compute_until_draft_accepted(tmp_path):
    """record 同样硬拦（plan：no compute on an unaccepted mechanism in dag
    modes）；接受的草稿落库后放行。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import OrchestrationMode

    db = _db(tmp_path, "gate-record", "dag_record")
    controller = DagController(db, "s1", OrchestrationMode.DAG_RECORD)
    await controller.initialize()

    gate = await controller.check_substantive_gate("submit_compute_job", {})
    assert gate is not None
    assert gate[0] == "block"
    assert "dag_propose_mechanism" in gate[1]

    _accept_draft(db)
    assert await controller.check_substantive_gate("submit_compute_job", {}) is None


@pytest.mark.asyncio
async def test_standard_never_gates(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import OrchestrationMode

    db = _db(tmp_path, "gate-std", "standard")
    controller = DagController(db, "s1", OrchestrationMode.STANDARD)
    await controller.initialize()
    assert await controller.check_substantive_gate("submit_compute_job", {}) is None
    assert await controller.check_substantive_gate("SubAgentLauncher", {}) is None
