"""Concrete geometry declarations; numbering is resolved at the owning tool boundary."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class DistanceWindowInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    atoms: list[StrictInt] = Field(min_length=2, max_length=2)
    min_ang: float = Field(gt=0)
    max_ang: float = Field(gt=0)

    @model_validator(mode="after")
    def valid_window(self):
        if len(set(self.atoms)) != 2 or min(self.atoms) < 0 or self.max_ang < self.min_ang:
            raise ValueError("Distance window needs distinct nonnegative atoms and min_ang <= max_ang")
        return self


class FrozenCoordinateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    coord_type: Literal["bond", "angle", "dihedral"]
    atoms: list[StrictInt]
    value: float | None = Field(default=None, description='Explicit frozen target in Angstrom/degrees; omitted means current geometry')

    @model_validator(mode="after")
    def valid_atoms(self):
        size = {"bond": 2, "angle": 3, "dihedral": 4}[self.coord_type]
        if len(self.atoms) != size or len(set(self.atoms)) != size or min(self.atoms) < 0:
            raise ValueError(f"{self.coord_type} needs {size} distinct nonnegative atom indices")
        return self


class ScanCoordinateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    coord_type: Literal["bond", "angle", "dihedral"] = "bond"
    atoms: list[StrictInt]
    scan_start: float | None = None
    scan_end: float
    scan_steps: StrictInt = Field(ge=1)

    @model_validator(mode="after")
    def valid_atoms(self):
        FrozenCoordinateInput(coord_type=self.coord_type, atoms=self.atoms)
        return self


def atom_index_base(engine: str | None = None) -> int:
    if engine == "orca":
        return 0
    if engine in (None, "gaussian", "xtb"):
        return 1
    raise ValueError(f"Unknown atom numbering context: {engine!r}")


def atom_indices(atoms, *, base: int, count: int) -> list[int]:
    if any(type(atom) is not int or not base <= atom < count + base for atom in atoms):
        raise ValueError(f"Atom indices {atoms!r} must be in {base}..{count + base - 1}")
    return [atom - base for atom in atoms]




def native_coordinate_settings(mol, *, engine: str, scans, freeze, scan_mode=None,
                               end_setting: str = '', orca_blocks: str | None = None) -> dict:
    """Shared Gaussian/ORCA scan and constraint syntax, using native numbering.

    Callers convert user numbering at their boundary. Returned metadata retains
    the actual starting values; Gaussian start mismatches are never hidden.
    """
    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    if engine not in {'gaussian', 'orca'}:
        raise ValueError('Native coordinates require Gaussian or ORCA')
    positions = mol.GetConformer().GetPositions()
    count = mol.GetNumAtoms()
    specs, mismatches = [], []
    for raw in scans:
        entry = raw if isinstance(raw, ScanCoordinateInput) else ScanCoordinateInput.model_validate(raw)
        idx = atom_indices(entry.atoms, base=atom_index_base(engine), count=count)
        current = InternalCoordinates._coordinate_value(positions, idx)
        start = current if entry.scan_start is None else entry.scan_start
        tolerance = 0.005 if entry.coord_type == 'bond' else 0.5
        if entry.scan_start is not None and abs(start - current) > tolerance:
            mismatches.append(f'{entry.coord_type} {entry.atoms}: requested scan_start={start} '
                              f'but the current geometry value is {current:.4f}')
        specs.append(dict(coord_type=entry.coord_type, idx=idx, start=start, end=entry.scan_end,
                          steps=entry.scan_steps, step_size=(entry.scan_end-start) / entry.scan_steps))
    scanned = {(spec['coord_type'], min(tuple(spec['idx']), tuple(reversed(spec['idx'])))) for spec in specs}
    if len(scanned) != len(specs):
        raise ValueError('Duplicate scanned coordinate (including reversed atom order)')
    frozen, seen = [], set()
    for raw in freeze:
        entry = raw if isinstance(raw, FrozenCoordinateInput) else FrozenCoordinateInput.model_validate(raw)
        idx = atom_indices(entry.atoms, base=atom_index_base(engine), count=count)
        key = (entry.coord_type, min(tuple(idx), tuple(reversed(idx))))
        if key in scanned:
            raise ValueError(f'Coordinate {entry.atoms} is both scanned and frozen')
        if key in seen:
            continue
        # Measurement validates geometry independently of whether a target was supplied.
        try:
            InternalCoordinates._coordinate_value(positions, idx)
        except ValueError as exc:
            raise ValueError(f'Degenerate frozen {entry.coord_type} {entry.atoms}: {exc}') from exc
        seen.add(key)
        frozen.append((entry.coord_type, idx, entry.value))
    letters = {'bond': 'B', 'angle': 'A', 'dihedral': 'D'}
    labels = [f"{letters[spec['coord_type']]} {' '.join(str(i + atom_index_base(engine)) for i in spec['idx'])}"
              f" from {spec['start']:.4f} to {spec['end']:.4f} "
              f"({spec['steps']} steps, {spec['step_size']:+.6f})" for spec in specs]
    if engine == 'gaussian':
        lines = [f"{letters[spec['coord_type']]} {' '.join(str(i + 1) for i in spec['idx'])} "
                 f"S {spec['steps']} {spec['step_size']:.6f}" for spec in specs]
        lines += [f"{letters[kind]} {' '.join(str(i + 1) for i in idx)} "
                  + (f'{value:.6f} ' if value is not None else '') + 'F' for kind, idx, value in frozen]
        native = {'end_setting': '\n\n'.join(filter(None, ['\n'.join(lines), end_setting])),
                  'orca_blocks': orca_blocks, 'task_type': [{'opt': 'modredundant'}]}
    else:
        blocks = ['%geom']
        if specs:
            blocks += ['    Scan']
            blocks += [f"        {letters[spec['coord_type']]} {' '.join(str(i) for i in spec['idx'])} "
                       f"= {spec['start']:.6f}, {spec['end']:.6f}, {spec['steps']}" for spec in specs]
            blocks += ['    end']
            if scan_mode == 'concerted':
                blocks += ['    Simul_Scan true']
        if frozen:
            blocks += ['    Constraints']
            blocks += [f"        {{ {letters[kind]} {' '.join(str(i) for i in idx)} "
                       + (f'{value:.6f} ' if value is not None else '') + 'C }' for kind, idx, value in frozen]
            blocks += ['    end']
        blocks += ['end']
        if orca_blocks:
            blocks += [orca_blocks.strip()]
        native = {'orca_blocks': '\n'.join(blocks), 'end_setting': end_setting, 'task_type': [{'opt': None}]}
    return {**native, 'specs': specs, 'frozen': frozen, 'start_mismatches': mismatches, 'scan_labels': labels}
