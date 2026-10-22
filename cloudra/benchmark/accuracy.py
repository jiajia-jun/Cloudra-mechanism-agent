"""Layer 3 — accuracy: 以交付物为准的逐边能垒/性质评分（不读任何 LLM 散文）。

口径（与题库 query 协议一致）：gold 机理图**逐边**承载参考答案能垒；评分边
集合是**全部 gold 边**，逐边规则：

- 带参考值（``barrier_kcal_mol`` 非 None）→ 双来源核对：要求两条独立来源
  **都存在且一致**——``log_barrier_kcal``（harness 从沙箱内绑定日志推出的值，
  ``barrier_evidence``）与 ``declared_barrier_kcal``（交付
  ``mechanism_graph.json`` 里该边声明的 ``barrier_kcal_mol``）；
- 不带参考值且有效可达（``accessible`` 且经由的 TS 节点也可达，见
  ``GoldMechanismGraph.edge_effectively_accessible``）→ 该边记 1.0（可算但
  标答未给参考值，记满分）；
- 标答规定不可达（边自身或经由的 TS 节点 ``accessible=false``）→ 匹配最终
  交付：正确否定记 1.0，误报可达、声明可信能垒或漏交记 0.0；标答中的负
  端点物种也必须否定；负性质题不能同时交付可信的能量差或键长数值。
  此分类罚分不被 ``max_penalty_fraction`` 封顶救回。

带参考值的边缺日志推算或缺声明 → 该边 0 分，仍占总权重，不清掉其他边贡献，
缺失罚分不受数值扣分封顶保护。声明在**任何合法组合**下都得不到支撑且证据
也对不上参考 → 置 fail-loud 结构化标记（``AccuracyReport.fail_loud``），由
runner 据此短路 composite（final 只保留图分；绝不用最终消息里的数字兜底）。
声明支撑得住（或虽支撑不住、但交付证据
里另有与参考一致的组合——即 agent 选了另一个构象/参考系定义、而正确的计算
已在它的日志里）→ 走正常数值路径或按「答案定义差异」固定小扣分
（`_DEFINITION_MISMATCH_EDGE_SCORE`），**不触发 fail-loud**（用户口径：这是
答案定义问题，不是科学错误）。一致后与 gold 边值比，用高斯容差评分；逐边
分数按 gold 边 ``weight`` 加权平均（权重越大 = 该边越容易算准/越可核实）。
带参考值边的罚分汇总后按 ``max_penalty_fraction`` 封顶；无参考边的
1.0/0.0 结构记账不封顶（见上）。

若 gold 机理图没有任何边但含负物种 → 按同物种、同角色的最终不可达声明
评分；没有负目标时沿用旧 null 行为（final_score=1.0）。探索日志不构成最终
可达声明。

性质锚点（``GoldSpec.reference_properties``，键带单位）：读交付图物种节点的
``properties`` 按键比对——数值型走高斯容差（σ 查模块级显式常量表
``_PROPERTY_SIGMAS``，键名子串匹配，表外数值键 fail-loud 抛错逼显式登记）；
字符串型（state_ordering 等）小写去空白后精确相等。多性质题取各键均值。

hard 档定性选择性（``score_qualitative_selectivity``）：任务带
``gold.selectivity.favored_channel`` 时替代 accuracy 槽位（composite 的
accuracy 权重给选择性分）——交付边中恰好一条 ``favored: true`` 且其
``channel`` 等于 gold favored_channel → 1.0，否则 0.0；barrier spread 数值
不评分。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from cloudra.benchmark.schema import (
    AccuracyRubric,
    GoldMechanismGraph,
    GoldSpec,
    NodeRole,
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
# 固定小扣分计入加权，绝不触发 fail-loud（用户口径）。
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
    final_score: float = 0.0             # 1 - capped_penalty（缺证据/声明的边计 0）
    # fail-loud：声明与日志冲突、且证据也对不上参考时置 True；缺失不触发。
    # 本层 accuracy 记 0，runner 据此短路 composite（final 只保留图分）。
    fail_loud: bool = False
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


def _has_trusted_property_number(graph: GoldMechanismGraph | None) -> bool:
    """当前负性质题的能量差/键长数值声明；诊断字段及文字说明不算。"""
    return bool(graph) and any(
        isinstance(value, (int, float))
        and any(
            token in key for token, _ in _PROPERTY_SIGMAS
            if token in ("kcal_mol", "bond_length_angstrom")
        )
        for node in graph.nodes
        for key, value in node.properties.items()
    )


def _negative_edge_claim_correct(gold_edge, gold_nodes, delivered_edge, delivered_graph) -> bool:
    if delivered_edge is None or delivered_graph is None:
        return False
    if (
        delivered_graph.edge_effectively_accessible(delivered_edge)
        or delivered_edge.barrier_kcal_mol is not None
        or (gold_edge.via is None and _has_trusted_property_number(delivered_graph))
    ):
        return False
    delivered_nodes = {node.id: node for node in delivered_graph.nodes}
    return all(
        gold_nodes[gold_id].accessible or not delivered_nodes[delivered_id].accessible
        for gold_id, delivered_id in (
            (gold_edge.from_node, delivered_edge.from_node),
            (gold_edge.to_node, delivered_edge.to_node),
        )
    )


def _find_matching_step(
    gold_edge,
    gold_nodes: dict,
    steps: list | None,
    delivered_graph: Optional[GoldMechanismGraph],
    cfg,
    match_threshold: float,
    require_channel: bool = False,
):
    """按**物种对应**找 gold 边的交付步（edge id 是题库内部约定，agent 不可知，
    绝不参与匹配）：交付边的 from/to 端点物种与 gold 边**同向**端点分别匹配
    （species_substitution_cost ≤ 阈值，与 Layer 1/graph GED 同口径；反向步
    能垒口径不同不匹配）。多候选按 bond_changes 对称差最小、端点代价最小、
    edge id 字典序取（确定性）。steps=None 时直接匹配交付边，不要求能垒
    证据；最佳键变化候选中若有正断言，优先返回它，不能用重复负声明掩盖。"""
    candidates = _rank_matching_steps(
        gold_edge, gold_nodes, steps, delivered_graph, cfg, match_threshold,
        require_channel,
    )
    if not candidates:
        return None
    if steps is None:
        best_bond_cost = candidates[0][0]
        for bond_cost, _, _, candidate in candidates:
            if bond_cost == best_bond_cost and not _negative_edge_claim_correct(
                gold_edge, gold_nodes, candidate, delivered_graph
            ):
                return candidate
    return candidates[0][3]


def _rank_matching_steps(
    gold_edge,
    gold_nodes: dict,
    steps: list | None,
    delivered_graph: Optional[GoldMechanismGraph],
    cfg,
    match_threshold: float,
    require_channel: bool = False,
):
    """All legal deliveries for one gold edge, ranked by the matching rules."""
    from cloudra.benchmark.graph_similarity import species_substitution_cost

    if delivered_graph is None:
        return []
    delivered_nodes = {n.id: n for n in delivered_graph.nodes}
    delivered_edges = {e.id: e for e in delivered_graph.edges}
    gold_from = gold_nodes.get(gold_edge.from_node)
    gold_to = gold_nodes.get(gold_edge.to_node)
    if gold_from is None or gold_to is None:
        return []
    gold_pairs = gold_edge.bond_changes.pairs()
    candidates: list[tuple[int, float, str, object]] = []
    for step in steps if steps is not None else delivered_graph.edges:
        d_edge = delivered_edges.get(step.edge_id) if steps is not None else step
        if d_edge is None:
            continue
        if require_channel and d_edge.channel != gold_edge.channel:
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
        candidates.append((symdiff, cost_from + cost_to, d_edge.id, step))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates


def _assign_matching_steps(
    scored_edges,
    edge_signatures,
    gold_nodes: dict,
    evidence,
    delivered_graph,
    cfg,
    match_threshold: float,
) -> dict:
    """Maximum-cardinality, minimum-chemistry-cost one-to-one assignment.

    Preserve the existing eligibility and bond/endpoint cost ordering globally.
    Exact ties follow Gold graph order and delivered IDs, never private Gold IDs
    or numerical agreement with the answer. Ungraded edges consume no evidence.
    """
    from fractions import Fraction

    import networkx as nx

    steps = evidence.steps if evidence is not None else None
    ranked = []
    equal_weights = sum(edge.weight for edge in scored_edges) <= 0
    for index, (edge, signature) in enumerate(zip(scored_edges, edge_signatures)):
        if edge.barrier_kcal_mol is None or (edge.weight == 0 and not equal_weights):
            continue
        require_channel = edge.channel is not None and edge_signatures.count(signature) > 1
        for symdiff, cost, step_id, step in _rank_matching_steps(
            edge, gold_nodes, steps, delivered_graph, cfg, match_threshold,
            require_channel,
        ):
            ranked.append((index, edge.id, symdiff, Fraction(cost), step_id, step))
    if not ranked:
        return {}

    # Float costs have power-of-two denominators. Convert them exactly so the
    # solver's deterministic tie-break cannot outweigh any chemical difference.
    denominator = max(item[3].denominator for item in ranked)
    count = len(scored_edges)
    bond_scale = count * max(int(item[3] * denominator) for item in ranked) + 1
    step_ids = sorted({item[4] for item in ranked})
    step_order = {step_id: index for index, step_id in enumerate(step_ids)}
    base = len(step_ids) + 1
    tie_scale = count * base ** (count + 1) + 1
    matching_graph = nx.Graph()
    for index, edge_id, symdiff, cost, step_id, step in ranked:
        chemistry_cost = symdiff * bond_scale + int(cost * denominator)
        tie = (step_order[step_id] - len(step_ids)) * base ** (count - index - 1)
        matching_graph.add_edge(('gold', edge_id), ('delivery', step_id),
            weight=chemistry_cost * tie_scale + tie, step=step)
    assigned = {}
    for left, right in nx.min_weight_matching(matching_graph):
        gold_key, delivery_key = (left, right) if left[0] == 'gold' else (right, left)
        assigned[gold_key[1]] = matching_graph.edges[gold_key, delivery_key]['step']
    return assigned


def score_accuracy(
    *,
    evidence: "BarrierEvidence",
    gold: GoldSpec,
    rubric: AccuracyRubric | None = None,
    delivered_graph: Optional[GoldMechanismGraph] = None,
    cfg=None,
    match_threshold: float = 0.2,
) -> AccuracyReport:
    """评分边集合 = 全部 gold 边：带参考值的边逐边核对（"声明得到日志支撑"），
    再对 gold 比、按 gold 边 weight 加权平均；不带参考值的 accessible 边记 1.0，
    不可达目标按最终交付的正确负声明记 1.0，误报或漏交记 0.0。
    gold.reference_properties 非空时走性质锚点模式（与能垒模式互斥）。"""
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
        rep.notes.append("accuracy disabled for this task; scored 1.0 (computable but not graded)")
        return rep
    if gold.reference_properties:
        return _score_properties(delivered_graph, gold.reference_properties, rep)
    from cloudra.benchmark.graph_similarity import GedConfig, species_substitution_cost

    cfg = cfg or GedConfig()
    scored_edges = list(gold.mechanism_graph.edges)
    if not scored_edges:
        negative_nodes = [
            node for node in gold.mechanism_graph.nodes
            if not node.accessible and node.role is not NodeRole.TRANSITION_STATE
        ]
        if negative_nodes:
            trusted_number = _has_trusted_property_number(delivered_graph)
            scores = []
            for node in negative_nodes:
                matches = [
                    candidate for candidate in (delivered_graph.nodes if delivered_graph else [])
                    if candidate.role == node.role
                    and species_substitution_cost(node.smiles, candidate.smiles, cfg) <= match_threshold
                ]
                correct = (
                    bool(matches) and not trusted_number
                    and all(not candidate.accessible for candidate in matches)
                )
                scores.append(float(correct))
                rep.notes.append(
                    f"negative species {node.id}: "
                    f"{'correct negative final claim' if correct else 'positive or missing final claim'}; "
                    f"scored {int(correct)}"
                )
            rep.gaussian_score = rep.final_score = sum(scores) / len(scores)
            rep.capped_penalty = 1.0 - rep.final_score
            return rep
        rep.gaussian_score = 1.0
        rep.final_score = 1.0
        rep.notes.append("gold mechanism graph carries no edges; accuracy not scored")
        return rep

    # 逐边核对：缺失计该边零分，声明/日志冲突才触发 fail-loud。
    gold_nodes = {n.id: n for n in gold.mechanism_graph.nodes}
    # 全零权重无法归一：退回逐边等权（避免除零；正常题库不出现）
    equal_fallback = sum(e.weight for e in scored_edges) <= 0
    if equal_fallback:
        rep.notes.append(
            "all scored-edge weights are zero; falling back to equal weighting"
        )
    weights = {e.id: (1.0 if equal_fallback else e.weight) for e in scored_edges}
    weight_total = sum(weights.values())
    edge_signatures = [
        (e.from_node, e.to_node, frozenset(e.bond_changes.pairs()))
        for e in scored_edges
    ]

    assigned_steps = _assign_matching_steps(
        scored_edges, edge_signatures, gold_nodes, evidence, delivered_graph,
        cfg, match_threshold,
    )

    failures: list[str] = []
    weighted_sum = 0.0
    graded_weight = 0.0        # 已交付双来源参考边的权重和（高斯/定义差异罚分）
    graded_score_sum = 0.0     # Σ w·g（带参考值边）
    uncapped_penalty = 0.0     # 缺证据、缺声明或负目标误报/漏交的零分记账
    for edge, signature in zip(scored_edges, edge_signatures):
        if edge.barrier_kcal_mol is None:
            if gold.mechanism_graph.edge_effectively_accessible(edge):
                rep.edge_scores[edge.id] = 1.0
                weighted_sum += weights[edge.id] * 1.0
                rep.notes.append(
                    f"edge {edge.id}: accessible but the gold reference carries no "
                    "reference barrier; scored 1.0"
                )
            else:
                delivered_edge = _find_matching_step(
                    edge, gold_nodes, None, delivered_graph, cfg, match_threshold,
                    require_channel=edge.channel is not None and edge_signatures.count(signature) > 1,
                )
                correct = _negative_edge_claim_correct(edge, gold_nodes, delivered_edge, delivered_graph)
                rep.edge_scores[edge.id] = float(correct)
                weighted_sum += weights[edge.id] * float(correct)
                uncapped_penalty += weights[edge.id] * float(not correct)
                rep.notes.append(
                    f"edge {edge.id}: effectively inaccessible in the gold reference; "
                    f"{'correct negative final claim' if correct else 'positive or missing final claim'}; "
                    f"scored {int(correct)}"
                )
            continue
        step = assigned_steps.get(edge.id)
        if step is None:
            rep.edge_scores[edge.id] = 0.0
            uncapped_penalty += weights[edge.id]
            rep.notes.append(
                f"gold edge {edge.id} carries a reference barrier but no delivered "
                "step matches its endpoint species; scored 0"
            )
            continue
        if step.edge_id != edge.id:
            rep.notes.append(
                f"gold edge {edge.id} matched delivered step {step.edge_id} "
                "by endpoint species"
            )
        if step.declared_kcal_mol is None:
            rep.edge_scores[edge.id] = 0.0
            uncapped_penalty += weights[edge.id]
            rep.notes.append(
                "delivered mechanism_graph.json declares no barrier_kcal_mol on "
                f"step edge {edge.id}; scored 0"
            )
            continue
        graded_weight += weights[edge.id]
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
                graded_score_sum += weights[edge.id] * _DEFINITION_MISMATCH_EDGE_SCORE
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
            graded_score_sum += weights[edge.id] * g
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
            graded_score_sum += weights[edge.id] * _DEFINITION_MISMATCH_EDGE_SCORE
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
        # fail-loud：参考边的声明/日志冲突且证据对不上参考 -> 置结构化标记、本层
        # accuracy 记 0（不给部分分，也不套 max_penalty_fraction 封顶），
        # composite 的短路由 runner 按 fail_loud 执行。
        rep.notes.extend(f"{note}; scored 0" for note in failures)
        rep.fail_loud = True
        rep.gaussian_score = 0.0
        rep.capped_penalty = 1.0
        rep.final_score = 0.0
        return rep

    rep.gaussian_score = weighted_sum / weight_total
    # max_penalty_fraction 只封顶带参考值边的罚分（高斯偏离/定义差异——兜合法的
    # 方法学差异）；缺失和负目标误报直接记账、不参与封顶，避免漏交或错误
    # 可达声明被数值容差保底抬分。
    graded_penalty = (graded_weight - graded_score_sum) / weight_total
    capped_graded = min(graded_penalty, rubric.max_penalty_fraction)
    rep.capped_penalty = capped_graded + uncapped_penalty / weight_total
    rep.final_score = 1.0 - rep.capped_penalty
    if graded_penalty > rubric.max_penalty_fraction:
        rep.notes.append(
            f"numeric penalty {graded_penalty:.3f} capped at {rubric.max_penalty_fraction}"
        )
    return rep
