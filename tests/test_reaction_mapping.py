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


def test_unlabelled_symmetric_mapping_remains_ambiguous():
    """防止工具把对称原子的等价排列包装成唯一化学事实。"""
    result = analyze_reaction_mapping("CC", "CC")

    assert result["mapping_status"] == "ambiguous"
    maps = {tuple(candidate["heavy_atom_map"]) for candidate in result["candidates"]}
    assert maps == {(1, 2), (2, 1)}


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
    assert "manual" in result.message or "agent" in result.message


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
    _write_mol(reactant, "C=COCC=C")
    _write_mol(product, "C=CCCC=O")

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
            reactant_text=Chem.MolToXYZBlock(reactant_mol),
            product_text=Chem.MolToXYZBlock(product_mol),
            atom_map=mapping.atom_map,
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
async def test_symmetric_concrete_embedding_is_inconclusive_without_labels(tmp_path, mock_session):
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
    assert result.binding_status == "inconclusive"
    assert result.atom_map == []
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


def test_tool_is_registered():
    """防止工具实现存在但 agent manifest 永远发现不到它。"""
    from cloudra.tools.registry import TOOL_REGISTRY

    targets = {(item.module, item.class_name) for item in TOOL_REGISTRY}
    assert ("cloudra.tools.Chemtool.reaction_mapping", "ReactionMapping") in targets
