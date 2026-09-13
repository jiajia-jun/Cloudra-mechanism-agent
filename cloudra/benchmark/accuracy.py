"""Layer 3 — accuracy: 以交付物为准的能垒/性质评分（不读任何 LLM 散文）。

口径（与题库 query 协议一致）：决速步（RDS）基元反应能垒，相对该步起点最小
值。评分要求两条独立来源**都存在且一致**：

- ``log_barrier_kcal``：harness 从沙箱内绑定日志推出的值（``barrier_evidence``）；
- ``declared_barrier_kcal``：交付 ``mechanism_graph.json`` 里该步声明的
  ``barrier_kcal_mol``。

两者缺一、或彼此偏差超过本题 sigma（复用同一容差，不新增阈值）→ 本层记 0
分并写明原因（fail-loud，绝不用最终消息里的数字兜底）。一致后才与 gold 比，
用既有高斯容差定义评分。

锚点可信度门禁：gold 锚点（能垒或性质）``verification=unverified`` 时不参与
accuracy 评分——异质口径锚点照常打分会让完美作答也得 ≈0 分。该题本层视为
excluded（报告注明 "accuracy excluded: anchor unverified"），composite 权重
走与 rubric disabled 相同的直通路径。代码只读任务 JSON 的 verification 字段，
不硬编码题号；回填把锚点升级为 verified/computed_by_us 后自动恢复评分。

性质锚点（``ReferenceComputation.properties``，键带单位）：读交付图物种节点
的 ``properties`` 按键比对——数值型走高斯容差（σ 查模块级显式常量表
``_PROPERTY_SIGMAS``，键名子串匹配，表外数值键 fail-loud 抛错逼显式登记）；
字符串型（state_ordering 等）小写去空白后精确相等。多性质题取各键均值。

hard 档定性选择性（``score_qualitative_selectivity``）：任务带
``gold.selectivity.favored_channel`` 时替代 accuracy 槽位（composite 的 0.3
权重给选择性分）——交付边中恰好一条 ``favored: true`` 且其 ``channel`` 等于
gold favored_channel → 1.0，否则 0.0；barrier spread 数值不评分。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from cloudra.benchmark.schema import (
    AccuracyRubric,
    GoldMechanismGraph,
    ReferenceComputation,
    SelectivityReference,
    VerificationStatus,
)

if TYPE_CHECKING:
    from cloudra.benchmark.barrier_evidence import BarrierEvidence

# 性质锚点的高斯容差表（键名子串匹配，首个命中生效；表外数值键 fail-loud）。
# 新增性质键必须在此显式登记 σ——没有默认兜底值。
_PROPERTY_SIGMAS = (
    ("bond_length_angstrom", 0.02),
    ("cm-1", 50.0),
    ("kcal_mol", 2.0),
)


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
    # 性质锚点模式：逐键得分（空 = 能垒模式或本层未评分）
    property_scores: dict[str, float] = field(default_factory=dict)
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


def _property_sigma(key: str) -> float:
    """性质键的高斯 σ：显式常量表子串匹配；表外数值键 fail-loud（逼显式登记）。"""
    for token, sigma in _PROPERTY_SIGMAS:
        if token in key:
            return sigma
    raise ValueError(
        f"no sigma registered for property key {key!r}; "
        "extend _PROPERTY_SIGMAS explicitly"
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _score_properties(
    delivered_graph: Optional[GoldMechanismGraph],
    gold: ReferenceComputation,
    rep: AccuracyReport,
) -> AccuracyReport:
    """性质锚点模式：交付图物种节点的 `properties` 逐键对 gold 比对取均值。"""
    scores: dict[str, float] = {}
    for key, gold_val in gold.properties.items():
        if delivered_graph is None:
            rep.notes.append(f"property {key}: no delivered graph; scored 0")
            scores[key] = 0.0
            continue
        declared = [
            (n.id, n.properties[key])
            for n in delivered_graph.nodes
            if key in n.properties
        ]
        if not declared:
            rep.notes.append(
                f"property {key}: not declared on any species node; scored 0"
            )
            scores[key] = 0.0
            continue
        if len(declared) > 1:
            rep.notes.append(
                f"property {key}: declared on multiple nodes "
                f"{[nid for nid, _ in declared]}; using {declared[0][0]} "
                "(first in graph order)"
            )
        node_id, val = declared[0]
        if isinstance(gold_val, str):
            if not isinstance(val, str):
                rep.notes.append(
                    f"property {key}: gold expects a string, node {node_id} "
                    f"declared {type(val).__name__}; scored 0"
                )
                scores[key] = 0.0
            else:
                scores[key] = (
                    1.0 if _normalize_text(val) == _normalize_text(gold_val) else 0.0
                )
                rep.notes.append(
                    f"property {key}: node {node_id} declares {val!r} vs gold "
                    f"{gold_val!r} -> {scores[key]}"
                )
        else:
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                rep.notes.append(
                    f"property {key}: gold expects a number, node {node_id} "
                    f"declared {val!r}; scored 0"
                )
                scores[key] = 0.0
            else:
                sigma = _property_sigma(key)
                scores[key] = gaussian_barrier_score(float(val), float(gold_val), sigma)
                rep.notes.append(
                    f"property {key}: node {node_id} declares {val} vs gold "
                    f"{gold_val} (sigma {sigma}) -> {scores[key]:.4f}"
                )
    rep.property_scores = scores
    rep.gaussian_score = sum(scores.values()) / len(scores)
    rep.final_score = rep.gaussian_score
    return rep


def score_qualitative_selectivity(
    delivered_graph: Optional[GoldMechanismGraph],
    selectivity: SelectivityReference,
) -> tuple[float, str]:
    """hard 档定性选择性：交付边中恰好一条 favored=true 且 channel 命中 gold
    favored_channel → 1.0；其余（无 favored 声明、多条 favored、channel 错）→ 0.0。
    barrier spread 数值不评分。"""
    if delivered_graph is None or not delivered_graph.edges:
        return 0.0, (
            "qualitative selectivity: no delivered graph edges; favored channel "
            "not declared"
        )
    favored = [e for e in delivered_graph.edges if e.favored is True]
    if not favored:
        return 0.0, (
            "qualitative selectivity: no edge declares `favored: true`; scored 0"
        )
    if len(favored) > 1:
        return 0.0, (
            "qualitative selectivity: multiple edges declare `favored: true` "
            f"({[e.id for e in favored]}); the contract requires exactly one; scored 0"
        )
    edge = favored[0]
    if edge.channel == selectivity.favored_channel:
        return 1.0, (
            f"qualitative selectivity: favored channel {edge.channel!r} matches "
            "the reference; scored 1"
        )
    return 0.0, (
        f"qualitative selectivity: favored channel {edge.channel!r} != reference "
        f"{selectivity.favored_channel!r}; scored 0"
    )


def score_accuracy(
    *,
    evidence: "BarrierEvidence",
    gold: ReferenceComputation,
    rubric: AccuracyRubric | None = None,
    delivered_graph: Optional[GoldMechanismGraph] = None,
) -> AccuracyReport:
    """逐步核对（每条边都要"声明得到日志支撑"），再对 RDS 与 gold 比。
    gold.properties 非空时走性质锚点模式（与能垒模式互斥）。"""
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
    # 锚点可信度门禁：unverified（口径未对齐）的锚点不参与 accuracy 评分
    if (gold.barrier_kcal_mol is not None or gold.properties) and (
        gold.verification is VerificationStatus.UNVERIFIED
    ):
        rep.gaussian_score = 1.0
        rep.final_score = 1.0
        rep.notes.append(
            "accuracy excluded: anchor unverified (reference frame not aligned); "
            "scored on graph + self-consistency"
        )
        return rep
    if gold.properties:
        return _score_properties(delivered_graph, gold, rep)
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
