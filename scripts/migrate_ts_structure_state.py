"""Explicit offline format-6 checkpoint conversion; never called by the runtime.

Usage: python -m scripts.migrate_ts_structure_state old-process.json new-process.json
The original checkpoint and every compute artifact remain untouched. Review the
result before a separately authorized offline ledger migration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from pydantic import TypeAdapter

from cloudra.tools.core.molecule import Molecule, with_positions
from cloudra.tools.core.reaction_state import ReactionStructures, set_heavy_binding
from cloudra.tools.core.ts_process import TsProcessRecord


def _input(value):
    value = deepcopy(value)
    value.get('reaction', {}).pop('atom_map', None)
    for role in ('reactant', 'product'):
        source = value.get('conformers', {}).get(role)
        if source and source.get('kind') == 'file':
            source.pop('heavy_atom_binding', None)
    return value


def convert_checkpoint(payload: dict) -> dict:
    """只转换已有完整证明的状态；不能证明则保留旧检查点只读。"""
    if payload.get('format_version') != 6:
        raise ValueError('Only format-6 checkpoints can be converted explicitly')
    old = deepcopy(payload)
    binding = old.get('input_binding', {})
    if binding.get('binding_status') != 'complete':
        raise ValueError('A confirmed complete concrete correspondence is required')
    mapping = binding.get('atom_map', [])
    if old['input']['reaction'].get('atom_map') != [index - 1 for index in mapping]:
        raise ValueError('The old declaration and confirmed concrete map disagree')
    molecules = {}
    from cloudra.tools.Chemtool.reaction_mapping import _identity_and_binding
    for role in ('reactant', 'product'):
        native = old.get('seed_molecules', {}).get(role)
        if not isinstance(native, str):
            raise ValueError(f'{role}: native molecular state is unavailable')
        if hashlib.sha256(native.encode()).hexdigest() != binding.get('hashes', {}).get(role + '_molecule'):
            raise ValueError(f'{role}: native molecule hash does not match its confirmed binding')
        molecule = TypeAdapter(Molecule).validate_python(native)
        indices = binding.get('heavy_atom_bindings', {}).get(role, [])
        identity, accepted, diagnostic = _identity_and_binding(old['input']['reaction'][role + '_smiles'], molecule,
            [index - 1 for index in indices] or None)
        if identity != 'match' or (molecule.GetNumHeavyAtoms() and not accepted):
            raise ValueError(f'{role}: old concrete identity is unproven: {diagnostic}')
        molecules[role] = set_heavy_binding(molecule, [index + 1 for index in accepted])
        table = old.get('structures', {}).get(role, {})
        source = old['input'].get('conformers', {}).get(role) or {}
        snapshot = dict(input_revision=table.get('input_revision', old.get('declaration_revision', 1)),
            paths={kind: source[kind + '_path'] for kind in ('xyz', 'mol') if source.get(kind + '_path')},
            snapshots={kind: table[kind + '_path'] for kind in ('xyz', 'mol') if table.get(kind + '_path')},
            hashes={kind: table[kind + '_sha256'] for kind in ('xyz', 'mol') if table.get(kind + '_sha256')})
        molecules[role].SetProp('cloudra_import_source', json.dumps(snapshot))
    structures = ReactionStructures(**molecules, product_to_reactant=tuple(index - 1 for index in mapping))
    candidate = old.get('current_ts_guess_path')
    if candidate:
        from cloudra.tools.core.structure_artifacts import read_xyz_atoms
        path = Path(candidate).resolve()
        if not path.is_relative_to(Path(old['run_dir']).resolve()):
            raise ValueError('The selected candidate must be an owned run artifact')
        atoms = read_xyz_atoms(str(path))
        if [symbol for symbol, _ in atoms] != [atom.GetSymbol() for atom in structures.reactant.GetAtoms()]:
            raise ValueError('The selected candidate does not match its confirmed working atom order')
        structures.candidate = with_positions(structures.reactant, [point for _, point in atoms])
    # 旧数组只存在原始离线文件中；新运行记录不保留兼容字段或双写路径。
    for field in ('input_binding', 'seed_molecules', 'current_seed_xyz_path', 'current_seed_mol_path',
        'product_seed_xyz_path', 'product_seed_mol_path', 'current_reactant_prepared_path',
        'current_ts_guess_path', 'effective_reaction_center'):
        old.pop(field, None)
    old.update(format_version=7, input=_input(old['input']), structures=structures.model_dump(mode='json'))
    for attempt in old.get('attempt_history', []):
        if attempt.get('input'):
            attempt['input'] = _input(attempt['input'])
    return TsProcessRecord.model_validate(old).model_dump(mode='json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    arguments = parser.parse_args()
    converted = convert_checkpoint(json.loads(arguments.source.read_text(encoding='utf-8')))
    with arguments.destination.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(converted, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
