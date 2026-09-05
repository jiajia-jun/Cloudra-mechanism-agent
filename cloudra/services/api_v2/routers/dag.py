"""DAG orchestration read/mutation routes (delivery graph, reviews, replan)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ..context import ApiContext
from ..models import DagMutationRequest, DagReplanRequest


def _dag_read_context(ctx: ApiContext, project_id: str):
    """Existing DAG store+engine for a project, or None (never initializes)."""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.store import DagStore, GraphBundleNotFound
    from cloudra.persistence.database import ConversationDB

    ctx.core.require_project(project_id)
    db = ConversationDB(project_id)
    if not Path(db.path).is_file():
        return None
    db.ensure_schema()
    store = DagStore(db)
    try:
        store.load_bundle()
    except GraphBundleNotFound:
        return None
    return store, DagEngine(store)


def _dag_controller(ctx: ApiContext, project_id: str):
    project = ctx.core.require_project(project_id)
    from cloudra.dag.controller import DagController
    from cloudra.persistence.database import ConversationDB

    if project.settings.orchestration_mode.value == "standard":
        return None
    db = ConversationDB(project_id)
    db.ensure_schema()
    return DagController(
        db,
        project_id,
        project.settings.orchestration_mode,
        conversation_id=project_id,
        working_directory=project.workspace_dir,
        core=ctx.core,
    )


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/dag/process", dependencies=ctx.protected)
    async def dag_process(project_id: str) -> dict[str, Any]:
        # Phase 4：process 图已删除。路由保留一个版本，一律 410。
        raise HTTPException(
            status_code=410,
            detail="the process graph was removed (delivery-only orchestration); use /dag/delivery",
        )

    @router.get("/api/v2/projects/{project_id}/dag/delivery", dependencies=ctx.protected)
    async def dag_delivery(project_id: str) -> dict[str, Any]:
        controller = await asyncio.to_thread(_dag_controller, ctx, project_id)
        if controller is None:
            return {"mode": "standard", "graph": None}
        await controller.initialize()
        snapshot = await asyncio.to_thread(controller.engine.snapshot)
        return {"mode": controller.mode.value, "graph": snapshot.delivery.model_dump(mode="json")}

    @router.get("/api/v2/projects/{project_id}/dag/report", dependencies=ctx.protected)
    async def dag_report(project_id: str) -> dict[str, Any] | None:
        controller = await asyncio.to_thread(_dag_controller, ctx, project_id)
        if controller is None:
            return None
        await controller.initialize()
        report = await asyncio.to_thread(controller.delivery_report)
        return report.model_dump(mode="json") if report is not None else None

    @router.get("/api/v2/projects/{project_id}/dag/history", dependencies=ctx.protected)
    async def dag_history(project_id: str) -> list[dict[str, Any]]:
        controller = await asyncio.to_thread(_dag_controller, ctx, project_id)
        if controller is None:
            return []
        return await asyncio.to_thread(controller.engine.history, limit=100)

    @router.get("/api/v2/projects/{project_id}/dag/projection", dependencies=ctx.protected)
    async def dag_projection(project_id: str) -> dict[str, Any] | None:
        from cloudra.dag.completion import build_projection

        context = await asyncio.to_thread(_dag_read_context, ctx, project_id)
        if context is None:
            return None
        store, engine = context
        mode = ctx.core.require_project(project_id).settings.orchestration_mode
        reviews = await asyncio.to_thread(store.list_call_reviews)
        pending = [
            {
                "review_id": row.review_id,
                "tool_name": row.tool_name,
                "is_success": row.is_success,
                "caller": row.caller_legacy_id or row.caller_role_id,
                "compute_job_id": row.compute_job_id,
                "result_summary": row.result_summary,
                "created_at": row.created_at,
            }
            for row in reviews
        ]
        projection = await asyncio.to_thread(
            build_projection,
            engine.snapshot(),
            mode=mode,
            contract=store.load_coverage_contract(),
            history=engine.history(limit=8),
            pending_reviews=pending,
        )
        return projection.model_dump(mode="json")

    @router.get("/api/v2/projects/{project_id}/dag/reviews", dependencies=ctx.protected)
    async def dag_reviews(project_id: str) -> dict[str, Any] | None:
        """CallReview 收件箱：pending 全量 + 最近已裁决/忽略（只读投影）。"""
        context = await asyncio.to_thread(_dag_read_context, ctx, project_id)
        if context is None:
            return None
        store, _engine = context
        pending = await asyncio.to_thread(store.list_call_reviews, "pending")
        everything = await asyncio.to_thread(store.list_call_reviews, None)

        def _row(review) -> dict[str, Any]:
            return {
                "review_id": review.review_id,
                "tool_name": review.tool_name,
                "is_success": review.is_success,
                "caller_session_id": review.caller_session_id,
                "caller_role_id": review.caller_role_id,
                "caller_legacy_id": review.caller_legacy_id,
                "arguments_digest": review.arguments_digest,
                "result_summary": review.result_summary,
                "compute_job_id": review.compute_job_id,
                "suggested_target_id": review.suggested_target_id,
                "suggested_stage": review.suggested_stage,
                "claim": review.claim,
                "rationale": review.rationale,
                "submitter": review.submitter,
                "source": review.source,
                "state": review.state,
                "created_at": review.created_at,
            }

        return {
            "pending": [_row(review) for review in pending],
            "recent": [_row(review) for review in everything if review.state != "pending"][-20:],
        }

    @router.get("/api/v2/projects/{project_id}/dag/draft", dependencies=ctx.protected)
    async def dag_draft(project_id: str) -> dict[str, Any] | None:
        """当前机理草稿 + mechanism_accepted（D4：EXISTS accepted draft）。"""
        context = await asyncio.to_thread(_dag_read_context, ctx, project_id)
        if context is None:
            return None
        store, _engine = context
        draft = await asyncio.to_thread(store.latest_draft)
        accepted = await asyncio.to_thread(store.has_accepted_draft)
        return {"mechanism_accepted": accepted, "draft": draft}

    @router.post("/api/v2/projects/{project_id}/dag/replan", dependencies=ctx.protected)
    async def dag_replan(project_id: str, body: DagReplanRequest) -> dict[str, Any]:
        """用户 replan：持久化一条结构化督导请求 + 通知 Supervisor，立即返回。

        事件驱动督导（Task 3）后本端点不再现场同步跑督导 LLM：请求落
        dag_review_requests（kind="exception"，正文保留用户 note），
        notify_supervisor 按状态表调度，裁决异步到达。返回 queued 语义——
        绝不伪报草稿已获批或复核已完成。
        """
        from cloudra.dag.review_requests import ReviewRequest
        from cloudra.runtime_v2.supervision import notify_supervisor

        context = await asyncio.to_thread(_dag_read_context, ctx, project_id)
        if context is None:
            raise HTTPException(status_code=404, detail="DAG bundle not initialized")
        mode = ctx.core.require_project(project_id).settings.orchestration_mode
        # schemas 与 dag.models 各有一个 OrchestrationMode 枚举——按 value 比较。
        if mode.value != "dag_guided":
            raise HTTPException(
                status_code=422,
                detail=f"replan is only available in dag_guided mode (current: {mode.value})",
            )
        store, _engine = context
        note = (body.note or "").strip()
        question = note or (
            "User requested a replan: re-review the current mechanism draft, "
            "the delivery graph, and the open coverage gaps."
        )
        # 裁决通知的收件人：项目 Coordinator（反馈落研究主线）；没有
        # Coordinator 时落 "user"（无活 agent，通知行直接闭环标记）。
        coordinator = next(
            (
                agent
                for agent in ctx.core.agents.values()
                if agent.project_id == project_id and agent.role_id == "coordinator"
            ),
            None,
        )

        def _enqueue() -> str:
            request = ReviewRequest(
                kind="exception",
                requester=coordinator.id if coordinator else "user",
                target_ids=[],
                question=question,
                proposal={"source": "user_replan", "note": note},
                basis_fingerprint="sha256:pending",
            )
            basis = store.review_basis(request)
            return store.enqueue_review(
                request.model_copy(update={"basis_fingerprint": basis})
            )

        request_id = await asyncio.to_thread(_enqueue)
        await notify_supervisor(ctx.core, project_id, reason="user replan")
        return {
            "trigger": "user_replan",
            "queued": True,
            "request_id": request_id,
            "summary": (
                f"Replan request {request_id} queued for the Supervisor. "
                "The review is asynchronous: this response does NOT mean the "
                "draft or plan has been approved."
            ),
        }

    @router.post("/api/v2/projects/{project_id}/dag/mutations", dependencies=ctx.protected)
    async def dag_mutations(project_id: str, body: DagMutationRequest) -> dict[str, Any]:
        from cloudra.dag.models import GraphActor, MutationBatch, parse_graph_operation

        context = await asyncio.to_thread(_dag_read_context, ctx, project_id)
        if context is None:
            raise HTTPException(status_code=404, detail="DAG bundle not initialized")
        _store, engine = context
        batch = MutationBatch(
            session_id="user",
            actor=GraphActor.USER,
            actor_id="user",
            base_revisions=body.base_revisions,
            operations=[parse_graph_operation(op) for op in body.operations],
            rationale=body.rationale,
        )
        result = await asyncio.to_thread(engine.apply_batch, batch)
        return result.model_dump(mode="json")

    return router
