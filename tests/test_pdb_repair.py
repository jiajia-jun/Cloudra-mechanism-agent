"""Real Gemmi/PDBFixer regression coverage for selective macromolecular repair."""

from pathlib import Path

import pytest


def _dependencies():
    gemmi = pytest.importorskip('gemmi')
    pytest.importorskip('pdbfixer')
    pytest.importorskip('openmm')
    return gemmi


def _structure(names, sequence=None, *, numbers=None, label_ids=None, chain_name='A'):
    gemmi = _dependencies()
    import pdbfixer

    structure = gemmi.Structure()
    structure.name = 'repair_test'
    model = gemmi.Model('1')
    chain = gemmi.Chain(chain_name)
    templates = Path(pdbfixer.__file__).parent / 'templates'
    for index, name in enumerate(names):
        residue = gemmi.read_structure(str(templates / f'{name}.pdb'))[0][0][0].clone()
        residue.seqid = gemmi.SeqId((numbers or list(range(1, len(names) + 1)))[index], ' ')
        residue.subchain = 'poly'
        residue.entity_id = '1'
        residue.entity_type = gemmi.EntityType.Polymer
        residue.label_seq = (label_ids[index] if label_ids is not None else None)
        for atom in residue:
            atom.pos.x += index * 4.0
        chain.add_residue(residue)
    model.add_chain(chain)
    structure.add_model(model)
    entity = gemmi.Entity('1')
    entity.entity_type = gemmi.EntityType.Polymer
    entity.polymer_type = gemmi.PolymerType.PeptideL
    entity.subchains = ['poly']
    entity.full_sequence = sequence or []
    structure.entities.append(entity)
    return structure


def _keys(structure):
    return {(ci, ri): f'opaque-{ci}-{ri}' for ci, chain in enumerate(structure[0]) for ri, _ in enumerate(chain)}


def test_declared_sequence_distinguishes_three_gap_kinds_with_opaque_anchors():
    from cloudra.tools.core.pdb_repair import inspect_missing

    structure = _structure(['ALA', 'THR'], ['GLY', 'ALA', 'SER', 'THR', 'VAL'], numbers=[100, 100])
    structure[0][0][1].seqid.icode = 'A'
    result = inspect_missing(structure, _keys(structure))
    assert result['analysis_status']['missing_residues']['status'] == 'completed'
    n_gap, = result['n_terminal_gaps']
    i_gap, = result['internal_gaps']
    c_gap, = result['c_terminal_gaps']
    assert (n_gap['residue_names'], i_gap['residue_names'], c_gap['residue_names']) == (['GLY'], ['SER'], ['VAL'])
    assert i_gap['left_anchor'] == 'opaque-0-0'
    assert i_gap['right_anchor'] == 'opaque-0-1'
    assert i_gap['sequence_range'] == [3, 3]
    assert i_gap['insertion_position'] == {'chain_index': 0, 'residue_index': 1}


def test_numbering_jump_without_declared_sequence_is_unknown():
    from cloudra.tools.core.pdb_repair import inspect_missing

    structure = _structure(['ALA', 'GLY'], numbers=[1, 99])
    result = inspect_missing(structure, _keys(structure))
    assert result['internal_gaps'] == []
    assert result['n_terminal_gaps'] == []
    assert result['c_terminal_gaps'] == []
    assert result['analysis_status']['missing_residues']['status'] == 'unknown'


def test_repeated_sequence_is_ambiguous_unless_label_positions_are_declared():
    from cloudra.tools.core.pdb_repair import inspect_missing

    structure = _structure(['ALA'], ['ALA', 'ALA', 'ALA'])
    result = inspect_missing(structure, _keys(structure))
    status = result['analysis_status']['missing_residues']
    assert status['status'] == 'unknown'
    assert status['chain_results'][0]['status'] == 'ambiguous'
    structure[0][0][0].label_seq = 2
    result = inspect_missing(structure, _keys(structure))
    assert result['n_terminal_gaps'][0]['sequence_range'] == [1, 1]
    assert result['c_terminal_gaps'][0]['sequence_range'] == [3, 3]


def test_missing_atoms_are_categorized_without_combining_altlocs():
    from cloudra.tools.core.pdb_repair import inspect_missing

    structure = _structure(['SER'], ['SER'])
    residue = structure[0][0][0]
    for index in range(len(residue) - 1, -1, -1):
        atom = residue[index]
        if atom.name == 'N':
            del residue[index]
        elif atom.name == 'CB':
            atom.altloc = 'A'
        elif atom.name == 'OG':
            atom.altloc = 'B'
    result = inspect_missing(structure, _keys(structure))
    atoms = {item['altloc']: item for item in result['missing_atoms']}
    assert atoms['A']['mainchain'] == ['N']
    assert atoms['A']['sidechain'] == ['OG']
    assert atoms['B']['sidechain'] == ['CB']
    assert atoms['A']['terminal'] == ['OXT']
    assert all(item['residue_key'] == 'opaque-0-0' for item in atoms.values())


def test_unknown_modified_residue_template_is_not_declared_complete():
    from cloudra.tools.core.pdb_repair import inspect_missing

    structure = _structure(['MET'], ['MSE'])
    structure[0][0][0].name = 'MSE'
    result = inspect_missing(structure, _keys(structure))
    assert result['missing_atoms'][0]['status'] == 'unsupported'
    assert structure[0][0][0].name == 'MSE'


def test_real_selective_internal_gap_repair_does_not_fill_old_missing_atoms():
    from cloudra.tools.core.pdb_repair import inspect_missing, repair_structure

    structure = _structure(['ALA', 'GLY', 'VAL'], ['ALA', 'SER', 'GLY', 'VAL'], numbers=[50, 50, 51], label_ids=[1, 3, 4], chain_name='LongChain')
    structure[0][0][1].seqid.icode = 'A'
    residue = structure[0][0][0]
    for index in range(len(residue) - 1, -1, -1):
        if residue[index].name == 'CB':
            del residue[index]
    keys = _keys(structure)
    result = inspect_missing(structure, keys)
    repaired, changes, unresolved, warnings, versions = repair_structure(
        structure, keys, {'add_missing_atoms': False}, result['internal_gaps'],
    )
    assert not unresolved
    assert [res.name for res in repaired[0][0]] == ['ALA', 'SER', 'GLY', 'VAL']
    assert 'CB' not in {atom.name for atom in repaired[0][0][0]}
    assert {atom.name for atom in repaired[0][0][1]} >= {'N', 'CA', 'C', 'O', 'CB', 'OG'}
    assert repaired[0][0].name == 'LongChain'
    assert repaired[0][0][0].seqid.num == 50
    assert repaired[0][0][2].seqid.num == 50
    assert repaired[0][0][2].seqid.icode == 'A'
    assert any(change['action'] == 'add_residue' and change['status'] == 'modeled' for change in changes)
    assert versions['pdbfixer']


def test_real_atom_repair_preserves_ligands_metals_and_original_coordinates():
    from cloudra.tools.core.pdb_repair import repair_structure

    gemmi = _dependencies()
    structure = _structure(['ALA'], ['ALA'])
    residue = structure[0][0][0]
    for index in range(len(residue) - 1, -1, -1):
        if residue[index].name == 'CB':
            del residue[index]
    for name, atom_name, element in [('LIG', 'C1', 'C'), ('ZN', 'ZN', 'Zn')]:
        extra = gemmi.Residue()
        extra.name = name
        extra.seqid = gemmi.SeqId(200 + len(structure[0][0]), ' ')
        extra.het_flag = 'H'
        extra.subchain = f'hetero{extra.seqid.num}'
        atom = gemmi.Atom()
        atom.name = atom_name
        atom.element = gemmi.Element(element)
        atom.pos = gemmi.Position(20, 20, 20)
        extra.add_atom(atom)
        structure[0][0].add_residue(extra)
    before = [(atom.name, atom.pos.x, atom.pos.y, atom.pos.z) for atom in structure[0][0][0]]
    repaired, changes, unresolved, warnings, versions = repair_structure(
        structure, _keys(structure), {'add_missing_atoms': True}, [],
    )
    assert 'CB' in {atom.name for atom in repaired[0][0][0]}
    assert [res.name for res in repaired[0][0]] == ['ALA', 'LIG', 'ZN']
    for name, x, y, z in before:
        assert repaired[0][0][0].find_atom(name, '\0').pos.dist(gemmi.Position(x, y, z)) < 1e-7
    assert not unresolved
    assert any('LIG' in warning and 'retained' in warning for warning in warnings)
    assert any(change['action'] == 'add_atom' and change['atom_name'] == 'CB' for change in changes)


def test_terminal_template_is_checked_on_polymer_not_trailing_heterogen():
    from cloudra.tools.core.pdb_repair import inspect_missing

    gemmi = _dependencies()
    structure = _structure(['ALA'], ['ALA'])
    extra = gemmi.Residue()
    extra.name = 'ZN'
    extra.seqid = gemmi.SeqId(9, ' ')
    extra.subchain = 'metal'
    extra.entity_type = gemmi.EntityType.NonPolymer
    atom = gemmi.Atom()
    atom.name = 'ZN'
    atom.element = gemmi.Element('Zn')
    extra.add_atom(atom)
    structure[0][0].add_residue(extra)
    result = inspect_missing(structure, _keys(structure))
    assert result['missing_atoms'][0]['terminal'] == ['OXT']


def test_real_gap_repair_before_trailing_heterogen_preserves_all_residue_order():
    from cloudra.tools.core.pdb_repair import inspect_missing, repair_structure

    gemmi = _dependencies()
    structure = _structure(['ALA', 'GLY', 'VAL'], ['ALA', 'SER', 'GLY', 'VAL'])
    extra = gemmi.Residue()
    extra.name = 'ZN'
    extra.seqid = gemmi.SeqId(9, ' ')
    extra.subchain = 'metal'
    extra.entity_type = gemmi.EntityType.NonPolymer
    atom = gemmi.Atom()
    atom.name = 'ZN'
    atom.element = gemmi.Element('Zn')
    atom.pos = gemmi.Position(30, 30, 30)
    extra.add_atom(atom)
    structure[0][0].add_residue(extra)
    keys = _keys(structure)
    gaps = inspect_missing(structure, keys)['internal_gaps']
    output, *_ = repair_structure(structure, keys, {'add_missing_atoms': False}, gaps)
    assert [res.name for res in output[0][0]] == ['ALA', 'SER', 'GLY', 'VAL', 'ZN']


def test_real_hydrogen_addition_is_recorded_without_filling_old_sidechain():
    from cloudra.tools.core.pdb_repair import repair_structure

    structure = _structure(['ALA'], ['ALA'])
    before = {(atom.name, atom.pos.x, atom.pos.y, atom.pos.z) for atom in structure[0][0][0]}
    output, changes, unresolved, warnings, _ = repair_structure(
        structure, _keys(structure), {'add_hydrogens': True, 'add_missing_atoms': False, 'ph': 7.0}, [],
    )
    assert any(atom.element.name == 'H' for atom in output[0][0][0])
    assert any(item['action'] == 'add_atom' and item['atom_name'].startswith('H') for item in changes)
    assert before <= {(atom.name, atom.pos.x, atom.pos.y, atom.pos.z) for atom in output[0][0][0]}
    assert 'OXT' not in {atom.name for atom in output[0][0][0]}
    assert not unresolved
    assert warnings


def test_backend_preserves_explicit_input_bonds_during_identifier_staging():
    from cloudra.tools.core.pdb_repair import _make_fixer

    gemmi = _dependencies()
    structure = _structure(['CYS', 'CYS'], ['CYS', 'CYS'])
    connection = gemmi.Connection()
    connection.name = 'disulfide'
    connection.type = gemmi.ConnectionType.Disulf
    for address, residue in [(connection.partner1, structure[0][0][0]), (connection.partner2, structure[0][0][1])]:
        address.chain_name = 'A'
        address.res_id.name = residue.name
        address.res_id.seqid = residue.seqid
        address.atom_name = 'SG'
    structure.connections.append(connection)
    fixer, mapping = _make_fixer(structure)
    assert any(a.name == b.name == 'SG' and a.residue != b.residue for a, b in fixer.topology.bonds())


def test_real_requested_nonstandard_replacement_only_changes_polymer():
    from cloudra.tools.core.pdb_repair import repair_structure

    gemmi = _dependencies()
    structure = _structure(['MET'], ['MSE'])
    structure[0][0][0].name = 'MSE'
    structure[0][0][0].find_atom('SD', '\0').name = 'SE'
    structure[0][0][0].find_atom('SE', '\0').element = gemmi.Element('Se')
    nonpoly = structure[0][0][0].clone()
    nonpoly.seqid = gemmi.SeqId(2, ' ')
    nonpoly.subchain = 'ligand'
    nonpoly.entity_type = gemmi.EntityType.NonPolymer
    structure[0][0].add_residue(nonpoly)
    output, changes, _, _, _ = repair_structure(
        structure, _keys(structure), {'replace_nonstandard_residues': True, 'add_missing_atoms': True}, [],
    )
    assert [res.name for res in output[0][0]] == ['MET', 'MSE']
    assert 'SD' in {atom.name for atom in output[0][0][0]}
    assert 'SE' in {atom.name for atom in output[0][0][1]}
    assert [item for item in changes if item['action'] == 'replace_residue'] == [
        {'action': 'replace_residue', 'residue_key': 'opaque-0-0', 'from': 'MSE', 'to': 'MET'},
    ]


def test_requested_unknown_polymer_template_fails_instead_of_skipping():
    from cloudra.tools.core.pdb_repair import repair_structure

    structure = _structure(['MET'], ['MSE'])
    structure[0][0][0].name = 'MSE'
    with pytest.raises(ValueError, match='No PDBFixer heavy-atom template.*MSE'):
        repair_structure(structure, _keys(structure), {'add_missing_atoms': True}, [])


def test_equivalent_pdb_seqres_and_mmcif_declared_sequence_have_same_gap_semantics():
    from cloudra.tools.core.pdb_repair import inspect_missing

    gemmi = _dependencies()
    original = _structure(['ALA', 'THR'], ['GLY', 'ALA', 'SER', 'THR', 'VAL'], numbers=[2, 4])
    pdb = gemmi.read_pdb_string(original.make_pdb_string())
    pdb.setup_entities()
    cif = gemmi.make_structure_from_block(original.make_mmcif_document().sole_block())
    cif.setup_entities()
    results = [inspect_missing(structure, _keys(structure)) for structure in [pdb, cif]]
    for field in ['internal_gaps', 'n_terminal_gaps', 'c_terminal_gaps']:
        semantics = [[(gap['kind'], gap['residue_names'], gap['sequence_range'], gap['left_anchor'], gap['right_anchor']) for gap in result[field]] for result in results]
        assert semantics[0] == semantics[1]
        assert semantics[0]


def test_unknown_hydrogen_definition_fails_when_real_ccd_loader_is_unavailable(monkeypatch):
    """Only the external network boundary is offline; backend validation is real."""
    from urllib.error import URLError

    from cloudra.tools.core.pdb_repair import repair_structure

    _dependencies()
    import pdbfixer.pdbfixer

    structure = _structure(['ALA'], ['ZZZ'])
    structure[0][0][0].name = 'ZZZ'
    requested_urls = []

    def offline(url):
        requested_urls.append(url)
        raise URLError('CCD lookup deliberately unavailable in this test')

    monkeypatch.setattr(pdbfixer.pdbfixer, 'urlopen', offline)
    with pytest.raises(ValueError, match='Unsupported.*hydrogen definition.*ZZZ'):
        repair_structure(structure, _keys(structure), {'add_hydrogens': True}, [])
    assert requested_urls == ['https://files.rcsb.org/ligands/download/ZZZ.cif']
    assert not any(atom.element.name == 'H' for atom in structure[0][0][0])


def test_hydrogens_disabled_does_not_download_ccd_or_modify_hydrogens(monkeypatch):
    from cloudra.tools.core.pdb_repair import repair_structure

    _dependencies()
    import pdbfixer.pdbfixer

    structure = _structure(['MET'], ['MSE'])
    structure[0][0][0].name = 'MSE'

    def unexpected_download(*args, **kwargs):
        pytest.fail('add_hydrogens=False must not download CCD hydrogen definitions')

    monkeypatch.setattr(pdbfixer.pdbfixer, 'urlopen', unexpected_download)
    output, changes, unresolved, _, _ = repair_structure(structure, _keys(structure), {'add_hydrogens': False}, [])
    assert changes == []
    assert unresolved == []
    assert not any(atom.element.name == 'H' for atom in output[0][0][0])


def test_duplicate_selected_gap_insertion_is_rejected_not_overwritten():
    from cloudra.tools.core.pdb_repair import inspect_missing, repair_structure

    structure = _structure(['ALA', 'GLY', 'VAL'], ['ALA', 'SER', 'GLY', 'VAL'])
    keys = _keys(structure)
    gap = inspect_missing(structure, keys)['internal_gaps'][0]
    second_gap = {**gap, 'gap_id': 'different-gap', 'residue_names': ['THR']}
    with pytest.raises(ValueError, match='Multiple selected gaps.*insertion'):
        repair_structure(structure, keys, {'add_missing_atoms': False}, [gap, second_gap])


def test_replacement_drops_and_logs_connections_to_removed_atoms():
    from cloudra.tools.core.pdb_repair import repair_structure

    gemmi = _dependencies()
    structure = _structure(['MET'], ['MSE'])
    residue = structure[0][0][0]
    residue.name = 'MSE'
    residue.find_atom('SD', '\0').name = 'SE'
    residue.find_atom('SE', '\0').element = gemmi.Element('Se')
    connection = gemmi.Connection()
    connection.name = 'old-SE-link'
    connection.type = gemmi.ConnectionType.MetalC
    for address, atom_name in [(connection.partner1, 'SE'), (connection.partner2, 'CA')]:
        address.chain_name = 'A'
        address.res_id.name = 'MSE'
        address.res_id.seqid = residue.seqid
        address.atom_name = atom_name
    structure.connections.append(connection)
    output, changes, _, warnings, _ = repair_structure(
        structure, _keys(structure), {'replace_nonstandard_residues': True, 'add_missing_atoms': True}, [],
    )
    assert not output.connections
    assert any(change['action'] == 'remove_connection' and change['connection_name'] == 'old-SE-link' for change in changes)
    assert any('connection' in warning for warning in warnings)
    assert len(structure.connections) == 1
