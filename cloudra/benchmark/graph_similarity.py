"""Chemical-parameterized graph scoring between two mechanism graphs.

Compares an agent-delivered mechanism graph against the gold reference.
Default scoring is **subgraph coverage** (`GedConfig.subgraph_scoring=True`):
the gold graph must embed into the delivered graph — extra delivered
nodes/edges are free ("thinking more is never punished"), missing or
chemically mismatched gold elements cost. A symmetric GED mode
(`subgraph_scoring=False`, networkx optimize_graph_edit_distance) is kept for
diagnostics.

- Node cost: an RDKit molhash shortcut (identical connectivity -> cost 0)
  falls back to a sigmoid of the Morgan-fingerprint Tanimoto distance.
  Stereochemistry is layered: easy/normal tiers are stereo-free (stereo
  ignored), the hard tier pays an extra stereo cost.
- Edge cost: the symmetric difference of the two steps' atom-mapped bond
  change sets (break/form pairs), normalized.

Both modes work on a lifted graph where each TS node is folded into its
elementary-step edge so that a missing TS, a wrong TS, or a wrong connectivity
all surface as edge edits. The public API returns both a scalar score in
[0, 1] (1 = gold fully covered) and the edit script.

RDKit is optional: without it node substitution degrades to exact set
equality of the SMILES lists (0 or 1). networkx is a hard dependency (lifted
graph representation; only exercised for search in symmetric-GED mode).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from cloudra.benchmark.schema import GoldMechanismGraph

try:  # RDKit is an optional import guard so non-chem contexts can still import
    from rdkit import Chem
    from rdkit.Chem import rdMolHash
    from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator

    _HAVE_RDKIT = True
except Exception:  # pragma: no cover
    _HAVE_RDKIT = False


@dataclass
class GedConfig:
    sigmoid_center: float = 0.40
    sigmoid_steepness: float = 10.0
    stereo_free: bool = True           # easy/normal: ignore stereochemistry
    # 子图打分（默认）：gold 图嵌入交付图即满分，交付多出的节点/边不罚
    # （"多想总是好事"）；缺失/化学不符的 gold 元素按插入代价扣分。
    # False 退回对称 GED（仅诊断用；最坏指数复杂度，受尺寸守卫保护）。
    subgraph_scoring: bool = True
    node_delete_cost: float = 1.0
    node_insert_cost: float = 1.0
    edge_delete_cost: float = 1.0
    edge_insert_cost: float = 1.0
    morgan_radius: int = 2
    morgan_nbits: int = 2048


@dataclass
class GedResult:
    score: float                       # 1.0 = identical, 0.0 = maximally different
    distance: float
    max_distance: float
    edit_script: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# per-species chemistry
# ---------------------------------------------------------------------------


def _mol(smiles: str):
    if not _HAVE_RDKIT:
        return None
    m = Chem.MolFromSmiles(smiles)
    return m


def _molhash(smiles: str, stereo_free: bool) -> Optional[str]:
    m = _mol(smiles)
    if m is None:
        return None
    if stereo_free:
        m = Chem.Mol(m)
        Chem.RemoveStereochemistry(m)
    try:
        return rdMolHash.MolHash(m, rdMolHash.HashFunction.CanonicalSmiles)
    except Exception:
        return Chem.MolToSmiles(m)


_MORGAN_GEN_CACHE: dict[tuple[int, int], object] = {}


def _morgan(smiles: str, cfg: GedConfig):
    m = _mol(smiles)
    if m is None:
        return None
    if cfg.stereo_free:
        m = Chem.Mol(m)
        Chem.RemoveStereochemistry(m)
    key = (cfg.morgan_radius, cfg.morgan_nbits)
    gen = _MORGAN_GEN_CACHE.get(key)
    if gen is None:
        gen = GetMorganGenerator(radius=cfg.morgan_radius, fpSize=cfg.morgan_nbits)
        _MORGAN_GEN_CACHE[key] = gen
    return gen.GetFingerprint(m)


def _tanimoto(fp_a, fp_b) -> float:
    if fp_a is None or fp_b is None:
        return 0.0
    from rdkit import DataStructs

    return DataStructs.TanimotoSimilarity(fp_a, fp_b)


def protonation_variant_quality(
    smiles_a: str, smiles_b: str, cfg: GedConfig, base_quality: float = 0.7
) -> float:
    """质子化/电荷态变体的绑定质量；骨架不同（非变体）返回 0.0。

    扣减不是定值：quality = 1 - (1 - base_quality) * w，权重 w = 指纹相对误差
    (1 - Morgan Tanimoto)。指纹在单重原子离子对上退化（[OH3+]/O 的 Tanimoto=0
    → w=1 → 扣满到 base_quality）；分子越大、质子化位点占比越小，w 越小、扣得
    越少（乙酸/乙酸根 t=0.5 → 0.85；14 重原子联苯胺/铵盐 t=0.59 → 0.88）。
    骨架通道只负责"圈定变体类"，严重程度由指纹度量。"""
    sa, sb = protonation_skeleton(smiles_a), protonation_skeleton(smiles_b)
    if sa is None or sa != sb:
        return 0.0
    w = 1.0 - _tanimoto(_morgan(smiles_a, cfg), _morgan(smiles_b, cfg))
    return 1.0 - (1.0 - base_quality) * w


def protonation_skeleton(smiles: str) -> Optional[str]:
    """质子化/电荷态不变的骨架标识：剥掉形式电荷、移除全部氢后的 canonical
    SMILES。`[OH3+]`/`O`/`[OH-]` 归一为 `O`，乙酸根/乙酸归一；键级保留，
    因此乙烷 vs 乙烯这类真实物种差异不受影响。纯氢体系（H2 等）无骨架可剥，
    退回归一前的 canonical hash；无法解析返回 None。"""
    if not _HAVE_RDKIT:
        return None
    m = _mol(smiles)
    if m is None:
        return None
    if all(a.GetAtomicNum() == 1 for a in m.GetAtoms()):
        return _molhash(smiles, True)
    m = Chem.RWMol(m)
    for atom in m.GetAtoms():
        # 清零电荷与显式氢计数后让 sanitize 重算隐含氢：[OH3+]/[OH-]/O 都归一为水
        atom.SetFormalCharge(0)
        atom.SetNumExplicitHs(0)
        atom.SetNoImplicit(False)
    try:
        Chem.SanitizeMol(m)
        return Chem.MolToSmiles(m.GetMol())
    except Exception:
        return None


def _sigmoid(tanimoto: float, center: float, steepness: float) -> float:
    # cost near 0 when tanimoto >> center, near 1 when tanimoto << center
    return 1.0 / (1.0 + math.exp(steepness * (tanimoto - center)))


def species_substitution_cost(smiles_a: list[str], smiles_b: list[str], cfg: GedConfig) -> float:
    """Cost to substitute a node whose species set is smiles_a by smiles_b.

    Multi-species nodes (complexes) are compared as sorted sets: the minimal
    total pairwise cost over the best assignment, normalized to [0, 1].
    """
    if not smiles_a and not smiles_b:
        return 0.0
    if not _HAVE_RDKIT:
        # 无 RDKit 时退化为多重集相等（排序列表比较，保留重复组分）：相同 0，不同 1
        return 0.0 if sorted(smiles_a) == sorted(smiles_b) else 1.0

    # molhash shortcut: identical canonical hash for every species -> 0
    ha = sorted(_molhash(s, cfg.stereo_free) or s for s in smiles_a)
    hb = sorted(_molhash(s, cfg.stereo_free) or s for s in smiles_b)
    if ha == hb:
        return 0.0

    fps_a = [_morgan(s, cfg) for s in smiles_a]
    fps_b = [_morgan(s, cfg) for s in smiles_b]
    n = max(len(smiles_a), len(smiles_b))
    if not smiles_a or not smiles_b:
        return 1.0  # one side has no species: full substitution cost

    # greedy assignment cost (small node sets, fine without Hungarian)
    import itertools

    best = math.inf
    for perm in itertools.permutations(range(len(fps_b))):
        total = 0.0
        for i, fa in enumerate(fps_a):
            fb = fps_b[perm[i]] if i < len(perm) else None
            total += _sigmoid(_tanimoto(fa, fb), cfg.sigmoid_center, cfg.sigmoid_steepness)
        # penalty for cardinality mismatch
        total += abs(len(fps_a) - len(fps_b))
        best = min(best, total)
    return min(1.0, best / n)


# ---------------------------------------------------------------------------
# lift mechanism graph to a plain networkx DiGraph
# ---------------------------------------------------------------------------


def _lift(graph: GoldMechanismGraph) -> nx.MultiDiGraph:
    """Fold TS nodes into edges: node attribute 'smiles'; edge attribute
    'bond_changes' (frozenset) and 'has_ts' bool. TS nodes carry no SMILES in
    the gold reference, so they are not compared as species; their presence /
    correctness is encoded on the edge.

    MultiDiGraph：同一对物种间可能有多条基元步边（双通道机理），普通
    DiGraph 会互相覆盖丢边。"""
    g = nx.MultiDiGraph()
    ts_ids = {n.id for n in graph.nodes if n.role.value == "transition_state"}
    for n in graph.nodes:
        if n.id in ts_ids:
            continue
        g.add_node(n.id, smiles=tuple(sorted(n.smiles)), accessible=n.accessible)
    for e in graph.edges:
        g.add_edge(
            e.from_node,
            e.to_node,
            bond_changes=e.bond_changes.pairs(),
            has_ts=bool(e.via),
            accessible=e.accessible,
        )
    return g


def _node_subst(n1, n2, cfg: GedConfig) -> float:
    return species_substitution_cost(list(n1.get("smiles", ())), list(n2.get("smiles", ())), cfg)


def _edge_subst(e1, e2, cfg: GedConfig) -> float:
    bc1 = e1.get("bond_changes", frozenset())
    bc2 = e2.get("bond_changes", frozenset())
    if not bc1 and not bc2:
        bond_cost = 0.0
    else:
        sym = bc1.symmetric_difference(bc2)
        union = bc1 | bc2
        bond_cost = len(sym) / len(union) if union else 0.0
    ts_cost = 0.0 if e1.get("has_ts") == e2.get("has_ts") else 0.5
    return min(1.0, bond_cost + ts_cost)


# ---------------------------------------------------------------------------
# subgraph coverage scoring (default)
# ---------------------------------------------------------------------------


# 单个 gold 节点的候选数 × 组合数的暴力 DFS 护栏：gold 图很小（easy 档 2 个
# 物种节点），正常交付候选列表很短；失控交付下候选爆炸时退回贪心指派。
_ASSIGNMENT_DFS_BUDGET = 200_000


def _assign_gold_nodes(
    gold_nodes: list[str],
    agent_nodes: list[str],
    cost_of,
    edge_cost_of=None,
) -> dict[str, Optional[str]]:
    """Injective gold->agent node assignment minimizing total cost.

    目标是节点替换代价 + （完整指派下的）边代价之和：退化机理（R/P 同
    SMILES）里节点代价并列的指派有多个，边连通性必须参与 tie-break，否则
    交叉指派会把真实存在的边判成缺失。未匹配的 gold 节点等价于"缺失"（按
    插入代价记账）。候选 = 替换代价严格小于 1.0 的节点（等于 1.0 与缺失同价
    且对边评估无意义）。候选组合在预算内全量 DFS，超预算退回贪心（仅按节点
    代价）。"""
    candidates: dict[str, list[tuple[float, str]]] = {}
    for g in gold_nodes:
        cands = sorted(
            (c, a) for a in agent_nodes if (c := cost_of(g, a)) < 1.0
        )
        candidates[g] = cands
    budget = 1
    for g in gold_nodes:
        budget *= max(1, len(candidates[g]))
    if budget <= _ASSIGNMENT_DFS_BUDGET:
        best_cost = math.inf
        best: dict[str, Optional[str]] = {}

        def dfs(i: int, used: set[str], total: float, cur: dict[str, Optional[str]]) -> None:
            nonlocal best_cost, best
            if total >= best_cost:
                return  # 边代价非负：节点部分已不优即可剪枝
            if i == len(gold_nodes):
                full = total + (edge_cost_of(cur) if edge_cost_of is not None else 0.0)
                if full < best_cost:
                    best_cost, best = full, dict(cur)
                return
            g = gold_nodes[i]
            for cost, a in candidates[g]:
                if a in used:
                    continue
                cur[g] = a
                dfs(i + 1, used | {a}, total + cost, cur)
            cur[g] = None  # 缺失
            dfs(i + 1, used, total + 1.0, cur)
            cur.pop(g)

        dfs(0, set(), 0.0, {})
        return best
    used: set[str] = set()
    assignment: dict[str, Optional[str]] = {}
    for g in sorted(gold_nodes, key=lambda g: candidates[g][0][0] if candidates[g] else math.inf):
        pick = next(((c, a) for c, a in candidates[g] if a not in used), None)
        if pick is not None:
            assignment[g] = pick[1]
            used.add(pick[1])
        else:
            assignment[g] = None
    return assignment


def _subgraph_similarity(
    agent: GoldMechanismGraph, gold: GoldMechanismGraph, cfg: GedConfig
) -> GedResult:
    """Subgraph coverage: every gold element must be covered by the delivered
    graph; extra delivered elements are free. Polynomial in practice (gold
    graphs are small), so no size guard is needed in this mode."""
    ga, gg = _lift(agent), _lift(gold)
    gold_nodes = list(gg.nodes)
    agent_nodes = list(ga.nodes)

    def cost_of(g: str, a: str) -> float:
        return _node_subst(gg.nodes[g], ga.nodes[a], cfg)

    def edge_cost_of(asn: dict[str, Optional[str]]) -> float:
        total = 0.0
        for u, v, gattrs in gg.edges(data=True):
            mu, mv = asn.get(u), asn.get(v)
            step = cfg.edge_insert_cost
            if mu is not None and mv is not None:
                for _key, aattrs in ga.get_edge_data(mu, mv, default={}).items():
                    step = min(step, _edge_subst(aattrs, gattrs, cfg))
            total += min(step, cfg.edge_insert_cost)
        return total

    assignment = _assign_gold_nodes(gold_nodes, agent_nodes, cost_of, edge_cost_of)

    distance = edge_cost_of(assignment)
    for g in gold_nodes:
        a = assignment.get(g)
        distance += cost_of(g, a) if a is not None else cfg.node_insert_cost

    max_distance = (
        cfg.node_insert_cost * gg.number_of_nodes()
        + cfg.edge_insert_cost * gg.number_of_edges()
    )
    score = 1.0 - (distance / max_distance) if max_distance > 0 else 1.0
    score = max(0.0, min(1.0, score))
    return GedResult(
        score=score,
        distance=float(distance),
        max_distance=float(max_distance),
        edit_script=_describe_edits(ga, gg),
    )


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


# 对称 GED 模式的交付图规模守卫：optimize_graph_edit_distance 最坏指数复杂度，
# 失控 agent 交付超大图会挂住评分器。交付节点数超过 max(比值 * gold 节点数,
# 绝对上限) 时直接判最大差异，不调用 networkx。子图打分模式多项式可控，不适用。
_GED_SIZE_GUARD_RATIO = 4
_GED_SIZE_GUARD_ABS = 30


def mechanism_similarity(
    agent: GoldMechanismGraph,
    gold: GoldMechanismGraph,
    cfg: Optional[GedConfig] = None,
) -> GedResult:
    """Score agent mechanism against gold. Returns GedResult with score in
    [0, 1] (1 = gold fully covered / identical) plus a human-readable edit
    script. Default mode is subgraph coverage (extras free); pass
    `GedConfig(subgraph_scoring=False)` for the symmetric GED diagnostic."""
    cfg = cfg or GedConfig()
    if cfg.subgraph_scoring:
        return _subgraph_similarity(agent, gold, cfg)
    guard_limit = max(_GED_SIZE_GUARD_RATIO * len(gold.nodes), _GED_SIZE_GUARD_ABS)
    if len(agent.nodes) > guard_limit:
        max_distance = (
            cfg.node_delete_cost * max(len(agent.nodes), len(gold.nodes))
            + cfg.edge_delete_cost * max(len(agent.edges), len(gold.edges))
        )
        note = (
            f"delivered graph too large ({len(agent.nodes)} nodes > guard limit "
            f"{guard_limit}, gold has {len(gold.nodes)}); short-circuited to "
            "maximally different without running GED"
        )
        return GedResult(score=0.0, distance=max_distance, max_distance=max_distance, edit_script=[note])
    ga, gg = _lift(agent), _lift(gold)

    def node_subst(a, b):
        return _node_subst(a, b, cfg)

    def edge_subst(a, b):
        return _edge_subst(a, b, cfg)

    gen = nx.optimize_graph_edit_distance(
        ga,
        gg,
        node_subst_cost=node_subst,
        edge_subst_cost=edge_subst,
        node_del_cost=lambda n: cfg.node_delete_cost,
        node_ins_cost=lambda n: cfg.node_insert_cost,
        edge_del_cost=lambda e: cfg.edge_delete_cost,
        edge_ins_cost=lambda e: cfg.edge_insert_cost,
    )
    # 生成器逐个产出逐步改进的上界（networkx 文档语义），取最小值即最优近似；
    # 取第一个产出会系统性高估距离。
    distance = min(gen) if not isinstance(gen, (int, float)) else gen

    max_distance = (
        cfg.node_delete_cost * max(ga.number_of_nodes(), gg.number_of_nodes())
        + cfg.edge_delete_cost * max(ga.number_of_edges(), gg.number_of_edges())
    )
    score = 1.0 - (distance / max_distance) if max_distance > 0 else 1.0
    score = max(0.0, min(1.0, score))

    edit_script = _describe_edits(ga, gg)
    return GedResult(score=score, distance=float(distance), max_distance=float(max_distance), edit_script=edit_script)


def _describe_edits(ga: nx.MultiDiGraph, gg: nx.MultiDiGraph) -> list[str]:
    """Human-readable structural diff. Agent 与 gold 的节点 id 命名空间不同，
    按 id 做差永远得到"全 removed/missing"，因此按物种 SMILES 多重集与
    （端点 SMILES + 键变化）描述的步骤多重集来描述差异。"""
    def species(multigraph):
        return sorted(tuple(sorted(attrs.get("smiles", ()))) for _, attrs in multigraph.nodes(data=True))

    def steps(multigraph):
        return sorted(
            (
                tuple(sorted(multigraph.nodes[u].get("smiles", ()))),
                tuple(sorted(multigraph.nodes[v].get("smiles", ()))),
                tuple(sorted(attrs.get("bond_changes", frozenset()))),
                # TS 折叠进边后，"是否经由 TS" 必须进 diff 键，否则缺 TS 的交付
                # 分数扣了、诊断文本却显示无差异
                bool(attrs.get("has_ts")),
            )
            for u, v, attrs in multigraph.edges(data=True)
        )

    out = []
    sa, sg = species(ga), species(gg)
    for s in sorted(set(sa) - set(sg)):
        out.append(f"species_removed:{list(s)}")
    for s in sorted(set(sg) - set(sa)):
        out.append(f"species_missing:{list(s)}")
    ea, eg = steps(ga), steps(gg)
    for e in sorted(set(ea) - set(eg)):
        out.append(f"step_removed:{e}")
    for e in sorted(set(eg) - set(ea)):
        out.append(f"step_missing:{e}")
    return out
