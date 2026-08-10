import json
from typing import Any

import httpx
import pytest

from cloudra.agent import Follower
from cloudra.api import create_app
from cloudra.config import get_config
from cloudra.database import ConversationDB
from cloudra.service import CloudraService
from cloudra.tools import ToolEntry
from cloudra.tools.Stoptool.stop_tool import StopTool


def _stop_react(tmp_path, monkeypatch, mode):
    from cloudra.react import reAct

    db_path = str(tmp_path / f"{mode}.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.react.get_database_path", lambda _cid: db_path)
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    entry = ToolEntry(
        cls=StopTool,
        tool_name="stop",
        tool_id="t-stop",
        input_schema=StopTool._get_field_default("input_schema"),
    )
    monkeypatch.setattr("cloudra.react.get_tools_lst", lambda: [entry])
    agent = Follower(
        id="a-stop",
        name="stop-test",
        prompt="test",
        query="mechanism",
        conversation_id=f"stop-{mode}",
        orchestration_mode=mode,
    )
    return reAct(agent, session_id=f"s-{mode}"), agent, db_path


def _stop_call(disposition):
    return {
        "id": "tc-stop",
        "type": "function",
        "function": {
            "name": "stop",
            "arguments": json.dumps(
                {
                    "reason": "deliver",
                    "delivery_disposition": disposition,
                }
            ),
        },
    }


@pytest.mark.asyncio
async def test_incomplete_delivery_rejects_complete_stop(tmp_path, monkeypatch):
    react, agent, _db_path = _stop_react(tmp_path, monkeypatch, "dag_record")

    stopped = await react.act_result([_stop_call("complete")])

    assert stopped is False
    assert react._continue is True
    context = await agent.get_context()
    tool_message = next(msg for msg in context if msg.get("role") == "tool")
    assert "empty_delivery_graph" in tool_message["content"]


@pytest.mark.asyncio
async def test_ordinary_text_cannot_bypass_incomplete_delivery_audit(
    tmp_path,
    monkeypatch,
):
    from unittest.mock import AsyncMock

    react, agent, _db_path = _stop_react(tmp_path, monkeypatch, "dag_record")
    await agent.update_context(
        {"role": "assistant", "content": "The mechanism study is complete."}
    )
    react.reasoning = AsyncMock(
        side_effect=[[], RuntimeError("entered another reasoning turn")]
    )
    react._consume_external_events = AsyncMock()

    with pytest.raises(RuntimeError, match="another reasoning turn"):
        await react._run_loop()

    assert react.reasoning.await_count == 2
    assert react.session.state != "completed"
    context = await agent.get_context()
    assert "empty_delivery_graph" in context[-1]["content"]


@pytest.mark.asyncio
async def test_partial_stop_preserves_gaps_and_audits_disposition(
    tmp_path,
    monkeypatch,
):
    react, _agent, db_path = _stop_react(tmp_path, monkeypatch, "dag_record")

    stopped = await react.act_result([_stop_call("partial")])

    assert stopped is True
    assert react._continue is False
    assert not react.dag_controller.delivery_report().complete
    with ConversationDB.from_path(db_path).connect() as con:
        row = con.execute(
            "SELECT disposition, report FROM dag_delivery_dispositions"
        ).fetchone()
    assert row[0] == "partial"
    assert json.loads(row[1])["complete"] is False


@pytest.mark.asyncio
async def test_standard_stop_does_not_touch_graph_storage(tmp_path, monkeypatch):
    react, _agent, db_path = _stop_react(tmp_path, monkeypatch, "standard")

    stopped = await react.act_result([_stop_call("complete")])

    assert stopped is True
    with ConversationDB.from_path(db_path).connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_dag_read_api_is_non_initializing_and_returns_persisted_state(
    tmp_path,
    monkeypatch,
):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, GraphOperation, MutationBatch
    from cloudra.dag.store import DagStore

    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    service = CloudraService()
    conversation_id = "dag-api-read"
    db = ConversationDB(conversation_id).init()
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get(
            f"/api/conversations/{conversation_id}/dag/projection"
        )
    assert missing.status_code == 404
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone()[0] == 0

    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="api-test",
            base_revisions=store.load_bundle().revisions,
            operations=[
                GraphOperation(
                    op="add_node",
                    graph="process",
                    data={
                        "node_id": "map",
                        "node_type": "work",
                        "label": "mapping",
                        "payload": {"status": "ready"},
                    },
                )
            ],
        )
    )
    assert seeded.accepted
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        projection = await client.get(
            f"/api/conversations/{conversation_id}/dag/projection"
        )
        graph = await client.get(
            f"/api/conversations/{conversation_id}/dag/graphs/process"
        )
        report = await client.get(
            f"/api/conversations/{conversation_id}/dag/delivery-report"
        )
        history = await client.get(
            f"/api/conversations/{conversation_id}/dag/history"
        )

    assert projection.status_code == graph.status_code == report.status_code == history.status_code == 200
    assert projection.json()["frontier"][0]["node_id"] == "map"
    assert graph.json()["nodes"][0]["node_id"] == "map"
    assert report.json()["complete"] is False
    assert history.json()[0]["actor"] == "harness"


@pytest.mark.asyncio
async def test_service_user_mutation_edits_and_audits(tmp_path, monkeypatch):
    """service.dag_apply_user_mutation：actor=user 落库、可 waive gate、受引擎校验。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, GraphOperation, MutationBatch
    from cloudra.dag.store import DagStore

    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    conversation_id = "user-mutation-service"
    db = ConversationDB(conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="coordinator",
            base_revisions=store.load_bundle().revisions,
            operations=[
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "r",
                        "node_type": "intermediate_occurrence",
                        "label": "reactant",
                        "payload": {"evidence_level": "proposed"},
                    },
                )
            ],
        )
    )
    assert seeded.accepted

    service = CloudraService()
    edited = service.dag_apply_user_mutation(
        conversation_id,
        [
            {
                "op": "update_node",
                "graph": "delivery",
                "data": {
                    "node_id": "r",
                    "changes": {
                        "evidence_level": "inconclusive",
                        "reason": "user reviewed the logs",
                    },
                },
            }
        ],
        store.load_bundle().revisions,
        "user review",
    )
    assert edited["accepted"] is True

    stale = service.dag_apply_user_mutation(
        conversation_id,
        [
            {
                "op": "update_node",
                "graph": "delivery",
                "data": {"node_id": "r", "changes": {"label": "X"}},
            }
        ],
        {"process": 0, "delivery": 0},
        "stale base revision",
    )
    assert stale["accepted"] is False
    assert stale["rejection_code"] == "stale_revision"

    forged = service.dag_apply_user_mutation(
        conversation_id,
        [
            {
                "op": "update_node",
                "graph": "delivery",
                "data": {"node_id": "r", "changes": {"evidence_level": "endpoint_supported"}},
            }
        ],
        store.load_bundle().revisions,
        "users cannot forge derived evidence either",
    )
    assert forged["accepted"] is False
    assert forged["rejection_code"] == "actor_forbidden"

    missing = service.dag_apply_user_mutation(
        "no-such-conversation",
        [],
        {"process": 0, "delivery": 0},
    )
    assert missing is None

    with db.connect() as con:
        actors = con.execute(
            "SELECT actor_type FROM dag_mutations WHERE accepted = 1 ORDER BY rowid"
        ).fetchall()
    assert [row[0] for row in actors] == ["agent", "user"]
