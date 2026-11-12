"""Native molecular drafts; all edits delegate to the Agent geometry authority."""
from __future__ import annotations

from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from cloudra.tools.core.geometry import fibonacci_sphere_directions
from cloudra.tools.core.molecule import Molecule, _copy_molecule, read_molecule, serialize_molecule, to_xyz

_BUILDER_ACTIONS = {'add_atom', 'delete_atom', 'atom_state', 'fill_valence'}
_TARGET_VALENCE = 'cloudra_target_valence'


class EditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    molecule: Molecule | None = None
    action: Literal['coordinate', 'mirror', 'bond', 'replace_group', 'resolve_bonds',
                    'add_atom', 'delete_atom', 'atom_state', 'fill_valence']
    atoms: list[int] = Field(default_factory=list)
    value: float | None = Field(default=None, allow_inf_nan=False)
    fixed_side: Literal['first', 'last'] = 'first'
    moving_atoms: list[int] | None = None
    plane: Literal['xy', 'xz', 'yz'] = 'yz'
    order: Literal[0, 1, 1.5, 2, 3] = 1
    smiles: str | None = None
    attachment_atom: int | None = None
    element: StrictStr | None = None
    # RDKit stores the native formal charge as a signed byte.
    formal_charge: StrictInt | None = Field(default=None, ge=-128, le=127)
    # One fill request can place at most 32 explicit hydrogen atoms.
    valence: StrictInt | None = Field(default=None, ge=0, le=32)

    @model_validator(mode='after')
    def valid_edit(self):
        if self.molecule is None and (self.action != 'add_atom' or self.atoms):
            raise ValueError('molecule is required except when adding the first atom without an anchor')
        if self.action == 'add_atom':
            from ase.data import atomic_numbers

            element = self.element.strip().capitalize() if self.element else ''
            if not atomic_numbers.get(element):
                raise ValueError('add_atom requires a chemical element symbol')
            if len(self.atoms) > 1 or (self.atoms and self.order == 0):
                raise ValueError('add_atom accepts one anchor with a positive bond order, or no anchor')
            self.element = element
        elif self.element is not None:
            raise ValueError('element is only valid for add_atom')
        if self.action == 'delete_atom' and not self.atoms:
            raise ValueError('delete_atom requires at least one atom')
        if self.action in {'atom_state', 'fill_valence'} and len(self.atoms) != 1:
            raise ValueError(f'{self.action} requires exactly one atom')
        if self.action == 'atom_state':
            if 'formal_charge' in self.model_fields_set and self.formal_charge is None:
                raise ValueError('formal_charge must be an integer when supplied')
        elif self.model_fields_set & {'formal_charge', 'valence'}:
            raise ValueError('formal_charge and valence are only valid for atom_state')
        if self.action == 'coordinate' and (len(self.atoms) not in (2, 3, 4) or self.value is None):
            raise ValueError('coordinate requires 2/3/4 ordered atoms and an absolute value')
        if self.action in {'bond', 'replace_group'} and len(self.atoms) != 2:
            raise ValueError(f'{self.action} requires exactly two ordered atoms')
        if self.action == 'replace_group' and not self.smiles:
            raise ValueError('replace_group requires smiles')
        atom_count = self.molecule.GetNumAtoms() if self.molecule is not None else 0
        for values in (self.atoms, self.moving_atoms):
            if values is not None and (len(set(values)) != len(values) or any(not 1 <= i <= atom_count for i in values)):
                raise ValueError('atom indices must be distinct, valid 1-based indices')
        if self.moving_atoms == []:
            raise ValueError('moving_atoms must contain at least one atom')
        return self


def _identities(mol):
    for atom in mol.GetAtoms():
        if not atom.HasProp('cloudra_atom_id'):
            atom.SetProp('cloudra_atom_id', uuid4().hex)
    return mol


def _graph_status(mol) -> str:
    return mol.GetProp('cloudra_graph_status') if mol.HasProp('cloudra_graph_status') else 'declared'


def _target_valence(atom) -> int | None:
    return atom.GetIntProp(_TARGET_VALENCE) if atom.HasProp(_TARGET_VALENCE) else None


def _bond_valence(atom) -> float:
    return sum((bond.GetBondTypeAsDouble() for bond in atom.GetBonds()), 0.0)


def _check_valence_targets(mol) -> None:
    for atom in mol.GetAtoms():
        target = _target_valence(atom)
        if target is not None and (actual := _bond_valence(atom)) > target:
            raise ValueError(f'Atom {atom.GetIdx() + 1} ({atom.GetSymbol()}) has bond valence {actual:g} above target valence {target}')


def geometry_view(mol) -> dict:
    """Coordinates plus the declared graph; viewing never guesses connectivity."""
    mol = _identities(_copy_molecule(mol))
    positions = mol.GetConformer().GetPositions()
    return {
        'molecule': serialize_molecule(mol),
        'xyz': to_xyz(mol),
        'atoms': [
            {'index': atom.GetIdx() + 1, 'symbol': atom.GetSymbol(),
             'atom_id': atom.GetProp('cloudra_atom_id'),
             'formal_charge': atom.GetFormalCharge(), 'target_valence': _target_valence(atom),
             'bond_valence': _bond_valence(atom),
             'x': float(pos[0]), 'y': float(pos[1]), 'z': float(pos[2])}
            for atom, pos in zip(mol.GetAtoms(), positions, strict=True)
        ],
        'bonds': [
            {'atom1': bond.GetBeginAtomIdx() + 1, 'atom2': bond.GetEndAtomIdx() + 1,
             'order': float(bond.GetBondTypeAsDouble())}
            for bond in mol.GetBonds()
        ],
        'graph_status': _graph_status(mol),
        'manual_bonds': bool(mol.HasProp('cloudra_manual_bonds')) and mol.GetBoolProp('cloudra_manual_bonds'),
    }


def create_geometry(input_text: str, input_format: str) -> dict:
    if input_format.lower() != 'smiles':
        return geometry_view(read_molecule(input_text=input_text, input_format=input_format))
    from rdkit import Chem

    from cloudra.tools.core.structure_builder import (
        BuildStrategy,
        PreparationRequest,
        StructureInput,
        prepare_structure,
    )

    graph = Chem.MolFromSmiles(input_text)
    if graph is None:
        raise ValueError('Invalid SMILES')
    with TemporaryDirectory(prefix='cloudra-workbench-build-') as directory:
        prepared = prepare_structure(PreparationRequest(
            structure=StructureInput(kind='smiles', value=input_text), output_dir=directory,
            total_charge=Chem.GetFormalCharge(graph), strategy=BuildStrategy(optimize=False),
        ))
        if prepared.mol is None or not prepared.has_coordinates or not prepared.mol.GetNumConformers():
            raise ValueError(f'Cannot build SMILES geometry: {prepared.status}')
        view = geometry_view(prepared.mol)
        view['warnings'] = ['SMILES geometry is a generated seed; it has not been optimized.']
        return view


def connection_smiles(smiles: str, attachment_atom: int | None = None) -> str:
    """Normalize an explicit attachment marker, or mark the user-selected atom."""
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError('Invalid fragment SMILES')
    if len(Chem.GetMolFrags(mol)) != 1:
        raise ValueError('A fragment must be one connected group')
    markers = [a for a in mol.GetAtoms() if a.GetAtomicNum() == 0]
    if not markers:
        if attachment_atom is None or not 1 <= attachment_atom <= mol.GetNumAtoms():
            raise ValueError('Unmarked SMILES requires attachment_atom (1-based connection atom)')
        rw = Chem.RWMol(mol)
        selected = rw.GetAtomWithIdx(attachment_atom - 1)
        # Replace one implicit/declared hydrogen by the explicitly requested connection.
        if selected.GetNumExplicitHs():
            selected.SetNumExplicitHs(selected.GetNumExplicitHs() - 1)
        marker = rw.AddAtom(Chem.Atom(0))
        rw.AddBond(attachment_atom - 1, marker, Chem.BondType.SINGLE)
        mol = rw.GetMol()
        Chem.SanitizeMol(mol)
    elif len(markers) != 1 or markers[0].GetDegree() != 1:
        raise ValueError('Fragment requires exactly one terminal [*] connection marker')
    return Chem.MolToSmiles(mol)


def _empty_molecule():
    from rdkit import Chem

    mol = Chem.RWMol()
    conformer = Chem.Conformer(0)
    conformer.Set3D(True)
    mol.AddConformer(conformer, assignId=True)
    return mol.GetMol()


def _initial_position(positions, symbols: list[str], element: str, anchor: int | None, order: float,
                      tetrahedral_neighbors: list[int]):
    import numpy as np

    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    if len(positions) == 0:
        return (0., 0., 0.)
    if not np.isfinite(positions).all():
        raise ValueError('Adding an atom requires finite draft coordinates')
    if anchor is None:
        clearances = [InternalCoordinates._van_der_waals_sum(element, symbol) for symbol in symbols]
        position = positions[positions[:, 0].argmax()].copy()
        position[0] = np.max(positions[:, 0] + clearances)
        return tuple(position)

    length = InternalCoordinates._reference_bond_length(symbols[anchor], element, order)
    directions = np.asarray(fibonacci_sphere_directions(128))
    candidates = positions[anchor] + length * directions
    distances = np.linalg.norm(candidates[:, None] - positions, axis=2)
    usable = (distances > 1e-9).all(axis=1)
    if not usable.any():
        raise ValueError('No noncoincident initial placement at the reference bond length')
    candidates, directions, distances = candidates[usable], directions[usable], distances[usable]
    others = [index for index in range(len(symbols)) if index != anchor]
    if not others:
        return tuple(candidates[0])
    clearances = [InternalCoordinates._reference_bond_length(element, symbols[index], 1) for index in others]
    clearance = np.min(distances[:, others] / clearances, axis=1)
    if tetrahedral_neighbors:
        vectors = positions[tetrahedral_neighbors] - positions[anchor]
        lengths = np.linalg.norm(vectors, axis=1)
        defined = lengths > 1e-9
        unit = vectors[defined] / lengths[defined, None]
        angle_error = ((directions @ unit.T + 1 / 3) ** 2).sum(axis=1)
        return tuple(candidates[np.lexsort((-clearance, angle_error))[0]])
    return tuple(candidates[clearance.argmax()])


def _append_atom(mol, element: str, anchor: int | None, order: float, *, tetrahedral: bool = False):
    from rdkit import Chem

    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    rw = Chem.RWMol(mol)
    symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    neighbors = ([atom.GetIdx() for atom in mol.GetAtomWithIdx(anchor).GetNeighbors()]
                 if tetrahedral and anchor is not None else [])
    positions = [
        _initial_position(conf.GetPositions(), symbols, element, anchor, order, neighbors)
        for conf in rw.GetConformers()
    ]
    atom = Chem.Atom(element)
    atom.SetNoImplicit(True)
    index = rw.AddAtom(atom)
    for conf, position in zip(rw.GetConformers(), positions, strict=True):
        conf.SetAtomPosition(index, position)
    result = rw.GetMol()
    if anchor is not None:
        result, _ = InternalCoordinates._op_bond(result, {'atoms': [anchor + 1, index + 1], 'order': order})
    else:
        result.UpdatePropertyCache(strict=False)
    return result


def _edit_builder(mol, request: EditRequest):
    from rdkit import Chem

    if request.action == 'add_atom':
        if not mol.GetNumAtoms():
            mol = _empty_molecule()
        anchor = request.atoms[0] - 1 if request.atoms else None
        return _append_atom(mol, request.element, anchor, request.order)
    if request.action == 'delete_atom':
        if len(request.atoms) == mol.GetNumAtoms():
            return _empty_molecule()
        rw = Chem.RWMol(mol)
        for index in sorted(request.atoms, reverse=True):
            rw.RemoveAtom(index - 1)
        result = rw.GetMol()
        result.UpdatePropertyCache(strict=False)
        Chem.FastFindRings(result)
        return result
    anchor = request.atoms[0] - 1
    atom = mol.GetAtomWithIdx(anchor)
    if request.action == 'atom_state':
        if request.formal_charge is not None:
            atom.SetFormalCharge(request.formal_charge)
        if 'valence' in request.model_fields_set:
            if request.valence is None:
                atom.ClearProp(_TARGET_VALENCE)
            else:
                atom.SetIntProp(_TARGET_VALENCE, request.valence)
        mol.UpdatePropertyCache(strict=False)
        return mol
    if _graph_status(mol) == 'unresolved':
        raise ValueError('Graph unresolved: resolve bonds before filling valence')
    target = _target_valence(atom)
    if target is None:
        raise ValueError('fill_valence requires an explicit target valence for the selected atom')
    actual = _bond_valence(atom)
    if not actual.is_integer() or target <= actual:
        raise ValueError('fill_valence requires a positive whole number of remaining bonds')
    # Materialize hydrogens as actual atom vertices, including on imported implicit-H atoms.
    atom.SetNumExplicitHs(0)
    atom.SetNoImplicit(True)
    remaining = target - int(actual)
    tetrahedral = atom.GetDegree() + remaining == 4
    for _ in range(remaining):
        mol = _append_atom(mol, 'H', anchor, 1, tetrahedral=tetrahedral)
    return mol


def edit_geometry(request: EditRequest | dict) -> dict:
    from rdkit import Chem

    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    request = request if isinstance(request, EditRequest) else EditRequest.model_validate(request)
    mol = _identities(_copy_molecule(request.molecule) if request.molecule is not None else _empty_molecule())
    before = {a.GetProp('cloudra_atom_id'): a.GetIdx() + 1 for a in mol.GetAtoms()}
    if request.action in _BUILDER_ACTIONS:
        result = _edit_builder(mol, request)
        summary = {}
        if request.action in {'add_atom', 'delete_atom'} and result.GetNumAtoms() and _graph_status(result) != 'unresolved':
            result.SetProp('cloudra_graph_status', 'edited')
    elif request.action == 'resolve_bonds':
        result, source, warnings = InternalCoordinates._resolve_molecule(mol, None)
        summary = {'moved_atoms': [], 'bond_source': source, 'warnings': warnings}
    else:
        op = request.model_dump(exclude={'molecule', 'action'}, exclude_none=True)
        op['type'] = request.action
        if request.action == 'replace_group':
            op['smiles'] = connection_smiles(request.smiles, request.attachment_atom)
            op['bond'] = request.atoms if request.fixed_side == 'first' else request.atoms[::-1]
        result, summary = InternalCoordinates._transform_molecule(mol, op)
    if request.action in _BUILDER_ACTIONS | {'bond', 'replace_group', 'resolve_bonds'}:
        _check_valence_targets(result)
    if request.action == 'bond' or (request.action == 'add_atom' and request.atoms and _graph_status(result) == 'unresolved'):
        result.SetBoolProp('cloudra_manual_bonds', True)
    if (request.action in {'atom_state', 'delete_atom', 'replace_group'}
            and _graph_status(mol) not in {'unresolved', 'distance-inferred'} and result.HasProp('cloudra_total_charge')):
        result.SetIntProp('cloudra_total_charge', Chem.GetFormalCharge(result))
    result = _identities(result)
    after = {a.GetProp('cloudra_atom_id'): a.GetIdx() + 1 for a in result.GetAtoms()}
    view = geometry_view(result)
    view['changes'] = {
        'deleted_atom_ids': [identity for identity in before if identity not in after],
        'deleted_atoms': [index for identity, index in before.items() if identity not in after],
        'index_map': {str(index): after[identity] for identity, index in before.items() if identity in after},
        'moved_atoms': summary.get('moved_atoms', []),
    }
    if request.action == 'replace_group':
        view['changes']['fragment_smiles'] = op['smiles']
    if summary.get('warnings'):
        view['warnings'] = summary['warnings']
    return view


def coordinate_value(mol, atoms: list[int]) -> float:
    """Measure one ordered 1-based coordinate without changing the structure."""
    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    indexes = [InternalCoordinates._transform_atom_index(i, mol.GetNumAtoms(), 'coordinate atoms') for i in atoms]
    if len(set(indexes)) != len(indexes):
        raise ValueError('coordinate atoms must be distinct')
    return InternalCoordinates._coordinate_value(mol.GetConformer().GetPositions(), indexes)
