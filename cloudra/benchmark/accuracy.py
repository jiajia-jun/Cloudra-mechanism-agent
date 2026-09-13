"""Layer 3 — accuracy: 以交付物为准的能垒评分（不读任何 LLM 散文）。

口径（与题库 query 协议一致）：决速步（RDS）基元反应能垒，相对该步起点最小
值。评分要求两条独立来源**都存在且一致**：

- ``log_barrier_kcal``：harness 从沙箱内绑定日志推出的值（``barrier_evidence``）；
- ``declared_barrier_kcal``：交付 ``mechanism_graph.json`` 里该步声明的
  ``barrier_kcal_mol``。

两者缺一、或彼此偏差超过本题 sigma（复用同一容差，不新增阈值）→ 本层记 0
分并写明原因（fail-loud，绝不用最终消息里的数字兜底）。一致后才与 gold 比，
用既有高斯容差定义评分。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cloudra.benchmark.schema import AccuracyRubric, ReferenceComputation

if TYPE_CHECKING:
    from cloudra.benchmark.barrier_evidence import BarrierEvidence


@dataclass
class AccuracyReport:
    enabled: bool = True
    log_barrier_kcal: float | None = None
    declared_barrier_kcal: float | None = None
    rds_edge_id: str = ""
    gold_barrier_kcal: float | None = None
    sigma_kcal: float = 3.0
    gaussian_score: float = 0.0          # in [0, 1], 1 = exact match
    capped_penalty: float = 0.0          # penalty actually applied after cap
    final_score: float = 0.0             # 1 - capped_penalty（缺证据/不一致直接 0）
    notes: list[str] = field(default_factory=list)


def gaussian_barrier_score(agent: float, gold: float, sigma: float) -> float:
    """exp(-(agent-gold)^2 / (2 sigma^2)) in [0, 1]."""
    if sigma <= 0:
        return 1.0 if agent == gold else 0.0
    d = agent - gold
    return math.exp(-(d * d) / (2.0 * sigma * sigma))


def _effective_sigma(rubric: AccuracyRubric, gold_barrier_kcal: float) -> float:
    """RDS 对 gold 比较的高斯宽度：小能垒放宽（rubric 小能垒口径），
    大能垒用基准 sigma。只用于对 gold 的比较，不动内部一致性核对。"""
    if gold_barrier_kcal <= rubric.small_barrier_threshold_kcal:
        return max(rubric.sigma_kcal_mol, rubric.small_barrier_sigma_kcal)
    return rubric.sigma_kcal_mol


def score_accuracy(
    *,
    evidence: "BarrierEvidence",
    gold: ReferenceComputation,
    rubric: AccuracyRubric | None = None,
) -> AccuracyReport:
    """逐步核对（每条边都要"声明得到日志支撑"），再对 RDS 与 gold 比。"""
    rubric = rubric or AccuracyRubric()
    rds = evidence.rds()
    rep = AccuracyReport(
        enabled=rubric.enabled,
        sigma_kcal=rubric.sigma_kcal_mol,
        log_barrier_kcal=rds.barrier_kcal_mol if rds is not None else None,
        declared_barrier_kcal=rds.declared_kcal_mol if rds is not None else None,
        rds_edge_id=rds.edge_id if rds is not None else "",
        gold_barrier_kcal=gold.barrier_kcal_mol,
    )

    if not rubric.enabled:
        rep.gaussian_score = 1.0
        rep.final_score = 1.0
        rep.notes.append("accuracy disabled for this task; scored on self-consistency only")
        return rep
    if gold.barrier_kcal_mol is None:
        rep.gaussian_score = 1.0
        rep.final_score = 1.0
        rep.notes.append("no gold barrier; accuracy not scored")
        return rep

    # --- 交付物双来源门禁：逐步核对（fail-loud，不给部分分） ---
    if not evidence.steps:
        rep.final_score = 0.0
        rep.notes.append(
            "no step barrier derivable from the delivered logs (each step's barrier "
            "must be backed by its own bound ORCA/Gaussian log files)"
        )
        return rep
    unbacked = [
        step.edge_id for step in evidence.steps if step.declared_kcal_mol is None
    ]
    if unbacked:
        rep.final_score = 0.0
        rep.notes.append(
            "the delivered mechanism_graph.json declares no barrier_kcal_mol on "
            f"step edge(s) {unbacked}; every computed step must be declared"
        )
        return rep
    inconsistent = [
        (step.edge_id, step.declared_kcal_mol, step.barrier_kcal_mol)
        for step in evidence.steps
        if abs(step.declared_kcal_mol - step.barrier_kcal_mol) > rubric.sigma_kcal_mol
    ]
    if inconsistent:
        rep.final_score = 0.0
        rep.notes.append(
            "declared vs log-derived barrier disagreement beyond sigma "
            f"{rubric.sigma_kcal_mol}: "
            + "; ".join(
                f"{edge}: declared {declared:.3f} vs logs {derived:.3f}"
                for edge, declared, derived in inconsistent
            )
        )
        return rep
    if rds is None:
        rep.final_score = 0.0
        rep.notes.append("no rate-determining step could be derived from the logs")
        return rep

    g = gaussian_barrier_score(
        rds.barrier_kcal_mol, gold.barrier_kcal_mol, _effective_sigma(rubric, gold.barrier_kcal_mol)
    )
    rep.sigma_kcal = _effective_sigma(rubric, gold.barrier_kcal_mol)
    rep.gaussian_score = g
    raw_penalty = 1.0 - g
    rep.capped_penalty = min(raw_penalty, rubric.max_penalty_fraction)
    rep.final_score = 1.0 - rep.capped_penalty
    rep.notes.append(
        f"RDS {rds.edge_id}: derived {rds.barrier_kcal_mol:.3f} kcal/mol from "
        f"{rds.ts_path} - {rds.base_path}; declaration agrees on all "
        f"{len(evidence.steps)} step(s)"
    )
    if raw_penalty > rubric.max_penalty_fraction:
        rep.notes.append(
            f"raw penalty {raw_penalty:.3f} capped at {rubric.max_penalty_fraction}"
        )
    return rep
