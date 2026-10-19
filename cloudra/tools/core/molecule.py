"""Geometry views and coordinate replacement for RDKit molecules."""

import base64
import math
from io import BytesIO, StringIO
from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer


def serialize_molecule(mol) -> str:
    """Persist native molecular state, including user properties and exact coordinates."""
    from rdkit import Chem

    flags = (Chem.PropertyPickleOptions.AllProps ^ Chem.PropertyPickleOptions.ComputedProps) | Chem.PropertyPickleOptions.CoordsAsDouble
    return base64.b64encode(mol.ToBinary(flags)).decode("ascii")


def _copy_molecule(value):
    from rdkit import Chem

    if isinstance(value, str):
        try:
            return Chem.Mol(base64.b64decode(value, validate=True))
        except (ValueError, RuntimeError) as exc:
            raise ValueError("invalid serialized native molecule state") from exc
    if not isinstance(value, Chem.Mol):
        raise ValueError("a molecule or its serialized native state is required")
    return Chem.Mol(value)


Molecule = Annotated[Any, BeforeValidator(_copy_molecule), PlainSerializer(serialize_molecule, return_type=str, when_used="json")]


def copy_conformer(mol, conf_id: int = -1):
    """Copy a molecule with its selected conformer, retaining all molecular properties."""
    from rdkit import Chem

    out = Chem.Mol(mol)
    conf = Chem.Conformer(mol.GetConformer(conf_id))
    out.RemoveAllConformers()
    out.AddConformer(conf, assignId=True)
    return out


def renumber_atoms(mol, order):
    """Copy and reorder atoms without discarding molecule-level properties."""
    from rdkit import Chem

    out = Chem.RenumberAtoms(mol, order)
    pairs = [(mol, out), *zip(mol.GetConformers(), out.GetConformers(), strict=True)]
    for source, target in pairs:
        for name, value in source.GetPropsAsDict(includePrivate=True, includeComputed=False, autoConvertStrings=False).items():
            if isinstance(value, bool):
                target.SetBoolProp(name, value)
            elif isinstance(value, int):
                if value > 2**31 - 1:
                    target.SetUnsignedProp(name, value)
                else:
                    target.SetIntProp(name, value)
            elif isinstance(value, float):
                target.SetDoubleProp(name, value)
            else:
                target.SetProp(name, value)
    return out


def _cartesian_atoms(rows, *, source):
    from ase import Atoms
    from ase.data import atomic_numbers

    symbols, positions = [], []
    for index, line in enumerate(rows, 1):
        tokens = line.split()
        if len(tokens) != 4:
            raise ValueError(f"{source}: expected Cartesian 'element x y z' at atom {index}; Z-matrix and freeze codes are unsupported")
        if tokens[0] not in atomic_numbers or atomic_numbers[tokens[0]] == 0:
            raise ValueError(f"{source}: unsupported atom {tokens[0]!r}; provide plain element symbols without isotope/dummy annotations")
        try:
            position = [float(value.replace('D', 'E').replace('d', 'e')) for value in tokens[1:]]
        except ValueError as exc:
            raise ValueError(f"{source}: invalid Cartesian coordinates at atom {index}") from exc
        if not all(math.isfinite(value) for value in position):
            raise ValueError(f"{source}: Cartesian coordinates must be finite at atom {index}")
        symbols.append(tokens[0])
        positions.append(position)
    if not symbols:
        raise ValueError(f"{source}: explicit Cartesian geometry is missing; checkpoint geometry is unsupported")
    return Atoms(symbols=symbols, positions=positions)


def _read_gaussian_structure(text):
    """Read one explicit Cartesian section, normalizing declared units to Angstrom."""
    from cloudra.tools.core.calculation_intent import native_tokens

    lines = [line.strip() for line in text.splitlines()]
    if any(line.lower() == '--link1--' for line in lines):
        raise ValueError("Gaussian Link1/multiple jobs are unsupported; provide one explicit Cartesian structure or convert the intended geometry to XYZ")
    index = 0
    while index < len(lines) and (not lines[index] or lines[index].startswith('%')):
        index += 1
    if index == len(lines) or not lines[index].startswith('#'):
        raise ValueError("Gaussian input is missing its route section; provide a single Cartesian input or XYZ")
    route = []
    while index < len(lines) and lines[index]:
        route.append(lines[index])
        index += 1
    source_units = None
    unit_names = {'angstrom': 'angstrom', 'angstroms': 'angstrom', 'ang': 'angstrom',
                  'bohr': 'bohr', 'au': 'bohr', 'a.u.': 'bohr'}
    for token in native_tokens(' '.join(route).lstrip('#')):
        key, separator, value = token.partition('=')
        if not separator and '(' in token:
            key, _, value = token.partition('(')
        options = {option.strip() for option in value.strip('()').split(',')}
        if key == 'opt' and options & {'qst2', 'qst3'}:
            raise ValueError("Gaussian QST2/QST3 jobs contain multiple geometries; provide the intended single Cartesian structure or XYZ")
        if key == 'geom' and options & {'check', 'checkpoint', 'allcheck', 'allcheckpoint'}:
            raise ValueError("Gaussian checkpoint geometry is unsupported; provide explicit Cartesian coordinates or an exported XYZ")
        if key == 'units':
            unit = unit_names.get(next(iter(options))) if len(options) == 1 else None
            if unit is None:
                raise ValueError(f"Gaussian units {value!r} are unsupported; provide Cartesian coordinates in Angstrom or Bohr")
            if source_units is not None and unit != source_units:
                raise ValueError("Conflicting Gaussian units declarations; provide one unambiguous coordinate unit")
            source_units = unit
    while index < len(lines) and not lines[index]:
        index += 1
    # The title is a complete section, not any line containing two integers.
    while index < len(lines) and lines[index]:
        index += 1
    while index < len(lines) and not lines[index]:
        index += 1
    try:
        tokens = lines[index].split()
        if len(tokens) != 2:
            raise ValueError
        charge, multiplicity = map(int, tokens)
    except (IndexError, ValueError) as exc:
        raise ValueError("Gaussian charge and multiplicity must be two integers after the title section") from exc
    if multiplicity <= 0:
        raise ValueError("Gaussian multiplicity must be positive")
    index += 1
    end = index
    while end < len(lines) and lines[end]:
        end += 1
    atoms = _cartesian_atoms(lines[index:end], source='Gaussian')
    if source_units == 'bohr':
        from ase.units import Bohr

        atoms.positions *= Bohr
    return atoms, charge, multiplicity, source_units or 'angstrom'


def _read_xyz_structure(text):
    import ase.io
    from ase.io.extxyz import XYZError

    lines = text.lstrip('\r\n').splitlines()
    if not lines:
        raise ValueError("XYZ input is empty; provide XYZ, MOL/SDF, or a single Gaussian Cartesian input")
    try:
        count = int(lines[0].strip())
    except ValueError:
        return _cartesian_atoms([line for line in lines if line.strip()], source='XYZ format')
    if count <= 0:
        raise ValueError("XYZ requires a positive atom count")
    atoms = None
    try:
        # ASE owns EXTXYZ property ordering and the existing final-frame rule.
        for atoms in ase.io.iread(StringIO('\n'.join(lines)), format='extxyz'):
            if len(atoms) == 0 or any(number == 0 for number in atoms.numbers):
                raise ValueError("XYZ requires real elements and a positive atom count")
            if not all(math.isfinite(value) for point in atoms.positions for value in point):
                raise ValueError("XYZ coordinates must be finite")
    except (ValueError, IndexError, KeyError, XYZError) as exc:
        raise ValueError(f"Invalid XYZ format: {exc}; check the atom count, comment line, and Cartesian rows") from exc
    if atoms is None:
        raise ValueError("XYZ input has no coordinate frame")
    return atoms


def _looks_like_gaussian(text):
    sections = [[]]
    for line in text.splitlines():
        if line.strip():
            sections[-1].append(line.strip())
        elif sections[-1]:
            sections.append([])
    route = [line for line in sections[0] if not line.startswith('%')]
    if not route or not route[0].startswith('#'):
        return False
    head = route[0][1:].strip().lower().split()
    if not head:
        return False
    key = head[0].partition('=')[0].partition('(')[0]
    if len(route) != len(sections[0]) or key in {'p', 'n', 't', 'geom', 'units', 'opt', 'freq', 'irc'}:
        return True
    if len(sections) < 3 or not sections[2] or len(sections[2][0].split()) != 2:
        return False
    try:
        tuple(map(int, sections[2][0].split()))
    except ValueError:
        return False
    return True


def read_molecule(input_path=None, input_text=None, input_format="auto", charge=None):
    """Read a declared graph or coordinate-only Mol; never infer bonds while converting."""
    from rdkit import Chem

    if input_path:
        try:
            text = Path(input_path).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Input structure file does not exist: {input_path}; check the resolved path or create the structure first") from exc
    elif input_text:
        text = input_text
    else:
        raise ValueError("Must provide input_path or input_text")
    fmt = input_format
    native_charge = native_multiplicity = native_units = None
    if fmt == "auto":
        if input_path:
            fmt = Path(input_path).suffix.lower().lstrip(".")
            if fmt not in {"mol", "sdf", "xyz"}:
                from ase.io.formats import extension2format

                native_format = extension2format.get(fmt)
                fmt = native_format.name if native_format else "auto"
        if fmt in {'auto', 'xyz', 'gaussian-in'}:
            lines = text.splitlines()
            counts = lines[3].split() if len(lines) > 3 else []
            if any(token in {"V2000", "V3000"} for token in counts):
                fmt = "sdf" if any(line.strip() == "$$$$" for line in lines) else "mol"
            elif _looks_like_gaussian(text):
                fmt = 'gaussian-in'
            elif fmt == 'auto':
                fmt = "xyz"
    elif fmt == 'xyz' and _looks_like_gaussian(text):
        raise ValueError("Gaussian content does not match input_format='xyz'; use input_format='auto' for a single Cartesian Gaussian input")
    if fmt == 'gaussian-in':
        atoms, native_charge, native_multiplicity, native_units = _read_gaussian_structure(text)
        if charge is not None and charge != native_charge:
            raise ValueError(f"Gaussian charge mismatch: declared charge {charge} differs from native charge {native_charge}")
        mol = from_ase(atoms)
    elif fmt == "mol":
        mol = Chem.MolFromMolBlock(text, removeHs=False)
    elif fmt == "sdf":
        mol = next(Chem.ForwardSDMolSupplier(BytesIO(text.encode("utf-8")), removeHs=False), None)
    else:
        import ase.io

        mol = from_ase(_read_xyz_structure(text) if fmt == 'xyz' else ase.io.read(StringIO(text), format=fmt or None))
    if fmt not in {'mol', 'sdf'}:
        mol.SetIntProp("cloudra_total_charge", native_charge if native_charge is not None else charge if charge is not None else 0)
        mol.SetProp("cloudra_graph_status", "unresolved")
        if native_multiplicity is not None:
            mol.SetIntProp('cloudra_multiplicity', native_multiplicity)
            mol.SetProp('cloudra_coordinate_units', 'angstrom')
            mol.SetProp('cloudra_source_coordinate_units', native_units)
    if mol is None:
        raise ValueError(f"Could not parse {fmt.upper()} molecule")
    if fmt in {"mol", "sdf"} and charge is not None and charge != Chem.GetFormalCharge(mol):
        raise ValueError(
            f"Declared charge {charge} differs from the molecule's formal charge {Chem.GetFormalCharge(mol)}; "
            "provide the molecular graph for the intended charge state."
        )
    return mol


def total_charge(mol) -> int:
    """Return declared total charge for coordinate-only input, otherwise the graph charge."""
    from rdkit import Chem

    if mol.HasProp("cloudra_total_charge"):
        return mol.GetIntProp("cloudra_total_charge")
    return Chem.GetFormalCharge(mol)


def from_ase(atoms):
    """Copy atoms and coordinates from ASE without guessing bonds or formal charges."""
    from rdkit import Chem

    mol = Chem.RWMol()
    conf = Chem.Conformer(len(atoms))
    for index, (symbol, position) in enumerate(zip(
        atoms.get_chemical_symbols(), atoms.get_positions(), strict=True,
    )):
        mol.AddAtom(Chem.Atom(symbol))
        conf.SetAtomPosition(index, tuple(map(float, position)))
    out = mol.GetMol()
    out.AddConformer(conf)
    return out


def to_ase(mol):
    """Return an independent ASE geometry view; chemistry stays in the molecule."""
    from ase import Atoms

    return Atoms(
        symbols=[atom.GetSymbol() for atom in mol.GetAtoms()],
        positions=mol.GetConformer().GetPositions(),
    )


def to_xyz(mol, comment: str = "") -> str:
    """Render the default conformer in atom order with eight decimal places."""
    positions = mol.GetConformer().GetPositions()
    lines = [str(mol.GetNumAtoms()), comment]
    for atom, position in zip(mol.GetAtoms(), positions, strict=True):
        lines.append(f"{atom.GetSymbol():<4} {position[0]:>14.8f} {position[1]:>14.8f} {position[2]:>14.8f}")
    return "\n".join(lines) + "\n"


def with_positions(mol, positions):
    """Copy the molecule and replace only its default conformer's coordinates."""
    from rdkit import Chem

    out = Chem.Mol(mol)
    conf = out.GetConformer()
    for index, position in zip(range(out.GetNumAtoms()), positions, strict=True):
        conf.SetAtomPosition(index, tuple(map(float, position)))
    return out
