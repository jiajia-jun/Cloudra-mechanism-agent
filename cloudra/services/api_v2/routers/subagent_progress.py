"""Scoped progress and bounded public history for Cloudra Subagent."""

from __future__ import annotations

import asyncio
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from cloudra.persistence.database import ComputeDB
from cloudra.persistence.paths import project_workspace_dir
from cloudra.runtime_v2.agent_host import is_background_parked
from cloudra.runtime_v2.js_runtime import filter_history
from cloudra.runtime_v2.observability import scoped_tool_receipts
from cloudra.runtime_v2.schemas import AgentState, CommandRejected, utc_now
from cloudra.services.compute_store import ACTIVE_STATES, _db_ready, list_compute_jobs
from cloudra.services.subagent_schema import AgentContext, HistoryLimit, ProjectProgress, TranscriptFilter

from ..context import ApiContext

_EXCERPT_LIMIT = 2000
_PROCESS_LIMIT = 8000
_HISTORY_SCAN_LIMIT = 500
_PUBLIC_HISTORY = {
    "agent.message_emitted": "assistant",
    "agent.message_injected": "incoming",
    "agent.thinking": "reasoning",
    "tool.requested": "tool",
    "llm.failed": "error",
    "run.finished": "error",
}


class AgentProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    limit: HistoryLimit = 1
    filter: TranscriptFilter | None = None
    include_reasoning: bool = Field(default=False, strict=True)


def _excerpt(text: str, limit: int) -> dict:
    return {"text": text[:limit], "truncated": len(text) > limit}


def _process_excerpt(workspace_dir: str | None, project_id: str) -> dict | None:
    root = Path(workspace_dir) if workspace_dir else project_workspace_dir(project_id)
    try:
        fd = os.open(root / "PROCESS.md", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, encoding="utf-8", errors="replace") as notes:
            info = os.fstat(notes.fileno())
            if not stat.S_ISREG(info.st_mode):
                return None
            text = notes.read(_PROCESS_LIMIT + 1)
    except OSError:
        return None
    return {
        **_excerpt(text, _PROCESS_LIMIT),
        "updated_at": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
    }


def _progress_rows(core, project_id, agents, boundaries, questions, approvals):
    db = ComputeDB()
    jobs_by_agent: dict[str, list[int]] = {}
    if _db_ready(db):
        for job in list_compute_jobs(db, conversation_id=project_id, states=ACTIVE_STATES):
            jobs_by_agent.setdefault(job["session_id"], []).append(job["id"])

    pending_by_agent: dict[str, list[dict]] = {}
    for row in questions:
        pending_by_agent.setdefault(row["session_id"], []).append({
            "kind": "question", "session_id": row["session_id"],
            "interaction_id": row["interaction_id"], "prompt": row["prompt"],
        })
    for row in approvals:
        pending_by_agent.setdefault(row["session_id"], []).append({
            "kind": "approval", "session_id": row["session_id"], "approval_id": row["id"],
            "summary": row["risk_summary"] or row["tool_name"],
        })

    rows, pending = [], []
    for agent in agents:
        boundary = boundaries.get(agent.id, 0)
        run_id = agent.current_run.run_id if agent.current_run else None
        items = pending_by_agent.get(agent.id, [])
        detail = agent.current_task
        activity = agent.state.value
        if is_background_parked(core, agent, before_session_seq=boundary):
            activity = "waiting_background"
        elif agent.state is AgentState.SUCCEEDED:
            activity = "idle"
        elif agent.state is AgentState.WAITING_APPROVAL and run_id is not None:
            transitions = core.event_log.query_session(
                agent.id, run_id=run_id, types={"agent.state_changed"},
                before_session_seq=boundary, limit=1,
            )
            if transitions and transitions[-1].data.get("reason") == "wait_review":
                activity = "waiting_review"

        if activity in {"waiting_background", "waiting_review"}:
            gates = core.event_log.query_session(
                agent.id, run_id=run_id, types={"agent.completion_gate"},
                before_session_seq=boundary, limit=1,
            )
            if gates:
                detail = gates[-1].data.get("reason")
        if activity == "waiting_review":
            items.append({"kind": "review", "session_id": agent.id, "summary": detail or ""})
        if items and activity in {"waiting_approval", "waiting_input"}:
            detail = items[0].get("prompt") or items[0].get("summary") or detail
        rows.append({
            "session_id": agent.id,
            "name": agent.display_name,
            "role_id": agent.role_id,
            "parent_session_id": agent.parent_session_id,
            "activity": activity,
            "detail": _excerpt(detail, _EXCERPT_LIMIT)["text"] if detail else None,
            "updated_at": agent.updated_at.isoformat(),
            "active_job_ids": jobs_by_agent.get(agent.id, []),
        })
        pending.extend(items)
    return rows, pending


async def _read_progress(ctx: ApiContext, project_id: str, session_id: str | None = None):
    core = ctx.core
    async with core.command_lock, core.event_writer._lock:
        project = core.require_project(project_id)
        if session_id is None:
            agents = core.list_project_agents(project_id)
        else:
            agent = core.require_agent(session_id)
            if agent.project_id != project_id:
                raise CommandRejected("not_found", "Agent session does not belong to this project.")
            agents = [agent]
        agents = [agent.model_copy(deep=True) for agent in agents]
        boundaries = (
            core.event_log.durable_metadata()["sessions"] if core.store is not None
            else core.event_log.high_session_watermarks
        )
        questions = core.pending.list_pending_interactions(project_id)
        approvals = core.pending.list_pending_approvals(project_id)
        workspace_dir = project.workspace_dir
    rows, pending = await asyncio.to_thread(
        _progress_rows, core, project_id, agents, boundaries, questions, approvals,
    )
    return rows, pending, workspace_dir, boundaries.get(session_id, 0)


async def project_progress(ctx: ApiContext, project_id: str, include_process: bool = True) -> dict:
    agents, pending, workspace_dir, _ = await _read_progress(ctx, project_id)
    process = (
        await asyncio.to_thread(_process_excerpt, workspace_dir, project_id) if include_process else None
    )
    return {
        "project_id": project_id, "observed_at": utc_now().isoformat(), "agents": agents,
        "pending": pending, "process": process,
    }


def _history(core, session_id: str, body: AgentProgressRequest, boundary: int) -> tuple[list[dict], bool]:
    types = {"agent.message_emitted"} if body.filter is None else set(_PUBLIC_HISTORY) - {"agent.thinking"}
    if body.include_reasoning:
        types.add("agent.thinking")

    cap = _HISTORY_SCAN_LIMIT + 1 if body.filter is not None else body.limit
    log = core.event_log
    candidates = []
    before = boundary
    while len(candidates) < cap:
        page = log.query_session(session_id, types=types, before_session_seq=before, limit=cap)
        if not page:
            break
        candidates.extend(
            event for event in reversed(page)
            if event.type != "run.finished" or event.data.get("outcome") == "failed"
        )
        before = page[0].session_seq - 1
        if len(page) < cap:
            break

    truncated = len(candidates) > _HISTORY_SCAN_LIMIT
    events = candidates[:_HISTORY_SCAN_LIMIT][::-1]
    receipts = {
        row["request_event_id"]: row for row in scoped_tool_receipts(
            log, session_id, [event for event in events if event.type == "tool.requested"],
            boundary, summary_limit=_EXCERPT_LIMIT,
        )
    }
    entries = []
    for event in events:
        receipt = receipts.get(event.event_id)
        if receipt is not None:
            excerpt = {
                "text": receipt["result_summary"] or "",
                "truncated": receipt.get("summary_truncated", False),
            }
        elif event.type == "llm.failed":
            excerpt = {"text": "Model request failed.", "truncated": False}
        elif event.type == "run.finished":
            kind = event.data.get("failure_kind")
            excerpt = _excerpt(f"Run failed ({kind})." if kind else "Run failed.", _EXCERPT_LIMIT)
        else:
            excerpt = _excerpt(str(event.data.get("content") or ""), _EXCERPT_LIMIT)
        entries.append({
            **excerpt, "event_id": event.event_id, "kind": _PUBLIC_HISTORY[event.type],
            "at": event.created_at.isoformat(),
            "tool_name": receipt["tool_name"] if receipt else None,
            "status": receipt["status"] if receipt else None,
        })
    return entries, truncated


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/subagent/progress", dependencies=ctx.protected)
    async def get_progress(project_id: str, include_process: bool = True) -> ProjectProgress:
        return await project_progress(ctx, project_id, include_process)

    @router.post(
        "/api/v2/projects/{project_id}/subagent/agents/{session_id}/progress", dependencies=ctx.protected,
    )
    async def get_agent_progress(project_id: str, session_id: str, body: AgentProgressRequest) -> AgentContext:
        agents, pending, _, boundary = await _read_progress(ctx, project_id, session_id)
        messages, truncated = await asyncio.to_thread(_history, ctx.core, session_id, body, boundary)
        if body.filter is not None:
            try:
                matches = await filter_history(body.filter, messages)
            except ValueError as exc:
                raise HTTPException(400, detail={"code": "invalid_request", "message": str(exc)}) from exc
            except RuntimeError as exc:
                raise HTTPException(503, detail={"code": "unavailable", "message": str(exc)}) from exc
            messages = [message for message, match in zip(messages, matches, strict=True) if match]
        return {
            "agent": agents[0], "pending": pending,
            "messages": messages[-body.limit:], "history_truncated": truncated,
        }

    return router
