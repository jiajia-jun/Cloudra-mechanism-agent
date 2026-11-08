"""Shared Gemmi parsing and explicit structure selections; no heavy imports at load time."""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path


def gemmi_backend():
    try:
        import gemmi
    except ImportError as exc:
        raise ImportError("Gemmi is required for PDB/mmCIF tools; install cloudra[pdb].") from exc
    return gemmi


def residue_keys(structure):
    """Copy Gemmi's native residue address; disambiguate only actual duplicates."""
    gemmi = gemmi_backend()
    addresses = {}
    for ci, chain in enumerate(structure[0]):
        for ri, residue in enumerate(chain):
            address = gemmi.AtomAddress()
            address.chain_name = chain.name
            address.res_id = residue
            addresses[(ci, ri)] = str(address).rstrip('/')
    counts = Counter(addresses.values())
    return {indices: value if counts[value] == 1 else f'{value} [{indices[0]}:{indices[1]}]'
            for indices, value in addresses.items()}


def load_structure(path: str, model_index: int = 0, chains: list[str] | None = None):
    gemmi = gemmi_backend()
    if Path(path).suffix.lower() not in {'.pdb', '.cif', '.mmcif'}:
        raise ValueError('input_path must be a .pdb, .cif or .mmcif structure file')
    structure = gemmi.read_structure(path)
    total = len(structure)
    if not 0 <= model_index < total:
        raise ValueError(f'model_index {model_index} is outside the {total} available models')
    selected = structure[model_index].clone()
    for i in reversed(range(total)):
        del structure[i]
    structure.add_model(selected)
    if chains is not None:
        if not chains:
            raise ValueError('chains must select at least one author chain ID')
        missing = set(chains) - {c.name for c in structure[0]}
        if missing:
            raise ValueError(f'Unknown author chain IDs: {sorted(missing)}')
        for i in reversed(range(len(structure[0]))):
            if structure[0][i].name not in chains:
                del structure[0][i]
    # Gemmi can classify a one-residue ATOM polymer as a ligand when the
    # file omits entity assignments. Preserve explicit mmCIF entity types;
    # use the record kind plus Gemmi's residue table only for unknown types.
    for chain in structure[0]:
        for residue in chain:
            info = gemmi.find_tabulated_residue(residue.name)
            if (residue.entity_type == gemmi.EntityType.Unknown and residue.het_flag == 'A'
                    and (info.is_amino_acid() or info.is_nucleic_acid())):
                residue.entity_type = gemmi.EntityType.Polymer
    structure.setup_entities()
    if not any(len(r) for c in structure[0] for r in c):
        raise ValueError('Selected model/chains contain no atoms')
    for chain in structure[0]:
        for residue in chain:
            for atom in residue:
                if not all(math.isfinite(value) for value in (atom.pos.x, atom.pos.y, atom.pos.z, atom.occ, atom.b_iso)):
                    raise ValueError(f'Non-finite coordinate/occupancy/B factor: {chain.name}/{residue.name} {residue.seqid}/{atom.name}')
    keys = residue_keys(structure)
    summary = summarize(structure)
    summary.update(model_count=total, selected_model_index=model_index,
                   scope='Selected model explicit coordinates only; no crystal symmetry partners.')
    return structure, keys, summary


def component_kind(residue):
    gemmi = gemmi_backend()
    if residue.is_water():
        return 'water'
    if residue.entity_type == gemmi.EntityType.Polymer:
        return 'polymer'
    if len(residue) == 1 and residue[0].element.is_metal:
        return 'metal'
    return 'ligand'


def components(structure, keys):
    return [dict(residue_key=keys[(ci, ri)], chain=chain.name,
                 residue_number=residue.seqid.num, insertion_code=residue.seqid.icode.strip(),
                 residue_name=residue.name, kind=component_kind(residue), atom_count=len(residue),
                 altlocs=sorted({a.altloc for a in residue if a.altloc != '\0'}))
            for ci, chain in enumerate(structure[0]) for ri, residue in enumerate(chain)]


def summarize(structure):
    return dict(chains=[c.name for c in structure[0]],
                residue_count=sum(len(c) for c in structure[0]),
                atom_count=sum(len(r) for c in structure[0] for r in c))


def select_altlocs(structure, keys, requested):
    changes = []
    for ci, chain in enumerate(structure[0]):
        for ri, residue in enumerate(chain):
            labels = sorted({a.altloc for a in residue if a.altloc != '\0'})
            if not labels:
                continue
            scores = {label: sum(a.occ for a in residue if a.altloc == label) /
                      sum(a.altloc == label for a in residue) for label in labels}
            selected = min(labels, key=lambda label: (-scores[label], label)) if requested == 'highest_occupancy' else requested
            if selected not in labels:
                raise ValueError(f'altloc {requested!r} does not exist for {keys[(ci, ri)]}; available: {labels}')
            removed = [dict(atom_name=a.name, altloc=a.altloc) for a in residue
                       if a.altloc not in {'\0', selected}]
            for ai in reversed(range(len(residue))):
                if residue[ai].altloc not in {'\0', selected}:
                    del residue[ai]
            names = [a.name for a in residue]
            if len(names) != len(set(names)):
                raise ValueError(f'Shared and selected conformer contain duplicate atom names for {keys[(ci, ri)]}')
            changes.append(dict(kind='altloc_selection', residue_key=keys[(ci, ri)],
                                selected_altloc=selected, occupancy_scores=scores, occupancy_score_basis='mean of labeled-atom occupancies; shared atoms excluded',
                                tied=sorted(label for label in labels if scores[label] == scores[selected]),
                                removed_atoms=removed))
    return changes


def filter_components(structure, keys, options, candidate_waters):
    keep, remove = set(options['keep_residue_keys']), set(options['remove_residue_keys'])
    known = set(keys.values())
    if keep & remove:
        raise ValueError(f'Residue keys selected for both keep and remove: {sorted(keep & remove)}')
    if (keep | remove) - known:
        raise ValueError(f'Residue keys absent from selected model/chains: {sorted((keep | remove) - known)}')
    changes = []
    retained = {}
    for ci, chain in enumerate(structure[0]):
        next_ri = 0
        drops = []
        for ri, residue in enumerate(chain):
            key, kind = keys[(ci, ri)], component_kind(residue)
            discard = ((kind == 'water' and (options['waters'] == 'none' or
                       options['waters'] == 'candidates' and key not in candidate_waters)) or
                       kind == 'ligand' and options['ligands'] == 'none' or
                       kind == 'metal' and options['metals'] == 'none')
            discard = key in remove or discard and key not in keep
            if discard:
                drops.append(ri)
                changes.append(dict(kind='removed_residue', residue_key=key, residue_name=residue.name,
                                    atoms=[a.name for a in residue], reason='exact_selection' if key in remove else kind))
            else:
                retained[(ci, next_ri)] = key
                next_ri += 1
        for ri in reversed(drops):
            del chain[ri]
    if not any(len(r) for c in structure[0] for r in c):
        raise ValueError('Component selection removed every atom')
    empty = [ci for ci, chain in enumerate(structure[0]) if not len(chain)]
    for ci in reversed(empty):
        del structure[0][ci]
    retained = {(ci - sum(removed < ci for removed in empty), ri): key
                for (ci, ri), key in retained.items()}
    return retained, changes


def write_structure(structure, path):
    """Reject identifiers PDB cannot represent instead of silently truncating."""
    if Path(path).suffix.lower() == '.pdb':
        for chain in structure[0]:
            if len(chain.name) > 1:
                raise ValueError(f'PDB cannot preserve author chain ID {chain.name!r}; use .cif output')
            for residue in chain:
                if not -999 <= residue.seqid.num <= 9999 or len(residue.name) > 3:
                    raise ValueError(f'PDB cannot preserve residue {chain.name}/{residue.name} {residue.seqid}; use .cif output')
                for atom in residue:
                    if len(atom.name) > 4 or any(abs(v) >= 10000 for v in (atom.pos.x, atom.pos.y, atom.pos.z)):
                        raise ValueError('PDB atom names/coordinates exceed fixed-width fields; use .cif output')
        if sum(len(r) for c in structure[0] for r in c) > 99999:
            raise ValueError('PDB atom serial capacity exceeded; use .cif output')
        structure.write_pdb(str(path))
    else:
        structure.make_mmcif_document().write_file(str(path))


def verify_structure(expected, path):
    gemmi = gemmi_backend()
    actual = gemmi.read_structure(str(path))
    if len(actual) != 1 or summarize(expected) != summarize(actual):
        raise ValueError('Written structure does not preserve selected chain/residue/atom counts')
    for ec, ac in zip(expected[0], actual[0], strict=True):
        for er, ar in zip(ec, ac, strict=True):
            if (er.name, str(er.seqid)) != (ar.name, str(ar.seqid)):
                raise ValueError('Written structure changed author residue identifiers; use .cif output')
            for ea, aa in zip(er, ar, strict=True):
                if ((ea.name, ea.element.name, ea.altloc) != (aa.name, aa.element.name, aa.altloc)
                        or not math.isfinite(ea.pos.dist(aa.pos)) or ea.pos.dist(aa.pos) > 0.002
                        or abs(ea.occ - aa.occ) > 0.006 or abs(ea.b_iso - aa.b_iso) > 0.006):
                    raise ValueError('Written structure changed atom identity or coordinates')
    return actual


def prune_connections(structure):
    """Remove links whose selected atoms no longer exist; record the lost facts."""
    changes = []
    for i in reversed(range(len(structure.connections))):
        connection = structure.connections[i]
        valid = True
        for address in (connection.partner1, connection.partner2):
            if structure[0].find_cra(address, ignore_segment=True).atom is None:
                valid = False
        if not valid:
            changes.append(dict(action='remove_connection', connection_name=connection.name,
                                partner1=str(connection.partner1), partner2=str(connection.partner2),
                                reason='Referenced atom/conformer not retained in selected output'))
            structure.connections.pop(i)
    serials = {atom.serial for chain in structure[0] for residue in chain for atom in residue}
    existing = structure.conect_map
    retained = Counter((first, second) for first, seconds in existing.items() for second in seconds
                       if first in serials and second in serials)
    dropped = sum(len(seconds) for seconds in existing.values()) - sum(retained.values())
    if dropped:
        changes.append(dict(action='remove_conect_records', count=dropped,
                            reason='Referenced atom serials not retained in selected output'))
        structure.clear_conect()
        for first, second in sorted({tuple(sorted(pair)) for pair in retained}):
            order = max(retained[(first, second)], retained[(second, first)])
            structure.add_conect(first, second, order)
    return changes


def annotation_inventory(structure):
    return dict(connections=len(structure.connections), conect_records=sum(len(v) for v in structure.conect_map.values()),
                raw_remarks=len(structure.raw_remarks), helices=len(structure.helices), sheets=len(structure.sheets),
                assemblies=len(structure.assemblies), ncs=len(structure.ncs))
