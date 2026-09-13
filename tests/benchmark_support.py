"""benchmark 完整链路测试支撑件（Task 3/4/5/6 共用）。

组装生产 pipeline 的测试 fixture、按 role/session/run 驱动的 ScriptedLLM、
条件等待、失败时事件/DB/子进程日志收集。ScriptedLLM 的每步校验上一轮工具
回执——绝不盲按全局调用次数发下一条回复（并发不串脚本）。

测试契约：只替换 LLM 与外部引擎；RuntimeCore / CommandBus / AgentRunner /
TurnPipeline / InvocationService / LegacyToolExecutor / JS host / SQLite /
scheduler / guard / calculator 全部真实。
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentSession, InvocationProtocol, effective_invocation_protocol
from cloudra.runtime_v2.turn_pipeline import LLMResponse

# ---------------------------------------------------------------------------
# ScriptedLLM
# ---------------------------------------------------------------------------

@dataclass
class Receipt:
    """上一轮工具回执的校验器（按 agent 自己的 history 校验，不串会话）。"""

    tool: str
    is_success: Optional[bool] = None
    contains: list[str] = field(default_factory=list)


@dataclass
class Step:
    """一个轮次的脚本回复：js 程序 / traditional 工具调用 / 纯文本三选一。

    ``js`` 与 ``calls`` 的 args 都可以是 (core, agent) 工厂——用于裁决 id 等
    运行时才知道的参数（Supervisor 的 review_id/request_id、exit 审批
    approval_id），脚本内容由测试侧只读 DAG store 生成，裁决仍走生产工具。

    ``run`` 显式钉住第几个 run（1-based）：通知驱动的多 run agent（督导/父
    agent）用它避免"通知在 run 中途到达 → 多出一轮"把后续脚本错位。
    """

    turn: int
    run: Optional[int] = None
    js: Optional[str | Callable[[Any, Any], str]] = None
    calls: Optional[list[tuple[str, dict | Callable[[Any, Any], dict]]]] = None
    content: str = ""
    receipts: list[Receipt] = field(default_factory=list)
    # 脚本化崩溃：模拟"该 agent 这一轮彻底失败"（用于并发混合成功/失败场景）
    crash: str = ""


def js(turn: int, code, *, run: Optional[int] = None, expect: Optional[Receipt] = None) -> Step:
    """JS 协议：一段 QuickJS 程序（js_exec 线缆调用）。"""
    return Step(turn=turn, run=run, js=code, receipts=[expect] if expect else [])


def calls(turn: int, items: list[tuple[str, dict | Callable[[Any, Any], dict]]],
          *, run: Optional[int] = None, content: str = "",
          expect: Optional[Receipt] = None) -> Step:
    """traditional 协议：直接工具调用列表。args 可以是 (core, agent) 工厂。"""
    return Step(turn=turn, run=run, calls=items, content=content,
                receipts=[expect] if expect else [])


def text(turn: int, content: str, *, run: Optional[int] = None,
         expect: Optional[Receipt] = None) -> Step:
    """纯文本最终回复（触发统一结束门禁）。"""
    return Step(turn=turn, run=run, content=content, receipts=[expect] if expect else [])


def crash(turn: int, message: str, *, run: Optional[int] = None) -> Step:
    """脚本化本轮 LLM 调用失败（该 agent 的 run 落 failed）。"""
    return Step(turn=turn, run=run, crash=message)


class ScriptedLLM:
    """按 (role, project) 池、按 (role, session, run) 计轮次驱动。

    每步先校验上一轮工具回执（检查该 agent 自己 history 里的上一次
    assistant tool_calls 与对应 tool 消息），杜绝"盲按全局调用次数"发
    回复；脚本错位（轮次/工具/回执不符）fail-loud。
    """

    def __init__(self, core: Any = None) -> None:
        self.core = core
        self._pools: dict[tuple[str, str], list[Step]] = defaultdict(list)
        self._runs: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._turn_index: dict[tuple[str, str, str], int] = {}
        self.calls_seen: list[dict] = []

    def script(self, role: str, steps: list[Step], *, project: Optional[str] = None) -> None:
        self._pools[(role, project or "*")].extend(steps)

    def _project_name(self, agent: AgentSession) -> str:
        if self.core is None:
            return "*"
        project = self.core.projects.get(agent.project_id)
        return project.name if project is not None else "*"

    def _pick_step(self, steps: list[Step], *, run_index: int, turn: int) -> Step:
        """选取本 (run, turn) 的步骤：显式 run 精确匹配优先；池里存在显式
        run 步骤时不再回落到未限定条目（防错配）。"""
        explicit = [s for s in steps if s.run is not None]
        for candidate in list(steps):
            if candidate.turn != turn:
                continue
            if candidate.run is not None and candidate.run != run_index:
                continue
            if candidate.run is None and explicit:
                continue
            steps.remove(candidate)
            return candidate
        raise AssertionError(
            f"no scripted step for run={run_index} turn={turn}; "
            f"pool={[(s.run, s.turn) for s in steps]}; "
            f"calls_seen={[(c['role'], c['run_index'], c['turn']) for c in self.calls_seen[-24:]]}"
        )

    async def complete(self, agent: AgentSession, messages: list[dict], tools, **_kwargs) -> LLMResponse:
        run_id = agent.current_run.run_id if agent.current_run is not None else ""
        key = (agent.role_id, agent.id, run_id)
        turn = self._turn_index.get(key, 0) + 1
        self._turn_index[key] = turn
        agent_key = (agent.role_id, agent.id)
        runs = self._runs[agent_key]
        if run_id and run_id not in runs:
            runs.append(run_id)
        run_index = runs.index(run_id) + 1 if run_id in runs else 1
        self.calls_seen.append(
            {"role": agent.role_id, "session": agent.id, "run": run_id, "turn": turn,
             "run_index": run_index, "tools": list(tools or [])}
        )
        name = self._project_name(agent)
        pool = self._pools.get((agent.role_id, name)) or self._pools.get((agent.role_id, "*"))
        assert pool, f"no scripted step for role={agent.role_id} project={name}"
        step = self._pick_step(pool, run_index=run_index, turn=turn)
        if step.crash:
            raise RuntimeError(f"scripted failure for role={agent.role_id}: {step.crash}")
        self._check_receipts(agent, messages, step.receipts)
        protocol = effective_invocation_protocol(agent)
        if step.js is not None and protocol is not InvocationProtocol.JAVASCRIPT:
            raise AssertionError(
                f"script drift: role={agent.role_id} has a js_exec step but the run "
                f"protocol is {protocol.value}; a top-level business tool call would be "
                "misrouted silently"
            )
        if step.calls is not None and protocol is InvocationProtocol.JAVASCRIPT:
            from cloudra.tools.capabilities import is_direct_only

            business = [name for name, _ in step.calls if not is_direct_only(name)]
            if business:
                raise AssertionError(
                    f"script drift: role={agent.role_id} has business tool-call steps "
                    f"{business} but the run protocol is {protocol.value}; business calls "
                    "belong inside a js_exec program (direct controls like stop are fine)"
                )

        if step.js is not None:
            code = step.js(self.core, agent) if callable(step.js) else step.js
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id=f"js-{agent.id}-{turn}", name="js_exec",
                                     arguments={"code": code})],
            )
        if step.calls is not None:
            built = []
            for i, (tool_name, args) in enumerate(step.calls):
                if callable(args):
                    args = args(self.core, agent)
                built.append(
                    ToolCall(id=f"tc-{agent.id}-{turn}-{i}", name=tool_name, arguments=args)
                )
            return LLMResponse(content=step.content, tool_calls=built)
        return LLMResponse(content=step.content)

    @staticmethod
    def _last_exchange(messages: list[dict]) -> tuple[dict | None, dict[str, str]]:
        """最近一次 assistant tool_calls 及其后的 tool 回执（按 tool_call_id 索引）。"""
        assistant: dict | None = None
        results: dict[str, str] = {}
        for item in messages:
            role = item.get("role")
            if role == "assistant" and item.get("tool_calls"):
                assistant = item
                results = {}
                continue
            if role == "tool":
                content = item.get("content")
                if isinstance(content, list):  # vision parts
                    content = "".join(
                        str(part.get("text", "")) for part in content
                        if isinstance(part, dict)
                    )
                results[str(item.get("tool_call_id") or "")] = str(content or "")
        return assistant, results

    def _check_receipts(self, agent: AgentSession, messages: list[dict], receipts: list[Receipt]) -> None:
        if not receipts:
            return
        assistant, results = self._last_exchange(messages)
        assert assistant is not None, f"role={agent.role_id} turn expects receipts but has no tool exchange"
        by_name = {call.get("name"): call.get("id") for call in assistant.get("tool_calls", [])}
        for receipt in receipts:
            call_id = by_name.get(receipt.tool)
            assert call_id is not None, (
                f"role={agent.role_id}: expected tool {receipt.tool!r} in previous turn, "
                f"got {sorted(by_name)}"
            )
            content = results.get(call_id, "")
            if receipt.is_success is not None:
                try:
                    parsed = json.loads(content)
                    actual = bool(parsed.get("is_success"))
                except Exception:
                    actual = None
                assert actual == receipt.is_success, (
                    f"role={agent.role_id}: {receipt.tool} is_success={actual!r} "
                    f"expected {receipt.is_success}; content={content[:400]}"
                )
            for needle in receipt.contains:
                assert needle in content, (
                    f"role={agent.role_id}: {receipt.tool} result missing {needle!r}; "
                    f"content={content[:400]}"
                )


# ---------------------------------------------------------------------------
# 生产 pipeline 装配（app.py 同源接线；LLM 替换为测试脚本）
# ---------------------------------------------------------------------------


def assemble_live_pipeline(core: Any, llm: ScriptedLLM) -> tuple[Any, Any]:
    """生产接线：default_stages + LegacyToolExecutor + InvocationService +
    TurnPipeline + AgentRunner。"""
    from cloudra.runtime_v2.adapters import (
        LegacyPromptProvider,
        LegacyToolExecutor,
        legacy_default_runtime_settings,
    )
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.invocation import InvocationService
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    core.runtime_defaults = legacy_default_runtime_settings()
    stages = default_stages(core)
    executor = LegacyToolExecutor(core)
    invocations = InvocationService(
        event_writer=core.event_writer, stages=stages, tools=executor, agents=core.agents
    )
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=executor,
        prompt_provider=LegacyPromptProvider(),
        event_hub=core.event_hub,
        notices=core.notices,
        invocations=invocations,
    )
    runner = AgentRunner(core, pipeline, max_turn_retries=0, retry_backoff=())
    core.runner = runner
    return pipeline, runner


# ---------------------------------------------------------------------------
# 条件等待与失败取证
# ---------------------------------------------------------------------------

async def wait_until(predicate: Callable[[], bool], timeout: float = 30.0,
                     what: str = "condition") -> None:
    """轮询等待（步进 20ms）；超时给出可读原因。"""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timeout waiting for {what}")
        await asyncio.sleep(0.02)


def collect_failure(core: Any, workdirs: list[Path] | None = None) -> dict[str, Any]:
    """失败取证摘要：agent 状态、关键事件、guard 日志与 engine 记录（无密钥）。"""
    summary: dict[str, Any] = {"agents": {}, "events": []}
    for agent in getattr(core, "agents", {}).values():
        summary["agents"][agent.id] = {
            "role": agent.role_id,
            "state": agent.state.value,
            "project": agent.project_id,
        }
    for envelope in getattr(core, "event_log", []):
        if envelope.type in {
            "tool.requested", "tool.finished", "tool.blocked", "agent.message_emitted",
            "agent.state_changed", "agent.completion_gate", "run.finished",
        }:
            summary["events"].append({
                "type": envelope.type,
                "session": envelope.session_id,
                "data": str((envelope.data or {}))[:500],
            })
    for workdir in workdirs or []:
        run_dir = Path(workdir) / ".cloudra"
        if run_dir.is_dir():
            for log in sorted(run_dir.glob("guard-*.log")):
                summary.setdefault("guard_logs", {})[log.name] = _tail(log, 800)
            for log in sorted(run_dir.glob("calc-*.out.log")):
                summary.setdefault("calc_logs", {})[log.name] = _tail(log, 800)
    return summary


def _tail(path: Path, chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "<unreadable>"
    return text[-chars:]
