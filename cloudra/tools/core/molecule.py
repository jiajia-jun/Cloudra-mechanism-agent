"""Geometry views and coordinate replacement for RDKit molecules."""

import base64
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


def read_molecule(input_path=None, input_text=None, input_format="auto", charge=None):
    """Read a declared graph or coordinate-only Mol; never infer bonds while converting."""
    from rdkit import Chem

    if input_path:
        text = Path(input_path).read_text(encoding="utf-8")
    elif input_text:
        text = input_text
    else:
        raise ValueError("Must provide input_path or input_text")
    fmt = input_format
    if fmt == "auto":
        if input_path:
            fmt = Path(input_path).suffix.lower().lstrip(".")
            if fmt not in {"mol", "sdf", "xyz"}:
                from ase.io.formats import extension2format

                native_format = extension2format.get(fmt)
                fmt = native_format.name if native_format else "auto"
        if fmt == "auto":
            lines = text.splitlines()
            counts = lines[3].split() if len(lines) > 3 else []
            if any(token in {"V2000", "V3000"} for token in counts):
                fmt = "sdf" if any(line.strip() == "$$$$" for line in lines) else "mol"
            else:
                fmt = "xyz"
    if fmt == "mol":
        mol = Chem.MolFromMolBlock(text, removeHs=False)
    elif fmt == "sdf":
        mol = next(Chem.ForwardSDMolSupplier(BytesIO(text.encode("utf-8")), removeHs=False), None)
    else:
        import ase.io

        if fmt == "xyz":
            if int(text.splitlines()[0].strip()) <= 0:
                raise ValueError("XYZ requires a positive atom count")
        mol = from_ase(ase.io.read(StringIO(text), format="extxyz" if fmt == "xyz" else fmt or None))
        mol.SetIntProp("cloudra_total_charge", charge if charge is not None else 0)
        mol.SetProp("cloudra_graph_status", "unresolved")
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
