"""Autonomous schedule mode stage.

When `agent.settings.schedule_mode` is True:
- Pins an autonomous schedule reminder into system messages via `notices.pin(agent.id, "schedule_mode", ...)`
- Intercepts `stop` tool calls (in-turn nudge, side-effect-free):
  - If a reminder is active (`core.reminders.pending(agent.id)` is truthy): allows `stop` so the agent can sleep until woken.
  - If no reminder is active:
    - On first attempt: blocks `stop`, instructs the model to either call `schedule` (timer or check_command) or verify completion and call `stop` again.
    - On second consecutive `stop` attempt: allows `stop` so the run-end gate sees the exit attempt.
  - Calling any tool other than `stop` resets the confirmation tracker.
- Run-end fact check (`audit_run_end`, Task 4A 统一结束门禁): both explicit
  stops admitted by the handshake and plain-text final replies reach the same
  runner-side boundary.  The handshake's second-stop self-confirmation is NOT
  completion evidence (计划 §6) — the gate re-evaluates verifiable facts:
    owned compute on a non-coordinator session or a pending reminder →
    wait_background (a real wake-up source); other verifiable background work
    without a reminder → continue_work (schedule a wake-up first); nothing pending →
  allow_final explicitly labelled agent-declared, not independently verified.
"""

from __future__ import annotations

from typing import Any

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall, ToolResult

SCHEDULE_NOTICE = (
    "[AUTONOMOUS SCHEDULE MODE ACTIVE]\n"
    "You are running in autonomous schedule mode.\n"
    "- For your own jobs submitted through submit_compute_job, a non-coordinator session can stop and wait for "
    "the automatic terminal notification; an extra schedule is unnecessary. Coordinator compute notifications "
    "are stored without waking the coordinator.\n"
    "- For other background work (including SSH/Slurm sbatch, background scripts, multi-step experiments, "
    "or a coordinator waiting directly on compute), call `schedule` before stopping. Prefer a read-only "
    "`check_command` plus `interval_seconds` and a timeout "
    "(e.g. `test -f job.log && grep -q 'Normal termination' job.log`, or `ssh <login> 'squeue -j <id>'`) "
    "so you wake when the work is actually done; `delay_seconds` / `wake_at` alone is the fallback timer.\n"
    "- While work is ongoing, stop only when an automatic compute notification or a pending schedule provides a wake-up.\n"
    "- If and only if the user's objective is 100% achieved and fully verified, confirm your conclusions and call `stop`."
)

INTERCEPT_MESSAGE = (
    "Stop intercepted by Schedule Mode: You have no active wake-up timer or check scheduled.\n"
    "Either:\n"
    "1. If background jobs/simulations/tasks are still running or future checks are needed, call "
    "schedule with check_command+interval_seconds+timeout_seconds (preferred) or delay_seconds+message "
    "now to schedule your next wake-up.\n"
    "2. If the user's goal is 100% completed and fully verified, call stop again to confirm completion."
)

BACKGROUND_WITHOUT_WAKEUP_MESSAGE = (
    "Verifiable background work is still pending (a sub-agent is not terminal or a "
    "compute job is unfinished) but no wake-up timer or check is scheduled. Call "
    "`schedule` with a read-only check_command + interval_seconds + timeout_seconds "
    "(preferred) or delay_seconds + message so you wake when the work is actually "
    "done, then stop. Re-confirming stop does not mark the goal complete — without "
    "a scheduled wake-up this run cannot end."
)

DECLARED_COMPLETION_REASON = (
    "schedule mode: no verifiable background work pending; the run ends as an "
    "agent-declared completion (not independently verified)"
)


class ScheduleStage:
    """Enforce autonomous schedule wake-up timers before stopping.

    ``_intercepted_stops`` is **deliberately volatile** (shell-private,
    discarded on restart): it tracks the in-dialogue confirmation handshake
    "first stop blocked → immediate second stop confirms completion", which
    only makes sense against a live run's conversation.  A restarted process
    rebuilds the agent's context from scratch, so a stale pre-restart
    intercept must NOT count as confirmation — otherwise the first stop after
    a restart would slip through unaudited.  The pending-reminder check itself
    reads ``core.reminders``' event projection, which is restart-safe.
    """

    name = "schedule"

    def __init__(self, core=None) -> None:
        self.core = core
        self._intercepted_stops: set[str] = set()

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        if not getattr(ctx.agent.settings, "schedule_mode", False):
            self._intercepted_stops.discard(ctx.agent.id)
            return PolicyResult.allow()

        if call.name != "stop":
            # Reset consecutive stop intercept tracker when agent performs any other tool action
            self._intercepted_stops.discard(ctx.agent.id)
            return PolicyResult.allow()

        # Call is "stop": check if there is an active pending reminder
        core = self.core
        has_pending_reminder = False
        if core is not None and hasattr(core, "reminders"):
            try:
                has_pending_reminder = bool(core.reminders.pending(ctx.agent.id))
            except Exception:
                has_pending_reminder = False

        if has_pending_reminder:
            # Active reminder exists: allow stop so agent suspends and sleeps
            self._intercepted_stops.discard(ctx.agent.id)
            return PolicyResult.allow()

        if await self._owned_compute_pending(ctx):
            # The compute broker provides a durable wake when this agent's
            # submitted jobs finish; a timer would only cause extra LLM runs.
            self._intercepted_stops.discard(ctx.agent.id)
            return PolicyResult.allow()

        # No pending reminder: check if this is a consecutive stop (confirmation)
        if ctx.agent.id in self._intercepted_stops:
            # Agent explicitly re-called stop after receiving the intercept instruction
            self._intercepted_stops.discard(ctx.agent.id)
            return PolicyResult.allow()

        # First stop attempt without a schedule: block it!
        self._intercepted_stops.add(ctx.agent.id)
        return PolicyResult.block(INTERCEPT_MESSAGE)

    async def audit_run_end(
        self,
        ctx: PipelineContext,
        *,
        explicit_stop: bool,
        stop_arguments: dict[str, Any] | None = None,
    ):
        """统一结束门禁的 schedule 判定（runner 收尾前；纯文本最终回复与显式
        stop 同边界，计划 §6）。

        唤醒来源必须可核实：有效 reminder（ReminderBroker 事件投影）、未终态
        子 agent（core.agents 投影）、在算作业（compute.db 权威）。模型的
        "有后台脚本在跑"声明不算数——没有可核实唤醒来源就要求先 schedule。
        """
        from cloudra.dag.stop_audit import StopGate

        core = self.core
        if await self._owned_compute_pending(ctx):
            return StopGate(
                action="wait_background",
                reason="this agent's compute jobs are still active; terminal notifications will wake it",
                basis="background_wait",
            )
        if not getattr(ctx.agent.settings, "schedule_mode", False):
            return None
        if core is not None and core.reminders.pending(ctx.agent.id):
            return StopGate(
                action="wait_background",
                reason="a schedule reminder is pending; the stop suspends until it fires",
                basis="background_wait",
            )
        if core is not None and await self._verifiable_background_pending(ctx):
            return StopGate(
                action="continue_work",
                reason=BACKGROUND_WITHOUT_WAKEUP_MESSAGE,
            )
        return StopGate(action="allow_final", reason=DECLARED_COMPLETION_REASON, basis="declared")

    async def _owned_compute_pending(self, ctx: PipelineContext) -> bool:
        if self.core is None or ctx.agent.role_id == "coordinator":
            # ComputeNotifyBroker deliberately parks coordinator notices;
            # it cannot use an owned job as an automatic wake source.
            return False
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.compute_store import acount_waitable_compute_jobs_for_session

        return bool(await acount_waitable_compute_jobs_for_session(
            ComputeDB(), ctx.agent.project_id, ctx.agent.id
        ))

    async def _verifiable_background_pending(self, ctx: PipelineContext) -> bool:
        from cloudra.dag.stop_audit import has_running_siblings, pending_compute_jobs_exist
        from cloudra.persistence.database import ConversationDB

        core = self.core
        if has_running_siblings(
            core, project_id=ctx.agent.project_id, session_id=ctx.agent.id
        ):
            return True
        return await pending_compute_jobs_exist(
            data_dir=ConversationDB(ctx.agent.project_id).data_dir,
            project_id=ctx.agent.project_id,
        )

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None:
        notices = getattr(ctx, "notices", None)
        enabled = bool(getattr(ctx.agent.settings, "schedule_mode", False))

        if notices is not None:
            if enabled:
                notices.pin(ctx.agent.id, "schedule_mode", SCHEDULE_NOTICE)
            else:
                notices.unpin(ctx.agent.id, "schedule_mode")
            return

        if enabled:
            messages.append({"role": "system", "content": SCHEDULE_NOTICE})
