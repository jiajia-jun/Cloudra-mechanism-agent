"""Native molecular drafts; all edits delegate to the Agent geometry authority."""
from __future__ import annotations

from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloudra.tools.core.molecule import Molecule, _copy_molecule, read_molecule, serialize_molecule, to_xyz


class EditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    molecule: Molecule
    action: Literal['coordinate', 'mirror', 'bond', 'replace_group', 'resolve_bonds']
    atoms: list[int] = Field(default_factory=list)
    value: float | None = Field(default=None, allow_inf_nan=False)
    fixed_side: Literal['first', 'last'] = 'first'
    moving_atoms: list[int] | None = None
    plane: Literal['xy', 'xz', 'yz'] = 'yz'
    order: Literal[0, 1, 1.5, 2, 3] = 1
    smiles: str | None = None
    attachment_atom: int | None = None

    @model_validator(mode='after')
    def valid_edit(self):
        if self.action == 'coordinate' and (len(self.atoms) not in (2, 3, 4) or self.value is None):
            raise ValueError('coordinate requires 2/3/4 ordered atoms and an absolute value')
        if self.action in {'bond', 'replace_group'} and len(self.atoms) != 2:
            raise ValueError(f'{self.action} requires exactly two ordered atoms')
        if self.action == 'replace_group' and not self.smiles:
            raise ValueError('replace_group requires smiles')
        for values in (self.atoms, self.moving_atoms):
            if values is not None and (len(set(values)) != len(values)
                                      or any(not 1 <= i <= self.molecule.GetNumAtoms() for i in values)):
                raise ValueError('atom indices must be distinct, valid 1-based indices')
        if self.moving_atoms == []:
            raise ValueError('moving_atoms must contain at least one atom')
        return self


def _identities(mol):
    for atom in mol.GetAtoms():
        if not atom.HasProp('cloudra_atom_id'):
            atom.SetProp('cloudra_atom_id', uuid4().hex)
    return mol


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
             'x': float(pos[0]), 'y': float(pos[1]), 'z': float(pos[2])}
            for atom, pos in zip(mol.GetAtoms(), positions, strict=True)
        ],
        'bonds': [
            {'atom1': bond.GetBeginAtomIdx() + 1, 'atom2': bond.GetEndAtomIdx() + 1,
             'order': float(bond.GetBondTypeAsDouble())}
            for bond in mol.GetBonds()
        ],
        'graph_status': mol.GetProp('cloudra_graph_status') if mol.HasProp('cloudra_graph_status') else 'declared',
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


def edit_geometry(request: EditRequest | dict) -> dict:
    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    request = request if isinstance(request, EditRequest) else EditRequest.model_validate(request)
    mol = _identities(_copy_molecule(request.molecule))
    before = {a.GetProp('cloudra_atom_id'): a.GetIdx() + 1 for a in mol.GetAtoms()}
    if request.action == 'resolve_bonds':
        result, source, warnings = InternalCoordinates._resolve_molecule(mol, None)
        summary = {'moved_atoms': [], 'bond_source': source, 'warnings': warnings}
    else:
        op = request.model_dump(exclude={'molecule', 'action'}, exclude_none=True)
        op['type'] = request.action
        if request.action == 'replace_group':
            op['smiles'] = connection_smiles(request.smiles, request.attachment_atom)
            op['bond'] = request.atoms if request.fixed_side == 'first' else request.atoms[::-1]
        result, summary = InternalCoordinates._transform_molecule(mol, op)
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
