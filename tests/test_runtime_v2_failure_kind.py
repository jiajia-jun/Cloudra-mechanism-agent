"""失败分类（评审 5.10）：``run.finished.failure_kind`` 的结构化分流。

- 分类只由 ``failures.classify_failure`` 一处派生（无字符串判定、无正则）；
- 失败 run 必须带分类：漏传即 fail-loud，不落没有分流依据的终态；
- runner 的重试预算耗尽与永久拒绝落进不同的桶，重启中断同理。
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.failures import RunFailureKind, classify_failure, is_retryable
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.schemas import AgentState, Command
from cloudra.runtime_v2.turn_pipeline import TurnPipeline

# ------------------------------------------------------------------ 纯分类


class _Http402(Exception):
    status_code = 402


class _Http429(Exception):
    status_code = 429


class _Http503(Exception):
    status_code = 503


# 与 LLM SDK 无关的自造类型：分类只看异常的来源包，不 import SDK。
_ConnectError = type("ConnectError", (Exception,), {"__module__": "httpx"})
_ReadTimeout = type("ReadTimeout", (Exception,), {"__module__": "requests.exceptions"})


def test_classify_failure_uses_structured_signals_only():
    assert classify_failure(_Http402("Insufficient Balance")) is RunFailureKind.PROVIDER_PERMANENT
    assert classify_failure(_Http429("rate limited")) is RunFailureKind.PROVIDER_TRANSIENT_EXHAUSTED
    assert classify_failure(_Http503("upstream down")) is RunFailureKind.PROVIDER_TRANSIENT_EXHAUSTED
    assert classify_failure(_ConnectError("connection reset")) is RunFailureKind.PROVIDER_TRANSIENT_EXHAUSTED
    assert classify_failure(_ReadTimeout("read timed out")) is RunFailureKind.PROVIDER_TRANSIENT_EXHAUSTED
    assert classify_failure(EventPersistenceError("store write failed")) is RunFailureKind.EVENT_PERSISTENCE
    # 来源不明的异常不是 provider 的锅：落到 harness 自身的问题桶。
    assert classify_failure(KeyError("missing key")) is RunFailureKind.PIPELINE_INTERNAL
    assert classify_failure(RuntimeError("boom")) is RunFailureKind.PIPELINE_INTERNAL


def test_retryability_matches_the_classification():
    """可重试 ≠ 可原谅：永久拒绝不重试，事件落盘失败永不重试。"""
    assert is_retryable(_Http402("x")) is False
    assert is_retryable(_Http429("x")) is True
    assert is_retryable(EventPersistenceError("x")) is False


def test_every_kind_is_named_in_the_ui():
    """每个分类都必须有前端的下一步说明（否则用户只看到一条没出路的报错）。"""
    from pathlib import Path

    ts = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "failureKind.ts").read_text(
        encoding="utf-8"
    )
    for kind in RunFailureKind:
        assert f"{kind.value}:" in ts, f"frontend/src/failureKind.ts lacks {kind.value}"


# ------------------------------------------------------- run.finished 不变量


@pytest.mark.asyncio
async def test_failed_run_requires_a_structured_kind():
    """漏传分类的失败 run 立刻炸掉，且不落任何终态事件。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "kindless"}))
    project = next(iter(core.projects.values()))
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    await core.agent_host.start_run(agent)

    with pytest.raises(ValueError, match="failure_kind"):
        await core.agent_host.finish_run(agent, outcome="failed", error="boom")
    assert agent.state is AgentState.RUNNING
    assert not [e for e in core.event_log.query_session(agent.id) if e.type == "run.finished"]

    # 带上分类才允许收尾。
    await core.agent_host.finish_run(
        agent,
        outcome="failed",
        error="boom",
        failure_kind=RunFailureKind.PIPELINE_INTERNAL,
    )
    finished = [e for e in core.event_log.query_session(agent.id) if e.type == "run.finished"]
    assert finished[-1].data["failure_kind"] == "pipeline_internal"
    assert finished[-1].data["error"] == "boom"

    # 成功的 run 不背分类。
    await core.agent_host.restart(agent)
    await core.agent_host.start_run(agent)
    await core.agent_host.finish_run(agent, outcome="succeeded")
    finished = [e for e in core.event_log.query_session(agent.id) if e.type == "run.finished"]
    assert finished[-1].data["failure_kind"] is None


# ------------------------------------------------------------------- 端到端


class _FailingLLM:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls += 1
        raise self.exc


class _NeverCalledTools:
    """从不被调用的工具执行替身（签名对齐真实 executor，带 **_kwargs）。"""

    async def execute(self, agent, call, **_kwargs):
        raise AssertionError("no tool call should reach the executor in this test")


async def _run_to_failure(exc: Exception, *, max_turn_retries: int) -> tuple[RuntimeCore, object]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=_FailingLLM(exc),
        tools=_NeverCalledTools(),
    )
    core.runner = AgentRunner(core, pipeline, max_turn_retries=max_turn_retries, retry_backoff=(0.0,))
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "failure kind"}))
    project = next(iter(core.projects.values()))
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": "go"},
            )
        )
    ).data
    deadline = asyncio.get_running_loop().time() + 5.0
    while agent.state is not AgentState.FAILED:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}")
        await asyncio.sleep(0.01)
    return core, agent


@pytest.mark.asyncio
async def test_transient_provider_error_lands_in_the_exhausted_bucket():
    """5xx 走完重试预算 → provider_transient_exhausted（不是永久拒绝）。"""
    core, agent = await _run_to_failure(_Http503("upstream unavailable"), max_turn_retries=2)
    retries = [e for e in core.event_log.query_session(agent.id) if e.type == "run.retry"]
    assert len(retries) == 2
    finished = core.event_log.query_session(agent.id, types={"run.finished"})
    assert finished[-1].data["failure_kind"] == "provider_transient_exhausted"
    await core.reminders.close()


@pytest.mark.asyncio
async def test_event_persistence_failure_is_its_own_bucket():
    """事件落盘失败不可重试，且绝不与 provider 失败同桶。"""
    core, agent = await _run_to_failure(
        EventPersistenceError("event persistence failed for run.started: disk full"),
        max_turn_retries=3,
    )
    assert [e for e in core.event_log.query_session(agent.id) if e.type == "run.retry"] == []
    finished = core.event_log.query_session(agent.id, types={"run.finished"})
    assert finished[-1].data["failure_kind"] == "event_persistence"
    await core.reminders.close()
