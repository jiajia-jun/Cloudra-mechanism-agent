"""One scientific input definition and its partial revision schema.

Structure-tool atom references are one-based; scan references use the declared
scan engine. Persisted references are zero-based and never reinterpreted when
another calculation changes engine.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    TypeAdapter,
    create_model,
    field_validator,
    model_validator,
)

from cloudra.tools.core.geometry_inputs import (
    DistanceWindowInput,
    FrozenCoordinateInput,
    ScanCoordinateInput,
    atom_index_base,
)
from cloudra.tools.core.qm_calculation import QmCalculation


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CalculationRef(InputModel):
    """Explicitly reuse one complete calculation defined in this TS input."""
    ref: str = Field(min_length=1)

    @field_validator('ref')
    @classmethod
    def reference_name(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError('calculation reference must be a nonblank exact definition name')
        return value


CalculationValue = QmCalculation | CalculationRef


def resolve_calculation(value: CalculationValue | dict | None,
                        definitions: Mapping[str, QmCalculation | dict]) -> QmCalculation | None:
    """Resolve local references and return an independent complete snapshot."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = TypeAdapter(CalculationValue).validate_python(value)
    if isinstance(value, CalculationRef):
        if value.ref not in definitions:
            raise ValueError(f'unknown calculation reference {value.ref!r}')
        value = QmCalculation.model_validate(definitions[value.ref])
    return value.model_copy(deep=True)


class TsReaction(InputModel):
    reactant_smiles: str = Field(min_length=1)
    product_smiles: str | list[str] = Field(min_length=1,
        description='A dot-joined SMILES declares a bound complex; a list declares separated products, displayed with +.')
    charge: StrictInt
    multiplicity: StrictInt = Field(ge=1)
    electronic_character: Literal['closed_shell', 'open_shell'] | None = Field(default=None,
        description="Optional declared electronic character, including open-shell singlets. This describes the requested seed state; it does not choose a ground state, wavefunction method or spin initialization.")
    selected_candidate: StrictInt | None = Field(default=None, ge=0, description="Optional 0-based override of the existing algorithm's ranked complete mapping candidates. Omitted/null adopts its first candidate automatically and reports the choice.")
    reaction_center: list[tuple[StrictInt, StrictInt]] = Field(default_factory=list, description="Optional forming/breaking atom pairs in the bound reactant's full coordinate order, 1-based and including explicit hydrogens. Omitted/empty derives the pairs from the bound reaction mapping.")


class GeneratedConformer(InputModel):
    kind: Literal["generate"]
    generation: Literal["ETKDGv3"] = 'ETKDGv3'
    seed: StrictInt = 42
    optimization: CalculationValue | None = None


class FileConformer(InputModel):
    kind: Literal["file"]
    xyz_path: str = Field(min_length=1)
    mol_path: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    optimization: CalculationValue | None = Field(default=None, description=(
        'Optional additional build-stage pre-optimization. Omit or set null to use the supplied file geometry as-is. '
        'This does not certify a minimum or replace later TS/IRC and endpoint verification. '
        'With ts_resume, patch optimization to null to clear a previous request; omitted source fields retain their values.'
    ))


class CatalogConformer(InputModel):
    kind: Literal["catalog"]
    catalog_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    optimization: CalculationValue | None = None


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
    reactant: ConformerSource | None = Field(default=None,
        description='Optional explicit reactant source. Omit or set null to generate the starting geometry from reaction.reactant_smiles with the program defaults.')
    product: ConformerSource | None = Field(default=None,
        description='Optional explicit product source. Omit or set null to generate the starting geometry from reaction.product_smiles with the program defaults.')
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
    calculation: CalculationValue
    scans: list[ScanCoordinateInput] = Field(min_length=1, max_length=2, description="Coordinates in the concrete scan-input atom order. ORCA references are 0-based; Gaussian/xTB references are 1-based. Convert concrete coordinate indices, not SMILES positions.")
    freeze: list[FrozenCoordinateInput] = Field(default_factory=list, description="Frozen coordinates in the same concrete input atom order and engine-specific numbering as scans.")
    force_constant: float | None = Field(default=None, gt=0, description="xTB restraint force constant in atomic units; explicitly declared")
    mode: Literal["concerted", "sequential", "grid"] | None = Field(default=None, description="Two ORCA coordinates require grid (independent surface) or concerted (simultaneous path, equal steps). xTB supports concerted/sequential. Omit for one coordinate or Gaussian grids.")
    solvation: PathSolvation | None = None

    @model_validator(mode="after")
    def scan_contract(self):
        if isinstance(self.calculation, QmCalculation):
            self.validate_calculation(self.calculation)
        return self

    def validate_calculation(self, calculation: QmCalculation):
        engine = calculation.engine
        if engine != "xtb":
            if self.force_constant is not None or self.solvation is not None:
                raise ValueError("force_constant and solvation are native xTB scan fields")
            if engine == "orca":
                if len(self.scans) == 2:
                    if self.mode not in {"concerted", "grid"}:
                        raise ValueError("Two-coordinate ORCA scans require explicit mode='concerted' (path) or 'grid' (independent surface)")
                    if self.mode == "concerted" and self.scans[0].scan_steps != self.scans[1].scan_steps:
                        raise ValueError("concerted ORCA scans require equal scan_steps")
                elif self.mode is not None:
                    raise ValueError("ORCA scan mode applies only to two scanned coordinates")
            elif self.mode is not None:
                raise ValueError("mode is supported only for native xTB or two-coordinate ORCA scans")
            return self
        if self.mode == "grid":
            raise ValueError("native xTB scans support concerted or sequential, not grid")
        if calculation.method != "GFN2-xTB":
            raise ValueError("native xTB scan currently supports explicitly declared GFN2-xTB")
        if calculation.keywords or calculation.orca_blocks or calculation.end_setting:
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
    xyz_path: str = Field(min_length=1, description="Candidate XYZ in the current bound reactant's full atom order. Coordinates and element labels must refer to the same source atoms; do not combine product-order coordinates with reactant-order labels.")
    evidence_refs: list[str] = Field(min_length=1)


TsGuess = Annotated[XtbPathGuess | ScanGuess | ProvidedGuess, Field(discriminator="kind")]


class EndpointSeed(InputModel):
    kind: Literal['file']
    xyz_path: str = Field(min_length=1, description='XYZ in the bound endpoint species atom order. The program applies the existing reaction atom map; accepted native IRC endpoint files already use TS working order.')
    mol_path: str | None = Field(default=None, description='MOL defining the XYZ atom order. Use the existing bound species MOL; a MOL already in TS working order is also recognized.')
    evidence_refs: list[str] = Field(min_length=1)


class EndpointVerification(InputModel):
    seed: EndpointSeed | None = None
    optimization: CalculationValue | None = None
    frequency: CalculationValue | None = None


class ProductEndpointVerification(EndpointVerification):
    component_logs: list[str] = Field(default_factory=list,
        description='Native frequency logs for the independently optimized separated products. The program snapshots the files and matches each real geometry to its declared component; every component must have zero imaginary frequencies. This does not verify a bound complex minimum.')


class TsVerification(InputModel):
    frequency: CalculationValue | None = None
    irc: CalculationValue | None = None
    irc_log: str | None = None
    reactant_endpoint: EndpointVerification = Field(default_factory=EndpointVerification,
        description='The declared reaction.reactant_smiles species, never a fixed IRC A/B direction. An explicit seed uses this species atom order; default IRC sources are provisional until optimization, frequency and direction checks pass.')
    product_endpoint: ProductEndpointVerification = Field(default_factory=ProductEndpointVerification,
        description='The declared reaction.product_smiles species, never a fixed IRC A/B direction. An explicit seed uses this species atom order (or an accepted native IRC working order); the runtime applies the bound atom map.')


class TsExecutionLimits(InputModel):
    source: str = Field(min_length=1)
    max_compute_actions: StrictInt | None = Field(default=None, ge=0)
    max_model_calls: StrictInt | None = Field(default=None, ge=0)


class TsExecution(InputModel):
    cpus: StrictInt = Field(default=1, ge=1)
    memory_mb: StrictInt = Field(default=4096, ge=1)
    limits: TsExecutionLimits | None = None


class TsInput(InputModel):
    reaction: TsReaction
    calculations: dict[str, QmCalculation] = Field(default_factory=dict,
        description='Complete local named calculations. Stages explicitly select a ref; nothing inherits an exploration or formal method automatically.')
    conformers: TsConformers = Field(default_factory=TsConformers)
    guess: TsGuess | None = None
    ts_optimization: CalculationValue | None = None
    verification: TsVerification = Field(default_factory=TsVerification)
    execution: TsExecution = Field(default_factory=TsExecution)

    @model_validator(mode='after')
    def calculation_references(self):
        for name in self.calculations:
            if not name.strip() or name != name.strip():
                raise ValueError('calculation definition names must be nonblank exact names')
        values = [self.ts_optimization, self.verification.frequency, self.verification.irc]
        for role in ('reactant', 'product'):
            endpoint = getattr(self.verification, role + '_endpoint')
            values.extend([endpoint.optimization, endpoint.frequency])
            source = getattr(self.conformers, role)
            values.append(getattr(source, 'optimization', None))
        for value in values:
            resolve_calculation(value, self.calculations)
        if self.guess and self.guess.kind == 'scan':
            self.guess.validate_calculation(resolve_calculation(self.guess.calculation, self.calculations))
        return self


class CalculationReplacement(InputModel):
    """Deliberate replacement; omitted optional settings reset to their defaults."""
    replace: CalculationValue


# Scientific operations are immutable units; source patches use the current kind.
_ATOMIC = {
    PathSolvation, XtbPathGuess, ProvidedGuess,
    DistanceWindowInput, FrozenCoordinateInput, ScanCoordinateInput,
}
_PARTIAL: dict[type[BaseModel], type[BaseModel]] = {}
_SOURCE_MODELS = {model.model_fields['kind'].annotation.__args__[0]: model for model in (
    GeneratedConformer, FileConformer, CatalogConformer, RotatedConformer)}


def _is_source_annotation(annotation):
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return get_origin(annotation) in (Union, UnionType) and any(
        part in _SOURCE_MODELS.values() for part in get_args(annotation))


def _patch_annotation(annotation):
    if _is_source_annotation(annotation):
        return ConformerSourceChanges
    if annotation is QmCalculation:
        return _partial_model(QmCalculation) | CalculationReplacement
    if annotation is CalculationRef:
        return CalculationReplacement
    if annotation == TsGuess:
        return _partial_model(ScanGuess) | XtbPathGuess | ProvidedGuess
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation if annotation in _ATOMIC else _partial_model(annotation)
    origin = get_origin(annotation)
    if origin is dict and get_args(annotation) == (str, QmCalculation):
        return dict[str, _partial_model(QmCalculation) | CalculationReplacement | None]
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
            if _is_source_annotation(field.annotation):
                info.discriminator = None
            fields[name] = (_patch_annotation(field.annotation) | None, info)
        _PARTIAL[model] = create_model(f"{model.__name__}Changes", __base__=InputModel, **fields)
    return _PARTIAL[model]


_source_fields = {}
for _source_model in _SOURCE_MODELS.values():
    for _name, _field in _source_model.model_fields.items():
        if _name == 'kind':
            continue
        _info = deepcopy(_field)
        _info.default = None
        _info.default_factory = None
        if _name in _source_fields and not _info.description:
            _info.description = _source_fields[_name][1].description
        _source_fields[_name] = (_patch_annotation(_field.annotation) | None, _info)
ConformerSourceChanges = create_model('ConformerSourceChanges', __base__=InputModel,
    kind=(Literal['generate', 'file', 'catalog', 'rotate_about_bond'] | None, None), **_source_fields)
TsInputChanges = _partial_model(TsInput)


def apply_input_changes(current: TsInput, changes: TsInputChanges) -> TsInput:
    def calculation_patch(old, patch):
        if isinstance(patch, CalculationReplacement):
            return patch.replace.model_dump(mode='json')
        if old and 'ref' in old:
            raise ValueError('patch a referenced calculation through its calculations definition, or explicitly replace the stage calculation')
        fields = patch.model_dump(mode='json', exclude_unset=True)
        for field in ('engine', 'method', 'basis_set'):
            if field in fields and isinstance(fields[field], str):
                fields[field] = fields[field].strip()
                if old and field in ('method', 'basis_set'):
                    before, after = old[field].lower(), fields[field].lower()
                    if field == 'basis_set':
                        # Match the native input comparator's basis spelling rule.
                        before, after = before.replace('-', ''), after.replace('-', '')
                    if before == after:
                        fields[field] = old[field]
            if old and field in fields and fields[field] != old[field]:
                raise ValueError(f'changing calculation {field} requires an explicit replace with a complete calculation')
        return {**(old or {}), **fields}

    def merge(old, patch):
        result = deepcopy(old)
        for name in patch.model_fields_set:
            value = getattr(patch, name)
            if name == 'calculations' and isinstance(value, dict):
                definitions = deepcopy(result.get(name) or {})
                for key, change in value.items():
                    if change is None:
                        definitions.pop(key, None)
                    else:
                        definitions[key] = calculation_patch(definitions.get(key), change)
                result[name] = definitions
            elif isinstance(value, (CalculationReplacement, _PARTIAL[QmCalculation])):
                result[name] = calculation_patch(result.get(name), value)
            elif isinstance(value, ConformerSourceChanges):
                previous = result.get(name) or {}
                kind = value.kind if 'kind' in value.model_fields_set else previous.get('kind')
                if kind not in _SOURCE_MODELS:
                    raise ValueError('a new conformer source requires its kind and complete source fields')
                if kind != previous.get('kind'):
                    previous = {}
                typed = _partial_model(_SOURCE_MODELS[kind]).model_validate(value.model_dump(exclude_unset=True))
                result[name] = merge(previous, typed)
            elif isinstance(value, BaseModel) and type(value) in _PARTIAL.values():
                previous = result.get(name) or {}
                if isinstance(value, _PARTIAL[ScanGuess]) and 'kind' in value.model_fields_set and previous.get('kind') != value.kind:
                    previous = {}
                result[name] = merge(previous, value)
            else:
                result[name] = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        return result
    merged = merge(current.model_dump(mode="json"), changes)
    guess = merged.get('guess')
    if isinstance(current.guess, ScanGuess) and guess and guess.get('kind') == 'scan':
        before = resolve_calculation(current.guess.calculation, current.calculations)
        after = resolve_calculation(guess['calculation'], merged.get('calculations') or {})
        explicit = changes.guess.model_fields_set if changes.guess is not None else set()
        if before.engine == 'xtb' and after.engine != 'xtb' and 'force_constant' not in explicit:
            guess['force_constant'] = None
    return TsInput.model_validate(merged)


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


def normalize_ts_input_atoms(value: TsInput | TsInputChanges, *, atom_tables: dict,
                             current_input: TsInput | None = None,
                             calculations: Mapping[str, QmCalculation] | None = None) -> TsInput | TsInputChanges:
    data = value.model_dump(mode="json", exclude_unset=isinstance(value, TsInputChanges))

    def indices(values, base, side="reactant"):
        count = len(atom_tables[side]) if side in atom_tables else None
        if any(type(atom) is not int or atom < base or (count is not None and atom >= count + base) for atom in values):
            raise ValueError(f"{side} atom references must use base {base} and the bound atom table")
        return [atom - base for atom in values]

    reaction = data.get("reaction") or {}
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
        current_endpoint = getattr(current_input.verification, f'{side}_endpoint') if current_input else None
        current_sources = (getattr(current_input.conformers, side), current_endpoint.seed if current_endpoint else None) if current_input else (None, None)
        for source, current_source in zip((conformers.get(side), endpoint.get("seed")), current_sources):
            kind = source.get('kind', current_source.kind if current_source else None) if source else None
            if source and kind == "rotate_about_bond" and source.get('atoms') is not None:
                source["atoms"] = indices(source["atoms"], 1, side)
    guess = data.get("guess")
    if guess and (guess.get('scans') is not None or guess.get('freeze') is not None):
        if isinstance(value, TsInput):
            engine = resolve_calculation(value.guess.calculation, value.calculations).engine
        elif current_input is not None:
            updated = apply_input_changes(current_input, value)
            if updated.guess is None or updated.guess.kind != 'scan':
                raise ValueError('scan coordinates require a current scan declaration')
            engine = resolve_calculation(updated.guess.calculation, updated.calculations).engine
        else:
            declaration = guess.get('calculation') or {}
            declaration = declaration.get('replace', declaration)
            if 'engine' in declaration:
                engine = declaration['engine']
            elif 'ref' in declaration:
                engine = resolve_calculation(declaration, calculations or {}).engine
            else:
                raise ValueError('scan atom numbering requires current_input or an explicitly resolved calculation')
        base = atom_index_base(engine)
        for row in (guess.get('scans') or []) + (guess.get('freeze') or []):
            row["atoms"] = indices(row["atoms"], base)
    return type(value).model_validate(data)
