"""Explicit offline conversion never becomes a runtime compatibility path."""
import hashlib
from copy import deepcopy

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from cloudra.tools.core.molecule import serialize_molecule
from cloudra.tools.core.ts_process import TsProcessRecord
from tests.ts_fixtures import calculation_input


def legacy_checkpoint(tmp_path):
    mol = Chem.AddHs(Chem.MolFromSmiles('O'))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    record = TsProcessRecord(run_id='ts_0001', run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        input=calculation_input(reactant_smiles='O', product_smiles='O', method='HF/STO-3G'))
    raw = record.model_dump(mode='json')
    native = serialize_molecule(mol)
    raw.update(format_version=6, structures={}, seed_molecules={'reactant': native, 'product': native},
        current_seed_xyz_path='', current_seed_mol_path='', product_seed_xyz_path='', product_seed_mol_path='',
        current_reactant_prepared_path='', current_ts_guess_path='', effective_reaction_center=[],
        input_binding=dict(binding_status='complete', atom_map=[1, 2, 3],
            heavy_atom_bindings={'reactant': [1], 'product': [1]},
            hashes={role + '_molecule': hashlib.sha256(native.encode()).hexdigest() for role in ('reactant', 'product')}))
    raw['input']['reaction']['atom_map'] = [0, 1, 2]
    raw['input']['reaction'].pop('selected_candidate')
    return raw


def test_proven_checkpoint_conversion_removes_parallel_state_without_mutating_original(tmp_path):
    from scripts.migrate_ts_structure_state import convert_checkpoint
    raw = legacy_checkpoint(tmp_path)
    original = deepcopy(raw)
    converted = convert_checkpoint(raw)
    record = TsProcessRecord.model_validate(converted)
    assert raw == original
    assert record.format_version == 7
    assert record.structures.product_to_reactant == (0, 1, 2)
    assert record.structures.reactant.GetAtomWithIdx(0).GetIntProp('cloudra_smiles_heavy_index') == 0
    assert not {'input_binding', 'seed_molecules', 'current_seed_xyz_path'} & converted.keys()
    assert 'atom_map' not in converted['input']['reaction']


def test_unproven_old_checkpoint_cannot_be_silently_upgraded(tmp_path):
    from scripts.migrate_ts_structure_state import convert_checkpoint
    raw = legacy_checkpoint(tmp_path)
    raw['input_binding']['hashes']['reactant_molecule'] = 'wrong'
    with pytest.raises(ValueError, match='hash'):
        convert_checkpoint(raw)
    raw = legacy_checkpoint(tmp_path)
    raw['input_binding']['binding_status'] = 'inconclusive'
    with pytest.raises(ValueError, match='confirmed'):
        convert_checkpoint(raw)
