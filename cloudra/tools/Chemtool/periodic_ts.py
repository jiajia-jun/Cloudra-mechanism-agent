"""Prepare and inspect fixed-cell periodic NEB runs."""

import asyncio
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal

from ase.io import read, write
from pydantic import Field, StrictInt, StringConstraints, model_validator

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.periodic_dimer import band_tangent, write_dimer
from cloudra.tools.core.periodic_io import write_periodic_geometry
from cloudra.tools.core.periodic_neb import build_band, read_endpoint

PathString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Engine = Literal['vasp', 'cp2k']


class ImageShift(input_schema):
    atom_index: PositiveInt = Field(description='1-based atom number in the initial structure.')
    shift: tuple[StrictInt, StrictInt, StrictInt] = Field(
        description='Integer lattice translations (a, b, c) from the supplied final atom position. Replaces its minimum-image choice.',
    )


class Prepare(input_schema):
    type: Literal['prepare']
    engine: Engine
    initial_path: PathString = Field(description='Single cell-bearing initial structure.')
    final_path: PathString = Field(description='Single final structure with the same cell, PBC and composition.')
    intermediate_images: PositiveInt = Field(description='Number of interior images. The two endpoints are additional.')
    output_dir: PathString = Field(description='New run directory for the seed band and engine-native geometry files.')
    interpolation: Literal['linear', 'idpp'] = Field(default='idpp', description='Geometric initialization of the band.')
    atom_map: list[tuple[PositiveInt, PositiveInt]] = Field(
        default_factory=list,
        description='Pairs of 1-based [initial atom, final atom]. Unlisted atoms keep their row numbers. The full map must be bijective.',
    )
    image_shifts: list[ImageShift] = Field(
        default_factory=list, description='Override the default minimum-image choice for specified atoms.',
    )
    waypoint_path: PathString | None = Field(
        default=None, description='Optional geometric waypoint in the initial atom order and the intended periodic image.',
    )
    fixed_atoms: list[PositiveInt] | None = Field(
        default=None,
        description='Replace endpoint constraints with these frozen 1-based initial atoms. Omit to inherit matching whole-atom constraints.',
    )


class Analyze(input_schema):
    type: Literal['analyze']
    run_dir: PathString = Field(description='Prepared run directory containing the native calculation output.')
    output_log: PathString | None = Field(
        default=None, description='Explicit native main output log if stored outside its usual name.',
    )
    candidate_path: PathString | None = Field(
        default=None, description='New .extxyz file for an observed, unique interior peak above both observed endpoints.',
    )
    dimer_dir: PathString | None = Field(
        default=None, description='New directory for the peak geometry and native dimer inputs using adjacent evaluated images.',
    )

    @model_validator(mode='after')
    def one_export(self):
        if self.candidate_path is not None and self.dimer_dir is not None:
            raise ValueError('Choose candidate_path or dimer_dir. The dimer directory already includes candidate.extxyz.')
        return self


class PeriodicTSInput(input_schema):
    operation: Annotated[Prepare | Analyze, Field(discriminator='type')]


class _BandRecord(input_schema):
    engine: Engine
    image_count: Annotated[int, Field(strict=True, ge=3)]
    geometry_sha256: str


class BandImage(output_schema):
    index: int = Field(description='Image number starting at 0 for the initial endpoint.')
    energy_ev: float | None
    geometry_observed: bool = Field(description='Native coordinates bound to this image energy are available.')


class PeriodicTSOutput(output_schema):
    is_success: bool = True
    message: str
    engine: Engine | None = None
    run_dir: str | None = None
    band_path: str | None = None
    engine_files: list[str] = Field(default_factory=list)
    idpp: dict | None = None
    images: list[BandImage] = Field(default_factory=list)
    band_complete: bool | None = Field(default=None, description='Native evidence binds a coherent evaluated band step to the prepared path.')
    native_converged: bool | None = None
    energy_convention: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    highest_interior_images: list[int] = Field(default_factory=list)
    forward_peak_ev: float | None = None
    reverse_peak_ev: float | None = None
    reaction_energy_ev: float | None = None
    candidate_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _adapter(engine: Engine):
    if engine == 'vasp':
        from cloudra.tools.core.periodic_neb_vasp import read_vasp_neb, write_vasp_neb

        return write_vasp_neb, read_vasp_neb
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb, write_cp2k_neb

    return write_cp2k_neb, read_cp2k_neb


@contextmanager
def _new_run_dir(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.periodic-ts-', dir=target.parent) as temporary:
        stage = Path(temporary)
        yield stage
        target.mkdir(exist_ok=False)
        try:
            stage.rename(target)
        except OSError:
            target.rmdir()
            raise


def _prepare(tool: Tool, request: Prepare) -> PeriodicTSOutput:
    initial, warnings = read_endpoint(Path(resolve_tool_path(tool, request.initial_path)))
    final, final_warnings = read_endpoint(Path(resolve_tool_path(tool, request.final_path)))
    warnings.extend(final_warnings)
    waypoint = None
    if request.waypoint_path is not None:
        waypoint, waypoint_warnings = read_endpoint(Path(resolve_tool_path(tool, request.waypoint_path)))
        warnings.extend(waypoint_warnings)

    shifts = {item.atom_index: item.shift for item in request.image_shifts}
    if len(shifts) != len(request.image_shifts):
        raise ValueError('Give at most one image_shifts entry per atom.')
    images, idpp = build_band(
        initial, final, intermediate_images=request.intermediate_images, interpolation=request.interpolation,
        atom_map=request.atom_map, image_shifts=shifts, fixed_atoms=request.fixed_atoms, waypoint=waypoint,
    )
    if not request.atom_map and len(set(initial.numbers)) != len(initial):
        warnings.append('Atom row numbers define correspondence. Check the identities of migrating atoms of the same element.')
    if idpp is not None and idpp['converged'] is False:
        warnings.append('IDPP reached its geometric step limit. Inspect the resulting seed before running the engine.')

    target = Path(resolve_tool_path(tool, request.output_dir))
    writer, _ = _adapter(request.engine)
    with _new_run_dir(target) as stage:
        files, engine_warnings = writer(stage, images)
        band_path = stage / 'band.extxyz'
        write(band_path, images, format='extxyz')
        record = _BandRecord(
            engine=request.engine, image_count=len(images), geometry_sha256=sha256(band_path.read_bytes()).hexdigest(),
        )
        (stage / 'band.json').write_text(record.model_dump_json(indent=2) + '\n', encoding='utf-8')

    return PeriodicTSOutput(
        engine=request.engine, run_dir=str(target), band_path=str(target / 'band.extxyz'),
        engine_files=[str(target / file) for file in files], idpp=idpp, warnings=warnings + engine_warnings,
        message='Wrote the periodic NEB seed and native geometry inputs. Supply the electronic and optimization settings for the engine run.',
    )


def _analyze(tool: Tool, request: Analyze) -> PeriodicTSOutput:
    directory = Path(resolve_tool_path(tool, request.run_dir))
    output_log = Path(resolve_tool_path(tool, request.output_log)) if request.output_log else None
    candidate = Path(resolve_tool_path(tool, request.candidate_path)) if request.candidate_path else None
    dimer_dir = Path(resolve_tool_path(tool, request.dimer_dir)) if request.dimer_dir else None
    if candidate is not None and candidate.suffix.lower() != '.extxyz':
        raise ValueError('Use an .extxyz candidate_path to preserve the cell, PBC and frozen atoms.')

    record = _BandRecord.model_validate_json((directory / 'band.json').read_bytes())
    band_path = directory / 'band.extxyz'
    if sha256(band_path.read_bytes()).hexdigest() != record.geometry_sha256:
        raise ValueError('The prepared band.extxyz has changed. Prepare a new run directory for the revised seed.')
    expected = read(band_path, index=':', format='extxyz')
    if len(expected) != record.image_count:
        raise ValueError('The prepared band has a different image count from band.json.')

    _, reader = _adapter(record.engine)
    native = reader(directory, expected, output_log)
    energies = native['energies_ev']
    geometries = native['geometries']
    warnings = list(native['warnings'])
    complete = native['band_complete']
    compare_endpoints = complete and native.get('profile_comparable', True)
    initial, final = energies[0], energies[-1]
    peaks = []
    forward = reverse = None
    if complete:
        peak = max(energies[1:-1])
        peaks = [i for i, energy in enumerate(energies[1:-1], start=1) if energy == peak]
        if compare_endpoints:
            forward = peak - initial if initial is not None else None
            reverse = peak - final if final is not None else None

    candidate_written = None
    files = []
    if candidate is not None or dimer_dir is not None:
        unique_peak = len(peaks) == 1 and forward is not None and reverse is not None and min(forward, reverse) > 0
        if not unique_peak or geometries[peaks[0]] is None:
            warnings.append('Candidate export needs a unique interior peak above both observed endpoints and its evaluated geometry.')
        else:
            index = peaks[0]
            observed = geometries[index]
            if native['native_converged'] is not True:
                warnings.append('This candidate comes from a band without established native convergence.')
            if candidate is not None:
                warnings.extend(write_periodic_geometry(candidate, observed, 'extxyz', exclusive=True))
                candidate_written = str(candidate)
            else:
                left, right = geometries[index - 1], geometries[index + 1]
                if left is None or right is None:
                    warnings.append('Dimer preparation requires evaluated geometries on both sides of the peak.')
                else:
                    axis = band_tangent(left, observed, right)
                    with _new_run_dir(dimer_dir) as stage:
                        write_periodic_geometry(stage / 'candidate.extxyz', observed, 'extxyz')
                        files, notes = write_dimer(stage, record.engine, observed, axis)
                    warnings.extend(notes)
                    candidate_written = str(dimer_dir / 'candidate.extxyz')
                    files = [str(dimer_dir / name) for name in files]

    return PeriodicTSOutput(
        engine=record.engine, run_dir=str(directory), band_path=str(band_path),
        images=[
            BandImage(index=index, energy_ev=energy, geometry_observed=geometry is not None)
            for index, (energy, geometry) in enumerate(zip(energies, geometries, strict=True))
        ],
        band_complete=complete, native_converged=native['native_converged'], energy_convention=native['energy_convention'],
        metrics=native['metrics'], highest_interior_images=peaks, forward_peak_ev=forward, reverse_peak_ev=reverse,
        reaction_energy_ev=final - initial if compare_endpoints and initial is not None and final is not None else None,
        candidate_path=candidate_written, engine_files=files, evidence_paths=native['evidence_paths'], warnings=warnings,
        message='Inspected native NEB evidence. An interior energy peak is a candidate for independent saddle and endpoint checks.',
    )


class PeriodicTS(Tool):
    tool_id: str = 'periodic-ts'
    tool_name: str = 'periodic_ts'
    tool_description: str = (
        'Prepare a fixed-cell periodic NEB path for VASP or CP2K between two explicit endpoints. '
        'Use atom_map, image_shifts, or waypoint_path to specify atom correspondence and migration routes. '
        'Analyze the native band and optionally save an evaluated saddle candidate or seed a dimer refinement. '
        'Choose electronic settings and submit the engine run separately.'
    )
    input_schema: Any = PeriodicTSInput
    output_schema: Any = PeriodicTSOutput

    def is_read(self) -> bool:
        return True

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: PeriodicTSInput, session=None) -> PeriodicTSOutput:
        operation = user_input.operation
        try:
            return await asyncio.to_thread(_prepare if isinstance(operation, Prepare) else _analyze, self, operation)
        except (ValueError, OSError) as exc:
            return PeriodicTSOutput(is_success=False, message=str(exc))
