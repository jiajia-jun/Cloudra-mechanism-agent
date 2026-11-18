"""Native molecular drafts; all edits delegate to the Agent geometry authority."""
from __future__ import annotations

from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictInt, StrictStr, model_validator

from cloudra.tools.core.geometry import fibonacci_sphere_directions
from cloudra.tools.core.molecule import Molecule, _copy_molecule, read_molecule, serialize_molecule, to_xyz

_BUILDER_ACTIONS = {'add_atom', 'add_group', 'delete_atom', 'atom_state', 'fill_valence'}
_TARGET_VALENCE = 'cloudra_target_valence'
_HYBRIDIZATION = 'cloudra_hybridization'


class EditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    molecule: Molecule | None = None
    action: Literal['coordinate', 'mirror', 'bond', 'replace_group', 'resolve_bonds',
                    'add_atom', 'add_group', 'delete_atom', 'atom_state', 'fill_valence', 'preoptimize']
    atoms: list[int] = Field(default_factory=list)
    value: float | None = Field(default=None, allow_inf_nan=False)
    fixed_side: Literal['first', 'last'] = 'first'
    moving_atoms: list[int] | None = None
    plane: Literal['xy', 'xz', 'yz'] = 'yz'
    order: Literal[0, 1, 1.5, 2, 3] = 1
    smiles: str | None = None
    attachment_atom: int | None = None
    position: tuple[FiniteFloat, FiniteFloat, FiniteFloat] | None = None
    element: StrictStr | None = None
    # RDKit stores the native formal charge as a signed byte.
    formal_charge: StrictInt | None = Field(default=None, ge=-128, le=127)
    # One fill request can place at most 32 explicit hydrogen atoms.
    valence: StrictInt | None = Field(default=None, ge=0, le=32)
    hybridization: Literal['sp', 'sp2', 'sp3'] | None = None
    force_field: Literal['MMFF94', 'UFF'] = 'MMFF94'

    @model_validator(mode='after')
    def valid_edit(self):
        adding = self.action in {'add_atom', 'add_group'}
        if self.molecule is None and (not adding or self.atoms):
            raise ValueError('molecule is required except when placing the first atom or group')
        if self.position is not None and (not adding or self.atoms):
            raise ValueError('position is only valid when placing an unconnected atom or group')
        if adding and (len(self.atoms) > 1 or self.order == 0):
            raise ValueError('placement accepts at most one anchor and a positive order')
        if self.action == 'add_group' and self.order != 1:
            raise ValueError('canvas groups attach with one single bond')
        if self.action == 'add_atom' or (self.action == 'atom_state' and self.element is not None):
            from ase.data import atomic_numbers

            element = self.element.strip().capitalize() if self.element else ''
            if not atomic_numbers.get(element):
                raise ValueError('A chemical element symbol is required')
            self.element = element
        elif self.element is not None:
            raise ValueError('element is only valid for adding or changing an atom')
        if self.action == 'delete_atom' and not self.atoms:
            raise ValueError('delete_atom requires at least one atom')
        if self.action in {'atom_state', 'fill_valence'} and len(self.atoms) != 1:
            raise ValueError(f'{self.action} requires exactly one atom')
        if self.action == 'atom_state':
            if 'formal_charge' in self.model_fields_set and self.formal_charge is None:
                raise ValueError('formal_charge must be an integer when supplied')
        elif self.model_fields_set & {'formal_charge', 'valence', 'hybridization'}:
            raise ValueError('formal_charge, valence and hybridization are only valid for atom_state')
        if 'force_field' in self.model_fields_set and self.action != 'preoptimize':
            raise ValueError('force_field is only valid for preoptimize')
        if self.action == 'preoptimize' and (self.atoms or self.moving_atoms is not None):
            raise ValueError('preoptimize operates on the complete current conformer')
        if self.action == 'coordinate' and (len(self.atoms) not in (2, 3, 4) or self.value is None):
            raise ValueError('coordinate requires 2/3/4 ordered atoms and an absolute value')
        if self.action in {'bond', 'replace_group'} and len(self.atoms) != 2:
            raise ValueError(f'{self.action} requires exactly two ordered atoms')
        if self.action in {'replace_group', 'add_group'} and not self.smiles:
            raise ValueError(f'{self.action} requires smiles')
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


def _local_geometry(mol, atom) -> dict:
    """Idealized seed domains, not an electronic-structure determination.

    Conventional closed-shell main-group valences are deliberately limited here.
    A manual target outside this table, radicals, hypervalence and unresolved
    connectivity remain unknown. Lone pairs occupy domains, never atom vertices.
    """
    override = atom.GetProp(_HYBRIDIZATION) if atom.HasProp(_HYBRIDIZATION) else None
    result = {'hybridization': override, 'hybridization_override': override, 'lone_pairs': None}
    if _graph_status(mol) in {'unresolved', 'distance-inferred'} or atom.GetNumRadicalElectrons():
        return result
    states = {
        ('B', 0): (3, 0), ('B', -1): (4, 0),
        ('C', 0): (4, 0), ('C', 1): (3, 0), ('C', -1): (3, 1),
        ('N', 0): (3, 1), ('N', 1): (4, 0), ('N', -1): (2, 2),
        ('O', 0): (2, 2), ('O', 1): (3, 1), ('O', -1): (1, 3),
        ('Si', 0): (4, 0), ('P', 0): (3, 1), ('P', 1): (4, 0),
        ('S', 0): (2, 2), ('S', -1): (1, 3), ('S', 1): (3, 1),
    }
    state = states.get((atom.GetSymbol(), atom.GetFormalCharge()))
    if state is None:
        return result
    valence, lone_pairs = state
    if _target_valence(atom) not in (None, valence):
        return result
    bonds = list(atom.GetBonds())
    orders = [bond.GetBondTypeAsDouble() for bond in bonds]
    aromatic = any(order == 1.5 for order in orders)
    # Aromatic N has pyridine/pyrrole representations whose 1.5 bond sums do
    # not equal their electron-counting valence. Require a valid aromatic ring.
    if aromatic:
        from rdkit import Chem

        checked = Chem.Mol(mol)
        if Chem.SanitizeMol(checked, catchErrors=True):
            return result
        perceived = checked.GetAtomWithIdx(atom.GetIdx())
        if not perceived.GetIsAromatic():
            return result
        result.update(hybridization=override or 'sp2', lone_pairs=lone_pairs)
        return result
    if (sum(orders) + atom.GetNumExplicitHs() > valence
            or any(order not in (1, 2, 3) for order in orders)):
        return result
    # A donor lone pair adjoining a pi system uses a p orbital (e.g. amide N).
    conjugated = lone_pairs > 0 and any(
        bond.GetBondTypeAsDouble() == 1 and (
            bond.GetOtherAtom(atom).GetIsAromatic()
            or any(other.GetIdx() != bond.GetIdx() and other.GetBondTypeAsDouble() in (1.5, 2, 3)
                   for other in bond.GetOtherAtom(atom).GetBonds())
        ) for bond in bonds
    )
    domains = valence - sum(order - 1 for order in orders) + lone_pairs
    hybridization = {2: 'sp', 3: 'sp2', 4: 'sp3'}.get(domains)
    if conjugated and hybridization == 'sp3':
        hybridization = 'sp2'
    result.update(hybridization=override or hybridization, lone_pairs=lone_pairs)
    return result


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
             **_local_geometry(mol, atom),
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


def _domain_directions(vectors, hybridization: str):
    """Exact ideal-angle candidates when fixed neighbors permit that geometry."""
    import numpy as np

    cosine = {'sp': -1., 'sp2': -.5, 'sp3': -1 / 3}[hybridization]
    lengths = np.linalg.norm(vectors, axis=1)
    unit = vectors[lengths > 1e-9] / lengths[lengths > 1e-9, None]
    if not len(unit):
        return np.asarray(fibonacci_sphere_directions(128)), unit, cosine
    _, singular, vh = np.linalg.svd(unit, full_matrices=True)
    rank = int(np.sum(singular > 1e-9))
    center = np.linalg.lstsq(unit, np.full(len(unit), cosine), rcond=None)[0]
    radius_squared = 1 - float(center @ center)
    if (radius_squared >= -1e-9 and (rank < 3 or radius_squared < 1e-9)
            and np.allclose(unit @ center, cosine, atol=1e-9)):
        radius = max(0., radius_squared) ** .5
        nullspace = vh[rank:]
        if radius_squared < 1e-9 or rank == 3:
            candidates = np.asarray([center])
        elif len(nullspace) == 1:
            candidates = np.asarray([center + radius * nullspace[0], center - radius * nullspace[0]])
        elif len(nullspace) == 2:
            angles = np.arange(128) * (2 * np.pi / 128)
            candidates = center + radius * (np.cos(angles)[:, None] * nullspace[0]
                                            + np.sin(angles)[:, None] * nullspace[1])
        else:
            candidates = np.asarray(fibonacci_sphere_directions(128))
    else:
        # Existing atoms are immovable. Select the closest angular seed and
        # explicitly warn the caller that this does not repair old bond angles.
        candidates = np.asarray(fibonacci_sphere_directions(128))
        if np.linalg.norm(center) > 1e-9:
            candidates = np.vstack((candidates, center / np.linalg.norm(center)))
    lengths = np.linalg.norm(candidates, axis=1)
    if not np.isfinite(lengths).all() or (lengths < 1e-9).any():
        raise ValueError('Local geometry produced an undefined placement direction')
    return candidates / lengths[:, None], unit, cosine


def _initial_position(positions, symbols: list[str], element: str, anchor: int | None, order: float,
                      neighbors: list[int], hybridization: str | None):
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
    if hybridization:
        directions, unit, cosine = _domain_directions(positions[neighbors] - positions[anchor], hybridization)
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
    if hybridization and len(unit):
        angle_error = ((directions @ unit.T - cosine) ** 2).sum(axis=1)
        # Round numerical noise so that clearance breaks genuinely equal fits.
        return tuple(candidates[np.lexsort((-clearance, np.round(angle_error, 12)))[0]])
    return tuple(candidates[clearance.argmax()])


def _append_piece(mol, piece, attachment: int, anchor: int | None, order: float, position=None, outward=None, bond_dir=None):
    """Append an atom or a rigid fragment without moving any existing atoms."""
    from rdkit import Chem

    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates
    from cloudra.tools.core.geometry import rotation_matrix_between

    first = mol.GetNumAtoms()
    result = Chem.CombineMols(mol, piece)
    element = piece.GetAtomWithIdx(attachment).GetSymbol()
    symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    neighbors = []
    hybridization = None
    if anchor is not None:
        neighbors = [atom.GetIdx() for atom in mol.GetAtomWithIdx(anchor).GetNeighbors()]
        result, _ = InternalCoordinates._op_bond(result, {'atoms': [anchor + 1, first + attachment + 1], 'order': order})
        if bond_dir in (Chem.BondDir.ENDUPRIGHT, Chem.BondDir.ENDDOWNRIGHT):
            result.GetBondBetweenAtoms(anchor, first + attachment).SetBondDir(bond_dir)
            Chem.SetBondStereoFromDirections(result)
        hybridization = _local_geometry(result, result.GetAtomWithIdx(anchor))['hybridization']
    local = piece.GetConformer().GetPositions()
    local = local - local[attachment]
    for original, conf in zip(mol.GetConformers(), result.GetConformers(), strict=True):
        coords = original.GetPositions()
        target = position if position is not None else _initial_position(coords, symbols, element, anchor, order, neighbors, hybridization)
        placed = local
        if outward is not None and anchor is not None:
            placed = local @ rotation_matrix_between(outward, coords[anchor] - target).T
        for index, xyz in enumerate(placed + target, first):
            conf.SetAtomPosition(index, xyz)
    result.UpdatePropertyCache(strict=False)
    return result


def _append_atom(mol, element: str, anchor: int | None, order: float, position=None):
    from rdkit import Chem

    piece = Chem.RWMol()
    atom = Chem.Atom(element)
    atom.SetNoImplicit(True)
    piece.AddAtom(atom)
    piece.AddConformer(Chem.Conformer(1))
    return _append_piece(mol, piece, 0, anchor, order, position)


def _edit_builder(mol, request: EditRequest):
    from rdkit import Chem

    if request.action in {'add_atom', 'add_group'}:
        if not mol.GetNumAtoms():
            mol = _empty_molecule()
        anchor = request.atoms[0] - 1 if request.atoms else None
        if request.action == 'add_atom':
            return _append_atom(mol, request.element, anchor, request.order, request.position)
        from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

        marked = connection_smiles(request.smiles, request.attachment_atom)
        piece, index, _, order, outward, bond_dir = InternalCoordinates._embed_substituent_3d(marked)
        if anchor is not None and order != 1:
            raise ValueError('编辑模式添加一根单键，请选择带单键连接点的基团')
        if anchor is None and piece.GetAtomWithIdx(index).GetDegree() == 1 and bond_dir in (
            Chem.BondDir.ENDUPRIGHT, Chem.BondDir.ENDDOWNRIGHT,
        ):
            raise ValueError('此基团的双键立体构型依赖连接原子，请点击已有原子以保留构型')
        return _append_piece(mol, piece, index, anchor, order, request.position, outward, bond_dir)
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
        if request.element is not None and request.element != atom.GetSymbol():
            atom.SetAtomicNum(Chem.GetPeriodicTable().GetAtomicNumber(request.element))
            atom.SetIsotope(0)
        if request.formal_charge is not None:
            atom.SetFormalCharge(request.formal_charge)
        if 'valence' in request.model_fields_set:
            if request.valence is None:
                atom.ClearProp(_TARGET_VALENCE)
            else:
                atom.SetIntProp(_TARGET_VALENCE, request.valence)
        if 'hybridization' in request.model_fields_set:
            if request.hybridization is None:
                atom.ClearProp(_HYBRIDIZATION)
            else:
                atom.SetProp(_HYBRIDIZATION, request.hybridization)
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
    for _ in range(remaining):
        mol = _append_atom(mol, 'H', anchor, 1)
    return mol


def _preoptimize(mol, engine: str):
    import numpy as np
    from rdkit import Chem

    from cloudra.tools.core.structure_builder import BuildStrategy, _make_force_field

    if not mol.GetNumAtoms() or not mol.GetNumConformers():
        raise ValueError('preoptimize requires a nonempty molecule with coordinates')
    if _graph_status(mol) in {'unresolved', 'distance-inferred'}:
        raise ValueError('preoptimize requires a resolved, declared bond-order graph')
    if mol.HasProp('cloudra_multiplicity') and mol.GetIntProp('cloudra_multiplicity') != 1:
        raise ValueError('preoptimize does not support open-shell electronic states')
    if mol.HasProp('cloudra_total_charge') and mol.GetIntProp('cloudra_total_charge') != Chem.GetFormalCharge(mol):
        raise ValueError('preoptimize requires atom formal charges consistent with the declared total charge')
    # Sanitize/type a private working graph. MMFF typing changes aromatic flags;
    # only its optimized coordinates are ever copied back to the exact draft.
    working = Chem.Mol(mol)
    if Chem.SanitizeMol(working, catchErrors=True):
        raise ValueError('preoptimize requires a chemically valid bond-order and formal-charge graph')
    if any(original.GetFormalCharge() != checked.GetFormalCharge()
           for original, checked in zip(mol.GetAtoms(), working.GetAtoms(), strict=True)):
        raise ValueError('preoptimize cannot silently repair formal charges; correct the declared graph first')
    if any(atom.GetNumRadicalElectrons() for graph in (mol, working) for atom in graph.GetAtoms()):
        raise ValueError('preoptimize does not support radical or incomplete-valence graphs')
    if any(atom.GetNumImplicitHs() or atom.GetNumExplicitHs() for atom in working.GetAtoms()):
        raise ValueError('preoptimize requires every hydrogen to be an explicit atom; fill valence first')
    positions = working.GetConformer().GetPositions()
    if not np.isfinite(positions).all():
        raise ValueError('preoptimize requires finite coordinates')
    conf_id = working.GetConformer().GetId()
    try:
        force_field = _make_force_field(working, conf_id, engine)
        if force_field is None:
            raise ValueError(f'{engine} parameters are unavailable for this graph; no fallback was used')
        force_field.Initialize()
        initial_energy = float(force_field.CalcEnergy())
        status = int(force_field.Minimize(maxIts=BuildStrategy().max_optimization_steps))
        final_energy = float(force_field.CalcEnergy())
    except (RuntimeError, OverflowError) as exc:
        raise ValueError(f'{engine} preoptimization failed: {exc}') from exc
    optimized = working.GetConformer(conf_id).GetPositions()
    if status not in (0, 1) or not np.isfinite([initial_energy, final_energy]).all() or not np.isfinite(optimized).all():
        raise ValueError(f'{engine} preoptimization returned invalid coordinates, energy or status')
    for index, position in enumerate(optimized):
        mol.GetConformer().SetAtomPosition(index, position)
    moved = [index + 1 for index in range(len(positions)) if not np.array_equal(positions[index], optimized[index])]
    warnings = ['Molecular force-field preoptimization is not quantum-chemical optimization or scientific validation.']
    if len(Chem.GetMolFrags(working)) > 1:
        warnings.append('Interfragment interactions are excluded; this does not optimize the relative arrangement of components.')
    if status == 1:
        warnings.append('The force-field iteration limit was reached without convergence; the returned coordinates are the last iterate.')
    return mol, {'moved_atoms': moved, 'warnings': warnings, 'optimization': {
        'force_field': engine, 'converged': status == 0, 'initial_energy': initial_energy,
        'final_energy': final_energy, 'energy_unit': 'kcal/mol',
    }}


def edit_geometry(request: EditRequest | dict) -> dict:
    from rdkit import Chem

    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    request = request if isinstance(request, EditRequest) else EditRequest.model_validate(request)
    mol = _identities(_copy_molecule(request.molecule) if request.molecule is not None else _empty_molecule())
    before = {a.GetProp('cloudra_atom_id'): a.GetIdx() + 1 for a in mol.GetAtoms()}
    if request.action in _BUILDER_ACTIONS:
        result = _edit_builder(mol, request)
        summary = {}
        if request.atoms and request.action in {'add_atom', 'add_group', 'fill_valence', 'atom_state'}:
            state = _local_geometry(result, result.GetAtomWithIdx(request.atoms[0] - 1))
            label = state['hybridization']
            summary['warnings'] = [
                f'Local {label} is an idealized geometry assumption; existing atom coordinates and bond angles are unchanged. '
                'Use explicit preoptimization to relax the complete geometry.' if label else
                'Local geometry is unknown for this electronic state or graph; placement uses spatial clearance only. '
                'Specify hybridization explicitly if a local geometry is intended.'
            ]
        if (request.action in {'add_atom', 'add_group', 'delete_atom'} and result.GetNumAtoms()
                and _graph_status(result) not in {'unresolved', 'distance-inferred'}):
            result.SetProp('cloudra_graph_status', 'edited')
    elif request.action == 'preoptimize':
        result, summary = _preoptimize(mol, request.force_field)
    elif request.action == 'resolve_bonds':
        result, source, warnings = InternalCoordinates._resolve_molecule(mol, None)
        summary = {'moved_atoms': [], 'bond_source': source, 'warnings': warnings}
    else:
        op = request.model_dump(exclude={'molecule', 'action', 'force_field', 'hybridization'}, exclude_none=True)
        op['type'] = request.action
        if request.action == 'replace_group':
            op['smiles'] = connection_smiles(request.smiles, request.attachment_atom)
            op['bond'] = request.atoms if request.fixed_side == 'first' else request.atoms[::-1]
        result, summary = InternalCoordinates._transform_molecule(mol, op)
    if request.action in _BUILDER_ACTIONS | {'bond', 'replace_group', 'resolve_bonds'}:
        _check_valence_targets(result)
    placed_bonds = request.action == 'add_group' or (request.action == 'add_atom' and bool(request.atoms))
    if request.action == 'bond' or (placed_bonds and _graph_status(result) == 'unresolved'):
        result.SetBoolProp('cloudra_manual_bonds', True)
    if (request.action in {'atom_state', 'delete_atom', 'replace_group', 'add_group'}
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
    if 'optimization' in summary:
        view['optimization'] = summary['optimization']
    return view


def coordinate_value(mol, atoms: list[int]) -> float:
    """Measure one ordered 1-based coordinate without changing the structure."""
    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    indexes = [InternalCoordinates._transform_atom_index(i, mol.GetNumAtoms(), 'coordinate atoms') for i in atoms]
    if len(set(indexes)) != len(indexes):
        raise ValueError('coordinate atoms must be distinct')
    return InternalCoordinates._coordinate_value(mol.GetConformer().GetPositions(), indexes)
