"""Compute job 控制面：一键取消全部（账本级取消，绝不杀计算进程）。

取消语义按作业状态分桶（``acancel_all_compute_jobs``）：ready 直接落
cancelled；running + Slurm 置 cancel_requested，由租约持有方的既有 poll
循环走 scancel 收尾；running + 本地只落 DB 终态（calculator 物理跑完，
guard 终态 CAS no-op）。
"""

from __future__ import annotations

from fastapi import APIRouter

from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import acancel_all_compute_jobs

from ..context import ApiContext


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v2/compute/cancel-all", dependencies=ctx.protected)
    async def cancel_all_compute_jobs() -> dict[str, int]:
        return await acancel_all_compute_jobs(ComputeDB())

    return router
