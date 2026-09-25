"""AgentHub forum API（routers/hub.py）：读投影 + 用户发帖。

口径：
- ``GET /api/v2/projects/{id}/hub/posts`` 是事件日志的纯投影，按项目隔离；
- ``POST`` 走的是与 agent ``agent_hub`` 工具同源的 EventWriter + 信箱通知
  路径，作者固定为 ``user``（无 session）；
- 通知语义与 tool 版一致：broadcast 通知全部非终态会话，其余 kind 只通知
  addressee 与被回复帖的原作者。
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.hub_bridge import handle_hub_tool
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline
from cloudra.services.api_v2 import create_v2_app


class StopLLM:
    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(content=f"{agent.role_id} done", stop_requested=True)


def _make_core() -> RuntimeCore:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=StopLLM(),
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline)
    return core


async def _make_project(core: RuntimeCore, name: str = "p"):
    return (
        await CommandBus(core).execute(Command(type="project.create", payload={"name": name}))
    ).data


async def _spawn(core: RuntimeCore, project_id: str, role_id: str = "coordinator"):
    result = await CommandBus(core).execute(
        Command(
            type="agent.spawn",
            target={"project_id": project_id},
            payload={"role_id": role_id, "query": "solve it"},
        )
    )
    agent = result.data
    deadline = asyncio.get_running_loop().time() + 5.0
    while agent.state.value not in {"succeeded", "failed"}:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}")
        await asyncio.sleep(0.01)
    return agent


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.asyncio
async def test_user_post_roundtrip_and_topic_filter():
    core = _make_core()
    project = await _make_project(core)
    other = await _make_project(core, "other")
    app = create_v2_app(core)
    async with _client(app) as client:
        resp = await client.get(f"/api/v2/projects/{project.id}/hub/posts")
        assert resp.status_code == 200
        assert resp.json() == {"posts": []}

        resp = await client.post(
            f"/api/v2/projects/{project.id}/hub/posts",
            json={"topic": "CO2 literature", "content": "Catalyst X gives 90% selectivity"},
        )
        assert resp.status_code == 200
        body = resp.json()
        post = body["post"]
        assert post["author_agent"] == "user"
        assert post["author_session"] is None
        assert post["kind"] == "finding"
        assert post["to_agent"] is None
        assert body["notified_count"] == 0
        assert body["failed_session_ids"] == []

        # 项目隔离：另一项目看不到。
        resp = await client.get(f"/api/v2/projects/{other.id}/hub/posts")
        assert resp.json() == {"posts": []}

        resp = await client.get(f"/api/v2/projects/{project.id}/hub/posts")
        rows = resp.json()["posts"]
        assert [r["id"] for r in rows] == [post["id"]]
        assert rows[0]["content"] == "Catalyst X gives 90% selectivity"

        resp = await client.get(
            f"/api/v2/projects/{project.id}/hub/posts", params={"topic": "CO2 literature"}
        )
        assert len(resp.json()["posts"]) == 1
        resp = await client.get(
            f"/api/v2/projects/{project.id}/hub/posts", params={"topic": "nope"}
        )
        assert resp.json()["posts"] == []


@pytest.mark.asyncio
async def test_user_post_validation_errors():
    core = _make_core()
    project = await _make_project(core)
    app = create_v2_app(core)
    async with _client(app) as client:
        # 空白 topic 经 strip 后为空 → 400。
        resp = await client.post(
            f"/api/v2/projects/{project.id}/hub/posts",
            json={"topic": "   ", "content": "x"},
        )
        assert resp.status_code == 400

        resp = await client.post(
            f"/api/v2/projects/{project.id}/hub/posts",
            json={"topic": "t", "content": "x", "kind": "essay"},
        )
        assert resp.status_code == 400

        resp = await client.post(
            f"/api/v2/projects/{project.id}/hub/posts",
            json={"topic": "t", "content": "x", "kind": "message"},
        )
        assert resp.status_code == 400

        resp = await client.post(
            f"/api/v2/projects/{project.id}/hub/posts",
            json={"topic": "t", "content": "x", "parent_id": "evt_missing"},
        )
        assert resp.status_code == 404

        resp = await client.post(
            "/api/v2/projects/prj_nope/hub/posts",
            json={"topic": "t", "content": "x"},
        )
        assert resp.status_code == 404
        resp = await client.get("/api/v2/projects/prj_nope/hub/posts")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_user_post_addressed_and_reply_notify_agents():
    core = _make_core()
    project = await _make_project(core)
    coordinator = await _spawn(core, project.id)
    app = create_v2_app(core)
    async with _client(app) as client:
        # 定向帖：只通知 addressee。
        resp = await client.post(
            f"/api/v2/projects/{project.id}/hub/posts",
            json={
                "topic": "IRC check", "content": "did the path converge?",
                "kind": "question", "to_agent": "coordinator",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["notified_count"] == 1
        notices = [
            e for e in core.event_log.query_project(project.id, types={"agent.message_injected"})
            if e.data.get("post_id") == body["post"]["id"]
        ]
        assert len(notices) == 1
        assert notices[0].session_id == coordinator.id
        assert "user" in str(notices[0].data.get("content", ""))

        # agent 发帖后用户回帖：原作者收到回复通知。
        agent_post = await handle_hub_tool(
            core, coordinator,
            ToolCall(id="t1", name="agent_hub", arguments={
                "action": "post", "topic": "IRC check", "content": "path converged both sides",
            }),
        )
        parent_id = agent_post.data["post_id"]
        resp = await client.post(
            f"/api/v2/projects/{project.id}/hub/posts",
            json={
                "topic": "IRC check", "content": "great, please upload the log",
                "parent_id": parent_id,
            },
        )
        assert resp.status_code == 200
        reply = resp.json()
        assert reply["post"]["parent_id"] == parent_id
        assert reply["notified_count"] == 1
        reply_notices = [
            e for e in core.event_log.query_project(project.id, types={"agent.message_injected"})
            if e.data.get("post_id") == reply["post"]["id"]
        ]
        assert len(reply_notices) == 1
        assert reply_notices[0].session_id == coordinator.id


@pytest.mark.asyncio
async def test_user_broadcast_notifies_all_nonterminal_sessions():
    core = _make_core()
    project = await _make_project(core)
    first = await _spawn(core, project.id)
    second = await _spawn(core, project.id)
    app = create_v2_app(core)
    async with _client(app) as client:
        resp = await client.post(
            f"/api/v2/projects/{project.id}/hub/posts",
            json={"topic": "standup", "content": "report status", "kind": "broadcast"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["notified_count"] == 2
        notified = {
            e.session_id
            for e in core.event_log.query_project(project.id, types={"agent.message_injected"})
            if e.data.get("post_id") == body["post"]["id"]
        }
        assert notified == {first.id, second.id}
