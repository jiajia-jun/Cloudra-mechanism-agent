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
from functools import partial
from pathlib import Path
from typing import Literal, Mapping, Sequence

from rdkit import Chem, DistanceGeometry
from rdkit.Chem import AllChem, rdDistGeom, rdMolAlign

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.complex_assembly import (
    MMFF_CONSTRAINT_FORCE_CONSTANT,
    AssemblyParameters,
)
from cloudra.tools.core.crest_runner import CrestRunRequest, run_crest
from cloudra.tools.core.geometry import kabsch_rmsd
from cloudra.tools.core.structure_artifacts import read_trajectory, read_xyz_atoms
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
    index_base: int = 1


def _numbering(prepared: PreparedStructure, index_base: int) -> str:
    return ", ".join(
        f"{identity.index + index_base}={identity.symbol}"
        for identity in prepared.atom_identities
    )


def _bad(prepared: PreparedStructure, detail: str, *, index_base: int = 1) -> ValueError:
    return ValueError(f"{detail}. Resolved atoms ({index_base}-based): {_numbering(prepared, index_base)}")


def load_resolved_graph(prepared: PreparedStructure, *, index_base: int = 1, allow_unoptimized: bool = False) -> Chem.Mol:
    """Load the builder's resolved, explicit-H graph without inventing coordinates."""
    graph_only_multi = (
        prepared.status == "assembly_failed"
        and len(prepared.components) > 1
        and all(not component.xyz_path for component in prepared.components)
    )
    bad = partial(_bad, prepared, index_base=index_base)
    explicitly_unoptimized = allow_unoptimized and all(c.embed_status in ("embedded","not_required") and c.optimization_status=="not_required" for c in prepared.components)
    if prepared.status != "ok" and not graph_only_multi and not explicitly_unoptimized:
        raise bad(f"builder status {prepared.status!r} has no usable resolved graph")
    if not prepared.components or not prepared.atom_identities:
        raise bad( "builder returned no components or atom identities")

    graph = None
    for component in prepared.components:
        path = Path(component.mol_path)
        if not path.is_file():
            raise bad(f"component MOL file is missing: {path}")
        fragment = Chem.MolFromMolFile(str(path), removeHs=False)
        if fragment is None:
            raise bad(f"component MOL file cannot be parsed: {path}")
        graph = fragment if graph is None else Chem.CombineMols(graph, fragment)

    actual = [atom.GetSymbol() for atom in graph.GetAtoms()]
    expected = [identity.symbol for identity in prepared.atom_identities]
    indices = [identity.index for identity in prepared.atom_identities]
    if len(actual) != len(expected) or actual != expected or indices != list(range(len(expected))):
        raise bad(
            f"resolved graph/identity element order mismatch: graph={actual}, identities={expected}",
        )
    return graph


def _atom_index(prepared: PreparedStructure, value: object, field: str, index_base: int = 1) -> int:
    if type(value) is not int or not index_base <= value < len(prepared.atom_identities) + index_base:
        raise _bad(prepared, f"{field} atom index {value!r} is invalid", index_base=index_base)
    return value - index_base


def resolve_explicit_filters(
    prepared: PreparedStructure,
    distance_filters: Sequence[Mapping[str, object]],
    *, index_base: int = 1,
) -> tuple[DistanceWindow, ...]:
    """Validate declared windows; absent ring edges are handled separately."""
    bad = partial(_bad, prepared, index_base=index_base)
    load_resolved_graph(prepared, index_base=index_base)
    by_pair: dict[tuple[int, int], DistanceWindow] = {}
    for row in distance_filters:
        if not isinstance(row, Mapping):
            raise bad(f"distance_filters entry must be an object, got {row!r}")
        atoms = row.get("atoms")
        if not isinstance(atoms, (list, tuple)) or len(atoms) != 2:
            raise bad(f"distance_filters atoms must contain two indices: {row!r}")
        left = _atom_index(prepared, atoms[0], "distance_filters", index_base)
        right = _atom_index(prepared, atoms[1], "distance_filters", index_base)
        if left == right:
            raise bad(f"distance_filters pair ({left + index_base}, {right + index_base}) repeats an atom")
        pair = tuple(sorted((left, right)))
        try:
            low = float(row["min_ang"])
            high = float(row["max_ang"])
        except (KeyError, TypeError, ValueError) as exc:
            raise bad(f"distance_filters pair {pair[0] + index_base}-{pair[1] + index_base} needs numeric min_ang/max_ang") from exc
        if not math.isfinite(low) or not math.isfinite(high) or low <= 0 or high < low:
            raise bad(
                f"distance_filters pair {pair[0] + index_base}-{pair[1] + index_base} has invalid window [{low}, {high}] Å",
            )
        window = DistanceWindow(pair, low, high, "explicit")
        old = by_pair.get(pair)
        if old is not None and old != window:
            raise bad(
                f"distance_filters pair {pair[0] + index_base}-{pair[1] + index_base} has conflicting duplicate windows",
            )
        by_pair[pair] = window
    return tuple(by_pair.values())


def resolve_guidance(
    prepared: PreparedStructure,
    ring_order: Sequence[int],
    distance_filters: Sequence[Mapping[str, object]],
    *,
    assembly_parameters: AssemblyParameters | None = None,
    index_base: int = 1,
) -> GuidancePlan:
    bad = partial(_bad, prepared, index_base=index_base)
    graph = load_resolved_graph(prepared, index_base=index_base)
    if not isinstance(ring_order, (list, tuple)) or (ring_order and len(ring_order) < 3):
        raise bad( "ring_order must contain at least three distinct atoms")
    ordered = tuple(_atom_index(prepared, value, "ring_order", index_base) for value in ring_order)
    if len(set(ordered)) != len(ordered):
        raise bad(f"ring_order repeats an atom: {list(ring_order)!r}")

    explicit = resolve_explicit_filters(prepared, distance_filters, index_base=index_base)
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
    if ordered and not forming:
        raise bad( "ring_order is already a fully covalent cycle; no prospective edge exists")
    return GuidancePlan(ordered, tuple(windows), tuple(forming), tuple(bonded), index_base)


def effective_window_rows(plan: GuidancePlan) -> list[dict]:
    return [
        {
            "atoms": [window.atoms[0] + plan.index_base, window.atoms[1] + plan.index_base],
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
            raise ValueError(f"positions cannot measure pair {left + plan.index_base}-{right + plan.index_base}") from exc
        if not math.isfinite(distance):
            raise ValueError(f"nonfinite distance for pair {left + plan.index_base}-{right + plan.index_base}")
        distances[f"{left + plan.index_base}-{right + plan.index_base}"] = distance
    return distances


def geometry_stereochemistry_errors(graph, positions) -> list[str]:
    """Compare declared stereochemistry with actual 3D geometry, without inference."""
    expected = Chem.Mol(graph)
    Chem.AssignStereochemistry(expected, cleanIt=True, force=True)
    chiral = {a.GetIdx():a.GetProp('_CIPCode') for a in expected.GetAtoms() if a.HasProp('_CIPCode')}
    bonds = {b.GetIdx():b.GetStereo() for b in expected.GetBonds()
             if b.GetStereo() not in (Chem.BondStereo.STEREONONE,Chem.BondStereo.STEREOANY)}
    if not chiral and not bonds:
        return []
    actual = Chem.Mol(graph)
    Chem.RemoveStereochemistry(actual)
    actual.RemoveAllConformers()
    conf = Chem.Conformer(actual.GetNumAtoms())
    conf.Set3D(True)
    for i,p in enumerate(positions):
        conf.SetAtomPosition(i,p)
    actual.AddConformer(conf)
    Chem.AssignStereochemistryFrom3D(actual, replaceExistingTags=True)
    Chem.AssignStereochemistry(actual, cleanIt=True, force=True)
    errors = []
    for i,code in chiral.items():
        atom=actual.GetAtomWithIdx(i)
        if not atom.HasProp('_CIPCode') or atom.GetProp('_CIPCode')!=code:
            errors.append(f'declared stereochemistry changed or unresolved at atom {i}')
    for i,stereo in bonds.items():
        if actual.GetBondWithIdx(i).GetStereo()!=stereo:
            errors.append(f'declared bond stereochemistry changed or unresolved at bond {i}')
    return errors


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
    reasons = geometry_stereochemistry_errors(graph, positions)
    for window in plan.windows:
        key = f"{window.atoms[0] + plan.index_base}-{window.atoms[1] + plan.index_base}"
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
    from cloudra.tools.core.complex_assembly import interfragment_clusters
    clusters = interfragment_clusters(positions, Chem.GetMolFrags(graph),
                                      [atom.GetAtomicNum() for atom in graph.GetAtoms()])
    if len(clusters) > 1:
        reasons.append(f"disconnected fragment clusters (0-based): {clusters}")
    graph_distances = Chem.GetDistanceMatrix(graph)
    for left in range(graph.GetNumAtoms()):
        for right in range(left + 1, graph.GetNumAtoms()):
            if graph_distances[left, right] <= 2 or (left, right) in plan.forming_pairs:
                continue
            if math.dist(positions[left], positions[right]) < clash_limit:
                reasons.append(f"atomic clash {left + plan.index_base}-{right + plan.index_base}")
    return not reasons, reasons, distances


@dataclass
class GuidedCandidate:
    xyz_path: str
    mol_path: str
    achieved_distances: dict[str, float]
    max_deviation_ang: float
    seed_kind: str = "constrained_preorganization"
    ring_shapes: list[dict] = field(default_factory=list)


@dataclass
class GuidedSearchResult:
    status: Literal["ok", "no_candidate", "build_failed", "engine_failed"]
    message: str
    candidates: list[GuidedCandidate] = field(default_factory=list)
    effective_windows: list[dict] = field(default_factory=list)
    forming_pairs: list[tuple[int, int]] = field(default_factory=list)
    prepared_path: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    ensemble_path: str = ""
    manifest_path: str = ""
    closest_path: str = ""
    diagnostics: list[str] = field(default_factory=list)
    constraint_targets: list[dict] = field(default_factory=list)
    crest_run_dir: str = ""


def _xyz_text(symbols: Sequence[str], positions: Sequence[Sequence[float]], comment: str) -> str:
    lines = [str(len(symbols)), comment]
    for symbol, (x, y, z) in zip(symbols, positions):
        lines.append(f"{symbol:<3} {x:>16.8f} {y:>16.8f} {z:>16.8f}")
    return "\n".join(lines) + "\n"


def _max_window_deviation(plan: GuidancePlan, distances: Mapping[str, float]) -> float:
    return max(
        (
            max(window.min_ang - distances[f"{window.atoms[0] + plan.index_base}-{window.atoms[1] + plan.index_base}"],
                0.0,
                distances[f"{window.atoms[0] + plan.index_base}-{window.atoms[1] + plan.index_base}"] - window.max_ang)
            for window in plan.windows
        ),
        default=0.0,
    )


def _fallback_note(plan: GuidancePlan) -> str:
    rows = [
        f"{window.atoms[0] + plan.index_base}-{window.atoms[1] + plan.index_base} "
        f"[{window.min_ang:g}, {window.max_ang:g}] Å"
        for window in plan.windows if window.source == "fallback"
    ]
    return "Fallback windows: " + ", ".join(rows) if rows else ""


def _validated_bounds(prepared: PreparedStructure, plan: GuidancePlan):
    """Reject incompatible windows before either RDKit embedding or placement sampling."""
    bad = partial(_bad, prepared, index_base=plan.index_base)
    graph = load_resolved_graph(prepared, index_base=plan.index_base)
    graph_distances = Chem.GetDistanceMatrix(graph)
    # Chem.CombineMols preserves atom order but leaves the combined ring cache
    # uninitialized; RDKit bounds construction requires it.
    Chem.GetSymmSSSR(graph)
    bounds = rdDistGeom.GetMoleculeBoundsMatrix(graph)
    applied: list[str] = []
    for window in plan.windows:
        left, right = window.atoms
        name = f"{left + plan.index_base}-{right + plan.index_base} ({window.source})"
        if graph.GetBondBetweenAtoms(left, right) is not None:
            symbols = [graph.GetAtomWithIdx(i).GetSymbol() for i in (left, right)]
            # Qualification already requires every input bond to survive. Check
            # that same connectivity rule at the shortest allowed distance.
            if not default_connectivity()(symbols, [(0., 0., 0.), (window.min_ang, 0., 0.)]):
                raise bad(
                    f"guided window {name} cannot preserve the input covalent bond "
                    f"({symbols[0]}-{symbols[1]}) under the existing qualification rule; "
                    "indices refer to the full structure including H, not SMILES heavy atoms; no search was run",
                )
        if (graph_distances[left, right] > 2
                and window.max_ang < AssemblyParameters().min_interfragment_distance):
            raise bad(
                f"guided window {name} cannot satisfy the nonbonded clash limit "
                f"of {AssemblyParameters().min_interfragment_distance} Å",
            )
        bounds[left, right] = window.max_ang
        bounds[right, left] = window.min_ang
        if not DistanceGeometry.DoTriangleSmoothing(bounds):
            raise bad(
                f"incompatible guided bounds when adding atom pair {name} after {applied}; "
                "no search was run",
            )
        applied.append(name)
    return bounds


def _save_guided_result(result: GuidedSearchResult, plan: GuidancePlan,
                        output_dir: str) -> GuidedSearchResult:
    os.makedirs(output_dir, exist_ok=True)
    from cloudra.tools.core.ring_conformation import describe_structure_rings

    for candidate in result.candidates:
        graph = Chem.MolFromMolFile(candidate.mol_path, removeHs=False)
        if graph is not None:
            atoms = read_xyz_atoms(candidate.xyz_path)
            candidate.ring_shapes = describe_structure_rings(graph, [pos for _, pos in atoms], plan.ring_order)
    if result.candidates:
        result.ensemble_path = os.path.join(output_dir, "confs.xyz")
        with_contents = []
        for candidate in result.candidates:
            with open(candidate.xyz_path, encoding="utf-8") as source:
                with_contents.append(source.read().rstrip() + "\n")
        atomic_write_text(result.ensemble_path, "".join(with_contents))
    result.effective_windows = effective_window_rows(plan)
    result.forming_pairs = list(plan.forming_pairs)
    result.manifest_path = os.path.join(output_dir, "guidance_manifest.json")
    atomic_write_text(result.manifest_path, json.dumps({
        "seed_kind": "constrained_preorganization",
        "atom_index_base": plan.index_base,
        "ring_shape_atom_index_base": 0,
        "status": result.status,
        "ring_order": [i + plan.index_base for i in plan.ring_order],
        "effective_windows": result.effective_windows,
        "forming_pairs": [[i + plan.index_base, j + plan.index_base] for i, j in plan.forming_pairs],
        "mmff_force_constant": MMFF_CONSTRAINT_FORCE_CONSTANT,
        "candidates": [asdict(candidate) for candidate in result.candidates],
        "counts": result.counts,
        "closest_path": result.closest_path,
        "diagnostics": result.diagnostics,
        "constraint_targets": result.constraint_targets,
        "crest_run_dir": result.crest_run_dir,
    }, indent=2) + "\n")
    return result


def _single_component_rdkit(
    prepared: PreparedStructure, plan: GuidancePlan, output_dir: str,
    num_confs: int, random_seed: int, rmsd_threshold: float, candidate_sink=None,
) -> GuidedSearchResult:
    mol = load_resolved_graph(prepared)
    if not AllChem.MMFFHasAllMoleculeParams(mol):
        return _save_guided_result(GuidedSearchResult(
            status="engine_failed",
            message="MMFF94 parameters are unavailable for guided relaxation",
            prepared_path=prepared.artifact_path,
        ), plan, output_dir)

    bounds = _validated_bounds(prepared, plan)

    params = AllChem.ETKDGv3()
    params.randomSeed = random_seed
    params.pruneRmsThresh = -1.0
    params.SetBoundsMat(bounds)
    conf_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=num_confs, params=params))
    parents = {cid: candidate_sink.capture(mol, cid, generator="ETKDG_guided", seed=random_seed) for cid in conf_ids} if candidate_sink else {}
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
    closest: tuple[float, list[list[float]], dict[str, float]] | None = None
    rejected: Counter[str] = Counter()

    def note_closest(conf_id: int) -> None:
        nonlocal closest
        positions = mol.GetConformer(conf_id).GetPositions().tolist()
        measured = measure_windows(plan, positions)
        deviation = _max_window_deviation(plan, measured)
        if closest is None or deviation < closest[0]:
            closest = (deviation, positions, measured)

    for conf_id in conf_ids:
        note_closest(conf_id)
        force_field = AllChem.MMFFGetMoleculeForceField(
            mol, mmff, confId=conf_id, ignoreInterfragInteractions=True,
        )
        if force_field is None:
            rejected["force_field_unavailable"] += 1
            if candidate_sink:
                from cloudra.tools.core.conformer_catalog import Qualification
                candidate_sink.capture(mol,conf_id,generator='guided_MMFF94',parent_id=parents[conf_id].candidate_id,
                    state='failed',qualification=Qualification(status='rejected',reasons=['force_field_unavailable']))
            continue
        for window in plan.windows:
            force_field.MMFFAddDistanceConstraint(
                *window.atoms, False, window.min_ang, window.max_ang,
                MMFF_CONSTRAINT_FORCE_CONSTANT,
            )
        force_field.Initialize()
        converged = force_field.Minimize(maxIts=2000) == 0
        note_closest(conf_id)
        if candidate_sink:
            from cloudra.tools.core.conformer_catalog import Qualification
            candidate_passed, candidate_reasons, _ = qualify_geometry(plan, mol, symbols, mol.GetConformer(conf_id).GetPositions())
            qualified = converged and candidate_passed
            candidate_sink.capture(mol, conf_id, generator="guided_MMFF94", parent_id=parents[conf_id].candidate_id,
                state="optimized" if qualified else "failed", qualification=Qualification(status="qualified" if qualified else "rejected",
                reasons=candidate_reasons + ([] if converged else ["optimization_not_converged"])))
        if not converged:
            rejected["optimization_not_converged"] += 1
            continue
        result.counts["optimized"] += 1
        positions = mol.GetConformer(conf_id).GetPositions()
        distances = measure_windows(plan, positions)
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
        _, closest_positions, closest_distances = closest
        result.closest_path = os.path.join(output_dir, "closest_attempt.xyz")
        atomic_write_text(result.closest_path, _xyz_text(
            symbols, closest_positions,
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
        f"{window.atoms[0] + plan.index_base}-{window.atoms[1] + plan.index_base}"
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


def _multi_component_rdkit(
    structure: StructureInput, prepared: PreparedStructure, plan: GuidancePlan,
    output_dir: str, charge: int, multiplicity: int, random_seed: int,
    rmsd_threshold: float, candidate_sink=None,
) -> GuidedSearchResult:
    graph = load_resolved_graph(prepared, index_base=plan.index_base)
    _validated_bounds(prepared, plan)
    built = prepare_structure(PreparationRequest(
        structure=structure,
        output_dir=os.path.join(output_dir, "guided_assembly"),
        total_charge=charge,
        multiplicity=multiplicity,
        random_seed=random_seed,
        strategy=BuildStrategy(
            embed=True, optimize=True,
            reaction_center=list(plan.forming_pairs),
            guided_windows=[
                (*window.atoms, window.min_ang, window.max_ang)
                for window in plan.windows
            ],
        ),
    ), candidate_sink=candidate_sink)
    result = GuidedSearchResult(
        status="no_candidate", message="", prepared_path=built.artifact_path,
        diagnostics=list(built.diagnostics),
        counts={"generated": len(built.assembly.candidates) if built.assembly else 0, "optimized": 0,
                "rejected": 0, "retained": 0},
    )
    if built.status != "ok" and built.status != "assembly_failed":
        result.status = "build_failed"
        result.message = f"guided component build failed: {built.message}. " + _fallback_note(plan)
        return _save_guided_result(result, plan, output_dir)
    if built.status == "assembly_failed":
        if built.assembly and built.assembly.trajectory_manifest_path:
            manifest = json.loads(Path(built.assembly.trajectory_manifest_path).read_text())
            closest_frame: tuple[float, list[str], list[list[float]], dict[str, float]] | None = None
            for row in manifest.get("trajectories", []):
                trajectory = read_trajectory(row["json_path"])
                for frame in (trajectory.initial_frame, trajectory.final_frame):
                    distances = measure_windows(plan, frame.positions)
                    deviation = _max_window_deviation(plan, distances)
                    if closest_frame is None or deviation < closest_frame[0]:
                        closest_frame = (deviation, frame.symbols, frame.positions, distances)
            if closest_frame is not None:
                _, symbols, positions, distances = closest_frame
                result.closest_path = os.path.join(output_dir, "closest_attempt.xyz")
                atomic_write_text(result.closest_path, _xyz_text(
                    symbols, positions, "closest guided assembly attempt; not qualified",
                ))
                result.diagnostics.append(f"closest achieved distances: {distances}")
        if not result.closest_path:
            result.diagnostics.append("No assembly geometry was retained for distance measurement")
        result.message = (
            f"guided assembly produced no usable seed: {built.message}. "
            f"Closest attempted geometry: {result.closest_path or 'none'}; "
            f"diagnostics: {result.diagnostics}. " + _fallback_note(plan)
        )
        return _save_guided_result(result, plan, output_dir)

    closest: tuple[float, str, list[tuple[str, list[float]]], dict[str, float]] | None = None
    rejected: Counter[str] = Counter()
    qualified: list[tuple[str, list[list[float]], dict[str, float]]] = []
    for path in (built.assembly.candidate_paths if built.assembly else []):
        atoms = read_xyz_atoms(path)
        symbols = [symbol for symbol, _position in atoms]
        positions = [position for _symbol, position in atoms]
        passed, reasons, distances = qualify_geometry(plan, graph, symbols, positions)
        if distances:
            deviation = _max_window_deviation(plan, distances)
            if closest is None or deviation < closest[0]:
                closest = (deviation, path, atoms, distances)
        if not passed:
            for reason in reasons:
                rejected[reason.split(":", 1)[0]] += 1
            continue
        qualified.append((path, positions, distances))

    heavy_indices = [atom.GetIdx() for atom in graph.GetAtoms() if atom.GetAtomicNum() > 1]
    selected: list[list[list[float]]] = []
    for path, positions, distances in qualified:
        heavy_positions = [positions[index] for index in heavy_indices]
        if any(kabsch_rmsd(heavy_positions, prior) <= rmsd_threshold for prior in selected):
            continue
        mol_path = str(Path(path).with_suffix(".mol"))
        if not Path(mol_path).is_file():
            raise ValueError(f"guided assembly did not produce matching MOL file: {mol_path}")
        selected.append(heavy_positions)
        result.candidates.append(GuidedCandidate(path, mol_path, distances, 0.0))

    result.counts["optimized"] = len(built.assembly.candidate_paths) if built.assembly else 0
    result.counts["retained"] = len(result.candidates)
    result.counts["rejected"] = result.counts["optimized"] - len(result.candidates)
    result.counts["qualified"] = len(qualified)
    result.counts["clustered_duplicates"] = len(qualified) - len(result.candidates)
    result.diagnostics.extend(f"{reason}: {count}" for reason, count in sorted(rejected.items()))
    if closest is not None:
        _, _path, atoms, distances = closest
        result.closest_path = os.path.join(output_dir, "closest_attempt.xyz")
        atomic_write_text(result.closest_path, _xyz_text(
            [symbol for symbol, _ in atoms], [position for _, position in atoms],
            "closest guided assembly attempt; not necessarily qualified",
        ))
        result.diagnostics.append(f"closest achieved distances: {distances}")
    result.status = "ok" if result.candidates else "no_candidate"
    result.message = (
        f"{len(result.candidates)} qualified constrained-preorganization seed(s). "
        if result.candidates else
        f"No guided assembly candidate qualified; closest attempted geometry: "
        f"{result.closest_path or 'none'}; diagnostics: {result.diagnostics}. "
    ) + _fallback_note(plan)
    return _save_guided_result(result, plan, output_dir)


def _crest_guided(
    prepared: PreparedStructure, plan: GuidancePlan, seed_result: GuidedSearchResult,
    output_dir: str, charge: int, multiplicity: int, mode: str, timeout: int,
) -> GuidedSearchResult:
    if seed_result.status != "ok":
        return seed_result
    graph = load_resolved_graph(prepared, index_base=plan.index_base)
    seed_path = seed_result.candidates[0].xyz_path
    seed_atoms = read_xyz_atoms(seed_path)
    seed_positions = [position for _symbol, position in seed_atoms]
    targets = []
    constrained_pairs = set()
    for window in plan.windows:
        pair = window.atoms
        constrained_pairs.add(pair)
        targets.append({"atoms": [pair[0] + 1, pair[1] + 1],
                        "target_ang": (window.min_ang + window.max_ang) / 2,
                        "source": window.source})
    for pair in plan.bonded_pairs:
        if pair not in constrained_pairs:
            targets.append({"atoms": [pair[0] + 1, pair[1] + 1],
                            "target_ang": math.dist(seed_positions[pair[0]], seed_positions[pair[1]]),
                            "source": "bonded_ring_edge"})
    constraint_text = "$constrain\n  force constant=0.02\n" + "".join(
        f"  distance: {target['atoms'][0]}, {target['atoms'][1]}, {target['target_ang']:.6f}\n"
        for target in targets
    ) + "$end\n"
    with open(seed_path, encoding="utf-8") as handle:
        seed_xyz = handle.read()
    run = run_crest(CrestRunRequest(
        xyz_text=seed_xyz, output_dir=os.path.join(output_dir, "crest"),
        charge=charge, multiplicity=multiplicity, timeout=timeout,
        electronic_character=prepared.electronic_state.get('electronic_character'),
        runtype="nci" if mode == "nci" else "default",
        noreftopo=len(prepared.components) > 1,
        constraint_text=constraint_text, run_label="guided",
    ))
    result = GuidedSearchResult(
        status="no_candidate", message="", prepared_path=seed_result.prepared_path,
        diagnostics=list(run.diagnostics),
        counts={"generated": len(run.conformers), "optimized": len(run.conformers),
                "rejected": 0, "retained": 0},
        constraint_targets=targets, crest_run_dir=run.run_dir,
    )
    if not run.scientific_success:
        result.status = "engine_failed"
        result.message = (
            f"CREST guided search failed ({run.termination_reason}, {run.stage}); "
            f"run artifacts: {run.run_dir}. " + _fallback_note(plan)
        )
        return _save_guided_result(result, plan, output_dir)
    closest: tuple[float, object, dict[str, float]] | None = None
    rejected: Counter[str] = Counter()
    for frame in run.conformers:
        passed, reasons, distances = qualify_geometry(
            plan, graph, frame.symbols, frame.positions,
        )
        if distances:
            deviation = _max_window_deviation(plan, distances)
            if closest is None or deviation < closest[0]:
                closest = (deviation, frame, distances)
        if not passed:
            for reason in reasons:
                rejected[reason.split(":", 1)[0]] += 1
            continue
        index = len(result.candidates)
        xyz_path = os.path.join(output_dir, f"crest_guided_seed_{index:03d}.xyz")
        mol_path = os.path.join(output_dir, f"crest_guided_seed_{index:03d}.mol")
        atomic_write_text(xyz_path, _xyz_text(
            frame.symbols, frame.positions, f"constrained CREST preorganization seed {index}",
        ))
        frame_mol = Chem.Mol(graph)
        conf = Chem.Conformer(graph.GetNumAtoms())
        for atom_index, position in enumerate(frame.positions):
            conf.SetAtomPosition(atom_index, position)
        frame_mol.RemoveAllConformers()
        frame_mol.AddConformer(conf)
        atomic_write_text(mol_path, Chem.MolToMolBlock(frame_mol))
        result.candidates.append(GuidedCandidate(xyz_path, mol_path, distances, 0.0))
    result.counts["retained"] = len(result.candidates)
    result.counts["rejected"] = len(run.conformers) - len(result.candidates)
    result.diagnostics.extend(f"{reason}: {count}" for reason, count in sorted(rejected.items()))
    if closest is not None:
        _, frame, distances = closest
        result.closest_path = os.path.join(output_dir, "closest_crest_attempt.xyz")
        atomic_write_text(result.closest_path, _xyz_text(
            frame.symbols, frame.positions, "closest CREST guided attempt; not necessarily qualified",
        ))
        result.diagnostics.append(f"closest achieved distances: {distances}")
    result.status = "ok" if result.candidates else "no_candidate"
    result.message = (
        f"{len(result.candidates)} qualified CREST preorganization seed(s). "
        if result.candidates else
        f"No CREST frame satisfied all guided windows; closest: {result.closest_path or 'none'}. "
    ) + _fallback_note(plan)
    return _save_guided_result(result, plan, output_dir)


def search_guided(
    *,
    structure: StructureInput,
    output_dir: str,
    ring_order: Sequence[int],
    distance_filters: Sequence[Mapping[str, object]],
    charge: int = 0,
    multiplicity: int = 1,
    electronic_character: Literal["closed_shell", "open_shell"] | None = None,
    backend: Literal["rdkit", "crest"] = "rdkit",
    mode: Literal["conformers", "nci"] = "conformers",
    num_confs: int = 50,
    random_seed: int = 42,
    rmsd_threshold: float = 0.5,
    timeout: int = 600,
    index_base: int = 1,
    candidate_sink=None,
) -> GuidedSearchResult:
    """Build constrained TS seeds. Later adapters extend this core to complexes/CREST."""
    if num_confs < 1 or rmsd_threshold < 0 or timeout < 1:
        raise ValueError("num_confs and timeout must be positive; rmsd_threshold must be nonnegative")
    if mode not in ("conformers", "nci") or (backend == "rdkit" and mode != "conformers"):
        raise ValueError(f"ring_order is unsupported with backend={backend!r}, mode={mode!r}")
    prepared = prepare_structure(PreparationRequest(
        structure=structure,
        output_dir=os.path.join(output_dir, "resolved_graph"),
        total_charge=charge,
        multiplicity=multiplicity,
        electronic_character=electronic_character,
        random_seed=random_seed,
        strategy=BuildStrategy(embed=False, optimize=False),
    ))
    if prepared.status not in ("ok", "assembly_failed"):
        return GuidedSearchResult(
            status="build_failed", message=f"structure resolution failed: {prepared.message}",
            prepared_path=prepared.artifact_path, diagnostics=list(prepared.diagnostics),
        )
    if prepared.electronic_state["requires_spin_aware_geometry"]:
        return GuidedSearchResult(
            status="build_failed",
            message="Guided seed generation cannot represent this electronic-state declaration or "
            "radical-marked graph because its pre-relaxation uses MMFF94. Supply an explicit MOL "
            "graph plus XYZ geometry with an electronic-state-aware QM optimization calculation. "
            "The current CREST interface cannot represent open-shell singlets; other declared states "
            "of single components can use unguided CREST.",
            prepared_path=prepared.artifact_path,
        )
    plan = resolve_guidance(prepared, ring_order, distance_filters, index_base=index_base)
    if len(prepared.components) != 1:
        seed_result = _multi_component_rdkit(
            structure, prepared, plan, output_dir, charge, multiplicity, random_seed,
            rmsd_threshold, candidate_sink,
        )
    else:
        seed_result = _single_component_rdkit(
            prepared, plan, output_dir, num_confs, random_seed, rmsd_threshold, candidate_sink,
        )
    if backend == "crest":
        return _crest_guided(
            prepared, plan, seed_result, output_dir, charge, multiplicity, mode, timeout,
        )
    return seed_result
