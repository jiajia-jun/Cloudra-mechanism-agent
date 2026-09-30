"""SPA 热点 HTTP 路由：前端天天打、此前只在 CommandBus/pending 测过的路径。

覆盖面钉死 api.ts 实际发出的形状（decision=approve|deny、tail=true、
before= cursor、cancel 空 body）。不测 UI——那是 Playwright/helper 的事。
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.schemas import AgentState
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline
from cloudra.services.api_v2 import create_v2_app


class _StopLLM:
    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(content="done", stop_requested=True)


async def _wait_for(predicate, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


def _app_with_runner() -> tuple[object, RuntimeCore]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=_StopLLM(),
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline)
    return create_v2_app(core), core


async def _project_with_agent(client: AsyncClient) -> tuple[dict, dict]:
    resp = await client.post("/api/v2/projects", json={"name": "spa-hot"})
    assert resp.status_code == 201
    project = resp.json()["data"]
    resp = await client.post(
        f"/api/v2/projects/{project['id']}/agents",
        json={"role_id": "coordinator", "query": "go"},
    )
    assert resp.status_code == 201
    agent = resp.json()["data"]
    return project, agent


@pytest.mark.asyncio
async def test_list_project_agents_and_get_agent():
    app, _core = _app_with_runner()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        project, agent = await _project_with_agent(client)

        resp = await client.get(f"/api/v2/projects/{project['id']}/agents")
        assert resp.status_code == 200
        rows = resp.json()
        assert any(row["id"] == agent["id"] for row in rows)

        resp = await client.get(f"/api/v2/agents/{agent['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == agent["id"]
        assert body["role_id"] == "coordinator"
        assert "children" in body


@pytest.mark.asyncio
async def test_agent_events_tail_and_before_match_spa_shapes():
    """api.events / api.eventsPage 永远发 after=0&tail=true，Load earlier 加 before=。

    before 游标是闭区间（<=）：SPA 用当前窗最老 session_seq 再拉一页，
    再用 event_id 去重（App loadOlder）。
    """
    app, core = _app_with_runner()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        _project, agent = await _project_with_agent(client)
        await _wait_for(lambda: core.require_agent(agent["id"]).state is AgentState.SUCCEEDED)

        resp = await client.get(
            f"/api/v2/agents/{agent['id']}/events",
            params={"after": 0, "limit": 500, "tail": True},
        )
        assert resp.status_code == 200
        newest = resp.json()
        assert isinstance(newest, list)
        assert len(newest) >= 1
        assert all("session_seq" in ev for ev in newest)
        assert newest == sorted(newest, key=lambda ev: ev["session_seq"])

        oldest = newest[0]["session_seq"]
        resp = await client.get(
            f"/api/v2/agents/{agent['id']}/events",
            params={"after": 0, "limit": 500, "tail": True, "before": oldest},
        )
        assert resp.status_code == 200
        older = resp.json()
        assert all(ev["session_seq"] <= oldest for ev in older)
        # 与 SPA 一致：按 event_id 去重后应能拿到不重复的增量（或空页）
        known = {ev["event_id"] for ev in newest}
        fresh = [ev for ev in older if ev["event_id"] not in known]
        assert all(ev["session_seq"] <= oldest for ev in fresh)


@pytest.mark.asyncio
async def test_cancel_agent_http_marks_cancelled():
    """SPA Cancel 发空 body POST /cancel；不依赖 spawn+query 的竞态终态。"""
    app, core = _app_with_runner()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v2/projects", json={"name": "spa-cancel"})
        assert resp.status_code == 201
        project = resp.json()["data"]
        # 无 query：不自动跑 LLM，状态可控
        resp = await client.post(
            f"/api/v2/projects/{project['id']}/agents",
            json={"role_id": "coordinator"},
        )
        assert resp.status_code == 201
        agent = resp.json()["data"]
        live = core.require_agent(agent["id"])
        await core.agent_host.start_run(live)
        assert live.state is AgentState.RUNNING

        resp = await client.post(f"/api/v2/agents/{agent['id']}/cancel", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is True, body
        assert body["data"]["state"] == "cancelled"

        # 幂等：再取消一次仍 accepted（终态 noop），SPA 刷新 listAgents 不炸
        resp = await client.post(f"/api/v2/agents/{agent['id']}/cancel", json={})
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True


@pytest.mark.asyncio
async def test_approval_decision_http_approve_and_deny():
    app, core = _app_with_runner()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        project, agent = await _project_with_agent(client)
        live = core.require_agent(agent["id"])
        await _wait_for(lambda: live.state is AgentState.SUCCEEDED)
        await core.agent_host.start_run(live)

        async def ask():
            return await core.pending.request_approval(
                live,
                tool_name="write",
                details="write file",
                normalized_arguments={"path": "a.txt"},
                risk_summary="write a.txt",
                candidate_diff="+hello",
            )

        task = asyncio.create_task(ask())
        await _wait_for(lambda: live.state is AgentState.WAITING_APPROVAL)
        pending = (await client.get(f"/api/v2/projects/{project['id']}/approvals")).json()
        assert len(pending) == 1
        aid = pending[0]["id"]

        # SPA 发 decision=approve（不是 approved）
        resp = await client.post(
            f"/api/v2/projects/{project['id']}/approvals/{aid}/decision",
            json={"decision": "approve", "reason": ""},
        )
        assert resp.status_code == 200
        assert resp.json() == {"accepted": True}
        approved, reason = await task
        assert approved is True and reason == ""
        assert (await client.get(f"/api/v2/projects/{project['id']}/approvals")).json() == []

        task2 = asyncio.create_task(ask())
        await _wait_for(lambda: core.pending.list_pending_approvals(project["id"]))
        aid2 = core.pending.list_pending_approvals(project["id"])[0]["id"]
        # SPA deny 固定 reason='denied by user'
        resp = await client.post(
            f"/api/v2/projects/{project['id']}/approvals/{aid2}/decision",
            json={"decision": "deny", "reason": "denied by user"},
        )
        assert resp.status_code == 200
        approved2, reason2 = await task2
        assert approved2 is False and reason2 == "denied by user"


@pytest.mark.asyncio
async def test_approval_decision_unknown_id_is_404():
    app, _core = _app_with_runner()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        project, _agent = await _project_with_agent(client)
        resp = await client.post(
            f"/api/v2/projects/{project['id']}/approvals/apv_missing/decision",
            json={"decision": "approve", "reason": ""},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_interaction_response_http():
    app, core = _app_with_runner()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        project, agent = await _project_with_agent(client)
        live = core.require_agent(agent["id"])
        await _wait_for(lambda: live.state is AgentState.SUCCEEDED)
        await core.agent_host.start_run(live)

        task = asyncio.create_task(core.pending.request_interaction(live, "which solvent?"))
        await _wait_for(lambda: core.pending.list_pending_interactions(project["id"]))
        rows = (await client.get(f"/api/v2/projects/{project['id']}/interactions")).json()
        assert len(rows) == 1
        ixn_id = rows[0]["interaction_id"]

        resp = await client.post(
            f"/api/v2/projects/{project['id']}/interactions/{ixn_id}/response",
            json={"response": "ethanol"},
        )
        assert resp.status_code == 200
        answer = await task
        assert answer == "ethanol"
        assert (await client.get(f"/api/v2/projects/{project['id']}/interactions")).json() == []


@pytest.mark.asyncio
async def test_interaction_response_empty_rejected():
    app, _core = _app_with_runner()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        project, _agent = await _project_with_agent(client)
        resp = await client.post(
            f"/api/v2/projects/{project['id']}/interactions/ixn_x/response",
            json={"response": ""},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unarchive_project_http():
    app, _core = _app_with_runner()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        project, _agent = await _project_with_agent(client)

        resp = await client.delete(f"/api/v2/projects/{project['id']}")
        assert resp.status_code == 200

        listed = (await client.get("/api/v2/projects")).json()
        assert all(p["id"] != project["id"] for p in listed)

        resp = await client.patch(
            f"/api/v2/projects/{project['id']}",
            json={"archived": False},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["archived"] is False

        listed = (await client.get("/api/v2/projects")).json()
        assert any(p["id"] == project["id"] for p in listed)
