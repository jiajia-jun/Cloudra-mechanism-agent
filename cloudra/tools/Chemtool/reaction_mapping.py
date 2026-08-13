"""反应物/产物原子映射与反应中心候选分析。

未标号 SMILES 的映射本质上可能不唯一。本模块返回候选和评分事实，不把最低编辑
排列包装成唯一机理结论。
"""

import itertools
import math
import os
from collections import Counter, defaultdict
from typing import Any, Literal, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

_MAX_EXHAUSTIVE_MAPPINGS = 100_000
_MAX_RETURNED_CANDIDATES = 16
_AMBIGUITY_SCORE_WINDOW = 2.0


def _parse_heavy_smiles(smiles: str, role: str):
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"{role} SMILES 无法解析: {smiles}")
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
        raise ValueError("atom-map 标签必须覆盖两端每一个重原子，不能只提供部分标签")
    if len(set(r_labels)) != len(r_labels) or len(set(p_labels)) != len(p_labels):
        raise ValueError("同一分子内 atom-map 标签不能重复")
    if set(r_labels) != set(p_labels):
        raise ValueError("反应物与产物的 atom-map 标签集合不一致")
    r_by_label = {label: idx for idx, label in enumerate(r_labels)}
    for p_idx, label in enumerate(p_labels):
        r_idx = r_by_label[label]
        if _atom_key(product.GetAtomWithIdx(p_idx)) != _atom_key(reactant.GetAtomWithIdx(r_idx)):
            raise ValueError(
                f"atom-map 标签 {label} 在两端连接了不同元素或同位素"
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
    unique: dict[tuple[int, ...], dict] = {}
    for mapping in raw_mappings:
        key = tuple(mapping)
        if key not in unique:
            unique[key] = _score_mapping(reactant, product, mapping, "rdkit_graph_search")
    candidates = sorted(
        unique.values(),
        key=lambda item: (item["score"], item["heavy_atom_map"]),
    )[:_MAX_RETURNED_CANDIDATES]
    return candidates, False


def analyze_reaction_mapping(
    reactant_smiles: str,
    product_smiles: str,
    selected_candidate: int = 0,
) -> dict:
    reactant = _parse_heavy_smiles(reactant_smiles, "反应物")
    product = _parse_heavy_smiles(product_smiles, "产物")
    r_inventory = Counter(_atom_key(atom) for atom in reactant.GetAtoms())
    p_inventory = Counter(_atom_key(atom) for atom in product.GetAtoms())
    if r_inventory != p_inventory:
        raise ValueError(f"反应前后重原子元素数不一致: {dict(r_inventory)} vs {dict(p_inventory)}")

    candidates, authoritative = _candidate_mappings(reactant, product)
    if not candidates:
        return {
            "mapping_status": "inconclusive",
            "candidates": [],
            "heavy_atom_map": [],
            "formed_bonds": [],
            "broken_bonds": [],
            "order_changes": [],
            "watch_pairs": [],
            "message": "没有生成可用的元素守恒映射候选。",
        }
    if not 0 <= selected_candidate < len(candidates):
        raise ValueError(
            f"selected_candidate={selected_candidate} 越界，共 {len(candidates)} 个候选"
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
        "映射由两端完整 atom-map 标签确定。"
        if authoritative
        else (
            "存在分数相近的原子映射候选，需要 agent 结合机理假设或人工选择。"
            if status == "ambiguous"
            else "图编辑与原子环境评分得到单一领先候选；仍建议结合机理检查。"
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


def _read_structure(
    path: Optional[str], text: Optional[str], fmt: str, charge: int, role: str,
):
    from rdkit import Chem

    if not path and not text:
        return None
    if path:
        if not os.path.isfile(path):
            raise ValueError(f"{role}结构文件不存在: {path}")
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
        from rdkit.Chem import rdDetermineBonds

        mol = Chem.MolFromXYZBlock(payload)
        if mol is not None:
            rdDetermineBonds.DetermineBonds(mol, charge=charge)
            Chem.SanitizeMol(mol)
    else:
        raise ValueError(f"{role}结构格式不支持: {actual_format or '无法从路径推断'}")
    if mol is None:
        raise ValueError(f"{role}结构无法按 {actual_format} 解析")
    return mol


def _identity_and_binding(expected_smiles: str, structure) -> tuple[str, list[int], str]:
    """返回图身份、expected heavy -> concrete full-atom index，以及绑定诊断。"""
    from rdkit import Chem

    if structure is None:
        return "not_provided", [], ""
    expected = _parse_heavy_smiles(expected_smiles, "端点")
    expected_labels = [atom.GetAtomMapNum() for atom in expected.GetAtoms()]
    concrete_heavy_atoms = [atom for atom in structure.GetAtoms() if atom.GetAtomicNum() != 1]
    concrete_labels = [atom.GetAtomMapNum() for atom in concrete_heavy_atoms]
    structure_heavy = Chem.RemoveHs(_clear_atom_maps(structure))
    if _canonical_heavy_smiles(expected) != _canonical_heavy_smiles(structure_heavy):
        return "mismatch", [], "具体结构与声明 SMILES 的分子图不一致。"

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
            concrete_atom = structure.GetAtomWithIdx(
                concrete_by_label[expected_atom.GetAtomMapNum()]
            )
            if _atom_key(expected_atom) != _atom_key(concrete_atom):
                return (
                    "match",
                    [],
                    f"具体结构 atom-map 标签 {expected_atom.GetAtomMapNum()} 的元素或同位素不一致。",
                )
        binding = [concrete_by_label[label] for label in expected_labels]
        return "match", binding, "具体结构的 atom-map 标签确定了重原子绑定。"

    expected_clean = _clear_atom_maps(expected)
    matches = structure_heavy.GetSubstructMatches(
        expected_clean, uniquify=False, useChirality=True, maxMatches=256,
    )
    if not matches:
        return "inconclusive", [], "分子图相同，但无法把 SMILES 原子绑定到具体结构。"
    original_heavy_indices = [
        atom.GetIdx() for atom in structure.GetAtoms() if atom.GetAtomicNum() != 1
    ]
    distinct = sorted(set(matches))
    if len(distinct) != 1:
        return (
            "match",
            [],
            f"具体结构存在 {len(distinct)} 个对称重原子绑定；没有 concrete atom-map 标签，绑定不唯一。",
        )
    return "match", [original_heavy_indices[idx] for idx in distinct[0]], ""


def _expand_full_atom_map(
    reactant_structure,
    product_structure,
    reactant_query_to_actual: list[int],
    product_query_to_actual: list[int],
    heavy_atom_map: list[int],
) -> tuple[list[int], str]:
    """把 SMILES 重原子映射绑定到 concrete product atom -> reactant atom。"""
    r_inventory = Counter(atom.GetAtomicNum() for atom in reactant_structure.GetAtoms())
    p_inventory = Counter(atom.GetAtomicNum() for atom in product_structure.GetAtoms())
    if r_inventory != p_inventory:
        return [], "具体结构的显式原子元素数不一致，不能生成全原子映射。"

    full_map = [-1] * product_structure.GetNumAtoms()
    for p_query_idx, r_query_one_based in enumerate(heavy_atom_map):
        p_actual = product_query_to_actual[p_query_idx]
        r_actual = reactant_query_to_actual[r_query_one_based - 1]
        full_map[p_actual] = r_actual

        p_hydrogens = sorted(
            atom.GetIdx() for atom in product_structure.GetAtomWithIdx(p_actual).GetNeighbors()
            if atom.GetAtomicNum() == 1
        )
        r_hydrogens = sorted(
            atom.GetIdx() for atom in reactant_structure.GetAtomWithIdx(r_actual).GetNeighbors()
            if atom.GetAtomicNum() == 1
        )
        if len(p_hydrogens) != len(r_hydrogens):
            return [], (
                f"映射重原子 P{p_query_idx + 1}→R{r_query_one_based} 的显式氢数不同；"
                "可能存在质子转移或结构缺氢。"
            )
        for p_h, r_h in zip(p_hydrogens, r_hydrogens):
            full_map[p_h] = r_h

    if -1 in full_map or sorted(full_map) != list(range(reactant_structure.GetNumAtoms())):
        return [], "仍有原子未映射或映射重复，不能输出部分 atom_map。"
    return [idx + 1 for idx in full_map], "全原子映射已绑定到具体结构顺序。"


def _bind_concrete_structures(user_input, mapping_result: dict) -> dict:
    reactant = _read_structure(
        user_input.reactant_path, user_input.reactant_text,
        user_input.reactant_format, user_input.reactant_charge, "反应物",
    )
    product = _read_structure(
        user_input.product_path, user_input.product_text,
        user_input.product_format, user_input.product_charge, "产物",
    )
    r_identity, r_binding, r_diagnostic = _identity_and_binding(user_input.reactant_smiles, reactant)
    p_identity, p_binding, p_diagnostic = _identity_and_binding(user_input.product_smiles, product)
    if reactant is None and product is None:
        from rdkit import Chem

        internal_reactant = Chem.AddHs(Chem.MolFromSmiles(user_input.reactant_smiles))
        internal_product = Chem.AddHs(Chem.MolFromSmiles(user_input.product_smiles))
        r_internal_binding = [
            atom.GetIdx() for atom in internal_reactant.GetAtoms() if atom.GetAtomicNum() != 1
        ]
        p_internal_binding = [
            atom.GetIdx() for atom in internal_product.GetAtoms() if atom.GetAtomicNum() != 1
        ]
        atom_map, diagnostic = _expand_full_atom_map(
            internal_reactant,
            internal_product,
            r_internal_binding,
            p_internal_binding,
            mapping_result["heavy_atom_map"],
        )
        concrete_pairs = [
            sorted([r_internal_binding[i - 1] + 1, r_internal_binding[j - 1] + 1])
            for i, j in mapping_result["watch_pairs"]
        ]
        return {
            "binding_status": "complete" if atom_map else "inconclusive",
            "binding_source": "internal_generated" if atom_map else "not_available",
            "reactant_identity": r_identity,
            "product_identity": p_identity,
            "atom_map": atom_map,
            "concrete_watch_pairs": sorted(concrete_pairs),
            "binding_diagnostics": [diagnostic],
        }
    if reactant is None or product is None:
        return {
            "binding_status": "inconclusive",
            "binding_source": "not_available",
            "reactant_identity": r_identity,
            "product_identity": p_identity,
            "atom_map": [],
            "concrete_watch_pairs": [],
            "binding_diagnostics": ["必须同时提供反应物和产物具体结构才能生成全原子映射。"],
        }
    if r_identity != "match" or p_identity != "match":
        return {
            "binding_status": "inconclusive",
            "binding_source": "not_available",
            "reactant_identity": r_identity,
            "product_identity": p_identity,
            "atom_map": [],
            "concrete_watch_pairs": [],
            "binding_diagnostics": [
                item for item in (r_diagnostic, p_diagnostic) if item
            ] or ["至少一个具体端点与声明 SMILES 的分子图不一致。"],
        }
    if not r_binding or not p_binding:
        return {
            "binding_status": "inconclusive",
            "binding_source": "not_available",
            "reactant_identity": r_identity,
            "product_identity": p_identity,
            "atom_map": [],
            "concrete_watch_pairs": [],
            "binding_diagnostics": [
                item for item in (r_diagnostic, p_diagnostic) if item
            ],
        }
    atom_map, diagnostic = _expand_full_atom_map(
        reactant, product, r_binding, p_binding, mapping_result["heavy_atom_map"],
    )
    concrete_pairs = [
        sorted([r_binding[i - 1] + 1, r_binding[j - 1] + 1])
        for i, j in mapping_result["watch_pairs"]
    ]
    return {
        "binding_status": "complete" if atom_map else "inconclusive",
        "binding_source": "concrete" if atom_map else "not_available",
        "reactant_identity": r_identity,
        "product_identity": p_identity,
        "atom_map": atom_map,
        "concrete_watch_pairs": sorted(concrete_pairs) if atom_map else [],
        "binding_diagnostics": [
            item for item in (r_diagnostic, p_diagnostic, diagnostic) if item
        ],
    }


class ReactionMapping_input_schema(input_schema):
    reactant_smiles: str = Field(description="Reactant SMILES.")
    product_smiles: str = Field(description="Product SMILES.")
    selected_candidate: int = Field(default=0, description="Selected mapping-candidate index (0-based).")
    reactant_path: Optional[str] = Field(default=None, description="Path of a concrete reactant structure (mol/sdf/xyz).")
    reactant_text: Optional[str] = Field(default=None, description="Concrete reactant structure text. Path takes precedence.")
    product_path: Optional[str] = Field(default=None, description="Path of a concrete product structure (mol/sdf/xyz).")
    product_text: Optional[str] = Field(default=None, description="Concrete product structure text. Path takes precedence.")
    reactant_format: Literal["auto", "mol", "sdf", "xyz"] = "auto"
    product_format: Literal["auto", "mol", "sdf", "xyz"] = "auto"
    reactant_charge: int = Field(default=0, description="Reactant total charge, used when inferring XYZ bond orders.")
    product_charge: int = Field(default=0, description="Product total charge, used when inferring XYZ bond orders.")


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
    formed_bonds: list[list[int]] = Field(default_factory=list)
    broken_bonds: list[list[int]] = Field(default_factory=list)
    order_changes: list[dict] = Field(default_factory=list)
    graph_watch_pairs: list[list[int]] = Field(default_factory=list)
    concrete_watch_pairs: list[list[int]] = Field(default_factory=list)
    watch_pairs: list[list[int]] = Field(
        default_factory=list,
        description="Reaction atom pairs usable on the currently bound coordinates; graph-level indices when there is no safe concrete binding.",
    )
    message: str = ""


class ReactionMapping(Tool):
    tool_id: str = "t-49"
    tool_name: str = "reaction_mapping"
    tool_description: str = "From reactant/product SMILES, generate inspectable atom-mapping candidates and reaction-center bond changes."
    input_schema: Any = ReactionMapping_input_schema
    output_schema: Any = ReactionMapping_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self, user_input: ReactionMapping_input_schema, session: Session,
    ) -> ReactionMapping_output_schema:
        try:
            result = analyze_reaction_mapping(
                user_input.reactant_smiles,
                user_input.product_smiles,
                selected_candidate=user_input.selected_candidate,
            )
            binding = _bind_concrete_structures(user_input, result)
            result["graph_watch_pairs"] = list(result["watch_pairs"])
            result.update(binding)
            if binding["binding_status"] == "complete":
                result["watch_pairs"] = binding["concrete_watch_pairs"]
            if binding["binding_diagnostics"]:
                result["message"] += " " + " ".join(binding["binding_diagnostics"])
            return ReactionMapping_output_schema(is_success=True, **result)
        except (OSError, RuntimeError, ValueError) as exc:
            return ReactionMapping_output_schema(
                is_success=False,
                mapping_status="inconclusive",
                message=f"反应映射失败: {exc}",
            )


def get_class():
    return ReactionMapping
