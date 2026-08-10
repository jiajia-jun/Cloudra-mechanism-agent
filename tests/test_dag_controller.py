from pathlib import Path

import pytest

from cloudra import session_store
from cloudra.database import ConversationDB


def _controller_api():
    try:
        from cloudra.dag.controller import DagController
        from cloudra.dag.models import OrchestrationMode
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"DAG controller API is missing: {exc}")
    return DagController, OrchestrationMode


def _db_with_session(tmp_path, conversation_id, mode):
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


@pytest.mark.asyncio
async def test_standard_controller_does_not_initialize_or_record_graph(tmp_path):
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-standard", "standard")
    controller = DagController(db, "s1", OrchestrationMode.STANDARD)

    await controller.initialize()
    await controller.on_tool_started(
        "tc1", "reaction_mapping", {"reactant_smiles": "C=COCC=C"}
    )
    ref = await controller.on_tool_finished(
        "tc1",
        "reaction_mapping",
        {"reactant_smiles": "C=COCC=C"},
        {"mapping_status": "unique", "heavy_atom_map": [1, 2, 3, 4, 5, 6]},
    )

    assert ref is None
    assert await controller.prompt_projection() == ""
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM dag_evidence").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_record_mode_persists_full_result_before_context_truncation(tmp_path):
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-record", "dag_record")
    controller = DagController(db, "s1", OrchestrationMode.DAG_RECORD)
    await controller.initialize()
    arguments = {"reactant_smiles": "C=COCC=C", "product_smiles": "C=CCCC=O"}
    result = {
        "mapping_status": "unique",
        "heavy_atom_map": [1, 2, 3, 4, 5, 6],
        "large_body": "x" * 2_000,
    }

    await controller.on_tool_started("tc1", "reaction_mapping", arguments)
    ref = await controller.on_tool_finished(
        "tc1", "reaction_mapping", arguments, result
    )

    persisted = controller.store.resolve_evidence(ref)
    node = next(
        node
        for node in controller.engine.snapshot().process.nodes
        if node.payload.get("tool_call_id") == "tc1"
    )
    assert persisted["result"] == result
    assert node.payload["status"] == "succeeded"
    assert ref in node.refs


@pytest.mark.asyncio
async def test_output_file_is_snapshotted_as_artifact_pointer(tmp_path):
    from cloudra.config import get_config

    DagController, OrchestrationMode = _controller_api()
    get_config().data_dir = tmp_path
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    xyz = workspace / "ts.xyz"
    xyz.write_text("1\nTS\nH 0 0 0\n", encoding="utf-8")
    db = _db_with_session(tmp_path, "controller-artifact", "dag_record")
    controller = DagController(
        db,
        "s1",
        OrchestrationMode.DAG_RECORD,
        working_directory=workspace,
        artifact_data_dir=tmp_path,
    )
    await controller.initialize()

    await controller.on_tool_started("tc2", "ts_guess", {"mode": "scan_parse"})
    await controller.on_tool_finished(
        "tc2",
        "ts_guess",
        {"mode": "scan_parse"},
        {"is_success": True, "ts_candidate_path": str(xyz)},
    )

    node = next(
        node
        for node in controller.engine.snapshot().process.nodes
        if node.payload.get("tool_call_id") == "tc2"
    )
    artifact_refs = [ref for ref in node.refs if ref.ref_type == "artifact"]
    assert len(artifact_refs) == 1
    assert artifact_refs[0].content_hash.startswith("sha256:")
    assert all(ref.ref_id != str(xyz) for ref in node.refs)
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_ts_guess_remains_advisory_for_delivery_edge(tmp_path):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, GraphOperation, MutationBatch
    from cloudra.dag.store import DagStore

    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-advisory", "dag_record")
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="seed",
            base_revisions=store.load_bundle().revisions,
            operations=[
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={"node_id": "r", "node_type": "intermediate_occurrence", "label": "R"},
                ),
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={"node_id": "p", "node_type": "intermediate_occurrence", "label": "P"},
                ),
                GraphOperation(
                    op="add_edge",
                    graph="delivery",
                    data={
                        "edge_id": "claisen",
                        "source_node_id": "r",
                        "target_node_id": "p",
                        "edge_type": "elementary_step",
                        "payload": {"evidence_level": "proposed"},
                    },
                ),
                GraphOperation(
                    op="add_node",
                    graph="process",
                    data={
                        "node_id": "guess",
                        "node_type": "calculation",
                        "label": "TS guess",
                        "payload": {
                            "status": "ready",
                            "tool_name": "ts_guess",
                            "delivery_target_type": "edge",
                            "delivery_target_id": "claisen",
                            "evidence_role": "endpoint_direction_check",
                        },
                    },
                ),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", OrchestrationMode.DAG_RECORD)
    await controller.initialize()

    arguments = {"mode": "verify", "strict": True}
    await controller.on_tool_started("tc3", "ts_guess", arguments)
    await controller.on_tool_finished(
        "tc3",
        "ts_guess",
        arguments,
        {"is_success": True, "verdict": "pass", "n_imag": 1},
    )

    edge = controller.engine.snapshot().delivery.edges[0]
    assert edge.payload["evidence_level"] == "proposed"
    assert edge.payload["endpoint_direction_consistent"] is True
    assert edge.refs


def test_endpoint_support_requires_identity_matching_after_direction_check():
    DagController, _OrchestrationMode = _controller_api()
    path_evidence = {
        "evidence_level": "saddle_supported",
        "saddle_supported": True,
        "short_irc_supported": True,
        "endpoint_a_minimum_supported": True,
        "endpoint_direction_consistent": True,
    }

    endpoint_b = DagController._derive_delivery_changes(
        path_evidence,
        "endpoint_b_optimization",
        "gaussian_log_parser",
        {},
        {"normal_termination": True, "imaginary_frequencies": []},
    )

    assert endpoint_b["endpoint_b_minimum_supported"] is True
    assert endpoint_b.get("evidence_level") != "endpoint_supported"

    identity_match = DagController._derive_delivery_changes(
        {**path_evidence, **endpoint_b},
        "endpoint_identity_match",
        "reaction_mapping",
        {},
        {
            "is_success": True,
            "binding_status": "complete",
            "reactant_identity": "match",
            "product_identity": "match",
        },
    )

    assert identity_match["endpoint_identity_matched"] is True
    assert identity_match["evidence_level"] == "endpoint_supported"


@pytest.mark.asyncio
async def test_dag_storage_failure_is_not_silently_downgraded(tmp_path, monkeypatch):
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-fail-closed", "dag_record")
    controller = DagController(db, "s1", OrchestrationMode.DAG_RECORD)
    monkeypatch.setattr(
        controller.store,
        "ensure_bundle",
        lambda _session_id: (_ for _ in ()).throw(RuntimeError("corrupt graph store")),
    )

    with pytest.raises(RuntimeError, match="corrupt graph store"):
        await controller.initialize()


@pytest.mark.asyncio
async def test_react_sends_full_result_to_controller_in_execution_order(
    tmp_path,
    monkeypatch,
):
    from typing import Any

    from cloudra.agent import Follower
    from cloudra.config import get_config
    from cloudra.react import reAct
    from cloudra.tools import ToolEntry
    from cloudra.tools_class import Tool, input_schema, output_schema

    events = []

    class ProbeInput(input_schema):
        text: str

    class ProbeOutput(output_schema):
        is_success: bool = True
        full_body: str

    class ProbeTool(Tool):
        tool_id: str = "t-dag-probe"
        tool_name: str = "dag_probe"
        input_schema: Any = ProbeInput
        output_schema: Any = ProbeOutput

        async def tool_call(self, user_input, session):
            events.append("executed")
            return ProbeOutput(full_body=user_input.text * 2_000)

    class FakeController:
        async def initialize(self):
            return None

        async def on_tool_started(self, call_id, name, arguments):
            events.append("started")

        async def on_tool_finished(self, call_id, name, arguments, result):
            events.append("finished")
            assert call_id == "tc-full"
            assert arguments == {"text": "z"}
            assert len(result["full_body"]) == 2_000

    db_path = str(tmp_path / "react.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.react.get_database_path", lambda _cid: db_path)
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    entry = ToolEntry(
        cls=ProbeTool,
        tool_name="dag_probe",
        tool_id="t-dag-probe",
        input_schema=ProbeInput,
    )
    monkeypatch.setattr("cloudra.react.get_tools_lst", lambda: [entry])
    agent = Follower(
        id="a-probe",
        name="probe",
        prompt="probe",
        query="probe",
        conversation_id="controller-react",
        orchestration_mode="dag_record",
    )
    react = reAct(agent, session_id="s-probe")
    react.dag_controller = FakeController()

    await react.act_result(
        [
            {
                "id": "tc-full",
                "type": "function",
                "function": {
                    "name": "dag_probe",
                    "arguments": '{"text":"z"}',
                },
            }
        ]
    )

    assert events == ["started", "executed", "finished"]
