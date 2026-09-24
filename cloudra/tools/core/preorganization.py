"""Soft distance guidance for reactants arranged toward a prospective cycle.

Public declarations use the builder's complete 1-based atom order. The core
uses 0-based indices so RDKit, assembly and xTB adapters share one graph.
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Mapping, Sequence

from rdkit import Chem, DistanceGeometry
from rdkit.Chem import AllChem, rdDistGeom, rdMolAlign

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.complex_assembly import (
    MMFF_CONSTRAINT_FORCE_CONSTANT,
    AssemblyParameters,
)
from cloudra.tools.core.structure_builder import (
    BuildStrategy,
    PreparationRequest,
    PreparedStructure,
    StructureInput,
    prepare_structure,
)
from cloudra.tools.core.topology_change import default_connectivity


@dataclass(frozen=True)
class DistanceWindow:
    atoms: tuple[int, int]
    min_ang: float
    max_ang: float
    source: Literal["explicit", "fallback"]


@dataclass(frozen=True)
class GuidancePlan:
    ring_order: tuple[int, ...]
    windows: tuple[DistanceWindow, ...]
    forming_pairs: tuple[tuple[int, int], ...]
    bonded_pairs: tuple[tuple[int, int], ...]


def _numbering(prepared: PreparedStructure) -> str:
    return ", ".join(
        f"{identity.index + 1}={identity.symbol}"
        for identity in prepared.atom_identities
    )


def _bad(prepared: PreparedStructure, detail: str) -> ValueError:
    return ValueError(f"{detail}. Resolved atoms (1-based): {_numbering(prepared)}")


def load_resolved_graph(prepared: PreparedStructure) -> Chem.Mol:
    """Load the builder's resolved, explicit-H graph without inventing coordinates."""
    graph_only_multi = (
        prepared.status == "assembly_failed"
        and len(prepared.components) > 1
        and all(not component.xyz_path for component in prepared.components)
    )
    if prepared.status != "ok" and not graph_only_multi:
        raise _bad(prepared, f"builder status {prepared.status!r} has no usable resolved graph")
    if not prepared.components or not prepared.atom_identities:
        raise _bad(prepared, "builder returned no components or atom identities")

    graph = None
    for component in prepared.components:
        path = Path(component.mol_path)
        if not path.is_file():
            raise _bad(prepared, f"component MOL file is missing: {path}")
        fragment = Chem.MolFromMolFile(str(path), removeHs=False)
        if fragment is None:
            raise _bad(prepared, f"component MOL file cannot be parsed: {path}")
        graph = fragment if graph is None else Chem.CombineMols(graph, fragment)

    actual = [atom.GetSymbol() for atom in graph.GetAtoms()]
    expected = [identity.symbol for identity in prepared.atom_identities]
    indices = [identity.index for identity in prepared.atom_identities]
    if len(actual) != len(expected) or actual != expected or indices != list(range(len(expected))):
        raise _bad(
            prepared,
            f"resolved graph/identity element order mismatch: graph={actual}, identities={expected}",
        )
    return graph


def _atom_index(prepared: PreparedStructure, value: object, field: str) -> int:
    if type(value) is not int or not 1 <= value <= len(prepared.atom_identities):
        raise _bad(prepared, f"{field} atom index {value!r} is invalid")
    return value - 1


def resolve_explicit_filters(
    prepared: PreparedStructure,
    distance_filters: Sequence[Mapping[str, object]],
) -> tuple[DistanceWindow, ...]:
    """Validate declared windows; absent ring edges are handled separately."""
    load_resolved_graph(prepared)
    by_pair: dict[tuple[int, int], DistanceWindow] = {}
    for row in distance_filters:
        if not isinstance(row, Mapping):
            raise _bad(prepared, f"distance_filters entry must be an object, got {row!r}")
        atoms = row.get("atoms")
        if not isinstance(atoms, (list, tuple)) or len(atoms) != 2:
            raise _bad(prepared, f"distance_filters atoms must contain two indices: {row!r}")
        left = _atom_index(prepared, atoms[0], "distance_filters")
        right = _atom_index(prepared, atoms[1], "distance_filters")
        if left == right:
            raise _bad(prepared, f"distance_filters pair ({left + 1}, {right + 1}) repeats an atom")
        pair = tuple(sorted((left, right)))
        try:
            low = float(row["min_ang"])
            high = float(row["max_ang"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _bad(prepared, f"distance_filters pair {pair[0] + 1}-{pair[1] + 1} needs numeric min_ang/max_ang") from exc
        if not math.isfinite(low) or not math.isfinite(high) or low <= 0 or high < low:
            raise _bad(
                prepared,
                f"distance_filters pair {pair[0] + 1}-{pair[1] + 1} has invalid window [{low}, {high}] Å",
            )
        window = DistanceWindow(pair, low, high, "explicit")
        old = by_pair.get(pair)
        if old is not None and old != window:
            raise _bad(
                prepared,
                f"distance_filters pair {pair[0] + 1}-{pair[1] + 1} has conflicting duplicate windows",
            )
        by_pair[pair] = window
    return tuple(by_pair.values())


def resolve_guidance(
    prepared: PreparedStructure,
    ring_order: Sequence[int],
    distance_filters: Sequence[Mapping[str, object]],
    *,
    assembly_parameters: AssemblyParameters | None = None,
) -> GuidancePlan:
    graph = load_resolved_graph(prepared)
    if not isinstance(ring_order, (list, tuple)) or len(ring_order) < 3:
        raise _bad(prepared, "ring_order must contain at least three distinct atoms")
    ordered = tuple(_atom_index(prepared, value, "ring_order") for value in ring_order)
    if len(set(ordered)) != len(ordered):
        raise _bad(prepared, f"ring_order repeats an atom: {list(ring_order)!r}")

    explicit = resolve_explicit_filters(prepared, distance_filters)
    by_pair = {window.atoms: window for window in explicit}
    forming: list[tuple[int, int]] = []
    bonded: list[tuple[int, int]] = []
    windows = list(explicit)
    fallback = (assembly_parameters or AssemblyParameters()).reaction_center_window
    for left, right in zip(ordered, ordered[1:] + ordered[:1]):
        pair = tuple(sorted((left, right)))
        if graph.GetBondBetweenAtoms(left, right) is not None:
            bonded.append(pair)
            continue
        forming.append(pair)
        if pair not in by_pair:
            windows.append(DistanceWindow(pair, fallback[0], fallback[1], "fallback"))
    if not forming:
        raise _bad(prepared, "ring_order is already a fully covalent cycle; no prospective edge exists")
    return GuidancePlan(ordered, tuple(windows), tuple(forming), tuple(bonded))


def effective_window_rows(plan: GuidancePlan) -> list[dict]:
    return [
        {
            "atoms": [window.atoms[0] + 1, window.atoms[1] + 1],
            "min_ang": window.min_ang,
            "max_ang": window.max_ang,
            "source": window.source,
        }
        for window in plan.windows
    ]


def measure_windows(
    plan: GuidancePlan, positions: Sequence[Sequence[float]],
) -> dict[str, float]:
    distances = {}
    for window in plan.windows:
        left, right = window.atoms
        try:
            distance = math.dist(positions[left], positions[right])
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"positions cannot measure pair {left + 1}-{right + 1}") from exc
        if not math.isfinite(distance):
            raise ValueError(f"nonfinite distance for pair {left + 1}-{right + 1}")
        distances[f"{left + 1}-{right + 1}"] = distance
    return distances


def qualify_geometry(
    plan: GuidancePlan,
    graph: Chem.Mol,
    symbols: Sequence[str],
    positions: Sequence[Sequence[float]],
) -> tuple[bool, list[str], dict[str, float]]:
    """Check a delivered frame, independently of restraints used to create it."""
    expected_symbols = [atom.GetSymbol() for atom in graph.GetAtoms()]
    actual_symbols = [symbol[:1].upper() + symbol[1:].lower() for symbol in symbols]
    if actual_symbols != expected_symbols or len(positions) != len(expected_symbols):
        return False, ["atom identity/order changed"], {}
    if any(len(position) != 3 or not all(math.isfinite(float(v)) for v in position)
           for position in positions):
        return False, ["nonfinite or incomplete coordinates"], {}

    distances = measure_windows(plan, positions)
    reasons = []
    for window in plan.windows:
        key = f"{window.atoms[0] + 1}-{window.atoms[1] + 1}"
        actual = distances[key]
        if not window.min_ang <= actual <= window.max_ang:
            reasons.append(
                f"distance window {key}: {actual:.3f} Å outside "
                f"[{window.min_ang:.3f}, {window.max_ang:.3f}] Å"
            )

    expected_bonds = {
        tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())))
        for bond in graph.GetBonds()
    }
    perceived = set(default_connectivity()(expected_symbols, positions))
    unexpected = perceived - expected_bonds - set(plan.forming_pairs)
    missing = expected_bonds - perceived
    if unexpected:
        reasons.append(f"unexpected covalent contacts: {sorted(unexpected)}")
    if missing:
        reasons.append(f"input covalent bonds lost: {sorted(missing)}")

    clash_limit = AssemblyParameters().min_interfragment_distance
    graph_distances = Chem.GetDistanceMatrix(graph)
    for left in range(graph.GetNumAtoms()):
        for right in range(left + 1, graph.GetNumAtoms()):
            if graph_distances[left, right] <= 2 or (left, right) in plan.forming_pairs:
                continue
            if math.dist(positions[left], positions[right]) < clash_limit:
                reasons.append(f"atomic clash {left + 1}-{right + 1}")
    return not reasons, reasons, distances


@dataclass
class GuidedCandidate:
    xyz_path: str
    mol_path: str
    achieved_distances: dict[str, float]
    max_deviation_ang: float
    seed_kind: str = "constrained_preorganization"


@dataclass
class GuidedSearchResult:
    status: Literal["ok", "no_candidate", "build_failed", "engine_failed"]
    message: str
    candidates: list[GuidedCandidate] = field(default_factory=list)
    effective_windows: list[dict] = field(default_factory=list)
    forming_pairs: list[tuple[int, int]] = field(default_factory=list)
    prepared_path: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    manifest_path: str = ""
    closest_path: str = ""
    diagnostics: list[str] = field(default_factory=list)


def _xyz_text(symbols: Sequence[str], positions: Sequence[Sequence[float]], comment: str) -> str:
    lines = [str(len(symbols)), comment]
    for symbol, (x, y, z) in zip(symbols, positions):
        lines.append(f"{symbol:<3} {x:>16.8f} {y:>16.8f} {z:>16.8f}")
    return "\n".join(lines) + "\n"


def _max_window_deviation(plan: GuidancePlan, distances: Mapping[str, float]) -> float:
    return max(
        (
            max(window.min_ang - distances[f"{window.atoms[0] + 1}-{window.atoms[1] + 1}"],
                0.0,
                distances[f"{window.atoms[0] + 1}-{window.atoms[1] + 1}"] - window.max_ang)
            for window in plan.windows
        ),
        default=0.0,
    )


def _fallback_note(plan: GuidancePlan) -> str:
    rows = [
        f"{window.atoms[0] + 1}-{window.atoms[1] + 1} "
        f"[{window.min_ang:g}, {window.max_ang:g}] Å"
        for window in plan.windows if window.source == "fallback"
    ]
    return "Fallback windows: " + ", ".join(rows) if rows else ""


def _save_guided_result(result: GuidedSearchResult, plan: GuidancePlan,
                        output_dir: str) -> GuidedSearchResult:
    os.makedirs(output_dir, exist_ok=True)
    result.effective_windows = effective_window_rows(plan)
    result.forming_pairs = list(plan.forming_pairs)
    result.manifest_path = os.path.join(output_dir, "guidance_manifest.json")
    atomic_write_text(result.manifest_path, json.dumps({
        "seed_kind": "constrained_preorganization",
        "status": result.status,
        "ring_order": [i + 1 for i in plan.ring_order],
        "effective_windows": result.effective_windows,
        "forming_pairs": [[i + 1, j + 1] for i, j in plan.forming_pairs],
        "mmff_force_constant": MMFF_CONSTRAINT_FORCE_CONSTANT,
        "candidates": [asdict(candidate) for candidate in result.candidates],
        "counts": result.counts,
        "closest_path": result.closest_path,
        "diagnostics": result.diagnostics,
    }, indent=2) + "\n")
    return result


def _single_component_rdkit(
    prepared: PreparedStructure, plan: GuidancePlan, output_dir: str,
    num_confs: int, random_seed: int, rmsd_threshold: float,
) -> GuidedSearchResult:
    mol = load_resolved_graph(prepared)
    if not AllChem.MMFFHasAllMoleculeParams(mol):
        return _save_guided_result(GuidedSearchResult(
            status="engine_failed",
            message="MMFF94 parameters are unavailable for guided relaxation",
            prepared_path=prepared.artifact_path,
        ), plan, output_dir)

    bounds = rdDistGeom.GetMoleculeBoundsMatrix(mol)
    for window in plan.windows:
        left, right = window.atoms
        bounds[left, right] = window.max_ang
        bounds[right, left] = window.min_ang
    if not DistanceGeometry.DoTriangleSmoothing(bounds):
        pairs = ", ".join(
            f"{window.atoms[0] + 1}-{window.atoms[1] + 1}"
            for window in plan.windows
        )
        raise ValueError(f"incompatible guided bounds for atom pairs {pairs}; no embedding was run")

    params = AllChem.ETKDGv3()
    params.randomSeed = random_seed
    params.pruneRmsThresh = -1.0
    params.SetBoundsMat(bounds)
    conf_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=num_confs, params=params))
    result = GuidedSearchResult(
        status="no_candidate",
        message="",
        prepared_path=prepared.artifact_path,
        counts={"generated": len(conf_ids), "optimized": 0, "rejected": 0, "retained": 0},
    )
    if not conf_ids:
        result.message = "ETKDG could not embed any conformers under the declared bounds. " + _fallback_note(plan)
        return _save_guided_result(result, plan, output_dir)

    symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    mmff = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
    accepted: list[tuple[int, float, dict[str, float]]] = []
    closest: tuple[float, int, dict[str, float]] | None = None
    rejected: Counter[str] = Counter()
    for conf_id in conf_ids:
        force_field = AllChem.MMFFGetMoleculeForceField(
            mol, mmff, confId=conf_id, ignoreInterfragInteractions=True,
        )
        if force_field is None:
            rejected["force_field_unavailable"] += 1
            continue
        for window in plan.windows:
            force_field.MMFFAddDistanceConstraint(
                *window.atoms, False, window.min_ang, window.max_ang,
                MMFF_CONSTRAINT_FORCE_CONSTANT,
            )
        force_field.Initialize()
        if force_field.Minimize(maxIts=2000) != 0:
            rejected["optimization_not_converged"] += 1
            continue
        result.counts["optimized"] += 1
        positions = mol.GetConformer(conf_id).GetPositions()
        distances = measure_windows(plan, positions)
        deviation = _max_window_deviation(plan, distances)
        if closest is None or deviation < closest[0]:
            closest = (deviation, conf_id, distances)
        passed, reasons, distances = qualify_geometry(plan, mol, symbols, positions)
        if not passed:
            for reason in reasons:
                rejected[reason.split(":", 1)[0]] += 1
            continue
        free_field = AllChem.MMFFGetMoleculeForceField(
            mol, mmff, confId=conf_id, ignoreInterfragInteractions=True,
        )
        if free_field is None:
            rejected["unrestrained_single_point_unavailable"] += 1
            continue
        free_field.Initialize()
        accepted.append((conf_id, float(free_field.CalcEnergy()), distances))

    result.counts["rejected"] = len(conf_ids) - len(accepted)
    result.diagnostics.extend(f"{reason}: {count}" for reason, count in sorted(rejected.items()))
    if closest is not None:
        _, closest_id, closest_distances = closest
        result.closest_path = os.path.join(output_dir, "closest_attempt.xyz")
        atomic_write_text(result.closest_path, _xyz_text(
            symbols, mol.GetConformer(closest_id).GetPositions(),
            "closest guided attempt; not necessarily qualified",
        ))
        result.diagnostics.append(f"closest achieved distances: {closest_distances}")

    # Diversity selection on the same heavy-atom RMSD definition as the tool.
    heavy = Chem.RemoveHs(mol)
    heavy_ids = {conf.GetId() for conf in heavy.GetConformers()}
    if any(conf_id not in heavy_ids for conf_id, _, _ in accepted):
        raise ValueError("RDKit RemoveHs lost conformer ids; heavy-atom RMSD clustering is unsafe")
    selected: list[tuple[int, dict[str, float]]] = []
    for conf_id, _energy, distances in sorted(accepted, key=lambda item: item[1]):
        if any(rdMolAlign.GetBestRMS(heavy, heavy, prbId=conf_id, refId=prior) <= rmsd_threshold
               for prior, _ in selected):
            continue
        selected.append((conf_id, distances))

    for index, (conf_id, distances) in enumerate(selected):
        xyz_path = os.path.join(output_dir, f"guided_seed_{index:03d}.xyz")
        mol_path = os.path.join(output_dir, f"guided_seed_{index:03d}.mol")
        atomic_write_text(xyz_path, _xyz_text(
            symbols, mol.GetConformer(conf_id).GetPositions(),
            f"constrained preorganization seed {index}",
        ))
        atomic_write_text(mol_path, Chem.MolToMolBlock(mol, confId=conf_id))
        result.candidates.append(GuidedCandidate(xyz_path, mol_path, distances, 0.0))

    result.counts["retained"] = len(result.candidates)
    result.status = "ok" if result.candidates else "no_candidate"
    pair_names = ", ".join(
        f"{window.atoms[0] + 1}-{window.atoms[1] + 1}"
        for window in plan.windows
    )
    result.message = (
        f"{len(result.candidates)} qualified constrained-preorganization seed(s) for pairs "
        f"{pair_names}. " + _fallback_note(plan)
        if result.candidates else
        f"No candidate qualified for atom pairs {pair_names}; "
        f"closest attempted geometry: {result.closest_path or 'none'}, "
        f"diagnostics: {result.diagnostics}. " + _fallback_note(plan)
    )
    return _save_guided_result(result, plan, output_dir)


def search_guided(
    *,
    structure: StructureInput,
    output_dir: str,
    ring_order: Sequence[int],
    distance_filters: Sequence[Mapping[str, object]],
    charge: int = 0,
    multiplicity: int = 1,
    backend: Literal["rdkit", "crest"] = "rdkit",
    mode: Literal["conformers", "nci"] = "conformers",
    num_confs: int = 50,
    random_seed: int = 42,
    rmsd_threshold: float = 0.5,
    timeout: int = 600,
) -> GuidedSearchResult:
    """Build constrained TS seeds. Later adapters extend this core to complexes/CREST."""
    if num_confs < 1 or rmsd_threshold < 0 or timeout < 1:
        raise ValueError("num_confs and timeout must be positive; rmsd_threshold must be nonnegative")
    if backend != "rdkit" or mode != "conformers":
        raise ValueError(f"guided backend={backend!r}, mode={mode!r} is not implemented")
    prepared = prepare_structure(PreparationRequest(
        structure=structure,
        output_dir=os.path.join(output_dir, "resolved_graph"),
        total_charge=charge,
        multiplicity=multiplicity,
        random_seed=random_seed,
        strategy=BuildStrategy(embed=False, optimize=False),
    ))
    if prepared.status not in ("ok", "assembly_failed"):
        return GuidedSearchResult(
            status="build_failed", message=f"structure resolution failed: {prepared.message}",
            prepared_path=prepared.artifact_path, diagnostics=list(prepared.diagnostics),
        )
    plan = resolve_guidance(prepared, ring_order, distance_filters)
    if len(prepared.components) != 1:
        raise ValueError("guided multicomponent assembly is not implemented")
    return _single_component_rdkit(
        prepared, plan, output_dir, num_confs, random_seed, rmsd_threshold,
    )
