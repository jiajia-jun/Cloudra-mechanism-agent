"""Comprehensive tests for smart fuzzy suggestions and typo correction across Cloudra subsystems."""

from types import SimpleNamespace

import pytest

from cloudra.dag.engine import DagEngine
from cloudra.dag.evidence_inbox import EvidenceInboxMixin
from cloudra.dag.models import (
    AddNode,
    GraphActor,
    GraphKind,
    MutationBatch,
    RemoveNode,
    SpeciesNode,
    UpdateNode,
)
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.persistence.workspace import resolve_existing_tool_path
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.hub_bridge import handle_hub_tool
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command
from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
from cloudra.tools.core.calculation_intent import validate_writer_request
from cloudra.tools.name_hints import hint_unknown_tool


def test_tool_name_fuzzy_correction():
    """Misspelled tool name receives 'Did you mean' suggestion with close registered tool."""
    msg = hint_unknown_tool("dag_propose", available_tools=["dag_propose_mechanism", "get_skill"])
    assert "Did you mean 'dag_propose_mechanism'?" in msg

    msg_skill = hint_unknown_tool("getskills", available_tools=["get_skill", "read", "write"])
    assert "Did you mean 'get_skill'?" in msg_skill


@pytest.mark.asyncio
async def test_agent_hub_role_fuzzy_correction():
    """Calling an unknown/misspelled role via agent_hub suggests the closest canonical role."""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "test_proj"}))
    project = next(iter(core.projects.values()))
    spawn_res = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "test query"},
        )
    )
    agent = spawn_res.data
    call = ToolCall(
        id="t1",
        name="agent_hub",
        arguments={"action": "call", "to": "smallmol", "message": "hello"},
    )
    res = await handle_hub_tool(core, agent, call)
    assert res.is_success is False
    assert "Did you mean 'small_mol'?" in res.summary
    assert "Available roles:" in res.summary


def test_workspace_file_fuzzy_correction(tmp_path, monkeypatch):
    """Missing input file in existing directory suggests nearby matching filenames."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "reaction_ts_opt.out").write_text("opt done", encoding="utf-8")
    monkeypatch.chdir(ws)

    tool = SimpleNamespace(subagent=SimpleNamespace(working_directory=str(ws)))
    with pytest.raises(FileNotFoundError) as exc:
        resolve_existing_tool_path(tool, "reaction_ts_opt.log")
    err_msg = str(exc.value)
    assert "Did you mean:" in err_msg
    assert "reaction_ts_opt.out" in err_msg


def test_dag_engine_missing_target_fuzzy_correction(tmp_path):
    """DagEngine operations with misspelled node/edge IDs suggest existing IDs."""
    db_path = tmp_path / "conv.db"
    db = ConversationDB.from_path(db_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)

    # Add a valid node 'reactant_complex'
    batch_add = MutationBatch(
        session_id="s1",
        actor=GraphActor.AGENT,
        actor_id="coordinator",
        base_revisions=store.load_bundle().revisions,
        rationale="add node",
        operations=[
            AddNode(
                op="add_node",
                graph=GraphKind.DELIVERY,
                node=SpeciesNode(
                    node_id="reactant_complex",
                    name="Reactant Complex",
                    smiles="CC",
                ),
            )
        ],
    )
    res_add = engine.apply_batch(batch_add)
    assert res_add.accepted is True

    # Try updating with typo 'reactant_complx'
    batch_update = MutationBatch(
        session_id="s1",
        actor=GraphActor.AGENT,
        actor_id="coordinator",
        base_revisions=res_add.revisions,
        rationale="update typo",
        operations=[
            UpdateNode(
                op="update_node",
                graph=GraphKind.DELIVERY,
                node_id="reactant_complx",
                changes={"label": "New Label"},
            )
        ],
    )
    res_update = engine.apply_batch(batch_update)
    assert res_update.accepted is False
    assert "Did you mean 'reactant_complex'?" in str(res_update.rejection_reason)
    assert "Available node_ids:" in str(res_update.rejection_reason)

    # Try removing with typo 'reactant_cmplx'
    batch_remove = MutationBatch(
        session_id="s1",
        actor=GraphActor.AGENT,
        actor_id="coordinator",
        base_revisions=res_add.revisions,
        rationale="testing remove typo",
        operations=[
            RemoveNode(
                op="remove_node",
                graph=GraphKind.DELIVERY,
                node_id="reactant_cmplx",
            )
        ],
    )
    res_remove = engine.apply_batch(batch_remove)
    assert res_remove.accepted is False
    assert "Did you mean 'reactant_complex'?" in str(res_remove.rejection_reason)
    assert "Available nodes:" in str(res_remove.rejection_reason)


def test_dag_evidence_inbox_delivery_target_fuzzy_correction(tmp_path):
    """EvidenceInboxMixin._delivery_target suggests closest element IDs on missing target."""
    graph = SimpleNamespace(
        nodes=[
            SimpleNamespace(node_id="intermediate_1"),
            SimpleNamespace(node_id="species_product"),
        ],
        edges=[
            SimpleNamespace(edge_id="step_1_ts"),
        ],
    )
    with pytest.raises(RuntimeError) as exc:
        EvidenceInboxMixin._delivery_target(graph, "intermed_1")
    err = str(exc.value)
    assert "delivery target 'intermed_1' does not exist." in err
    assert "Did you mean 'intermediate_1'?" in err
    assert "Available targets:" in err


@pytest.mark.asyncio
async def test_dag_apply_stage_bind_fuzzy_correction(tmp_path):
    """apply_stage_bind suggests close matches for invalid stage_kind and verdict."""
    class DummyInbox(EvidenceInboxMixin):
        def __init__(self):
            self.enabled = True
        async def initialize(self):
            pass

    inbox = DummyInbox()
    with pytest.raises(RuntimeError) as exc_stage:
        await inbox.apply_stage_bind(
            element_id="e1",
            stage_kind="ts_optim",
            ref=None,
            verdict="agree",
            tool_succeeded=True,
        )
    assert "Did you mean 'ts_opt'?" in str(exc_stage.value)

    with pytest.raises(RuntimeError) as exc_verdict:
        await inbox.apply_stage_bind(
            element_id="e1",
            stage_kind="ts_opt",
            ref=None,
            verdict="agreed",
            tool_succeeded=True,
        )
    assert "Did you mean 'agree'?" in str(exc_verdict.value)


def test_calculation_intent_unknown_native_task_is_advice_not_correction():
    """Unknown native task spelling is preserved rather than guessed into opt."""
    entries = validate_writer_request({"engine": "gaussian", "task_type": [{"optim": None}]})
    entry = next(item for item in entries if item['code'] == 'unknown_task_key')
    assert entry['severity'] == 'warning'
    assert "'optim'" in entry['message'] and 'preserved' in entry['message']
    assert not any("Did you mean" in item['message'] for item in entries)


@pytest.mark.asyncio
async def test_ts_guess_mode_fuzzy_correction():
    """ts_guess tool_call suggests close matches when an unknown mode is requested."""
    tool = TsGuess()
    res = await tool.tool_call(TsGuess_input_schema.model_construct(mode="interpol"), None)
    assert res.is_success is False
    assert "Did you mean 'interpolate'?" in res.message
    assert "Allowed modes:" in res.message
