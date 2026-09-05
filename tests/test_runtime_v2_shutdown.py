"""Task 5 shutdown semantics (plan 2026-09-05-event-driven-supervisor, Task 5).

Covers:
- daemon_supervisor.request_daemons_shutdown / daemons.stop marker (blocks
  ensure_*, persist/clear lifecycle, scheduler daemon self-exit);
- api_v2 lifespan teardown order with four live activity classes (runner,
  supervisor runner, detached finalize, open LLM SSE stream): after shutdown
  no registered execution survives and no new LLM request fires;
- web_launcher._terminate_runtime SIGTERM -> wait -> SIGKILL escalation.

Local fake HTTP/SSE server only — never touches a real provider.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from cloudra.infra.llm_client import LLMClient
from cloudra.runtime_v2.adapters import LegacyLLMProvider
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentState, Command, InvocationProtocol
from cloudra.runtime_v2.turn_pipeline import TurnPipeline
from cloudra.services import daemon_supervisor
from tests.test_llm_cancellation import _FakeLLMServer
from tests.test_runtime_v2_cancellation import GatedSummarizer, _wait_until


@pytest.fixture(autouse=True)
def _reset_daemon_shutdown():
    daemon_supervisor._reset_shutdown_for_tests()
    yield
    daemon_supervisor._reset_shutdown_for_tests()
    try:
        Path(daemon_supervisor.daemons_stop_marker_path()).unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------- daemons


def test_request_daemons_shutdown_blocks_ensure(monkeypatch):
    """After request_daemons_shutdown, ensure_* must refuse to spawn (the
    watchdog's self-healing is disabled by the same flag)."""
    spawned = []
    monkeypatch.setattr(
        "cloudra.infra.compute_utils.spawn_detached",
        lambda *args, **kwargs: spawned.append(args),
    )
    daemon_supervisor.request_daemons_shutdown()
    daemon_supervisor.ensure_scheduler()
    daemon_supervisor.ensure_kg_vec()
    assert spawned == []


def test_daemons_stop_marker_persist_and_clear():
    """persist=True writes the cross-process marker; a fresh process (in-proc
    flag cleared) still sees shutdown requested until an explicit start clears
    the marker."""
    daemon_supervisor.request_daemons_shutdown(persist=True)
    assert Path(daemon_supervisor.daemons_stop_marker_path()).is_file()
    daemon_supervisor._reset_shutdown_for_tests()  # simulate a fresh process
    assert daemon_supervisor.daemons_shutdown_requested()
    daemon_supervisor.clear_daemons_shutdown()
    assert not daemon_supervisor.daemons_shutdown_requested()


@pytest.mark.asyncio
async def test_scheduler_daemon_exits_on_stop_marker():
    """The scheduler daemon checks the marker every tick and exits cleanly
    (its flock is released by process exit); compute processes are never
    touched."""
    from cloudra.scheduler.daemon import SchedulerDaemon

    daemon = SchedulerDaemon(poll_interval=0.05)
    daemon_supervisor.request_daemons_shutdown(persist=True)
    await asyncio.wait_for(daemon.serve(), timeout=10)


# ------------------------------------------------------- web launcher kill


def test_terminate_runtime_escalates_to_sigkill():
    """A runtime child that ignores SIGTERM must be SIGKILLed and reaped —
    no fire-and-forget terminate."""
    from cloudra.web_launcher import _terminate_runtime

    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _terminate_runtime(proc, grace=0.3)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


# ---------------------------------------------------------- lifespan order


class EchoTools:
    async def execute(self, agent, call: ToolCall, **_kwargs):
        return ToolResult(is_success=True, summary=f"echo:{call.arguments.get('x')}", data={})


async def _wait_state(agent, state: AgentState, timeout: float = 5.0):
    await _wait_until(lambda: agent.state is state, timeout=timeout, what=f"state {state.value}")


@pytest.mark.asyncio
async def test_api_lifespan_shutdown_reclaims_all_activity_classes():
    """Shutdown with four live activity classes: two parked runner SSE turns
    (coordinator + supervisor), one detached finalize mid-summary, and the
    open SSE connections themselves.  After the lifespan exits: no registered
    runner/background execution survives, the SSE connections are closed
    (server tail writes fail), and no new LLM request fires afterwards."""
    server = _FakeLLMServer()
    sse_gate = threading.Event()
    summarizer_gate = asyncio.Event()
    summarizer = GatedSummarizer(gate=summarizer_gate)
    core = RuntimeCore(strict_events=True)

    def factory(settings, **_kwargs):
        return LLMClient(api_key="k", base_url=server.base_url, model="fake", timeout=30)

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=LegacyLLMProvider(client_factory=factory),
        tools=EchoTools(),
    )
    from cloudra.services.api_v2.app import create_v2_app

    app = create_v2_app(core, pipeline=pipeline)
    assert isinstance(core.runner, AgentRunner)
    core.runner.run_summarizer = summarizer
    bus = CommandBus(core)
    try:
        async with app.router.lifespan_context(app):
            await bus.execute(Command(type="project.create", payload={"name": "shutdown"}))
            project = next(iter(core.projects.values()))
            agents = []
            for role in ("coordinator", "supervisor"):
                result = await bus.execute(
                    Command(
                        type="agent.spawn",
                        target={"project_id": project.id},
                        payload={"role_id": role, "query": "work"},
                    )
                )
                agent = result.data
                agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
                agents.append(agent)
            # Both agents complete run 1 (ungated stream) and their detached
            # finalizes park inside the gated summarizer.
            for agent in agents:
                await _wait_state(agent, AgentState.SUCCEEDED)
            await _wait_until(lambda: summarizer.calls == 2, what="two parked finalizes")
            assert server.total_requests() == 2
            # Arm the SSE gate and re-wake both agents: run 2 parks mid-stream.
            server.sse_gate = sse_gate
            tail_baseline = len(server.tail_done)  # run-1 streams finished normally
            for agent in agents:
                await bus.execute(
                    Command(
                        type="agent.message",
                        target={"session_id": agent.id},
                        payload={"content": "again"},
                    )
                )
            await _wait_until(
                lambda: server.total_requests() >= 4, what="two parked SSE runs"
            )
        # ---- lifespan exited: watchdog stopped, admission closed, core.aclose ran
        assert core.runner._tasks == {}
        assert core.runner._background == {}
        # 停止准入：shutdown 后 runner 拒绝一切 schedule/唤醒重排。
        assert core.runner._accepting is False
        assert not [
            task
            for task in asyncio.all_tasks()
            if task.get_name().startswith("finalize:") and not task.done()
        ]
        # The parked SSE connections were closed abortively: once the gate
        # opens, the server's tail writes fail instead of succeeding.  The
        # wait must ignore run-1's already-completed tails (baseline above).
        sse_gate.set()
        summarizer_gate.set()
        await _wait_until(
            lambda: len(server.write_failures) >= 2
            or len(server.tail_done) > tail_baseline,
            timeout=5.0,
            what="server write outcome for both parked streams",
        )
        assert len(server.write_failures) >= 2, (
            f"shutdown did not close the in-flight SSE connections "
            f"(write_failures={server.write_failures}, tail_done={server.tail_done})"
        )
        # No new LLM request may fire after shutdown completed.
        counts = server.total_requests()
        deadline = asyncio.get_running_loop().time() + 0.3
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
        assert server.total_requests() == counts
        assert summarizer.calls == 2
    finally:
        sse_gate.set()
        summarizer_gate.set()
        for task in asyncio.all_tasks():
            if task.get_name().startswith("finalize:") and not task.done():
                task.cancel()
        server.close()


# ------------------------------------------------------------ cloudra stop


def test_stop_all_without_api_writes_marker_and_reports(monkeypatch, tmp_path):
    """无 API 在跑时：stop_all 落持久关停 marker、按 flock 探测报告守护状态，
    绝不碰计算进程（不存在计算库时报告 None）。"""
    monkeypatch.setattr("cloudra.services.shutdown.find_api_port", lambda: None)
    monkeypatch.setattr(
        "cloudra.scheduler.daemon.scheduler_lock_path",
        lambda: str(tmp_path / "scheduler.lock"),
    )
    monkeypatch.setattr(
        "cloudra.services.shutdown.kg_vec_lock_path",
        lambda: str(tmp_path / "kg_vec.lock"),
    )
    from cloudra.services.shutdown import stop_all

    report = stop_all(timeout=1.0)
    assert report["api_port"] is None
    assert report["api_stopped"] is None
    assert report["daemons"] == {"scheduler": "stopped", "kg_vec": "stopped"}
    assert report["compute_jobs_running"] is None
    assert Path(daemon_supervisor.daemons_stop_marker_path()).is_file()


def test_cli_stop_invokes_stop_all(monkeypatch):
    """`cloudra stop` 是最小显式全停入口：调用 stop_all 并打印复查报告。"""
    from click.testing import CliRunner

    import cloudra.cli as cli_mod

    calls = []

    def fake_stop_all(*, timeout=20.0):
        calls.append(timeout)
        return {
            "stop_marker": True,
            "api_port": None,
            "api_stopped": None,
            "daemons": {"scheduler": "stopped", "kg_vec": "stopped"},
            "compute_jobs_running": None,
        }

    monkeypatch.setattr("cloudra.services.shutdown.stop_all", fake_stop_all)
    result = CliRunner().invoke(cli_mod.cli, ["stop"])
    assert result.exit_code == 0, result.output
    assert calls == [20.0]
