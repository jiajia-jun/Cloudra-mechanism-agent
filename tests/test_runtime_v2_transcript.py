"""Project transcript: full-payload Markdown renderer + download endpoint."""

from __future__ import annotations

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.schemas import AgentSession, Project
from cloudra.runtime_v2.transcript import render_project_transcript


def _fixtures():
    project = Project(id="prj_1", name="demo")
    agent = AgentSession(
        id="as_1", project_id="prj_1", role_id="coordinator", display_name="Coordinator"
    )
    return project, agent


def _seed_log() -> EventLog:
    log = EventLog()
    base = dict(project_id="prj_1", session_id="as_1", run_id="run_1")
    log.append(
        "run.started",
        stream="agent",
        **base,
        data={"settings_summary": {"model": "m0"}},
    )
    log.append(
        "agent.message_injected",
        stream="project",
        **{k: v for k, v in base.items() if k != "run_id"},
        data={"message_id": "msg_1", "sender": "user", "content": "do the thing"},
    )
    thinking = "step 1: reason about ```code fences``` and **markdown** " + "x" * 5000
    log.append("agent.thinking", stream="agent", **base, data={"content": thinking})
    log.append(
        "tool.started",
        stream="agent",
        **base,
        data={"tool_call_id": "tc1", "tool_name": "echo", "arguments_summary": {"x": 1}},
    )
    log.append(
        "tool.finished",
        stream="agent",
        **base,
        data={
            "tool_call_id": "tc1",
            "tool_name": "echo",
            "is_success": True,
            "result_summary": "echo:1 " + "y" * 3000,
            "duration_ms": 5,
        },
    )
    log.append(
        "agent.message_emitted",
        stream="agent",
        **base,
        data={"sender": "coordinator", "content": "final answer"},
    )
    log.append("run.finished", stream="agent", **base, data={"outcome": "succeeded"})
    log.append(
        "context.run_summarized",
        stream="agent",
        **base,
        data={
            "summary": "run one trajectory",
            "outcome": "succeeded",
            "fallback": False,
            "seq_range": {"start": 1, "end": 7},
        },
    )
    log.append(
        "context.handover_updated",
        stream="agent",
        **base,
        data={"handover": "project state snapshot", "based_on_run_id": "run_1", "revision": 1},
    )
    return log


def test_render_includes_full_payloads():
    project, agent = _fixtures()
    log = _seed_log()
    text = render_project_transcript(project, {agent.id: agent}, list(log))
    assert text.startswith("# Cloudra transcript — demo")
    assert "do the thing" in text
    # Thinking chain is preserved in full, fence-breaking backticks included.
    assert "x" * 5000 in text
    assert "```code fences```" in text
    # Tool call pairs arguments + full result.
    assert '"x": 1' in text
    assert "y" * 3000 in text
    assert "final answer" in text
    assert "run one trajectory" in text
    assert "project state snapshot" in text
    assert "revision 1" in text
    # Run boundaries render as headings.
    assert "Run `run_1`" in text


def test_render_skips_transient_types():
    project, agent = _fixtures()
    log = _seed_log()
    log.append(
        "llm.chunk",
        stream="agent",
        project_id="prj_1",
        session_id="as_1",
        run_id="run_1",
        data={"kind": "content", "delta": "transient"},
    )
    text = render_project_transcript(project, {agent.id: agent}, list(log))
    assert "transient" not in text


def test_transcript_endpoint_downloads_markdown():
    from fastapi.testclient import TestClient

    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.services.api_v2 import create_v2_app

    core = RuntimeCore(strict_events=True)
    project, agent = _fixtures()
    core.projects[project.id] = project
    core.agents[agent.id] = agent
    for event in _seed_log():
        core.event_log.append(
            event.type,
            stream=event.stream,
            project_id=event.project_id,
            session_id=event.session_id,
            run_id=event.run_id,
            data=event.data,
        )
    client = TestClient(create_v2_app(core))
    response = client.get("/api/v2/projects/prj_1/transcript")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert "cloudra-transcript-demo.md" in response.headers["content-disposition"]
    assert "do the thing" in response.text
    assert "x" * 5000 in response.text


def test_transcript_endpoint_404_for_unknown_project():
    from fastapi.testclient import TestClient

    from cloudra.services.api_v2 import create_v2_app

    client = TestClient(create_v2_app())
    assert client.get("/api/v2/projects/nope/transcript").status_code == 404
