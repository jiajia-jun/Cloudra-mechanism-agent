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
    if engine in (None, "gaussian"):
        return 1
    raise ValueError(f"Unknown atom numbering context: {engine!r}")


def atom_indices(atoms, *, base: int, count: int) -> list[int]:
    if any(type(atom) is not int or not base <= atom < count + base for atom in atoms):
        raise ValueError(f"Atom indices {atoms!r} must be in {base}..{count + base - 1}")
    return [atom - base for atom in atoms]


def normalize_ts_atoms(declaration, *, engine):
    """Public software-native declaration/adjustment to internal zero-based fields."""
    base = atom_index_base(engine)
    data = declaration.model_dump(exclude_unset=True)

    def indices(values):
        if any(type(i) is not int or i < base for i in values):
            raise ValueError(f"{engine} atom indices start at {base}")
        return [i - base for i in values]

    for name in ("ring_order", "atom_map"):
        if data.get(name) is not None:
            data[name] = indices(data[name])
    if data.get("reaction_center") is not None:
        data["reaction_center"] = [indices(pair) for pair in data["reaction_center"]]
    if data.get("distance_filters") is not None:
        for row in data["distance_filters"]:
            row["atoms"] = indices(row["atoms"])
    if data.get("product_geometry") is not None:
        data["product_geometry"]["atoms"] = indices(data["product_geometry"]["atoms"])
    if data.get("scan") is not None:
        for name in ("scans", "freeze"):
            for row in data["scan"].get(name, []):
                row["atoms"] = indices(row["atoms"])
    return type(declaration).model_validate(data)


class ScanPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: str = Field(min_length=1)
    scans: list[ScanCoordinateInput] = Field(min_length=1, max_length=2)
    freeze: list[FrozenCoordinateInput] = Field(default_factory=list)
