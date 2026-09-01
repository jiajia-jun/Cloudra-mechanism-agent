"""Autonomous schedule mode stage.

When `agent.settings.schedule_mode` is True:
- Pins an autonomous schedule reminder into system messages via `notices.pin(agent.id, "schedule_mode", ...)`
- Intercepts `stop` tool calls:
  - If a reminder is active (`core.reminders.pending(agent.id)` is truthy): allows `stop` so the agent can sleep until woken.
  - If no reminder is active:
    - On first attempt: blocks `stop`, instructs the model to either call `schedule(DurationSeconds=..., Prompt=...)` or verify completion and call `stop` again.
    - On second consecutive `stop` attempt: allows `stop` as explicit confirmation that the goal is 100% complete.
  - Calling any tool other than `stop` resets the confirmation tracker.
"""

from __future__ import annotations

from typing import Any

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall, ToolResult

SCHEDULE_NOTICE = (
    "[AUTONOMOUS SCHEDULE MODE ACTIVE]\n"
    "You are running in autonomous schedule mode.\n"
    "- If tasks, calculations, or simulations are in progress (or if you submitted background jobs via "
    "submit_compute_job, SSH/Slurm sbatch, background scripts, or multi-step experiments), you MUST call "
    "`schedule(DurationSeconds=<seconds>, Prompt='<wake up instruction>')` to set a wake-up timer before stopping.\n"
    "- Do not stop without a pending schedule timer while work is ongoing.\n"
    "- If and only if the user's objective is 100% achieved and fully verified, confirm your conclusions and call `stop`."
)

INTERCEPT_MESSAGE = (
    "Stop intercepted by Schedule Mode: You have no active wake-up timer scheduled.\n"
    "Either:\n"
    "1. If background jobs/simulations/tasks are still running or future checks are needed, call "
    "schedule(DurationSeconds=..., Prompt='...') now to schedule your next wake-up.\n"
    "2. If the user's goal is 100% completed and fully verified, call stop again to confirm completion."
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

        # No pending reminder: check if this is a consecutive stop (confirmation)
        if ctx.agent.id in self._intercepted_stops:
            # Agent explicitly re-called stop after receiving the intercept instruction
            self._intercepted_stops.discard(ctx.agent.id)
            return PolicyResult.allow()

        # First stop attempt without a schedule: block it!
        self._intercepted_stops.add(ctx.agent.id)
        return PolicyResult.block(INTERCEPT_MESSAGE)

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
