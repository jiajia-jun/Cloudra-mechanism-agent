"""Backend views for project activity and complete, scoped tool receipts."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.observability import (
    ACTIVITY_EVENT_TYPES,
    CALL_EVENT_TYPES,
    agent_activity,
    call_summary,
    tool_receipts,
)
from cloudra.runtime_v2.policies.goal_stage import read_goal
from cloudra.runtime_v2.schemas import utc_now
from cloudra.services.compute_store import _db_ready, get_compute_job, list_compute_jobs

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

    def event_snapshot(project_id, types):
        marks = (
            ctx.core.event_writer.persisted_watermarks()
            if ctx.core.store is not None
            else ctx.core.event_log.high_watermarks
        )
        watermark = marks.get(project_id, 0)
        events = ctx.core.event_log.query_project(project_id, types=types, limit=None)
        return [e for e in events if e.seq <= watermark], watermark

    async def calls_for(session_id, *, details=False):
        agent = ctx.core.require_agent(session_id)
        events, _ = event_snapshot(agent.project_id, CALL_EVENT_TYPES)
        return await asyncio.to_thread(
            tool_receipts,
            [e for e in events if e.session_id == session_id],
            details=details,
        )

    @router.get("/api/v2/agents/{session_id}/tool-calls", dependencies=ctx.protected)
    async def tool_calls(
        session_id: str, before: int | None = Query(default=None, ge=1), limit: int = Query(default=50, ge=1, le=200)
    ) -> dict:
        rows = [r for r in reversed(await calls_for(session_id)) if before is None or r["request_seq"] < before]
        page = rows[:limit]
        return {
            "items": [call_summary(r) for r in page],
            "next_before": page[-1]["request_seq"] if len(rows) > limit else None,
        }

    @router.get("/api/v2/agents/{session_id}/tool-calls/{request_event_id}", dependencies=ctx.protected)
    async def tool_call(session_id: str, request_event_id: str) -> dict:
        rows = await calls_for(session_id, details=True)
        row = next((r for r in rows if r["request_event_id"] == request_event_id), None)
        if row is None:
            raise HTTPException(404, "tool call not found")
        return await asyncio.to_thread(_jobs_for_receipt, row)

    @router.get("/api/v2/projects/{project_id}/activity", dependencies=ctx.protected)
    async def project_activity(project_id: str) -> dict:
        ctx.core.require_project(project_id)
        events, watermark = event_snapshot(project_id, ACTIVITY_EVENT_TYPES)
        agents = [a.model_copy(deep=True) for a in ctx.core.agents.values() if a.project_id == project_id]
        reminders = ctx.core.reminders.pending_in_project(project_id, through_seq=watermark)

        def collect():
            calls_by_agent, events_by_agent = defaultdict(list), defaultdict(list)
            for row in tool_receipts(events, details=False):
                calls_by_agent[row["session_id"]].append(row)
            for event in events:
                events_by_agent[event.session_id].append(event)
            db = ComputeDB()
            jobs = (
                list_compute_jobs(db, conversation_id=project_id, states=("ready", "running", "cancel_requested"))
                if _db_ready(db)
                else []
            )
            rows = []
            for agent in agents:
                row = agent_activity(agent, events_by_agent[agent.id], calls_by_agent[agent.id])
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
            return {
                "project_id": project_id,
                "as_of_seq": watermark,
                "observed_at": utc_now().isoformat(),
                "agents": rows,
            }

        return await asyncio.to_thread(collect)

    return router
