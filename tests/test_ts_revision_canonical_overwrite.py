"""Proved source reorderings are internal; caller files never become outputs."""
from pathlib import Path

import pytest

from cloudra.tools.core.reaction_state import heavy_binding, source_snapshot
from tests.test_ts_revision_identity import molecular_fixture, revise, write_source

pytestmark = pytest.mark.usefixtures('rdkit_chemistry')


def test_file_reorder_updates_owned_molecules_and_converts_only_explicit_indices(tmp_path):
    from cloudra.tools.core.molecule import renumber_atoms

    record, mol = molecular_fixture(tmp_path)
    source = write_source(tmp_path / 'incoming', 'reactant', renumber_atoms(mol, [2, 0, 1]))
    original = {name: Path(source[name]).read_bytes() for name in ('xyz_path', 'mol_path')}
    revised, receipt = revise(record, {
        'conformers': {'reactant': source, 'guidance': {'ring_order': [0, 1, 2],
            'distance_filters': [{'atoms': [0, 1], 'min_ang': .5, 'max_ang': 2.}]}},
        'reaction': {'reaction_center': [[0, 1]]},
        'guess': {'scans': [{'coord_type': 'bond', 'atoms': [0, 1], 'scan_start': 1., 'scan_end': 2., 'scan_steps': 3}]},
    })
    assert [a.GetAtomMapNum() for a in revised.structures.reactant.GetAtoms()] == [10, 11, 12]
    assert heavy_binding(revised.structures.reactant) == [1]
    assert revised.structures.product_to_reactant == (0, 1, 2)
    assert revised.input.reaction.reaction_center == [(2, 0)]
    assert revised.input.conformers.guidance.ring_order == [2, 0, 1]
    assert revised.input.conformers.guidance.distance_filters[0].atoms == [2, 0]
    assert revised.input.guess.scans[0].atoms == [2, 0]
    # Omitted references were already canonical and must not convert again.
    assert revised.input.guess.freeze[0].atoms == [0, 2]
    assert all(Path(source[name]).read_bytes() == content for name, content in original.items())
    snapshot = source_snapshot(revised.structures.reactant)
    assert snapshot['input_revision'] == 2
    assert Path(snapshot['snapshots']['xyz']).read_bytes() == original['xyz_path']
    assert 'conformers.reactant' in receipt.changes


def test_both_endpoint_reorders_preserve_the_existing_cross_structure_map(tmp_path):
    from cloudra.tools.core.molecule import renumber_atoms
    from cloudra.tools.core.reaction_state import path_endpoints

    record, mol = molecular_fixture(tmp_path)
    revised, _ = revise(record, {'conformers': {
        'reactant': write_source(tmp_path / 'incoming', 'reactant', renumber_atoms(mol, [2, 0, 1])),
        'product': write_source(tmp_path / 'incoming', 'product', renumber_atoms(mol, [1, 2, 0])),
    }})
    reactant, product = path_endpoints(revised.structures)
    assert [a.GetAtomMapNum() for a in reactant.GetAtoms()] == [10, 11, 12]
    assert [a.GetAtomMapNum() for a in product.GetAtoms()] == [10, 11, 12]
    assert revised.input.reaction.reaction_center == record.input.reaction.reaction_center
    assert revised.input.guess == record.input.guess


@pytest.mark.parametrize('candidate_order', ['incoming', 'canonical'])
def test_simultaneous_provided_candidate_reorder_uses_immutable_internal_copy(tmp_path, candidate_order):
    from rdkit import Chem

    from cloudra.tools.core.molecule import renumber_atoms
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    record, mol = molecular_fixture(tmp_path)
    reordered = renumber_atoms(mol, [2, 0, 1])
    source = write_source(tmp_path / 'incoming', 'reactant', reordered)
    guess = tmp_path / 'provided.xyz'
    guess.write_text(Chem.MolToXYZBlock(reordered if candidate_order == 'incoming' else mol))
    original = guess.read_bytes()
    revised, _ = revise(record, {'conformers': {'reactant': source},
        'guess': {'kind': 'provided', 'xyz_path': str(guess), 'evidence_refs': [str(guess)]}})
    assert guess.read_bytes() == original
    assert revised.input.guess.xyz_path != str(guess)
    assert [symbol for symbol, _ in read_xyz_atoms(revised.input.guess.xyz_path)] == ['O', 'H', 'H']
    expected = record.structures.reactant.GetConformer().GetPositions().tolist()
    actual = [point for _, point in read_xyz_atoms(revised.input.guess.xyz_path)]
    assert [value for point in actual for value in point] == pytest.approx([value for point in expected for value in point])


def test_simultaneous_provided_candidate_with_unproved_order_is_rejected(tmp_path):
    from rdkit import Chem

    from cloudra.tools.core.molecule import renumber_atoms

    record, mol = molecular_fixture(tmp_path)
    reordered = renumber_atoms(mol, [2, 0, 1])
    source = write_source(tmp_path / 'incoming', 'reactant', reordered)
    reordered.GetConformer().SetAtomPosition(0, (9., 9., 9.))
    guess = tmp_path / 'unassociated.xyz'
    guess.write_text(Chem.MolToXYZBlock(reordered))
    before = guess.read_bytes()
    with pytest.raises(ValueError, match='association is unproved'):
        revise(record, {'conformers': {'reactant': source},
            'guess': {'kind': 'provided', 'xyz_path': str(guess), 'evidence_refs': [str(guess)]}})
    assert guess.read_bytes() == before


def test_partial_rotation_settings_do_not_reconvert_inherited_axis(tmp_path):
    from cloudra.tools.core.molecule import renumber_atoms
    from cloudra.tools.core.ts_inputs import RotatedConformer

    record, mol = molecular_fixture(tmp_path)
    record.input.conformers.product = RotatedConformer(kind='rotate_about_bond', atoms=(0, 1), degrees=30.)
    source = write_source(tmp_path / 'incoming', 'reactant', renumber_atoms(mol, [2, 0, 1]))
    revised, _ = revise(record, {'conformers': {'reactant': source, 'product': {'degrees': 60.}}})
    assert revised.input.conformers.product.atoms == (0, 1)
    assert revised.structures.product is None
