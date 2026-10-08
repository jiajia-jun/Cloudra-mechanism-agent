"""Per-agent routes (messages, lifecycle, goal, context) plus the skills list."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from cloudra.runtime_v2.schemas import Command, RuntimeSettingsPatch

from ..context import ApiContext
from ..models import (
    CancelPost,
    CommandResponse,
    CompactRequest,
    ContextInjectRequest,
    GoalSetRequest,
    MessagePost,
    RestartPost,
    _command_payload,
)
from ..views import agent_dict


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/agents/{session_id}", dependencies=ctx.protected)
    async def get_agent(session_id: str) -> dict[str, Any]:
        agent = ctx.core.require_agent(session_id)
        data = await asyncio.to_thread(agent_dict, ctx.core, agent)
        data["children"] = [
            child.id for child in ctx.core.agents.values() if child.parent_session_id == session_id
        ]
        return data

    @router.get("/api/v2/agents/{session_id}/transcript", dependencies=ctx.protected)
    async def agent_transcript(session_id: str) -> dict[str, Any]:
        agent = ctx.core.require_agent(session_id)
        messages = []
        events = await asyncio.to_thread(ctx.core.event_log.query_session, session_id)
        for event in events:
            if event.type in {"agent.message_injected", "agent.message_emitted"}:
                data = event.data
                messages.append(
                    {
                        "message_id": data.get("message_id"),
                        "sender": data.get("sender"),
                        "content": data.get("content"),
                        "event_id": event.event_id,
                        "created_at": event.created_at.isoformat(),
                    }
                )
        return {"session_id": session_id, "agent_id": agent.role_id, "messages": messages}

    @router.get("/api/v2/agents/{session_id}/events", dependencies=ctx.protected)
    async def agent_events(
        session_id: str,
        after: int = 0,
        before: Optional[int] = Query(default=None, ge=0),
        types: Optional[str] = Query(default=None),
        limit: int = Query(default=1000, ge=1, le=5000),
        tail: bool = Query(default=False),
    ) -> list[dict[str, Any]]:
        """Page through one session's events.

        ``tail=true`` returns the most recent ``limit`` events (optionally at
        or before the ``before`` session_seq cursor — used to page backwards
        from the newest end); ``tail=false`` pages forward from ``after``.
        """
        ctx.core.require_agent(session_id)
        wanted = [t.strip() for t in types.split(",") if t.strip()] if types else None
        events = await asyncio.to_thread(
            ctx.core.event_log.query_session,
            session_id,
            after_session_seq=after,
            before_session_seq=before,
            types=wanted,
            limit=limit,
            tail=tail,
        )
        return [event.model_dump(mode="json") for event in events]

    @router.get("/api/v2/agents/{session_id}/events/{event_id}", dependencies=ctx.protected)
    async def agent_event_detail(session_id: str, event_id: str) -> dict[str, Any]:
        ctx.core.require_agent(session_id)
        event = await asyncio.to_thread(ctx.core.event_log.get, event_id)
        if event is None or event.session_id != session_id:
            raise HTTPException(status_code=404, detail="event not found")
        return event.model_dump(mode="json")

    @router.post("/api/v2/agents/{session_id}/messages", dependencies=ctx.protected)
    async def inject_message(session_id: str, body: MessagePost) -> CommandResponse:
        command = Command(
            type="agent.message",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)

    @router.post("/api/v2/agents/{session_id}/cancel", dependencies=ctx.protected)
    async def cancel_agent(session_id: str, body: CancelPost) -> CommandResponse:
        command = Command(
            type="agent.cancel",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)

    @router.post("/api/v2/agents/{session_id}/restart", dependencies=ctx.protected)
    async def restart_agent(session_id: str, body: RestartPost) -> CommandResponse:
        command = Command(
            type="agent.restart",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)

    @router.patch("/api/v2/agents/{session_id}/settings", dependencies=ctx.protected)
    async def patch_agent_settings(session_id: str, patch: RuntimeSettingsPatch) -> CommandResponse:
        command = Command(
            type="agent.settings_update",
            target={"session_id": session_id},
            payload=patch.model_dump(exclude_unset=True),
        )
        return await ctx.execute(command)

    @router.get("/api/v2/agents/{session_id}/goal", dependencies=ctx.protected)
    async def get_goal(session_id: str) -> dict[str, Any]:
        from cloudra.runtime_v2.policies.goal_stage import read_goal

        agent = ctx.core.require_agent(session_id)
        return {"goal": await asyncio.to_thread(read_goal, agent)}

    @router.post("/api/v2/agents/{session_id}/goal", dependencies=ctx.protected)
    async def set_goal(session_id: str, body: GoalSetRequest) -> dict[str, Any]:
        from cloudra.runtime_v2.policies.goal_stage import write_goal

        agent = ctx.core.require_agent(session_id)
        goal = body.model_dump()
        await asyncio.to_thread(write_goal, agent, goal)
        return {"goal": goal}

    @router.post("/api/v2/agents/{session_id}/compact", dependencies=ctx.protected)
    async def compact_agent(session_id: str, body: CompactRequest) -> CommandResponse:
        command = Command(
            type="agent.compact",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)

    @router.post("/api/v2/agents/{session_id}/context/inject", dependencies=ctx.protected)
    async def inject_context(session_id: str, body: ContextInjectRequest) -> CommandResponse:
        """Lightweight context injection (pin/unpin/push a notice).

        The notice reaches the agent's next LLM turn as a system message and
        lands in the event log (context.pin_set / pin_cleared / injected) —
        auditable, replayable, no wakeup.  Use /messages when a wakeup is
        wanted.
        """
        command = Command(
            type="context.inject",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        # Validate here (not only in the command handler) so an unknown agent
        # surfaces as 404 instead of an accepted=false 200.
        ctx.core.require_agent(session_id)
        return await ctx.execute(command)

    @router.get("/api/v2/agents/{session_id}/context", dependencies=ctx.protected)
    async def agent_context_stats(session_id: str) -> dict[str, Any]:
        """Read-only per-agent context usage, derived from the session events.

        ``tokens`` is an estimate over persisted event text; the exact current
        context size is ``last_prompt_tokens`` from the latest LLM call.
        """
        from cloudra.infra.token_estimator import TokenEstimator

        ctx.core.require_agent(session_id)

        def _collect() -> tuple[dict[str, dict[str, int]], int | None]:
            """逐事件 token 估算（同步 DB 查询 + 计数循环），只经 to_thread 调用。"""
            by_role: dict[str, dict[str, int]] = {
                role: {"messages": 0, "tokens": 0} for role in ("user", "assistant", "tool")
            }
            last_prompt_tokens: int | None = None
            for event in ctx.core.event_log.iter_events(
                session_id=session_id,
                types={"agent.message_injected", "agent.message_emitted", "tool.finished", "llm.completed"},
            ):
                if event.type in {"agent.message_injected", "agent.message_emitted"}:
                    role = "user" if event.type == "agent.message_injected" else "assistant"
                    text = str(event.data.get("content") or "")
                elif event.type == "tool.finished":
                    role = "tool"
                    text = str(event.data.get("result_summary") or "")
                elif event.type == "llm.completed":
                    usage = event.data.get("usage") or {}
                    if usage.get("prompt_tokens"):
                        last_prompt_tokens = int(usage["prompt_tokens"])
                    continue
                else:
                    continue
                by_role[role]["messages"] += 1
                by_role[role]["tokens"] += TokenEstimator.count_text(text)
            return by_role, last_prompt_tokens

        # 全量事件扫描 + 逐条计数是同步重活，卸载出事件循环。
        by_role, last_prompt_tokens = await asyncio.to_thread(_collect)
        return {
            "session_id": session_id,
            "messages": sum(bucket["messages"] for bucket in by_role.values()),
            "tokens": sum(bucket["tokens"] for bucket in by_role.values()),
            "by_role": by_role,
            "last_prompt_tokens": last_prompt_tokens,
        }

    @router.get("/api/v2/skills", dependencies=ctx.protected)
    async def list_skills() -> list[dict[str, Any]]:
        from cloudra.base.skill_class import skill_loader

        return await asyncio.to_thread(skill_loader().skill_datas_get)

    return router
