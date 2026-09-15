"""Layer 3 — accuracy: 以交付物为准的逐边能垒/性质评分（不读任何 LLM 散文）。

口径（与题库 query 协议一致）：gold 机理图**逐边**承载参考答案能垒；评分对
**每条带参考值的 gold 边**在交付 evidence 里按 edge_id 找对应步，要求两条独立
来源**都存在且一致**：

- ``log_barrier_kcal``：harness 从沙箱内绑定日志推出的值（``barrier_evidence``）；
- ``declared_barrier_kcal``：交付 ``mechanism_graph.json`` 里该边声明的
  ``barrier_kcal_mol``。

该边缺日志推算、缺声明、或声明在**任何合法组合**下都得不到支撑且证据也对
不上参考 → 该边 0 分并 fail-loud 归零整题（绝不用最终消息里的数字兜底）。
声明支撑得住（或虽支撑不住、但交付证据里另有与参考一致的组合——即 agent
选了另一个构象/参考系定义、而正确的计算已在它的日志里）→ 走正常数值路径或
按「答案定义差异」固定小扣分（`_DEFINITION_MISMATCH_EDGE_SCORE`），**不归零**
（用户口径：这是答案定义问题，不是科学错误）。一致后与 gold 边值比，
用高斯容差评分；逐边分数按 gold 边 ``weight`` 加权平均（权重越大 = 该边越
容易算准/越可核实）。汇总后仍按 ``max_penalty_fraction`` 封顶。

若 gold 机理图不存在任何带参考值的边 → accuracy 不评分（final_score=1.0），
沿用旧 null 行为。

性质锚点（``GoldSpec.reference_properties``，键带单位）：读交付图物种节点的
``properties`` 按键比对——数值型走高斯容差（σ 查模块级显式常量表
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
    GoldSpec,
    SelectivityReference,
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

# 「答案定义差异」的逐边记分：证据里已经含有与参考一致的组合（agent 只是
# 报/选了另一个构象或参考系定义），属定义层面的不一致而非科学错误——按此
# 固定小扣分计入加权，绝不走 fail-loud 归零（用户口径）。
_DEFINITION_MISMATCH_EDGE_SCORE = 0.9


@dataclass
class AccuracyReport:
    enabled: bool = True
    log_barrier_kcal: float | None = None
    declared_barrier_kcal: float | None = None
    rds_edge_id: str = ""
    sigma_kcal: float = 3.0
    gaussian_score: float = 0.0          # in [0, 1], 1 = exact match
    capped_penalty: float = 0.0          # penalty actually applied after cap
    final_score: float = 0.0             # 1 - capped_penalty（缺证据/不一致直接边 0）
    # 逐边能垒得分：edge_id -> 高斯分（空 = 非能垒模式或本层未评分）
    edge_scores: dict[str, float] = field(default_factory=dict)
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
    """逐边对 gold 比较的高斯宽度：小能垒放宽（rubric 小能垒口径），
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
    gold_properties: dict[str, float | str],
    rep: AccuracyReport,
) -> AccuracyReport:
    """性质锚点模式：交付图物种节点的 `properties` 逐键对 gold 比对取均值。"""
    scores: dict[str, float] = {}
    for key, gold_val in gold_properties.items():
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


def _find_matching_step(
    gold_edge,
    gold_nodes: dict,
    steps: list,
    delivered_graph: Optional[GoldMechanismGraph],
    cfg,
    match_threshold: float,
):
    """按**物种对应**找 gold 边的交付步（edge id 是题库内部约定，agent 不可知，
    绝不参与匹配）：交付边的 from/to 端点物种与 gold 边**同向**端点分别匹配
    （species_substitution_cost ≤ 阈值，与 Layer 1/graph GED 同口径；反向步
    能垒口径不同不匹配）。多候选按 bond_changes 对称差最小、端点代价最小、
    edge id 字典序取（确定性）。"""
    from cloudra.benchmark.graph_similarity import species_substitution_cost

    if delivered_graph is None:
        return None
    delivered_nodes = {n.id: n for n in delivered_graph.nodes}
    delivered_edges = {e.id: e for e in delivered_graph.edges}
    gold_from = gold_nodes.get(gold_edge.from_node)
    gold_to = gold_nodes.get(gold_edge.to_node)
    if gold_from is None or gold_to is None:
        return None
    gold_pairs = gold_edge.bond_changes.pairs()
    candidates: list[tuple[int, float, str, object]] = []
    for step in steps:
        d_edge = delivered_edges.get(step.edge_id)
        if d_edge is None:
            continue
        d_from = delivered_nodes.get(d_edge.from_node)
        d_to = delivered_nodes.get(d_edge.to_node)
        if d_from is None or d_to is None:
            continue
        cost_from = species_substitution_cost(gold_from.smiles, d_from.smiles, cfg)
        cost_to = species_substitution_cost(gold_to.smiles, d_to.smiles, cfg)
        if cost_from > match_threshold or cost_to > match_threshold:
            continue
        symdiff = len(gold_pairs ^ d_edge.bond_changes.pairs())
        candidates.append((symdiff, cost_from + cost_to, step.edge_id, step))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][3]


def score_accuracy(
    *,
    evidence: "BarrierEvidence",
    gold: GoldSpec,
    rubric: AccuracyRubric | None = None,
    delivered_graph: Optional[GoldMechanismGraph] = None,
    cfg=None,
    match_threshold: float = 0.2,
) -> AccuracyReport:
    """逐边核对（每条 gold 带参考值的边都要"声明得到日志支撑"），再逐边对
    gold 比、按 gold 边 weight 加权平均。gold.reference_properties 非空时走性质
    锚点模式（与能垒模式互斥）。"""
    rubric = rubric or AccuracyRubric()
    rds = evidence.rds()
    rep = AccuracyReport(
        enabled=rubric.enabled,
        sigma_kcal=rubric.sigma_kcal_mol,
        log_barrier_kcal=rds.barrier_kcal_mol if rds is not None else None,
        declared_barrier_kcal=rds.declared_kcal_mol if rds is not None else None,
        rds_edge_id=rds.edge_id if rds is not None else "",
    )

    if not rubric.enabled:
        rep.gaussian_score = 1.0
        rep.final_score = 1.0
        rep.notes.append("accuracy disabled for this task; scored on self-consistency only")
        return rep
    if gold.reference_properties:
        return _score_properties(delivered_graph, gold.reference_properties, rep)
    ref_edges = [
        e for e in gold.mechanism_graph.edges if e.barrier_kcal_mol is not None
    ]
    if not ref_edges:
        rep.gaussian_score = 1.0
        rep.final_score = 1.0
        rep.notes.append("no gold edge carries a reference barrier; accuracy not scored")
        return rep

    # --- 交付物双来源门禁：逐边核对（任一参考边缺失/不一致 -> 整题 fail-loud 记 0） ---
    from cloudra.benchmark.graph_similarity import GedConfig

    cfg = cfg or GedConfig()
    gold_nodes = {n.id: n for n in gold.mechanism_graph.nodes}
    # 全零权重无法归一：退回逐边等权（避免除零；正常题库不出现）
    equal_fallback = sum(e.weight for e in ref_edges) <= 0
    if equal_fallback:
        rep.notes.append(
            "all reference-edge weights are zero; falling back to equal weighting"
        )
    weights = {e.id: (1.0 if equal_fallback else e.weight) for e in ref_edges}
    weight_total = sum(weights.values())

    failures: list[str] = []
    weighted_sum = 0.0
    for edge in ref_edges:
        step = _find_matching_step(
            edge, gold_nodes, evidence.steps, delivered_graph, cfg, match_threshold
        )
        if step is None:
            rep.edge_scores[edge.id] = 0.0
            failures.append(
                f"gold edge {edge.id} carries a reference barrier but no delivered "
                "step matches its endpoint species"
            )
            continue
        if step.edge_id != edge.id:
            rep.notes.append(
                f"gold edge {edge.id} matched delivered step {step.edge_id} "
                "by endpoint species"
            )
        if step.declared_kcal_mol is None:
            rep.edge_scores[edge.id] = 0.0
            failures.append(
                "delivered mechanism_graph.json declares no barrier_kcal_mol on "
                f"step edge {edge.id}"
            )
            continue
        declared = step.declared_kcal_mol
        # 该边全部合法组合（TS 日志 × 起点极小值日志；含策略选中的那组）。
        # 声明支撑得住哪一组、哪一组能对上参考，决定这条边怎么算分：
        # 支撑得住 → 正常数值路径；支撑不住但证据里有能对参考的 → 答案定义/
        # 构象指认差异（小扣分，不是科学错误）；两者皆无 → 无据声明 fail-loud。
        candidates = evidence.alternatives.get(step.edge_id) or [step]
        sigma_eff = _effective_sigma(rubric, edge.barrier_kcal_mol)
        supported = [
            c for c in candidates
            if abs(declared - c.barrier_kcal_mol) <= rubric.sigma_kcal_mol
        ]
        matches_ref = [
            c for c in candidates
            if abs(c.barrier_kcal_mol - edge.barrier_kcal_mol) <= sigma_eff
        ]

        if supported:
            same_as_ref = any(
                (c.ts_path, c.base_path) in {(m.ts_path, m.base_path) for m in matches_ref}
                for c in supported
            )
            if matches_ref and not same_as_ref:
                rep.edge_scores[edge.id] = _DEFINITION_MISMATCH_EDGE_SCORE
                weighted_sum += weights[edge.id] * _DEFINITION_MISMATCH_EDGE_SCORE
                ref = min(
                    matches_ref,
                    key=lambda c: (abs(c.barrier_kcal_mol - edge.barrier_kcal_mol),
                                   c.ts_path, c.base_path),
                )
                rep.notes.append(
                    f"edge {edge.id}: declared {declared:.3f} is supported by "
                    f"{supported[0].ts_path} / {supported[0].base_path}, but the "
                    f"delivered evidence also contains a combination consistent "
                    f"with the reference ({ref.barrier_kcal_mol:.3f} vs gold "
                    f"{edge.barrier_kcal_mol:.3f}, {ref.ts_path} / {ref.base_path}) "
                    "-> answer-definition mismatch, scored "
                    f"{_DEFINITION_MISMATCH_EDGE_SCORE}"
                )
                continue
            chosen = step if step in supported else min(
                supported,
                key=lambda c: (abs(declared - c.barrier_kcal_mol), c.ts_path, c.base_path),
            )
            g = gaussian_barrier_score(chosen.barrier_kcal_mol, edge.barrier_kcal_mol, sigma_eff)
            rep.edge_scores[edge.id] = g
            weighted_sum += weights[edge.id] * g
            rep.notes.append(
                f"edge {edge.id}: log-derived {chosen.barrier_kcal_mol:.3f} vs gold "
                f"{edge.barrier_kcal_mol:.3f} (sigma {sigma_eff:.1f}) -> {g:.4f} "
                f"(weight {weights[edge.id]})"
            )
            continue

        if matches_ref:
            ref = min(
                matches_ref,
                key=lambda c: (abs(c.barrier_kcal_mol - edge.barrier_kcal_mol),
                               c.ts_path, c.base_path),
            )
            rep.edge_scores[edge.id] = _DEFINITION_MISMATCH_EDGE_SCORE
            weighted_sum += weights[edge.id] * _DEFINITION_MISMATCH_EDGE_SCORE
            rep.notes.append(
                f"edge {edge.id}: declared {declared:.3f} is not supported by any "
                "delivered log combination, but the evidence contains one "
                f"consistent with the reference ({ref.barrier_kcal_mol:.3f} vs gold "
                f"{edge.barrier_kcal_mol:.3f}, {ref.ts_path} / {ref.base_path}) "
                "-> answer-definition mismatch, scored "
                f"{_DEFINITION_MISMATCH_EDGE_SCORE}"
            )
            continue

        rep.edge_scores[edge.id] = 0.0
        failures.append(
            "declared vs log-derived barrier disagreement on edge "
            f"{edge.id} beyond sigma {rubric.sigma_kcal_mol}: declared "
            f"{declared:.3f} vs logs {step.barrier_kcal_mol:.3f}"
        )

    if failures:
        # fail-loud：任一参考边的声明/推算缺失或不一致 -> 整题 accuracy 记 0，
        # 不给部分分，也不套 max_penalty_fraction 封顶。
        rep.notes.extend(f"{note}; scored 0" for note in failures)
        rep.gaussian_score = 0.0
        rep.capped_penalty = 1.0
        rep.final_score = 0.0
        return rep

    rep.gaussian_score = weighted_sum / weight_total
    raw_penalty = 1.0 - rep.gaussian_score
    rep.capped_penalty = min(raw_penalty, rubric.max_penalty_fraction)
    rep.final_score = 1.0 - rep.capped_penalty
    if raw_penalty > rubric.max_penalty_fraction:
        rep.notes.append(
            f"raw penalty {raw_penalty:.3f} capped at {rubric.max_penalty_fraction}"
        )
    return rep
