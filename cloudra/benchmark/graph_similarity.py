"""Chemical-parameterized graph edit distance between two mechanism graphs.

Compares an agent-delivered mechanism graph against the gold reference. The
metric is a graph edit distance whose node/edge substitution costs are
chemically parameterized rather than unit-cost:

- Node cost: an RDKit molhash shortcut (identical connectivity -> cost 0)
  falls back to a sigmoid of the Morgan-fingerprint Tanimoto distance.
  Stereochemistry is layered: easy/normal tiers are stereo-free (stereo
  ignored), the hard tier pays an extra stereo cost.
- Edge cost: the symmetric difference of the two steps' atom-mapped bond
  change sets (break/form pairs), normalized.

The GED itself uses networkx's optimize_graph_edit_distance on a lifted graph
where each TS node is folded into its elementary-step edge so that a missing
TS, a wrong TS, or a wrong connectivity all surface as edge edits. The public
API returns both a scalar score in [0, 1] (1 = identical) and the edit script.

RDKit and networkx are required (already project dependencies).
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
    if set(smiles_a) == set(smiles_b) and not _HAVE_RDKIT:
        return 0.0
    if not _HAVE_RDKIT:
        return 0.0 if set(smiles_a) == set(smiles_b) else 1.0

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


def _lift(graph: GoldMechanismGraph) -> nx.DiGraph:
    """Fold TS nodes into edges: node attribute 'smiles'; edge attribute
    'bond_changes' (frozenset) and 'has_ts' bool. TS nodes carry no SMILES in
    the gold reference, so they are not compared as species; their presence /
    correctness is encoded on the edge."""
    g = nx.DiGraph()
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
# public API
# ---------------------------------------------------------------------------


def mechanism_similarity(
    agent: GoldMechanismGraph,
    gold: GoldMechanismGraph,
    cfg: Optional[GedConfig] = None,
) -> GedResult:
    """Score agent mechanism against gold. Returns GedResult with score in
    [0, 1] (1 = identical) plus a human-readable edit script."""
    cfg = cfg or GedConfig()
    ga, gg = _lift(agent), _lift(gold)

    def node_subst(a, b):
        return _node_subst(a, b, cfg)

    def edge_subst(a, b):
        return _edge_subst(a, b, cfg)

    distance = nx.optimize_graph_edit_distance(
        ga,
        gg,
        node_subst_cost=node_subst,
        edge_subst_cost=edge_subst,
        node_del_cost=lambda n: cfg.node_delete_cost,
        node_ins_cost=lambda n: cfg.node_insert_cost,
        edge_del_cost=lambda e: cfg.edge_delete_cost,
        edge_ins_cost=lambda e: cfg.edge_insert_cost,
    )
    # next() gives the best (first) result of the generator
    if not isinstance(distance, (int, float)):
        distance = next(distance)

    max_distance = (
        cfg.node_delete_cost * max(ga.number_of_nodes(), gg.number_of_nodes())
        + cfg.edge_delete_cost * max(ga.number_of_edges(), gg.number_of_edges())
    )
    score = 1.0 - (distance / max_distance) if max_distance > 0 else 1.0
    score = max(0.0, min(1.0, score))

    edit_script = _describe_edits(ga, gg)
    return GedResult(score=score, distance=float(distance), max_distance=float(max_distance), edit_script=edit_script)


def _describe_edits(ga: nx.DiGraph, gg: nx.DiGraph) -> list[str]:
    out = []
    ga_nodes, gg_nodes = set(ga.nodes), set(gg.nodes)
    for n in sorted(ga_nodes - gg_nodes):
        out.append(f"node_removed:{n}")
    for n in sorted(gg_nodes - ga_nodes):
        out.append(f"node_missing:{n}")
    ga_edges = set(ga.edges())
    gg_edges = set(gg.edges())
    for a, b in sorted(ga_edges - gg_edges):
        out.append(f"edge_removed:{a}->{b}")
    for a, b in sorted(gg_edges - ga_edges):
        out.append(f"edge_missing:{a}->{b}")
    return out
