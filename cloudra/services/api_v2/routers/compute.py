"""Compute job 控制面：项目作业队列只读查询 + 多节点容量视图 + 一键取消全部
（账本请求，由执行端确认停止）。

查询口径：活跃态 = ready/running/cancel_requested（与项目硬删除门禁同一口径）；
行投影里的 ``session_id`` 即归属 agent（终态推送的收件人），``node_id`` 是作业
归属的注册节点（容量按节点分池记账）。

取消语义（``acancel_all_compute_jobs``）：ready 直接落 cancelled；全部
running 置 cancel_requested，执行端确认计算退出后才落 cancelled。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import (
    _db_ready,
    acancel_all_compute_jobs,
    aget_compute_job,
    alist_compute_jobs,
    arequest_compute_job_cancellation,
)

from ..context import ApiContext
from ..models import ComputeCancelPost

_ACTIVE_STATES = ("ready", "running", "cancel_requested")


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/compute/jobs/{job_id}", dependencies=ctx.protected)
    async def project_compute_job(project_id: str, job_id: int) -> dict:
        ctx.core.require_project(project_id)
        db = ComputeDB()
        job = await aget_compute_job(db, job_id) if await asyncio.to_thread(_db_ready, db) else None
        if job is None or job["conversation_id"] != project_id:
            raise HTTPException(404, "compute job not found")
        return job

    @router.get("/api/v2/projects/{project_id}/compute/jobs", dependencies=ctx.protected)
    async def list_project_compute_jobs(
        project_id: str, active_only: bool = True
    ) -> list[dict]:
        """项目作业队列（默认只活跃态；active_only=false 取最近 100 条含终态）。"""
        ctx.core.require_project(project_id)
        return await alist_compute_jobs(
            ComputeDB(),
            states=_ACTIVE_STATES if active_only else None,
            conversation_id=project_id,
            order="recent",
            limit=None if active_only else 100,
        )

    @router.post("/api/v2/projects/{project_id}/compute/jobs/{job_id}/cancel", dependencies=ctx.protected)
    async def cancel_project_compute_job(project_id: str, job_id: int, body: ComputeCancelPost) -> dict:
        ctx.core.require_project(project_id)
        try:
            return await arequest_compute_job_cancellation(
                ComputeDB(), job_id, project_id=project_id, reason=body.reason,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/api/v2/compute/nodes", dependencies=ctx.protected)
    async def list_compute_nodes() -> list[dict]:
        """注册节点容量视图（全局，非项目作用域）：每节点生效容量 / 在用量 / 余量。

        与调度守护的认领额度同源（``services/node_capacity.py``）；OS 实时余量
        探测是阻塞活（vm_stat 子进程），卸载出事件循环。
        """
        from cloudra.services.node_capacity import node_capacity_views

        views, _default_node_id = await asyncio.to_thread(node_capacity_views, ComputeDB())
        return views

    @router.post("/api/v2/compute/cancel-all", dependencies=ctx.protected)
    async def cancel_all_compute_jobs() -> dict[str, int]:
        return await acancel_all_compute_jobs(ComputeDB())

    return router
