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


def test_program_events_render_source_outputs_and_receipts():
    project, agent = _fixtures()
    log = EventLog()
    base = dict(project_id=project.id, session_id=agent.id, run_id="run_1")
    source = "const tick = `back``ticks`;\nconst fence = ```js\nnested```;\ntext(tick);"
    log.append("program.submitted", stream="agent", **base, data={
        "execution_id": "exec_1", "outer_tool_call_id": "wire_1",
        "code": source, "source_hash": "deadbeef",
    })
    log.append("tool.requested", stream="agent", **base, data={
        "tool_call_id": "tc_1", "tool_name": "log_parser",
        "arguments_summary": {"log_path": "/x.out"}, "execution_id": "exec_1",
    })
    log.append("tool.result_recorded", stream="agent", **base, data={
        "tool_call_id": "tc_1", "tool_name": "log_parser", "execution_id": "exec_1",
        "result": {"is_success": True, "summary": "ok", "data": {"energy": -40.1}, "duration_ms": 3},
    })
    log.append("program.output", stream="agent", **base, data={
        "execution_id": "exec_1", "output_index": 0, "value": {"energy": -40.1},
    })
    log.append("program.finished", stream="agent", **base, data={
        "execution_id": "exec_1", "outer_tool_call_id": "wire_1", "status": "completed",
        "duration_ms": 42, "error": None,
        "calls": [{"call_id": "tc_1", "tool_name": "log_parser", "status": "completed",
                   "effect_state": "completed", "raw_result_event_id": "evt_raw"}],
    })
    transcript = render_project_transcript(project, {agent.id: agent}, list(log))
    # Source survives verbatim (fence chosen longer than any backtick run).
    assert source in transcript
    assert "````" in transcript  # fence longer than the nested ``` run
    assert "exec `exec_1`" in transcript
    assert "outer call `wire_1`" in transcript
    assert "sha256 `deadbeef`" in transcript
    assert "program output #0" in transcript
    assert '"energy": -40.1' in transcript  # structured output not summarized away
    assert "`tc_1` `log_parser` — completed / completed · raw `evt_raw`" in transcript
    assert "**failed**" not in transcript


def test_program_finished_renders_error_and_control_decision():
    project, agent = _fixtures()
    log = EventLog()
    base = dict(project_id=project.id, session_id=agent.id, run_id="run_1")
    log.append("program.finished", stream="agent", **base, data={
        "execution_id": "exec_2", "outer_tool_call_id": "wire_2", "status": "failed",
        "duration_ms": 7,
        "error": {"code": "policy_wait", "message": "needs approval", "call_id": "tc_9"},
        "calls": [], "control_decision": "wait_approval",
    })
    transcript = render_project_transcript(project, {agent.id: agent}, list(log))
    assert "**failed**" in transcript
    assert "policy_wait" in transcript
    assert "control decision: `wait_approval`" in transcript


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
