"""LLM 卡片打标流水线（v13）：受控词表 + 缓存 + 行对齐写回。

数据流：``vector_store/cards.jsonl``（17,188 行 = 8,594 卡 × zh/en）按
card_id 分组后逐批送 LLM，输出约束到 ``vector_store/tag_vocab.yaml`` 的
受控 id；同一 card 的 zh/en 两行共享同一份 tags（写回按行原位更新，
**行数与顺序不变，vectors.f16.npy 的行对齐因此不受影响、无需重编码**）。

幂等与断点：每张卡的缓存键 = sha1(card_id|heading|content)——重跑只调
新卡/内容变过的卡；缓存 ``vector_store/_tag_state/tag_cache.jsonl`` 是
append-only jsonl，后行覆盖前行。

词表生长：LLM 提议词表外的 tag 不落库，按 (facet, value) 聚合写入
``_tag_state/pending_tags.json`` 供人工审核后手工补进词表。

domain 不打标：cards.jsonl 既有 ``domain`` 字段（与源目录 1:1）即权威。
LLM 传输复用 ``cloudra.infra.llm_client``（自带重试/退避/三级 fallback），
provider 取 config.coordinator，可被 CLI 参数覆盖。本模块不做任何
模块级 IO——词表/缓存在函数调用期惰性加载。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
VOCAB_FILE = _REPO_ROOT / "vector_store" / "tag_vocab.yaml"
CARDS_FILE = _REPO_ROOT / "vector_store" / "cards.jsonl"
TAG_STATE_DIR = _REPO_ROOT / "vector_store" / "_tag_state"
CACHE_FILE = TAG_STATE_DIR / "tag_cache.jsonl"
PENDING_FILE = TAG_STATE_DIR / "pending_tags.json"

# 参与打标的 facet（domain 继承既有字段，不在此列）
TAG_FACETS = ("method", "software", "problem", "error")
_CONTENT_CUT = 600  # 单卡正文截断（码点），控制 prompt 与费用
_BATCH_SIZE = 15
_CONCURRENCY = 4
_MAX_TOKENS = 2400

_SYSTEM_PROMPT = """你是计算化学知识库的卡片标注器。对给出的每张知识卡片，从四个维度的受控词表中选出恰好匹配的标签：
- method：涉及的计算方法/理论层级/分析方法
- software：涉及的软件（含其子程序/工具脚本）
- problem：解决的问题类型/任务类型
- error：卡片内容对应的程序报错（没有明确报错内容就留空）

规则：
1. 只能使用词表里列出的 tag id，一个字都不能改；宁缺毋滥，没有把握就不标。
2. method 与 problem 可并存（如"SCF不收敛的解决"→ problem: scf_not_converged）。
3. 卡片提到具体软件就必须标 software。
4. error 只在卡片明确讨论某种报错/失败输出时标注。
5. 每个维度的值可以是 0 到多个。
只输出 JSON 对象，键是卡片 cid，值是 {"method": [...], "software": [...], "problem": [...], "error": [...]}（数组元素是 tag id 字符串），不要输出任何其他文字。"""


# --------------------------------------------------------------------------
# 词表
# --------------------------------------------------------------------------

class TagVocab:
    """tag_vocab.yaml 的内存索引：id 校验 + 别名倒排（查询侧报错检测共用）。"""

    def __init__(self, version: int, values: dict[str, dict[str, dict[str, Any]]]):
        self.version = version
        self.values = values
        self.alias_index: dict[str, tuple[str, str]] = {}
        for facet, defs in values.items():
            for tid, d in defs.items():
                for alias in d.get("aliases", []):
                    self.alias_index.setdefault(str(alias).strip().lower(), (facet, tid))

    @classmethod
    def load(cls, path: Path | None = None) -> "TagVocab":
        p = Path(path) if path else VOCAB_FILE
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        values: dict[str, dict[str, dict[str, Any]]] = {}
        for facet, items in (raw.get("facets") or {}).items():
            values[facet] = {}
            for item in items or []:
                tid = str(item.get("id") or "").strip()
                if tid:
                    values[facet][tid] = item
        return cls(version=int(raw.get("version") or 1), values=values)

    def is_known(self, facet: str, tid: str) -> bool:
        return tid in self.values.get(facet, {})

    def enum_text(self) -> str:
        """prompt 用紧凑枚举：每行 `facet id (label): alias1/alias2/...`。"""
        lines: list[str] = []
        for facet in TAG_FACETS:
            for tid, d in self.values.get(facet, {}).items():
                aliases = "/".join(str(a) for a in d.get("aliases", [])[:6])
                label = d.get("label") or tid
                lines.append(f"{facet} {tid} ({label}): {aliases}" if aliases
                             else f"{facet} {tid} ({label})")
        return "\n".join(lines)


def detect_error_tags(query: str, vocab: TagVocab) -> list[str]:
    """查询文本 → 命中的 error tag id（确定性子串检测，ASCII 不区分大小写）。

    只认 error facet 的 aliases：这是"报错优先检索路径"的触发器，宁可
    漏检不可误检——aliases 必须是程序输出原文级别的签名。
    """
    low = query.lower()
    out: list[str] = []
    for alias, (facet, tid) in vocab.alias_index.items():
        if facet == "error" and alias and alias in low and tid not in out:
            out.append(tid)
    return out


# --------------------------------------------------------------------------
# 缓存
# --------------------------------------------------------------------------

def cache_key(card_id: str, heading: str, content: str) -> str:
    h = hashlib.sha1(f"{card_id}|{heading}|{content}".encode("utf-8")).hexdigest()
    return h[:20]


def load_cache(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p = Path(path) if path else CACHE_FILE
    if not p.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("key"):
                out[str(row["key"])] = row
    return out


def append_cache(entries: list[dict[str, Any]], path: Path | None = None) -> None:
    p = Path(path) if path else CACHE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# 卡片读取与写回
# --------------------------------------------------------------------------

def read_cards(path: Path | None = None) -> list[dict[str, Any]]:
    p = Path(path) if path else CARDS_FILE
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def group_by_card(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """zh/en 两行折叠成一组：以 zh 行（缺则首行）为文本代表，携带全部行号。"""
    order: list[str] = []
    groups: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows):
        cid = str(row.get("card_id") or "")
        if not cid:
            continue
        g = groups.get(cid)
        if g is None:
            g = {"card_id": cid, "row_indexes": [], "text_row": row}
            groups[cid] = g
            order.append(cid)
        g["row_indexes"].append(i)
        if row.get("lang") == "zh":
            g["text_row"] = row
    return [groups[cid] for cid in order]


def writeback_tags(
    rows: list[dict[str, Any]], tags_by_cid: dict[str, dict[str, list[str]]],
    path: Path | None = None,
) -> dict[str, int]:
    """把 tags 原位写进每行（同 card_id 的 zh/en 共享），原子替换文件。

    行数与顺序严格不变——vectors.f16.npy 按行对齐，这是硬约束。
    """
    p = Path(path) if path else CARDS_FILE
    tagged_cids: set[str] = set()
    out_lines: list[str] = []
    for row in rows:
        cid = str(row.get("card_id") or "")
        new_row = dict(row)
        tags = tags_by_cid.get(cid)
        if tags:
            new_row["tags"] = {k: list(v) for k, v in tags.items() if v}
            tagged_cids.add(cid)
        out_lines.append(json.dumps(new_row, ensure_ascii=False))
    tmp = p.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return {"rows": len(rows), "cards": len(tagged_cids)}


# --------------------------------------------------------------------------
# LLM 打标
# --------------------------------------------------------------------------

def _card_prompt_block(group: dict[str, Any]) -> str:
    row = group["text_row"]
    heading = str(row.get("heading") or "")
    content = str(row.get("content") or "")
    return f"cid: {group['card_id']}\n标题: {heading}\n正文: {content[:_CONTENT_CUT]}"


def _build_user_prompt(batch: list[dict[str, Any]], vocab: TagVocab) -> str:
    cards = "\n\n".join(_card_prompt_block(g) for g in batch)
    return f"## 受控词表\n{vocab.enum_text()}\n\n## 待标注卡片\n{cards}"


def parse_llm_tags(
    data: dict[str, Any], batch: list[dict[str, Any]], vocab: TagVocab,
) -> tuple[dict[str, dict[str, list[str]]], list[dict[str, str]]]:
    """校验 LLM 输出：词表内 id 才落库，词表外的进 pending。

    返回 (tags_by_cid, pending)；pending 元素 {card_id, facet, value}。
    """
    tags_out: dict[str, dict[str, list[str]]] = {}
    pending: list[dict[str, str]] = []
    valid_cids = {g["card_id"] for g in batch}
    for cid, facet_tags in data.items():
        cid = str(cid)
        if cid not in valid_cids or not isinstance(facet_tags, dict):
            continue
        cleaned: dict[str, list[str]] = {}
        for facet in TAG_FACETS:
            raw_list = facet_tags.get(facet)
            if not isinstance(raw_list, list):
                continue
            vals: list[str] = []
            for v in raw_list:
                tid = str(v).strip()
                if not tid:
                    continue
                if vocab.is_known(facet, tid):
                    if tid not in vals:
                        vals.append(tid)
                else:
                    pending.append({"card_id": cid, "facet": facet, "value": tid})
            if vals:
                cleaned[facet] = vals
        if cleaned:
            tags_out[cid] = cleaned
    return tags_out, pending


def tag_cards(
    *,
    vocab: TagVocab,
    cards_path: Path | None = None,
    cache_path: Path | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    batch_size: int = _BATCH_SIZE,
    concurrency: int = _CONCURRENCY,
    limit: int = 0,
    refresh: bool = False,
    dry_run: bool = False,
    write_cache: bool = True,
) -> dict[str, Any]:
    """主流程：读卡 → 查缓存 → LLM 补标 → 校验 →（可选）写回 + 落缓存。

    同步入口（内部 asyncio.run 驱动 LLMClient）。返回 report dict；不直接
    打印（CLI 层负责 rich 渲染）。dry_run 下既不写 cards.jsonl 也不落缓存，
    但 LLM 调用照常发生（预览费用/质量用）。
    """
    started = time.perf_counter()
    rows = read_cards(cards_path)
    groups = group_by_card(rows)
    if limit and limit > 0:
        groups = groups[:limit]
    cache = {} if refresh else load_cache(cache_path)

    # provider 设置：显式参数 > config.coordinator
    if not (model and base_url and api_key):
        from cloudra.infra.config import get_config
        coord = get_config().coordinator
        model = model or coord.model
        base_url = base_url or coord.url
        api_key = api_key or coord.key

    todo = [
        g for g in groups
        if cache_key(g["card_id"], str(g["text_row"].get("heading") or ""),
                     str(g["text_row"].get("content") or "")) not in cache
    ]
    batches = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]

    tags_by_cid: dict[str, dict[str, list[str]]] = {}
    pending: list[dict[str, str]] = []
    llm_errors: list[str] = []
    new_cache_rows: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(max(1, concurrency))
    progress = {"done": 0}

    async def _one(batch: list[dict[str, Any]]) -> None:
        async with sem:
            from cloudra.infra.llm_client import LLMClient
            client = LLMClient(api_key=api_key or "", base_url=base_url or "", model=model)
            try:
                data, err = await client.chat_json(
                    _SYSTEM_PROMPT, _build_user_prompt(batch, vocab),
                    max_tokens=_MAX_TOKENS, temperature=0.2,
                )
            except Exception as exc:  # 传输层抛错（重试耗尽等）
                err = exc
                data = None
            finally:
                await client.aclose()
            if data is None:
                llm_errors.append(f"{type(err).__name__}: {err}" if err else "empty response")
                return
            batch_tags, batch_pending = parse_llm_tags(data, batch, vocab)
            tags_by_cid.update(batch_tags)
            pending.extend(batch_pending)
            now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            for g in batch:
                key = cache_key(g["card_id"], str(g["text_row"].get("heading") or ""),
                                str(g["text_row"].get("content") or ""))
                new_cache_rows.append({
                    "key": key, "card_id": g["card_id"],
                    "tags": batch_tags.get(g["card_id"], {}),
                    "model": model, "at": now,
                })
            progress["done"] += len(batch)

    async def _run() -> None:
        if not batches:
            return
        await asyncio.gather(*(_one(b) for b in batches))

    asyncio.run(_run())

    # 合并缓存命中
    from_cache = 0
    for g in groups:
        key = cache_key(g["card_id"], str(g["text_row"].get("heading") or ""),
                        str(g["text_row"].get("content") or ""))
        entry = cache.get(key)
        if entry is not None:
            tags = entry.get("tags") or {}
            if tags:
                tags_by_cid.setdefault(str(g["card_id"]), tags)
            from_cache += 1

    write_stats: dict[str, int] = {}
    if not dry_run:
        if new_cache_rows and write_cache:
            append_cache(new_cache_rows, cache_path)
        write_stats = writeback_tags(rows, tags_by_cid, cards_path)
        # pending 跟随缓存目录（测试可重定向，不污染仓库）
        _write_pending(pending, (Path(cache_path).parent if cache_path else TAG_STATE_DIR))

    return {
        "cards_total": len(groups),
        "cards_with_tags": len(tags_by_cid),
        "from_cache": from_cache,
        "llm_called": sum(len(b) for b in batches),
        "llm_batches": len(batches),
        "llm_errors": llm_errors,
        "pending": pending,
        "write": write_stats,
        "seconds": round(time.perf_counter() - started, 1),
    }


def _write_pending(pending: list[dict[str, str]], state_dir: Path | None = None) -> None:
    """pending 聚合落盘（历史累加计数），供人工审核补词表。"""
    if not pending:
        return
    d = Path(state_dir) if state_dir else TAG_STATE_DIR
    pending_file = d / PENDING_FILE.name
    d.mkdir(parents=True, exist_ok=True)
    existing: Counter[tuple[str, str]] = Counter()
    if pending_file.is_file():
        try:
            for k, v in json.loads(pending_file.read_text(encoding="utf-8")).items():
                facet, _, value = k.partition(":")
                existing[(facet, value)] = int(v)
        except (json.JSONDecodeError, ValueError):
            pass
    for item in pending:
        existing[(item["facet"], item["value"])] += 1
    merged = {f"{f}:{v}": n for (f, v), n in sorted(existing.items())}
    tmp = pending_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, pending_file)


# --------------------------------------------------------------------------
# 卡片 tags → 图谱反贴（store.rebuild_entity_tags 的输入构建）
# --------------------------------------------------------------------------

def source_tag_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    """cards 行 → {relations.source 键: {facet: [tag]}}。

    kg_relations.source 是博客级指针（"kb:422"/"kb:dyn01"），卡片是
    "kb:422:3" 式 blog:段号——同博客所有卡的 tags 并集后挂到该键上。
    """
    out: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        tags = row.get("tags")
        if not isinstance(tags, dict) or not tags:
            continue
        blog_id = str(row.get("blog_id") or "").strip()
        if not blog_id:
            continue
        key = f"kb:{blog_id}"
        merged = out.setdefault(key, {})
        for facet in TAG_FACETS:
            vals = [str(v) for v in (tags.get(facet) or []) if v]
            if vals:
                slot = merged.setdefault(facet, [])
                for v in vals:
                    if v not in slot:
                        slot.append(v)
    return out


# --------------------------------------------------------------------------
# 覆盖率统计（CLI tag stats 用）
# --------------------------------------------------------------------------

def coverage_report(rows: list[dict[str, Any]] | None = None,
                    path: Path | None = None) -> dict[str, Any]:
    """cards.jsonl 当前 tags 字段的覆盖率与分布。"""
    if rows is None:
        rows = read_cards(path)
    per_card: dict[str, set[str]] = {}
    dist: dict[str, Counter[str]] = {f: Counter() for f in TAG_FACETS}
    for row in rows:
        tags = row.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        merged = per_card.setdefault(str(row.get("card_id") or ""), set())
        for facet, vals in tags.items():
            if facet in dist and isinstance(vals, list):
                merged.update(f"{facet}:{v}" for v in vals)
                dist[facet].update(str(v) for v in vals)
    tagged_cards = sum(1 for s in per_card.values() if s)
    return {
        "cards": len(per_card),
        "tagged_cards": tagged_cards,
        "coverage_pct": round(100.0 * tagged_cards / len(per_card), 1) if per_card else 0.0,
        "facet_cards": {
            f: round(100.0 * sum(1 for s in per_card.values()
                                 if any(t.startswith(f"{f}:") for t in s)) / len(per_card), 1)
            if per_card else 0.0
            for f in TAG_FACETS
        },
        "top": {f: dist[f].most_common(10) for f in TAG_FACETS},
    }
