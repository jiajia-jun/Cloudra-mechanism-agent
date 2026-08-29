"""Layer 3 — accuracy: Gaussian-tolerance barrier scoring against the gold
reference. Per-task sigma; a configurable cap on how much accuracy can cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from cloudra.benchmark.schema import AccuracyRubric, ReferenceComputation


@dataclass
class AccuracyReport:
    enabled: bool = True
    agent_barrier_kcal: float | None = None
    gold_barrier_kcal: float | None = None
    sigma_kcal: float = 3.0
    gaussian_score: float = 0.0          # in [0, 1], 1 = exact match
    capped_penalty: float = 0.0          # penalty actually applied after cap
    final_score: float = 0.0             # 1 - capped_penalty
    notes: list[str] = field(default_factory=list)


def gaussian_barrier_score(agent: float, gold: float, sigma: float) -> float:
    """exp(-(agent-gold)^2 / (2 sigma^2)) in [0, 1]."""
    if sigma <= 0:
        return 1.0 if agent == gold else 0.0
    d = agent - gold
    return math.exp(-(d * d) / (2.0 * sigma * sigma))


def score_accuracy(
    agent_barrier_kcal: float | None,
    gold: ReferenceComputation,
    rubric: AccuracyRubric | None = None,
) -> AccuracyReport:
    rubric = rubric or AccuracyRubric()
    rep = AccuracyReport(enabled=rubric.enabled, sigma_kcal=rubric.sigma_kcal_mol)
    rep.agent_barrier_kcal = agent_barrier_kcal
    rep.gold_barrier_kcal = gold.barrier_kcal_mol

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
    if agent_barrier_kcal is None:
        rep.gaussian_score = 0.0
        rep.capped_penalty = rubric.max_penalty_fraction
        rep.final_score = 1.0 - rep.capped_penalty
        rep.notes.append("agent barrier missing")
        return rep

    g = gaussian_barrier_score(agent_barrier_kcal, gold.barrier_kcal_mol, rubric.sigma_kcal_mol)
    rep.gaussian_score = g
    raw_penalty = 1.0 - g
    rep.capped_penalty = min(raw_penalty, rubric.max_penalty_fraction)
    rep.final_score = 1.0 - rep.capped_penalty
    if raw_penalty > rubric.max_penalty_fraction:
        rep.notes.append(
            f"raw penalty {raw_penalty:.3f} capped at {rubric.max_penalty_fraction}"
        )
    return rep
