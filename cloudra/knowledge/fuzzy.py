"""零部署兜底：语义通道的子串模糊匹配层（v10）。

数据源是仓库内 ``vector_store/cards.jsonl``（7497 卡，静态提交）。微服务不可用或
返回不足配额时，用确定性子串匹配补位卡片槽——克隆仓库零操作也有基础知识
检索。pip 安装场景没有 ``vector_store\\`` 目录：路径不存在时返回 ``[]``，行为与
v9.1 完全一致。匹配是"关键词包含"级：无语义泛化，质量预期见
docs/PLUGINS.md 的"零部署兜底"小节。

实现约束：纯标准库；懒加载 + 进程生命周期缓存（数据是仓库静态提交，不
刷新）；``threading.Lock`` 双检防并发首查双解析。所有函数 sync-only，
``plugin.search`` 的宿主已在 worker 线程执行。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_QUERY_MAX = 200  # 查询截断（码点）

_CACHE: list[dict[str, Any]] | None = None
_LOCK = threading.Lock()


def _cards_file() -> Path:
    # cloudra/knowledge/fuzzy.py -> parents[2] == 仓库根（源码检出/可编辑安装）。
    return Path(__file__).resolve().parents[2] / "vector_store" / "cards.jsonl"


def _reset_cache() -> None:
    """测试钩子：清空缓存。"""
    global _CACHE
    with _LOCK:
        _CACHE = None


def _parse(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            heading = str(row.get("heading") or "")
            content = str(row.get("content") or "")
            # ASCII 部分预 lower（CJK 不受影响）：ASCII token 两侧 lower 子串匹配。
            rows.append({
                "card_id": str(row.get("card_id") or ""),
                "domain": str(row.get("domain") or ""),
                "heading": heading,
                "content": content,
                "lang": str(row.get("lang") or "zh"),
                "text": heading + "\n" + content,
                "text_low": (heading + "\n" + content).lower(),
            })
    return rows


def _ensure_cards() -> list[dict[str, Any]]:
    global _CACHE
    if _CACHE is None:
        with _LOCK:
            if _CACHE is None:  # 双检：并发首查只解析一次
                _CACHE = _parse(_cards_file())
    return _CACHE


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """确定性子串匹配。返回 [{card_id, domain, heading, content, score}]。

    - 查询按空白分 token（>200 码点截断；空查询 → ``[]``）
    - ASCII token 两侧 lower 子串匹配；中文 token 原样子串匹配
    - AND 语义：所有 token 在 text 命中才是候选
    - score = 0.6·(heading 命中任一 token) + 0.4·(1/(1+首个命中位次/500))
    - 排序 score desc、card_id asc（平局决胜，保证确定性）；零命中 → ``[]``
    """
    if limit < 1:
        return []
    tokens = query[:_QUERY_MAX].split()
    if not tokens:
        return []
    hits: list[tuple[float, dict[str, Any]]] = []
    for card in _ensure_cards():
        text, text_low = card["text"], card["text_low"]
        first_pos: int | None = None
        heading_hit = False
        ok = True
        for tok in tokens:
            if tok.isascii():
                low = tok.lower()
                pos = text_low.find(low)
                if pos < 0:
                    ok = False
                    break
                if not heading_hit and low in card["heading"].lower():
                    heading_hit = True
            else:
                pos = text.find(tok)
                if pos < 0:
                    ok = False
                    break
                if not heading_hit and tok in card["heading"]:
                    heading_hit = True
            if first_pos is None or pos < first_pos:
                first_pos = pos
        if not ok or first_pos is None:
            continue
        score = 0.6 * (1.0 if heading_hit else 0.0) + 0.4 * (1.0 / (1.0 + first_pos / 500.0))
        hits.append((score, card))
    # 双语库：同 card_id 的 zh/en 行都可能命中——按查询语言偏好决胜后去重
    # （ASCII 主导查询偏 en 行，否则偏 zh 行），保留高分行，防止同卡双占。
    ascii_dom = sum(1 for t in tokens if t.isascii()) / len(tokens) >= 0.7 if tokens else False
    hits.sort(key=lambda x: (-x[0], 0 if (x[1]["lang"] == "en") == ascii_dom else 1,
                             x[1]["card_id"]))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s, c in hits:
        if c["card_id"] in seen:
            continue
        seen.add(c["card_id"])
        out.append({
            "card_id": c["card_id"],
            "domain": c["domain"],
            "heading": c["heading"],
            "content": c["content"],
            "lang": c["lang"],
            "score": s,
        })
        if len(out) >= limit:
            break
    return out
