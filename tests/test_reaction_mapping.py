"""reaction_mapping：反应图映射、键变化与具体原子序绑定。"""

import pytest

pytest.importorskip("rdkit")

from rdkit import Chem
from rdkit.Chem import AllChem

from cloudra.tools.Chemtool.reaction_mapping import (
    ReactionMapping,
    ReactionMapping_input_schema,
    analyze_reaction_mapping,
)
from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema


def _write_mol(path, smiles: str, add_hs: bool = True):
    mol = Chem.MolFromSmiles(smiles)
    if add_hs:
        mol = Chem.AddHs(mol)
    AllChem.Compute2DCoords(mol)
    path.write_text(Chem.MolToMolBlock(mol), encoding="utf-8")


def _write_renumbered_mol(path, smiles: str, heavy_order: list[int]):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.Compute2DCoords(mol)
    hydrogen_indices = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 1]
    renumbered = Chem.RenumberAtoms(mol, heavy_order + hydrogen_indices)
    path.write_text(Chem.MolToMolBlock(renumbered), encoding="utf-8")


def test_identity_mapping_has_no_bond_edits():
    """防止恒等反应被臆造反应中心或非恒等原子排列。"""
    result = analyze_reaction_mapping("CCO", "CCO")

    assert result["mapping_status"] == "unique"
    assert result["heavy_atom_map"] == [1, 2, 3]
    assert result["formed_bonds"] == []
    assert result["broken_bonds"] == []
    assert result["order_changes"] == []
    assert result["watch_pairs"] == []


def test_complete_atom_map_labels_are_authoritative():
    """防止对称分子忽略用户明确给出的 atom-map 标签而擅自换序。"""
    result = analyze_reaction_mapping(
        "[CH3:1][CH3:2]",
        "[CH3:2][CH3:1]",
    )

    assert result["mapping_status"] == "unique"
    assert result["heavy_atom_map"] == [2, 1]
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["source"] == "atom_map_labels"


@pytest.mark.parametrize('use_labels', [False, True])
def test_declared_binding_is_not_limited_by_symmetric_match_enumeration(use_labels):
    from cloudra.tools.Chemtool.reaction_mapping import _identity_and_binding

    smiles = 'C(C(C)(C)C)(C(C)(C)C)(C(C)(C)C)C(C)(C)C'
    expected = Chem.MolFromSmiles(smiles)
    automorphisms = expected.GetSubstructMatches(expected, uniquify=False, maxMatches=257)
    assert len(automorphisms) == 257
    binding = list(automorphisms[-1])
    structure = Chem.AddHs(expected)
    if use_labels:
        for index, target in enumerate(binding):
            expected.GetAtomWithIdx(index).SetAtomMapNum(index + 1)
            structure.GetAtomWithIdx(target).SetAtomMapNum(index + 1)
        smiles = Chem.MolToSmiles(expected, canonical=False)
    identity, actual, diagnostic = _identity_and_binding(
        smiles, structure, None if use_labels else binding)
    assert identity == 'match'
    assert actual == binding, diagnostic


def test_complete_atom_map_labels_cannot_cross_elements():
    with pytest.raises(ValueError, match="element|isotope"):
        analyze_reaction_mapping(
            "[CH3:1][OH:2]",
            "[OH:1][CH3:2]",
        )


def test_stereochemical_inversion_is_exposed_in_candidate_score():
    retained = analyze_reaction_mapping("F[C@](Cl)(Br)I", "F[C@](Cl)(Br)I")
    inverted = analyze_reaction_mapping("F[C@](Cl)(Br)I", "F[C@@](Cl)(Br)I")

    assert retained["candidates"][0]["stereo_mismatch"] == 0
    assert inverted["candidates"][0]["stereo_mismatch"] >= 1
    assert inverted["candidates"][0]["score"] > retained["candidates"][0]["score"]


def test_symmetric_automorphism_mirrors_merge_into_one_candidate():
    """对称分子的自同构镜像（编辑事实与 score 完全一致）必须合并成一个候选——
    镜像不是独立的化学候选，不应制造假 ambiguous、也不应挤占候选窗口。"""
    result = analyze_reaction_mapping("CC", "CC")

    assert result["mapping_status"] == "unique"
    assert len(result["candidates"]) == 1
    assert result["heavy_atom_map"] == [1, 2]
    assert result["formed_bonds"] == []
    assert result["broken_bonds"] == []


def test_high_symmetry_identity_collapses_to_single_edit_fact_candidate():
    """苯→苯有 6! 个碳排列映射：所有零编辑的自同构镜像必须合并成恰好一个
    score=0 候选（不再挤占窗口、不制造假 ambiguous）；编辑事实真正不同的
    非极小映射仍是独立候选，但不影响顶层唯一性判定。"""
    result = analyze_reaction_mapping("c1ccccc1", "c1ccccc1")

    assert result["mapping_status"] == "unique"
    zero_edit = [c for c in result["candidates"] if c["bond_edit_count"] == 0]
    assert len(zero_edit) == 1
    assert zero_edit[0]["score"] == 0.0
    assert zero_edit[0]["heavy_atom_map"] == [1, 2, 3, 4, 5, 6]


def test_claisen_mapping_reports_pericyclic_bond_changes():
    """防止两个 SMILES 的映射歧义被静默折叠；agent 可再选择 [3,3] 候选。"""
    initial = analyze_reaction_mapping("C=COCC=C", "C=CCCC=O")

    assert initial["mapping_status"] == "ambiguous"
    maps = [candidate["heavy_atom_map"] for candidate in initial["candidates"]]
    assert [4, 5, 6, 1, 2, 3] in maps
    assert [6, 5, 4, 1, 2, 3] in maps

    claisen_index = maps.index([4, 5, 6, 1, 2, 3])
    result = analyze_reaction_mapping(
        "C=COCC=C", "C=CCCC=O", selected_candidate=claisen_index,
    )
    assert result["heavy_atom_map"] == [4, 5, 6, 1, 2, 3]
    assert result["formed_bonds"] == [[1, 6]]
    assert result["broken_bonds"] == [[3, 4]]
    assert result["order_changes"] == [
        {"atoms": [1, 2], "reactant_order": 2.0, "product_order": 1.0},
        {"atoms": [2, 3], "reactant_order": 1.0, "product_order": 2.0},
        {"atoms": [4, 5], "reactant_order": 1.0, "product_order": 2.0},
        {"atoms": [5, 6], "reactant_order": 2.0, "product_order": 1.0},
    ]
    assert result["watch_pairs"] == [[1, 6], [3, 4]]


def test_unbalanced_reaction_is_operational_failure():
    """防止元素数不守恒时仍返回长度不合法的 ts_guess atom_map。"""
    with pytest.raises(ValueError, match="element counts"):
        analyze_reaction_mapping("CC", "CCC")


def test_ts_mapping_automatically_adopts_ranked_complete_symmetric_binding():
    from cloudra.tools.Chemtool.reaction_mapping import bind_reaction_structures
    from cloudra.tools.core.ts_inputs import TsInput

    declaration = TsInput(reaction={
        'reactant_smiles': 'CC', 'product_smiles': 'CC', 'charge': 0, 'multiplicity': 1,
    })
    reactant = Chem.AddHs(Chem.MolFromSmiles('CC'))
    product = Chem.AddHs(Chem.MolFromSmiles('CC'))

    result = bind_reaction_structures(declaration, reactant, product)
    repeated = bind_reaction_structures(declaration, reactant, product)

    assert result['mapping_status'] == 'ambiguous'
    assert result['binding_status'] == 'complete'
    assert result['atom_map'] == result['candidates'][0]['atom_map']
    assert repeated['atom_map'] == result['atom_map']
    assert sorted(result['atom_map']) == list(range(1, reactant.GetNumAtoms() + 1))
    assert 'Automatically selected' in result['message']


def test_ts_mapping_explicit_candidate_overrides_automatic_selection():
    from cloudra.tools.Chemtool.reaction_mapping import bind_reaction_structures
    from cloudra.tools.core.ts_inputs import TsInput

    declaration = TsInput(reaction={
        'reactant_smiles': 'CC', 'product_smiles': 'CC', 'charge': 0, 'multiplicity': 1,
    })
    reactant = Chem.AddHs(Chem.MolFromSmiles('CC'))
    product = Chem.AddHs(Chem.MolFromSmiles('CC'))
    automatic = bind_reaction_structures(declaration, reactant, product)
    selected = len(automatic['candidates']) - 1
    assert selected > 0
    declaration.reaction.selected_candidate = selected

    result = bind_reaction_structures(declaration, reactant, product)

    assert result['binding_status'] == 'complete'
    assert result['atom_map'] == automatic['candidates'][selected]['atom_map']
    assert result['atom_map'] != automatic['atom_map']


@pytest.mark.asyncio
async def test_tool_returns_advisory_mapping_result(mock_session):
    """工具边界应保留 ambiguous，而不是把顶层候选改写成 pass。"""
    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="C=COCC=C",
            product_smiles="C=CCCC=O",
        ),
        mock_session,
    )

    assert result.is_success is True
    assert result.mapping_status == "ambiguous"
    assert any(c["heavy_atom_map"] == [4, 5, 6, 1, 2, 3] for c in result.candidates)
    assert result.binding_status == 'complete'
    assert result.atom_map == result.candidates[0]['atom_map']


@pytest.mark.asyncio
async def test_tool_reports_malformed_or_unbalanced_input_as_operational_failure(mock_session):
    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(reactant_smiles="CC", product_smiles="CCC"),
        mock_session,
    )

    assert result.is_success is False
    assert result.mapping_status == "inconclusive"
    assert "element counts" in result.message


@pytest.mark.asyncio
async def test_concrete_mol_files_expand_claisen_full_atom_map(tmp_path, mock_session):
    """防止只映重原子，导致显式氢 XYZ 无法传给 ts_guess.interpolate。"""
    reactant = tmp_path / "allyl_vinyl_ether.mol"
    product = tmp_path / "pentenal.mol"
    _write_mol(reactant, "C=COCC=C")
    _write_mol(product, "C=CCCC=O")

    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="[CH2:1]=[CH:2][O:3][CH2:4][CH:5]=[CH2:6]",
            product_smiles="[CH2:4]=[CH:5][CH2:6][CH2:1][CH:2]=[O:3]",
            reactant_path=str(reactant),
            product_path=str(product),
        ),
        mock_session,
    )

    assert result.is_success is True
    assert result.mapping_status == "unique"
    assert result.reactant_identity == "match"
    assert result.product_identity == "match"
    assert result.binding_status == "complete"
    assert result.atom_map == [4, 5, 6, 1, 2, 3, 10, 11, 12, 13, 14, 7, 8, 9]


@pytest.mark.asyncio
async def test_claisen_full_map_round_trips_into_ts_guess_interpolate(tmp_path, mock_session):
    """真实的显式氢/异序端点必须能直接沿 mapping 进入插值，不靠手工重排 XYZ。"""
    reactant = tmp_path / "allyl_vinyl_ether.mol"
    product = tmp_path / "pentenal.mol"
    _write_mol(reactant, "[CH2:1]=[CH:2][O:3][CH2:4][CH:5]=[CH2:6]")
    _write_mol(product, "[CH2:4]=[CH:5][CH2:6][CH2:1][CH:2]=[O:3]")

    mapping = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="[CH2:1]=[CH:2][O:3][CH2:4][CH:5]=[CH2:6]",
            product_smiles="[CH2:4]=[CH:5][CH2:6][CH2:1][CH:2]=[O:3]",
            reactant_path=str(reactant),
            product_path=str(product),
        ),
        mock_session,
    )
    reactant_mol = Chem.MolFromMolFile(str(reactant), removeHs=False)
    product_mol = Chem.MolFromMolFile(str(product), removeHs=False)
    assert reactant_mol is not None and product_mol is not None

    interpolated = await TsGuess().safe_call(
        TsGuess_input_schema(
            mode="interpolate",
            reactant_path=str(reactant),
            product_path=str(product),
            watch_pairs=mapping.watch_pairs,
            n_images=5,
            interp_method="linear",
            output_dir=str(tmp_path / "claisen_images"),
        ),
        mock_session,
    )

    assert mapping.binding_status == "complete"
    assert interpolated.is_success is True
    assert len(list((tmp_path / "claisen_images").glob("img_*.xyz"))) == 5
    assert "C1-C6" in interpolated.distance_table
    assert "O3-C4" in interpolated.distance_table


@pytest.mark.asyncio
async def test_claisen_xyz_binding_preserves_concrete_atom_order(tmp_path, mock_session):
    """MOL 转成 XYZ 后，reaction_mapping 仍应按 XYZ 的显式原子顺序给出同一全映射。"""
    reactant = tmp_path / "allyl_vinyl_ether.mol"
    product = tmp_path / "pentenal.mol"
    _write_mol(reactant, "C=COCC=C")
    _write_mol(product, "C=CCCC=O")
    reactant_mol = Chem.MolFromMolFile(str(reactant), removeHs=False)
    product_mol = Chem.MolFromMolFile(str(product), removeHs=False)
    assert reactant_mol is not None and product_mol is not None

    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="[CH2:1]=[CH:2][O:3][CH2:4][CH:5]=[CH2:6]",
            product_smiles="[CH2:4]=[CH:5][CH2:6][CH2:1][CH:2]=[O:3]",
            reactant_text=Chem.MolToXYZBlock(reactant_mol),
            reactant_format="xyz",
            product_text=Chem.MolToXYZBlock(product_mol),
            product_format="xyz",
        ),
        mock_session,
    )

    assert result.binding_status == "complete"
    assert result.atom_map == [4, 5, 6, 1, 2, 3, 10, 11, 12, 13, 14, 7, 8, 9]


@pytest.mark.asyncio
async def test_concrete_watch_pairs_follow_renumbered_reactant_coordinates(tmp_path, mock_session):
    reactant = tmp_path / "reactant_renumbered.mol"
    product = tmp_path / "product_renumbered.mol"
    _write_renumbered_mol(reactant, "C=COCC=C", [2, 0, 1, 5, 4, 3])
    _write_renumbered_mol(product, "C=CCCC=O", [5, 3, 0, 1, 2, 4])

    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="[CH2:1]=[CH:2][O:3][CH2:4][CH:5]=[CH2:6]",
            product_smiles="[CH2:4]=[CH:5][CH2:6][CH2:1][CH:2]=[O:3]",
            reactant_path=str(reactant),
            product_path=str(product),
        ),
        mock_session,
    )

    assert result.binding_status == "complete"
    assert result.graph_watch_pairs == [[1, 6], [3, 4]]
    assert result.watch_pairs == [[1, 6], [2, 4]]
    assert result.concrete_watch_pairs == result.watch_pairs


@pytest.mark.asyncio
async def test_symmetric_concrete_embedding_uses_ranked_mapping_without_manual_labels(tmp_path, mock_session):
    reactant = tmp_path / "ethane_r.mol"
    product = tmp_path / "ethane_p.mol"
    _write_mol(reactant, "CC")
    _write_mol(product, "CC")

    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="[CH3:1][CH3:2]",
            product_smiles="[CH3:1][CH3:2]",
            reactant_path=str(reactant),
            product_path=str(product),
        ),
        mock_session,
    )

    assert result.reactant_identity == result.product_identity == "match"
    assert result.binding_status == "complete"
    assert result.atom_map == result.candidates[0]['atom_map']
    assert result.mapping_status == 'ambiguous'
    assert any("symmetric" in item or "not unique" in item for item in result.binding_diagnostics)


@pytest.mark.asyncio
async def test_smiles_only_can_emit_safe_internal_explicit_hydrogen_map(mock_session):
    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="[CH3:1][CH2:2][OH:3]",
            product_smiles="[CH3:1][CH2:2][OH:3]",
        ),
        mock_session,
    )

    assert result.binding_status == "complete"
    assert result.binding_source == "internal_generated"
    assert result.atom_map == list(range(1, 10))


@pytest.mark.asyncio
async def test_structure_identity_mismatch_does_not_emit_full_map(tmp_path, mock_session):
    """防止具体端点与声明 SMILES 不同仍生成可执行的全原子映射。"""
    reactant = tmp_path / "ethanol.mol"
    wrong_product = tmp_path / "propanol.mol"
    _write_mol(reactant, "CCO")
    _write_mol(wrong_product, "CCCO")

    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="CCO",
            product_smiles="CCO",
            reactant_path=str(reactant),
            product_path=str(wrong_product),
        ),
        mock_session,
    )

    assert result.is_success is True
    assert result.reactant_identity == "match"
    assert result.product_identity == "mismatch"
    assert result.binding_status == "inconclusive"
    assert result.atom_map == []


@pytest.mark.asyncio
async def test_missing_explicit_hydrogens_is_inconclusive_not_partial_map(tmp_path, mock_session):
    """防止一端缺氢时返回长度看似合法、实际错位的 atom_map。"""
    reactant = tmp_path / "ethanol_h.mol"
    product = tmp_path / "ethanol_heavy_only.mol"
    _write_mol(reactant, "CCO", add_hs=True)
    _write_mol(product, "CCO", add_hs=False)

    result = await ReactionMapping().safe_call(
        ReactionMapping_input_schema(
            reactant_smiles="CCO",
            product_smiles="CCO",
            reactant_path=str(reactant),
            product_path=str(product),
        ),
        mock_session,
    )

    assert result.reactant_identity == "match"
    assert result.product_identity == "match"
    assert result.binding_status == "inconclusive"
    assert result.atom_map == []


def test_potential_axes_sp2_sp2_hindered_biphenyl():
    """受阻联苯应检出潜在轴，对称/自由旋转体系不应检出。"""
    result = analyze_reaction_mapping(
        "Cc1cccc(Cl)c1-c1c(Cl)cccc1",
        "Cc1cccc(Cl)c1-c1c(Cl)cccc1",
    )
    axes = result["potential_axes"]["reactant"]
    assert len(axes) == 1
    assert axes[0]["hybridization"] == ["SP2", "SP2"]
    assert axes[0]["axis_congestion"] >= 9.0


def test_potential_axes_reject_symmetric_and_sp3_sp3():
    """对称联苯与 sp3-sp3 σ键不应报潜在轴（等价端/构象异构）。"""
    for smiles in ("c1ccccc1-c1ccccc1", "Cc1cccc(C)c1-c1c(C)cccc1C", "CCCC"):
        result = analyze_reaction_mapping(smiles, smiles)
        assert result["potential_axes"]["reactant"] == []


def test_potential_axes_sp3_tertiary_carbon_axis():
    """叔碳 sp3-sp2 阻旋轴应检出；CH2 苄基（一端仅一个重取代基）应排除。"""
    result = analyze_reaction_mapping(
        "Cc1cccc(Cl)c1-C(C)c1c(C)cccc1Cl",
        "Cc1cccc(Cl)c1-C(C)c1c(C)cccc1Cl",
    )
    axes = result["potential_axes"]["reactant"]
    assert any("SP3" in ax["hybridization"] for ax in axes)

    benzyl = analyze_reaction_mapping("Cc1ccccc1Cc1ccccc1Cl", "Cc1ccccc1Cc1ccccc1Cl")
    assert benzyl["potential_axes"]["reactant"] == []


def test_potential_axes_literature_aryl_ch_me_biaryl():
    """文献经典阻旋骨架 Ar-CH(Me)-Ar'（Bringmann/Clayden 型邻位双取代）应检出 sp2-sp3 轴。"""
    result = analyze_reaction_mapping(
        "Cc1cccc(Cl)c1C(C)c1c(C)cccc1Cl",
        "Cc1cccc(Cl)c1C(C)c1c(C)cccc1Cl",
    )
    axes = result["potential_axes"]["reactant"]
    sp2_sp3 = [ax for ax in axes if sorted(ax["hybridization"]) == ["SP2", "SP3"]]
    assert sp2_sp3, "Ar-CH(Me)-Ar' scaffold should expose an sp2-sp3 chiral axis"
    for ax in sp2_sp3:
        assert ax["axis_congestion"] >= 9.0
        assert ax["configuration"] == "unspecified"


def test_potential_axes_reject_equivalent_ends():
    """叔丁基三个甲基等价、N-苄基端单取代，都不应误报为轴。"""
    for smiles in (
        "Cc1ccc2ccccc2c1C(C)(C)C",      # 1-tBu-2-Me 萘：叔丁基甲基等价
        "CC(C)(C)c1ccccc1NCc1ccccc1Cl",  # N-苄基-2-叔丁基苯胺：N/苄基端单取代
    ):
        result = analyze_reaction_mapping(smiles, smiles)
        assert result["potential_axes"]["reactant"] == []


def test_axial_stereo_mismatch_counts_atropisomer_flip():
    """sp2-sp2 轴经映射后 atropisomer 构型翻转到对映体应计入 stereo_mismatch。"""
    retained = analyze_reaction_mapping(
        "Cc1cccc(Cl)c1-c1c(Cl)cccc1 |wU:7.6,wU:8.8|",
        "Cc1cccc(Cl)c1-c1c(Cl)cccc1 |wU:7.6,wU:8.8|",
    )
    flipped = analyze_reaction_mapping(
        "Cc1cccc(Cl)c1-c1c(Cl)cccc1 |wU:7.6,wU:8.8|",
        "Cc1cccc(Cl)c1-c1c(Cl)cccc1 |wD:7.6,wD:8.8|",
    )
    assert retained["candidates"][0]["stereo_mismatch"] == 0
    assert flipped["candidates"][0]["stereo_mismatch"] >= 1


def test_tool_is_registered():
    """防止工具实现存在但 agent manifest 永远发现不到它。"""
    from cloudra.tools.registry import TOOL_REGISTRY

    targets = {(item.module, item.class_name) for item in TOOL_REGISTRY}
    assert ("cloudra.tools.Chemtool.reaction_mapping", "ReactionMapping") in targets


# ---------------------------------------------------------------------------
# T8：全原子映射的氢同位素配对（氘代示踪/KIE 场景 D 不得配到 H 上）
# ---------------------------------------------------------------------------


def _methanol_with_deuterium(d_idx: int):
    """CH3OH 显式氢 mol（C0 O1 H2-5；H5 在 O 上），把 idx=d_idx 的氢标成 D。"""
    mol = Chem.AddHs(Chem.MolFromSmiles("CO"))
    mol.GetAtomWithIdx(d_idx).SetIsotope(2)
    return mol


def test_deuterium_pairs_with_deuterium_in_full_atom_map():
    """两端羟基氢都是 D：D 必须配到 D，而不是按排序索引错配到某个甲基 H。"""
    from cloudra.tools.Chemtool.reaction_mapping import _expand_full_atom_maps

    reactant = _methanol_with_deuterium(5)
    product = _methanol_with_deuterium(5)
    atom_maps, diagnostic = _expand_full_atom_maps(
        reactant, product, [0, 1], [0, 1], [1, 2],
    )
    assert atom_maps == [[1, 2, 3, 4, 5, 6]], (atom_maps, diagnostic)
    # D（product idx 5）确实配到了 reactant 的 D（idx 5），不是某个 H
    assert atom_maps[0][5] == 6


def test_transferred_deuterium_keeps_its_isotope_identity():
    """跨中心的 D 必须仍映射到 D；只枚举未局部配对的氢。"""
    from cloudra.tools.Chemtool.reaction_mapping import _expand_full_atom_maps

    reactant = _methanol_with_deuterium(5)   # D 在羟基上
    product = _methanol_with_deuterium(2)    # D 在甲基上
    atom_maps, diagnostic = _expand_full_atom_maps(
        reactant, product, [0, 1], [0, 1], [1, 2],
    )
    assert atom_maps == [[1, 2, 6, 3, 4, 5]]
    assert reactant.GetAtomWithIdx(atom_maps[0][2] - 1).GetIsotope() == product.GetAtomWithIdx(2).GetIsotope() == 2
