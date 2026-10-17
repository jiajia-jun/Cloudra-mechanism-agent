"""Revisions retain proved molecular identity without reopening old sources."""
from pathlib import Path

import pytest

from cloudra.tools.core.ts_inputs import TsResumeRequest
from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
from tests.test_ts_revision_state import state_fixture

pytestmark = pytest.mark.usefixtures('rdkit_chemistry')


def write_source(directory, role, mol):
    from rdkit import Chem
    directory.mkdir(parents=True, exist_ok=True)
    xyz, graph = directory / f'{role}.xyz', directory / f'{role}.mol'
    xyz.write_text(Chem.MolToXYZBlock(mol))
    graph.write_text(Chem.MolToMolBlock(mol))
    return {'kind': 'file', 'xyz_path': str(xyz), 'mol_path': str(graph)}


def molecular_fixture(tmp_path, *, labels=True):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.reaction_state import ReactionStructures, import_file_structure, set_heavy_binding
    from cloudra.tools.core.ts_inputs import TsInput

    _, record = state_fixture(tmp_path)
    mol = Chem.AddHs(Chem.MolFromSmiles('O'))
    assert AllChem.EmbedMolecule(mol, randomSeed=42) == 0
    if labels:
        for atom in mol.GetAtoms():
            atom.SetAtomMapNum(atom.GetIdx() + 10)
    payload = record.input.model_dump(mode='json')
    payload['conformers'] = {
        'reactant': write_source(tmp_path, 'reactant', mol),
        'product': write_source(tmp_path, 'product', mol),
        'guidance': {'ring_order': [0, 1, 2], 'distance_filters': [{'atoms': [0, 1], 'min_ang': .5, 'max_ang': 2.}]},
    }
    payload['reaction']['reaction_center'] = [[0, 1]]
    payload['guess'] = {'kind': 'scan', 'calculation': {'engine': 'orca', 'method': 'HF', 'basis_set': 'STO-3G'},
        'scans': [{'coord_type': 'bond', 'atoms': [0, 1], 'scan_start': 1., 'scan_end': 2., 'scan_steps': 3}],
        'freeze': [{'coord_type': 'bond', 'atoms': [0, 2]}]}
    record.input = TsInput.model_validate(payload)
    record.structures = ReactionStructures(
        reactant=set_heavy_binding(import_file_structure(record, 'reactant', record.input.conformers.reactant), [1]),
        product=set_heavy_binding(import_file_structure(record, 'product', record.input.conformers.product), [1]),
        product_to_reactant=(0, 1, 2))
    record.stage = 'refine'
    return record, mol


def revise(record, changes):
    request = TsResumeRequest(changes=changes, reason='Update current structures',
        request_key='revision', expected_revision=record.revision)
    receipt = plan_input_revision(record, request)
    return revise_record(record, request, receipt), receipt


def test_same_path_is_an_explicit_coordinate_import_and_history_keeps_old_geometry(tmp_path):
    from cloudra.tools.core.reaction_state import heavy_binding, source_snapshot
    from cloudra.tools.core.ts_process import TsJobStep

    record, mol = molecular_fixture(tmp_path)
    before = record.structures.reactant.GetConformer().GetPositions().tolist()
    record.job_steps = [TsJobStep(purpose='ts_opt', job_id=7, state='done')]
    mol.GetConformer().SetAtomPosition(1, (1.4, .8, .1))
    source = write_source(tmp_path, 'reactant', mol)
    raw = {name: Path(source[name]).read_bytes() for name in ('xyz_path', 'mol_path')}
    revised, receipt = revise(record, {'conformers': {'reactant': {'xyz_path': source['xyz_path']}}})
    assert revised.structures.reactant.GetConformer().GetPositions().tolist() != before
    assert revised.structures.product_to_reactant == (0, 1, 2)
    assert heavy_binding(revised.structures.reactant) == [1]
    assert revised.input.reaction.reaction_center == [(0, 1)]
    assert revised.input.guess == record.input.guess
    assert receipt.invalidated[0].job_id == 7
    assert revised.job_steps == []
    assert revised.attempt_history[0].structures.reactant.GetConformer().GetPositions().tolist() == before
    assert record.structures.reactant.GetConformer().GetPositions().tolist() == before
    assert source_snapshot(revised.structures.reactant)['input_revision'] == 2
    assert all(Path(source[name]).read_bytes() == data for name, data in raw.items())


def test_calculation_only_and_preoptimization_removal_keep_imported_state(tmp_path):
    from cloudra.tools.core.molecule import serialize_molecule

    record, _ = molecular_fixture(tmp_path)
    before = serialize_molecule(record.structures.reactant)
    # A mutable caller file is no longer an execution-time source of truth.
    Path(record.input.conformers.reactant.xyz_path).write_text('unrelated later contents')
    revised, _ = revise(record, {'ts_optimization': {'keywords': 'TightSCF'}})
    assert serialize_molecule(revised.structures.reactant) == before
    assert revised.structures.product_to_reactant == (0, 1, 2)
    record.input.conformers.reactant.optimization = record.input.ts_optimization
    revised, _ = revise(record, {'conformers': {'reactant': {'optimization': None}}})
    assert revised.input.conformers.reactant.optimization is None
    assert revised.input.conformers.reactant.mol_path == record.input.conformers.reactant.mol_path
    assert serialize_molecule(revised.structures.reactant) == before
    assert revised.structures.product_to_reactant == (0, 1, 2)


def test_unproved_identity_drops_inherited_atom_references_and_mapping(tmp_path):
    from rdkit import Chem
    record, mol = molecular_fixture(tmp_path, labels=False)
    swapped = Chem.RenumberAtoms(mol, [0, 2, 1])
    source = write_source(tmp_path / 'new', 'reactant', swapped)
    revised, _ = revise(record, {'conformers': {'reactant': source}})
    assert revised.structures.product_to_reactant is None
    assert revised.input.reaction.reaction_center == []
    assert revised.input.conformers.guidance.ring_order == []
    assert revised.input.conformers.guidance.distance_filters == []
    assert revised.input.guess is None
    assert record.structures.product_to_reactant == (0, 1, 2)


@pytest.mark.parametrize('reaction', [{'charge': 1}, {'multiplicity': 3}, {'product_smiles': '[OH2]'}])
def test_chemical_declaration_change_does_not_inherit_mapping_or_reread_source(tmp_path, reaction):
    from cloudra.tools.core.molecule import serialize_molecule
    record, _ = molecular_fixture(tmp_path)
    before = serialize_molecule(record.structures.reactant)
    Path(record.input.conformers.reactant.xyz_path).unlink()
    revised, _ = revise(record, {'reaction': reaction})
    assert revised.structures.product_to_reactant is None
    assert serialize_molecule(revised.structures.reactant) == before
    assert revised.stage == 'declare'


def test_unproved_source_order_does_not_retain_scan_atoms_from_calculation_only_patch(tmp_path):
    from rdkit import Chem
    record, mol = molecular_fixture(tmp_path, labels=False)
    source = write_source(tmp_path / 'new', 'reactant', Chem.RenumberAtoms(mol, [0, 2, 1]))
    revised, _ = revise(record, {'conformers': {'reactant': source},
        'guess': {'calculation': {'keywords': 'TightSCF'}}})
    assert revised.input.guess is None


def test_unproved_new_source_does_not_inherit_a_previous_mapping_candidate_choice(tmp_path):
    from rdkit import Chem
    record, mol = molecular_fixture(tmp_path, labels=False)
    record.input.reaction.selected_candidate = 0
    source = write_source(tmp_path / 'new', 'reactant', Chem.RenumberAtoms(mol, [0, 2, 1]))
    revised, _ = revise(record, {'conformers': {'reactant': source}})
    assert revised.input.reaction.selected_candidate is None


def test_species_change_rebuilds_a_generated_endpoint_instead_of_reusing_old_molecule(tmp_path):
    from cloudra.tools.core.ts_inputs import GeneratedConformer
    from cloudra.tools.core.ts_process import _build

    record, _ = molecular_fixture(tmp_path)
    record.input.conformers.reactant = GeneratedConformer(kind='generate', generation='ETKDGv3', seed=42)
    revised, _ = revise(record, {'reaction': {'reactant_smiles': 'CCO'}})
    assert revised.structures.reactant is None
    _build(revised)
    assert revised.blocked is None
    assert revised.structures.reactant.GetNumAtoms() == 9
    assert record.structures.reactant.GetNumAtoms() == 3
