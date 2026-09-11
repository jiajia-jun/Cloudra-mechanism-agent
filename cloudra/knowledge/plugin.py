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

v13 报错优先路由：查询文本经词表 aliases 做确定性报错签名检测
（``tagging.detect_error_tags``，只认 verbatim 程序输出，宁漏勿误）。命中
时两通道都带 error tag 过滤重查一遍——语义通道过滤空则回退无过滤重试，
图谱通道同理（词表/打标缺失时行为与 v12 完全一致，优雅降级）。另外按
_ascii_dominant 启发把 lang 传给语义通道（v11 启发复用，zh 查询维持混合）。
命中条目携带受控 tags，经 render_library_hits 对 agent 可见。

本模块禁止模块级/构造期的 DB/网络操作：provider 可能被 uvicorn 事件循环
线程实例化（``plugins`` 配置列表在 app 启动时加载），一切资源都在
``search()`` 调用期惰性获取。``search`` 为同步方法，宿主
（``knowledge.search_library``）自动 ``to_thread`` 卸载。
"""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from cloudra.knowledge import fuzzy, store
from cloudra.persistence.paths import knowledge_graph_db_path
from cloudra.runtime_v2.knowledge import KnowledgeEntry, flatten_tags

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


def _ascii_dominant(query: str) -> bool:  # v11：英文查询启发（确定性）
    tokens = [t for t in query.split() if t]
    if not tokens:
        return False
    return sum(1 for t in tokens if t.isascii()) / len(tokens) >= 0.7


class ChemKBPlugin:
    name = "chem-kb"

    # 禁止构造期 IO（见模块 docstring）；db/httpx 客户端都在 search 期获取。
    def __init__(self) -> None:
        # 语义通道最近一次检索调用的健康记录：
        # {"ok": bool, "at": iso, "error"?: str}；尚无检索调用时为 None。
        self.last_health: dict[str, Any] | None = None
        # 报错路由词表（TagVocab | False 负缓存 | None 未加载）；search 期惰性读。
        self._vocab: Any = None

    def _detect_errors(self, query: str) -> list[str]:
        """查询 → 命中的报错签名 tag（词表缺失/损坏时静默禁用路由）。"""
        if self._vocab is None:
            try:
                from cloudra.knowledge.tagging import TagVocab
                self._vocab = TagVocab.load()
            except Exception:
                logger.warning("tag vocab unavailable, error routing disabled", exc_info=True)
                self._vocab = False
        if not self._vocab:
            return []
        from cloudra.knowledge.tagging import detect_error_tags
        return detect_error_tags(query, self._vocab)

    def _record_health(self, ok: bool, error: str | None = None) -> None:
        record: dict[str, Any] = {
            "ok": ok,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if error:
            record["error"] = error
        self.last_health = record

    def health(self) -> dict[str, Any]:
        """语义通道健康：实时代理一次 GET /health，叠加上次检索错误（若有）。

        返回 ``{"ok", "url", "model"?, "library_model"?, "count"?, "warning"?,
        "error"?, "last_error"?}``；探测本身失败时 ok=False 且带 error，绝不抛。
        """
        url = _vec_url()
        out: dict[str, Any] = {"ok": False, "url": url}
        try:
            resp = httpx.get(f"{url}/health", timeout=_VEC_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            out["ok"] = bool(data.get("ok"))
            for key in ("model", "library_model", "count", "warning"):
                if data.get(key) is not None:
                    out[key] = data[key]
        except Exception as exc:
            out["error"] = f"{type(exc).__name__}: {exc}"
        if self.last_health and not self.last_health.get("ok"):
            out["last_error"] = self.last_health.get("error")
        return out

    def search(self, query: str, *, limit: int = 5) -> list[KnowledgeEntry]:
        if limit < 1:
            return []
        if limit < 2:
            sem_quota = graph_quota = 1
        else:
            sem_quota = math.ceil(limit * 3 / 5)
            graph_quota = limit - sem_quota  # floor(limit*2/5)

        db_path = knowledge_graph_db_path()
        # v13：报错签名检测 + 查询语言启发；两通道带过滤检索，空则各自回退。
        err_tags = self._detect_errors(query)
        lang = "en" if _ascii_dominant(query) else None
        sem = self._semantic_channel(query, sem_quota, error_tags=err_tags, lang=lang)
        graph = self._graph_channel(db_path, query, graph_quota, error_tags=err_tags)

        # 卡片通道补位（优先级链：语义 > 模糊 > 图谱补位，见模块 docstring）。
        # 图谱通道死 → 卡片槽目标扩到 limit（先放大 k 重取语义，与 v9.1 补位
        # 行为一致）；语义槽未满（服务停/命中少）→ 模糊层按 card_id 去重补足。
        # 放大重取透传 lang 与 error_tags：报错查询下过滤命中是高相关信息，
        # 只因配额不足就被无过滤重取整体覆盖（赋值替换）会把它们换成泛化卡。
        card_target = limit if not graph else sem_quota
        if len(sem) < card_target:
            if not graph:
                sem = self._semantic_channel(query, card_target,
                                             error_tags=err_tags, lang=lang)
            if len(sem) < card_target:
                sem = sem + self._fuzzy_topup(query, card_target - len(sem), sem)
        # 模糊层也没填满语义槽 → KG 补满全部配额（error_tags 维持——通道内部
        # 自带过滤空回退，语义与首轮一致）。
        if graph and len(sem) < sem_quota:
            graph = self._graph_channel(db_path, query, limit, error_tags=err_tags)

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
                tags=flatten_tags(h.get("tags")),
            ))
            if len(out) >= need:
                break
        if out:
            logger.debug("chem-kb fuzzy fallback: +%d card(s) for %r", len(out), query)
        return out

    def _graph_channel(
        self, db_path, query: str, quota: int, error_tags: list[str] | None = None,
    ) -> list[KnowledgeEntry]:
        if quota <= 0 or not db_path.exists():
            return []
        facets = {"error": error_tags} if error_tags else None
        rows = store.search_graph(db_path, query, limit=quota, facets=facets)
        if not rows and facets:  # 打标未建/签名不沾边 → 回退无过滤（优雅降级）
            rows = store.search_graph(db_path, query, limit=quota)
        en = _ascii_dominant(query)
        out: list[KnowledgeEntry] = []
        for r in rows:
            # 英文查询优先展示 label_en（回退 label）；content 保留原 label 可溯源。
            label = (r.get("label_en") if en else None) or r["label"]
            out.append(KnowledgeEntry(
                title=f"〔图谱〕{label}",
                content=str(r["content"]),
                evidence_level="L0",
                source=str(r["source"]),
                falsified=False,
                score=float(r["score"]),
                tags=flatten_tags(r.get("tags")),
            ))
        return out

    def _semantic_channel(
        self, query: str, quota: int, error_tags: list[str] | None = None,
        lang: str | None = None,
    ) -> list[KnowledgeEntry]:
        if quota <= 0:
            return []
        payload: dict[str, Any] = {"query": query, "k": quota}
        if lang:
            payload["lang"] = lang
        if error_tags:
            payload["tags"] = {"error": error_tags}
        try:
            resp = httpx.post(f"{_vec_url()}/search", json=payload, timeout=_VEC_TIMEOUT)
            resp.raise_for_status()
            hits = resp.json().get("hits") or []
            if not hits and error_tags:
                # 报错过滤空（tags 未建/库里没有该签名）→ 无过滤重试一次
                payload.pop("tags")
                resp = httpx.post(f"{_vec_url()}/search", json=payload, timeout=_VEC_TIMEOUT)
                resp.raise_for_status()
                hits = resp.json().get("hits") or []
        except Exception as exc:
            # 服务不在 / 超时 / 响应畸形：该通道为空，绝不抛——但不再静默：
            # 告警日志 + 实例健康记录（health() 与 /api/v2/knowledge/health 可见）。
            logger.warning("chem-kb semantic channel unavailable (%s): %s", _vec_url(), exc)
            self._record_health(False, f"{type(exc).__name__}: {exc}")
            return []
        self._record_health(True)
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
                tags=flatten_tags(h.get("tags")),
            ))
        return out


plugin = ChemKBPlugin()
# 必须实例导出（不能只给 class）：class 的 name 属性会让 plugins._looks_like_plugin
# 把类本身误判为插件实例而拒绝调用工厂路径。
