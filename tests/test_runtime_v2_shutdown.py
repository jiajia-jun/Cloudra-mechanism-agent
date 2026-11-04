"""Task 5 shutdown semantics (plan 2026-09-05-event-driven-supervisor, Task 5).

Covers:
- explicit daemons.stop marker and standalone scheduler exit;
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

import pytest

from cloudra.infra.llm_client import LLMClient
from cloudra.persistence import paths
from cloudra.runtime_v2.adapters import LegacyLLMProvider
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentState, Command, InvocationProtocol
from cloudra.runtime_v2.turn_pipeline import TurnPipeline
from tests.test_llm_cancellation import _FakeLLMServer
from tests.test_runtime_v2_cancellation import _wait_until


@pytest.mark.asyncio
async def test_scheduler_daemon_exits_on_stop_marker():
    """The scheduler daemon checks the marker every tick and exits cleanly
    (its flock is released by process exit); compute processes are never
    touched."""
    from cloudra.scheduler.daemon import SchedulerDaemon

    daemon = SchedulerDaemon(poll_interval=0.05)
    marker = paths.daemons_stop_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
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
    """Shutdown with live activity classes: two parked runner SSE turns
    (coordinator + supervisor) and the open SSE connections themselves.
    After the lifespan exits: no registered runner/background execution
    survives, the SSE connections are closed (server tail writes fail),
    and no new LLM request fires afterwards.

    （Task 4 注：原先的「detached finalize mid-summary」活动类随 per-run
    自动摘要管线一并删除——run 收尾不再发 LLM 摘要请求。）"""
    server = _FakeLLMServer()
    sse_gate = threading.Event()
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
            # Both agents complete run 1 (ungated stream).
            for agent in agents:
                await _wait_state(agent, AgentState.SUCCEEDED)
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
        # ---- lifespan exited: admission closed and core.aclose ran
        assert core.runner._tasks == {}
        assert core.runner._background == {}
        # 停止准入：shutdown 后 runner 拒绝一切 schedule/唤醒重排。
        assert core.runner._accepting is False
        # The parked SSE connections were closed abortively: once the gate
        # opens, the server's tail writes fail instead of succeeding.  The
        # wait must ignore run-1's already-completed tails (baseline above).
        sse_gate.set()
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
    finally:
        sse_gate.set()
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
    assert paths.daemons_stop_marker_path().is_file()


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


# ------------------------------------------------------- stop 升级路径（GH #38 兜底）


def _patch_stop_env(monkeypatch, tmp_path, *, healthy_after_shutdown: bool):
    """stop_all 的外部接触面全部打桩：找到 8000 上的 API、POST 已送达、
    健康探测按参数表现、守护锁不存在、等待只求值一次（不打真拍子）。"""
    monkeypatch.setattr("cloudra.services.shutdown.find_api_port", lambda: 8000)
    monkeypatch.setattr(
        "cloudra.services.shutdown.request_api_shutdown", lambda port: True
    )
    monkeypatch.setattr(
        "cloudra.services.shutdown.api_is_healthy",
        lambda port, **_: healthy_after_shutdown,
    )
    monkeypatch.setattr(
        "cloudra.services.shutdown._wait_for", lambda predicate, timeout: predicate()
    )
    monkeypatch.setattr(
        "cloudra.scheduler.daemon.scheduler_lock_path",
        lambda: str(tmp_path / "scheduler.lock"),
    )
    monkeypatch.setattr(
        "cloudra.services.shutdown.kg_vec_lock_path",
        lambda: str(tmp_path / "kg_vec.lock"),
    )


def test_stop_all_cooperative_shutdown_never_escalates(monkeypatch, tmp_path):
    """协作关停成功（健康端口随 lifespan 退出、进程死亡）时不触碰信号路径。"""
    _patch_stop_env(monkeypatch, tmp_path, healthy_after_shutdown=False)
    monkeypatch.setattr(
        "cloudra.services.shutdown._port_listener_pid", lambda port: 4242
    )
    monkeypatch.setattr("cloudra.services.shutdown._pid_alive", lambda pid: False)
    sent = []
    monkeypatch.setattr(
        "cloudra.services.shutdown._signal_pid",
        lambda pid, sig: sent.append(sig) or True,
    )
    from cloudra.services.shutdown import stop_all

    report = stop_all(timeout=0.5)
    assert sent == []
    assert report["api_stopped"] is True
    assert report["api_escalated"] is None


def test_stop_all_escalates_sigterm_when_cooperative_hangs(monkeypatch, tmp_path):
    """协作端点无响应（事件循环卡死/鉴权失败）：健康端口一直 200，直接对
    关停前锁定的归属 PID 信号升级。"""
    _patch_stop_env(monkeypatch, tmp_path, healthy_after_shutdown=True)
    monkeypatch.setattr(
        "cloudra.services.shutdown._port_listener_pid", lambda port: 4242
    )
    import signal as signal_mod

    sent = []
    monkeypatch.setattr(
        "cloudra.services.shutdown._signal_pid",
        lambda pid, sig: sent.append(sig) or True,
    )
    # SIGTERM 后进程死、端口不再应答
    monkeypatch.setattr(
        "cloudra.services.shutdown.api_is_healthy",
        lambda port, **_: not sent,
    )
    monkeypatch.setattr(
        "cloudra.services.shutdown._pid_alive", lambda pid: not sent
    )
    from cloudra.services.shutdown import stop_all

    report = stop_all(timeout=0.5)
    assert sent == [signal_mod.SIGTERM]
    assert report["api_escalated"] == "sigterm"
    assert report["api_stopped"] is True


def test_stop_all_escalates_when_process_survives_port_close(monkeypatch, tmp_path):
    """GH #38 的挂死形态：优雅关停先关监听（健康转失败）但进程被常驻 SSE
    排干拖死——排空窗口过后对关停前锁定的 PID 升级，SIGTERM 不动则 SIGKILL。
    绝不出现「报告已停止、进程还活着」。"""
    _patch_stop_env(monkeypatch, tmp_path, healthy_after_shutdown=False)
    monkeypatch.setattr(
        "cloudra.services.shutdown._port_listener_pid", lambda port: 4242
    )
    import signal as signal_mod

    sent = []
    monkeypatch.setattr(
        "cloudra.services.shutdown._signal_pid",
        lambda pid, sig: sent.append(sig) or True,
    )
    # 进程活到 SIGKILL 才死
    monkeypatch.setattr(
        "cloudra.services.shutdown._pid_alive",
        lambda pid: signal_mod.SIGKILL not in sent,
    )
    from cloudra.services.shutdown import stop_all

    report = stop_all(timeout=0.5)
    assert sent == [signal_mod.SIGTERM, signal_mod.SIGKILL]
    assert report["api_escalated"] == "sigkill"
    assert report["api_stopped"] is True


def test_stop_all_reports_failure_when_no_attributable_pid(monkeypatch, tmp_path):
    """定位不到端口归属 PID 时：如实报告未停止，绝不碰任何进程。"""
    _patch_stop_env(monkeypatch, tmp_path, healthy_after_shutdown=True)
    monkeypatch.setattr(
        "cloudra.services.shutdown._port_listener_pid", lambda port: None
    )
    sent = []
    monkeypatch.setattr(
        "cloudra.services.shutdown._signal_pid",
        lambda pid, sig: sent.append(sig) or True,
    )
    from cloudra.services.shutdown import stop_all

    report = stop_all(timeout=0.5)
    assert sent == []
    assert report["api_escalated"] is None
    assert report["api_stopped"] is False


@pytest.mark.asyncio
async def test_api_lifespan_leaves_scheduler_stop_marker_alone():
    from cloudra.services.api_v2.app import create_v2_app

    marker = paths.daemons_stop_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()

    app = create_v2_app(RuntimeCore(strict_events=True))
    async with app.router.lifespan_context(app):
        assert marker.is_file(), "a bare API must not clear a scheduler stop request"
    assert marker.is_file()


def test_cli_stop_reports_a_scheduler_that_did_not_exit(monkeypatch):
    from click.testing import CliRunner

    from cloudra.cli import cli

    monkeypatch.setattr(
        "cloudra.services.shutdown.stop_all",
        lambda **kwargs: {
            "stop_marker": True,
            "api_port": None,
            "api_stopped": None,
            "daemons": {"scheduler": "running"},
            "compute_jobs_running": None,
        },
    )
    result = CliRunner().invoke(cli, ["stop"])
    assert result.exit_code == 1
    assert "仍在运行" in result.output
