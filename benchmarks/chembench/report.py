"""
ChemBench benchmark report — 结果序列化与聚合模块。

输出目录结构（在 cloudra.config.data_dir 下）：
    benchmarks/chembench/<run_id>/
    ├── summary.json          # 总体统计
    ├── questions/
    │   ├── <uuid>.json       # 每题详情（含 conversation_id，可通过 API 查询）
    │   └── ...
    └── by_keyword/
        ├── organic-chemistry.json
        └── ...               # 按关键词分类的统计

每题的 JSON 包含指向 Cloudra conversation 的 conversation_id，
使得论文审稿人可以通过 API 复现或查询任意一道题的完整推理过程。
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cloudra.config import get_config


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class QuestionResult:
    """单题评测结果。"""
    uuid:             str
    name:             str
    conversation_id:  str              # Cloudra Conversation ID，可通过 /conversations/{id} 查询
    query:            str              # 发送给 Coordinator 的原始 query
    raw_output:       str              # Coordinator 的完整输出
    extracted_answer: Optional[str]   # 从 [ANSWER]...[/ANSWER] 提取的答案
    preferred_score:  str             # "multiple_choice_grade" | "mae"
    targets:          list            # ChemBench 标准答案
    keywords:         list            # 题目关键词
    metrics:          dict            # score_result() 的返回值
    elapsed_seconds:  float = 0.0    # 本题耗时
    timed_out:        bool  = False   # 是否超时


@dataclass
class BenchmarkRun:
    """整次 benchmark 运行的汇总。"""
    run_id:       str
    start_time:   str
    end_time:     str                     = ""
    total:        int                     = 0
    answered:     int                     = 0     # 成功提取到答案的题数
    correct:      int                     = 0
    timed_out:    int                     = 0
    accuracy:     float                   = 0.0
    mc_accuracy:  float                   = 0.0
    mae_mean:     float                   = float("nan")
    by_keyword:   dict[str, dict]         = field(default_factory=dict)
    config_snapshot: dict                 = field(default_factory=dict)


# ── Reporter ──────────────────────────────────────────────────────────────────

class BenchmarkReporter:
    """
    将每题结果实时写入磁盘，同时在运行结束后生成汇总报告。

    设计为"边跑边写"：每道题完成后立即持久化，确保中途中断也不丢数据。
    """

    def __init__(self, run_id: str, namespace: str = "chembench"):
        self.run_id = run_id
        self._root  = _run_dir(run_id, namespace)
        self._q_dir = self._root / "questions"
        self._kw_dir = self._root / "by_keyword"
        self._q_dir.mkdir(parents=True, exist_ok=True)
        self._kw_dir.mkdir(parents=True, exist_ok=True)
        self._results: list[QuestionResult] = []
        self._start_time = _now_iso()

    # ── 逐题写入 ─────────────────────────────────────────────────────────────

    def record(self, result: QuestionResult) -> None:
        """持久化单题结果（线程安全：每题写独立文件）。"""
        self._results.append(result)
        q_path = self._q_dir / f"{_safe_filename(result.uuid)}.json"
        q_path.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 最终汇总 ─────────────────────────────────────────────────────────────

    def finalize(self, config_snapshot: dict | None = None) -> BenchmarkRun:
        """计算全局统计并写入 summary.json，返回 BenchmarkRun 对象。"""
        run = self._aggregate(config_snapshot or {})
        self._write_by_keyword()
        summary_path = self._root / "summary.json"
        summary_path.write_text(
            json.dumps(asdict(run), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return run

    # ── 内部计算 ─────────────────────────────────────────────────────────────

    def _aggregate(self, config_snapshot: dict) -> BenchmarkRun:
        results  = self._results
        total    = len(results)
        answered = sum(1 for r in results if r.extracted_answer is not None)
        correct  = sum(r.metrics.get("all_correct", 0) for r in results)
        timed_out = sum(1 for r in results if r.timed_out)

        # MC accuracy
        mc_results = [r for r in results if r.preferred_score == "multiple_choice_grade"]
        mc_correct  = sum(r.metrics.get("all_correct", 0) for r in mc_results)
        mc_accuracy = mc_correct / len(mc_results) if mc_results else float("nan")

        # MAE mean
        mae_values = [
            r.metrics["mae"]
            for r in results
            if r.preferred_score == "mae" and not math.isnan(r.metrics.get("mae", float("nan")))
        ]
        mae_mean = sum(mae_values) / len(mae_values) if mae_values else float("nan")

        return BenchmarkRun(
            run_id          = self.run_id,
            start_time      = self._start_time,
            end_time        = _now_iso(),
            total           = total,
            answered        = answered,
            correct         = correct,
            timed_out       = timed_out,
            accuracy        = correct / total if total else 0.0,
            mc_accuracy     = mc_accuracy,
            mae_mean        = mae_mean,
            config_snapshot = config_snapshot,
        )

    def _write_by_keyword(self) -> None:
        """按第一个 keyword 分组写入子统计文件。"""
        kw_groups: dict[str, list[QuestionResult]] = defaultdict(list)
        for r in self._results:
            kw = (r.keywords[0] if r.keywords else "uncategorized")
            kw_groups[kw].append(r)

        by_keyword: dict[str, dict] = {}
        for kw, group in kw_groups.items():
            total   = len(group)
            correct = sum(r.metrics.get("all_correct", 0) for r in group)
            by_keyword[kw] = {
                "total":    total,
                "correct":  correct,
                "accuracy": correct / total if total else 0.0,
            }
            kw_path = self._kw_dir / f"{_safe_filename(kw)}.json"
            kw_path.write_text(
                json.dumps(by_keyword[kw], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    @property
    def output_dir(self) -> Path:
        return self._root


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _run_dir(run_id: str, namespace: str = "chembench") -> Path:
    data_dir = Path(get_config().data_dir)
    return data_dir / "benchmarks" / namespace / run_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(name: str) -> str:
    """将任意字符串转为安全文件名（保留字母数字和连字符）。"""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name)[:128]



