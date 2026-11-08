"""Shared, explicit-coordinate PDB interaction evidence.

Gemmi contacts are distance candidates. PLIP's atom typing, angular rules and
metal geometry estimates are kept separately and are never inferred from counts.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
import string
import tempfile
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

_RULE_UNITS = {
    'WATER_BRIDGE_MINDIST': 'angstrom',
    'WATER_BRIDGE_MAXDIST': 'angstrom',
    'WATER_BRIDGE_OMEGA_MIN': 'degree',
    'WATER_BRIDGE_OMEGA_MAX': 'degree',
    'WATER_BRIDGE_THETA_MIN': 'degree',
    'METAL_DIST_MAX': 'angstrom',
}
_PLIP_LOCK = threading.Lock()  # PLIP thresholds are process-global module attributes.
_SCOPE = 'Selected model explicit coordinates only; no crystallographic symmetry partners.'


def validate_interaction_overrides(overrides: dict[str, float]) -> None:
    """Validate public names and numeric domains without importing optional backends."""
    if not isinstance(overrides, dict):
        raise ValueError('interaction_overrides must be a mapping of PLIP parameter names to numbers')
    for name, value in overrides.items():
        if name not in _RULE_UNITS:
            raise ValueError(f'Unsupported interaction override: {name}')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{name} must be a finite number')
        if _RULE_UNITS[name] == 'degree':
            if not 0 <= value <= 180:
                raise ValueError(f'{name} must be between 0 and 180 degrees')
        elif value <= 0:
            raise ValueError(f'{name} must be greater than zero angstrom')
    for lower, upper in [('WATER_BRIDGE_MINDIST', 'WATER_BRIDGE_MAXDIST'),
                         ('WATER_BRIDGE_OMEGA_MIN', 'WATER_BRIDGE_OMEGA_MAX')]:
        if lower in overrides and upper in overrides and overrides[lower] >= overrides[upper]:
            raise ValueError(f'{lower} must be less than {upper}')


def _status(status: str, reason: str) -> dict[str, str]:
    return {'status': status, 'reason': reason}


def _version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _altloc(atom: Any) -> str:
    return atom.altloc.strip('\x00 ')


def _compatible(first: Any, second: Any) -> bool:
    a, b = _altloc(first), _altloc(second)
    return not a or not b or a == b


def _atom_info(chain: Any, residue: Any, atom: Any, residue_key: str) -> dict[str, Any]:
    component = 'water' if residue.is_water() else ('polymer' if residue.het_flag == 'A' else 'ligand')
    return {
        'residue_key': residue_key,
        'chain': chain.name,
        'residue_number': residue.seqid.num,
        'insertion_code': residue.seqid.icode.strip(),
        'residue_name': residue.name,
        'atom_name': atom.name,
        'element': atom.element.name,
        'altloc': _altloc(atom),
        'occupancy': float(atom.occ),
        'b_factor': float(atom.b_iso),
        'component': component,
    }


def _inventory(structure: Any, residue_keys: dict[tuple[int, int], str]):
    atoms, waters, metals = {}, {}, {}
    for ci, chain in enumerate(structure[0]):
        for ri, residue in enumerate(chain):
            if (ci, ri) not in residue_keys:
                raise ValueError(f'Missing residue_key for chain index {ci}, residue index {ri}')
            for ai, atom in enumerate(residue):
                if not all(math.isfinite(value) for value in
                           (atom.pos.x, atom.pos.y, atom.pos.z, atom.occ, atom.b_iso)):
                    raise ValueError(f'Atom coordinates, occupancy and B factor must be finite: '
                                     f'{residue_keys[ci, ri]} {atom.name}')
                index = (ci, ri, ai)
                info = _atom_info(chain, residue, atom, residue_keys[ci, ri])
                atoms[index] = (atom, info)
                if residue.is_water() and atom.element.name == 'O':
                    waters[index] = {
                        'residue_key': info['residue_key'], 'water': info,
                        'reasons': [], 'polar_contacts': [], 'metal_contacts': [],
                        'plip_water_bridges': [],
                    }
                if atom.element.is_metal:
                    metals[index] = {
                        'residue_key': info['residue_key'], 'element': info['element'],
                        'metal': info, 'candidates': [], 'plip_interactions': [],
                        'explicit_connections': [],
                    }
    return atoms, waters, metals


def _explicit_connections(structure: Any, atoms: dict, metals: dict) -> None:
    lookup: dict[tuple, list] = {}
    for index, (atom, info) in atoms.items():
        key = (info['chain'], info['residue_number'], info['insertion_code'], info['atom_name'])
        lookup.setdefault(key, []).append(index)

    def resolve(address):
        key = (address.chain_name, address.res_id.seqid.num,
               address.res_id.seqid.icode.strip(), address.atom_name)
        return [index for index in lookup.get(key, [])
                if (not address.res_id.name or atoms[index][1]['residue_name'] == address.res_id.name)
                and (not address.altloc.strip('\x00 ')
                     or _altloc(atoms[index][0]) == address.altloc.strip('\x00 '))]

    for connection in structure.connections:
        first, second = resolve(connection.partner1), resolve(connection.partner2)
        for left, right in [(first, second), (second, first)]:
            for metal_index in left:
                if metal_index not in metals:
                    continue
                for target_index in right:
                    metal, target = atoms[metal_index][0], atoms[target_index][0]
                    if not _compatible(metal, target):
                        continue
                    metals[metal_index]['explicit_connections'].append({
                        'atom': atoms[target_index][1], 'source': 'input LINK/struct_conn',
                        'connection_name': connection.name, 'connection_type': connection.type.name,
                        'asu': connection.asu.name,
                        'within_explicit_coordinates': connection.asu.name != 'Different',
                        'reported_distance': float(connection.reported_distance),
                        'explicit_coordinate_distance': float(metal.pos.dist(target.pos)),
                    })


def _distance_candidates(gemmi: Any, structure: Any, atoms: dict, waters: dict,
                         metals: dict, rules: dict[str, float]) -> None:
    # An empty, non-crystallographic UnitCell makes the index cover the model's
    # bounding box. Passing structure.cell could wrap contacts or add images.
    radius = max(rules['WATER_BRIDGE_MAXDIST'], rules['METAL_DIST_MAX'])
    neighbors = gemmi.NeighborSearch(structure[0], gemmi.UnitCell(), radius).populate(include_h=False)

    def near(index, minimum, maximum):
        center = atoms[index][0]
        found = {}
        for mark in neighbors.find_neighbors(center, min_dist=minimum, max_dist=maximum):
            other_index = (mark.chain_idx, mark.residue_idx, mark.atom_idx)
            if mark.image_idx != 0 or other_index == index:
                continue
            target, info = atoms[other_index]
            if info['element'] not in {'N', 'O', 'S'} or not _compatible(center, target):
                continue
            distance = float(center.pos.dist(target.pos))
            if minimum <= distance <= maximum:
                found[other_index] = {**info, 'distance': distance, 'basis': 'distance_screen_only'}
        return sorted(found.items())

    for index, water in waters.items():
        water['polar_contacts'] = [info for _, info in near(index, rules['WATER_BRIDGE_MINDIST'],
                                                          rules['WATER_BRIDGE_MAXDIST'])
                                   if info['component'] != 'water']
        if water['polar_contacts']:
            water['reasons'].append('polar_contact_candidate')
    for index, site in metals.items():
        # PLIP's metal cutoff is strict (<); it is a generic search limit, not
        # an element-specific bond length or a coordination-number criterion.
        site['candidates'] = [info for _, info in near(index, 0, rules['METAL_DIST_MAX'])
                              if info['distance'] < rules['METAL_DIST_MAX']]
        for target_index, info in near(index, 0, rules['METAL_DIST_MAX']):
            if target_index not in waters or info['distance'] >= rules['METAL_DIST_MAX']:
                continue
            water = waters[target_index]
            water['metal_contacts'].append({**site['metal'], 'distance': info['distance'],
                                            'basis': 'distance_screen_only'})
            if 'metal_related_water' not in water['reasons']:
                water['reasons'].append('metal_related_water')


def _plip_input(structure: Any, gemmi: Any, atoms: dict, directory: str, conformer: str = ''):
    """Write shared atoms plus one compatible altloc, preserving original indices."""
    chains = string.ascii_uppercase + string.ascii_lowercase + string.digits
    copied = structure.clone()
    copied[0].num = 1
    copied.connections.clear()
    copied_serials = {}
    serial = 0
    chain_count = 0
    for ci, chain in enumerate(copied[0]):
        residue_count = 0
        for ri, residue in enumerate(chain):
            kept = [ai for ai, atom in enumerate(residue) if _altloc(atom) in ('', conformer)]
            for ai in range(len(residue) - 1, -1, -1):
                if _altloc(residue[ai]) not in ('', conformer):
                    del residue[ai]
            if not kept:
                continue
            if residue_count == 0:
                if chain_count >= len(chains):
                    raise NotImplementedError('PLIP temporary PDB supports at most 62 nonempty chains')
                chain.name = chains[chain_count]
                chain_count += 1
            residue_count += 1
            if residue_count > 9999:
                raise NotImplementedError('PLIP temporary PDB supports at most 9999 residues per chain')
            if len(residue.name) > 3:
                raise NotImplementedError(f'PLIP temporary PDB cannot express residue name {residue.name!r}')
            names = [atom.name for atom in residue]
            if len(names) != len(set(names)):
                raise NotImplementedError('PLIP analysis cannot safely process duplicate atom names '
                                          'within one compatible conformer')
            residue.seqid = gemmi.SeqId(residue_count, ' ')
            residue.segment = ''
            for original_ai, atom in zip(kept, residue, strict=True):
                if len(atom.name) > 4 or any(not math.isfinite(p) or not -999.999 <= p <= 9999.999
                                             for p in (atom.pos.x, atom.pos.y, atom.pos.z)):
                    raise NotImplementedError('PLIP temporary PDB cannot express atom names or coordinates')
                serial += 1
                if serial > 99999:
                    raise NotImplementedError('PLIP temporary PDB supports at most 99999 atoms')
                atom.serial = serial
                atom.altloc = '\x00'
                copied_serials[serial] = (ci, ri, original_ai)
        for ri in range(len(chain) - 1, -1, -1):
            if not len(chain[ri]):
                del chain[ri]
    for ci in range(len(copied[0]) - 1, -1, -1):
        if not len(copied[0][ci]):
            del copied[0][ci]
    options = gemmi.PdbWriteOptions()
    options.preserve_serial = True
    options.ter_records = False
    options.link_records = False
    options.ssbond_records = False
    options.conect_records = False
    options.seqres_records = False
    options.cryst1_record = False
    path = Path(directory) / 'analysis.pdb'
    copied.write_pdb(str(path), options)
    return path, copied_serials


def _finite(value: Any):
    number = float(value)
    return number if math.isfinite(number) else None


def _plip_results(complex_: Any, serials: dict, atoms: dict, waters: dict,
                  metals: dict, failures: list[str]) -> None:
    def original(serial):
        try:
            index = serials[int(serial)]
            return index, atoms[index][1]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f'PLIP atom {serial!r} cannot be mapped to the original input') from error

    for interactions in complex_.interaction_sets.values():
        for bridge in interactions.water_bridges:
            try:
                water_index, _ = original(bridge.water_orig_idx)
                _, acceptor = original(bridge.a_orig_idx)
                _, donor = original(bridge.d_orig_idx)
                if water_index not in waters:
                    raise ValueError('PLIP water bridge does not map to an input water oxygen')
                record = {
                    'source': 'PLIP', 'acceptor': acceptor, 'donor': donor,
                    'ligand_residue_key': (acceptor if bridge.protisdon else donor)['residue_key'],
                    'acceptor_type': bridge.atype, 'donor_type': bridge.dtype,
                    'distance_aw': _finite(bridge.distance_aw), 'distance_dw': _finite(bridge.distance_dw),
                    'donor_angle': _finite(bridge.d_angle), 'water_angle': _finite(bridge.w_angle),
                    'protein_is_donor': bool(bridge.protisdon), 'bridge_type': bridge.type,
                }
                if record not in waters[water_index]['plip_water_bridges']:
                    waters[water_index]['plip_water_bridges'].append(record)
                if 'plip_water_bridge' not in waters[water_index]['reasons']:
                    waters[water_index]['reasons'].append('plip_water_bridge')
            except ValueError as error:
                failures.append(str(error))
        for interaction in interactions.metal_complexes:
            try:
                metal_index, _ = original(interaction.metal_orig_idx)
                _, target = original(interaction.target_orig_idx)
                if metal_index not in metals:
                    raise ValueError('PLIP metal does not map to an input metal atom')
                record = {
                    'source': 'PLIP', 'atom': target,
                    'ligand_residue_key': metals[metal_index]['residue_key'],
                    'donor_type': interaction.target_type, 'metal_type': interaction.metal_type,
                    'location': interaction.location, 'distance': _finite(interaction.distance),
                    'geometry': interaction.geometry, 'estimated_coordination_number': interaction.coordination_num,
                    'observed_partners': int(interaction.num_partners), 'rms': _finite(interaction.rms),
                }
                if record not in metals[metal_index]['plip_interactions']:
                    metals[metal_index]['plip_interactions'].append(record)
            except ValueError as error:
                failures.append(str(error))


def _run_plip(structure: Any, gemmi: Any, atoms: dict, waters: dict, metals: dict,
              config: Any, rules: dict[str, float], warnings: list[str]):
    try:
        # OpenBabel 3.2.1 and RDKit share native-library names. With this
        # validated backend set, loading OpenBabel first can segfault a later
        # RDKit import in the existing chemistry tool catalog. Initialize the
        # optional installed RDKit before PLIP's OpenBabel import; do not add a
        # dependency when RDKit is absent, or load it during schema discovery.
        if importlib.util.find_spec('rdkit') is not None:
            importlib.import_module('rdkit.Chem')
        preparation = importlib.import_module('plip.structure.preparation')
    except ImportError as error:
        return _status('unavailable', f'PLIP engine unavailable: {error}')
    failures, unsupported = [], []
    labels = sorted({_altloc(atom) for atom, _ in atoms.values()} - {''}) or ['']
    with tempfile.TemporaryDirectory(prefix='cloudra-plip-') as directory:
        settings = {**rules, 'NOFIX': True, 'NOFIXFILE': True, 'MODEL': 1}
        previous = {name: getattr(config, name) for name in settings}
        try:
            for name, value in settings.items():
                setattr(config, name, value)
            for number, label in enumerate(labels):
                try:
                    conformer_directory = Path(directory) / str(number)
                    conformer_directory.mkdir()
                    path, serials = _plip_input(structure, gemmi, atoms, str(conformer_directory), label)
                    complex_ = preparation.PDBComplex()
                    complex_.output_path = str(conformer_directory)
                    complex_.load_pdb(str(path))
                    for ligand in complex_.ligands:
                        try:
                            complex_.characterize_complex(ligand)
                        except Exception as error:  # Preserve other completed ligand sites/conformers.
                            failures.append(f'PLIP conformer {label!r} ligand {ligand.hetid}: '
                                            f'{type(error).__name__}: {error}')
                    _plip_results(complex_, serials, atoms, waters, metals, failures)
                except NotImplementedError as error:
                    unsupported.append(str(error))
                except Exception as error:
                    failures.append(f'PLIP conformer {label!r} analysis failed: {type(error).__name__}: {error}')
            warnings.append('PLIP analyzed temporary PDB copies containing shared atoms plus each '
                            f'compatible altloc separately ({labels!r}), with mapped chain/residue/atom identities; '
                            'input coordinates and identifiers were not changed. '
                            'Temporary analysis coordinates use PDB precision (0.001 angstrom). '
                            f'Polar hydrogen addition was {"disabled" if config.NOHYDRO else "enabled"}; '
                            'added hydrogen positions affect PLIP donor angles. '
                            'PLIP input fixing was disabled to preserve the original-atom mapping. '
                            'Identical interaction records across compatible copies were deduplicated.')
        finally:
            for name, value in previous.items():
                setattr(config, name, value)
    if failures:
        return _status('failed', '; '.join(failures + unsupported))
    if unsupported:
        return _status('unsupported', '; '.join(unsupported))
    return _status('completed', 'PLIP protein-ligand water bridges and metal interactions analyzed '
                   'in separate compatible conformers; waters/metals outside eligible ligand sites '
                   'have distance candidates only')


def analyze_interactions(structure: Any, residue_keys: dict[tuple[int, int], str],
                         overrides: dict[str, float]) -> dict[str, Any]:
    """Analyze one selected Gemmi model, retaining original atom/residue identities.

    Failure of an optional analysis does not erase inventory or completed evidence.
    Callers must inspect analysis_status before treating candidate sets as complete.
    """
    validate_interaction_overrides(overrides)
    gemmi = importlib.import_module('gemmi')
    if len(structure) != 1:
        raise ValueError('Interaction analysis requires exactly one selected model')
    atoms, waters, metals = _inventory(structure, residue_keys)
    _explicit_connections(structure, atoms, metals)
    warnings = [_SCOPE,
                'All water labels are geometric candidates, not evidence of catalytic or biological importance. '
                'Metal distance-screen candidate counts are not formal coordination numbers.']
    versions = {'gemmi': gemmi.__version__, 'plip': _version('plip'), 'openbabel': _version('openbabel')}
    effective = {'source': 'plip.basic.config', 'backend_version': versions['plip'],
                 'scope': _SCOPE, 'parameters': {},
                 'coverage': 'PLIP eligible protein-ligand sites; supplementary Gemmi N/O/S distance candidates. '
                 'METAL_DIST_MAX is a generic candidate search limit, not an element-specific bond length.'}
    with _PLIP_LOCK:
        try:
            config = importlib.import_module('plip.basic.config')
            rules = {name: float(getattr(config, name)) for name in _RULE_UNITS}
        except (ImportError, AttributeError, TypeError, ValueError) as error:
            plip_status = _status('unavailable', f'PLIP default rules unavailable: {error}; '
                                  'no fallback distance or angle thresholds were invented')
        else:
            rules.update(overrides)
            validate_interaction_overrides(rules)
            effective['parameters'] = {
                name: {'value': value, 'unit': _RULE_UNITS[name],
                       'source': 'override' if name in overrides else 'plip.basic.config'}
                for name, value in rules.items()
            }
            _distance_candidates(gemmi, structure, atoms, waters, metals, rules)
            try:
                plip_status = _run_plip(structure, gemmi, atoms, waters, metals, config, rules, warnings)
            except Exception as error:
                plip_status = _status('failed', f'PLIP analysis failed: {type(error).__name__}: {error}')
    status = {'water_candidates': dict(plip_status), 'metal_sites': dict(plip_status), 'plip': plip_status}
    if plip_status['status'] != 'completed':
        warnings.append(plip_status['reason'])
        if effective['parameters']:
            warnings.append('Gemmi distance candidates and explicit input connections are retained; '
                            'PLIP-dependent interaction evidence is incomplete.')
    return {'water_candidates': [water for water in waters.values() if water['reasons']],
            'metal_sites': list(metals.values()), 'effective_rules': effective,
            'analysis_status': status, 'warnings': warnings, 'backend_versions': versions}
