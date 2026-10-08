"""One scientific input definition and its partial revision schema.

Structure-tool atom references are one-based; scan references use the declared
scan engine. Persisted references are zero-based and never reinterpreted when
another calculation changes engine.
"""
from __future__ import annotations

from copy import deepcopy
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, StrictInt, create_model, field_validator, model_validator

from cloudra.tools.core.geometry_inputs import (
    DistanceWindowInput,
    FrozenCoordinateInput,
    ScanCoordinateInput,
    atom_index_base,
)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TsCalculation(InputModel):
    """An explicit calculation; keywords replace rather than accumulate."""
    engine: Literal["orca", "gaussian", "xtb"]
    method: str = Field(min_length=1)
    keywords: str = ""
    frequency_mode: Literal["auto", "analytic", "numeric"] = "auto"
    orca_blocks: str | None = None
    end_setting: str = ""

    @field_validator("method")
    @classmethod
    def nonempty_method(cls, value):
        if not value.strip():
            raise ValueError("method must be explicitly declared")
        return value


class TsReaction(InputModel):
    reactant_smiles: str = Field(min_length=1)
    product_smiles: str = Field(min_length=1)
    charge: StrictInt
    multiplicity: StrictInt = Field(ge=1)
    atom_map: list[StrictInt] = Field(default_factory=list, description="Full concrete atom mapping in product-coordinate order; each value is a 1-based reactant-coordinate atom index, including explicit hydrogens. Use reaction_mapping.atom_map bound to these structures, not heavy_atom_map or SMILES positions.")
    reaction_center: list[tuple[StrictInt, StrictInt]] = Field(default_factory=list, description="Forming/breaking atom pairs in the bound reactant's full coordinate order, 1-based and including explicit hydrogens. Use reaction_mapping.concrete_watch_pairs for the same concrete structure.")


class GeneratedConformer(InputModel):
    kind: Literal["generate"]
    generation: Literal["ETKDGv3"]
    seed: StrictInt
    optimization: TsCalculation | None = None


class HeavyAtomBinding(InputModel):
    structure_digest: str = Field(min_length=1, description="Matching reaction_mapping.structure_digests value for this concrete endpoint. Binds its atom order, graph and coordinates; a stale or mismatched digest is rejected.")
    indices: list[StrictInt] = Field(min_length=1, description="1-based indices in this file's full coordinate atom order, listed in declared SMILES heavy-atom order. Explicit hydrogen rows count toward indices; the selected atoms must be heavy atoms.")


class FileConformer(InputModel):
    kind: Literal["file"]
    xyz_path: str = Field(min_length=1)
    mol_path: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    optimization: TsCalculation | None = None
    heavy_atom_binding: HeavyAtomBinding | None = None


class CatalogConformer(InputModel):
    kind: Literal["catalog"]
    catalog_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    partition_revision: str = Field(min_length=1)
    optimization: TsCalculation | None = None


class RotatedConformer(InputModel):
    kind: Literal["rotate_about_bond"]
    atoms: tuple[StrictInt, StrictInt] = Field(description="Bond-axis atom pair in the bound conformer's full coordinate order, 1-based; do not use SMILES heavy-atom indices.")
    degrees: float


ConformerSource = Annotated[
    GeneratedConformer | FileConformer | CatalogConformer | RotatedConformer,
    Field(discriminator="kind"),
]


class ConformerGuidance(InputModel):
    ring_order: list[StrictInt] = Field(default_factory=list, description="Ordered ring atoms in the bound reactant's full coordinate order, 1-based.")
    distance_filters: list[DistanceWindowInput] = Field(default_factory=list, description="Distance windows whose atom pairs use the bound reactant's full coordinate order, 1-based, including explicit hydrogen rows.")


class TsConformers(InputModel):
    reactant: ConformerSource | None = None
    product: ConformerSource | None = None
    guidance: ConformerGuidance = Field(default_factory=ConformerGuidance)


class PathSolvation(InputModel):
    model: Literal["alpb", "gbsa"]
    solvent: str = Field(min_length=1)


class XtbPathGuess(InputModel):
    kind: Literal["xtb_path"]
    method: str = Field(min_length=1)
    solvation: PathSolvation | None = None
    refinement_runs: StrictInt | None = Field(default=None, ge=1, description="xTB path refinement cap; omitted/null uses the runner default of 100. This is a compute limit, not a convergence criterion.")


class ScanGuess(InputModel):
    kind: Literal["scan"]
    calculation: TsCalculation
    scans: list[ScanCoordinateInput] = Field(min_length=1, max_length=2, description="Coordinates in the concrete scan-input atom order. ORCA references are 0-based; Gaussian/xTB references are 1-based. Convert concrete coordinate indices, not SMILES positions.")
    freeze: list[FrozenCoordinateInput] = Field(default_factory=list, description="Frozen coordinates in the same concrete input atom order and engine-specific numbering as scans.")
    force_constant: float | None = Field(default=None, gt=0, description="xTB restraint force constant in atomic units; explicitly declared")
    mode: Literal["concerted", "sequential"] | None = None
    solvation: PathSolvation | None = None

    @model_validator(mode="after")
    def scan_contract(self):
        engine = self.calculation.engine
        if engine != "xtb":
            if any(value is not None for value in (self.force_constant, self.mode, self.solvation)):
                raise ValueError("force_constant, mode and solvation are native xTB scan fields")
            if engine == "orca" and len(self.scans) != 1:
                raise ValueError("ORCA relaxed scan accepts exactly one coordinate")
            return self
        if self.calculation.method != "GFN2-xTB":
            raise ValueError("native xTB scan currently supports explicitly declared GFN2-xTB")
        if self.calculation.keywords or self.calculation.orca_blocks or self.calculation.end_setting:
            raise ValueError("native xTB scan rejects ORCA/Gaussian directives")
        if self.force_constant is None:
            raise ValueError("force_constant is required for native xTB scan")
        if self.freeze:
            raise ValueError("native xTB scan does not silently reinterpret freeze as a soft restraint")
        if len(self.scans) == 1 and self.mode is not None:
            raise ValueError("mode is derived for a one-coordinate xTB scan")
        if len(self.scans) == 2:
            if self.mode is None:
                raise ValueError("mode is required for two-coordinate xTB scan")
            if self.mode == "concerted" and self.scans[0].scan_steps != self.scans[1].scan_steps:
                raise ValueError("concerted xTB scans require equal scan_steps")
        for row in self.scans:
            if row.scan_start is None or row.scan_steps < 2:
                raise ValueError("native xTB scan requires scan_start and at least two scan points")
        keys = [(row.coord_type, min(tuple(row.atoms), tuple(reversed(row.atoms)))) for row in self.scans]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate scan coordinate")
        return self


class ProvidedGuess(InputModel):
    kind: Literal["provided"]
    xyz_path: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)


TsGuess = Annotated[XtbPathGuess | ScanGuess | ProvidedGuess, Field(discriminator="kind")]


class EndpointSeed(InputModel):
    kind: Literal['file']
    xyz_path: str = Field(min_length=1)
    mol_path: str | None = None
    evidence_refs: list[str] = Field(min_length=1)


class EndpointVerification(InputModel):
    seed: EndpointSeed | None = None
    optimization: TsCalculation | None = None
    frequency: TsCalculation | None = None


class TsVerification(InputModel):
    frequency: TsCalculation | None = None
    irc: TsCalculation | None = None
    irc_log: str | None = None
    reactant_endpoint: EndpointVerification = Field(default_factory=EndpointVerification)
    product_endpoint: EndpointVerification = Field(default_factory=EndpointVerification)


class TsExecutionLimits(InputModel):
    source: str = Field(min_length=1)
    max_compute_actions: StrictInt | None = Field(default=None, ge=0)
    max_model_calls: StrictInt | None = Field(default=None, ge=0)
    max_interventions: StrictInt | None = Field(default=None, ge=0)


class TsExecution(InputModel):
    cpus: StrictInt = Field(default=1, ge=1)
    memory_mb: StrictInt = Field(default=4096, ge=1)
    limits: TsExecutionLimits | None = None


class TsInput(InputModel):
    reaction: TsReaction
    conformers: TsConformers = Field(default_factory=TsConformers)
    guess: TsGuess | None = None
    ts_optimization: TsCalculation | None = None
    verification: TsVerification = Field(default_factory=TsVerification)
    execution: TsExecution = Field(default_factory=TsExecution)


# Scientific operations and sources are immutable units. All other nested
# groups derive their patch fields from the same definition as prepare.
_ATOMIC = {
    TsCalculation, GeneratedConformer, HeavyAtomBinding, FileConformer, CatalogConformer,
    RotatedConformer, PathSolvation, XtbPathGuess, ScanGuess, ProvidedGuess,
    DistanceWindowInput, FrozenCoordinateInput, ScanCoordinateInput,
}
_PARTIAL: dict[type[BaseModel], type[BaseModel]] = {}


def _patch_annotation(annotation):
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation if annotation in _ATOMIC else _partial_model(annotation)
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return Union[tuple(_patch_annotation(arg) for arg in get_args(annotation))]
    return annotation


def _partial_model(model):
    if model not in _PARTIAL:
        fields = {}
        for name, field in model.model_fields.items():
            info = deepcopy(field)
            info.default = None
            info.default_factory = None
            fields[name] = (_patch_annotation(field.annotation) | None, info)
        _PARTIAL[model] = create_model(f"{model.__name__}Changes", __base__=InputModel, **fields)
    return _PARTIAL[model]


TsInputChanges = _partial_model(TsInput)


def apply_input_changes(current: TsInput, changes: TsInputChanges) -> TsInput:
    def merge(old, patch):
        result = deepcopy(old)
        for name in patch.model_fields_set:
            value = getattr(patch, name)
            if isinstance(value, BaseModel) and type(value) in _PARTIAL.values():
                result[name] = merge(result.get(name) or {}, value)
            else:
                result[name] = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        return result
    return TsInput.model_validate(merge(current.model_dump(mode="json"), changes))


class TsResumeRequest(InputModel):
    changes: TsInputChanges = Field(default_factory=TsInputChanges)
    reason: str = Field(min_length=1)
    request_key: str = Field(min_length=1)
    expected_revision: StrictInt = Field(ge=0)

    @field_validator("reason", "request_key")
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip():
            raise ValueError("nonblank reason and request_key required")
        return value


def normalize_ts_input_atoms(value: TsInput | TsInputChanges, *, atom_tables: dict) -> TsInput | TsInputChanges:
    data = value.model_dump(mode="json", exclude_unset=isinstance(value, TsInputChanges))

    def indices(values, base, side="reactant"):
        count = len(atom_tables[side]) if side in atom_tables else None
        if any(type(atom) is not int or atom < base or (count is not None and atom >= count + base) for atom in values):
            raise ValueError(f"{side} atom references must use base {base} and the bound atom table")
        return [atom - base for atom in values]

    reaction = data.get("reaction") or {}
    if reaction.get("atom_map") is not None:
        reaction["atom_map"] = indices(reaction["atom_map"], 1)
    if reaction.get("reaction_center") is not None:
        reaction["reaction_center"] = [indices(pair, 1) for pair in reaction["reaction_center"]]
    conformers = data.get("conformers") or {}
    guidance = conformers.get("guidance") or {}
    if guidance.get("ring_order") is not None:
        guidance["ring_order"] = indices(guidance["ring_order"], 1)
    for window in guidance.get("distance_filters") or []:
        window["atoms"] = indices(window["atoms"], 1)
    for side in ("reactant", "product"):
        endpoint = (data.get("verification") or {}).get(f"{side}_endpoint") or {}
        for source in (conformers.get(side), endpoint.get("seed")):
            if source and source["kind"] == "rotate_about_bond":
                source["atoms"] = indices(source["atoms"], 1, side)
    guess = data.get("guess")
    if guess and guess["kind"] == "scan":
        base = atom_index_base(guess["calculation"]["engine"])
        for row in guess["scans"] + guess.get("freeze", []):
            row["atoms"] = indices(row["atoms"], base)
    return type(value).model_validate(data)
