import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import TERMINAL_STATES, alist_compute_jobs

description = (
    "Inspect the compute queue across registered nodes: per-node capacity, currently running jobs with their "
    "reserved cpus/memory, queued (ready) jobs in scheduling order with their resource requests, and why they "
    "are waiting. Capacity is accounted per node (each node has its own quota; a job only competes with jobs "
    "targeting the same node). "
    "Use for: checking free capacity before deciding how many cpus/memory_mb to request in submit_compute_job, "
    "or understanding why a submitted job is still queued. "
    "Do not use for: reading a specific job's result (use query_compute_job), or canceling jobs. "
    "NEVER poll this to wait on jobs. Terminal states are pushed to the owning agent automatically and wake it, "
    "so re-querying the queue while you wait can only return information you already had — each poll burns a "
    "model turn, and repeated no-progress turns are strike-counted by the completion gate (strikes FAIL "
    "the run). Query ONLY for an on-demand capacity/queue check right before submitting. "
    "Scheduling is FIFO within the same priority; running jobs are never preempted."
)


class QueryComputeQueue_input_schema(input_schema):
    recent_terminal: int = Field(
        default=5,
        description="How many recently finished jobs to include at the end (0 to skip).",
    )


class QueryComputeQueue_output_schema(output_schema):
    is_success: bool = Field(description="Whether the query succeeded")
    nodes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One entry per registered node (node_id, display_name, scheduler, capacity, in_flight, free). "
            "For a node running on this host, 'capacity.effective' = min('capacity.registered', "
            "'capacity.os_available') and 'os_available' covers usage the job ledger cannot see (engines "
            "started outside submit_compute_job); remote/cluster nodes report their registered quota as-is. "
            "A job is only scheduled against its own node's free capacity."
        ),
    )
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
        from cloudra.services.node_capacity import fair_share_mb, node_capacity_views

        # 节点级全局视图：中央 compute.db 的全量排队/在跑（不按会话过滤——
        # 它本来就是给 agent 看节点算力状态的）。容量探测（vm_stat 子进程）与
        # 在用量读库都是阻塞活，整体卸载到线程。
        db = ComputeDB()
        if not os.path.exists(db.path):
            nodes, _ = await asyncio.to_thread(node_capacity_views, None)
            return QueryComputeQueue_output_schema(
                is_success=True,
                nodes=nodes,
                message="No compute jobs have been submitted yet.",
            )
        nodes, default_node_id = await asyncio.to_thread(node_capacity_views, db)
        by_id = {view["node_id"]: view for view in nodes}

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

        def _node_of(row) -> str:
            return str(row["node_id"] or default_node_id)

        def _default_mem(node_key: str) -> int:
            entry = by_id.get(node_key)
            return fair_share_mb(entry["capacity"]["effective"]) if entry else 0

        running = [
            {
                "job_id": r["id"],
                "jobtype": r["jobtype"],
                "node_id": _node_of(r),
                "scheduler": r["scheduler"],
                "started_at": _iso(r["start_timestamp"]),
                "cpus": r["req_cpus"] or 1,
                "memory_mb": (
                    r["req_memory_mb"]
                    if r["req_memory_mb"] is not None
                    else _default_mem(_node_of(r))
                ),
                "priority": r["priority"] or 0,
            }
            for r in running_rows
        ]

        queued = []
        for position, r in enumerate(ready_rows, start=1):
            node_key = _node_of(r)
            entry = by_id.get(node_key)
            req_cpus = r["req_cpus"] or 1
            req_mem = (
                r["req_memory_mb"] if r["req_memory_mb"] is not None else _default_mem(node_key)
            )
            if entry is None:
                # 节点已从注册表消失：调度器不会认领它（绝不改投别的机器跑），
                # 这条原因就是给用户的修复指引。
                reason = (
                    f"waiting: node {node_key!r} is not in the node registry; "
                    "the scheduler will not claim this job until the node is registered"
                )
            else:
                free = entry["free"]
                if free["slots"] < 1:
                    reason = f"waiting: node {node_key} job slots are full"
                elif req_cpus > free["cpus"] or req_mem > free["memory_mb"]:
                    reason = f"waiting: not enough free cpus/memory on node {node_key} right now"
                else:
                    reason = "queued: should start on the next scheduler tick"
            queued.append({
                "job_id": r["id"],
                "position": position,
                "jobtype": r["jobtype"],
                "node_id": node_key,
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
                "node_id": _node_of(r),
                "state": r["state"],
                "ended_at": _iso(r["end_timestamp"]),
                "last_error": r["last_error"] or "",
            }
            for r in terminal_rows
        ]
        message = (
            f"{len(running)} running, {len(queued)} queued across {len(nodes)} node(s). "
            "Capacity is accounted per node: a job only competes with jobs targeting the same node."
        )
        if running or queued:
            message += (
                " STOP POLLING. Terminal states are pushed to the owning agent automatically and "
                "will wake it — re-querying this queue does not make jobs finish faster and never "
                "tells you anything new about completion. Every poll burns a model turn, and "
                "repeated no-progress turn endings are strike-counted by the completion gate "
                "(strikes FAIL the run). Do other work or end your turn and wait for the push. "
                "If you genuinely need an interim checkpoint, use schedule once with a one-shot "
                "read-only check_command."
            )
        return QueryComputeQueue_output_schema(
            is_success=True,
            nodes=nodes,
            running=running,
            queued=queued,
            terminal=terminal,
            message=message,
        )


def get_class():
    return QueryComputeQueue
