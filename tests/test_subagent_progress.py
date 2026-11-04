"""Cloudra Subagent progress uses public event projections and scoped state."""

import shutil
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentSession, AgentState, CurrentRun, Project, utc_now
from cloudra.services.api_v2 import create_v2_app

PROJECT_PROGRESS = "/api/v2/projects/p/subagent/progress"
AGENT_PROGRESS = "/api/v2/projects/p/subagent/agents/a/progress"
HOST = Path(__file__).resolve().parents[1] / "cloudra/runtime_v2/js_host"
requires_js = pytest.mark.skipif(
    shutil.which("node") is None
    or not (HOST / "node_modules/quickjs-emscripten/package.json").is_file(),
    reason="optional Node/QuickJS prerequisites missing",
)


@pytest.fixture
def core(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="Research", workspace_dir=str(tmp_path))
    core.projects["other"] = Project(id="other", name="Other")
    core.agents["a"] = AgentSession(
        id="a", project_id="p", role_id="coordinator", display_name="Coordinator",
    )
    core.agents["foreign"] = AgentSession(
        id="foreign", project_id="other", role_id="researcher", display_name="Other researcher",
    )
    return core


def _client(core):
    return AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver")


def _emit(core, type_, data, *, run_id="run-1"):
    return core.event_log.append(
        type_, stream="agent", project_id="p", session_id="a", run_id=run_id, data=data,
    )


@pytest.mark.asyncio
async def test_project_progress_distinguishes_background_and_review_and_bounds_notes(core, tmp_path):
    agent = core.agents["a"]
    agent.state = AgentState.SUCCEEDED
    _emit(core, "agent.completion_gate", {"action": "wait_background", "reason": "Calculation in progress"})
    _emit(core, "agent.state_changed", {"to": "succeeded"})
    _emit(core, "run.finished", {"outcome": "succeeded"})
    async with _client(core) as client:
        response = await client.get(PROJECT_PROGRESS)
        assert response.status_code == 200
        assert response.json()["process"] is None
        assert [(a["session_id"], a["activity"], a["detail"]) for a in response.json()["agents"]] == [
            ("a", "waiting_background", "Calculation in progress"),
        ]

        agent.state = AgentState.WAITING_APPROVAL
        agent.current_run = CurrentRun(run_id="run-2", started_at=utc_now())
        _emit(core, "agent.completion_gate", {"action": "wait_review", "reason": "Exit review"}, run_id="run-2")
        _emit(core, "agent.state_changed", {"to": "waiting_approval", "reason": "wait_review"}, run_id="run-2")
        (tmp_path / "PROCESS.md").write_text("化" * 8100, encoding="utf-8")
        payload = (await client.get(PROJECT_PROGRESS)).json()
        assert payload["agents"][0]["activity"] == "waiting_review"
        assert payload["pending"] == [{"kind": "review", "session_id": "a", "summary": "Exit review"}]
        assert payload["process"]["text"] == "化" * 8000
        assert payload["process"]["truncated"] is True
        assert payload["process"]["updated_at"]
        assert (await client.get(PROJECT_PROGRESS, params={"include_process": "false"})).json()["process"] is None


@pytest.mark.asyncio
async def test_progress_uses_current_wait_instead_of_an_old_review_gate(core):
    agent = core.agents["a"]
    agent.state = AgentState.WAITING_APPROVAL
    agent.current_run = CurrentRun(run_id="run-1", started_at=utc_now())
    _emit(core, "agent.completion_gate", {"action": "wait_review", "reason": "Earlier review"})
    _emit(core, "agent.state_changed", {"to": "running", "reason": "resumed"})
    core.pending.apply(_emit(core, "approval.requested", {
        "approval_id": "approval-1", "tool_name": "bash", "risk_summary": "Write research file",
        "normalized_arguments": {"private": "raw tool arguments"},
    }))
    _emit(core, "agent.state_changed", {"to": "waiting_approval", "reason": "approval"})
    async with _client(core) as client:
        response = await client.get(PROJECT_PROGRESS)
        assert response.status_code == 200
        assert response.json()["agents"][0]["activity"] == "waiting_approval"
        assert response.json()["pending"] == [{
            "kind": "approval", "session_id": "a", "approval_id": "approval-1",
            "summary": "Write research file",
        }]


@pytest.mark.asyncio
async def test_public_history_defaults_to_last_assistant_and_is_scoped(core):
    _emit(core, "agent.message_injected", {"content": "user notes"})
    public = _emit(core, "agent.message_emitted", {"content": "answer"})
    hidden = _emit(core, "agent.thinking", {"content": "recorded reasoning"})
    _emit(core, "llm.failed", {"error": "provider error"})
    async with _client(core) as client:
        assert (await client.post(AGENT_PROGRESS.replace("/a/", "/foreign/"), json={})).status_code == 404
        response = await client.post(AGENT_PROGRESS, json={})
        assert response.status_code == 200
        assert response.json()["messages"] == [{
            "event_id": public.event_id,
            "kind": "assistant",
            "text": "answer",
            "truncated": False,
            "at": public.created_at.isoformat(),
            "tool_name": None,
            "status": None,
        }]
        response = await client.post(AGENT_PROGRESS, json={"limit": 2, "include_reasoning": True})
        assert [m["event_id"] for m in response.json()["messages"]] == [public.event_id, hidden.event_id]


@requires_js
@pytest.mark.asyncio
async def test_filter_applies_before_limit_to_public_tool_receipts(core):
    failure_ids = []
    for index, status in enumerate(["failed", "failed", "completed"]):
        request = _emit(core, "tool.requested", {
            "tool_call_id": str(index), "tool_name": "probe",
            "arguments_summary": {"private_argument": "private"},
        })
        _emit(core, "tool.result_recorded", {
            "tool_call_id": str(index), "result": {"data": {"private_result": "private"}},
        })
        _emit(core, "tool.finished", {
            "tool_call_id": str(index), "status": status, "result_summary": "公開" * 1100,
        })
        if status == "failed":
            failure_ids.append(request.event_id)
    _emit(core, "agent.thinking", {"content": "private reasoning"})
    _emit(core, "agent.message_emitted", {"content": "latest answer"})
    async with _client(core) as client:
        result = await client.post(AGENT_PROGRESS, json={
            "limit": 2,
            "filter": (
                "entry.kind === 'tool' && entry.status === 'failed' && entry.text.length <= 2000 "
                "&& !entry.arguments && !entry.result"
            ),
        })
        assert result.status_code == 200
        assert [m["event_id"] for m in result.json()["messages"]] == failure_ids
        assert all(m["truncated"] for m in result.json()["messages"])
        response = await client.post(AGENT_PROGRESS, json={"filter": "entry.kind === 'reasoning'"})
        assert response.json()["messages"] == []


@requires_js
@pytest.mark.asyncio
async def test_filter_has_no_host_bridge_and_history_scan_is_bounded(core):
    _emit(core, "agent.message_emitted", {"content": "beyond the search window"})
    for index in range(500):
        _emit(core, "agent.message_emitted", {"content": f"public {index}"})
    async with _client(core) as client:
        result = await client.post(AGENT_PROGRESS, json={
            "filter": (
                "typeof tools === 'undefined' && typeof process === 'undefined' "
                "&& typeof require === 'undefined' && typeof fetch === 'undefined' "
                "&& typeof text === 'undefined' && entry.text === 'public 0'"
            ),
        })
        assert result.status_code == 200
        assert result.json()["history_truncated"] is True
        assert [m["text"] for m in result.json()["messages"]] == ["public 0"]


@requires_js
@pytest.mark.asyncio
@pytest.mark.parametrize("expression", ["entry.", "'not a boolean'", "(() => { while (true) {} })()"])
async def test_invalid_filter_fails_loudly_without_changing_history(core, expression):
    _emit(core, "agent.message_emitted", {"content": "still here"})
    async with _client(core) as client:
        response = await client.post(AGENT_PROGRESS, json={"filter": expression})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_request"
        assert (await client.post(AGENT_PROGRESS, json={})).json()["messages"][0]["text"] == "still here"
