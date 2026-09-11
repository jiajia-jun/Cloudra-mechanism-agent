"""chem-kb knowledge routes (overview / health / search / ego graph)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from ..context import ApiContext


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/knowledge/overview", dependencies=ctx.protected)
    async def knowledge_overview() -> dict[str, Any]:
        """chem-kb 库概览（缺库时 db_present=False，不建库）。"""
        from cloudra.knowledge import store
        from cloudra.persistence.paths import knowledge_graph_db_path

        return await asyncio.to_thread(store.overview, knowledge_graph_db_path())

    @router.get("/api/v2/knowledge/health", dependencies=ctx.protected)
    async def knowledge_health() -> dict[str, Any]:
        """三通道健康聚合：语义（kg_vec 微服务）/ 图谱 / 模糊兜底（绝不抛，失败带 error）。"""
        from cloudra.knowledge.health import knowledge_health as aggregate

        return await asyncio.to_thread(aggregate)

    @router.get("/api/v2/knowledge/search", dependencies=ctx.protected)
    async def knowledge_search(
        q: str = "",
        limit: int = 10,
        tag: list[str] = Query(default=[]),
        entity_type: str | None = Query(default=None, alias="type"),
    ) -> dict[str, Any]:
        """图谱检索（FTS→LIKE 回退 + 1~2 跳邻域；v13 支持 tag/type 分面）。

        ``tag`` 可重复，格式 ``facet:tag_id``（如 ``error:err_l502``）；裸
        ``tag_id`` 按 error 惯例处理。``type`` 为 KG 实体类型
        （concept/method/software/pitfall/...）。
        """
        from cloudra.knowledge import store, tagging
        from cloudra.persistence.paths import knowledge_graph_db_path

        q = q.strip()
        if not q:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing q")
        limit = max(1, min(50, limit))
        facets = tagging.parse_tag_filters([str(t) for t in tag])
        rows = await asyncio.to_thread(
            store.search_graph, knowledge_graph_db_path(), q, limit,
            facets or None, entity_type,
        )
        return {
            "query": q,
            "fallback": rows[0]["fallback"] if rows else None,
            "results": rows,
        }

    @router.get("/api/v2/knowledge/graph", dependencies=ctx.protected)
    async def knowledge_graph(focus: str, hops: int = 1) -> dict[str, Any]:
        """focus 实体的 ego 邻域（1~2 跳；>300 节点确定性截断）。"""
        from cloudra.knowledge import store
        from cloudra.persistence.paths import knowledge_graph_db_path

        focus = focus.strip()
        if not focus:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing focus")
        if hops not in (1, 2):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="hops must be 1 or 2")
        result = await asyncio.to_thread(store.ego_graph, knowledge_graph_db_path(), focus, hops)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="focus not found or no db")
        return result

    return router
