"""Goal anchor stage: pin the per-agent task goal into every LLM turn.

The legacy ``goal_set`` tool persists the goal to ``plan/{key}_goal.json``
(via ``agent_store_path``), but PromptAssembler never reads that file — in
legacy the goal reached the model only because the TUI also pinned it into the
legacy Agent message list.  runtime_v2 has no JSONL history file, so the goal
is re-read each turn and pinned into ``notices``；通知按「未应用变更按顺序
追加」进入上下文（Task 3）：未变化的 goal 不重复，更新/撤销以追加消息
表达，旧消息不重写。
Replace semantics come free: the file holds exactly one goal.

IO boundary (3d): the file read is shell-side — ``TurnPipeline``'s
``goal_reader`` callback reads the goal before stages run and hands it to
this stage via ``PipelineContext.goal`` (default: the built-in ``read_goal``
below; pass ``None`` to disable goal injection).  The stage itself is
IO-free; its decision (goal payload → injection text) is the pure
``resolve_goal_content``.  ``read_goal`` / ``write_goal`` remain the shared
file helpers for the shell default, the ``goal_set`` tool and the UI routes
(``/api/v2/agents/{id}/goal``), so all three operate on the same file.

The stage holds no state at all; the goal file on disk is the authority.
"""

from __future__ import annotations

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
    """Sync file IO — call it from a shell (or offload it), never on the loop."""
    from cloudra.tools.Plantool._store import agent_store_path, load_json

    goal = load_json(agent_store_path(_store_proxy(agent), "goal.json"), None)
    return goal if isinstance(goal, dict) and goal.get("objective") else None


def write_goal(agent, goal: dict[str, Any]) -> None:
    from cloudra.tools.Plantool._store import agent_store_path, save_json

    save_json(agent_store_path(_store_proxy(agent), "goal.json"), goal)


def format_goal(goal: dict[str, Any]) -> str:
    from cloudra.tools.Plantool.goal import GOAL_MARKER, GoalSet

    return GoalSet._format(goal) if goal.get("objective") else GOAL_MARKER


def resolve_goal_content(goal: dict[str, Any] | None) -> str:
    """Pure decision: goal payload (pre-read by the shell) → injection text."""
    return format_goal(goal) if goal is not None else ""


class GoalStage:
    """Pin the persisted goal anchor as a system message on every turn.

    Stateless and IO-free: the goal arrives pre-read on ``ctx.goal``.
    """

    name = "goal"

    async def before_tool(self, ctx: PipelineContext, call) -> PolicyResult:
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None:
        content = resolve_goal_content(ctx.goal)
        notices = getattr(ctx, "notices", None)
        if notices is not None:
            # 已撤销/更新的 goal 通过 notices 的追加消息表达（替代/撤销说明），
            # 不再过滤重写 history 里的旧 goal 消息（缓存前缀不变量）。
            if content:
                notices.pin(ctx.agent.id, "goal", content)
            else:
                notices.unpin(ctx.agent.id, "goal")
            return
        if content:
            messages.append({"role": "system", "content": content})
