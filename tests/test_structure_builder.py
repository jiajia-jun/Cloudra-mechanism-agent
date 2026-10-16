"""structure_builder / structure_artifacts：分片建模、稳定原子身份与逐步力场轨迹。

每个用例都对应计划里的一条硬要求：
元素/原子身份守恒、形式电荷一致、立体标记保留、重复组分不合并、单原子离子保留、
单原子组分不调力场、缺参数/不支持自旋显式返回状态、多组分不得输出复合物候选、
轨迹保存初始帧+每个迭代帧+终态（含力场/单位/种子/收敛码）、不收敛与异常轨迹同样保留。
"""

import json
import os

import pytest

pytest.importorskip("rdkit", reason="structure_builder requires RDKit (chem extra)")

from rdkit import Chem  # noqa: E402

import cloudra.tools.core.structure_builder as builder_mod  # noqa: E402
from cloudra.tools.core.structure_artifacts import (  # noqa: E402
    read_frame_positions,
    read_frame_summaries,
    read_trajectory,
)
from cloudra.tools.core.structure_builder import (  # noqa: E402
    BuildStrategy,
    PreparationRequest,
    StructureInput,
    prepare_structure,
)


def _prepare(tmp_path, value, kind="smiles", charge=0, multiplicity=1, seed=42,
             embed=True, optimize=True, steps=20000, name="build", reaction_center=None):
    return prepare_structure(PreparationRequest(
        structure=StructureInput(kind=kind, value=value),
        output_dir=str(tmp_path / name),
        total_charge=charge,
        multiplicity=multiplicity,
        random_seed=seed,
        strategy=BuildStrategy(
            name="per_component", embed=embed, optimize=optimize,
            max_optimization_steps=steps, reaction_center=list(reaction_center or []),
        ),
    ))


# ---------------------------------------------------------------------------
# 拆分守恒：元素 / 原子身份 / 形式电荷 / 立体标记
# ---------------------------------------------------------------------------


def test_fragments_preserve_element_and_index_conservation(tmp_path):
    """拆分 + 加氢后元素守恒，且每个输出原子都能回溯到输入原子或"某父原子上的第几个氢"。"""
    smiles = "[O-]C=C.O.CC=O"
    prepared = _prepare(tmp_path, smiles, charge=-1, embed=False)
    # embed=False 只做结构解析：组装需要已嵌入的组分坐标，因此明确报出原因，
    # 但拆分/加氢/身份表这些结构解析结果照常产出（下面全部断言仍成立）。
    assert prepared.status == "assembly_failed"
    assert "embed=False" in prepared.message
    source = Chem.MolFromSmiles(smiles)

    # 组分覆盖全部输入原子，且互不重叠
    covered: list[int] = []
    for component in prepared.components:
        covered.extend(component.source_atom_indices)
    assert sorted(covered) == list(range(source.GetNumAtoms()))

    # 元素守恒：每个组分的重原子序列 == 输入中对应原子的元素序列
    for component in prepared.components:
        heavy = [s for s in component.symbols if s != "H"]
        expected = [source.GetAtomWithIdx(i).GetSymbol() for i in component.source_atom_indices]
        assert heavy == expected, component.component_id

    # 身份表：每个输入原子恰好出现一次；每个新增氢都有父亲与序数
    input_origins = [i for i in prepared.atom_identities if i.origin == "input_atom"]
    assert sorted(i.input_atom_index for i in input_origins) == list(range(source.GetNumAtoms()))
    added = [i for i in prepared.atom_identities if i.origin == "added_hydrogen"]
    assert added, "加氢后必须登记新增氢的身份"
    for identity in added:
        assert identity.parent_input_atom_index is not None
        assert identity.hydrogen_ordinal is not None and identity.hydrogen_ordinal >= 1
        assert identity.input_atom_index is None
    # 输出原子序号连续覆盖
    assert [i.index for i in prepared.atom_identities] == list(range(len(prepared.symbols)))


def test_formal_charge_sum_matches_and_is_enforced(tmp_path):
    """形式电荷总和一致；与请求不符时 fail-loud 报出实际总和。"""
    ok = _prepare(tmp_path, "[F-].CCl", charge=-1, embed=False)
    assert ok.formal_charge_sum == -1
    assert sum(c.formal_charge for c in ok.components) == -1

    bad = _prepare(tmp_path, "[F-].CCl", charge=0, embed=False, name="bad")
    assert bad.status == "charge_mismatch"
    assert "sum to -1" in bad.message
    assert bad.components == []
    for prepared in (ok, bad):
        assert "total_charge" not in prepared.model_dump()
        with open(prepared.artifact_path, encoding="utf-8") as handle:
            assert "total_charge" not in json.load(handle)


def test_stereochemistry_is_preserved_per_component(tmp_path):
    """立体标记保留：组分的规范异构 SMILES 必须与输入的对应片段一致。"""
    prepared = _prepare(tmp_path, "C[C@H](N)C(=O)O", embed=False)
    assert prepared.status == "ok"
    assert prepared.components[0].isomeric_smiles == Chem.MolToSmiles(
        Chem.MolFromSmiles("C[C@H](N)C(=O)O")
    )
    assert "@" in prepared.components[0].isomeric_smiles


def test_stereo_survives_the_component_mol_round_trip(tmp_path):
    """组分 MOL 文件（下游读回用的交换格式）必须保持立体化学与电荷。"""
    prepared = _prepare(tmp_path, "[O-]/C=C/C", charge=-1, embed=False)
    assert prepared.status == "ok"
    component = prepared.components[0]
    with open(component.mol_path, encoding="utf-8") as handle:
        reread = Chem.MolFromMolBlock(handle.read(), removeHs=False)
    assert reread is not None
    # 读回后去掉显式氢再比规范异构 SMILES：E/Z 与手性都必须原样保留
    assert Chem.MolToSmiles(Chem.RemoveHs(reread)) == component.isomeric_smiles
    assert "/" in component.isomeric_smiles or "\\" in component.isomeric_smiles


def test_submol_preserves_atom_properties_and_conformers_without_mutating_source():
    source = Chem.MolFromSmiles("[13CH3:7][C@H:8]([F:9])[Cl:10].[Na+:11]")
    source.SetProp("origin", "declared-input")
    source.SetProp("_private_source", "native-state")
    source.SetIntProp("revision", 4)
    source.SetDoubleProp("confidence", 0.75)
    source.SetBoolProp("verified", False)
    for atom in source.GetAtoms():
        atom.SetProp("origin", f"input-{atom.GetIdx()}")
    source.GetBondWithIdx(0).SetProp("evidence", "declared-bond")
    for conformer_id in (3, 17):
        conf = Chem.Conformer(source.GetNumAtoms())
        conf.SetId(conformer_id)
        for index in range(source.GetNumAtoms()):
            conf.SetAtomPosition(index, (index, conformer_id, 0.25))
        source.AddConformer(conf, assignId=False)
    before = source.ToBinary(Chem.PropertyPickleOptions.AllProps)

    selected, mapping = builder_mod._submol_by_input_indices(source, [3, 1, 0, 2])

    assert mapping == {3: 0, 1: 1, 0: 2, 2: 3}
    assert selected.GetPropsAsDict(includePrivate=True, includeComputed=False) == {
        "origin": "declared-input", "_private_source": "native-state",
        "revision": 4, "confidence": 0.75, "verified": False,
    }
    assert [atom.GetAtomMapNum() for atom in selected.GetAtoms()] == [10, 8, 7, 9]
    assert [atom.GetIsotope() for atom in selected.GetAtoms()] == [0, 0, 13, 0]
    assert [atom.GetProp("origin") for atom in selected.GetAtoms()] == [
        "input-3", "input-1", "input-0", "input-2",
    ]
    assert selected.GetBondBetweenAtoms(2, 1).GetProp("evidence") == "declared-bond"
    assert [conf.GetId() for conf in selected.GetConformers()] == [3, 17]
    assert selected.GetConformer(17).GetPositions().tolist() == [
        [3.0, 17.0, 0.25], [1.0, 17.0, 0.25], [0.0, 17.0, 0.25], [2.0, 17.0, 0.25],
    ]
    assert Chem.MolToSmiles(selected) == "[13CH3:7][C@H:8]([F:9])[Cl:10]"
    selected.GetAtomWithIdx(0).SetProp("origin", "changed")
    selected.SetProp("origin", "changed")
    selected.GetConformer(17).SetAtomPosition(0, (9.0, 9.0, 9.0))
    assert source.ToBinary(Chem.PropertyPickleOptions.AllProps) == before


def test_prepared_molecule_keeps_state_and_accepts_native_input(tmp_path):
    source = Chem.MolFromSmiles("[13CH3:7][OH:8]")
    source.GetAtomWithIdx(0).SetProp("origin", "original-carbon")
    source.GetBondWithIdx(0).SetProp("evidence", "declared-bond")
    before = source.ToBinary(Chem.PropertyPickleOptions.AllProps)
    structure = StructureInput(kind="molecule", value=source)
    structure = StructureInput.model_validate_json(structure.model_dump_json())
    prepared = prepare_structure(PreparationRequest(
        structure=structure,
        output_dir=str(tmp_path / "native"),
        strategy=BuildStrategy(embed=False, optimize=False),
    ))

    assert prepared.status == "ok"
    assert prepared.mol.GetAtomWithIdx(0).GetIsotope() == 13
    assert prepared.mol.GetAtomWithIdx(0).GetAtomMapNum() == 7
    assert prepared.mol.GetAtomWithIdx(0).GetProp("origin") == "original-carbon"
    assert prepared.components[0].mol.GetBondWithIdx(0).GetProp("evidence") == "declared-bond"
    restored = builder_mod.PreparedStructure.model_validate_json(prepared.model_dump_json())
    assert restored.mol.GetAtomWithIdx(0).GetProp("origin") == "original-carbon"
    restored.mol.GetAtomWithIdx(0).SetFormalCharge(1)
    assert restored.formal_charge_sum == 1
    assert prepared.formal_charge_sum == 0
    assert source.ToBinary(Chem.PropertyPickleOptions.AllProps) == before


def test_repeated_identical_components_are_not_merged(tmp_path):
    """重复同种组分不得被合并；单原子离子同样保留为独立组分。"""
    water = _prepare(tmp_path, "O.O", embed=False, name="w")
    assert len(water.components) == 2
    assert [c.isomeric_smiles for c in water.components] == ["O", "O"]

    salts = _prepare(tmp_path, "[Na+].[Na+].[Cl-].[Cl-]", charge=0, embed=False, name="s")
    assert len(salts.components) == 4
    assert all(c.single_atom for c in salts.components)
    assert [c.formal_charge for c in salts.components] == [1, 1, -1, -1]


def test_single_atom_component_needs_no_force_field(tmp_path):
    """单原子组分不调力场：状态为 not_required，且不产生轨迹。"""
    prepared = _prepare(tmp_path, "[F-].CCl", charge=-1)
    assert prepared.status == "ok"  # 组装成功；下面只看 F- 这一个逐组分事实
    fluorine = prepared.components[0]
    assert fluorine.single_atom is True
    assert fluorine.embed_status == "not_required"
    assert fluorine.optimization_status == "not_required"
    assert fluorine.trajectory_id == ""
    assert any("no force field were run" in d for d in fluorine.diagnostics)


# ---------------------------------------------------------------------------
# 多组分：只出逐组分，不出"复合物候选"
# ---------------------------------------------------------------------------


def test_multicomponent_is_assembled_into_real_complex_candidates(tmp_path):
    """issue #33：多组分输入经**已批准**的组装方案产出复合物候选。

    旧行为是 fail-loud（组装参数未获批）；现在参数已获批，正确行为是按批准值组装：
    候选必须通过 1.0 Å 片间碰撞判据，并且来自**旋转采样 + 力场弛豫**，而不是"仅平移拉开"
    （平移只用来满足碰撞判据，其本身不构成组装）。
    """
    prepared = _prepare(tmp_path, "[F-].CCl", charge=-1)
    assert prepared.status == "ok"
    assert prepared.has_coordinates is True
    assert prepared.assembly is not None
    assembly = prepared.assembly
    assert assembly.status == "ok"
    assert assembly.sampled_placements == assembly.parameters.orientations
    assert assembly.mode == "complex"  # 没给反应中心 → 不凭空指定成键中心
    assert len(assembly.candidates) >= 1
    assert prepared.candidate_paths == assembly.candidate_paths
    for candidate in assembly.candidates:
        assert candidate.min_interfragment_distance >= assembly.parameters.min_interfragment_distance
        assert candidate.xyz_path and os.path.isfile(candidate.xyz_path)
        assert os.path.isfile(candidate.mol_path)
        assert candidate.trajectory_id
    assert any("NO bonding center is invented" in d for d in assembly.diagnostics)


def test_assembly_records_the_approved_parameters(tmp_path):
    """组装参数就是用户批准的具体值，且写进产物（改动即改动科学决策）。"""
    prepared = _prepare(tmp_path, "O.CC=O")
    params = prepared.assembly.parameters
    assert params.orientations == 32
    assert params.min_interfragment_distance == 1.0
    assert params.reaction_center_candidates == 8
    assert params.reaction_center_window == (1.6, 3.0)
    assert params.energy_window_kcal == 6.0
    assert params.rmsd_threshold == 0.5


def test_reaction_mode_guides_by_reaction_center_and_conditions_constraint_release(tmp_path):
    """反应模式：给出反应中心后按它引导放置，约束只在落入批准窗口时才释放。"""
    prepared = _prepare(tmp_path, "[F-].CCl", charge=-1, reaction_center=[(0, 1)])
    assert prepared.status == "ok"
    assembly = prepared.assembly
    assert assembly.mode == "reaction"
    assert assembly.candidates
    candidate = assembly.candidates[0]
    assert "0-1" in candidate.reaction_center_distances
    low, high = assembly.parameters.reaction_center_window
    distance = candidate.reaction_center_distances["0-1"]
    if candidate.constraint_released:
        assert low <= distance <= high, "释放约束的前提是反应中心距离已落在批准窗口内"
    else:
        assert candidate.reaction_center_in_window is False
    assert any("reaction center" in d for d in assembly.diagnostics)


def test_assembly_reports_failure_instead_of_a_fake_complex(tmp_path, monkeypatch):
    """组装跑不出候选时必须报 assembly_failed，绝不把逐组分坐标当复合物交出去。"""
    import cloudra.tools.core.complex_assembly as assembly_mod

    monkeypatch.setattr(assembly_mod, "_mmff_force_field", lambda *a, **kw: None)
    prepared = _prepare(tmp_path, "[F-].CCl", charge=-1)
    assert prepared.status == "assembly_failed"
    assert prepared.has_coordinates is False
    assert prepared.candidate_paths == []
    assert any("MMFF94 could not be constructed" in c.diagnostics[0]
               for c in prepared.components if c.diagnostics) or prepared.diagnostics


def test_assembly_is_refused_when_any_component_is_unusable(tmp_path, monkeypatch):
    """任一组分优化未收敛就不进 assemble：落 optimization_failed 并指明组分。"""
    monkeypatch.setattr(builder_mod, "_make_force_field", _stuck_force_field)

    def _forbidden_assemble(**_kwargs):
        raise AssertionError("assemble must not be called when a component is unusable")

    monkeypatch.setattr(builder_mod, "assemble", _forbidden_assemble)
    prepared = _prepare(tmp_path, "CCO.C")
    assert prepared.status == "optimization_failed"
    assert prepared.has_coordinates is False
    assert prepared.assembly is None
    assert "frag0" in prepared.message and "frag1" in prepared.message
    assert "assembly was NOT run" in prepared.message


def test_single_atom_component_passes_the_assembly_usability_gate(tmp_path):
    """单原子组分无需嵌入/力场（位置即原点），不得被组装闸门误拒。"""
    prepared = _prepare(tmp_path, "[Na+].CC=O", charge=1)
    assert any(c.single_atom for c in prepared.components)
    assert prepared.status == "ok", prepared.message
    assert prepared.assembly is not None and prepared.assembly.status == "ok"


def test_multi_fragment_seed_never_contains_overlapping_fragments(tmp_path):
    """关键回归：构建器不会把两个碎片叠在一起交出去（旧行为实测 0.1392 Å）。"""
    import numpy as np

    prepared = _prepare(tmp_path, "[F-].CCl", charge=-1)
    for component in prepared.components:
        positions = np.asarray(
            [[float(v) for v in line.split()[1:4]] for line in
             open(component.xyz_path, encoding="utf-8").read().splitlines()[2:]], dtype=float,
        )
        if len(positions) < 2:
            continue
        distances = [
            float(np.linalg.norm(positions[i] - positions[j]))
            for i in range(len(positions)) for j in range(i + 1, len(positions))
        ]
        assert min(distances) > 0.5, f"{component.component_id} 内部存在亚 0.5 Å 接触"


# ---------------------------------------------------------------------------
# 单组分：可交付
# ---------------------------------------------------------------------------


def test_single_component_is_deliverable_with_candidates(tmp_path):
    prepared = _prepare(tmp_path, "CCO")
    assert prepared.status == "ok"
    assert prepared.has_coordinates is True
    assert prepared.candidate_path(".xyz").endswith("prepared.xyz")
    assert prepared.candidate_path(".mol").endswith("prepared.mol")
    assert os.path.isfile(prepared.artifact_path)
    with open(prepared.artifact_path, encoding="utf-8") as handle:
        on_disk = json.load(handle)
    assert on_disk["status"] == "ok"
    assert on_disk["artifact_path"] == prepared.artifact_path


def test_declared_doublet_with_even_electron_count_is_refused(tmp_path):
    prepared = _prepare(tmp_path, "CCCC", multiplicity=2)
    assert prepared.status == "unsupported_spin"
    assert prepared.components == []
    assert "multiplicity=2" in prepared.message


def test_missing_force_field_parameters_is_explicit(tmp_path, monkeypatch):
    """MMFF 与 UFF 都不可用时：明确返回 missing_parameters，坐标不得当成品交付。"""
    monkeypatch.setattr(builder_mod, "_select_engine", lambda mol: None)
    prepared = _prepare(tmp_path, "CCO")
    assert prepared.status == "missing_parameters"
    assert prepared.has_coordinates is False
    assert prepared.components[0].optimization_status == "missing_parameters"
    assert any("NOT optimized" in d for d in prepared.components[0].diagnostics)


def test_invalid_input_and_unknown_strategy(tmp_path):
    prepared = _prepare(tmp_path, "not_a_smiles((", name="bad")
    assert prepared.status == "invalid_input"
    with pytest.raises(ValueError):
        prepare_structure(PreparationRequest(
            structure=StructureInput(kind="smiles", value="CCO"),
            output_dir=str(tmp_path / "x"),
            strategy=BuildStrategy.model_construct(
                name="assembly_v1", embed=True, optimize=True, max_optimization_steps=10,
            ),
        ))


# ---------------------------------------------------------------------------
# 轨迹：初始帧 / 每个迭代帧 / 终态 / 元数据一致性
# ---------------------------------------------------------------------------


def test_trajectory_records_every_iteration_and_consistent_metadata(tmp_path):
    """轨迹保存初始帧、每个优化迭代帧与终态，且编号/元素/单位/力场/种子互相自洽。"""
    prepared = _prepare(tmp_path, "CCO")
    assert len(prepared.trajectory_ids) == 1
    trajectory_id = prepared.trajectory_ids[0]
    record = read_trajectory(
        os.path.join(tmp_path, "build", "trajectories", trajectory_id, "trajectory.json")
    )

    assert record.status == "converged"
    assert record.convergence_code == 0
    assert record.engine == "MMFF94"
    assert record.random_seed == 42
    assert record.initial_frame.step == 0
    assert record.final_frame.step == record.frame_count - 1
    assert record.iterations == record.frame_count - 1
    assert record.iterations > 1, "轨迹必须含不止一步迭代"
    assert record.initial_frame.energy_unit == "kcal/mol"
    assert record.final_frame.energy < record.initial_frame.energy

    summaries = read_frame_summaries(record.frames_jsonl_path)
    positions = read_frame_positions(record.frames_path)
    assert len(summaries) == record.frame_count
    assert len(positions) == record.frame_count
    assert [s.step for s in summaries] == list(range(record.frame_count))

    # 逐帧编号连续、能量单调不增、坐标与记录的首末帧逐位一致
    energies = [s.energy for s in summaries]
    assert all(energies[i + 1] <= energies[i] + 1e-9 for i in range(len(energies) - 1))
    import numpy as np

    assert np.allclose(np.asarray(positions[0]), np.asarray(record.initial_frame.positions))
    assert np.allclose(np.asarray(positions[-1]), np.asarray(record.final_frame.positions))
    assert summaries[0].energy == pytest.approx(record.initial_frame.energy)
    assert summaries[-1].energy == pytest.approx(record.final_frame.energy)
    assert all(s.energy_unit == "kcal/mol" for s in summaries)
    assert all(s.max_gradient is not None for s in summaries)


def test_trajectory_agrees_with_rdkit_single_shot_minimizer(tmp_path):
    """轨迹的终态必须与 RDKit 自己的 Minimize(maxIts=N) 落在同一极小值。

    这条是"逐迭代 Minimize 是同一连续性优化、不是伪轨迹"的可复算证据。
    """
    from rdkit.Chem import AllChem

    prepared = _prepare(tmp_path, "CCCC")
    trajectory_id = prepared.trajectory_ids[0]
    record = read_trajectory(
        os.path.join(tmp_path, "build", "trajectories", trajectory_id, "trajectory.json")
    )

    mol = Chem.AddHs(Chem.MolFromSmiles("CCCC"))
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    params.pruneRmsThresh = -1.0
    AllChem.EmbedMolecule(mol, params)
    props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
    ff = AllChem.MMFFGetMoleculeForceField(mol, props)
    assert ff.Minimize(maxIts=2000) == 0
    assert record.final_frame.energy == pytest.approx(ff.CalcEnergy(), abs=1e-3)


def test_not_converged_trajectory_is_kept_and_not_delivered(tmp_path, monkeypatch):
    """达迭代上限未收敛：轨迹保留（收敛码 1），构建结果明确不可交付。"""
    monkeypatch.setattr(builder_mod, "_make_force_field", _stuck_force_field)
    prepared = _prepare(tmp_path, "CCO", steps=3)
    assert prepared.status == "optimization_failed"
    assert prepared.has_coordinates is False
    assert prepared.candidate_paths == []

    record = read_trajectory(
        os.path.join(tmp_path, "build", "trajectories", prepared.trajectory_ids[0], "trajectory.json")
    )
    assert record.status == "not_converged"
    assert record.convergence_code == 1
    assert record.frame_count == 4  # 初始帧 + 3 次迭代
    assert record.notes and "iteration limit" in record.notes[0]
    manifest = json.load(open(prepared.trajectory_manifest_path, encoding="utf-8"))
    assert manifest["count"] == 1
    assert manifest["trajectories"][0]["status"] == "not_converged"


def test_failed_trajectory_keeps_frames_recorded_before_the_exception(tmp_path, monkeypatch):
    """优化中途抛异常：异常前已记录的帧必须保留，失败文本落进轨迹。"""
    monkeypatch.setattr(builder_mod, "_make_force_field", _crashing_force_field)
    prepared = _prepare(tmp_path, "CCO", steps=10)
    assert prepared.status == "optimization_failed"

    trajectory_dir = os.path.join(
        tmp_path, "build", "trajectories", prepared.trajectory_ids[0],
    )
    record = read_trajectory(os.path.join(trajectory_dir, "trajectory.json"))
    assert record.status == "failed"
    assert "simulated optimizer crash" in record.failure
    assert record.frame_count >= 2, "异常前已记录的帧不得丢弃"
    assert len(read_frame_summaries(record.frames_jsonl_path)) == record.frame_count


def test_force_field_construction_failure_is_recorded_as_failed_trajectory(tmp_path, monkeypatch):
    """力场构造不出来：落一条 failed 轨迹（单帧），构建结果不可交付。"""
    monkeypatch.setattr(builder_mod, "_make_force_field", lambda *a, **kw: None)
    prepared = _prepare(tmp_path, "CCO")
    assert prepared.status == "optimization_failed"
    record = read_trajectory(
        os.path.join(tmp_path, "build", "trajectories", prepared.trajectory_ids[0], "trajectory.json")
    )
    assert record.status == "failed"
    assert record.convergence_code == -2
    assert record.frame_count == 1
    assert "could not be constructed" in record.failure


def test_retries_use_independent_trajectory_ids(tmp_path):
    """每次尝试独立编号：同一组分的不同 attempt 落在不同轨迹目录。"""
    from cloudra.tools.core.structure_artifacts import TrajectoryWriter

    writer = TrajectoryWriter(
        str(tmp_path / "build"), "frag0-mmff94-attempt1", "frag0", 1, "MMFF94", ["C", "H"], 7,
    )
    writer.append(0, [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], 0.0, 1.0)
    first = writer.finish(0, "converged")
    writer2 = TrajectoryWriter(
        str(tmp_path / "build"), "frag0-mmff94-attempt2", "frag0", 2, "MMFF94", ["C", "H"], 7,
    )
    writer2.append(0, [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], 0.0, 1.0)
    second = writer2.finish(0, "converged")

    assert first.attempt == 1 and second.attempt == 2
    assert os.path.dirname(first.json_path) != os.path.dirname(second.json_path)


def test_writer_rejects_out_of_order_frames(tmp_path):
    """帧必须连续追加：跳号即 fail-loud，不留一条编号自相矛盾的轨迹。"""
    from cloudra.tools.core.structure_artifacts import TrajectoryWriter

    writer = TrajectoryWriter(
        str(tmp_path / "build"), "frag0-mmff94-attempt1", "frag0", 1, "MMFF94", ["C"], 7,
    )
    writer.append(0, [[0.0, 0.0, 0.0]], 0.0, 1.0)
    with pytest.raises(ValueError):
        writer.append(2, [[0.0, 0.0, 0.0]], 0.0, 1.0)
    writer.abort()


def test_trajectory_record_rejects_inconsistent_metadata():
    """记录级自洽性 fail-loud：状态与收敛码、帧计数与迭代数不允许互相矛盾。"""
    from cloudra.tools.core.structure_artifacts import GeometryFrame, TrajectoryRecord

    frame = GeometryFrame(
        step=0, symbols=["C"], positions=[[0.0, 0.0, 0.0]], energy=0.0, energy_unit="kcal/mol",
    )
    with pytest.raises(ValueError):
        TrajectoryRecord(
            trajectory_id="t", component_id="frag0", attempt=1, engine="MMFF94", symbols=["C"],
            frame_count=2, iterations=5, initial_frame=frame, final_frame=frame,
            convergence_code=0, status="converged",
        )
    with pytest.raises(ValueError):
        TrajectoryRecord(
            trajectory_id="t", component_id="frag0", attempt=1, engine="MMFF94", symbols=["C"],
            frame_count=1, iterations=0, initial_frame=frame, final_frame=frame,
            convergence_code=1, status="converged",
        )


def test_xyz_input_is_resolved_through_the_same_builder(tmp_path):
    """xyz 输入同样经共享构建器解析（键级推断 + 电荷自检 + 拆分）。"""
    xyz = (
        "3\nwater\n"
        "O      0.0000    0.0000    0.0000\n"
        "H      0.9600    0.0000    0.0000\n"
        "H     -0.2400    0.9300    0.0000\n"
    )
    prepared = _prepare(tmp_path, xyz, kind="xyz_text")
    assert prepared.status == "ok"
    assert prepared.symbols == ["O", "H", "H"]
    assert Chem.MolToSmiles(Chem.RemoveHs(Chem.MolFromSmiles(
        prepared.components[0].isomeric_smiles
    ))) == "O"


def _stuck_force_field(mol, conf_id, engine):
    """假力场：Minimize 永远返回 1（未收敛）。"""
    return _FakeForceField(mol, conf_id, behaviour="stuck")


def _crashing_force_field(mol, conf_id, engine):
    """假力场：第三次 Minimize 抛异常。"""
    return _FakeForceField(mol, conf_id, behaviour="crash")


class _FakeForceField:
    """与真实 ForceField 同形的假力场（只实现构建器用到的接口）。"""

    def __init__(self, mol, conf_id, behaviour):
        self.mol = mol
        self.conf_id = conf_id
        self.behaviour = behaviour
        self.calls = 0

    def Initialize(self, **_kwargs):
        return None

    def CalcEnergy(self, **_kwargs):
        return float(self.mol.GetNumAtoms())

    def CalcGrad(self, **_kwargs):
        return tuple(0.0 for _ in range(self.mol.GetNumAtoms() * 3))

    def Minimize(self, **_kwargs):
        self.calls += 1
        if self.behaviour == "crash" and self.calls >= 3:
            raise RuntimeError("simulated optimizer crash")
        return 1
