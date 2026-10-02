"""Router assembly: one APIRouter factory per domain.

``build_routers`` returns routers in the exact registration order of the
original single-file app, so route matching precedence is unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..context import ApiContext
from . import (
    agents,
    artifacts,
    benchmark,
    chem,
    compute,
    dag,
    events,
    fs,
    hub,
    knowledge,
    observability,
    pending,
    projects,
    reminders,
    roles,
    runtime,
    telemetry,
)


def build_routers(ctx: ApiContext) -> list[APIRouter]:
    return [
        runtime.build_router(ctx),
        projects.build_router(ctx),
        agents.build_router(ctx),
        observability.build_router(ctx),
        knowledge.build_router(ctx),
        roles.build_router(ctx),
        pending.build_router(ctx),
        artifacts.build_router(ctx),
        dag.build_router(ctx),
        chem.build_router(ctx),
        events.build_router(ctx),
        hub.build_router(ctx),
        benchmark.build_router(ctx),
        compute.build_router(ctx),
        reminders.build_router(ctx),
        fs.build_router(ctx),
        telemetry.build_router(ctx),
    ]
