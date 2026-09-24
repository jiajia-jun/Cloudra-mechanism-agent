"""Soft distance guidance for reactants arranged toward a prospective cycle.

Public declarations use the builder's complete 1-based atom order. The core
uses 0-based indices so RDKit, assembly and xTB adapters share one graph.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

from rdkit import Chem

from cloudra.tools.core.complex_assembly import AssemblyParameters
from cloudra.tools.core.structure_builder import PreparedStructure
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
