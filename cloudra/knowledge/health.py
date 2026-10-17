"""chem-kb 健康聚合：图谱索引（chem_kg.db）与完整来源正文（cards.jsonl）。

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


def content_health() -> dict[str, Any]:
    """完整来源正文可读取，计数按来源合并卡片与语言版本。"""
    from cloudra.knowledge.content import load_sources
    from cloudra.persistence.paths import knowledge_cards_path

    path = knowledge_cards_path()
    if not path.is_file():
        return {"ok": False, "error": f"content file missing: {path}"}
    try:
        sources = load_sources()
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": bool(sources), "sources": len(sources)}


def knowledge_health() -> dict[str, Any]:
    """图谱和来源正文健康状态；读取失败时返回 error。"""
    return {"graph": graph_health(), "content": content_health()}
