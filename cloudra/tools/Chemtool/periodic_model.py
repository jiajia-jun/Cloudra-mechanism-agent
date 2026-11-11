"""Build initial periodic geometries from a known structure."""

import asyncio
from collections import Counter
from itertools import islice
from math import ceil, gcd
from pathlib import Path
from typing import Annotated, Any, Literal

import numpy as np
from ase import Atom, Atoms
from ase.build import make_supercell
from ase.data import atomic_numbers
from ase.geometry import minkowski_reduce
from pydantic import AfterValidator, Field, StrictInt, StringConstraints, model_validator
from scipy.spatial.transform import Rotation

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.periodic_geometry import (
    GEOMETRY_TOLERANCE_ANGSTROM,
    AdsorptionSite,
    SiteKind,
    adsorption_surface,
    enumerate_adsorption_sites,
    minimum_image_distances,
    slab_normal,
)
from cloudra.tools.core.periodic_io import (
    geometry_format_from_path,
    read_geometry,
    validate_atomic_geometry,
    validate_cell_geometry,
    write_periodic_geometry,
)

PathString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PositiveLength = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
Vector = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
IntegerVector = tuple[StrictInt, StrictInt, StrictInt]


def _element(symbol: str) -> str:
    if not atomic_numbers.get(symbol):
        raise ValueError('Use an element symbol such as Ag, O or Li.')
    return symbol


Element = Annotated[str, AfterValidator(_element)]


class Inspect(input_schema):
    type: Literal['inspect']
    element: Element | None = Field(default=None, description='Return only atom sites of this element.')
    start_atom: PositiveInt = Field(default=1, description='Start at this 1-based atom number in the input.')
    limit: PositiveInt = Field(default=24, le=100, description='Maximum number of atom sites in the response.')


class Supercell(input_schema):
    type: Literal['supercell']
    repeat: tuple[PositiveInt, PositiveInt, PositiveInt] | None = Field(
        default=None, description='Repeat counts along input a, b and c.',
    )
    matrix: tuple[IntegerVector, IntegerVector, IntegerVector] | None = Field(
        default=None, description='Integer transformation P with new cell vectors given by P times the input cell.',
    )
    min_lengths_angstrom: tuple[PositiveLength | None, PositiveLength | None, PositiveLength | None] | None = Field(
        default=None, description='Minimum lengths of the a, b and c vectors in Å. Null entries leave that vector unchanged.',
    )

    @model_validator(mode='after')
    def one_size(self):
        if sum(value is not None for value in (self.repeat, self.matrix, self.min_lengths_angstrom)) != 1:
            raise ValueError('Give exactly one of repeat, matrix or min_lengths_angstrom.')
        if self.min_lengths_angstrom == (None, None, None):
            raise ValueError('Give at least one minimum length.')
        return self


class Slab(input_schema):
    type: Literal['slab']
    miller: IntegerVector = Field(description='Signed (h,k,l) in the input cell basis. Supply a conventional cell for conventional indices.')
    layers: PositiveInt = Field(description='Number of distinct geometric atomic planes to keep, counted from the selected cut.')
    vacuum_angstrom: PositiveLength = Field(description='Total vacuum gap along the slab normal in Å, split equally on the two sides.')
    termination: PositiveInt | None = Field(
        default=None, description='1-based cut number from a preview. Required to write a slab when there is more than one candidate.',
    )


class Remove(input_schema):
    type: Literal['remove']
    atom_index: PositiveInt = Field(description='1-based atom number in the input structure. Use inspect to obtain it.')


class Replace(input_schema):
    type: Literal['replace']
    atom_index: PositiveInt = Field(description='1-based atom number in the input structure. Use inspect to obtain it.')
    element: Element = Field(description='Replacement element.')


class Add(input_schema):
    type: Literal['add']
    element: Element
    fractional: Vector = Field(description='Site coordinates in the input fractional basis. Periodic axes wrap into the cell.')


SiteEdit = Annotated[Remove | Replace | Add, Field(discriminator='type')]


class EditSites(input_schema):
    type: Literal['edit_sites']
    edits: list[SiteEdit] = Field(min_length=1, description='Vacancy, substitution or explicit atom insertion. All atom numbers refer to the original input.')


class SurfaceInput(input_schema):
    side: Literal['top', 'bottom'] = Field(
        description='Top follows the cell vector out of the periodic plane; bottom points the opposite way.',
    )
    vacuum_axis: Literal['a', 'b', 'c'] | None = Field(
        default=None, description='Required for three-periodic slabs such as POSCAR. Names the out-of-plane lattice vector.',
    )
    surface_atoms: list[PositiveInt] | None = Field(
        default=None, min_length=1,
        description='Atom numbers for candidate enumeration. Omit for the outermost atomic plane of a clean slab.',
    )


class AdsorptionSites(SurfaceInput):
    type: Literal['adsorption_sites']
    kind: SiteKind | None = Field(default=None, description='Filter by kind while keeping the original candidate numbers.')
    start_site: PositiveInt = Field(default=1, description='First 1-based candidate number to return.')
    limit: PositiveInt = Field(default=24, le=100, description='Maximum number of candidates to return.')


class AtopAtom(input_schema):
    atom_index: PositiveInt = Field(description='1-based input atom to use directly as an atop reference.')


class AdsorbateOrientation(input_schema):
    axis_atom: PositiveInt = Field(description='1-based molecule atom defining the vector from the anchor.')
    direction: Literal['outward'] | Vector = Field(
        description='Align the anchor-to-axis vector with the outward surface normal or a slab Cartesian direction.',
    )
    twist_degrees: FiniteFloat = Field(default=0.0, description='Subsequent right-handed rotation around direction in degrees.')


class AdsorbateGeometry(input_schema):
    path: PathString = Field(description='Single nonperiodic XYZ or EXTXYZ file with explicit Å coordinates.')
    anchor_atom: PositiveInt = Field(description='1-based molecule atom to place above the site.')
    orientation: AdsorbateOrientation | None = Field(default=None, description='Omit to use the orientation in the input file.')


class Adsorb(SurfaceInput):
    type: Literal['adsorb']
    site: PositiveInt | AtopAtom = Field(description='Candidate number or an explicit input atom as an atop reference.')
    adsorbate: Element | AdsorbateGeometry = Field(description='Element symbol for one atom, or an explicit molecule.')
    height_angstrom: PositiveLength = Field(description='Anchor displacement from the site along the outward normal in Å.')


Operation = Annotated[Inspect | Supercell | Slab | EditSites | AdsorptionSites | Adsorb, Field(discriminator='type')]


class PeriodicModelInput(input_schema):
    input_path: PathString = Field(
        description='CIF, POSCAR/CONTCAR, EXTXYZ, XSF, GEN, QE .pwi/.pwo, or ABACUS STRU structure file. '
        'Absolute or relative to the agent working directory.',
    )
    operation: Operation
    output_path: PathString | None = Field(
        default=None, description='New structure file path for a build. Omit for inspection or a candidate preview.',
    )

    @model_validator(mode='after')
    def output_matches_operation(self):
        if isinstance(self.operation, (Inspect, AdsorptionSites)) and self.output_path is not None:
            raise ValueError(f'Omit output_path for {self.operation.type}.')
        if isinstance(self.operation, (Supercell, EditSites, Adsorb)) and self.output_path is None:
            raise ValueError(f'Give an output_path for {self.operation.type}.')
        return self


class Site(output_schema):
    atom_index: int
    element: str
    fractional: Vector


class Termination(output_schema):
    index: int
    bottom: dict[str, int]
    top: dict[str, int]
    cleavage_gap_angstrom: float
    thickness_angstrom: float


class CellSummary(output_schema):
    atom_count: int
    composition: dict[str, int]
    lattice_angstrom: tuple[Vector, Vector, Vector]
    lengths_angstrom: Vector
    pbc: tuple[bool, bool, bool]
    shortest_periodic_translation_angstrom: float
    thickness_angstrom: float | None = None
    vacuum_angstrom: float | None = None


class PeriodicModelOutput(output_schema):
    is_success: bool = True
    output_path: str | None = None
    summary: CellSummary | None = Field(default=None, description="Geometry summary before export to the target format.")
    sites: list[Site] = Field(default_factory=list)
    terminations: list[Termination] = Field(default_factory=list)
    termination: int | None = None
    adsorption_sites: list[AdsorptionSite] = Field(default_factory=list)
    adsorbate_min_distance_angstrom: float | None = None
    warnings: list[str] = Field(default_factory=list)
    message: str = ''


def _summarize(atoms: Atoms) -> CellSummary:
    reduced, _ = minkowski_reduce(atoms.cell, pbc=atoms.pbc)
    normal_size = {}
    if sum(atoms.pbc) == 2:
        normal = slab_normal(atoms.cell, atoms.pbc)
        thickness = float(np.ptp(atoms.positions @ normal))
        normal_size = {
            'thickness_angstrom': thickness,
            'vacuum_angstrom': max(0.0, abs(float(atoms.cell[~atoms.pbc][0] @ normal)) - thickness),
        }
    return CellSummary(
        atom_count=len(atoms), composition=Counter(atoms.get_chemical_symbols()),
        lattice_angstrom=atoms.cell.tolist(), lengths_angstrom=atoms.cell.lengths().tolist(),
        pbc=atoms.pbc.tolist(),
        shortest_periodic_translation_angstrom=float(np.linalg.norm(reduced[atoms.pbc], axis=1).min()),
        **normal_size,
    )


def _supercell(atoms: Atoms, operation: Supercell) -> Atoms:
    if operation.matrix is not None:
        matrix = np.array(operation.matrix, dtype=int)
        if np.linalg.matrix_rank(matrix) != 3:
            raise ValueError('The supercell matrix must be nonsingular.')
    else:
        repeat = operation.repeat
        if repeat is None:
            repeat = tuple(
                1 if length is None else ceil(length / original)
                for length, original in zip(operation.min_lengths_angstrom, atoms.cell.lengths())
            )
        matrix = np.diag(repeat)

    for axis in np.flatnonzero(~atoms.pbc):
        unchanged_axis = np.eye(3, dtype=int)[axis]
        if not (np.array_equal(matrix[axis], unchanged_axis) and np.array_equal(matrix[:, axis], unchanged_axis)):
            raise ValueError('A supercell cannot repeat or mix a nonperiodic axis. Expand only the periodic directions.')
    if np.array_equal(matrix, np.diag(matrix.diagonal())) and np.all(matrix.diagonal() > 0):
        return atoms.repeat(matrix.diagonal())
    return make_supercell(atoms, matrix)


def _bezout(a: int, b: int) -> tuple[int, int, int]:
    """Return d >= 0 and x, y with a*x + b*y = d = gcd(a, b)."""
    if b == 0:
        return abs(a), 1 if a >= 0 else -1, 0
    divisor, x, y = _bezout(b, a % b)
    return divisor, y, x - (a // b) * y


def _surface_basis(miller: IntegerVector) -> list[list[int]]:
    divisor = gcd(*miller)
    if divisor == 0:
        raise ValueError('The Miller indices cannot all be zero.')
    h, k, normal_index = (value // divisor for value in miller)
    if h == k == 0:
        return [[1, 0, 0], [0, normal_index, 0], [0, 0, normal_index]]
    d, s, t = _bezout(h, k)
    _, x, y = _bezout(d, normal_index)
    # The first two rows cross to (h,k,l); the third advances one plane.
    return [[k // d, -h // d, 0], [s * normal_index, t * normal_index, -d], [s * x, t * x, y]]


def _slab(atoms: Atoms, operation: Slab, *, build: bool) -> tuple[Atoms | None, list[Termination], int | None]:
    if not atoms.pbc.all():
        raise ValueError('Cut a slab from a bulk input with three periodic axes.')
    cell = _surface_basis(operation.miller) @ atoms.cell
    atoms.set_cell(cell)
    scaled = atoms.get_scaled_positions()
    # Round only for grouping coincident planes, leaving atomic coordinates intact.
    levels, plane = np.unique(np.round(scaled[:, 2], 10) % 1, return_inverse=True)
    count = len(levels)
    compositions = [Counter() for _ in levels]
    for index, symbol in zip(plane, atoms.get_chemical_symbols()):
        compositions[index][symbol] += 1
    normal = np.cross(cell[0], cell[1])
    normal /= np.linalg.norm(normal)
    repeat_height = abs(float(cell[2] @ normal))
    gaps = levels - np.roll(levels, 1)
    gaps[0] += 1
    terminations = []
    for index, bottom in enumerate(compositions):
        repeats_to_top, top = divmod(index + operation.layers - 1, count)
        terminations.append(Termination(
            index=index + 1, bottom=bottom, top=compositions[top],
            cleavage_gap_angstrom=float(gaps[index] * repeat_height),
            thickness_angstrom=float((repeats_to_top + levels[top] - levels[index]) * repeat_height),
        ))
    selected = operation.termination
    if selected is not None and selected > count:
        raise ValueError(f'Termination {selected} is absent. Choose a cut number between 1 and {count}.')
    if selected is None and count == 1:
        selected = 1
    if not build or selected is None:
        return None, terminations, selected

    first = selected - 1
    cut = levels[first] - gaps[first] / 2
    scaled[:, 2] = (scaled[:, 2] - cut) % 1
    atoms.set_scaled_positions(scaled)
    repeats = (operation.layers + count - 1) // count
    atoms = atoms.repeat((1, 1, repeats))
    layer_number = np.tile((plane - first) % count, repeats) + np.repeat(np.arange(repeats) * count, len(plane))
    atoms = atoms[layer_number < operation.layers]

    # Rotate the full geometry before replacing the tilted stacking vector with a vacuum axis.
    a, b, c = atoms.cell
    if c @ normal < 0:
        normal = -normal
        b = -b
    x = a / np.linalg.norm(a)
    frame = np.column_stack((x, np.cross(normal, x), normal))
    atoms.positions[:] = atoms.positions @ frame
    cell = np.array([a, b, c]) @ frame
    cell[:2, 2] = 0
    cell[2] = (0, 0, np.ptp(atoms.positions[:, 2]) + operation.vacuum_angstrom)
    atoms.set_cell(cell)
    atoms.pbc = (True, True, False)
    atoms.center(axis=2)
    atoms.wrap()
    return atoms, terminations, selected


def _atom_index(atoms: Atoms, atom_number: int) -> int:
    if atom_number > len(atoms):
        raise ValueError(f'Atom {atom_number} is outside the input structure, which has {len(atoms)} atoms.')
    return atom_number - 1


def _edit_sites(atoms: Atoms, operation: EditSites) -> Atoms:
    removals = []
    seen = set()
    additions = []
    for edit in operation.edits:
        if isinstance(edit, Add):
            additions.append(edit)
            continue
        index = _atom_index(atoms, edit.atom_index)
        if index in seen:
            raise ValueError(f'Atom {edit.atom_index} has more than one edit.')
        seen.add(index)
        if isinstance(edit, Remove):
            removals.append(index)
        else:
            atoms[index].symbol = edit.element

    del atoms[removals]
    for addition in additions:
        fractional = np.array(addition.fractional)
        fractional[atoms.pbc] %= 1
        atoms.append(Atom(addition.element, fractional @ atoms.cell))
        distances = minimum_image_distances(atoms, atoms.positions[-1:], atoms.positions[:-1])
        if np.any(distances < GEOMETRY_TOLERANCE_ANGSTROM):
            raise ValueError(f'Inserted {addition.element} at {addition.fractional} coincides with an existing site.')
    if not len(atoms):
        raise ValueError('Site edits would leave an empty structure.')
    return atoms


def _candidate_sites(
    atoms: Atoms, operation: SurfaceInput, in_plane: np.ndarray, normal: np.ndarray,
) -> list[AdsorptionSite]:
    indices = None
    if operation.surface_atoms is not None:
        indices = sorted(_atom_index(atoms, number) for number in operation.surface_atoms)
    return enumerate_adsorption_sites(atoms, in_plane, normal, indices)


def _adsorb(atoms: Atoms, operation: Adsorb, warnings: list[str]) -> tuple[AdsorptionSite, float]:
    in_plane, normal = adsorption_surface(atoms, operation.vacuum_axis, operation.side)
    if isinstance(operation.site, AtopAtom):
        index = _atom_index(atoms, operation.site.atom_index)
        site = AdsorptionSite(None, 'ontop', tuple(atoms.positions[index].tolist()), [operation.site.atom_index])
    else:
        candidates = _candidate_sites(atoms, operation, in_plane, normal)
        if operation.site > len(candidates):
            raise ValueError(f'Site {operation.site} is absent. Preview adsorption_sites for this slab and surface selection.')
        site = candidates[operation.site - 1]

    if isinstance(operation.adsorbate, str):
        molecule = Atoms(operation.adsorbate)
    else:
        geometry = operation.adsorbate
        path = Path(geometry.path)
        if path.suffix.lower() not in {'.xyz', '.extxyz'}:
            raise ValueError('Use an XYZ or EXTXYZ adsorbate. Convert other molecule files with format_converter.')
        template, count, _ = read_geometry(path, 'extxyz')
        validate_atomic_geometry(template)
        if count != 1 or template.pbc.any():
            raise ValueError('Provide one nonperiodic adsorbate geometry.')
        if template.info.get('cloudra_coordinate_units', 'angstrom') != 'angstrom':
            raise ValueError('Provide adsorbate coordinates in Å.')
        molecule = Atoms(numbers=template.numbers, positions=template.positions)
        anchor = _atom_index(molecule, geometry.anchor_atom)
        molecule.translate(-molecule.positions[anchor].copy())
        if geometry.orientation is not None:
            orientation = geometry.orientation
            axis = molecule.positions[_atom_index(molecule, orientation.axis_atom)]
            direction = normal if orientation.direction == 'outward' else np.asarray(orientation.direction)
            norm = np.linalg.norm(direction)
            if not np.linalg.norm(axis) or not np.isfinite(norm) or not norm:
                raise ValueError('Give a distinct axis atom and a nonzero finite orientation direction.')
            unit_direction = direction / norm
            align, _ = Rotation.align_vectors(unit_direction, axis)
            twist = Rotation.from_rotvec(unit_direction * orientation.twist_degrees, degrees=True)
            molecule.positions[:] = (twist * align).apply(molecule.positions)

    molecule.translate(np.asarray(site.position_angstrom) + operation.height_angstrom * normal)
    distances = minimum_image_distances(atoms, molecule.positions, atoms.positions)
    minimum = float(distances.min())
    if minimum < GEOMETRY_TOLERANCE_ANGSTROM:
        raise ValueError('An adsorbate atom coincides with an input atom under periodic boundaries.')
    if len(molecule) > 1:
        internal = minimum_image_distances(atoms, molecule.positions, molecule.positions)
        if np.any(internal[np.triu_indices(len(molecule), k=1)] < GEOMETRY_TOLERANCE_ANGSTROM):
            raise ValueError('Adsorbate atoms coincide under periodic boundaries.')
    fractional = atoms.cell.scaled_positions(molecule.positions)[:, ~in_plane]
    if np.any((fractional < 0) | (fractional > 1)):
        warnings.append('The placed adsorbate extends outside the cell along the vacuum axis.')
    atoms.extend(molecule)
    return site, minimum


def _run_model(input_path: Path, output_path: Path | None, operation: Operation) -> PeriodicModelOutput:
    source_format = geometry_format_from_path(input_path)
    atoms, frame_count, warnings = read_geometry(input_path, source_format)
    if frame_count != 1:
        raise ValueError('Provide a single geometry. Use format_converter to extract a frame first.')
    validate_cell_geometry(atoms)
    if not atoms.pbc.any():
        raise ValueError('The input must declare periodic axes.')
    if isinstance(operation, Inspect):
        sites = (
            Site(atom_index=index, element=symbol, fractional=fractional.tolist())
            for index, (symbol, fractional) in enumerate(zip(atoms.get_chemical_symbols(), atoms.get_scaled_positions()), 1)
            if index >= operation.start_atom and (operation.element is None or symbol == operation.element)
        )
        return PeriodicModelOutput(summary=_summarize(atoms), sites=list(islice(sites, operation.limit)), warnings=warnings)
    if isinstance(operation, AdsorptionSites):
        in_plane, normal = adsorption_surface(atoms, operation.vacuum_axis, operation.side)
        candidates = _candidate_sites(atoms, operation, in_plane, normal)
        matches = (site for site in candidates[operation.start_site - 1:] if operation.kind in (None, site.kind))
        return PeriodicModelOutput(
            summary=_summarize(atoms), adsorption_sites=list(islice(matches, operation.limit)), warnings=warnings,
            message='Geometric adsorption candidates for the selected surface.',
        )

    summary = _summarize(atoms) if isinstance(operation, Slab) else None
    had_constraints = bool(atoms.constraints)
    atoms = Atoms(numbers=atoms.numbers, positions=atoms.positions, cell=atoms.cell, pbc=atoms.pbc)
    terminations = []
    selected = None
    adsorption_sites = []
    min_distance = None
    if isinstance(operation, Slab):
        atoms, terminations, selected = _slab(atoms, operation, build=output_path is not None)
        if atoms is None:
            return PeriodicModelOutput(
                summary=summary, terminations=terminations, termination=selected, warnings=warnings,
                message='Geometric cleavage candidates. Supply output_path and the chosen termination to write a slab.',
            )
    elif isinstance(operation, Supercell):
        atoms = _supercell(atoms, operation)
    elif isinstance(operation, Adsorb):
        site, min_distance = _adsorb(atoms, operation, warnings)
        adsorption_sites.append(site)
    else:
        atoms = _edit_sites(atoms, operation)

    summary = _summarize(atoms)
    if had_constraints:
        warnings.append('Modeling produces geometry only. Input atom constraints were not transferred.')
    warnings.extend(write_periodic_geometry(output_path, atoms, geometry_format_from_path(output_path), exclusive=True))
    return PeriodicModelOutput(
        output_path=str(output_path), summary=summary, terminations=terminations, termination=selected,
        adsorption_sites=adsorption_sites, adsorbate_min_distance_angstrom=min_distance,
        warnings=warnings, message='Initial periodic geometry written.',
    )


class PeriodicModel(Tool):
    tool_id: str = 'periodic-model'
    tool_name: str = 'periodic_model'
    tool_description: str = (
        'Inspect a known crystal, expand a bulk or slab supercell, cut a slab by Miller indices, '
        'or edit explicit sites for defects. Enumerate surface adsorption sites and place atoms or molecules. '
        'Inspect for 1-based atom numbers and preview slab terminations before choosing a cut. '
        'Use EXTXYZ to keep per-axis periodicity when chaining operations. Results are initial geometries.'
    )
    input_schema: Any = PeriodicModelInput
    output_schema: Any = PeriodicModelOutput

    def is_read(self) -> bool:
        return True

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: PeriodicModelInput, session=None) -> PeriodicModelOutput:
        source = Path(resolve_tool_path(self, user_input.input_path))
        target = Path(resolve_tool_path(self, user_input.output_path)) if user_input.output_path else None
        operation = user_input.operation
        if isinstance(operation, Adsorb) and isinstance(operation.adsorbate, AdsorbateGeometry):
            geometry = operation.adsorbate
            geometry = geometry.model_copy(update={'path': resolve_tool_path(self, geometry.path)})
            operation = operation.model_copy(update={'adsorbate': geometry})
        try:
            return await asyncio.to_thread(_run_model, source, target, operation)
        except (ValueError, OSError) as exc:
            return PeriodicModelOutput(is_success=False, message=str(exc))
