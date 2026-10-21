"""Three-arm ablation behaviour (standard / dag_record / dag_guided)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from cloudra.runtime_v2.schemas import OrchestrationMode
from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema


class _Settings:
    def __init__(self, mode: OrchestrationMode) -> None:
        self.orchestration_mode = mode


class _Agent:
    def __init__(self, mode: OrchestrationMode) -> None:
        self.settings = _Settings(mode)
        self.working_directory = "/tmp"
        self.conversation_id = "conv-test"


def _call(orchestration: OrchestrationMode, **kwargs):
    tool = TsGuess(subagent=_Agent(orchestration))
    return asyncio.run(tool.tool_call(TsGuess_input_schema(**kwargs), None))


def test_standard_mode_disables_verification():
    out = _call(OrchestrationMode.STANDARD, mode="verify", freq_log="freq.log")
    assert out.is_success is False
    assert "disabled in standard orchestration mode" in (out.message or "")


def test_standard_mode_disables_strict_verification():
    out = _call(OrchestrationMode.STANDARD, mode="verify", freq_log="freq.log", strict=True)
    assert out.is_success is False
    assert "disabled in standard orchestration mode" in (out.message or "")


def test_guided_mode_does_not_apply_the_standard_gate():
    out = _call(OrchestrationMode.DAG_GUIDED, mode="verify", freq_log="/nonexistent/freq.log")
    assert "disabled in standard orchestration mode" not in (out.message or "")


def test_with_orchestration_mode_forces_the_arm():
    from cloudra.benchmark.runner import load_tasks, with_orchestration_mode

    tasks = load_tasks(Path("ideapool/tasks/easy"))[:2]
    forced = with_orchestration_mode(tasks, OrchestrationMode.DAG_RECORD)
    assert len(forced) == len(tasks)
    assert all(t.prompt.orchestration_mode is OrchestrationMode.DAG_RECORD for t in forced)
    # the source task objects are untouched
    assert all(t.prompt.orchestration_mode is not OrchestrationMode.DAG_RECORD
               for t in tasks if t.prompt.orchestration_mode is not OrchestrationMode.DAG_RECORD)
