"""chem-kb 混合图书馆 provider：图谱通道（本地 SQLite）+ 语义通道（向量微服务）+ 模糊兜底层。

配额结构性保证双通道全带上：``limit=5`` 时语义通道 ``ceil(3/5)=3`` 条、
图谱通道 ``floor(2/5)=2`` 条；``limit < 2`` 时各保 1。

终版退化矩阵（微服务 / KG 库 / cards.jsonl → 行为）：

    ✓    ✓    —    3 语义 + 2 图谱（满血，模糊层零参与）
    ✗    ✓    ✓    3 模糊 + 2 图谱（零部署兜底，降级叙事仍双通道）
    ✗    ✓    ✗    5 图谱（KG 补位不变）
    ✓    ✗    —    5 语义（补位不变）
    ✗    ✗    ✓    5 模糊
    ✗    ✗    ✗    []

附加规则：语义通道返回不足配额（服务活着但命中少）→ 模糊层按 card_id
去重补足语义槽；补完仍有空槽才轮到 KG 补位——优先级链固定为
语义 > 模糊 > 图谱补位。条目内顺序按各通道原始分排序——跨通道分数只是
近似（bm25 / 余弦 / 子串分不同量纲），最终排序以 ``runtime_v2/knowledge.py``
的 (level, falsified, -score) 为准。

本模块禁止模块级/构造期的 DB/网络操作：provider 可能被 uvicorn 事件循环
线程实例化（``plugins`` 配置列表在 app 启动时加载），一切资源都在
``search()`` 调用期惰性获取。``search`` 为同步方法，宿主
（``knowledge.search_library``）自动 ``to_thread`` 卸载。
"""

from __future__ import annotations

import logging
import math
import os

import httpx

from cloudra.knowledge import fuzzy, store
from cloudra.persistence.paths import knowledge_graph_db_path
from cloudra.runtime_v2.knowledge import KnowledgeEntry

logger = logging.getLogger(__name__)

PLUGIN_SPEC = "cloudra.knowledge.plugin:plugin"
VEC_URL_ENV = "CLOUDRA_KG_VEC_URL"
VEC_URL_DEFAULT = "http://127.0.0.1:8765"
_VEC_TIMEOUT = 3.0
_STITCH_LIMIT = 2  # 每张卡追加的卡内关系条数


def _vec_url() -> str:
    return (os.getenv(VEC_URL_ENV) or VEC_URL_DEFAULT).rstrip("/")


def _stitch_content(content: str, db_path, blog_id: str) -> str:
    """语义命中的 content 追加 1~2 条卡内关系（" ‖图: A—rel→B"），总长 ≤200 码点。"""
    try:
        rels = store.relations_of_source(db_path, f"kb:{blog_id}", _STITCH_LIMIT)
    except Exception:
        rels = []
    if not rels:
        return store._fold(content)
    graph_line = " ‖图: " + "；".join(
        f"{r['src_label']}—{r['rel_type']}→{r['dst_label']}" for r in rels
    )
    return store._fold(content + graph_line)


class ChemKBPlugin:
    name = "chem-kb"

    # 禁止构造期 IO（见模块 docstring）；db/httpx 客户端都在 search 期获取。

    def search(self, query: str, *, limit: int = 5) -> list[KnowledgeEntry]:
        if limit < 1:
            return []
        if limit < 2:
            sem_quota = graph_quota = 1
        else:
            sem_quota = math.ceil(limit * 3 / 5)
            graph_quota = limit - sem_quota  # floor(limit*2/5)

        db_path = knowledge_graph_db_path()
        sem = self._semantic_channel(query, sem_quota)
        graph = self._graph_channel(db_path, query, graph_quota)

        # 卡片通道补位（优先级链：语义 > 模糊 > 图谱补位，见模块 docstring）。
        # 图谱通道死 → 卡片槽目标扩到 limit（先放大 k 重取语义，与 v9.1 补位
        # 行为一致）；语义槽未满（服务停/命中少）→ 模糊层按 card_id 去重补足。
        card_target = limit if not graph else sem_quota
        if len(sem) < card_target:
            if not graph:
                sem = self._semantic_channel(query, card_target)
            if len(sem) < card_target:
                sem = sem + self._fuzzy_topup(query, card_target - len(sem), sem)
        # 模糊层也没填满语义槽 → KG 补满全部配额。
        if graph and len(sem) < sem_quota:
            graph = self._graph_channel(db_path, query, limit)

        entries = sorted(sem + graph, key=lambda e: -e.score)
        return entries[:limit]

    def _fuzzy_topup(
        self, query: str, need: int, existing: list[KnowledgeEntry]
    ) -> list[KnowledgeEntry]:
        """模糊层补位：〔卡片·模糊〕条目（诚实标记，agent 可感知降级）。

        过量取回 ``need + len(existing)``：去重最多吃掉与既有语义命中同卡的
        那些行，不过量就会"差一条"漏给 KG 补位。
        """
        if need <= 0:
            return []
        try:
            hits = fuzzy.search(query, need + len(existing))
        except Exception:
            logger.exception("chem-kb fuzzy fallback failed")
            return []
        have = {e.source for e in existing}
        out: list[KnowledgeEntry] = []
        for h in hits:
            card_id = str(h.get("card_id") or "")
            if not card_id or card_id in have:
                continue
            have.add(card_id)
            try:
                score = float(h.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            out.append(KnowledgeEntry(
                title=f"〔卡片·模糊〕{h.get('heading') or card_id}",
                content=store._fold(str(h.get("content") or "")),
                evidence_level="L0",
                source=card_id,
                falsified=False,
                score=score,
            ))
            if len(out) >= need:
                break
        if out:
            logger.debug("chem-kb fuzzy fallback: +%d card(s) for %r", len(out), query)
        return out

    def _graph_channel(self, db_path, query: str, quota: int) -> list[KnowledgeEntry]:
        if quota <= 0 or not db_path.exists():
            return []
        rows = store.search_graph(db_path, query, limit=quota)
        return [
            KnowledgeEntry(
                title=f"〔图谱〕{r['label']}",
                content=str(r["content"]),
                evidence_level="L0",
                source=str(r["source"]),
                falsified=False,
                score=float(r["score"]),
            )
            for r in rows
        ]

    def _semantic_channel(self, query: str, quota: int) -> list[KnowledgeEntry]:
        if quota <= 0:
            return []
        try:
            resp = httpx.post(
                f"{_vec_url()}/search",
                json={"query": query, "k": quota},
                timeout=_VEC_TIMEOUT,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits") or []
        except Exception:
            # 服务不在 / 超时 / 响应畸形：该通道为空，绝不抛。
            return []
        db_path = knowledge_graph_db_path()
        out: list[KnowledgeEntry] = []
        for h in hits:
            if not isinstance(h, dict):
                continue
            blog_id = str(h.get("blog_id") or "")
            if not blog_id:
                parts = str(h.get("card_id") or "").split(":")
                blog_id = parts[1] if len(parts) >= 2 else ""
            content = str(h.get("content") or "")
            if blog_id and db_path.exists():
                content = _stitch_content(content, db_path, blog_id)
            try:
                score = float(h.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            out.append(KnowledgeEntry(
                title=f"〔卡片〕{h.get('heading') or h.get('card_id') or '知识卡片'}",
                content=content,
                evidence_level="L0",
                source=str(h.get("card_id") or "chem-kb"),
                falsified=False,
                score=score,
            ))
        return out


plugin = ChemKBPlugin()
# 必须实例导出（不能只给 class）：class 的 name 属性会让 plugins._looks_like_plugin
# 把类本身误判为插件实例而拒绝调用工厂路径。
