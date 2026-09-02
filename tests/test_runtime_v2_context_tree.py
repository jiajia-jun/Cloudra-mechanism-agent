"""Context tree: run-end summarization, handover maintenance, wake-up seeding."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.context_tree import (
    SEED_MARKER,
    build_seed_context,
    fallback_run_summary,
    parse_summary_output,
)
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class ScriptedLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls.append(list(messages))
        assert self.responses, "no scripted LLM response left"
        return self.responses.pop(0)


class EchoTools:
    async def execute(self, agent, call: ToolCall) -> ToolResult:
        return ToolResult(is_success=True, summary=f"echo:{call.arguments.get('x')}", data={})


async def _setup(llm, run_summarizer=None):
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=EchoTools(),
    )
    core.runner = AgentRunner(core, pipeline, run_summarizer=run_summarizer)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "ctx demo"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    return core, bus, project, result.data


async def _wait_state(agent, state: str, timeout: float = 2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


async def _wait_event(core, session_id: str, type: str, timeout: float = 2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        matches = [e for e in core.event_log if e.session_id == session_id and e.type == type]
        if matches:
            return matches[-1]
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"event {type} never appended for {session_id}")
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------------- unit


def test_parse_summary_output_both_markers():
    run_log, handover = parse_summary_output("[RUN LOG]\ndid X\n[HANDOVER]\nstate Y")
    assert run_log == "did X"
    assert handover == "state Y"


def test_parse_summary_output_missing_handover_keeps_previous():
    run_log, handover = parse_summary_output("[RUN LOG]\nonly a log")
    assert run_log == "only a log"
    assert handover is None


def test_parse_summary_output_no_markers_whole_text_is_log():
    run_log, handover = parse_summary_output("free form summary")
    assert run_log == "free form summary"
    assert handover is None


def test_fallback_run_summary_from_events():
    log = EventLog()
    log.append(
        "tool.finished",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="r",
        data={"tool_name": "echo", "is_success": True, "result_summary": "echo:1"},
    )
    log.append(
        "agent.message_emitted",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="r",
        data={"sender": "coordinator", "content": "all done"},
    )
    summary = fallback_run_summary(list(log))
    assert "echo" in summary and "ok" in summary
    assert "all done" in summary


def test_build_seed_context_empty_without_run_summaries():
    log = EventLog()
    log.append(
        "agent.message_injected",
        stream="project",
        project_id="p",
        session_id="s",
        data={"sender": "user", "content": "hello"},
    )
    assert build_seed_context(log, "s") == []


def test_seed_includes_run_that_died_without_summary():
    """A process kill skips finalization; the seed must not lose that run."""
    log = EventLog()
    log.append(
        "agent.message_injected",
        stream="project",
        project_id="p",
        session_id="s",
        data={"sender": "user", "content": "run the calculation"},
    )
    log.append(
        "tool.finished",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="dead-run",
        data={"tool_name": "bash", "is_success": True, "result_summary": "energy=-40.2"},
    )
    log.append(
        "run.finished",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="dead-run",
        data={"outcome": "failed", "error": "interrupted by process restart"},
    )
    seed = build_seed_context(log, "s")
    assert seed and seed[0]["role"] == "system"
    summaries = [m for m in seed if m["role"] == "assistant"]
    assert len(summaries) == 1
    assert "auto-derived" in summaries[0]["content"]
    assert "dead-run" in summaries[0]["content"]
    assert "energy=-40.2" in summaries[0]["content"]
    assert "interrupted by process restart" in summaries[0]["content"]
    users = [m["content"] for m in seed if m["role"] == "user"]
    assert users == ["run the calculation"]


def test_seed_does_not_duplicate_activity_of_summarized_runs():
    """Activity events of a finalized run must not add a second summary."""
    log = EventLog()
    log.append(
        "tool.finished",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="r1",
        data={"tool_name": "bash", "is_success": True, "result_summary": "ok"},
    )
    log.append(
        "context.run_summarized",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="r1",
        data={"summary": "r1 did things", "seq_range": {"start": 1, "end": 2}},
    )
    log.append(
        "tool.finished",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="r2-dead",
        data={"tool_name": "qm_input_writer", "is_success": True, "result_summary": "wrote ts.gjf"},
    )
    seed = build_seed_context(log, "s")
    summaries = [m["content"] for m in seed if m["role"] == "assistant"]
    assert len(summaries) == 2
    assert "r1 did things" in summaries[0] and "auto-derived" not in summaries[0]
    assert "auto-derived" in summaries[1] and "wrote ts.gjf" in summaries[1]


def test_seed_keeps_only_the_latest_reminder_chapter():
    """Long-running schedule polls are duplicate junk; keep one chapter."""
    log = EventLog()
    log.append(
        "agent.message_injected",
        stream="project",
        project_id="p",
        session_id="s",
        data={"sender": "user", "content": "watch the gaussian job"},
    )
    log.append(
        "context.run_summarized",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="r-user",
        data={"summary": "submitted job.gjf", "seq_range": {"start": 1, "end": 2}},
    )
    for i in range(3):
        log.append(
            "agent.message_injected",
            stream="project",
            project_id="p",
            session_id="s",
            data={"sender": "agent", "content": f"[Reminder] check log pass {i}"},
        )
        log.append(
            "context.run_summarized",
            stream="agent",
            project_id="p",
            session_id="s",
            run_id=f"r-poll-{i}",
            data={"summary": f"still running {i}", "seq_range": {"start": 10 + i, "end": 11 + i}},
        )
    log.append(
        "agent.message_injected",
        stream="project",
        project_id="p",
        session_id="s",
        data={"sender": "user", "content": "is it done?"},
    )
    log.append(
        "context.run_summarized",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="r-user-2",
        data={"summary": "told the user not yet", "seq_range": {"start": 20, "end": 21}},
    )
    seed = build_seed_context(log, "s")
    users = [m["content"] for m in seed if m["role"] == "user"]
    assert users == [
        "watch the gaussian job",
        "[Reminder] check log pass 2",
        "is it done?",
    ]
    summaries = [m["content"] for m in seed if m["role"] == "assistant"]
    assert any("submitted job.gjf" in s for s in summaries)
    assert any("still running 2" in s for s in summaries)
    assert any("told the user not yet" in s for s in summaries)
    assert not any("still running 0" in s or "still running 1" in s for s in summaries)
    assert not any("check log pass 0" in s or "check log pass 1" in s for s in summaries)


def test_seed_budget_shrinks_oldest_summaries():
    log = EventLog()
    log.append(
        "agent.message_injected",
        stream="project",
        project_id="p",
        session_id="s",
        data={"sender": "user", "content": "first ask"},
    )
    for i in range(5):
        log.append(
            "context.run_summarized",
            stream="agent",
            project_id="p",
            session_id="s",
            run_id=f"run{i}",
            data={"summary": "S" * 2000, "seq_range": {"start": i, "end": i + 1}},
        )
    log.append(
        "agent.message_injected",
        stream="project",
        project_id="p",
        session_id="s",
        data={"sender": "user", "content": "second ask"},
    )
    log.append(
        "context.handover_updated",
        stream="agent",
        project_id="p",
        session_id="s",
        run_id="run4",
        data={"handover": "CURRENT STATE", "revision": 1},
    )
    seed = build_seed_context(log, "s", budget=6000)
    assert seed[0]["role"] == "system"
    assert seed[0]["content"].startswith(SEED_MARKER)
    assert "CURRENT STATE" in seed[0]["content"]
    # User messages are never degraded.
    users = [m["content"] for m in seed if m["role"] == "user"]
    assert users == ["first ask", "second ask"]
    summaries = [m for m in seed if m["role"] == "assistant"]
    assert "omitted for budget" in summaries[0]["content"]
    assert "run0" in summaries[0]["content"]  # pointer names the run + seq range
    assert "S" * 100 in summaries[-1]["content"]  # newest summary intact
    assert all("_pointer" not in m for m in seed)


# --------------------------------------------------------------- integration


@pytest.mark.asyncio
async def test_stop_produces_run_summary_and_handover():
    async def fake_summarizer(messages):
        return "[RUN LOG]\ndid the thing\n[HANDOVER]\nproject state v1"

    llm = ScriptedLLM([LLMResponse(content="done", stop_requested=True)])
    core, _, _, agent = await _setup(llm, run_summarizer=fake_summarizer)
    await _wait_state(agent, "succeeded")
    summarized = await _wait_event(core, agent.id, "context.run_summarized")
    assert summarized.data["summary"] == "did the thing"
    assert summarized.data["outcome"] == "succeeded"
    assert summarized.data["fallback"] is False
    assert summarized.data["seq_range"] is not None
    handover = await _wait_event(core, agent.id, "context.handover_updated")
    assert handover.data["handover"] == "project state v1"
    assert handover.data["revision"] == 1


@pytest.mark.asyncio
async def test_seed_injected_on_next_wake():
    async def fake_summarizer(messages):
        return "[RUN LOG]\nrun one did X\n[HANDOVER]\nstate after run1"

    llm = ScriptedLLM(
        [
            LLMResponse(content="done1", stop_requested=True),
            LLMResponse(content="done2", stop_requested=True),
        ]
    )
    core, bus, _, agent = await _setup(llm, run_summarizer=fake_summarizer)
    await _wait_state(agent, "succeeded")
    await _wait_event(core, agent.id, "context.handover_updated")

    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "second request"},
        )
    )
    await _wait_state(agent, "succeeded")
    assert len(llm.calls) == 2
    restored = llm.calls[1]
    assert restored[0]["role"] == "system"
    assert restored[0]["content"].startswith(SEED_MARKER)
    assert "state after run1" in restored[0]["content"]
    roles = [m["role"] for m in restored]
    # seed: system + user(verbatim) + assistant(summary); then the new inbox message
    user_texts = [m["content"] for m in restored if m["role"] == "user"]
    assert "solve it" in user_texts  # every user message verbatim
    assert "second request" in user_texts
    seeded_summary = [m for m in restored if m["role"] == "assistant"]
    assert any("run one did X" in str(m["content"]) for m in seeded_summary)
    # chronological: system, user, assistant summary, new user message
    assert roles[0] == "system" and roles[1] == "user" and roles[2] == "assistant"


@pytest.mark.asyncio
async def test_summarizer_failure_falls_back_without_breaking_run():
    async def boom(messages):
        raise RuntimeError("no LLM")

    llm = ScriptedLLM([LLMResponse(content="done", stop_requested=True)])
    core, _, _, agent = await _setup(llm, run_summarizer=boom)
    await _wait_state(agent, "succeeded")
    summarized = await _wait_event(core, agent.id, "context.run_summarized")
    assert summarized.data["fallback"] is True
    assert "done" in summarized.data["summary"]  # event-derived final message
    stale = [e for e in core.event_log if e.type == "context.handover_updated"]
    assert stale == []


@pytest.mark.asyncio
async def test_missing_handover_marker_keeps_previous_handover():
    async def fake_summarizer(messages):
        return "[RUN LOG]\nonly a log"

    llm = ScriptedLLM([LLMResponse(content="done", stop_requested=True)])
    core, _, _, agent = await _setup(llm, run_summarizer=fake_summarizer)
    await _wait_state(agent, "succeeded")
    summarized = await _wait_event(core, agent.id, "context.run_summarized")
    assert summarized.data["summary"] == "only a log"
    assert summarized.data["fallback"] is False
    assert not [e for e in core.event_log if e.type == "context.handover_updated"]


@pytest.mark.asyncio
async def test_first_run_has_no_seed():
    llm = ScriptedLLM([LLMResponse(content="done", stop_requested=True)])
    core, _, _, agent = await _setup(llm, run_summarizer=None)
    await _wait_state(agent, "succeeded")
    assert not any(
        str(m.get("content") or "").startswith(SEED_MARKER) for m in llm.calls[0]
    )


@pytest.mark.asyncio
async def test_failed_run_gets_deterministic_summary():
    class CrashLLM:
        async def complete(self, agent, messages, tools, **_kwargs):
            raise RuntimeError("provider down")

    core, _, _, agent = await _setup(CrashLLM(), run_summarizer=None)
    core.runner.max_turn_retries = 0  # fail fast; backoff would outlive the test
    await _wait_state(agent, "failed")
    summarized = await _wait_event(core, agent.id, "context.run_summarized")
    assert summarized.data["outcome"] == "failed"
    assert summarized.data["fallback"] is True
    assert "provider down" in summarized.data["summary"]


@pytest.mark.asyncio
async def test_compaction_finished_carries_summary(monkeypatch):
    async def fake_summarize(agent, messages):
        return "SUMMARY"

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", fake_summarize
    )

    class GatedLLM:
        def __init__(self) -> None:
            self.gate = asyncio.Event()
            self.calls = 0

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                await self.gate.wait()
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(id="tc1", name="echo", arguments={"x": 1})],
                )
            return LLMResponse(content="done", stop_requested=True)

    llm = GatedLLM()
    core, bus, _, agent = await _setup(llm)
    await asyncio.sleep(0.02)  # first LLM call in flight, gated
    await bus.execute(
        Command(
            type="agent.compact",
            target={"session_id": agent.id},
            payload={"keep_recent": 1},
        )
    )
    llm.gate.set()
    await _wait_state(agent, "succeeded")
    finished = await _wait_event(core, agent.id, "compaction.finished")
    assert "SUMMARY" in finished.data["summary"]
