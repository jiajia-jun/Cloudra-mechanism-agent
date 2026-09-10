"""Unattended-mode guard: fail-closed block of human-interaction tools.

``RuntimeSettings.unattended`` marks an agent running with nobody to answer
(benchmark eval, GH #31). ``yolo`` only covers the permission/approval channel
(``PermissionStage``); ``ask_user`` bypasses it entirely —
``pending.request_interaction`` parks the agent in ``waiting_input`` forever,
which the benchmark backend then has to cancel as stuck. This stage blocks
``ask_user`` in ``before_tool`` before the executor and the pending broker are
reached, so the state machine can never park on a human that does not exist.

The block message is ordinary tool feedback (decision "continue"): the model
keeps working instead of hanging. The wire projection hides the tool too
(``tool_catalog._settings_hidden_tools``), so this stage is defense in depth
for misrouted calls, not the primary UX.
"""

from __future__ import annotations

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall

ASK_USER_TOOL = "ask_user"

_BLOCK_MESSAGE = (
    "[unattended] ask_user is unavailable in autonomous evaluation mode: there is "
    "no human who can answer. Decide autonomously from chemical principles and "
    "proceed with the best available course of action; if the task genuinely "
    "cannot be solved without external input, state that clearly in your final "
    "summary instead of asking."
)


class UnattendedStage:
    name = "unattended"

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        if call.name == ASK_USER_TOOL and ctx.settings.unattended:
            return PolicyResult.block(_BLOCK_MESSAGE)
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None:
        return None
