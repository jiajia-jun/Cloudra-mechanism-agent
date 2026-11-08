"""Gemmi sequence evidence and selective PDBFixer repair.

OpenMM receives a temporary mmCIF with synthetic identifiers.  Original Gemmi
residues are the authority for author IDs, insertion codes and atom metadata;
only actual backend additions/replacements are merged back into that structure.
"""

from importlib.metadata import PackageNotFoundError, version
from io import StringIO

_MAINCHAIN = {'N', 'CA', 'C', 'O'}


def _versions():
    result = {}
    for package in ('gemmi', 'pdbfixer', 'openmm'):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            pass
    return result


def _altlocs(residue):
    return sorted({atom.altloc for atom in residue if atom.altloc not in ('', ' ', '\0')}) or ['']


def _is_template_target(residue):
    # Water molecules and isolated ions have no polymer heavy-atom template.
    return not residue.is_water() and not (len(residue) == 1 and residue[0].element.is_metal)


def _make_fixer(structure, conformer=''):
    """Load one compatible conformer without PDB truncation or silent renaming."""
    import gemmi
    from openmm import Platform
    from pdbfixer import PDBFixer

    staged = structure.clone()
    staged_model = gemmi.Model('1')
    selected_atoms = []
    for ci, chain in enumerate(structure[0]):
        staged_chain = None
        previous_segment = None
        for ri, original in enumerate(chain):
            # Separate polymer subchains from same-author-chain heterogens.
            # PDBFixer uses topology chain boundaries for terminal atoms.
            segment = (original.subchain, original.entity_type)
            if staged_chain is None or segment != previous_segment:
                staged_chain = gemmi.Chain(f'backend{len(staged_model)}')
                staged_model.add_chain(staged_chain)
                staged_chain = staged_model[-1]
                previous_segment = segment
            residue = original.clone()
            labels = _altlocs(residue)
            chosen = conformer if conformer in labels else labels[0]
            for ai in range(len(residue) - 1, -1, -1):
                if residue[ai].altloc not in ('', ' ', '\0', chosen):
                    del residue[ai]
            if not len(residue):
                raise ValueError(f'Residue {ci}:{ri} has no atoms in its selected conformer')
            for atom in residue:
                atom.altloc = '\0'
            # Keep every original residue distinct, including identical author IDs.
            residue.seqid = gemmi.SeqId(1000 * (ri + 1), ' ')
            residue.subchain = staged_chain.name
            residue.label_seq = ri + 1
            selected_atoms.append((ci, ri, residue.name, [atom.name for atom in residue]))
            staged_chain.add_residue(residue)
    del staged[0]
    staged.add_model(staged_model)
    staged.connections.clear()
    fixer = PDBFixer(pdbxfile=StringIO(staged.make_mmcif_document().as_string()), platform=Platform.getPlatformByName('Reference'))
    residues = list(fixer.topology.residues())
    if len(residues) != len(selected_atoms):
        raise ValueError('OpenMM mmCIF import changed the residue count')
    mapping = {}
    for backend, (ci, ri, name, atom_names) in zip(residues, selected_atoms, strict=True):
        atoms = list(backend.atoms())
        if len(atoms) != len(atom_names):
            raise ValueError(f'OpenMM mmCIF import changed atom count for residue {ci}:{ri}')
        # OpenMM canonicalizes some residue/atom names on read.  This is not an
        # authorized nonstandard replacement, so restore the supplied names.
        backend.name = name
        for atom, atom_name in zip(atoms, atom_names, strict=True):
            atom.name = atom_name
        mapping[(ci, ri)] = backend
    # Transfer explicit supported covalent/disulfide links after identifier
    # staging.  Metal contacts remain input evidence, not invented constraints.
    bonds = {frozenset((a, b)) for a, b in fixer.topology.bonds()}
    for connection in structure.connections:
        if connection.type not in (gemmi.ConnectionType.Covale, gemmi.ConnectionType.Disulf):
            continue
        partners = []
        for address in (connection.partner1, connection.partner2):
            cra = structure[0].find_cra(address, ignore_segment=True)
            if cra.atom is None or cra.residue is None:
                break
            position = next(((ci, ri) for ci, chain in enumerate(structure[0]) for ri, residue in enumerate(chain) if residue == cra.residue), None)
            if position is None:
                break
            labels = _altlocs(cra.residue)
            selected = conformer if conformer in labels else labels[0]
            if cra.atom.altloc not in ('', ' ', '\0', selected):
                break
            atom = next((atom for atom in mapping[position].atoms() if atom.name == cra.atom.name), None)
            if atom is None:
                break
            partners.append(atom)
        if len(partners) == 2 and frozenset(partners) not in bonds:
            fixer.topology.addBond(*partners)
            bonds.add(frozenset(partners))
    fixer.missingResidues = {}
    return fixer, mapping


def _backend_gap_key(gap, mapping):
    pos = gap['insertion_position']
    ci, ri = pos['chain_index'], pos['residue_index']
    if gap['kind'] == 'c_terminal':
        residue = mapping[(ci, ri - 1)]
        return residue.chain.index, list(residue.chain.residues()).index(residue) + 1
    residue = mapping[(ci, ri)]
    return residue.chain.index, list(residue.chain.residues()).index(residue)


def _sequence_bounds(sequence, residues, *, reverse=False):
    """Conservative ambiguity check for Gemmi's mapping, constrained by labels.

    This does not model a loop or choose an alignment.  It verifies that the
    exact ordered residue names have only one possible placement in SEQRES /
    entity_poly_seq.  Author numbering never establishes missing residues.
    """
    positions = [None] * len(residues)
    cursor = len(sequence) - 1 if reverse else 0
    indices = range(len(residues) - 1, -1, -1) if reverse else range(len(residues))
    for index in indices:
        residue = residues[index]
        fixed = residue.label_seq - 1 if residue.label_seq is not None else None
        if fixed is not None:
            if not 0 <= fixed < len(sequence) or sequence[fixed] != residue.name:
                return None
            if (reverse and fixed > cursor) or (not reverse and fixed < cursor):
                return None
            cursor = fixed
        else:
            while 0 <= cursor < len(sequence) and sequence[cursor] != residue.name:
                cursor += -1 if reverse else 1
            if not 0 <= cursor < len(sequence):
                return None
        positions[index] = cursor + 1
        cursor += -1 if reverse else 1
    return positions


def _detect_gaps(structure, residue_keys):
    """Use declared entity sequence and Gemmi's sequence-to-polymer mapping."""
    gaps = {'internal_gaps': [], 'n_terminal_gaps': [], 'c_terminal_gaps': []}
    chain_results = []
    for ci, chain in enumerate(structure[0]):
        for polymer in chain.subchains():
            entity = structure.get_entity_of(polymer)
            if entity is None or not entity.full_sequence:
                # Only polymer spans need sequence evidence.  Nonpolymers are
                # not incomplete chains merely because they lack SEQRES.
                if not any(res.entity_type.name == 'Polymer' for res in polymer):
                    continue
                chain_results.append({'chain': chain.name, 'status': 'unknown', 'reason': 'No declared polymer sequence'})
                continue
            if entity.entity_type.name != 'Polymer':
                continue
            sequence = list(entity.full_sequence)
            observed = list(polymer)
            if not observed:
                continue
            first = _sequence_bounds(sequence, observed)
            last = _sequence_bounds(sequence, observed, reverse=True)
            if first is None or last is None:
                chain_results.append({'chain': chain.name, 'status': 'unknown', 'reason': 'Declared sequence cannot be mapped exactly to observed residue identities'})
                continue
            if first != last:
                chain_results.append({'chain': chain.name, 'status': 'ambiguous', 'reason': 'Repeated sequence admits multiple coordinate placements'})
                continue
            # Gemmi supplies the actual mapping, retaining explicit label_seq
            # positions.  The independent uniqueness check prevents its chosen
            # alignment from being mistaken for unique experimental evidence.
            aligned = structure.clone()
            aligned.assign_label_seq_id()
            indices = [next(ri for ri, res in enumerate(chain) if res == observed_res) for observed_res in observed]
            mapped = [aligned[0][ci][ri].label_seq for ri in indices]
            if mapped != first:
                chain_results.append({'chain': chain.name, 'status': 'unknown', 'reason': 'Gemmi alignment does not uniquely agree with declared sequence evidence'})
                continue
            chain_results.append({'chain': chain.name, 'status': 'completed', 'reason': 'Declared entity sequence mapped to observed residues with Gemmi'})
            boundaries = [0, *first, len(sequence) + 1]
            for index in range(len(boundaries) - 1):
                start, end = boundaries[index] + 1, boundaries[index + 1] - 1
                if start > end:
                    continue
                kind = 'n_terminal' if index == 0 else 'c_terminal' if index == len(observed) else 'internal'
                insertion = indices[index] if index < len(observed) else indices[-1] + 1
                gaps[f'{kind}_gaps'].append({
                    'gap_id': f'gap:{ci}:{insertion}:{start}-{end}',
                    'kind': kind,
                    'chain': chain.name,
                    'residue_names': sequence[start - 1:end],
                    'sequence_range': [start, end],
                    'left_anchor': residue_keys[(ci, indices[index - 1])] if index else None,
                    'right_anchor': residue_keys[(ci, indices[index])] if index < len(observed) else None,
                    'insertion_position': {'chain_index': ci, 'residue_index': insertion},
                    'evidence': ['declared_entity_sequence', 'gemmi_sequence_mapping', 'label_seq_id' if any(res.label_seq is not None for res in observed) else 'unique_sequence_placement'],
                    'status': 'detected',
                })
    unknown = any(item['status'] != 'completed' for item in chain_results)
    if not chain_results:
        # A structure without polymers has no polymer gaps to analyze.
        status = {'status': 'completed', 'reason': 'No polymer sequence gaps applicable', 'chain_results': []}
    else:
        status = {'status': 'unknown' if unknown else 'completed', 'reason': 'Some polymer sequence mappings are unknown or ambiguous' if unknown else 'Declared polymer sequence mapping completed', 'chain_results': chain_results}
    return gaps, status


def inspect_missing(structure, residue_keys):
    """Inspect missing polymer residues and compatible-conformer heavy atoms."""
    versions = _versions()
    gaps, sequence_status = _detect_gaps(structure, residue_keys)
    result = {**gaps, 'missing_atoms': [], 'analysis_status': {'missing_residues': sequence_status}, 'warnings': [], 'backend_versions': versions}
    if sequence_status['status'] == 'unknown':
        result['warnings'].append('Missing-residue completeness requires a declared construct sequence; missing/unobserved annotations alone do not establish full chain sequence')
    try:
        import openmm  # noqa: F401
        import pdbfixer  # noqa: F401
    except ImportError as exc:
        result['analysis_status']['missing_atoms'] = {'status': 'unavailable', 'reason': str(exc)}
        return result
    try:
        labels = sorted({label for chain in structure[0] for residue in chain for label in _altlocs(residue) if label}) or ['']
        for label_index, label in enumerate(labels):
            fixer, mapping = _make_fixer(structure, label)
            for gap in [*gaps['internal_gaps'], *gaps['n_terminal_gaps'], *gaps['c_terminal_gaps']]:
                fixer.missingResidues[_backend_gap_key(gap, mapping)] = gap['residue_names']
            fixer.findMissingAtoms()
            for (ci, ri), backend in mapping.items():
                residue = structure[0][ci][ri]
                altlocs = _altlocs(residue)
                if label not in altlocs and not (altlocs == [''] and label_index == 0):
                    continue
                if not _is_template_target(residue):
                    continue
                record = {'residue_key': residue_keys[(ci, ri)], 'residue_name': residue.name, 'altloc': label if label in altlocs else '', 'mainchain': [], 'sidechain': [], 'terminal': []}
                if residue.name not in fixer.templates:
                    result['missing_atoms'].append({**record, 'status': 'unsupported', 'reason': 'No PDBFixer heavy-atom template; residue was not replaced'})
                    continue
                missing = [atom.name for atom in fixer.missingAtoms.get(backend, [])]
                terminals = list(fixer.missingTerminals.get(backend, []))
                if missing or terminals:
                    record.update(status='missing', mainchain=[name for name in missing if name in _MAINCHAIN], sidechain=[name for name in missing if name not in _MAINCHAIN and name != 'OXT'], terminal=[name for name in missing if name == 'OXT'] + terminals)
                    result['missing_atoms'].append(record)
        unsupported = any(item['status'] == 'unsupported' for item in result['missing_atoms'])
        result['analysis_status']['missing_atoms'] = {'status': 'unsupported' if unsupported else 'completed', 'reason': 'Some residues lack PDBFixer templates' if unsupported else 'PDBFixer heavy-atom templates checked per compatible conformer'}
    except Exception as exc:
        result['analysis_status']['missing_atoms'] = {'status': 'failed', 'reason': f'{type(exc).__name__}: {exc}'}
    return result


def repair_structure(structure, residue_keys, options, selected_gaps):
    """Run only the requested PDBFixer operations and merge actual changes."""
    import gemmi
    from openmm.app import Modeller, PDBxFile

    warnings = []
    changes = []
    unresolved = []
    fixer, mapping = _make_fixer(structure)
    if any(len(_altlocs(residue)) > 1 for chain in structure[0] for residue in chain):
        raise ValueError('Repair requires one compatible selected conformer per residue')
    if options.get('replace_nonstandard_residues', False):
        fixer.findNonstandardResidues()
        allowed = {backend for (ci, ri), backend in mapping.items() if structure[0][ci][ri].entity_type == gemmi.EntityType.Polymer}
        fixer.nonstandardResidues = [(res, name) for res, name in fixer.nonstandardResidues if res in allowed]
        for residue, replacement in fixer.nonstandardResidues:
            ci, ri = next(key for key, value in mapping.items() if value == residue)
            changes.append({'action': 'replace_residue', 'residue_key': residue_keys[(ci, ri)], 'from': residue.name, 'to': replacement})
        fixer.replaceNonstandardResidues()
        mapping = {(ci, ri): residue for (ci, ri), residue in zip(mapping, fixer.topology.residues(), strict=True)}
    fixer.missingResidues = {}
    gap_map = {}
    for gap in selected_gaps:
        if gap.get('status') != 'detected' or not gap.get('residue_names'):
            raise ValueError(f"Gap {gap.get('gap_id')} has no unambiguous sequence/insertion evidence")
        pos = gap['insertion_position']
        ci, ri = pos['chain_index'], pos['residue_index']
        if not 0 <= ci < len(structure[0]) or not 0 <= ri <= len(structure[0][ci]):
            raise ValueError(f"Gap {gap['gap_id']} insertion position is outside the selected structure")
        unsupported_names = [name for name in gap['residue_names'] if name not in fixer.templates]
        if unsupported_names:
            raise ValueError(f"No PDBFixer template for modeled gap residues: {unsupported_names}")
        backend_key = _backend_gap_key(gap, mapping)
        if (ci, ri) in gap_map or backend_key in fixer.missingResidues:
            raise ValueError(f'Multiple selected gaps share an insertion position: {ci}:{ri}')
        fixer.missingResidues[backend_key] = list(gap['residue_names'])
        gap_map[(ci, ri)] = gap
    fixer.findMissingAtoms()
    add_atoms = options.get('add_missing_atoms', False)
    if not add_atoms:
        fixer.missingAtoms = {}
        fixer.missingTerminals = {}
    else:
        for (ci, ri), backend in mapping.items():
            residue = structure[0][ci][ri]
            if _is_template_target(residue) and backend.name not in fixer.templates:
                if residue.entity_type == gemmi.EntityType.Polymer:
                    raise ValueError(f'No PDBFixer heavy-atom template for polymer residue {residue_keys[(ci, ri)]} ({residue.name}); requested repair cannot be completed')
                warnings.append(f'No PDBFixer heavy-atom template for nonpolymer {residue.name} ({residue_keys[(ci, ri)]}); original residue retained')
    if fixer.missingResidues or fixer.missingAtoms or fixer.missingTerminals:
        fixer.addMissingAtoms(seed=1)
    if options.get('add_hydrogens', False):
        # PDBFixer normally ignores absent CCD definitions.  Check its own
        # generated variants before adding H so an unavailable requested step
        # cannot be reported as complete.  The second library call uses its CCD
        # cache; it does not repeat successful/failed external lookups.
        definitions = fixer._downloadNonstandardDefinitions()
        for residue in fixer.topology.residues():
            atoms = list(residue.atoms())
            if len(atoms) == 1 and atoms[0].element is not None and gemmi.Element(atoms[0].element.symbol).is_metal:
                continue
            if residue.name not in Modeller._residueHydrogens and fixer._describeVariant(residue, definitions) is None:
                raise ValueError(f'Unsupported PDBFixer/OpenMM hydrogen definition for residue {residue.name} (backend chain {residue.chain.index}, residue {residue.id}); no matching standard or CCD definition')
        if definitions:
            warnings.append(f'PDBFixer used RCSB CCD hydrogen definitions for: {", ".join(sorted(definitions))}')
        fixer.addMissingHydrogens(pH=options.get('ph', 7.0))
        warnings.append('Hydrogens use PDBFixer/OpenMM default protonation rules, not a full-system pKa or metal protonation optimization')
    stream = StringIO()
    PDBxFile.writeFile(fixer.topology, fixer.positions, stream, keepIds=True)
    modeled = gemmi.make_structure_from_block(gemmi.cif.read_string(stream.getvalue()).sole_block())
    # OpenMM may split label subchains on export, so residue order (not its
    # generated chain identifiers) is used with the explicit insertion plan.
    backend_residues = [residue for chain in modeled[0] for residue in chain]
    output = structure.clone()
    for ci in range(len(output[0]) - 1, -1, -1):
        del output[0][ci]
    cursor = 0
    output_positions = {}
    for ci, chain in enumerate(structure[0]):
        new_chain = gemmi.Chain(chain.name)
        next_number = max((res.seqid.num for res in chain), default=0) + 1
        for ri in range(len(chain) + 1):
            if (ci, ri) in gap_map:
                gap = gap_map[(ci, ri)]
                for offset, name in enumerate(gap['residue_names']):
                    new_residue = backend_residues[cursor].clone()
                    cursor += 1
                    if new_residue.name != name:
                        raise ValueError(f'PDBFixer changed requested modeled residue {name} into {new_residue.name}')
                    new_residue.seqid = gemmi.SeqId(next_number, ' ')
                    next_number += 1
                    anchor = chain[min(ri, len(chain) - 1)]
                    new_residue.subchain = anchor.subchain
                    new_residue.entity_id = anchor.entity_id
                    new_residue.entity_type = gemmi.EntityType.Polymer
                    new_residue.label_seq = gap['sequence_range'][0] + offset
                    for atom in new_residue:
                        atom.occ = 1.0
                    new_chain.add_residue(new_residue)
                    changes.append({'action': 'add_residue', 'gap_id': gap['gap_id'], 'status': 'modeled', 'residue_name': name, 'chain': chain.name, 'author_residue_number': new_residue.seqid.num, 'label_seq_id': new_residue.label_seq, 'left_anchor': gap['left_anchor'], 'right_anchor': gap['right_anchor'], 'atom_names': [atom.name for atom in new_residue]})
            if ri == len(chain):
                continue
            backend_residue = backend_residues[cursor]
            cursor += 1
            original = chain[ri]
            merged = original.clone()
            merged.name = backend_residue.name
            backend_atoms = {atom.name: atom for atom in backend_residue}
            original_names = {atom.name for atom in original}
            for ai in range(len(merged) - 1, -1, -1):
                if merged[ai].name not in backend_atoms:
                    changes.append({'action': 'remove_atom', 'residue_key': residue_keys[(ci, ri)], 'atom_name': merged[ai].name})
                    del merged[ai]
            for atom in backend_residue:
                if atom.name not in original_names:
                    merged.add_atom(atom.clone())
                    changes.append({'action': 'add_atom', 'residue_key': residue_keys[(ci, ri)], 'residue_name': merged.name, 'atom_name': atom.name})
            new_chain.add_residue(merged)
            output_positions[(ci, ri)] = len(new_chain) - 1
        output[0].add_chain(new_chain)
    if cursor != len(backend_residues):
        raise ValueError('PDBFixer output residue count disagrees with the selected insertion plan')
    for connection in output.connections:
        for address in (connection.partner1, connection.partner2):
            original_cra = structure[0].find_cra(address, ignore_segment=True)
            if original_cra.residue is not None:
                position = next(((ci, ri) for ci, chain in enumerate(structure[0]) for ri, residue in enumerate(chain) if residue == original_cra.residue), None)
                if position is not None:
                    ci, ri = position
                    address.res_id.name = output[0][ci][output_positions[position]].name
    from cloudra.tools.core.pdb_structure import prune_connections
    connection_changes = prune_connections(output)
    changes.extend(connection_changes)
    if connection_changes:
        warnings.append('Input connection records referencing atoms absent after repair were removed and logged')
    if selected_gaps:
        warnings.append('Added residues are modeled conformations; loops, termini and metal-site neighborhoods remain uncertain')
    return output, changes, unresolved, warnings, _versions()
