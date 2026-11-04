"""Backend views for project activity and complete, scoped tool receipts."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.observability import (
    ACTIVITY_EVENT_TYPES,
    CALL_EVENT_TYPES,
    agent_activity,
    call_summary,
    scoped_tool_receipts,
    tool_receipts,
)
from cloudra.runtime_v2.policies.goal_stage import read_goal
from cloudra.runtime_v2.schemas import utc_now
from cloudra.services.compute_store import ACTIVE_STATES, _db_ready, get_compute_job, list_compute_jobs

from ..context import ApiContext


def _jobs_for_receipt(row: dict) -> dict:
    db = ComputeDB()
    if not _db_ready(db):
        return {**row, "compute_jobs": [], "unavailable_compute_job_ids": row["compute_job_ids"]}
    jobs, unavailable = [], []
    for job_id in row["compute_job_ids"]:
        job = get_compute_job(db, job_id)
        if job is None or job["conversation_id"] != row["project_id"]:
            unavailable.append(job_id)
        else:
            jobs.append(job)
    return {**row, "compute_jobs": jobs, "unavailable_compute_job_ids": unavailable}


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    def metadata():
        log = ctx.core.event_log
        return log.durable_metadata() if ctx.core.store is not None else {
            "projects": log.high_watermarks, "sessions": log.high_session_watermarks,
        }

    @router.get("/api/v2/agents/{session_id}/tool-calls", dependencies=ctx.protected)
    async def tool_calls(
        session_id: str, before: int | None = Query(default=None, ge=1), limit: int = Query(default=50, ge=1, le=200)
    ) -> dict:
        ctx.core.require_agent(session_id)
        boundary = metadata()["sessions"].get(session_id, 0)

        def collect():
            requests = ctx.core.event_log.query_session(
                session_id, types={"tool.requested"}, limit=limit + 1,
                before_session_seq=min(boundary, before - 1) if before is not None else boundary,
            )
            page = requests[-limit:]
            rows = scoped_tool_receipts(ctx.core.event_log, session_id, page, boundary)
            return {
                "items": [call_summary(row) for row in rows],
                "next_before": page[0].session_seq if len(requests) > limit else None,
            }

        return await asyncio.to_thread(collect)

    @router.get("/api/v2/agents/{session_id}/tool-calls/{request_event_id}", dependencies=ctx.protected)
    async def tool_call(session_id: str, request_event_id: str) -> dict:
        agent = ctx.core.require_agent(session_id)
        boundary = metadata()["sessions"].get(session_id, 0)

        def collect():
            request = ctx.core.event_log.get(request_event_id)
            if (request is None or request.type != "tool.requested"
                    or request.session_id != session_id or request.project_id != agent.project_id
                    or (request.session_seq or 0) > boundary):
                raise HTTPException(404, "tool call not found")
            rows = scoped_tool_receipts(ctx.core.event_log, session_id, [request], boundary, details=True)
            if not rows:
                raise HTTPException(404, "tool call not found")
            return _jobs_for_receipt(rows[0])

        return await asyncio.to_thread(collect)

    @router.get("/api/v2/projects/{project_id}/activity", dependencies=ctx.protected)
    async def project_activity(project_id: str) -> dict:
        async with ctx.core.command_lock:
            async with ctx.core.event_writer._lock:
                ctx.core.require_project(project_id)
                marks = metadata()
                watermark = marks["projects"].get(project_id, 0)
                agents = [a.model_copy(deep=True) for a in ctx.core.agents.values() if a.project_id == project_id]
                reminders = ctx.core.reminders.pending_in_project(project_id)

        def collect():
            db = ComputeDB()
            jobs = (
                list_compute_jobs(db, conversation_id=project_id, states=ACTIVE_STATES)
                if _db_ready(db)
                else []
            )
            rows = []
            log = ctx.core.event_log
            for agent in agents:
                boundary = marks["sessions"].get(agent.id, 0)
                run_id = agent.current_run.run_id if agent.current_run else None
                calls = tool_receipts(log.query_session(
                    agent.id, run_id=run_id, before_session_seq=boundary,
                    types=CALL_EVENT_TYPES, limit=None,
                ), details=False) if run_id is not None else []
                # Only fixed tails are needed outside the current run. All old
                # attempts stay behind the existing lazy tool-call pagination.
                tails = [
                    log.query_session(agent.id, types=types, before_session_seq=boundary, limit=1)
                    for types in (ACTIVITY_EVENT_TYPES, {"agent.completion_gate"}, {"run.finished", "agent.cancelled"})
                ]
                if run_id is not None:
                    tails.append(log.query_session(
                        agent.id, run_id=run_id, before_session_seq=boundary,
                        types={"llm.request_started", "llm.completed", "llm.failed"}, limit=1,
                    ))
                events = sorted({e.event_id: e for tail in tails for e in tail}.values(), key=lambda e: e.session_seq)
                row = agent_activity(agent, events, calls)
                row["goal"] = read_goal(agent)
                row["compute_jobs"] = [j for j in jobs if j["session_id"] == agent.id]
                row["reminders"] = [r for r in reminders if r["session_id"] == agent.id]
                if row["activity"] == "waiting_background":
                    source = row["last_completion_gate"]["event_id"]
                    row["waits"] = [
                        {"kind": "compute_job", "target_id": str(j["id"]), "event_id": source}
                        for j in row["compute_jobs"]
                    ] + [
                        {"kind": "reminder", "target_id": str(r["schedule_id"]), "event_id": source}
                        for r in row["reminders"]
                    ]
                rows.append(row)
            return {"project_id": project_id, "as_of_seq": watermark,
                    "observed_at": utc_now().isoformat(), "agents": rows}

        return await asyncio.to_thread(collect)

    return router
