#!/usr/bin/env python3
"""【考古】旧题池 accessible 边来源分类——**不是**本轮 gold 战役待办队列。

2026-09-21 起主线是「边选反应边填 gold」，候选不来自 ideapool/tasks 存量池
（见 `gold_compute/README.md`）。本脚本仅复算历史池里「数值有没有可查来源记录」，
方便审计 archive / edge_barriers，**禁止**当排期缺口表。

用法：uv run python gold_compute/archive/gold_ledger.py
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIERS = ("easy", "normal", "hard")
KINDS = ("computed", "literature", "unrecorded", "null")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def accessible_edges() -> list[tuple[str, str, str, object]]:
    """(tier, task_id, edge_id, 题源自带的 barrier_kcal_mol) —— 只取 accessible 边。"""
    rows: list[tuple[str, str, str, object]] = []
    for tier in TIERS:
        for path in sorted((ROOT / "ideapool" / "tasks" / tier).glob("*.json")):
            task_id = path.stem
            doc = _load_json(path)
            graph = (doc.get("gold") or {}).get("mechanism_graph") or {}
            for edge in graph.get("edges", []):
                if not edge.get("accessible", False):
                    continue
                rows.append((tier, task_id, edge.get("id") or "", edge.get("barrier_kcal_mol")))
    return rows


def typed_records(subdir: str = "") -> dict[str, dict]:
    """task_id(文件名) -> 打标记录文档。"""
    base = ROOT / "gold_compute" / "edge_barriers" / subdir if subdir else ROOT / "gold_compute" / "edge_barriers"
    return {p.stem: _load_json(p) for p in sorted(base.glob("*.json"))}


def classify(
    edge_id: str,
    task_id: str,
    source_barrier: object,
    computed: dict[str, dict],
    barriers: dict[str, dict],
) -> tuple[str, object]:
    computed_doc = computed.get(task_id) or {}
    computed_edge = (computed_doc.get("edges") or {}).get(edge_id)
    method = str(computed_doc.get("method") or "").strip()
    barrier_edge = (barriers.get(task_id) or {}).get("edges") or {}
    recorded = barrier_edge.get(edge_id) if isinstance(barrier_edge, dict) else None

    value = None
    for candidate in (computed_edge, recorded):
        if candidate and candidate.get("barrier_kcal_mol") is not None:
            value = candidate["barrier_kcal_mol"]
            break
    if value is None:
        value = source_barrier

    if computed_edge is not None and method != "literature":
        return "computed", value
    if computed_edge is not None or (recorded and (recorded.get("source") or recorded.get("doi"))):
        return "literature", value
    if value is not None:
        return "unrecorded", value
    return "null", value


def main() -> int:
    computed = typed_records("computed")
    barriers = typed_records()
    edges = accessible_edges()

    totals = collections.Counter()
    by_tier: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    gaps: list[tuple[str, str, str, object]] = []
    for tier, task_id, edge_id, source_barrier in edges:
        kind, value = classify(edge_id, task_id, source_barrier, computed, barriers)
        totals[kind] += 1
        by_tier[tier][kind] += 1
        if kind in ("unrecorded", "null"):
            gaps.append((f"{tier}/{task_id}", edge_id, kind, value))

    print(f"gold 参考答案总账 — accessible 交付边 {sum(totals.values())} 条")
    for kind in KINDS:
        print(f"  {kind:11s} {totals[kind]:3d}")
    print(f"  缺口合计     {len(gaps):3d}（unrecorded + null）")
    print("\n按 tier：")
    for tier in TIERS:
        cells = "  ".join(f"{k}={by_tier[tier][k]}" for k in KINDS)
        print(f"  {tier:7s} {cells}")

    print(f"\n缺口队列（{len(gaps)} 条）：")
    for task, edge_id, kind, value in gaps:
        shown = "none" if value is None else value
        print(f"  {task:10s} {edge_id:12s} {kind:11s} {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
