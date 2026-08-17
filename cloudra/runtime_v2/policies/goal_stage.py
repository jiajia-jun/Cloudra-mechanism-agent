"""Goal anchor stage: pin the per-agent task goal into every LLM turn.

The legacy ``goal_set`` tool persists the goal to ``plan/{key}_goal.json``
(via ``agent_store_path``), but PromptAssembler never reads that file — in
legacy the goal reached the model only because the TUI also pinned it into the
ContextManager message list.  runtime_v2 has no ContextManager, so this stage
re-reads the file each turn and appends a fresh ``[Task goal]`` system
message.  Replace semantics come free: the file holds exactly one goal.

The UI routes (``/api/v2/agents/{id}/goal``) share ``read_goal`` /
``write_goal`` with this stage, so the tool, the stage and the UI all operate
on the same file.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult


def _store_proxy(agent) -> SimpleNamespace:
    # Same key as _LegacyAgentBridge (runtime_v2 uses agent.id as both the
    # legacy agent_id and session_id), so goal_set, this stage and the API
    # route all read/write one file.
    return SimpleNamespace(
        id=agent.id,
        conversation_id=agent.project_id,
        session_id=agent.id,
    )


def read_goal(agent) -> dict[str, Any] | None:
    from cloudra.tools.Plantool._store import agent_store_path, load_json

    goal = load_json(agent_store_path(_store_proxy(agent), "goal.json"), None)
    return goal if isinstance(goal, dict) and goal.get("objective") else None


def write_goal(agent, goal: dict[str, Any]) -> None:
    from cloudra.tools.Plantool._store import agent_store_path, save_json

    save_json(agent_store_path(_store_proxy(agent), "goal.json"), goal)


def format_goal(goal: dict[str, Any]) -> str:
    from cloudra.tools.Plantool.goal import GOAL_MARKER, GoalSet

    return GoalSet._format(goal) if goal.get("objective") else GOAL_MARKER


class GoalStage:
    """Pin the persisted goal anchor as a system message on every turn."""

    name = "goal"

    async def before_tool(self, ctx: PipelineContext, call) -> PolicyResult:
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None:
        goal = await asyncio.to_thread(read_goal, ctx.agent)
        from cloudra.tools.Plantool.goal import GOAL_MARKER

        # Defensive dedup: the anchor must appear exactly once in history.
        messages[:] = [
            m
            for m in messages
            if not (
                m.get("role") == "system"
                and str(m.get("content", "")).startswith(GOAL_MARKER)
            )
        ]
        content = format_goal(goal) if goal is not None else ""
        notices = getattr(ctx, "notices", None)
        if notices is not None:
            if content:
                notices.pin(ctx.agent.id, "goal", content)
            else:
                notices.unpin(ctx.agent.id, "goal")
            return
        if content:
            messages.append({"role": "system", "content": content})
