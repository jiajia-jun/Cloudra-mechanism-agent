"""complex_assembly：平移方向、解离判据、无约束能量重估、重原子聚类、取向采样。"""

import numpy as np
import pytest

pytest.importorskip("rdkit", reason="complex_assembly requires RDKit (chem extra)")

from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402

import cloudra.tools.core.complex_assembly as assembly_mod  # noqa: E402
from cloudra.tools.core.complex_assembly import (  # noqa: E402
    AssemblyParameters,
    _greedy_heavy_atom_clusters,
    _sample_placements,
    _separate_along_axis,
    assemble,
    combine_components,
)


def _embedded_mol(smiles: str, seed: int = 42):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    assert AllChem.EmbedMolecule(mol, params) == 0
    assert AllChem.MMFFOptimizeMolecule(mol) == 0
    return mol


def _two_component_complex(tmp_path, monkeypatch, relax, reaction_center=None):
    monkeypatch.setattr(assembly_mod, "_relax_with_trajectory", relax)
    components = [(_embedded_mol("O"), 0), (_embedded_mol("C"), 0)]
    return assemble(
        components=components, output_dir=str(tmp_path),
        reaction_center=reaction_center,
    )


# ---------------------------------------------------------------------------
# 平移方向：最近片间连线，而不是固定 +x
# ---------------------------------------------------------------------------


def test_separation_pushes_along_the_nearest_pair_direction():
    """最近对在 z 方向时，推开方向必须沿 z（旧实现只会推 +x）。"""
    positions = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.1]]
    out = _separate_along_axis(positions, [[0], [1]], 1.0)
    moved = out[1]
    assert moved[2] >= 1.0, f"应沿最近对连线（z）推开，得到 {moved}"
    assert abs(moved[0]) < 1e-9 and abs(moved[1]) < 1e-9
    assert float(np.linalg.norm(out[1] - out[0])) >= 1.0


def test_separation_falls_back_to_plus_x_only_on_exact_overlap():
    positions = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    out = _separate_along_axis(positions, [[0], [1]], 1.0)
    assert float(np.linalg.norm(out[1] - out[0])) >= 1.0


# ---------------------------------------------------------------------------
# 解离判据：片间距离超出 vdW 接触倍数即丢弃
# ---------------------------------------------------------------------------


def test_dissociated_placements_are_never_delivered(tmp_path, monkeypatch):
    """弛豫后碎片被推到 30 Å 外：全部判解离丢弃，绝不作为复合物候选交付。"""

    def _explode(mol, conf_id, writer, parameters, **_kwargs):
        conf = mol.GetConformer(conf_id)
        frags = Chem.GetMolFrags(mol)
        for index in frags[1]:
            point = conf.GetAtomPosition(index)
            conf.SetAtomPosition(index, (point.x + 30.0, point.y, point.z))
        writer.append(
            0,
            [[float(v) for v in conf.GetAtomPosition(i)] for i in range(mol.GetNumAtoms())],
            0.0, None,
        )
        return True, False, ""

    result = _two_component_complex(tmp_path, monkeypatch, _explode)
    assert result.status == "no_candidate"
    assert result.candidates == []
    assert result.dissociated_after_relaxation > 0
    assert result.collapsed_after_relaxation == 0
    assert "dissociation limit" in result.message
    assert any("vdW contact" in d for d in result.diagnostics)


def test_bound_complex_is_not_flagged_as_dissociated(tmp_path, monkeypatch):
    """对照：弛豫不动几何时，正常结合的复合物不得被解离判据误杀。"""

    def _keep(mol, conf_id, writer, parameters, **_kwargs):
        conf = mol.GetConformer(conf_id)
        writer.append(
            0,
            [[float(v) for v in conf.GetAtomPosition(i)] for i in range(mol.GetNumAtoms())],
            0.0, None,
        )
        return True, False, ""

    result = _two_component_complex(tmp_path, monkeypatch, _keep)
    assert result.dissociated_after_relaxation == 0
    assert result.status == "ok"
    for candidate in result.candidates:
        assert candidate.min_interfragment_distance >= result.parameters.min_interfragment_distance


# ---------------------------------------------------------------------------
# 反应模式：约束未释放的候选用无约束单点重估能量
# ---------------------------------------------------------------------------


def test_unreleased_candidate_energy_is_unconstrained_single_point(tmp_path, monkeypatch):
    """final_frame.energy 含约束惩罚时不得进排序：候选能量 = 最终几何的无约束单点。"""
    penalty_energy = 999.0

    def _constrained(mol, conf_id, writer, parameters, **_kwargs):
        conf = mol.GetConformer(conf_id)
        writer.append(
            0,
            [[float(v) for v in conf.GetAtomPosition(i)] for i in range(mol.GetNumAtoms())],
            penalty_energy, None,
        )
        return True, False, ""  # converged, constraint NOT released

    components = [(_embedded_mol("O"), 0), (_embedded_mol("C"), 0)]
    monkeypatch.setattr(assembly_mod, "_relax_with_trajectory", _constrained)
    result = assemble(
        components=components, output_dir=str(tmp_path),
        reaction_center=[(0, 3)],  # 水的 O 与甲烷的 C
    )
    assert result.status == "ok"
    assert any("unconstrained MMFF94 single point" in d for d in result.diagnostics)
    for candidate in result.candidates:
        assert candidate.constraint_released is False
        assert candidate.energy_kcal != penalty_energy, "约束惩罚能量不得进入候选排序"
        assert candidate.energy_kcal < 100.0


# ---------------------------------------------------------------------------
# 重原子 RMSD 聚类：氢取向噪声不拆簇
# ---------------------------------------------------------------------------


def test_clustering_compares_heavy_atoms_only():
    """同一复合物只动羟基氢取向 → 同簇；全原子口径下它们会超过阈值（正是被修的 bug）。"""
    heavy = [[0.0, 0.0, 0.0], [1.4, 0.0, 0.0], [-1.4, 0.0, 0.0]]
    base = heavy + [[1.9, 0.8, 0.0]]
    rotated_h = heavy + [[1.9, -0.8, 0.0]]  # 只动 H（0.8→-0.8，全原子 RMSD 大）
    # 重原子本身的几何改变（拉长一根键；注意 Kabsch 去质心，纯平移不算差异）
    stretched = [[0.0, 0.0, 0.0], [1.4, 0.0, 0.0], [-3.4, 0.0, 0.0]] + [[1.9, 0.8, 0.0]]
    heavy_indices = [0, 1, 2]
    cluster_ids, representatives = _greedy_heavy_atom_clusters(
        [base, rotated_h, stretched], heavy_indices, 0.5,
    )
    assert cluster_ids[0] == cluster_ids[1], "只有氢取向不同的候选必须同簇"
    assert cluster_ids[2] != cluster_ids[0], "重原子几何改变 2 Å 的候选必须另立一簇"
    assert representatives == [0, 2]


# ---------------------------------------------------------------------------
# 取向采样：方向索引不解耦时 gcd 退化；扭转角采样
# ---------------------------------------------------------------------------


def test_orientation_sampling_is_not_degenerate(tmp_path):
    """orientations=7（旧索引 (sample*7+g*3)%7 会把全部采样压到同一方向）：7 个放置必须互不相同。"""
    components = [(_embedded_mol("O"), 0), (_embedded_mol("C"), 0), (_embedded_mol("N"), 0)]
    mol = combine_components(components)
    groups = assembly_mod._component_atom_groups(components)
    placements = _sample_placements(mol, groups, AssemblyParameters(orientations=7))
    assert len(placements) == 7
    fingerprints = {
        tuple(np.round(np.asarray(positions, dtype=float), 6).ravel())
        for _index, positions in placements
    }
    assert len(fingerprints) == 7, "取向采样退化：多个放置落到了同一相对取向"
