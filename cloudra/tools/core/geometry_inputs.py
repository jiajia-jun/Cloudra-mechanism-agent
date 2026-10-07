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



