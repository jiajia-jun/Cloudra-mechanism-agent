"""complex_assembly：平移方向、解离判据、无约束能量重估、重原子聚类、取向采样。"""

import json
from pathlib import Path

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
from cloudra.tools.core.structure_artifacts import read_trajectory, read_xyz_atoms  # noqa: E402


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


def test_real_relaxation_reports_the_unconstrained_single_point_not_the_penalty(tmp_path):
    """端到端（真实力场，无 mock）：约束保持时交付能量必须是无约束单点，不是轨迹终态能量。

    反应中心取水分子内的 O-H 对（0-1）：窗口 1.8–2.6 Å 对共价键不可达（O-H 伸缩力常数远大于
    约束的 k=100），因此每个放置的约束全程激活、轨迹终态能量含真实惩罚项——正是旧实现直接拿
    去排序的那种能量。这里从**交付的 .xyz 几何**独立重算无约束 MMFF94 单点，要求与候选能量一致，
    并确认轨迹终态能量（含惩罚）与候选能量相差一个明显的惩罚项。
    """
    components = [(_embedded_mol("O"), 0), (_embedded_mol("C"), 0)]
    result = assemble(
        components=components, output_dir=str(tmp_path),
        reaction_center=[(0, 1)],  # 水的 O-H 共价对：默认窗口对其不可达
    )
    assert result.status == "ok"
    assert result.collapsed_after_relaxation == 0
    assert result.dissociated_after_relaxation == 0
    assert result.optimized_placements == result.parameters.reaction_center_candidates

    manifest = json.loads(Path(result.trajectory_manifest_path).read_text(encoding="utf-8"))
    records = [read_trajectory(entry["json_path"]) for entry in manifest["trajectories"]]
    assert len(records) == result.optimized_placements
    penalized = [record.final_frame.energy for record in records]
    assert all(record.status == "converged" for record in records)

    candidate = result.candidates[0]
    assert candidate.constraint_released is False
    assert any("unconstrained MMFF94 single point" in d for d in result.diagnostics)

    lines = Path(candidate.xyz_path).read_text(encoding="utf-8").splitlines()
    atom_count = int(lines[0])
    symbols = [line.split()[0] for line in lines[2:2 + atom_count]]
    positions = [[float(v) for v in line.split()[1:4]] for line in lines[2:2 + atom_count]]
    mol = combine_components(components)
    assert symbols == [atom.GetSymbol() for atom in mol.GetAtoms()]
    conf = mol.GetConformer()
    for index, (x, y, z) in enumerate(positions):
        conf.SetAtomPosition(index, (x, y, z))
    props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
    ff = AllChem.MMFFGetMoleculeForceField(
        mol, props, confId=conf.GetId(), ignoreInterfragInteractions=False,
    )
    ff.Initialize()
    assert ff.CalcEnergy() == pytest.approx(candidate.energy_kcal, abs=1e-3), (
        "候选能量必须就是交付几何上的无约束 MMFF94 单点"
    )
    assert min(penalized) - candidate.energy_kcal > 1.0, (
        "轨迹终态能量含约束惩罚项，旧实现直接拿它排序；两者必须相差一个可观测的惩罚量"
    )


def test_guided_assembly_keeps_soft_windows_and_ignores_equilibrium_energy_cutoff(tmp_path):
    components = [(_embedded_mol("CCO"), 0), (_embedded_mol("O"), 0)]
    windows = [(2, 9, 2.5, 3.8), (0, 9, 2.5, 3.8), (1, 9, 2.5, 3.8)]
    result = assemble(
        components=components, output_dir=str(tmp_path),
        parameters=AssemblyParameters(energy_window_kcal=-1.0),
        reaction_center=[(2, 9), (0, 9)], guided_windows=windows,
    )
    assert result.status == "ok"
    assert result.candidates
    assert len(result.candidates) > 3  # strict guidance is checked before heavy-atom deduplication
    assert all(candidate.constraint_released is False for candidate in result.candidates)
    qualified = 0
    for candidate in result.candidates:
        atoms = read_xyz_atoms(candidate.xyz_path)
        positions = [position for _, position in atoms]
        if all(low <= float(np.linalg.norm(
                    np.asarray(positions[left]) - np.asarray(positions[right])
                )) <= high for left, right, low, high in windows):
            qualified += 1
    assert qualified > 0


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


# ---------------------------------------------------------------------------
# 组分合并：多组分 + sp2 立体标记（GH #37）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("smiles", ["O.C/C=C/C", "O.CC/C(=N/O)/C"])
def test_combine_components_keeps_sp2_stereo(smiles):
    """多组分带 sp2 立体（C=C / C=N）时合并必须成立且立体不丢。

    旧实现按 `GetBonds()` 顺序在加键的**同一趟**里 `SetStereoAtoms`，而 sp2 立体的参考原子
    是远端取代基、其单键常排在双键之后（如 `C/C=C/C` 的键序 0-1 SINGLE、1-2 DOUBLE、
    2-3 SINGLE）→ RDKit 抛 "endIdx not connected to end atom of bond"，整条组装路径崩溃。
    """
    fragments = Chem.GetMolFrags(Chem.MolFromSmiles(smiles), asMols=True, sanitizeFrags=True)
    components = [(_embedded_mol(Chem.MolToSmiles(frag)), 0) for frag in fragments]
    mol = combine_components(components)

    stereo_bonds = [b for b in mol.GetBonds() if b.GetStereo() != Chem.BondStereo.STEREONONE]
    assert len(stereo_bonds) == 1, "输入里的 E/Z 双键必须原样保留"
    bond = stereo_bonds[0]
    stereo_atoms = list(bond.GetStereoAtoms())
    assert len(stereo_atoms) == 2, "参考原子必须随原子序号偏移一起搬迁"
    # 参考原子语义 = 分别与本键的 begin/end 相连（RDKit 前置条件，也是它校验的东西）
    for stereo_atom, terminal in zip(stereo_atoms, (bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())):
        assert mol.GetBondBetweenAtoms(stereo_atom, terminal) is not None
    # 立体标记必须整条落在同一个组分窗口内（原子序号偏移没串到别的碎片上）
    bounds: list[tuple[int, int]] = []
    offset = 0
    for component_mol, _conf_id in components:
        bounds.append((offset, offset + component_mol.GetNumAtoms()))
        offset += component_mol.GetNumAtoms()
    window = next(w for w in bounds if w[0] <= bond.GetBeginAtomIdx() < w[1])
    assert all(
        window[0] <= idx < window[1]
        for idx in [bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), *stereo_atoms]
    )


# ---------------------------------------------------------------------------
# 收敛门禁：力场优化未收敛的放置绝不交付为复合物候选
# ---------------------------------------------------------------------------


def test_unconverged_placements_are_never_delivered(tmp_path, monkeypatch):
    """弛豫未收敛 (code != 0)：必须丢弃，全部未收敛时报 no_candidate，绝不交付 status='ok'。"""

    def _unconverged(mol, conf_id, writer, parameters, **_kwargs):
        conf = mol.GetConformer(conf_id)
        writer.append(
            0,
            [[float(v) for v in conf.GetAtomPosition(i)] for i in range(mol.GetNumAtoms())],
            0.0, None,
        )
        return False, False, ""  # converged=False

    result = _two_component_complex(tmp_path, monkeypatch, _unconverged)
    assert result.status == "no_candidate"
    assert result.candidates == []
    assert result.unconverged_after_relaxation > 0
    assert "did not converge" in result.message
    assert any("did not converge" in d for d in result.diagnostics)


def test_mixed_convergence_delivers_only_converged_candidates(tmp_path, monkeypatch):
    """部分放置收敛、部分未收敛：只有收敛的进入候选，未收敛的被丢弃。"""
    call_count = 0

    def _mixed(mol, conf_id, writer, parameters, **_kwargs):
        nonlocal call_count
        call_count += 1
        conf = mol.GetConformer(conf_id)
        writer.append(
            0,
            [[float(v) for v in conf.GetAtomPosition(i)] for i in range(mol.GetNumAtoms())],
            0.0, None,
        )
        # 偶数次调用收敛，奇数次未收敛
        converged = (call_count % 2 == 0)
        return converged, False, ""

    result = _two_component_complex(tmp_path, monkeypatch, _mixed)
    assert result.status == "ok"
    assert len(result.candidates) > 0
    assert result.unconverged_after_relaxation > 0
    assert any("relaxation did not converge" in d for d in result.diagnostics)


def test_unconstrained_relaxation_failure_is_caught(tmp_path, monkeypatch):
    """反应模式第二阶段无约束弛豫未收敛时，必须识别为未收敛并丢弃。"""

    class FakeFF:
        def __init__(self, should_fail: bool):
            self._should_fail = should_fail

        def MMFFAddDistanceConstraint(self, *args, **kwargs):
            pass

        def Initialize(self):
            pass

        def CalcEnergy(self):
            return 10.0

        def CalcGrad(self):
            return [0.01, 0.01]

        def Minimize(self, maxIts=2000):
            return 1 if self._should_fail else 0

    ff_calls = 0

    def _fake_make_ff(mol, conf_id):
        nonlocal ff_calls
        ff_calls += 1
        # 阶段 1 成功 (1, 3, 5...)，阶段 2 (无约束) 失败 (2, 4, 6...)
        return FakeFF(should_fail=(ff_calls % 2 == 0))

    monkeypatch.setattr(assembly_mod, "_mmff_force_field", _fake_make_ff)
    components = [(_embedded_mol("O"), 0), (_embedded_mol("C"), 0)]
    monkeypatch.setattr(assembly_mod, "_distance", lambda *a: 2.0)
    result = assemble(
        components=components, output_dir=str(tmp_path),
        reaction_center=[(0, 1)],
    )
    assert result.status == "no_candidate"
    assert result.unconverged_after_relaxation > 0
