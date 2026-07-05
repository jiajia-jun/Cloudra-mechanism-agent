"""
ChemBench comparison report — merge any two benchmark runs.

Reads two run directories, matches questions by uuid, and writes a side-by-side
report in Markdown, JSON, and CSV formats.

The comparison is intentionally generic (baseline vs treatment) so it can be
used for OpenCode vs Cloudra, Cloudra-CLI vs Cloudra-Internal, or any future
pair of backends.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cloudra.config import get_config


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class SideStats:
    """Statistics for one side of the comparison."""
    run_id: str
    total: int = 0
    answered: int = 0
    correct: int = 0
    accuracy: float = 0.0
    mc_accuracy: float = float("nan")
    mae_mean: float = float("nan")


@dataclass
class TopicDelta:
    """Per-topic comparison between baseline and treatment."""
    topic: str
    total: int = 0
    baseline_correct: int = 0
    treatment_correct: int = 0
    baseline_accuracy: float = 0.0
    treatment_accuracy: float = 0.0
    delta: float = 0.0  # treatment - baseline


@dataclass
class QuestionComparison:
    """Per-question comparison."""
    uuid: str
    name: str = ""
    topic: str = "uncategorized"
    preferred_score: str = ""
    baseline_answer: str | None = None
    treatment_answer: str | None = None
    baseline_correct: int = 0
    treatment_correct: int = 0
    both_correct: int = 0
    only_treatment: int = 0
    only_baseline: int = 0
    neither: int = 0


@dataclass
class ComparisonReport:
    """Final comparison report."""
    baseline: SideStats
    treatment: SideStats
    total_matched: int = 0
    accuracy_delta: float = 0.0  # treatment - baseline
    relative_improvement: float = float("nan")  # delta / baseline_accuracy
    by_topic: list[TopicDelta] = field(default_factory=list)
    questions: list[QuestionComparison] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    labels: dict[str, str] = field(default_factory=lambda: {"baseline": "Baseline", "treatment": "Treatment"})


# ── 核心合并逻辑 ──────────────────────────────────────────────────────────────

def compare_runs(baseline_dir: Path, treatment_dir: Path) -> ComparisonReport:
    """Read two run directories and produce a comparison report."""
    baseline_questions = _load_questions(baseline_dir)
    treatment_questions = _load_questions(treatment_dir)

    baseline_summary = _load_summary(baseline_dir)
    treatment_summary = _load_summary(treatment_dir)

    matched: list[tuple[dict, dict]] = []
    for q_uuid, bq in baseline_questions.items():
        tq = treatment_questions.get(q_uuid)
        if tq:
            matched.append((bq, tq))

    report = ComparisonReport(
        baseline=_side_stats(baseline_summary),
        treatment=_side_stats(treatment_summary),
        total_matched=len(matched),
    )

    if report.baseline.accuracy > 0:
        report.accuracy_delta = report.treatment.accuracy - report.baseline.accuracy
        report.relative_improvement = report.accuracy_delta / report.baseline.accuracy

    # Aggregate by topic
    topic_groups: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for bq, tq in matched:
        topic = _topic_of(bq)
        topic_groups[topic].append((bq, tq))

    for topic, group in sorted(topic_groups.items()):
        b_correct = sum(_is_correct(bq) for bq, _ in group)
        t_correct = sum(_is_correct(tq) for _, tq in group)
        total = len(group)
        report.by_topic.append(
            TopicDelta(
                topic=topic,
                total=total,
                baseline_correct=b_correct,
                treatment_correct=t_correct,
                baseline_accuracy=b_correct / total if total else 0.0,
                treatment_accuracy=t_correct / total if total else 0.0,
                delta=(t_correct - b_correct) / total if total else 0.0,
            )
        )

    # Per-question details
    for bq, tq in matched:
        bc = _is_correct(bq)
        tc = _is_correct(tq)
        report.questions.append(
            QuestionComparison(
                uuid=bq.get("uuid", ""),
                name=bq.get("name", ""),
                topic=_topic_of(bq),
                preferred_score=bq.get("preferred_score", ""),
                baseline_answer=bq.get("extracted_answer"),
                treatment_answer=tq.get("extracted_answer"),
                baseline_correct=int(bc),
                treatment_correct=int(tc),
                both_correct=int(bc and tc),
                only_treatment=int(tc and not bc),
                only_baseline=int(bc and not tc),
                neither=int(not bc and not tc),
            )
        )

    return report


# ── 输出 ──────────────────────────────────────────────────────────────────────

def write_report(report: ComparisonReport, output_dir: Path, labels: dict[str, str] | None = None) -> None:
    """Write comparison.json, comparison.md, and per_question.csv."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if labels:
        report.labels = labels

    json_path = output_dir / "comparison.json"
    json_path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_path = output_dir / "comparison.md"
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    csv_path = output_dir / "per_question.csv"
    _write_csv(report.questions, csv_path)


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _load_questions(run_dir: Path) -> dict[str, dict]:
    """Load all question detail files from a run directory, indexed by uuid."""
    questions: dict[str, dict] = {}
    q_dir = run_dir / "questions"
    if not q_dir.exists():
        return questions
    for path in q_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            uuid = data.get("uuid")
            if uuid:
                questions[uuid] = data
        except Exception:
            continue
    return questions


def _load_summary(run_dir: Path) -> dict:
    """Load summary.json from a run directory."""
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _side_stats(summary: dict) -> SideStats:
    """Build SideStats from a summary dict."""
    return SideStats(
        run_id=summary.get("run_id", ""),
        total=summary.get("total", 0),
        answered=summary.get("answered", 0),
        correct=summary.get("correct", 0),
        accuracy=summary.get("accuracy", 0.0),
        mc_accuracy=summary.get("mc_accuracy", float("nan")),
        mae_mean=summary.get("mae_mean", float("nan")),
    )


def _is_correct(q: dict) -> bool:
    return bool(q.get("metrics", {}).get("all_correct", 0))


def _topic_of(q: dict) -> str:
    keywords = q.get("keywords", []) or []
    return keywords[0] if keywords else "uncategorized"


def _write_csv(questions: list[QuestionComparison], path: Path) -> None:
    if not questions:
        return
    fieldnames = [
        "uuid", "name", "topic", "preferred_score",
        "baseline_answer", "treatment_answer",
        "baseline_correct", "treatment_correct",
        "both_correct", "only_treatment", "only_baseline", "neither",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for q in questions:
            writer.writerow(asdict(q))


def _render_markdown(report: ComparisonReport) -> str:
    b = report.baseline
    t = report.treatment
    labels = report.labels
    baseline_label = labels.get("baseline", "Baseline")
    treatment_label = labels.get("treatment", "Treatment")

    lines = [
        f"# ChemBench {baseline_label} vs {treatment_label} 对比报告",
        "",
        f"- 生成时间: {report.generated_at}",
        f"- 匹配题数: {report.total_matched}",
        "",
        "## 总体对比",
        "",
        f"| 指标 | {baseline_label} | {treatment_label} | Delta |",
        "|------|----------|---------|-------|",
        f"| 总题数 | {b.total} | {t.total} | — |",
        f"| 已作答 | {b.answered} | {t.answered} | {t.answered - b.answered:+d} |",
        f"| 正确数 | {b.correct} | {t.correct} | {t.correct - b.correct:+d} |",
        f"| 总正确率 | {b.accuracy:.1%} | {t.accuracy:.1%} | {report.accuracy_delta:+.1%} |",
        f"| MC 正确率 | {_pct(b.mc_accuracy)} | {_pct(t.mc_accuracy)} | — |",
        f"| 数值 MAE 均值 | {_fmt_mae(b.mae_mean)} | {_fmt_mae(t.mae_mean)} | — |",
        "",
    ]

    if not math.isnan(report.relative_improvement):
        lines.extend([
            f"**相对提升**: {report.relative_improvement:+.1%}",
            "",
        ])

    lines.extend([
        "## 分 Topic 对比",
        "",
        f"| Topic | 题数 | {baseline_label} 正确率 | {treatment_label} 正确率 | Delta |",
        "|-------|------|-----------------|----------------|-------|",
    ])
    for td in report.by_topic:
        lines.append(
            f"| {td.topic} | {td.total} | {td.baseline_accuracy:.1%} | "
            f"{td.treatment_accuracy:.1%} | {td.delta:+.1%} |"
        )
    lines.append("")

    treatment_wins = [q for q in report.questions if q.only_treatment]
    baseline_wins = [q for q in report.questions if q.only_baseline]
    both_right = sum(1 for q in report.questions if q.both_correct)
    both_wrong = sum(1 for q in report.questions if q.neither)

    lines.extend([
        "## 亮点",
        "",
        f"- 双方都对: {both_right}",
        f"- 双方都错: {both_wrong}",
        f"- 仅 {treatment_label} 对: {len(treatment_wins)}",
        f"- 仅 {baseline_label} 对: {len(baseline_wins)}",
        "",
    ])

    if treatment_wins:
        lines.extend([f"### {treatment_label} 答对但 {baseline_label} 答错的题", ""])
        for q in treatment_wins[:20]:
            lines.append(f"- `{q.uuid}` ({q.topic}): {q.name}")
        if len(treatment_wins) > 20:
            lines.append(f"- ... 还有 {len(treatment_wins) - 20} 题")
        lines.append("")

    if baseline_wins:
        lines.extend([f"### {baseline_label} 答对但 {treatment_label} 答错的题", ""])
        for q in baseline_wins[:20]:
            lines.append(f"- `{q.uuid}` ({q.topic}): {q.name}")
        if len(baseline_wins) > 20:
            lines.append(f"- ... 还有 {len(baseline_wins) - 20} 题")
        lines.append("")

    lines.extend([
        "## 说明",
        "",
        f"- {baseline_label} 与 {treatment_label} 在相同 ChemBench 题目上的横向对比。",
        "- 详细逐题数据见 `per_question.csv`。",
        "",
    ])

    return "\n".join(lines)


def _pct(value: float) -> str:
    return f"{value:.1%}" if not math.isnan(value) else "N/A"


def _fmt_mae(value: float) -> str:
    return f"{value:.4f}" if not math.isnan(value) else "N/A"


# ── 路径解析 ──────────────────────────────────────────────────────────────────

def resolve_run_dir(run_id_or_path: str, namespace: str) -> Path:
    """Resolve a run_id or directory path to an absolute run directory."""
    p = Path(run_id_or_path)
    if p.exists() and p.is_dir():
        return p

    data_dir = Path(get_config().data_dir)
    return data_dir / "benchmarks" / namespace / run_id_or_path
