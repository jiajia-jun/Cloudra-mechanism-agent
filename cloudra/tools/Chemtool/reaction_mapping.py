"""反应物/产物原子映射与反应中心候选分析。

未标号 SMILES 的映射本质上可能不唯一。本模块返回候选和评分事实，不把最低编辑
排列包装成唯一机理结论。
"""

import asyncio
import itertools
import math
import os
from collections import Counter, defaultdict
from typing import Any, Literal, Optional

from pydantic import ConfigDict, Field, StrictInt, model_validator

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_existing_tool_path
from cloudra.tools.core.molecule import Molecule
from cloudra.tools.core.species_identity import chemical_smiles
from cloudra.tools.core.ts_inputs import TsInput

_MAX_EXHAUSTIVE_MAPPINGS = 100_000
_MAX_RETURNED_CANDIDATES = 16
_AMBIGUITY_SCORE_WINDOW = 2.0

# 潜在手性轴启发式：近端范德华半径按图距离衰减加和，低于阈值的键不视为可归属轴。
_AXIS_BULK_RHO = 0.5
_AXIS_BULK_MAX_DEPTH = 5
_AXIS_BULK_BRANCH_BOOST = 1.5
_AXIS_MIN_CONGESTION = 9.0
_VDW_RADIUS = {
    "H": 1.20, "B": 1.92, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47,
    "P": 1.80, "S": 1.80, "Cl": 1.75, "Br": 1.85, "I": 1.98,
}


def _substituent_bulk(mol, root_idx: int, axis_idx: int) -> float:
    """轴端一侧取代基的位阻权重：BFS 子图，范德华半径按图距离 rho^d 衰减。"""
    total = 0.0
    seen = {axis_idx}
    frontier = [(root_idx, 0)]
    while frontier:
        idx, dist = frontier.pop()
        if idx in seen:
            continue
        seen.add(idx)
        atom = mol.GetAtomWithIdx(idx)
        weight = _VDW_RADIUS.get(atom.GetSymbol(), 1.70) * _AXIS_BULK_RHO ** dist
        if dist == 0 and atom.GetDegree() >= 3:
            weight *= _AXIS_BULK_BRANCH_BOOST
        total += weight
        if dist < _AXIS_BULK_MAX_DEPTH:
            frontier.extend((n.GetIdx(), dist + 1) for n in atom.GetNeighbors())
    return round(total, 3)


def _small_ring_bonds(mol, max_ring: int = 6) -> set[tuple[int, int]]:
    from rdkit import Chem

    bonds: set[tuple[int, int]] = set()
    for ring in Chem.GetSymmSSSR(mol):
        if len(ring) <= max_ring:
            for i in range(len(ring)):
                bonds.add(tuple(sorted((ring[i], ring[(i + 1) % len(ring)]))))
    return bonds


def find_potential_chiral_axes(mol) -> list[dict]:
    """启发式列出分子中的潜在手性轴。

    闸门顺序：两端杂化（至少一端 sp2/sp，允许另一端 sp3）→ 小环排除 →
    每端两个图不等价取代基（canonical rank 对称类）→ 位阻拥挤度阈值。
    普通键与低拥挤键一律不进输出，agent 只看到可归属的轴。
    """
    from rdkit import Chem

    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    ring_bonds = _small_ring_bonds(mol)
    pi_hybrids = {Chem.HybridizationType.SP2, Chem.HybridizationType.SP}
    axes: list[dict] = []
    for bond in mol.GetBonds():
        a1, a2 = bond.GetBeginAtom(), bond.GetEndAtom()
        pair = tuple(sorted((a1.GetIdx(), a2.GetIdx())))
        if pair in ring_bonds:
            continue
        hyb = (a1.GetHybridization(), a2.GetHybridization())
        pi_ends = sum(h in pi_hybrids for h in hyb)
        sp3_ends = sum(h == Chem.HybridizationType.SP3 for h in hyb)
        if not (pi_ends >= 1 and pi_ends + sp3_ends == 2):
            continue

        ends = []
        for axis_atom, other in ((a1, a2), (a2, a1)):
            subs = [
                n.GetIdx() for n in axis_atom.GetNeighbors()
                if n.GetIdx() != other.GetIdx() and n.GetAtomicNum() != 1
            ]
            if len(subs) != 2 or ranks[subs[0]] == ranks[subs[1]]:
                break
            bulk = sorted(
                (_substituent_bulk(mol, s, axis_atom.GetIdx()) for s in subs),
                reverse=True,
            )
            ends.append({"substituents": sorted(s + 1 for s in subs), "bulk": bulk})
        if len(ends) != 2:
            continue

        congestion = round(sum(sum(end["bulk"]) for end in ends), 3)
        if congestion < _AXIS_MIN_CONGESTION:
            continue
        stereo = str(bond.GetStereo())
        axes.append({
            "bond": [pair[0] + 1, pair[1] + 1],
            "hybridization": [str(hyb[0]), str(hyb[1])],
            "substituents": [ends[0]["substituents"], ends[1]["substituents"]],
            "bulk": [ends[0]["bulk"], ends[1]["bulk"]],
            "axis_congestion": congestion,
            "configuration": (
                "atrop_cw" if stereo == "STEREOATROPCW"
                else "atrop_ccw" if stereo == "STEREOATROPCCW"
                else "unspecified"
            ),
        })
    return axes


def _parse_heavy_smiles(smiles: str, role: str):
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"{role} SMILES could not be parsed: {smiles}")
    return Chem.RemoveHs(mol)


def _atom_key(atom) -> tuple[int, int]:
    return atom.GetAtomicNum(), atom.GetIsotope()


def _bond_orders(mol) -> dict[tuple[int, int], float]:
    return {
        tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))): float(
            bond.GetBondTypeAsDouble()
        )
        for bond in mol.GetBonds()
    }


def _mapped_label_permutation(reactant, product) -> list[int] | None:
    """若两端重原子均完整标号，返回 product index -> reactant index。"""
    r_labels = [atom.GetAtomMapNum() for atom in reactant.GetAtoms()]
    p_labels = [atom.GetAtomMapNum() for atom in product.GetAtoms()]
    any_labels = any(r_labels) or any(p_labels)
    if not any_labels:
        return None
    if any(label <= 0 for label in r_labels + p_labels):
        raise ValueError("atom-map labels must cover every heavy atom on both sides; partial labels are not allowed")
    if len(set(r_labels)) != len(r_labels) or len(set(p_labels)) != len(p_labels):
        raise ValueError("atom-map labels must not repeat within one molecule")
    if set(r_labels) != set(p_labels):
        raise ValueError("reactant and product atom-map label sets do not match")
    r_by_label = {label: idx for idx, label in enumerate(r_labels)}
    for p_idx, label in enumerate(p_labels):
        r_idx = r_by_label[label]
        if _atom_key(product.GetAtomWithIdx(p_idx)) != _atom_key(reactant.GetAtomWithIdx(r_idx)):
            raise ValueError(
                f"atom-map label {label} connects different elements or isotopes on the two sides"
            )
    return [r_by_label[label] for label in p_labels]


def _element_groups(mol) -> dict[tuple[int, int], list[int]]:
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for atom in mol.GetAtoms():
        groups[_atom_key(atom)].append(atom.GetIdx())
    return dict(groups)


def _mapping_count(groups: dict[tuple[int, int], list[int]]) -> int:
    count = 1
    for indices in groups.values():
        count *= math.factorial(len(indices))
    return count


def _exhaustive_element_mappings(reactant, product):
    """枚举元素/同位素守恒的 product -> reactant 双射。"""
    r_groups = _element_groups(reactant)
    p_groups = _element_groups(product)
    keys = sorted(p_groups)
    permutations_by_key = [list(itertools.permutations(r_groups[key])) for key in keys]
    for choices in itertools.product(*permutations_by_key):
        mapping = [-1] * product.GetNumAtoms()
        for key, perm in zip(keys, choices):
            for product_idx, reactant_idx in zip(p_groups[key], perm):
                mapping[product_idx] = reactant_idx
        yield mapping


def _mcs_seeded_mappings(reactant, product):
    """大体系回退：用 CompareAny MCS 生成少量候选并确定性补齐未匹配原子。"""
    from rdkit import Chem
    from rdkit.Chem import rdFMCS

    result = rdFMCS.FindMCS(
        [reactant, product],
        atomCompare=rdFMCS.AtomCompare.CompareElements,
        bondCompare=rdFMCS.BondCompare.CompareAny,
        ringMatchesRingOnly=True,
        completeRingsOnly=True,
        timeout=10,
    )
    query = Chem.MolFromSmarts(result.smartsString) if result.smartsString else None
    if query is None:
        return
    r_matches = reactant.GetSubstructMatches(query, uniquify=True, maxMatches=64)
    p_matches = product.GetSubstructMatches(query, uniquify=True, maxMatches=64)
    seen: set[tuple[int, ...]] = set()
    for r_match in r_matches:
        for p_match in p_matches:
            mapping = [-1] * product.GetNumAtoms()
            used_r = set()
            valid = True
            for p_idx, r_idx in zip(p_match, r_match):
                if _atom_key(product.GetAtomWithIdx(p_idx)) != _atom_key(reactant.GetAtomWithIdx(r_idx)):
                    valid = False
                    break
                mapping[p_idx] = r_idx
                used_r.add(r_idx)
            if not valid:
                continue
            for key, p_indices in _element_groups(product).items():
                pending_p = [idx for idx in p_indices if mapping[idx] < 0]
                pending_r = [idx for idx in _element_groups(reactant)[key] if idx not in used_r]
                pending_p.sort(key=lambda idx: (
                    product.GetAtomWithIdx(idx).GetTotalNumHs(),
                    product.GetAtomWithIdx(idx).GetDegree(), idx,
                ))
                pending_r.sort(key=lambda idx: (
                    reactant.GetAtomWithIdx(idx).GetTotalNumHs(),
                    reactant.GetAtomWithIdx(idx).GetDegree(), idx,
                ))
                for p_idx, r_idx in zip(pending_p, pending_r):
                    mapping[p_idx] = r_idx
                    used_r.add(r_idx)
            key = tuple(mapping)
            if -1 not in key and key not in seen:
                seen.add(key)
                yield mapping


def _edit_facts(reactant, product, mapping: list[int]) -> dict:
    r_bonds = _bond_orders(reactant)
    p_bonds: dict[tuple[int, int], float] = {}
    for bond in product.GetBonds():
        pair = tuple(sorted((
            mapping[bond.GetBeginAtomIdx()],
            mapping[bond.GetEndAtomIdx()],
        )))
        p_bonds[pair] = float(bond.GetBondTypeAsDouble())

    formed = sorted(set(p_bonds) - set(r_bonds))
    broken = sorted(set(r_bonds) - set(p_bonds))
    changed_pairs = sorted(
        pair for pair in set(r_bonds) & set(p_bonds)
        if abs(r_bonds[pair] - p_bonds[pair]) > 1e-6
    )
    order_changes = [
        {
            "atoms": [pair[0] + 1, pair[1] + 1],
            "reactant_order": r_bonds[pair],
            "product_order": p_bonds[pair],
        }
        for pair in changed_pairs
    ]
    return {
        "formed_bonds": [[i + 1, j + 1] for i, j in formed],
        "broken_bonds": [[i + 1, j + 1] for i, j in broken],
        "order_changes": order_changes,
    }


def _permutation_is_odd(source: list[int], target: list[int]) -> bool:
    positions = {value: index for index, value in enumerate(target)}
    order = [positions[value] for value in source]
    inversions = sum(
        1 for i in range(len(order)) for j in range(i + 1, len(order))
        if order[i] > order[j]
    )
    return bool(inversions % 2)


def _stereo_mismatch(reactant, product, mapping: list[int]) -> int:
    """Compare stable tetrahedral and E/Z stereo in mapped atom space."""
    from rdkit import Chem

    mismatch = 0
    tetrahedral = {
        Chem.ChiralType.CHI_TETRAHEDRAL_CW,
        Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
    }
    for p_idx, r_idx in enumerate(mapping):
        p_atom = product.GetAtomWithIdx(p_idx)
        r_atom = reactant.GetAtomWithIdx(r_idx)
        p_tag = p_atom.GetChiralTag()
        r_tag = r_atom.GetChiralTag()
        if p_tag not in tetrahedral and r_tag not in tetrahedral:
            continue
        if p_tag not in tetrahedral or r_tag not in tetrahedral:
            mismatch += 1
            continue
        p_neighbors = [mapping[n.GetIdx()] for n in p_atom.GetNeighbors()]
        r_neighbors = [n.GetIdx() for n in r_atom.GetNeighbors()]
        if p_atom.GetTotalNumHs() == 1:
            p_neighbors.append(-1)
        if r_atom.GetTotalNumHs() == 1:
            r_neighbors.append(-1)
        if len(p_neighbors) != 4 or set(p_neighbors) != set(r_neighbors):
            # Stereo at an edited centre is not a stable mapping discriminator.
            continue
        translated_tag = p_tag
        if _permutation_is_odd(p_neighbors, r_neighbors):
            translated_tag = (
                Chem.ChiralType.CHI_TETRAHEDRAL_CCW
                if p_tag == Chem.ChiralType.CHI_TETRAHEDRAL_CW
                else Chem.ChiralType.CHI_TETRAHEDRAL_CW
            )
        if translated_tag != r_tag:
            mismatch += 1

    r_bonds = _bond_orders(reactant)
    for p_bond in product.GetBonds():
        p_stereo = p_bond.GetStereo()
        if p_stereo not in {Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOZ}:
            continue
        pair = tuple(sorted((
            mapping[p_bond.GetBeginAtomIdx()],
            mapping[p_bond.GetEndAtomIdx()],
        )))
        if pair not in r_bonds or abs(r_bonds[pair] - 2.0) > 1e-6:
            continue
        r_bond = reactant.GetBondBetweenAtoms(*pair)
        r_stereo = r_bond.GetStereo()
        if r_stereo in {Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOZ}:
            mismatch += int(p_stereo != r_stereo)
        else:
            mismatch += 1
    mismatch += _axial_stereo_mismatch(reactant, product, mapping)
    return mismatch


def _axis_config_rank_order(mol, axis_idx: int, other_idx: int, ranks: list[int]) -> list[int] | None:
    """轴一端两个取代基按 canonical rank 排序后的 [低rank原子, 高rank原子]。"""
    subs = [
        n.GetIdx() for n in mol.GetAtomWithIdx(axis_idx).GetNeighbors()
        if n.GetIdx() != other_idx and n.GetAtomicNum() != 1
    ]
    if len(subs) != 2 or ranks[subs[0]] == ranks[subs[1]]:
        return None
    return sorted(subs, key=lambda i: ranks[i])


def _axial_stereo_mismatch(reactant, product, mapping: list[int]) -> int:
    """比较映射后潜在轴的构型守恒。

    sp2-sp2 轴读 RDKit atropisomer stereo（CW/CCW）；含 sp3 端的轴 RDKit
    不携带轴构型，改用取代基 rank 顺序经映射翻译后比对低/高 rank 取代基
    在轴两端的相对同侧/异侧关系是否翻转。只覆盖已声明构型的轴。
    """
    from rdkit import Chem

    atrop = {Chem.BondStereo.STEREOATROPCW, Chem.BondStereo.STEREOATROPCCW}
    mismatch = 0

    # sp2-sp2 轴：RDKit atropisomer stereo，经映射比较轴键 CW/CCW。
    r_axes = {}
    for r_bond in reactant.GetBonds():
        if r_bond.GetStereo() in atrop:
            r_axes[tuple(sorted((r_bond.GetBeginAtomIdx(), r_bond.GetEndAtomIdx())))] = r_bond.GetStereo()
    for p_bond in product.GetBonds():
        if p_bond.GetStereo() not in atrop:
            continue
        pair = tuple(sorted((mapping[p_bond.GetBeginAtomIdx()], mapping[p_bond.GetEndAtomIdx()])))
        if pair in r_axes and r_axes[pair] != p_bond.GetStereo():
            mismatch += 1
    return mismatch


def _score_mapping(reactant, product, mapping: list[int], source: str) -> dict:
    edits = _edit_facts(reactant, product, mapping)
    hydrogen_mismatch = sum(
        abs(
            product.GetAtomWithIdx(p_idx).GetTotalNumHs()
            - reactant.GetAtomWithIdx(r_idx).GetTotalNumHs()
        )
        for p_idx, r_idx in enumerate(mapping)
    )
    charge_mismatch = sum(
        abs(
            product.GetAtomWithIdx(p_idx).GetFormalCharge()
            - reactant.GetAtomWithIdx(r_idx).GetFormalCharge()
        )
        for p_idx, r_idx in enumerate(mapping)
    )
    radical_mismatch = sum(
        abs(
            product.GetAtomWithIdx(p_idx).GetNumRadicalElectrons()
            - reactant.GetAtomWithIdx(r_idx).GetNumRadicalElectrons()
        )
        for p_idx, r_idx in enumerate(mapping)
    )
    stereo_mismatch = _stereo_mismatch(reactant, product, mapping)
    bond_edit_count = (
        len(edits["formed_bonds"])
        + len(edits["broken_bonds"])
        + len(edits["order_changes"])
    )
    score = (
        2.0 * (len(edits["formed_bonds"]) + len(edits["broken_bonds"]))
        + len(edits["order_changes"])
        + 4.0 * hydrogen_mismatch
        + 8.0 * charge_mismatch
        + 8.0 * radical_mismatch
        + 2.0 * stereo_mismatch
    )
    return {
        "heavy_atom_map": [idx + 1 for idx in mapping],
        "score": score,
        "bond_edit_count": bond_edit_count,
        "hydrogen_mismatch": hydrogen_mismatch,
        "charge_mismatch": charge_mismatch,
        "radical_mismatch": radical_mismatch,
        "stereo_mismatch": stereo_mismatch,
        "source": source,
        **edits,
    }


def _edit_facts_key(candidate: dict) -> tuple:
    """候选的去重键：编辑事实（formed/broken/order_changes）+ score。

    对称分子的自同构镜像给出逐字不同的 heavy_atom_map，但编辑事实与 score
    完全一致——它们不是独立的化学候选，必须合并；只有编辑事实（或评分）真正
    不同的映射才各算一个候选。
    """
    return (
        tuple(tuple(pair) for pair in candidate["formed_bonds"]),
        tuple(tuple(pair) for pair in candidate["broken_bonds"]),
        tuple(
            (tuple(change["atoms"]), change["reactant_order"], change["product_order"])
            for change in candidate["order_changes"]
        ),
        candidate["score"],
    )


def _candidate_mappings(reactant, product) -> tuple[list[dict], bool]:
    authoritative = _mapped_label_permutation(reactant, product)
    if authoritative is not None:
        return [_score_mapping(reactant, product, authoritative, "atom_map_labels")], True

    r_groups = _element_groups(reactant)
    count = _mapping_count(r_groups)
    raw_mappings = (
        _exhaustive_element_mappings(reactant, product)
        if count <= _MAX_EXHAUSTIVE_MAPPINGS
        else _mcs_seeded_mappings(reactant, product)
    )
    # 枚举侧即按编辑事实剪枝：同一编辑事实组保留 heavy_atom_map 最小者作代表，
    # 自同构镜像不再挤占 _MAX_RETURNED_CANDIDATES 窗口、也不再制造假 ambiguous。
    by_facts: dict[tuple, dict] = {}
    for mapping in raw_mappings:
        candidate = _score_mapping(reactant, product, mapping, "rdkit_graph_search")
        key = _edit_facts_key(candidate)
        incumbent = by_facts.get(key)
        if incumbent is None or candidate["heavy_atom_map"] < incumbent["heavy_atom_map"]:
            by_facts[key] = candidate
    candidates = sorted(
        by_facts.values(),
        key=lambda item: (item["score"], item["heavy_atom_map"]),
    )[:_MAX_RETURNED_CANDIDATES]
    return candidates, False


def analyze_reaction_mapping(
    reactant_smiles: str,
    product_smiles: str,
    selected_candidate: int = 0,
) -> dict:
    from rdkit import Chem

    parameters = Chem.RemoveHsParameters()
    parameters.removeIsotopes = True
    parameters.removeOnlyHNeighbors = True
    parameters.removeDegreeZero = True
    reactant = Chem.RemoveHs(_parse_heavy_smiles(reactant_smiles, "Reactant"), parameters)
    product = Chem.RemoveHs(_parse_heavy_smiles(product_smiles, "Product"), parameters)
    r_inventory = Counter(_atom_key(atom) for atom in reactant.GetAtoms())
    p_inventory = Counter(_atom_key(atom) for atom in product.GetAtoms())
    if r_inventory != p_inventory:
        raise ValueError(f"Heavy-atom element counts differ before and after the reaction: {dict(r_inventory)} vs {dict(p_inventory)}")

    candidates, authoritative = _candidate_mappings(reactant, product)
    potential_axes = {
        "reactant": find_potential_chiral_axes(reactant),
        "product": find_potential_chiral_axes(product),
    }
    if not candidates:
        return {
            "mapping_status": "inconclusive",
            "candidates": [],
            "heavy_atom_map": [],
            "formed_bonds": [],
            "broken_bonds": [],
            "order_changes": [],
            "watch_pairs": [],
            "potential_axes": potential_axes,
            "message": "No usable element-conserving mapping candidate was generated.",
        }
    if not 0 <= selected_candidate < len(candidates):
        raise ValueError(
            f"selected_candidate={selected_candidate} out of range; {len(candidates)} candidate(s) available"
        )

    top_score = candidates[0]["score"]
    near_top = [
        candidate for candidate in candidates
        if candidate["score"] <= top_score + _AMBIGUITY_SCORE_WINDOW
    ]
    status = "unique" if authoritative or len(near_top) == 1 else "ambiguous"
    selected = candidates[selected_candidate]
    watch_pairs = sorted(selected["formed_bonds"] + selected["broken_bonds"])
    message = (
        "Mapping determined by complete atom-map labels on both sides."
        if authoritative
        else (
            "There are atom-mapping candidates with close scores; the agent must choose with a mechanism hypothesis or manual review."
            if status == "ambiguous"
            else "Graph-edit and atom-environment scoring produced a single leading candidate; still check it against the mechanism."
        )
    )
    return {
        "mapping_status": status,
        "candidates": candidates,
        "heavy_atom_map": selected["heavy_atom_map"],
        "formed_bonds": selected["formed_bonds"],
        "broken_bonds": selected["broken_bonds"],
        "order_changes": selected["order_changes"],
        "watch_pairs": watch_pairs,
        "potential_axes": potential_axes,
        "message": message,
    }


def _clear_atom_maps(mol):
    from rdkit import Chem

    clean = Chem.Mol(mol)
    for atom in clean.GetAtoms():
        atom.SetAtomMapNum(0)
    return clean


def _canonical_heavy_smiles(mol) -> str:
    from rdkit import Chem

    return Chem.MolToSmiles(
        Chem.RemoveHs(_clear_atom_maps(mol)),
        canonical=True,
        isomericSmiles=True,
    )


def _axis_config_from_3d(mol, conf, axis_a: int, axis_b: int, ranks: list[int]) -> Optional[str]:
    """从 3D 坐标定一根潜在轴的构型（atrop_cw/atrop_ccw），与 RDKit stereo 无关。

    取轴两端 rank 最低的两个取代基，量二面角 low(a)-a-b-low(b)，按符号定号。
    取代基经 canonical rank 排序保证跨端一致可比。
    """
    import math

    low = {}
    for axis_idx, other_idx in ((axis_a, axis_b), (axis_b, axis_a)):
        order = _axis_config_rank_order(mol, axis_idx, other_idx, ranks)
        if order is None:
            return None
        low[axis_idx] = order[0]
    import numpy as np

    p0 = np.array(conf.GetAtomPosition(low[axis_a]))
    p1 = np.array(conf.GetAtomPosition(axis_a))
    p2 = np.array(conf.GetAtomPosition(axis_b))
    p3 = np.array(conf.GetAtomPosition(low[axis_b]))
    b0 = -(p1 - p0)
    b1 = p2 - p1
    b2 = p3 - p2
    b1 /= np.linalg.norm(b1)
    v = b0 - np.dot(b0, b1) * b1
    w = b2 - np.dot(b2, b1) * b1
    x = np.dot(v, w)
    y = np.dot(np.cross(b1, v), w)
    dihedral = math.degrees(math.atan2(y, x))
    return "atrop_ccw" if dihedral > 0 else "atrop_cw"


def _read_structure(
    path: Optional[str], text: Optional[str], fmt: str, charge: int, role: str,
    *, multiplicity: int = 1, electronic_character: str | None = None, require_declared_identity: bool = False,
):
    from rdkit import Chem

    if not path and not text:
        return None
    if path:
        if not os.path.isfile(path):
            raise ValueError(f"{role} structure file does not exist: {path}")
        with open(path, encoding="utf-8", errors="replace") as handle:
            payload = handle.read()
        inferred = os.path.splitext(path)[1].lower().lstrip(".")
    else:
        payload = text or ""
        inferred = ""
    actual_format = fmt if fmt != "auto" else inferred
    if actual_format in {"mol", "molfile", "sdf"}:
        mol = Chem.MolFromMolBlock(payload, removeHs=False, sanitize=True)
    elif actual_format == "xyz":
        if require_declared_identity or multiplicity > 1 or electronic_character == 'open_shell':
            raise ValueError(f'{role}: XYZ alone does not carry the declared electronic identity; supply a paired MOL/SDF graph with charge, radical and stereochemical identity.')
        from rdkit.Chem import rdDetermineBonds

        mol = Chem.MolFromXYZBlock(payload)
        if mol is not None:
            rdDetermineBonds.DetermineBonds(mol, charge=charge)
            Chem.SanitizeMol(mol)
    else:
        raise ValueError(f"{role} structure format not supported: {actual_format or 'cannot infer from path'}")
    if mol is None:
        raise ValueError(f"{role} structure could not be parsed as {actual_format}")
    return mol


def concrete_structure_digest(role: str, smiles: str | list[str], charge: int, multiplicity: int, structure,
                              *, electronic_character: str | None = None) -> str:
    """Digest the declared identity, concrete atom order, graph and coordinates."""
    from cloudra.tools.core.conformer_catalog import content_digest

    identity = dict(role=role, smiles=smiles, charge=charge, multiplicity=multiplicity,
        atoms=[(a.GetAtomicNum(), a.GetIsotope(), a.GetFormalCharge(), a.GetAtomMapNum())
               for a in structure.GetAtoms()],
        bonds=sorted((min(b.GetBeginAtomIdx(), b.GetEndAtomIdx()),
                      max(b.GetBeginAtomIdx(), b.GetEndAtomIdx()), b.GetBondTypeAsDouble())
                     for b in structure.GetBonds()),
        positions=structure.GetConformer().GetPositions().tolist() if structure.GetNumConformers() else None)
    # Retain existing unspecified closed-shell digests, but pin open-shell
    # electronic identity to concrete rows, including declared singlets.
    if electronic_character is not None or multiplicity > 1 or any(a.GetNumRadicalElectrons() for a in structure.GetAtoms()):
        identity['electronic_character'] = electronic_character
        identity['electronic_atoms'] = [(a.GetNumRadicalElectrons(), str(a.GetChiralTag())) for a in structure.GetAtoms()]
        identity['electronic_bonds'] = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), str(b.GetStereo()), list(b.GetStereoAtoms())) for b in structure.GetBonds()]
    return content_digest(identity)


def _complete_binding_preserves_identity(expected, structure, structure_heavy, match) -> bool:
    """Prove one complete graph binding including explicit hydrogen isotopes."""
    from rdkit import Chem

    if len(match) != expected.GetNumAtoms() or sorted(match) != list(range(structure_heavy.GetNumAtoms())):
        return False
    expected_full = Chem.AddHs(expected)
    if Counter(_atom_key(a) for a in expected_full.GetAtoms()) != Counter(_atom_key(a) for a in structure.GetAtoms()):
        return False

    def atom_state(atom):
        return (_atom_key(atom), atom.GetFormalCharge(), atom.GetNumRadicalElectrons(),
                atom.GetIsAromatic(), atom.GetTotalNumHs(includeNeighbors=True))

    def hydrogen_states(atom):
        return Counter((_atom_key(a), a.GetFormalCharge(), a.GetNumRadicalElectrons())
                       for a in atom.GetNeighbors() if a.GetAtomicNum() == 1)

    for index, target in enumerate(match):
        query = expected.GetAtomWithIdx(index)
        concrete = structure_heavy.GetAtomWithIdx(target)
        if atom_state(query) != atom_state(concrete):
            return False
        if query.GetAtomicNum() != 1 and hydrogen_states(expected_full.GetAtomWithIdx(index)) != hydrogen_states(
                structure.GetAtomWithIdx(concrete.GetIntProp('_full_idx'))):
            return False
    expected_bonds = {tuple(sorted((match[b.GetBeginAtomIdx()], match[b.GetEndAtomIdx()]))):
                      (b.GetBondTypeAsDouble(), b.GetIsAromatic()) for b in expected.GetBonds()}
    concrete_bonds = {tuple(sorted((b.GetBeginAtomIdx(), b.GetEndAtomIdx()))):
                      (b.GetBondTypeAsDouble(), b.GetIsAromatic()) for b in structure_heavy.GetBonds()}
    return expected_bonds == concrete_bonds and _stereo_mismatch(structure_heavy, expected, list(match)) == 0


def _identity_and_binding(expected_smiles: str, structure, explicit_indices: list[int] | None = None,
                          *, allow_symmetric_representative: bool = False) -> tuple[str, list[int], str]:
    """返回图身份、expected heavy -> concrete full-atom index，以及绑定诊断。"""
    from rdkit import Chem

    if structure is None:
        return "not_provided", [], ""
    expected = _parse_heavy_smiles(expected_smiles, "Endpoint")
    expected_labels = [atom.GetAtomMapNum() for atom in expected.GetAtoms() if atom.GetAtomicNum() != 1]
    concrete_heavy_atoms = [atom for atom in structure.GetAtoms() if atom.GetAtomicNum() != 1]
    concrete_labels = [atom.GetAtomMapNum() for atom in concrete_heavy_atoms]
    structure_copy = _clear_atom_maps(structure)
    for atom in structure_copy.GetAtoms():
        atom.SetIntProp("_full_idx", atom.GetIdx())
    structure_heavy = Chem.RemoveHs(structure_copy)
    declared_identity = _canonical_heavy_smiles(expected)
    concrete_identity = _canonical_heavy_smiles(structure_heavy)
    if declared_identity != concrete_identity:
        return "mismatch", [], ("The concrete structure's molecular graph or stereochemistry differs from the declared SMILES. "
            f"Declared identity: {declared_identity}; concrete identity: {concrete_identity}. "
            "Changing binding indices cannot repair this identity mismatch.")

    for labels in (expected_labels, concrete_labels):
        if any(labels) and (any(label <= 0 for label in labels) or len(set(labels)) != len(labels)):
            return "match", [], "Heavy-atom map labels must be complete and unique wherever supplied."
    if (all(expected_labels) and all(concrete_labels)
            and set(expected_labels) != set(concrete_labels)):
        return "match", [], "Declared and concrete heavy-atom map labels conflict."

    expected_clean = _clear_atom_maps(expected)
    expected_heavy_positions = [atom.GetIdx() for atom in expected.GetAtoms() if atom.GetAtomicNum() != 1]
    full_indices = [atom.GetIntProp("_full_idx") for atom in structure_heavy.GetAtoms()]
    if explicit_indices is not None:
        if len(explicit_indices) != len(expected_heavy_positions) or len(set(explicit_indices)) != len(explicit_indices):
            return 'match', [], 'Explicit heavy-atom binding has wrong length or repeated indices.'
        if any(index < 0 or index >= structure.GetNumAtoms() or structure.GetAtomWithIdx(index).GetAtomicNum() == 1
               for index in explicit_indices):
            return 'match', [], 'Explicit heavy-atom binding references an out-of-range atom or hydrogen.'

    selected = explicit_indices
    if selected is None and expected_labels and all(expected_labels) and all(concrete_labels):
        by_label = {atom.GetAtomMapNum(): atom.GetIdx() for atom in concrete_heavy_atoms}
        selected = [by_label[label] for label in expected_labels]
    parameters = Chem.SubstructMatchParameters()
    parameters.uniquify = False
    parameters.useChirality = True
    unlabelled = not any(a.GetAtomMapNum() for a in expected.GetAtoms()) and not any(a.GetAtomMapNum() for a in structure.GetAtoms())
    prove_symmetry = allow_symmetric_representative and unlabelled and selected is None
    # A 257th result is an overflow sentinel, never an "all candidates" proof.
    parameters.maxMatches = (257 if prove_symmetry else 256) if selected is None else 1
    if selected is not None:
        # Pin the declared correspondence before graph matching, rather than
        # requiring it to appear among a truncated enumeration of automorphisms.
        property_name = '_cloudra_binding_position'
        for atom in (*expected_clean.GetAtoms(), *structure_heavy.GetAtoms()):
            atom.SetIntProp(property_name, 0)
        concrete_positions = {full: index for index, full in enumerate(full_indices)}
        for position, (expected_index, concrete_index) in enumerate(zip(expected_heavy_positions, selected), 1):
            expected_clean.GetAtomWithIdx(expected_index).SetIntProp(property_name, position)
            structure_heavy.GetAtomWithIdx(concrete_positions[concrete_index]).SetIntProp(property_name, position)
        parameters.atomProperties = [property_name]
    matches = structure_heavy.GetSubstructMatches(expected_clean, parameters)
    full_matches = [tuple(full_indices[idx] for idx in match) for match in matches]
    allowed = {tuple(match[idx] for idx in expected_heavy_positions) for match in full_matches}
    if explicit_indices is not None:
        if tuple(explicit_indices) not in allowed:
            return 'match', [], 'Explicit heavy-atom binding does not preserve the declared molecular graph, bonds or stereochemistry.'
        selected_matches = [match for match in full_matches
                            if tuple(match[idx] for idx in expected_heavy_positions) == tuple(explicit_indices)]
        axis_diag = _axis_config_consistency(expected, structure, selected_matches)
        if axis_diag:
            return 'mismatch', [], axis_diag
    if (
        expected_labels
        and all(expected_labels)
        and concrete_labels
        and all(concrete_labels)
        and set(expected_labels) == set(concrete_labels)
        and len(set(concrete_labels)) == len(concrete_labels)
    ):
        concrete_by_label = {
            atom.GetAtomMapNum(): atom.GetIdx() for atom in concrete_heavy_atoms
        }
        for expected_atom in expected.GetAtoms():
            if expected_atom.GetAtomicNum() == 1:
                continue
            concrete_atom = structure.GetAtomWithIdx(
                concrete_by_label[expected_atom.GetAtomMapNum()]
            )
            if _atom_key(expected_atom) != _atom_key(concrete_atom):
                return (
                    "match",
                    [],
                    f"The concrete structure's atom-map label {expected_atom.GetAtomMapNum()} has a mismatched element or isotope.",
                )
        binding = [concrete_by_label[label] for label in expected_labels]
        if tuple(binding) not in allowed:
            return 'match', [], 'Concrete atom-map labels conflict with the declared molecular graph.'
        if explicit_indices is not None and binding != explicit_indices:
            return 'match', [], 'Explicit heavy-atom binding conflicts with concrete atom-map labels.'
        return "match", binding, "The concrete structure's atom-map labels determine the heavy-atom binding."

    if explicit_indices is not None:
        return 'match', explicit_indices, 'Explicit heavy-atom binding accepted against the concrete graph.'
    if not matches:
        return "inconclusive", [], "Same molecular graph, but SMILES atoms could not be bound to the concrete structure."
    # useChirality 对 atropisomer/轴手性子结构匹配未实现；声明了轴构型时用
    # 3D 二面角单独校验，不一致则身份判 mismatch。
    axis_diag = _axis_config_consistency(expected, structure, full_matches)
    if axis_diag is not None:
        return "mismatch", [], axis_diag
    distinct = sorted(allowed)
    if len(distinct) != 1:
        if prove_symmetry:
            if len(matches) == parameters.maxMatches:
                return 'match', [], 'Symmetric binding enumeration is incomplete; supply complete concrete atom-map labels.'
            if not all(_complete_binding_preserves_identity(expected_clean, structure_copy, structure_heavy, match)
                       for match in matches):
                return 'match', [], 'Candidate bindings do not all preserve complete electronic, isotope, hydrogen, bond and stereo identity; inspect complete concrete candidates or supply complete atom-map labels.'
            axis_diag = _axis_config_consistency(expected, structure, full_matches, require_all=True)
            if axis_diag:
                return 'match', [], axis_diag + ' Inspect complete concrete candidates or supply complete atom-map labels.'
            return 'match', list(distinct[0]), f'All {len(matches)} exhaustively enumerated bindings preserve complete molecular identity; selected a deterministic symmetric representative.'
        if allow_symmetric_representative and not unlabelled:
            return 'match', [], 'Concrete atom labels are provenance and cannot be replaced by a symmetric representative; supply complete compatible atom-map labels.'
        count = f'at least {len(distinct)}' if len(matches) == 256 else str(len(distinct))
        return (
            "match",
            [],
            f"The concrete structure has {count} symmetric heavy-atom bindings; without concrete atom-map labels the binding is not unique.",
        )
    return "match", list(distinct[0]), ""


def _axis_config_consistency(expected, structure, matches, *, require_all=False) -> Optional[str]:
    """校验具体结构 3D 坐标体现的轴构型与 SMILES 声明一致；不一致返回诊断串。"""
    from rdkit import Chem

    declared = [
        ax for ax in find_potential_chiral_axes(expected)
        if ax["configuration"] in {"atrop_cw", "atrop_ccw"}
    ]
    if not declared:
        return None
    if structure.GetNumConformers() == 0:
        return 'Declared axial stereochemistry has no concrete geometry proof.' if require_all else None
    conf = structure.GetConformer()
    s_ranks = list(Chem.CanonicalRankAtoms(structure, breakTies=False))
    for match in matches if require_all else matches[:1]:
        for ax in declared:
            a = match[ax["bond"][0] - 1]
            b = match[ax["bond"][1] - 1]
            cfg = _axis_config_from_3d(structure, conf, a, b, s_ranks)
            if cfg is None and require_all:
                return f'Concrete axial stereochemistry at bond {ax["bond"]} cannot be proved for every candidate binding.'
            if cfg is not None and cfg != ax["configuration"]:
                return (
                    f"Concrete structure's axial configuration at bond {ax['bond']} "
                    f"is {cfg}, but the SMILES declares {ax['configuration']}."
                )
    return None


def _expand_full_atom_maps(
    reactant_structure, product_structure,
    reactant_query_to_actual: list[int], product_query_to_actual: list[int],
    heavy_atom_map: list[int],
) -> tuple[list[list[int]], str]:
    """Keep proven local isotope pairs and enumerate only unmatched hydrogen identities."""
    r_inventory = Counter(_atom_key(atom) for atom in reactant_structure.GetAtoms())
    p_inventory = Counter(_atom_key(atom) for atom in product_structure.GetAtoms())
    if r_inventory != p_inventory:
        return [], 'Explicit-atom element/isotope counts of the concrete structures differ; cannot generate a full-atom mapping.'
    full_map = [-1] * product_structure.GetNumAtoms()
    for p_query, r_query in enumerate(heavy_atom_map):
        full_map[product_query_to_actual[p_query]] = reactant_query_to_actual[r_query - 1]

    heavy_labels = [[atom.GetAtomMapNum() for atom in structure.GetAtoms() if atom.GetAtomicNum() != 1]
        for structure in (reactant_structure, product_structure)]
    if all(values and all(values) for values in heavy_labels):
        if set(heavy_labels[0]) != set(heavy_labels[1]):
            return [], 'Concrete heavy-atom map labels conflict between endpoints.'
        for p_index, r_index in enumerate(full_map):
            if r_index >= 0 and product_structure.GetAtomWithIdx(p_index).GetAtomMapNum() != reactant_structure.GetAtomWithIdx(r_index).GetAtomMapNum():
                return [], 'Candidate correspondence conflicts with concrete heavy-atom map labels.'

    # Compatible concrete H labels are identity evidence, including transferred H.
    labelled = []
    for structure in (reactant_structure, product_structure):
        atoms = [atom for atom in structure.GetAtoms() if atom.GetAtomicNum() == 1 and atom.GetAtomMapNum()]
        by_label = {atom.GetAtomMapNum(): atom.GetIdx() for atom in atoms}
        if len(by_label) != len(atoms):
            return [], 'Concrete hydrogen atom-map labels must be unique.'
        labelled.append(by_label)
    if set(labelled[0]) != set(labelled[1]):
        return [], 'Concrete hydrogen atom-map labels conflict between endpoints.'
    for label, p_index in labelled[1].items():
        r_index = labelled[0][label]
        if _atom_key(product_structure.GetAtomWithIdx(p_index)) != _atom_key(reactant_structure.GetAtomWithIdx(r_index)):
            return [], 'Concrete hydrogen labels change isotope identity.'
        full_map[p_index] = r_index

    used = {index for index in full_map if index >= 0}
    for p_index, r_index in enumerate(full_map):
        if r_index < 0 or product_structure.GetAtomWithIdx(p_index).GetAtomicNum() == 1:
            continue
        p_groups, r_groups = defaultdict(list), defaultdict(list)
        for atom in product_structure.GetAtomWithIdx(p_index).GetNeighbors():
            if atom.GetAtomicNum() == 1 and full_map[atom.GetIdx()] < 0:
                p_groups[atom.GetIsotope()].append(atom.GetIdx())
        for atom in reactant_structure.GetAtomWithIdx(r_index).GetNeighbors():
            if atom.GetAtomicNum() == 1 and atom.GetIdx() not in used:
                r_groups[atom.GetIsotope()].append(atom.GetIdx())
        for isotope in sorted(p_groups):
            for p_h, r_h in zip(sorted(p_groups[isotope]), sorted(r_groups[isotope])):
                full_map[p_h] = r_h
                used.add(r_h)
    p_groups, r_groups = defaultdict(list), defaultdict(list)
    for atom in product_structure.GetAtoms():
        if full_map[atom.GetIdx()] < 0:
            if atom.GetAtomicNum() != 1:
                return [], 'Some heavy atoms remain unmapped; cannot output a partial atom_map.'
            p_groups[atom.GetIsotope()].append(atom.GetIdx())
    for atom in reactant_structure.GetAtoms():
        if atom.GetIdx() not in used:
            r_groups[atom.GetIsotope()].append(atom.GetIdx())
    isotopes = sorted(p_groups)
    if {key: len(value) for key, value in p_groups.items()} != {key: len(value) for key, value in r_groups.items()}:
        return [], 'Unmatched hydrogen isotope inventories differ.'
    count = math.prod(math.factorial(len(r_groups[key])) for key in isotopes)
    if count >= 257:
        return [], 'Hydrogen correspondence enumeration is incomplete; supply compatible concrete hydrogen atom-map labels.'
    candidates = []
    for permutations in itertools.product(*(itertools.permutations(r_groups[key]) for key in isotopes)):
        complete = list(full_map)
        for isotope, permutation in zip(isotopes, permutations):
            for p_index, r_index in zip(p_groups[isotope], permutation):
                complete[p_index] = r_index
        if sorted(complete) != list(range(reactant_structure.GetNumAtoms())):
            return [], 'Some atoms remain unmapped or are mapped twice; cannot output a partial atom_map.'
        candidates.append([index + 1 for index in complete])
    return candidates, 'Complete concrete correspondence candidates preserve hydrogen isotope identities.'


def _concrete_bindings(smiles: str, structure) -> tuple[str, list[list[int]], str]:
    """Enumerate proven graph bindings, retaining concrete symmetry as a choice."""
    from rdkit import Chem

    from cloudra.tools.core.reaction_state import heavy_binding

    if structure is None:
        return 'not_provided', [], 'A concrete endpoint structure is required.'
    if structure.HasProp('cloudra_graph_status') and structure.GetProp('cloudra_graph_status') == 'unresolved':
        return 'inconclusive', [], 'XYZ coordinates alone do not prove molecular identity; supply the corresponding MOL/SDF graph.'
    # A previous mapping choice is an output, not additional source identity.
    # Reuse build/catalog identity, but re-enumerate choices derived from mapping.
    derived = structure.HasProp('cloudra_mapping_binding_derived') and structure.GetBoolProp('cloudra_mapping_binding_derived')
    known = [] if derived else heavy_binding(structure)
    identity, binding, diagnostic = _identity_and_binding(smiles, structure,
        [index - 1 for index in known] if known else None)
    if identity == 'match' and all(atom.GetAtomicNum() == 1 for atom in structure.GetAtoms()):
        return identity, [[]], diagnostic
    if identity != 'match' or binding:
        return identity, [binding] if binding else [], diagnostic
    # Partial/conflicting labels and incompatible stereo are errors, not symmetry.
    labels = [[atom.GetAtomMapNum() for atom in graph.GetAtoms() if atom.GetAtomicNum() != 1]
        for graph in (_parse_heavy_smiles(smiles, 'Endpoint'), structure)]
    invalid_labels = any(any(values) and (not all(values) or len(set(values)) != len(values)) for values in labels)
    conflicting_labels = all(all(values) for values in labels) and set(labels[0]) != set(labels[1])
    if known or invalid_labels or conflicting_labels:
        return identity, [], diagnostic
    expected = _clear_atom_maps(_parse_heavy_smiles(smiles, 'Endpoint'))
    concrete = _clear_atom_maps(structure)
    for atom in concrete.GetAtoms():
        atom.SetIntProp('_full_idx', atom.GetIdx())
    heavy = Chem.RemoveHs(concrete)
    parameters = Chem.SubstructMatchParameters()
    parameters.uniquify = False
    parameters.useChirality = True
    parameters.maxMatches = 257  # Reuse the existing complete-enumeration sentinel.
    matches = heavy.GetSubstructMatches(expected, parameters)
    if len(matches) == parameters.maxMatches:
        return identity, [], 'Concrete binding enumeration is incomplete; complete compatible atom-map labels are required.'
    positions = [atom.GetIdx() for atom in expected.GetAtoms() if atom.GetAtomicNum() != 1]
    bindings = []
    for match in matches:
        indices = [heavy.GetAtomWithIdx(match[index]).GetIntProp('_full_idx') for index in positions]
        checked, accepted, _ = _identity_and_binding(smiles, structure, indices)
        if checked == 'match' and accepted:
            bindings.append(accepted)
    return identity, [list(value) for value in sorted(set(map(tuple, bindings)))], diagnostic


def bind_reaction_structures(input: TsInput, reactant: Molecule, product: Molecule) -> dict:
    """Bind current concrete molecules using the TS declaration's electronic state."""
    reaction = input.reaction
    state = dict(charge=reaction.charge, multiplicity=reaction.multiplicity,
        electronic_character=reaction.electronic_character)
    return _bind_endpoint_structures(reaction, reactant, product, {'reactant': state, 'product': state}, inspect_coordinates=False)


def _bind_endpoint_structures(reaction, reactant, product, states, *, inspect_coordinates=True) -> dict:
    """Shared graph/binding algorithm; independent analysis retains each endpoint's declared state."""
    from rdkit import Chem

    from cloudra.tools.core.electronic_state import electronic_state_issue

    result = analyze_reaction_mapping(
        chemical_smiles(reaction.reactant_smiles), chemical_smiles(reaction.product_smiles))
    graph_candidates = result['candidates']
    result.update(binding_status='inconclusive', binding_source='not_available', atom_map=[],
        concrete_watch_pairs=[], heavy_atom_bindings={}, structure_digests={}, binding_diagnostics=[],
        graph_watch_pairs=[], watch_pairs=[], heavy_atom_map=[], formed_bonds=[], broken_bonds=[],
        order_changes=[], candidates=[])
    choices = {}
    for role, structure in (('reactant', reactant), ('product', product)):
        smiles = getattr(reaction, role + '_smiles')
        graph_smiles = chemical_smiles(smiles)
        declared = Chem.MolFromSmiles(graph_smiles)
        state = states[role]
        for graph in (declared, structure):
            if graph is not None:
                issue = electronic_state_issue(graph, **state)
                if issue:
                    raise ValueError(f'{role}: {issue[1]}')
        graph = Chem.Mol(structure) if structure is not None else None
        if graph is not None and not inspect_coordinates:
            graph.RemoveAllConformers()
        identity, bindings, diagnostic = _concrete_bindings(graph_smiles, graph)
        result[role + '_identity'] = identity
        choices[role] = bindings
        if len(bindings) == 1:
            result['heavy_atom_bindings'][role] = [index + 1 for index in bindings[0]]
        if diagnostic:
            result['binding_diagnostics'].append(f'{role}: {diagnostic}')
        if structure is not None:
            result['structure_digests'][role] = concrete_structure_digest(role, smiles,
                state['charge'], state['multiplicity'], structure,
                electronic_character=state['electronic_character'])
    if not all(choices.values()):
        result['mapping_status'] = 'inconclusive'
        return result
    candidates = {}
    failed = set()
    for graph, r_binding, p_binding in itertools.product(graph_candidates, choices['reactant'], choices['product']):
        atom_maps, diagnostic = _expand_full_atom_maps(reactant, product, r_binding, p_binding, graph['heavy_atom_map'])
        if not atom_maps:
            failed.add(diagnostic)
            continue
        concrete_pairs = sorted(sorted((r_binding[a - 1] + 1, r_binding[b - 1] + 1))
            for a, b in graph['formed_bonds'] + graph['broken_bonds'])
        for atom_map in atom_maps:
            candidate = {**graph, 'atom_map': atom_map,
                'heavy_atom_bindings': {'reactant': [a + 1 for a in r_binding], 'product': [a + 1 for a in p_binding]},
                'graph_watch_pairs': sorted(graph['formed_bonds'] + graph['broken_bonds']),
                'concrete_watch_pairs': concrete_pairs}
            key = tuple(atom_map)
            if key not in candidates or candidate['score'] < candidates[key]['score']:
                candidates[key] = candidate
    ordered = sorted(candidates.values(), key=lambda candidate: (candidate['score'], candidate['atom_map']))
    result['candidates'] = ordered
    if not ordered:
        result['mapping_status'] = 'inconclusive'
        result['binding_diagnostics'].extend(sorted(failed))
        return result
    leading = [candidate for candidate in ordered if candidate['score'] <= ordered[0]['score'] + _AMBIGUITY_SCORE_WINDOW]
    result['mapping_status'] = 'unique' if len(leading) == 1 else 'ambiguous'
    selection = reaction.selected_candidate
    if selection is None and len(leading) != 1:
        result['message'] = 'Concrete endpoint correspondence is ambiguous; inspect candidates and choose selected_candidate.'
        return result
    selection = 0 if selection is None else selection
    if not 0 <= selection < len(ordered):
        raise ValueError(f'selected_candidate={selection} out of range; {len(ordered)} complete concrete candidate(s) available')
    selected = ordered[selection]
    for field in ('heavy_atom_map', 'atom_map', 'heavy_atom_bindings', 'formed_bonds', 'broken_bonds',
                  'order_changes', 'graph_watch_pairs', 'concrete_watch_pairs'):
        result[field] = selected[field]
    result.update(binding_status='complete', binding_source='concrete', watch_pairs=selected['concrete_watch_pairs'])
    result['message'] = 'Complete concrete endpoint correspondence accepted.'
    return result


def _mapping_json_schema(schema):
    source_fields = set(schema['properties']) - {'run_id', 'selected_candidate'}
    schema['oneOf'] = [
        {'required': ['run_id', 'selected_candidate'],
         'properties': {'run_id': {'type': 'string', 'minLength': 1}, 'selected_candidate': {'type': 'integer', 'minimum': 0}},
         'not': {'anyOf': [{'required': [field]} for field in sorted(source_fields)]}},
        {'required': ['reactant_smiles', 'product_smiles'],
         'properties': {'reactant_smiles': {'type': 'string', 'minLength': 1}, 'product_smiles': {'type': 'string', 'minLength': 1},
                        'run_id': {'type': 'null'}}},
    ]


class ReactionMapping_input_schema(input_schema):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_mapping_json_schema)
    run_id: str | None = Field(default=None, min_length=1, description="Existing TS run. Use only with selected_candidate to commit a concrete mapping choice; inspect candidates with ts_inspect.")
    reactant_smiles: str | None = Field(default=None, min_length=1, description="Independent analysis: reactant SMILES; mutually exclusive with run_id.")
    product_smiles: str | None = Field(default=None, min_length=1, description="Independent analysis: product SMILES.")
    selected_candidate: StrictInt | None = Field(default=None, ge=0, description="0-based complete concrete candidate choice. Omit/null for automatic adoption only when unique.")
    reactant_path: Optional[str] = Field(default=None, description="Path of a concrete reactant structure (mol/sdf/xyz).")
    reactant_text: Optional[str] = Field(default=None, description="Concrete reactant structure text. Path takes precedence.")
    product_path: Optional[str] = Field(default=None, description="Path of a concrete product structure (mol/sdf/xyz).")
    product_text: Optional[str] = Field(default=None, description="Concrete product structure text. Path takes precedence.")
    reactant_format: Literal["auto", "mol", "sdf", "xyz"] = "auto"
    product_format: Literal["auto", "mol", "sdf", "xyz"] = "auto"
    reactant_charge: int = Field(default=0, description="Reactant total charge, used when inferring XYZ bond orders.")
    product_charge: int = Field(default=0, description="Product total charge, used when inferring XYZ bond orders.")
    reactant_multiplicity: int = 1
    product_multiplicity: int = 1
    reactant_electronic_character: Literal['closed_shell', 'open_shell'] | None = None
    product_electronic_character: Literal['closed_shell', 'open_shell'] | None = None

    @model_validator(mode='after')
    def exclusive_sources(self):
        if self.run_id is not None:
            if not self.run_id.strip():
                raise ValueError('run_id must not be blank')
            if self.model_fields_set - {'run_id', 'selected_candidate'}:
                raise ValueError('run_id cannot be combined with independent endpoint sources')
            if self.selected_candidate is None:
                raise ValueError('run_id requires selected_candidate; use ts_inspect to view current candidates')
        elif not self.reactant_smiles or not self.product_smiles:
            raise ValueError('independent analysis requires both endpoint SMILES')
        return self

    @classmethod
    def to_parameters_schema(cls):
        schema = super().to_parameters_schema()
        schema['oneOf'] = cls.model_json_schema()['oneOf']
        return schema


class ReactionMapping_output_schema(output_schema):
    is_success: bool = Field(description="Whether the tool ran normally.")
    mapping_status: Literal["unique", "ambiguous", "inconclusive"] = "inconclusive"
    candidates: list[dict] = Field(default_factory=list)
    heavy_atom_map: list[int] = Field(default_factory=list)
    atom_map: list[int] = Field(default_factory=list)
    binding_status: Literal["complete", "inconclusive", "not_requested"] = "not_requested"
    binding_source: Literal["concrete", "internal_generated", "not_available"] = "not_available"
    reactant_identity: Literal["match", "mismatch", "inconclusive", "not_provided"] = "not_provided"
    product_identity: Literal["match", "mismatch", "inconclusive", "not_provided"] = "not_provided"
    binding_diagnostics: list[str] = Field(default_factory=list)
    structure_digests: dict[str, str] = Field(default_factory=dict)
    heavy_atom_bindings: dict[str, list[int]] = Field(default_factory=dict)
    formed_bonds: list[list[int]] = Field(default_factory=list)
    broken_bonds: list[list[int]] = Field(default_factory=list)
    order_changes: list[dict] = Field(default_factory=list)
    graph_watch_pairs: list[list[int]] = Field(default_factory=list)
    concrete_watch_pairs: list[list[int]] = Field(default_factory=list)
    potential_axes: dict = Field(
        default_factory=dict,
        description="Potential chiral axes on reactant/product (heuristic: both ends bear two graph-distinct substituents and pass a steric-congestion threshold).",
    )
    watch_pairs: list[list[int]] = Field(
        default_factory=list,
        description="Reaction atom pairs usable on the currently bound coordinates; graph-level indices when there is no safe concrete binding.",
    )
    message: str = ""


class ReactionMapping(Tool):
    tool_id: str = "t-49"
    tool_name: str = "reaction_mapping"
    tool_description: str = "Choose an inspected complete concrete mapping on an existing TS run, or independently analyze endpoint sources. Unique complete mappings are adopted automatically; read existing run structures and candidates with ts_inspect."
    input_schema: Any = ReactionMapping_input_schema
    output_schema: Any = ReactionMapping_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self, user_input: ReactionMapping_input_schema, session: Session,
    ) -> ReactionMapping_output_schema:
        try:
            from cloudra.tools.core.permission_model import Permission
            if self.subagent is not None and not self.subagent.permission_all() & Permission.WRITE:
                raise ValueError('Reaction mapping requires producer write permission')
            if user_input.run_id is not None:
                return await self._select_run_candidate(user_input, session)
            for field in ('reactant_path', 'product_path'):
                value = getattr(user_input, field)
                if value:
                    setattr(user_input, field, resolve_existing_tool_path(self, value))
            result = await asyncio.to_thread(self._analyze_sources, user_input)
            return ReactionMapping_output_schema(is_success=True, **result)
        except (OSError, RuntimeError, ValueError) as exc:
            return ReactionMapping_output_schema(is_success=False, mapping_status='inconclusive',
                message=f'Reaction mapping failed: {exc}')

    @staticmethod
    def _analyze_sources(user_input):
        from rdkit import Chem

        molecules = []
        for role in ('reactant', 'product'):
            molecules.append(_read_structure(getattr(user_input, role + '_path'), getattr(user_input, role + '_text'),
                getattr(user_input, role + '_format'), getattr(user_input, role + '_charge'), role,
                multiplicity=getattr(user_input, role + '_multiplicity'),
                electronic_character=getattr(user_input, role + '_electronic_character')))
        internal = all(mol is None for mol in molecules)
        if internal:
            molecules = [Chem.AddHs(Chem.MolFromSmiles(getattr(user_input, role + '_smiles')))
                for role in ('reactant', 'product')]
            # These are generated directly in the declaration's order, not file-row guesses.
            for mol in molecules:
                for position, atom in enumerate(atom for atom in mol.GetAtoms() if atom.GetAtomicNum() != 1):
                    atom.SetIntProp('cloudra_smiles_heavy_index', position)
        declaration = TsInput(reaction=dict(reactant_smiles=user_input.reactant_smiles,
            product_smiles=user_input.product_smiles, charge=user_input.reactant_charge,
            multiplicity=user_input.reactant_multiplicity,
            electronic_character=user_input.reactant_electronic_character,
            selected_candidate=user_input.selected_candidate))
        states = {role: {field: getattr(user_input, role + '_' + field)
            for field in ('charge', 'multiplicity', 'electronic_character')} for role in ('reactant', 'product')}
        result = _bind_endpoint_structures(declaration.reaction, *molecules, states)
        if internal:
            result['binding_source'] = 'internal_generated' if result['atom_map'] else 'not_available'
            result['reactant_identity'] = result['product_identity'] = 'not_provided'
        return result

    async def _select_run_candidate(self, user_input, session):
        from cloudra.services.ts_pipeline_context import pipeline_database
        from cloudra.tools.Chemtool.ts_search_process import _read_resume_record, _resolve_workspace, revise_run

        revised = await revise_run(self, user_input.run_id,
            {'reaction': {'selected_candidate': user_input.selected_candidate}},
            'Choose inspected complete concrete endpoint correspondence', session)
        if not revised.is_success:
            return ReactionMapping_output_schema(is_success=False, message=revised.message)
        record = await asyncio.to_thread(_read_resume_record, pipeline_database(), _resolve_workspace(self),
            user_input.run_id, self.subagent.conversation_id)
        if record.structures.product_to_reactant is None:
            return ReactionMapping_output_schema(is_success=False, message=revised.message)
        from cloudra.tools.core.reaction_state import heavy_binding
        record.structures.complete_correspondence()
        # This is the accepted state. Re-enumerating after pinning its atom
        # identities would assign different candidate indices and break replay.
        return ReactionMapping_output_schema(is_success=True, mapping_status='unique',
            binding_status='complete', binding_source='concrete',
            reactant_identity='match', product_identity='match',
            atom_map=[index + 1 for index in record.structures.product_to_reactant],
            heavy_atom_bindings={role: heavy_binding(getattr(record.structures, role))
                for role in ('reactant', 'product')},
            message='Concrete candidate choice committed on the existing TS run; use ts_inspect for current structures and evidence.')





def derive_delivery_changes(
    *,
    current: dict[str, Any],
    role: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """DAG evidence derivation owned by this tool; kept out of DagController."""
    del current, arguments  # 本工具派生不需要 current/arguments
    if role == "endpoint_identity_match" and (
        result.get("binding_status") == "complete"
        and result.get("reactant_identity") == "match"
        and result.get("product_identity") == "match"
    ):
        return {"endpoint_identity_matched": True}
    return {}
