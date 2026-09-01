"""DAG harness as a policy stage.

The stage wraps the deterministic dag/ engine (DagController) without making
the turn pipeline aware of graphs.  ``dag_record`` / ``dag_guided`` are just
the same stage enabled by the agent's settings.

State & side-effect declaration (3d):

- The graph itself is NOT stage state: the single authority is the project's
  ConversationDB (dag store, on-disk SQLite), so every restart rebuilds it
  losslessly.  ``_controllers`` is a **deliberately volatile**, lazily
  rebuilt cache of DagController instances (``_controller()`` recreates them
  on demand); dropping it on restart costs one reconstruction, nothing else.
- ``_subagent_windows`` (tool_call_id → delivery fingerprint) pairs one tool
  call's before/after within a live turn; it is meaningless once the turn
  dies, hence **deliberately volatile** and never restored.
- Side effects (SQLite via DagController, the supervisor's LLM loop,
  CommandBus spawn for the supervision shell) stay inside the stage by
  exemption: DagController is an imperative engine over its own durable
  store and the supervisor call is inherently IO, so purifying them into
  Decision/Effect objects would build a parallel command system for no
  recoverability gain — the recoverable state already lives in the dag store
  and the event log (the supervision shell's lifecycle is plain
  agent.spawned/state_changed events).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from cloudra.dag.controller import DagController
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall, ToolResult

logger = logging.getLogger(__name__)


class _SupervisionShell:
    """Project one supervision run onto a reusable shell agent session.

    The real work is GraphSupervisor's own loop inside DagController; this
    shell never goes through the LLM pipeline — it exists so the UI shows the
    Supervisor as a child agent (running → succeeded with a summary) instead
    of the parent looking frozen while the supervisor is awaited inline.

    ``self.shell`` is a **deliberately volatile** reference cache: the shell
    agent's actual lifecycle (spawn/restart/run start/finish) is event-sourced
    via CommandBus and AgentHost, so a restart rebuilds the agent from the
    log and a fresh shell would simply spawn again on the next supervision.
    """

    def __init__(self, core, parent) -> None:
        self.core = core
        self.parent = parent
        self.shell = None

    async def _publish_tail(self, before: int) -> None:
        for envelope in list(self.core.event_log)[before:]:
            await self.core.event_hub.publish(envelope)

    async def __call__(self, phase: str, trigger: str, result, error_note) -> None:
        core = self.core
        if phase == "start":
            if self.shell is None:
                from cloudra.runtime_v2.commands import CommandBus
                from cloudra.runtime_v2.schemas import Command

                spawned = await CommandBus(core).execute(
                    Command(
                        type="agent.spawn",
                        target={"project_id": self.parent.project_id},
                        payload={"role_id": "supervisor", "parent_session_id": self.parent.id},
                    )
                )
                # spawn 被拒时 data 是 {"error": ...}：壳投影不可用，督导本体
                # 仍照常运行，只是这一轮 UI 上没有子 agent 状态可显示。
                if spawned.accepted and hasattr(spawned.data, "state"):
                    self.shell = spawned.data
                else:
                    return
            before = len(core.event_log)
            if self.shell.state.value in {"succeeded", "failed", "cancelled"}:
                core.agent_host.restart(self.shell)
            core.agent_host.start_run(self.shell)
            await self._publish_tail(before)
            return
        shell = self.shell
        if shell is None:
            return
        content = self._summary(trigger, result, error_note)
        before = len(core.event_log)
        core.event_log.append(
            "agent.message_emitted",
            stream="agent",
            project_id=shell.project_id,
            session_id=shell.id,
            run_id=shell.current_run.run_id if shell.current_run else None,
            data={"sender": "supervisor", "content": content},
        )
        core.agent_host.finish_run(shell, outcome="failed" if error_note else "succeeded")
        await self._publish_tail(before)

    @staticmethod
    def _summary(trigger: str, result, error_note) -> str:
        if error_note:
            return f"Supervision ({trigger}) failed: {error_note}"
        if result is None:
            return f"Supervision ({trigger}) produced no result."
        accepted = sum(1 for m in result.mutations if m.get("accepted"))
        content = f"Supervision ({trigger}): rounds={result.rounds} mutations={accepted}/{len(result.mutations)}"
        if result.note:
            content += f" note={result.note}"
        report = getattr(result, "report", "") or ""
        if report.strip():
            content += f"\n{report.strip()}"
        return content


class DagPolicyStage:
    name = "dag"

    def __init__(self, core=None) -> None:
        self._controllers: dict[str, DagController] = {}
        # Optional kernel handle, used only for the v2-native "siblings still
        # running" check in the stop gate.  Tests without a core fall back to
        # the controller's own (legacy-table) background check.
        self._core = core
        # SubAgentLauncher/Swarm window: tool_call_id → (delivery revision, ref count)
        self._subagent_windows: dict[str, tuple[int, int]] = {}

    @staticmethod
    def _legacy_agent_id(role_id: str) -> str:
        """DAG 变更日志与 CallReview sidecar 使用 legacy 子 agent id（a-0..a-8）；
        v2 的 role_id 经此唯一映射推出（D13），launcher/swarm 两条 spawn 路径一致。"""
        from cloudra.subagents.registry import legacy_agent_id_for_role

        return legacy_agent_id_for_role(role_id)

    async def _controller(self, ctx: PipelineContext) -> DagController | None:
        mode = ctx.settings.orchestration_mode
        if mode.value == "standard":
            return None
        agent = ctx.agent
        controller = self._controllers.get(agent.id)
        if controller is None or controller.mode.value != mode.value:
            # 同步 SQLite init 必须卸载出事件循环线程（护栏告警/死锁根因）
            db = await asyncio.to_thread(lambda: ConversationDB(agent.project_id).init())
            supervisor = None
            if mode.value == "dag_guided":
                from cloudra.core.supervisor import GraphSupervisor

                supervisor = GraphSupervisor(
                    conversation_id=agent.project_id,
                    working_directory=ctx.workspace_dir,
                )
            controller = DagController(
                db,
                agent.id,
                mode,
                conversation_id=agent.project_id,
                working_directory=ctx.workspace_dir,
                agent_id=self._legacy_agent_id(agent.role_id),
                role_id=agent.role_id,
                supervisor=supervisor,
                on_supervision=_SupervisionShell(self._core, agent) if self._core is not None else None,
                core=self._core,
            )
            self._controllers[agent.id] = controller
        return controller

    def _has_running_siblings(self, ctx: PipelineContext) -> bool:
        """v2-native pending-background check for the stop gate.

        With sub-agents running, stop means "suspend until woken", not
        delivery — the legacy runtime made the same distinction via its
        subagent/compute/reminder tables.
        """
        if self._core is None:
            return False
        terminal = {"succeeded", "failed", "cancelled"}
        return any(
            a.id != ctx.agent.id
            and a.project_id == ctx.agent.project_id
            and a.state.value not in terminal
            for a in self._core.agents.values()
        )

    async def _audit_stop(self, ctx: PipelineContext, controller: DagController, call: ToolCall) -> PolicyResult:
        if self._has_running_siblings(ctx):
            return PolicyResult.allow()  # suspend, not delivery — no audit trail
        # D8.1：缺省不再声称 complete——只有显式 complete 才进入完成审计
        disposition = str(call.arguments.get("delivery_disposition") or "partial")
        allowed, report = await controller.audit_stop(disposition)
        if allowed:
            return PolicyResult.allow()
        gaps = [*(report.unresolved if report else []), *(report.inconclusive if report else [])]
        lines = [
            f"- {g.code} on {g.target_type} {g.target_id}: {g.detail}" for g in gaps[:12]
        ]
        message = (
            "Delivery declared complete but the coverage audit failed. "
            "Resolve the gaps (or re-declare with delivery_disposition='partial'):\n" + "\n".join(lines)
        )
        ctx.emit("dag.gate_blocked", {"gate": "delivery", "message": message, "tool": call.name})
        return PolicyResult.block(message)

    @staticmethod
    def _delivery_fingerprint(controller: DagController) -> tuple[int, int]:
        snapshot = controller.engine.snapshot()
        delivery = snapshot.delivery
        n_refs = sum(len(getattr(node, "refs", None) or []) for node in delivery.nodes)
        n_refs += sum(len(getattr(edge, "refs", None) or []) for edge in delivery.edges)
        return int(getattr(delivery, "revision", 0) or 0), n_refs

    @staticmethod
    def _apply_delivery_delta(ctx: PipelineContext, result: ToolResult, finished) -> None:
        line = None
        if finished is not None:
            summary_fn = getattr(finished, "summary_line", None)
            if callable(summary_fn):
                line = summary_fn()
        if not line:
            return
        combined = f"{result.summary}\n{line}".strip() if result.summary else line
        object.__setattr__(result, "summary", combined)
        notices = getattr(ctx, "notices", None)
        if notices is not None:
            notices.push(ctx.agent.id, line)

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        controller = await self._controller(ctx)
        if controller is None:
            return PolicyResult.allow()
        await controller.initialize()
        if call.name in {"SubAgentLauncher", "SubAgentSwarm"} and controller.mode.value == "dag_guided":
            self._subagent_windows[call.id] = await asyncio.to_thread(
                self._delivery_fingerprint, controller
            )
        if call.name == "stop":
            return await self._audit_stop(ctx, controller, call)
        disposition = await controller.check_substantive_gate(call.name, call.arguments)
        if disposition is None:
            return PolicyResult.allow()
        kind, message = disposition
        if kind == "block":
            ctx.emit("dag.gate_blocked", {"gate": self.name, "message": message, "tool": call.name})
            return PolicyResult.block(message)
        if kind == "warn":
            ctx.emit("agent.warning", {"code": "dag.gate.warn", "message": message})
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None:
        controller = await self._controller(ctx)
        if controller is None:
            return
        payload = {**(result.data or {}), "is_success": result.is_success}
        finished = await controller.on_tool_finished(
            call.id,
            call.name,
            call.arguments,
            payload,
        )
        self._apply_delivery_delta(ctx, result, finished)
        window = self._subagent_windows.pop(call.id, None)
        if (
            window is not None
            and controller.mode.value == "dag_guided"
            and call.name in {"SubAgentLauncher", "SubAgentSwarm"}
        ):
            after = await asyncio.to_thread(self._delivery_fingerprint, controller)
            if after != window:
                await controller.maybe_supervise("delivery_updated")

    async def on_run_end(self, agent, *, explicit_stop: bool) -> None:
        """D8.3：未调用 stop 的运行结束（最终消息路径）在 dag 模式下自动
        记录 partial——complete 只能来自被审计的显式 stop。"""
        if explicit_stop:
            return
        controller = self._controllers.get(agent.id)
        if controller is None or not controller.enabled:
            return
        try:
            await controller.record_unaudited_partial()
        except Exception:  # 收尾记录失败不能打崩 run 生命周期
            logger.warning("[DagPolicyStage] unaudited partial record failed", exc_info=True)

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None:
        controller = await self._controller(ctx)
        notices = getattr(ctx, "notices", None)
        if controller is None:
            if notices is not None:
                notices.unpin(ctx.agent.id, "dag")
            return
        projection = await controller.prompt_projection()
        if notices is not None:
            if projection:
                notices.pin(ctx.agent.id, "dag", projection)
            else:
                notices.unpin(ctx.agent.id, "dag")
            return
        if projection:
            messages.append({"role": "system", "content": projection})
