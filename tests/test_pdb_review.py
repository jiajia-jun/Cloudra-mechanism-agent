"""Cross-module PDB regressions found during integration review."""

from pathlib import Path

import pytest


@pytest.mark.parametrize('field', ['coordinate', 'occupancy', 'b_factor'])
def test_preserve_clean_rejects_nonfinite_atom_data_before_publishing(tmp_path, field):
    gemmi = pytest.importorskip('gemmi')
    from cloudra.tools.Chemtool.pdb_clean import PDBCleanInput
    from cloudra.tools.core.pdb_workflow import clean_structure

    structure = gemmi.Structure()
    structure.name = 'invalid_atom_data'
    model = gemmi.Model('1')
    chain = gemmi.Chain('A')
    residue = gemmi.Residue()
    residue.name = 'ALA'
    residue.seqid = gemmi.SeqId(1, ' ')
    residue.het_flag = 'A'
    atom = gemmi.Atom()
    atom.name = 'CA'
    atom.element = gemmi.Element('C')
    if field == 'coordinate':
        atom.pos.x = float('nan')
    elif field == 'occupancy':
        atom.occ = float('nan')
    else:
        atom.b_iso = float('nan')
    residue.add_atom(atom)
    chain.add_residue(residue)
    model.add_chain(chain)
    structure.add_model(model)
    source = tmp_path / 'invalid.cif'
    output = tmp_path / 'clean.cif'
    structure.make_mmcif_document().write_file(str(source))
    original = source.read_bytes()

    result = clean_structure(PDBCleanInput(
        input_path=str(source), output_path=str(output), purpose='preserve input atoms',
    ).model_dump())

    assert not result['is_success'], result
    assert 'finite' in result['message']
    assert not output.exists()
    assert not (tmp_path / 'clean.cif.changes.json').exists()
    assert source.read_bytes() == original


def test_filtering_gap_anchor_cannot_silently_skip_requested_gap(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    pdbfixer = pytest.importorskip('pdbfixer')
    pytest.importorskip('openmm')
    from cloudra.tools.Chemtool.pdb_clean import PDBCleanInput
    from cloudra.tools.core.pdb_structure import load_structure
    from cloudra.tools.core.pdb_workflow import clean_structure

    structure = gemmi.Structure()
    structure.name = 'filtered_gap_anchor'
    model = gemmi.Model('1')
    chain = gemmi.Chain('A')
    templates = Path(pdbfixer.__file__).parent / 'templates'
    for index, (name, label) in enumerate(zip(['ALA', 'GLY', 'VAL'], [1, 3, 5], strict=True)):
        residue = gemmi.read_structure(str(templates / f'{name}.pdb'))[0][0][0].clone()
        residue.seqid = gemmi.SeqId(index + 1, ' ')
        residue.subchain = 'poly'
        residue.entity_id = '1'
        residue.entity_type = gemmi.EntityType.Polymer
        residue.label_seq = label
        for atom in residue:
            atom.pos.x += index * 4
        chain.add_residue(residue)
    model.add_chain(chain)
    structure.add_model(model)
    entity = gemmi.Entity('1')
    entity.entity_type = gemmi.EntityType.Polymer
    entity.polymer_type = gemmi.PolymerType.PeptideL
    entity.subchains = ['poly']
    entity.full_sequence = ['ALA', 'SER', 'GLY', 'THR', 'VAL']
    structure.entities.append(entity)
    source = tmp_path / 'gaps.cif'
    output = tmp_path / 'clean.cif'
    structure.make_mmcif_document().write_file(str(source))
    _, keys, _ = load_structure(str(source))

    result = clean_structure(PDBCleanInput(
        input_path=str(source), output_path=str(output), purpose='repair both gaps and remove central glycine',
        add_missing_residues='internal', add_missing_atoms=False,
        remove_residue_keys=[keys[(0, 1)]],
    ).model_dump())

    if result['is_success']:
        actual = gemmi.read_structure(str(output))
        assert [residue.name for residue in actual[0][0]] == ['ALA', 'SER', 'THR', 'VAL']
    else:
        assert not output.exists()
        assert not (tmp_path / 'clean.cif.changes.json').exists()


def test_selected_water_and_protein_keep_original_altloc_compatibility(tmp_path):
    gemmi = pytest.importorskip('gemmi')
    pytest.importorskip('plip')
    pytest.importorskip('openbabel.openbabel')
    from cloudra.tools.Chemtool.pdb_clean import PDBCleanInput
    from cloudra.tools.core.pdb_workflow import clean_structure
    source = tmp_path/'altloc.pdb'
    source.write_text(
        'ATOM      1  N  AALA A   1       0.000   0.000   0.000  0.60 10.00           N  \n'
        'ATOM      2  N  BALA A   1      10.000   0.000   0.000  0.40 10.00           N  \n'
        'HETATM    3  O  BHOH A 101       3.000   0.000   0.000  1.00 10.00           O  \nEND\n'
    )
    output = tmp_path/'selected.cif'
    result = clean_structure(PDBCleanInput(input_path=str(source),output_path=str(output),
        purpose='retain only compatible candidate water',waters='candidates').model_dump())
    assert result['is_success'], result['message']
    actual = gemmi.read_structure(str(output))
    assert [r.name for r in actual[0][0]] == ['ALA']
    assert actual[0][0][0][0].altloc == 'A'
