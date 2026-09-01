"""chem-kb 三通道健康聚合：语义（kg_vec 微服务）/ 图谱（chem_kg.db）/ 模糊兜底（cards.jsonl）。

``GET /api/v2/knowledge/health`` 路由与 ``cloudra knowledge status`` CLI 共用
本模块，避免两处各写一套探测。所有函数 sync-only；事件循环里的调用方必须
``asyncio.to_thread`` 卸载（api_v2 路由即如此）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

PathLike = Union[str, Path]


def graph_health(db_path: Optional[PathLike] = None) -> dict[str, Any]:
    """图谱通道：库文件存在且只读可开；overview 的全量计数顺便带回实体/关系数。"""
    from cloudra.knowledge import store
    from cloudra.persistence.paths import knowledge_graph_db_path

    db = Path(db_path) if db_path is not None else knowledge_graph_db_path()
    if not db.exists():
        return {"ok": False, "error": f"db missing: {db}"}
    try:
        info = store.overview(db)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "entities": info["entities"], "relations": info["relations"]}


def fuzzy_health() -> dict[str, Any]:
    """模糊兜底通道：cards.jsonl 存在且可解析（解析结果进程内缓存，探测即热身）。"""
    from cloudra.knowledge import fuzzy

    path = fuzzy._cards_file()
    if not path.is_file():
        return {"ok": False, "error": f"cards file missing: {path}"}
    try:
        cards = fuzzy._ensure_cards()
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": bool(cards), "cards": len(cards)}


def semantic_health() -> dict[str, Any]:
    """语义通道：kg_vec 微服务 /health 实时代理 + 上次检索错误（module 级 plugin 单例）。

    生产里注册进 runtime 的正是这个单例（plugins 配置 ``cloudra.knowledge.plugin:plugin``），
    因此它带的 last_health 反映真实检索流量。
    """
    from cloudra.knowledge.plugin import plugin

    return plugin.health()


def knowledge_health() -> dict[str, Any]:
    """三通道聚合：``{"semantic", "graph", "fuzzy"}``，各通道至少含 ``ok``，失败带 ``error``。"""
    return {
        "semantic": semantic_health(),
        "graph": graph_health(),
        "fuzzy": fuzzy_health(),
    }
