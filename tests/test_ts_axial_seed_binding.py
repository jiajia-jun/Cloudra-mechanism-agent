"""A declared axis is graph identity; coarse coordinates wait for optimization."""

from pathlib import Path

import pytest

from cloudra.tools.Chemtool.reaction_mapping import ReactionMapping_input_schema, check_concrete_binding
from cloudra.tools.core import ts_process
from cloudra.tools.core.ts_inputs import EndpointSeed, FileConformer
from tests.test_ts_stage_inputs import record_fixture


def test_axial_seed_can_enter_ts_optimization_without_relaxing_final_identity(tmp_path):
    Chem = pytest.importorskip("rdkit.Chem")
    AllChem = pytest.importorskip("rdkit.Chem.AllChem")
    from cloudra.tools.Chemtool.reaction_mapping import _axis_config_consistency

    smiles = "Cc1cccc(Cl)c1-c1c(Cl)cccc1 |wU:7.6,wU:8.8|"
    declared = Chem.MolFromSmiles(smiles)
    embedded = Chem.AddHs(declared)
    assert AllChem.EmbedMolecule(embedded, randomSeed=11) == 0
    indices = [atom.GetIdx() for atom in embedded.GetAtoms() if atom.GetAtomicNum() != 1]

    def reflected(molecule):
        result = Chem.Mol(molecule)
        conformer = result.GetConformer()
        for index, point in enumerate(conformer.GetPositions().tolist()):
            conformer.SetAtomPosition(index, [-point[0], point[1], point[2]])
        return result

    # Keep the MOL's declared graph and its original reference geometry valid.
    # The separate XYZ intentionally contains the opposite coarse axial geometry.
    coarse = embedded if _axis_config_consistency(declared, embedded, [indices]) else reflected(embedded)
    reference = reflected(coarse)
    assert _axis_config_consistency(declared, coarse, [indices])
    assert _axis_config_consistency(declared, reference, [indices]) is None
    binding = {"indices": [index + 1 for index in indices]}
    record = record_fixture(tmp_path, stage="map")
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = smiles
    record.input.reaction.atom_map = list(range(coarse.GetNumAtoms()))
    record.input.conformers.guidance.ring_order = []
    for role in ("reactant", "product"):
        xyz, mol = tmp_path / (role + ".xyz"), tmp_path / (role + ".mol")
        xyz.write_text(Chem.MolToXYZBlock(coarse))
        mol.write_text(Chem.MolToMolBlock(reference))
        setattr(record.input.conformers, role, FileConformer(kind="file",
            xyz_path=str(xyz), mol_path=str(mol), heavy_atom_binding=binding))
    ts_process._build(record)

    ts_process._map(record)

    assert record.blocked is None, record.blocked
    assert record.input_binding["binding_status"] == "complete"
    assert record.terminal is None
    source = record.input.conformers.reactant
    endpoint = record.input.verification.reactant_endpoint
    endpoint.seed = EndpointSeed(kind="file", xyz_path=source.xyz_path,
        mol_path=source.mol_path, evidence_refs=[source.xyz_path])
    endpoint.optimization = record.input.ts_optimization
    directory = tmp_path / "endpoint_opt"
    directory.mkdir()
    error, input_path = ts_process._write_endpoint_input(record, str(directory), "reactant", "opt")
    assert error == "", error
    assert Path(input_path).is_file()
    # Sending a seed into optimization must not certify this wrong geometry.
    atoms = ([atom.GetSymbol() for atom in coarse.GetAtoms()],
             coarse.GetConformer().GetPositions().tolist())
    error = ts_process._endpoint_identity_error(record, "reactant", atoms)
    assert error
    correct_atoms = (atoms[0], reference.GetConformer().GetPositions().tolist())
    assert ts_process._endpoint_identity_error(record, "reactant", correct_atoms) == ""

    # Public standalone binding continues to inspect the supplied coordinates.
    public = ReactionMapping_input_schema(reactant_smiles=smiles, product_smiles=smiles,
        reactant_text=Chem.MolToMolBlock(coarse), product_text=Chem.MolToMolBlock(coarse),
        reactant_format="mol", product_format="mol", reactant_binding=binding, product_binding=binding)
    checked = check_concrete_binding(public,
        {"atom_map": list(range(1, coarse.GetNumAtoms() + 1)), "watch_pairs": []})
    assert checked["binding_status"] == "inconclusive"
    assert any("axial configuration" in diagnostic for diagnostic in checked["binding_diagnostics"])
