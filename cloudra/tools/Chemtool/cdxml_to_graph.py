"""CDXML reaction-scheme parser: build a SMILES graph and an optional DAG proposal.

This module intentionally does **not** depend on cdxml_tools or pycdxml.  It uses:

* ``molli`` for high-fidelity CDXML structure parsing (connectivity, charge,
  multiplicity, stereochemistry/wedge information).
* RDKit only for canonical isomeric SMILES serialization (via a mol2 roundtrip
  from molli, avoiding the openbabel dependency in ``molli.external.rdkit``).
* A small custom reaction-layout parser over ``molli.CDXMLFile.tree`` for arrow
  detection and reactant/product/reagent/solvent/condition role assignment.

The tool is read-only: it never writes the DAG itself.  In DAG mode it returns a
ready-to-use ``dag_propose_mechanism`` payload for the Coordinator.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_existing_tool_path

try:
    import molli as ml
    _MOLLI_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    ml = None
    _MOLLI_AVAILABLE = False

try:
    from rdkit import Chem
    _RDKIT_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    Chem = None
    _RDKIT_AVAILABLE = False

description = (
    "Parse a ChemDraw CDXML reaction scheme into a graph whose nodes are "
    "isomeric SMILES (reactant/product complexes) and whose edges are candidate "
    "elementary steps from the drawn arrows. Uses molli for stereochemical "
    "fidelity and RDKit for canonical SMILES. If the parsed graph is a DAG, "
    "also returns a ready-to-use dag_propose_mechanism payload. "
    "Use for: a .cdxml file exported from ChemDraw (Selection -> Get CDXML) "
    "that contains one or more reaction arrows. "
    "Do not use for: hand-written CDXML text; use cdxml_path to an existing file."
)


class CdxmlToGraph_input_schema(input_schema):
    cdxml_path: str = Field(
        description="Absolute or workspace-relative path to an existing .cdxml file."
    )
    save_mol2: bool = Field(
        default=False,
        description=(
            "If true, write each parsed fragment/complex as a .mol2 file under "
            "the session's .cloudra/tool_output/cdxml_graph directory and return "
            "the paths. Default false (only SMILES/formula/charge/multiplicity)."
        ),
    )


class CdxmlToGraph_output_schema(output_schema):
    is_success: bool = Field(description="Whether parsing succeeded")
    graph: dict[str, Any] = Field(default_factory=dict, description="Parsed reaction graph")
    dag_proposal: dict[str, Any] | None = Field(
        default=None, description="Ready-to-use dag_propose_mechanism payload when graph is a DAG"
    )
    unresolved: list[dict[str, Any]] = Field(
        default_factory=list, description="Fragments/compounds that could not be converted to SMILES"
    )
    warnings: list[str] = Field(default_factory=list, description="Non-fatal parsing warnings")
    mol2_files: dict[str, str] = Field(
        default_factory=dict, description="Mol2 output paths when save_mol2=true"
    )
    message: str = Field(default="", description="Status or error message")


@dataclass
class _FragmentInfo:
    frag_id: str
    box: tuple[float, float, float, float]
    smiles: str | None
    formula: str
    charge: int
    multiplicity: int
    connectivity: list[list[Any]]
    mol2: str = ""


def _box(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    try:
        vals = [float(x) for x in value.split()]
        if len(vals) != 4:
            return None
        return (min(vals[0], vals[2]), min(vals[1], vals[3]), max(vals[0], vals[2]), max(vals[1], vals[3]))
    except Exception:
        return None


def _center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _contains_center(big: tuple[float, float, float, float], small: tuple[float, float, float, float]) -> bool:
    x, y = _center(small)
    return big[0] <= x <= big[2] and big[1] <= y <= big[3]


def _arrow_regions(arrow: Any) -> dict[str, tuple[float, float, float, float]]:
    """Return expanded boxes for tail/head/top/bottom around an arrow.

    方向由 Head3D→Tail3D 的支配轴决定：水平箭头按 x（尾在左/头在右，反之亦然）；
    垂直箭头（hx==tx）必须按 y 判定——指向上方时反应物在箭尾下方、产物在箭头
    上方。旧实现对垂直箭头一律落 else 分支把 head 钉在左侧，反应物/产物静默对调。
    """
    b = _box(arrow.get("BoundingBox"))
    if b is None:
        raise ValueError(f"arrow {arrow.get('id')} has no BoundingBox")
    head = arrow.get("Head3D", "").split()[:2]
    tail = arrow.get("Tail3D", "").split()[:2]
    try:
        hx = float(head[0])
        tx = float(tail[0])
        hy = float(head[1]) if len(head) > 1 else 0.0
        ty = float(tail[1]) if len(tail) > 1 else 0.0
    except Exception:
        hx, tx, hy, ty = b[2], b[0], 0.0, 0.0
    x0, y0, x1, y1 = b
    dx, dy = hx - tx, hy - ty

    if abs(dx) >= abs(dy):
        # 水平箭头：反应物侧=尾部，产物侧=头部
        if dx > 0:  # 头在右
            return {
                "tail": (x0 - 200, y0 - 60, x0, y1 + 60),
                "head": (x1, y0 - 60, x1 + 200, y1 + 60),
                "top": (x0, y1, x1, y1 + 80),
                "bottom": (x0, y0 - 80, x1, y0),
            }
        return {
            "tail": (x1, y0 - 60, x1 + 200, y1 + 60),
            "head": (x0 - 200, y0 - 60, x0, y1 + 60),
            "top": (x0, y1, x1, y1 + 80),
            "bottom": (x0, y0 - 80, x1, y0),
        }
    # 垂直箭头：头在上 → 反应物在下（箭尾）/ 产物在上（箭头）；试剂在左右
    if dy > 0:  # 指向上
        return {
            "tail": (x0 - 60, y0 - 200, x1 + 60, y0),
            "head": (x0 - 60, y1, x1 + 60, y1 + 200),
            "top": (x0 - 80, y0, x0, y1),
            "bottom": (x1, y0, x1 + 80, y1),
        }
    # 指向下
    return {
        "tail": (x0 - 60, y1, x1 + 60, y1 + 200),
        "head": (x0 - 60, y0 - 200, x1 + 60, y0),
        "top": (x0 - 80, y0, x0, y1),
        "bottom": (x1, y0, x1 + 80, y1),
    }


_COMMON_SOLVENTS = {
    "dmf", "dma", "dmso", "thf", "2-methf", "2-methylthf", "dcm", "ch2cl2",
    "dce", "chloroform", "chcl3", "ccl4", "meoh", "ethanol", "etoh", "iproh",
    "ipa", "tbuoh", "acetone", "mek", "mibk", "acetonitrile", "mecn", "etoac",
    "ethyl acetate", "toluene", "benzene", "xylene", "hexane", "hexanes",
    "heptane", "pentane", "cyclohexane", "water", "h2o", "pyridine", "et2o",
    "diethyl ether", "dioxane", "1,4-dioxane", "nmp", "hmpa", "solvent",
}

_CONDITION_PATTERNS = {
    "reaction_time": [
        (r"^\s*(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)\b", 3600.0),
        (r"^\s*(\d+(?:\.\d+)?)\s*(min|mins|minute|minutes)\b", 60.0),
        (r"^\s*overnight\b", 12 * 3600.0),
    ],
}


def _parse_condition_text(text: str) -> dict[str, Any]:
    """Best-effort structured condition extraction from a ChemDraw text box."""
    raw = " ".join(text.split())
    result: dict[str, Any] = {
        "raw_text": raw,
        "temperature": None,
        "reaction_time": None,
        "stir_speed": None,
        "pressure": None,
        "gas": None,
    }
    low = raw.lower()
    # Temperature
    if re.search(r"\brt\b", low):
        result["temperature"] = "rt"
    else:
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*(°?\s*c|°c|celsius)", low)
        if m:
            result["temperature"] = f"{m.group(1)} C"
    # Time
    m = re.search(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|min|mins|minute|minutes)\b", low)
    if m:
        unit = m.group(2).lower()
        result["reaction_time"] = (
            f"{float(m.group(1)) / 60:.6g} hr" if unit.startswith("min") else f"{m.group(1)} hr"
        )
    elif "overnight" in low:
        result["reaction_time"] = "overnight"
    # Stir speed
    m = re.search(r"(\d+)\s*(rpm|r\.?p\.?m\.?)", low)
    if m:
        result["stir_speed"] = f"{m.group(1)} RPM"
    # Pressure
    m = re.search(r"(\d+(?:\.\d+)?)\s*(bar|psi|mpa|atm)", low)
    if m:
        result["pressure"] = f"{m.group(1)} {m.group(2).upper()}"
    # Gas
    for gas in ("N2", "O2", "H2", "CO2", "Ar", "He"):
        if re.search(rf"\b{gas}\b", raw):
            result["gas"] = gas
    return result


def _fragment_to_info(cdxml_file: Any, frag: Any, *, save_mol2: bool, mol2_dir: str | None = None) -> _FragmentInfo:
    """Parse one top-level CDXML fragment via molli and serialize to RDKit SMILES."""
    frag_id = str(frag.get("id") or "")
    box = _box(frag.get("BoundingBox"))
    if box is None:
        raise ValueError(f"fragment {frag_id} has no BoundingBox")

    mol = cdxml_file._parse_fragment(frag, name=frag_id or "fragment")
    mol.add_implicit_hydrogens()

    connectivity: list[list[Any]] = []
    for bond in mol.bonds:
        connectivity.append([
            mol.index_atom(bond.a1),
            mol.index_atom(bond.a2),
            str(bond.btype.name),
        ])

    mol2_text = ""
    smiles: str | None = None
    if _RDKIT_AVAILABLE:
        try:
            mol2_text = mol.dumps_mol2()
            rdmol = Chem.MolFromMol2Block(mol2_text, removeHs=True)
            if rdmol is not None:
                smiles = Chem.MolToSmiles(rdmol)
        except Exception:
            smiles = None

    info = _FragmentInfo(
        frag_id=frag_id,
        box=box,
        smiles=smiles,
        formula=str(mol.formula),
        charge=int(mol.charge),
        multiplicity=int(mol.mult),
        connectivity=connectivity,
        mol2=mol2_text,
    )

    if save_mol2 and mol2_text and mol2_dir:
        os.makedirs(mol2_dir, exist_ok=True)
        out_path = os.path.join(mol2_dir, f"frag_{frag_id}.mol2")
        atomic_write_text(out_path, mol2_text)
        info.mol2 = out_path

    return info


def _text_value(t: Any) -> str:
    return "".join((s.text or "") for s in t.findall("s")).strip()


def _classify_text(raw: str, region: str, reactions: list[dict[str, Any]]):
    """Attach a text element to the current reaction's solvent/reagent/condition lists."""
    cond = _parse_condition_text(raw)
    low = raw.lower()
    has_condition = any(
        cond[k] is not None for k in ("temperature", "reaction_time", "stir_speed", "pressure", "gas")
    )
    solvent_words = [s for s in _COMMON_SOLVENTS if s in low]
    if solvent_words:
        reactions[-1]["solvents"].append(raw)
    if has_condition:
        reactions[-1]["conditions"].append(cond)
    if not solvent_words and not has_condition:
        reactions[-1]["reagents"].append(raw)


def _collect_reactions(cdxml_file: Any) -> tuple[list[dict[str, Any]], list[_FragmentInfo], list[str]]:
    """Build per-arrow reaction records from molli's tree and xfrags."""
    root = cdxml_file.tree.getroot()
    frag_infos: list[_FragmentInfo] = []
    warnings: list[str] = []

    # Use molli's already flattened top-level fragments (page/fragment + page/group/fragment).
    for frag in cdxml_file.xfrags:
        try:
            frag_infos.append(_fragment_to_info(cdxml_file, frag, save_mol2=False))
        except Exception as exc:
            warnings.append(f"fragment {frag.get('id')} skipped: {exc}")

    reactions: list[dict[str, Any]] = []
    for page in root.findall("page"):
        for arrow in page.findall(".//arrow"):
            try:
                regions = _arrow_regions(arrow)
            except Exception as exc:
                warnings.append(f"arrow {arrow.get('id')} skipped: {exc}")
                continue
            reaction: dict[str, Any] = {
                "arrow_id": str(arrow.get("id") or len(reactions) + 1),
                "reactants": [],
                "products": [],
                "reagents": [],
                "solvents": [],
                "conditions": [],
                "raw_texts": [],
            }
            reactions.append(reaction)
            for info in frag_infos:
                if info.box is None:
                    continue
                if _contains_center(regions["tail"], info.box):
                    reaction["reactants"].append(info)
                elif _contains_center(regions["head"], info.box):
                    reaction["products"].append(info)
                elif _contains_center(regions["top"], info.box) or _contains_center(regions["bottom"], info.box):
                    reaction["reagents"].append(info)

            # Text boxes near the arrow: conditions/solvents/reagents.
            for t in page.findall("t") + page.findall("group/t"):
                tbox = _box(t.get("BoundingBox"))
                if tbox is None:
                    continue
                raw = _text_value(t)
                if not raw:
                    continue
                if _contains_center(regions["top"], tbox) or _contains_center(regions["bottom"], tbox):
                    reaction["raw_texts"].append(raw)
                    _classify_text(raw, "top/bottom", reactions)

    return reactions, frag_infos, warnings


def _is_dag(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[bool, list[list[str]]]:
    """Simple Kahn topological check; returns (is_dag, cycle_node_lists)."""
    nid = {n["node_id"] for n in nodes}
    adj: dict[str, list[str]] = {i: [] for i in nid}
    indeg: dict[str, int] = {i: 0 for i in nid}
    for e in edges:
        if e["source_node_id"] in adj and e["target_node_id"] in adj:
            adj[e["source_node_id"]].append(e["target_node_id"])
            indeg[e["target_node_id"]] += 1
    queue = [i for i, d in indeg.items() if d == 0]
    order = []
    while queue:
        node = queue.pop()
        order.append(node)
        for nb in adj.get(node, []):
            indeg[nb] -= 1
            if indeg[nb] == 0:
                queue.append(nb)
    is_dag = len(order) == len(nid)
    cycles: list[list[str]] = []
    if not is_dag:
        # Report nodes that never got zero indegree as a coarse cycle set.
        cycles = [[i for i, d in indeg.items() if d > 0]]
    return is_dag, cycles


def _continuity_gaps(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report places where a product complex is not exactly the next source complex."""
    gaps: list[dict[str, Any]] = []
    for e in edges:
        target_components = set(e.get("metadata", {}).get("product_components", []))
        if not target_components:
            continue
        for other in edges:
            if other["edge_id"] == e["edge_id"]:
                continue
            source_components = set(other.get("metadata", {}).get("reactant_components", []))
            if source_components and target_components & source_components and other["source_node_id"] != e["target_node_id"]:
                gaps.append({
                    "from_edge": e["edge_id"],
                    "to_edge": other["edge_id"],
                    "shared_components": sorted(target_components & source_components),
                    "note": (
                        "the product complex is not exactly the next reactant complex; "
                        "add association/dissociation or intermediate occurrence(s) as needed"
                    ),
                })
    # Deduplicate (from/to unordered enough for a hint).
    seen = set()
    out = []
    for g in gaps:
        key = tuple(sorted((g["from_edge"], g["to_edge"])))
        if key not in seen:
            seen.add(key)
            out.append(g)
    return out


_DEFAULT_EDGE_STAGES = [
    "ts_guess",
    "ts_opt",
    "frequency",
    "short_irc",
    "endpoint_a",
    "endpoint_b",
    "direction",
    "identity",
]
_DEFAULT_NODE_STAGES = ["geometry"]


def _build_graph(
    reactions: list[dict[str, Any]],
    frag_infos: list[_FragmentInfo] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_by_complex: dict[str, str] = {}
    unresolved: list[dict[str, Any]] = []
    warnings: list[str] = []

    def _complex_id(role: str, idx: int) -> str:
        return f"cdx_arrow{idx + 1}_{role}"

    def _smiles_of_infos(infos: list[_FragmentInfo]) -> str | None:
        if not infos:
            return None
        parts = []
        for info in infos:
            if not info.smiles:
                return None
            parts.append(info.smiles)
        return ".".join(parts)

    def _component_tags(infos: list[_FragmentInfo]) -> list[str]:
        return [i.frag_id for i in infos]

    def _rdkit_complex_props(smiles: str) -> tuple[str, int, int]:
        if not _RDKIT_AVAILABLE:
            return "", 0, 1
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return "", 0, 1
            from rdkit.Chem import rdMolDescriptors
            formula = rdMolDescriptors.CalcMolFormula(mol)
            charge = Chem.GetFormalCharge(mol)
            mult = 1 + sum(a.GetNumRadicalElectrons() for a in mol.GetAtoms())
            return formula, charge, mult
        except Exception:
            return "", 0, 1

    def _add_complex_node(role: str, idx: int, infos: list[_FragmentInfo], components: list[str], smiles: str) -> str:
        nid = _complex_id(role, idx)
        formula, charge, mult = _rdkit_complex_props(smiles)
        nodes.append({
            "node_id": nid,
            "label": f"{role} complex {idx + 1}",
            "smiles": smiles,
            "role": role,
            "formula": formula,
            "charge": charge,
            "multiplicity": mult,
            "components": [
                {
                    "fragment_id": i.frag_id,
                    "smiles": i.smiles,
                    "formula": i.formula,
                    "charge": i.charge,
                    "multiplicity": i.multiplicity,
                }
                for i in infos
            ],
            "metadata": {
                "fragment_ids": [i.frag_id for i in infos],
                "component_smiles": [i.smiles for i in infos],
                "formula_components": [i.formula for i in infos],
            },
        })
        return nid

    for idx, reaction in enumerate(reactions):
        reactants = reaction.get("reactants", [])
        products = reaction.get("products", [])
        if not reactants or not products:
            warnings.append(
                f"arrow {reaction.get('arrow_id')} skipped: missing reactants or products "
                f"({len(reactants)} reactants, {len(products)} products)"
            )
            continue

        src_smiles = _smiles_of_infos(reactants)
        tgt_smiles = _smiles_of_infos(products)
        if src_smiles is None or tgt_smiles is None:
            for info in list(reactants) + list(products):
                if not info.smiles:
                    unresolved.append({
                        "fragment_id": info.frag_id,
                        "formula": info.formula,
                        "reason": "could not convert fragment to SMILES",
                    })
            warnings.append(f"arrow {reaction.get('arrow_id')} skipped: unresolved SMILES in reactants/products")
            continue

        src_id = node_by_complex.get(src_smiles) or _add_complex_node("reactant", idx, reactants, _component_tags(reactants), src_smiles)
        tgt_id = node_by_complex.get(tgt_smiles) or _add_complex_node("product", idx, products, _component_tags(products), tgt_smiles)
        node_by_complex[src_smiles] = src_id
        node_by_complex[tgt_smiles] = tgt_id

        edge_id = f"cdx_arrow{idx + 1}_step"
        edges.append({
            "edge_id": edge_id,
            "source_node_id": src_id,
            "target_node_id": tgt_id,
            "label": f"arrow_{reaction.get('arrow_id')}",
            "metadata": {
                "arrow_id": reaction.get("arrow_id"),
                "reactant_components": [i.smiles for i in reactants],
                "product_components": [i.smiles for i in products],
                "reagents": [i.smiles for i in reaction.get("reagents", []) if isinstance(i, _FragmentInfo) and i.smiles],
                "solvents": reaction.get("solvents", []),
                "conditions": reaction.get("conditions", []),
                "raw_texts": reaction.get("raw_texts", []),
            },
            "annotations": _edge_annotation(reaction),
        })

    # Infer occurrence roles globally: source-only=reactant, target-only=product,
    # both=intermediate (this matters for delivery DAG proposals).
    sources = {e["source_node_id"] for e in edges}
    targets = {e["target_node_id"] for e in edges}
    for node in nodes:
        if node["node_id"] in sources and node["node_id"] in targets:
            node["role"] = "intermediate"
        elif node["node_id"] in targets:
            node["role"] = "product"
        elif node["node_id"] in sources:
            node["role"] = "reactant"

    # If the CDXML contains structures but no arrows, still surface them as
    # unconnected reference nodes instead of returning an empty graph.
    if not edges and not nodes and frag_infos:
        for info in frag_infos:
            if not info.smiles:
                unresolved.append({
                    "fragment_id": info.frag_id,
                    "formula": info.formula,
                    "reason": "could not convert fragment to SMILES",
                })
                continue
            nid = f"cdx_frag_{info.frag_id}"
            nodes.append({
                "node_id": nid,
                "label": f"fragment {info.frag_id}",
                "smiles": info.smiles,
                "role": None,
                "formula": info.formula,
                "charge": info.charge,
                "multiplicity": info.multiplicity,
                "components": [{
                    "fragment_id": info.frag_id,
                    "smiles": info.smiles,
                    "formula": info.formula,
                    "charge": info.charge,
                    "multiplicity": info.multiplicity,
                }],
                "metadata": {
                    "fragment_ids": [info.frag_id],
                    "component_smiles": [info.smiles],
                    "formula_components": [info.formula],
                },
            })
        if nodes:
            warnings.append(
                "no reaction arrows found; returning standalone structure nodes "
                "as reference only, not a mechanism graph"
            )

    graph = {
        "nodes": nodes,
        "edges": edges,
        "is_dag": False,
        "cycles": [],
        "continuity_gaps": [],
    }

    is_dag, cycles = _is_dag(nodes, edges)
    graph["is_dag"] = is_dag
    graph["cycles"] = cycles
    graph["continuity_gaps"] = _continuity_gaps(edges)

    dag_proposal = None
    if is_dag and nodes and edges:
        dag_proposal = _make_dag_proposal(graph)

    return graph, dag_proposal, warnings, unresolved


def _edge_annotation(reaction: dict[str, Any]) -> str:
    bits = []
    if reaction.get("solvents") and not (
        len(reaction["solvents"]) == 1
        and reaction["solvents"][0].lower().startswith("solvent")
    ):
        bits.append("Solvent: " + "; ".join(reaction["solvents"]))
    for cond in reaction.get("conditions", []):
        fields = [f"{k}: {v}" for k, v in cond.items() if k != "raw_text" and v is not None]
        if fields:
            bits.append("; ".join(fields))
        if cond.get("raw_text"):
            bits.append(cond["raw_text"])
    if reaction.get("raw_texts") and not bits:
        bits.extend(reaction["raw_texts"])
    return " | ".join(bits)


def _make_dag_proposal(graph: dict[str, Any]) -> dict[str, Any]:
    operations = []
    stage_contracts = {}
    for node in graph["nodes"]:
        if not node.get("smiles"):
            continue
        operations.append({
            "op": "add_node",
            "graph": "delivery",
            "node": {
                "node_id": node["node_id"],
                "node_type": "occurrence",
                "label": node["label"],
                "role": node["role"],
                "smiles": node["smiles"],
                "metadata": node.get("metadata", {}),
            },
        })
        stage_contracts[node["node_id"]] = _DEFAULT_NODE_STAGES[:]
    for edge in graph["edges"]:
        if not edge["source_node_id"] or not edge["target_node_id"]:
            continue
        operations.append({
            "op": "add_edge",
            "graph": "delivery",
            "edge": {
                "edge_id": edge["edge_id"],
                "edge_type": "elementary_step",
                "source_node_id": edge["source_node_id"],
                "target_node_id": edge["target_node_id"],
                "label": edge.get("label", ""),
                "metadata": edge.get("metadata", {}),
                "annotations": edge.get("annotations", ""),
            },
        })
        stage_contracts[edge["edge_id"]] = _DEFAULT_EDGE_STAGES[:]
    rationale = (
        "Imported from CDXML reaction scheme. This is an unvalidated mechanism "
        "hypothesis: drawn arrows are not guaranteed to be elementary steps. "
        "Insert missing intermediates and split non-elementary arrows before "
        "accepting; transition states are represented by edge evidence stages, "
        "not as graph nodes."
    )
    return {
        "operations": operations,
        "stage_contracts": stage_contracts,
        "rationale": rationale,
    }


class CdxmlToGraph(Tool):
    tool_id: str = "t-51"
    tool_name: str = "cdxml_to_graph"
    tool_description: str = description
    input_schema: Any = CdxmlToGraph_input_schema
    output_schema: Any = CdxmlToGraph_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: CdxmlToGraph_input_schema, session: Session) -> CdxmlToGraph_output_schema:
        if not _MOLLI_AVAILABLE or not _RDKIT_AVAILABLE:
            return CdxmlToGraph_output_schema(
                is_success=False,
                message="molli and RDKit are required. Install with: pip install 'cloudra[chem]' (molli>=1.3.0).",
            )

        try:
            path = resolve_existing_tool_path(self, user_input.cdxml_path)
        except FileNotFoundError as exc:
            return CdxmlToGraph_output_schema(
                is_success=False,
                message=str(exc),
            )

        mol2_files: dict[str, str] = {}
        mol2_dir = None
        if user_input.save_mol2:
            base_dir = os.path.join(os.path.dirname(session.path) or ".", ".cloudra", "tool_output", "cdxml_graph")
            mol2_dir = base_dir
            os.makedirs(mol2_dir, exist_ok=True)

        try:
            cdxml_file = ml.CDXMLFile(path)
            # Reparse fragments with optional mol2 persistence (first pass was for layout).
            frag_map = {}
            for frag in cdxml_file.xfrags:
                try:
                    info = _fragment_to_info(
                        cdxml_file,
                        frag,
                        save_mol2=user_input.save_mol2,
                        mol2_dir=mol2_dir,
                    )
                    frag_map[str(frag.get("id"))] = info
                    if user_input.save_mol2 and info.mol2 and os.path.isfile(info.mol2):
                        mol2_files[str(frag.get("id"))] = info.mol2
                except Exception:
                    continue

            reactions, _, warnings = _collect_reactions(cdxml_file)
            # Replace layout infos with enriched infos from the same fragments so save_mol2 paths survive.
            for reaction in reactions:
                for key in ("reactants", "products", "reagents"):
                    reaction[key] = [
                        frag_map.get(i.frag_id, i)
                        if isinstance(i, _FragmentInfo) and i.frag_id in frag_map
                        else i
                        for i in reaction[key]
                    ]

            graph, dag_proposal, graph_warnings, unresolved = _build_graph(reactions, list(frag_map.values()))
            warnings.extend(graph_warnings)

            message = (
                f"Parsed {len(graph['nodes'])} complex nodes and {len(graph['edges'])} "
                f"candidate edges; graph is {'DAG' if graph['is_dag'] else 'not DAG'}."
            )
            if not graph["is_dag"]:
                message += " Returned as reference only; unroll cycles before DAG proposal."
            if warnings:
                message += " Warnings: " + "; ".join(warnings[:5])
            return CdxmlToGraph_output_schema(
                is_success=True,
                graph=graph,
                dag_proposal=dag_proposal,
                unresolved=unresolved,
                warnings=warnings,
                mol2_files=mol2_files,
                message=message,
            )
        except Exception as exc:
            return CdxmlToGraph_output_schema(
                is_success=False,
                message=f"CDXML parsing failed: {exc}",
            )


def get_class():
    return CdxmlToGraph
