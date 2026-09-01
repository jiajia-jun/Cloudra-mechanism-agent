import os
from datetime import datetime
from typing import Any, Dict, List

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import TERMINAL_STATES, alist_compute_jobs

description = (
    "Inspect the compute queue: node capacity, currently running jobs with their reserved cpus/memory, "
    "queued (ready) jobs in scheduling order with their resource requests, and why they are waiting. "
    "Use for: checking free capacity before deciding how many cpus/memory_mb to request in submit_compute_job, "
    "or understanding why a submitted job is still queued. "
    "Do not use for: reading a specific job's result (use query_compute_job), or canceling jobs. "
    "Scheduling is FIFO within the same priority; running jobs are never preempted."
)


class QueryComputeQueue_input_schema(input_schema):
    recent_terminal: int = Field(
        default=5,
        description="How many recently finished jobs to include at the end (0 to skip).",
    )


class QueryComputeQueue_output_schema(output_schema):
    is_success: bool = Field(description="Whether the query succeeded")
    capacity: Dict[str, Any] = Field(default_factory=dict, description="Node total capacity and current in-flight usage")
    running: List[Dict[str, Any]] = Field(default_factory=list, description="Running jobs")
    queued: List[Dict[str, Any]] = Field(default_factory=list, description="Queued jobs in scheduling order")
    terminal: List[Dict[str, Any]] = Field(default_factory=list, description="Recently finished jobs")
    message: str = Field(default="", description="Status or error message")


def _iso(ts) -> str:
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


class QueryComputeQueue(Tool):
    tool_id: str = 't-58'
    tool_name: str = 'query_compute_queue'
    tool_description: str = description
    input_schema: Any = QueryComputeQueue_input_schema
    output_schema: Any = QueryComputeQueue_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: QueryComputeQueue_input_schema, session: Session) -> QueryComputeQueue_output_schema:
        from cloudra.services.nodes import NodeRegistry, default_resources

        try:
            capacity = dict(NodeRegistry.from_environment().node(None).resources)
        except Exception:
            capacity = default_resources()
        cap_slots = max(1, int(capacity.get("max_concurrent", 1)))
        default_mem = max(1, int(capacity.get("memory_mb", 1024)) // cap_slots)

        # 节点级全局视图：中央 compute.db 的全量排队/在跑（不按会话过滤——
        # 它本来就是给 agent 看节点算力状态的）
        db = ComputeDB()
        if not os.path.exists(db.path):
            return QueryComputeQueue_output_schema(
                is_success=True,
                capacity={"node": capacity, "in_flight": {"slots": 0, "cpus": 0, "memory_mb": 0}},
                message="No compute jobs have been submitted on this node yet.",
            )

        try:
            running_rows = await alist_compute_jobs(db, states=("running",), order="id")
            ready_rows = await alist_compute_jobs(db, states=("ready",), order="priority")
            terminal_rows: list = []
            limit = max(0, min(int(user_input.recent_terminal or 0), 20))
            if limit:
                terminal_rows = await alist_compute_jobs(
                    db, states=TERMINAL_STATES, order="ended", limit=limit
                )
        except Exception as e:
            return QueryComputeQueue_output_schema(is_success=False, message=f"Query failed: {e}")

        running = [
            {
                "job_id": r["id"],
                "jobtype": r["jobtype"],
                "scheduler": r["scheduler"],
                "started_at": _iso(r["start_timestamp"]),
                "cpus": r["req_cpus"] or 1,
                "memory_mb": r["req_memory_mb"] if r["req_memory_mb"] is not None else default_mem,
                "priority": r["priority"] or 0,
            }
            for r in running_rows
        ]
        used_cpus = sum(j["cpus"] for j in running)
        used_mem = sum(j["memory_mb"] for j in running)

        queued = []
        for position, r in enumerate(ready_rows, start=1):
            req_cpus = r["req_cpus"] or 1
            req_mem = r["req_memory_mb"] if r["req_memory_mb"] is not None else default_mem
            if len(running) >= cap_slots:
                reason = "waiting: node job slots are full"
            elif used_cpus + req_cpus > capacity.get("cpus", 1) or used_mem + req_mem > capacity.get("memory_mb", 1):
                reason = "waiting: not enough free cpus/memory right now"
            else:
                reason = "queued: should start on the next scheduler tick"
            queued.append({
                "job_id": r["id"],
                "position": position,
                "jobtype": r["jobtype"],
                "scheduler": r["scheduler"],
                "cpus": req_cpus,
                "memory_mb": req_mem,
                "priority": r["priority"] or 0,
                "status": reason,
            })

        terminal = [
            {
                "job_id": r["id"],
                "jobtype": r["jobtype"],
                "state": r["state"],
                "ended_at": _iso(r["end_timestamp"]),
                "last_error": r["last_error"] or "",
            }
            for r in terminal_rows
        ]
        return QueryComputeQueue_output_schema(
            is_success=True,
            capacity={
                "node": capacity,
                "in_flight": {"slots": len(running), "cpus": used_cpus, "memory_mb": used_mem},
            },
            running=running,
            queued=queued,
            terminal=terminal,
            message=(
                f"{len(running)} running, {len(queued)} queued. "
                "In-flight usage is node-global (the scheduler accounts all projects from the central compute.db)."
            ),
        )


def get_class():
    return QueryComputeQueue
