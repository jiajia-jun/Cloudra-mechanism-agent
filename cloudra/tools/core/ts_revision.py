"""TS revisions retain a proved canonical atom order in current source files."""
import hashlib
from copy import deepcopy
from pathlib import Path

from cloudra.services.ts_pipeline_store import TsEvidenceReference, TsRevisionReceipt, revision_request_digest
from cloudra.tools.core.ts_inputs import TsResumeRequest, apply_input_changes

_FORMAL = ('ts_opt', 'frequency', 'irc', 'reactant_opt', 'reactant_frequency', 'product_opt', 'product_frequency')
_DEPENDENTS = {
    'ts_opt': set(_FORMAL), 'frequency': set(_FORMAL[1:]), 'irc': set(_FORMAL[2:]),
    'reactant_opt': {'reactant_opt', 'reactant_frequency'}, 'reactant_frequency': {'reactant_frequency'},
    'product_opt': {'product_opt', 'product_frequency'}, 'product_frequency': {'product_frequency'},
    'guess': {'path', 'scan', *_FORMAL},
    'build': {'candidate_opt', 'candidate_evaluation', 'product_seed_opt', 'path', 'scan', *_FORMAL},
}


def _differences(before, after, prefix=''):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for field in sorted(before.keys() | after.keys()):
            path = f'{prefix}.{field}' if prefix else field
            result.extend(_differences(before.get(field), after.get(field), path))
        return result
    return [prefix] if before != after else []


def _failed_step(record):
    steps = ([record.scan_step] if record.scan_step else []) + list(record.job_steps)
    if record.failed_attempt:
        matched = next((step for step in steps if f'{step.source_input_revision}:{step.purpose}:{step.job_id}' == record.failed_attempt['attempt_id']), None)
        if matched is not None:
            return matched
    return next((step for step in reversed(steps) if step.state in ('failed', 'cancelled', 'missing')), None)


def _input_revision_differences(record, updated):
    differences = _differences(record.input.model_dump(mode='json'), updated.model_dump(mode='json'))
    for role in ('reactant', 'product'):
        if _file_source_drift(record, role) or _missing_source_arrived(record, role):
            differences.append(f'conformers.{role}.xyz_path')
    return sorted(set(differences))


def _validated_scan_recovery(record, request, failed, updated, differences):
    """Bind declared recovery artifacts, without choosing a scientific correction."""
    from cloudra.tools.core.ts_inputs import ScanRepairReceipt
    from cloudra.tools.core.ts_process import _artifact_sha256, _refinement_log_path, _workspace_input_path

    if failed is None or failed.purpose != 'scan':
        if request.scan_recovery is not None:
            raise ValueError('scan recovery does not refer to a current failed scan')
        return None
    recovery = request.scan_recovery
    if recovery is None:
        raise ValueError('failed scan requires independently bound recovery evidence; reason or point-count changes alone cannot retry it')
    attempt_id = f'{failed.source_input_revision}:scan:{failed.job_id}'
    if recovery.failed_attempt_id != attempt_id:
        raise ValueError('scan recovery failed_attempt_id does not match the current failure')
    failure = dict(record.failed_attempt or dict(attempt_id=attempt_id, purpose='scan',
        job_id=failed.job_id, input_revision=failed.source_input_revision,
        failure_class=record.blocked.failure_class if record.blocked else 'unclassified_failure',
        diagnostics=record.blocked.atom_details if record.blocked else []))
    paths = dict(input=Path(failed.input_path).resolve(), log=Path(_refinement_log_path(record, failed)).resolve())
    failure_hashes = {}
    for name, path in paths.items():
        actual = _artifact_sha256(path)
        if name + '_sha256' in failure and failure[name + '_sha256'] != actual:
            raise ValueError(f'scan recovery cannot replace the original failed {name} artifact')
        declared = getattr(recovery, 'failure_' + name + '_sha256')
        if declared != actual:
            raise ValueError(f'scan recovery failed {name} fingerprint is stale or mismatched')
        failure_hashes[str(path)] = actual
        failure[name + '_sha256'] = actual
        failure[name + '_path'] = str(path)
    artifacts = []
    for ref in recovery.evidence_refs:
        path = _workspace_input_path(record, ref.path)
        if path in paths.values() or ref.sha256 in failure_hashes.values():
            raise ValueError('scan recovery must cite repair evidence rather than repeating failed input/log artifacts')
        if _artifact_sha256(path) != ref.sha256:
            raise ValueError('scan recovery artifact is missing or its fingerprint changed')
        if any(item['path'] == str(path) for item in artifacts):
            raise ValueError('scan recovery contains duplicate artifact references')
        source_role = None
        for role in ('reactant', 'product'):
            source = getattr(updated.conformers, role)
            previous = getattr(record.input.conformers, role)
            if not source or source.kind != 'file':
                continue
            for name in ('xyz', 'mol'):
                source_path = getattr(source, name + '_path')
                if source_path is None or _workspace_input_path(record, source_path) != path:
                    continue
                if role in record.structures:
                    before = Path(record.run_dir) / 'build' / f"input_{record.structures[role]['input_revision']:04d}" / role / f'seed.{name}'
                elif previous and previous.kind == 'file' and getattr(previous, name + '_path'):
                    before = _workspace_input_path(record, getattr(previous, name + '_path'))
                else:
                    before = Path(record.current_seed_xyz_path if role == 'reactant' else record.product_seed_xyz_path) if name == 'xyz' else Path(record.current_seed_mol_path if role == 'reactant' else record.product_seed_mol_path)
                before_digest = _artifact_sha256(before)
                if before_digest is not None and before_digest != ref.sha256:
                    source_role = role
        artifact = dict(path=str(path), sha256=ref.sha256)
        if source_role:
            artifact.update(kind='changed_conformer_file', role=source_role)
        else:
            try:
                repair = ScanRepairReceipt.model_validate_json(path.read_bytes())
            except ValueError as exc:
                raise ValueError('scan recovery artifact has no changed input or scoped repair receipt binding') from exc
            if (repair.failed_attempt_id != attempt_id
                    or repair.failure_input_sha256 != failure['input_sha256']):
                raise ValueError('scan recovery repair receipt binding differs from the failed attempt/input')
            artifact.update(kind='repair_receipt', receipt=repair.model_dump(mode='json'))
        artifacts.append(artifact)

    def at(value, field):
        for part in field.split('.'):
            value = value.get(part) if isinstance(value, dict) else None
        return value

    before, after = record.input.model_dump(mode='json'), updated.model_dump(mode='json')
    return dict(failed_attempt=failure, reason=request.reason,
        input_diff=[dict(field=field, before=at(before, field), after=at(after, field)) for field in differences],
        evidence_refs=artifacts, source_hashes=_revision_source_hashes(record, updated),
        verification='artifact_integrity_and_failure_binding',
        scientific_recovery_verified=False)


def _source_identity(record, source):
    if source is None:
        return None
    fields = {'file': ('xyz_path', 'mol_path'), 'catalog': ('catalog_id', 'candidate_id', 'partition_revision'),
              'generate': ('generation', 'seed'), 'rotate_about_bond': ()}[source.kind]
    values = [getattr(source, field) for field in fields]
    if source.kind == 'file':
        from cloudra.tools.core.ts_process import _workspace_input_path
        values = [str(_workspace_input_path(record, value)) if value else None for value in values]
    return (source.kind, *values)


def _file_source_drift(record, role):
    from cloudra.tools.core.ts_process import _workspace_input_path

    source = getattr(record.input.conformers, role)
    if source is None or source.kind != 'file' or role not in record.structures:
        return False
    source_revision = record.structures[role]['input_revision']
    snapshot = Path(record.run_dir) / 'build' / f'input_{source_revision:04d}' / role
    for name, source_path in (('seed.xyz', source.xyz_path), ('seed.mol', source.mol_path)):
        if source_path is None:
            continue
        old = snapshot / name
        current = _workspace_input_path(record, source_path)
        if not old.is_file() or not current.is_file():
            return True
        if hashlib.sha256(old.read_bytes()).digest() != hashlib.sha256(current.read_bytes()).digest():
            return True
    return False


def _missing_source_arrived(record, role):
    if role in record.structures or record.blocked is None:
        return False
    return any(issue.get('code') == 'source_missing' and issue.get('role') == role
               and Path(issue.get('path', '')).is_file() for issue in record.blocked.issues)


def _revision_source_hashes(record, value):
    from cloudra.tools.core.ts_process import _workspace_input_path

    hashes = {}
    for role in ('reactant', 'product'):
        source = getattr(value.conformers, role)
        if source is None or source.kind != 'file':
            continue
        role_hashes = {}
        for name, source_path in (('xyz', source.xyz_path), ('mol', source.mol_path)):
            if source_path is not None:
                path = _workspace_input_path(record, source_path)
                if path.is_file():
                    role_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if role_hashes:
            hashes[role] = role_hashes
    return hashes


def _canonical_file_projection(record, updated, role, permutation):
    """Capture a current mutable FILE and project its bytes into old atom order."""
    from rdkit import Chem

    from cloudra.tools.Chemtool.reaction_mapping import _read_structure, concrete_structure_digest
    from cloudra.tools.core.ts_process import _workspace_input_path

    source = getattr(updated.conformers, role)
    if source is None or source.kind != 'file' or not permutation:
        return None
    paths = {name: str(_workspace_input_path(record, path))
             for name, path in (('xyz', source.xyz_path), ('mol', source.mol_path)) if path}
    before = {name: Path(path).read_bytes() for name, path in paths.items()}
    rows = before['xyz'].decode('utf-8').splitlines(keepends=True)
    count = int(rows[0].strip())
    if count != len(permutation) or len(rows) < count + 2:
        raise ValueError(f'{role}: canonical atom permutation does not cover the XYZ rows')
    canonical_rows = [rows[index + 2] for index in permutation]
    after = {'xyz': ''.join([*rows[:2], *canonical_rows, *rows[count + 2:]]).encode('utf-8')}
    graph = _read_structure(None, before.get('mol', before['xyz']).decode('utf-8'),
                            'mol' if 'mol' in before else 'xyz', updated.reaction.charge, role)
    graph = Chem.RenumberAtoms(graph, permutation)
    positions = [[float(token) for token in row.split()[1:4]] for row in canonical_rows]
    conf = Chem.Conformer(count)
    for index, point in enumerate(positions):
        conf.SetAtomPosition(index, point)
    graph.RemoveAllConformers()
    graph.AddConformer(conf)
    if 'mol' in before:
        after['mol'] = Chem.MolToMolBlock(graph).encode('utf-8')
        roundtrip = _read_structure(None, after['mol'].decode('utf-8'), 'mol', updated.reaction.charge, role)
        if _graph_atom_permutation(graph, roundtrip, same_rows=True) != list(range(count)):
            raise ValueError(f'{role}: canonical MOL roundtrip changes molecular identity or stereo; XYZ and MOL must agree')
    inverse = [0] * count
    for old_index, raw_index in enumerate(permutation):
        inverse[raw_index] = old_index
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in after.items()}
    digest = concrete_structure_digest(role, getattr(updated.reaction, role + '_smiles'),
        updated.reaction.charge, updated.reaction.multiplicity, graph,
        electronic_character=updated.reaction.electronic_character)
    normalization = dict(status='pending', input_revision=record.declaration_revision + 1, paths=paths,
        source_to_canonical=[index + 1 for index in inverse],
        canonical_to_source=[index + 1 for index in permutation], canonical_hashes=hashes)
    table = deepcopy(record.structures[role])
    for key in ('table_path', 'heavy_atom_indices'):
        table.pop(key, None)
    table.update(source_kind='file', input_revision=record.declaration_revision + 1,
        xyz_path=paths['xyz'], mol_path=paths.get('mol'), xyz_sha256=hashes['xyz'],
        mol_sha256=hashes.get('mol'), structure_digest=digest, binding_status='unverified',
        normalization=normalization)
    return dict(paths=paths, before=before, after=after, graph=graph, inverse=inverse, table=table)


def _source_atom_permutation(record, updated, role):
    """Old -> new full-atom indices; [] means unchanged, None means unproved."""
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_process import _workspace_input_path

    before, after = getattr(record.input.conformers, role), getattr(updated.conformers, role)
    if (_source_identity(record, before) == _source_identity(record, after)
            and not _file_source_drift(record, role) and not _missing_source_arrived(record, role)):
        return []
    if before is None or after is None or after.kind != 'file' or role not in record.structures:
        return None
    table = record.structures[role]
    snapshot = Path(record.run_dir) / 'build' / f"input_{table['input_revision']:04d}" / role
    old_xyz = snapshot / 'seed.xyz' if before.kind == 'file' else Path(table['xyz_path'])
    old_mol = (snapshot / 'seed.mol' if before.mol_path else None) if before.kind == 'file' else (
        Path(table['mol_path']) if table.get('mol_path') else None)
    new_xyz = _workspace_input_path(record, after.xyz_path)
    try:
        if before.kind != 'file':
            if table.get('source_kind') != before.kind:
                return None
            for path, digest in ((old_xyz, table.get('xyz_sha256')), (old_mol, table.get('mol_sha256'))):
                if path is not None and (not digest or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
                    return None
        old_atoms, new_atoms = read_xyz_atoms(str(old_xyz)), read_xyz_atoms(str(new_xyz))
        # Builder origin tags are atom identity assertions, not free comments.
        # A changed/removed assertion must not be hidden by coordinate equality.
        annotations = [
            [tuple(token for token in row.split()[4:] if token.startswith('in:'))
             for row in path.read_text().splitlines()[2:2 + len(atoms)]]
            for path, atoms in ((old_xyz, old_atoms), (new_xyz, new_atoms))
        ]
        # Exact coordinates certify the same concrete rows, even for symmetric
        # atoms. Element sequence alone never establishes this correspondence.
        same_rows = old_atoms == new_atoms
        new_mol = _workspace_input_path(record, after.mol_path) if after.mol_path else None
        if old_mol is None and new_mol is None and same_rows:
            return list(range(len(old_atoms))) if annotations[0] == annotations[1] else None
        from cloudra.tools.Chemtool.reaction_mapping import _read_structure
        old = _read_structure(str(old_mol or old_xyz), None, 'mol' if old_mol else 'xyz', record.input.reaction.charge, role)
        new = _read_structure(str(new_mol or new_xyz), None, 'mol' if new_mol else 'xyz', updated.reaction.charge, role)
        if ([atom.GetSymbol() for atom in old.GetAtoms()] != [symbol for symbol, _ in old_atoms]
                or [atom.GetSymbol() for atom in new.GetAtoms()] != [symbol for symbol, _ in new_atoms]):
            return None
        permutation = _graph_atom_permutation(old, new, same_rows=same_rows)
        if permutation is not None and any(annotations[0][old_index] != annotations[1][new_index]
                                           for old_index, new_index in enumerate(permutation)):
            return None
        return permutation
    except (ValueError, OSError):
        return None


def _graph_atom_permutation(old, new, *, same_rows):
    """Require an exact, unique full molecular graph correspondence."""
    from rdkit import Chem

    from cloudra.tools.Chemtool.reaction_mapping import _mapped_label_permutation

    if old.GetNumAtoms() != new.GetNumAtoms() or old.GetNumBonds() != new.GetNumBonds():
        return None
    if not same_rows:
        # If supplied, labels are authoritative and must cover all atoms,
        # including hydrogens. Conflicting/partial labels cannot be guessed.
        _mapped_label_permutation(old, new)
    atom_property, bond_property = '_cloudra_revision_atom', '_cloudra_revision_bond'
    for mol in (old, new):
        for atom in mol.GetAtoms():
            atom.SetProp(atom_property, repr((atom.GetAtomicNum(), atom.GetIsotope(),
                atom.GetFormalCharge(), atom.GetNumRadicalElectrons(), atom.GetIsAromatic(),
                atom.GetAtomMapNum(), atom.GetIdx() if same_rows else None)))
        for bond in mol.GetBonds():
            bond.SetProp(bond_property, repr((str(bond.GetBondType()), bond.GetIsAromatic(), bond.GetIsConjugated())))
    parameters = Chem.SubstructMatchParameters()
    parameters.uniquify, parameters.useChirality, parameters.maxMatches = False, True, 2
    parameters.atomProperties, parameters.bondProperties = [atom_property], [bond_property]
    # Canonical stereo identity also rejects newly specified/lost stereo that a
    # one-directional substructure query with unspecified stereo could accept.
    if Chem.MolToSmiles(old) != Chem.MolToSmiles(new):
        return None
    matches = old.GetSubstructMatches(new, parameters)
    if len(matches) != 1:
        return None
    old_to_new = [0] * old.GetNumAtoms()
    for new_index, old_index in enumerate(matches[0]):
        old_to_new[old_index] = new_index
    return old_to_new


def _atom_correspondences(record, updated):
    result = {role: _source_atom_permutation(record, updated, role) for role in ('reactant', 'product')}
    if (record.input.conformers.product and updated.conformers.product
            and record.input.conformers.product.kind == updated.conformers.product.kind == 'rotate_about_bond'):
        result['product'] = result['reactant']
    return result


def _refresh_canonical_bindings(record, updated, changes, projections):
    """Validate bindings in their declared order, then bind canonical geometry."""
    from rdkit import Chem

    from cloudra.tools.Chemtool.reaction_mapping import (
        _identity_and_binding,
        _read_structure,
        concrete_structure_digest,
    )
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    for role in ('reactant', 'product'):
        projection = projections.get(role)
        before, after = getattr(record.input.conformers, role), getattr(updated.conformers, role)
        if before is None or after is None or after.kind != 'file' or after.heavy_atom_binding is None:
            continue
        if projection is None and (before.kind != 'file' or role not in record.structures):
            continue
        explicit_source = getattr(changes.conformers, role) if changes.conformers else None
        explicit = explicit_source and 'heavy_atom_binding' in explicit_source.model_fields_set
        if explicit:
            if projection is None:
                continue
            raw = projection['before']
            graph = _read_structure(None, raw.get('mol', raw['xyz']).decode('utf-8'),
                'mol' if 'mol' in raw else 'xyz', updated.reaction.charge, role)
            positions = [[float(v) for v in row.split()[1:4]]
                         for row in raw['xyz'].decode('utf-8').splitlines()[2:2 + graph.GetNumAtoms()]]
            value, binding = updated, after.heavy_atom_binding
        else:
            if before.kind != 'file' or before.heavy_atom_binding is None:
                continue
            table = record.structures[role]
            snapshot = Path(record.run_dir) / 'build' / f"input_{table['input_revision']:04d}" / role
            xyz = snapshot / 'seed.xyz'
            mol = snapshot / 'seed.mol' if before.mol_path else None
            graph = _read_structure(str(mol or xyz), None, 'mol' if mol else 'xyz',
                                    record.input.reaction.charge, role)
            positions = [position for _, position in read_xyz_atoms(str(xyz))]
            value, binding = record.input, before.heavy_atom_binding
        conf = Chem.Conformer(len(positions))
        for index, point in enumerate(positions):
            conf.SetAtomPosition(index, point)
        graph.RemoveAllConformers()
        graph.AddConformer(conf)
        actual = concrete_structure_digest(role, getattr(value.reaction, role + '_smiles'),
            value.reaction.charge, value.reaction.multiplicity, graph,
            electronic_character=value.reaction.electronic_character)
        qualifier = 'explicit' if explicit else 'inherited'
        if binding.structure_digest != actual:
            raise ValueError(f'{role}: {qualifier} heavy-atom binding structure digest is stale')
        if any(index < 1 or index > graph.GetNumAtoms() for index in binding.indices):
            raise ValueError(f'{role}: {qualifier} heavy-atom binding indices are outside the full atom table')
        identity, matched, diagnostic = _identity_and_binding(getattr(value.reaction, role + '_smiles'),
            graph, [index - 1 for index in binding.indices])
        if identity != 'match' or not matched:
            raise ValueError(f'{role}: {qualifier} heavy-atom binding is invalid: {diagnostic}')
        after.heavy_atom_binding.indices = ([projection['inverse'][index - 1] + 1 for index in binding.indices]
                                            if explicit else list(binding.indices))
        after.heavy_atom_binding.structure_digest = (projection['table']['structure_digest'] if projection else
            concrete_structure_digest(role, getattr(updated.reaction, role + '_smiles'),
                updated.reaction.charge, updated.reaction.multiplicity, graph,
                electronic_character=updated.reaction.electronic_character))


def _stale_atom_references(record, updated, changes, correspondences):
    species_changed = any(
        getattr(record.input.reaction, field) != getattr(updated.reaction, field)
        for field in ('reactant_smiles', 'product_smiles')
    )
    unknown = {role for role, permutation in correspondences.items() if permutation is None}
    if species_changed:
        unknown = {'reactant', 'product'}
    if not unknown and not any(correspondences.values()):
        return []
    reaction_fields = changes.reaction.model_fields_set if changes.reaction is not None else set()
    conformers = changes.conformers
    guidance = conformers.guidance if conformers is not None else None
    guidance_fields = guidance.model_fields_set if guidance is not None else set()
    stale = []
    if unknown and record.input.reaction.atom_map and 'atom_map' not in reaction_fields:
        stale.append('reaction.atom_map')
    if 'reactant' in unknown and record.input.reaction.reaction_center and 'reaction_center' not in reaction_fields:
        stale.append('reaction.reaction_center')
    existing_guidance = record.input.conformers.guidance
    if 'reactant' in unknown and existing_guidance.ring_order and 'ring_order' not in guidance_fields:
        stale.append('conformers.guidance.ring_order')
    if 'reactant' in unknown and existing_guidance.distance_filters and 'distance_filters' not in guidance_fields:
        stale.append('conformers.guidance.distance_filters')
    product = record.input.conformers.product
    if ('reactant' in unknown and product and product.kind == 'rotate_about_bond'
            and not (conformers and 'product' in conformers.model_fields_set)):
        stale.append('conformers.product')
    guess = record.input.guess
    if guess is not None and 'guess' not in changes.model_fields_set:
        if species_changed or (guess.kind == 'scan' and 'reactant' in unknown):
            stale.append('guess')
        elif guess.kind == 'provided' and ('reactant' in unknown or any(
                old != new for old, new in enumerate(correspondences['reactant']))):
            stale.append('guess')
    return stale


def plan_input_revision(record, request: TsResumeRequest) -> TsRevisionReceipt:
    """Return affected job references; do not mutate record, files or ledger."""
    steps = list(record.job_steps) + ([record.scan_step] if record.scan_step else [])
    if record.waiting_for or any(step.state in ('ready', 'running', 'cancel_requested') for step in steps):
        raise ValueError('active compute jobs prevent input revisions; use ts_inspect')
    updated = _apply_revision_input(record, request.changes)
    differences = _input_revision_differences(record, updated)
    failed = _failed_step(record)
    recovery = _validated_scan_recovery(record, request, failed, updated, differences)
    if not differences and failed is None:
        raise ValueError('no input change or failed attempt to retry; use ts_inspect')
    before_limits, after_limits = record.input.execution.limits, updated.execution.limits
    if after_limits and after_limits.max_interventions is not None and record.intervention_count + 1 > after_limits.max_interventions:
        raise ValueError('intervention limit exhausted')
    if before_limits:
        if after_limits is None or before_limits.source != after_limits.source:
            raise ValueError('authorized limits cannot be removed or change source')
        for field in ('max_compute_actions', 'max_model_calls', 'max_interventions'):
            before, after = getattr(before_limits, field), getattr(after_limits, field)
            if before is not None and (after is None or after > before):
                raise ValueError('input revision cannot raise authorized limits')
    invalidated = set()
    for path in differences:
        if path.startswith(('reaction.reactant_smiles', 'reaction.product_smiles', 'reaction.charge', 'reaction.multiplicity', 'reaction.electronic_character', 'reaction.reaction_center', 'conformers.')):
            invalidated.update(_DEPENDENTS['build'])
        elif path.startswith(('reaction.atom_map', 'guess')):
            invalidated.update(_DEPENDENTS['guess'])
        elif path.startswith('ts_optimization'):
            invalidated.update(_DEPENDENTS['ts_opt'])
        elif path.startswith('verification.'):
            field = path.split('.')[1]
            if field.endswith('_endpoint'):
                side = field.removesuffix('_endpoint')
                task = path.split('.')[2]
                purpose = side + ('_frequency' if task == 'frequency' else '_opt')
            else:
                purpose = 'irc' if field == 'irc_log' else field
            invalidated.update(_DEPENDENTS[purpose])
    if failed is not None:
        invalidated.update(_DEPENDENTS.get(failed.purpose, {failed.purpose}))
    retained, invalid = [], []
    for step in steps:
        if step.job_id is None and not step.external_source:
            continue
        ref = TsEvidenceReference(declaration_revision=step.source_input_revision,
                                  stage_key=step.stage_key or step.purpose, attempt=1, job_id=step.job_id)
        (invalid if step.purpose in invalidated else retained).append(ref)
    released = [key for purpose, key in record.budget_action_keys.items() if purpose in invalidated or (purpose.startswith('candidate_constraints:') and 'candidate_evaluation' in invalidated)]
    return TsRevisionReceipt(request_key=request.request_key, request_digest=revision_request_digest(request), reason=request.reason,
        previous_revision=request.expected_revision, revision=request.expected_revision + 1,
        previous_input_revision=record.declaration_revision, input_revision=record.declaration_revision + 1,
        changes=differences, retained=retained, invalidated=invalid,
        source_hashes=_revision_source_hashes(record, apply_input_changes(record.input, request.changes)),
        recovery_evidence=recovery, released_action_keys=released)


def revise_record(record, request, receipt):
    """Construct a new checkpoint on a deep copy; no writes or submissions."""
    from cloudra.tools.core.ts_process import STAGE_ORDER, TsAttemptHistory
    revised = record.model_copy(deep=True)
    revised.attempt_history.append(TsAttemptHistory(declaration_revision=record.declaration_revision,
        selected_candidate_id=record.selected_candidate_id, job_steps=[*record.job_steps, *([record.scan_step] if record.scan_step else [])], stage_records=record.stage_records,
        input=record.input, terminal=record.terminal, blocked=record.blocked, failed_attempt=record.failed_attempt,
        recovery_evidence=receipt.recovery_evidence, reason=request.reason))
    source_hashes = _revision_source_hashes(record, apply_input_changes(record.input, request.changes))
    if plan_input_revision(record, request) != receipt:
        raise ValueError('revision plan changed since input inspection; use ts_inspect and retry')
    revised.input, projections = _project_revision_input(record, request.changes)
    if source_hashes != _revision_source_hashes(record, revised.input):
        raise ValueError('source changed during input revision; use ts_inspect and redeclare the source')
    revised.declaration_revision = receipt.input_revision
    revised.revision = receipt.revision
    invalid_refs = {(ref.stage_key, ref.job_id) for ref in receipt.invalidated}
    invalid = {step.purpose for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]
        if (step.stage_key or step.purpose, step.job_id) in invalid_refs}
    restart = []
    for path in receipt.changes:
        if path.startswith(('reaction.reactant_smiles', 'reaction.product_smiles', 'reaction.charge', 'reaction.multiplicity', 'reaction.electronic_character')):
            restart.append('declare')
        elif path.startswith('conformers.'):
            restart.append('build')
        elif path.startswith('reaction.atom_map'):
            restart.append('map')
        elif path.startswith('reaction.reaction_center'):
            restart.append('build')
        elif path.startswith('guess'):
            restart.append('guess')
        elif path.startswith('ts_optimization'):
            restart.append('submit')
        elif path.startswith('verification.'):
            restart.append('refine')
    failed = _failed_step(record)
    if failed is not None:
        if failed.purpose in ('scan', 'path'):
            restart.append('guess')
        elif failed.purpose in ('candidate_opt', 'candidate_evaluation', 'product_seed_opt'):
            restart.append('build')
        elif failed.purpose == 'ts_opt':
            restart.append('submit')
        else:
            restart.append('refine')
    if not record.is_terminal:
        restart.append(record.stage)
    revised.stage = min(restart, key=STAGE_ORDER.index) if restart else record.stage
    revised.job_steps = [step for step in revised.job_steps if step.purpose not in invalid]
    if revised.scan_step and revised.scan_step.purpose in invalid:
        revised.scan_step = None
    revised.stage_records = [row for row in revised.stage_records if STAGE_ORDER.index(row.stage) < STAGE_ORDER.index(revised.stage)]
    for purpose in invalid:
        revised.budget_action_keys.pop(purpose, None)
        revised.budget_reservations.pop(purpose, None)
    for stage_key, action_key in list(revised.budget_action_keys.items()):
        if action_key in receipt.released_action_keys:
            revised.budget_action_keys.pop(stage_key, None)
            revised.budget_reservations.pop(stage_key, None)
    if STAGE_ORDER.index(revised.stage) <= STAGE_ORDER.index('guess'):
        revised.current_ts_guess_path = ''
        revised.path_kind = 'not_attempted'
        revised.job_id, revised.job_input_path = None, ''
    elif 'ts_opt' in invalid or any(path.startswith('ts_optimization') for path in receipt.changes):
        revised.job_id, revised.job_input_path = None, ''
    if STAGE_ORDER.index(revised.stage) <= STAGE_ORDER.index('map'):
        revised.input_binding = {}
        for table in revised.structures.values():
            table['binding_status'] = 'unverified'
            table.pop('heavy_atom_indices', None)
    if STAGE_ORDER.index(revised.stage) <= STAGE_ORDER.index('build'):
        if source_hashes:
            revised.input_binding['revision_source_hashes'] = {
                role: (projections[role]['table']['normalization']['canonical_hashes']
                       if role in projections else hashes) for role, hashes in source_hashes.items()}
        revised.structures = {}
        revised.structures.update({role: projection['table'] for role, projection in projections.items()
                                  if role in ('reactant', 'product')})
        revised.current_seed_xyz_path, revised.current_seed_mol_path = '', ''
        revised.product_seed_xyz_path, revised.product_seed_mol_path = '', ''
        revised.current_reactant_prepared_path = ''
        revised.active_attempt_dir, revised.guidance_manifest_path = '', ''
        revised.effective_reaction_center = []
        if record.input.conformers.reactant != revised.input.conformers.reactant:
            revised.catalog_id = revised.partition_revision = revised.selected_candidate_id = None
            revised.cards_path = ''
        if record.input.conformers.product != revised.input.conformers.product:
            revised.product_seed_candidate_id = None
        if any(path.startswith(('reaction.', 'conformers.reactant', 'conformers.guidance')) for path in receipt.changes):
            revised.optimization_checkpoints = {}
    if failed is not None and failed.purpose == 'candidate_evaluation':
        revised.optimization_checkpoints = {}
    revised.evidence_candidates = [artifact for row in revised.stage_records for artifact in row.artifacts]
    revised.terminal, revised.blocked, revised.waiting_for = None, None, ''
    revised.failed_attempt = None
    revised.intervention_count += 1
    return revised


def _project_revision_input(record, changes):
    """Project canonical input and file rewrites without mutating source files."""
    changes = changes.model_copy(deep=True)
    updated = apply_input_changes(record.input, changes)
    hashes = _revision_source_hashes(record, updated)
    correspondences = _atom_correspondences(record, updated)
    for role, permutation in correspondences.items():
        source = getattr(updated.conformers, role)
        if permutation is None and source and source.kind == 'file' and role in record.structures:
            raise ValueError(f'{role}: full atom correspondence is unproved; current source cannot be normalized to the prior atom numbering')
    stale = _stale_atom_references(record, updated, changes, correspondences)
    for field in stale:
        if field == 'reaction.atom_map':
            updated.reaction.atom_map = []
        elif field == 'reaction.reaction_center':
            updated.reaction.reaction_center = []
        elif field == 'conformers.guidance.ring_order':
            updated.conformers.guidance.ring_order = []
        elif field == 'conformers.guidance.distance_filters':
            updated.conformers.guidance.distance_filters = []
        elif field == 'conformers.product':
            updated.conformers.product = None
        elif field == 'guess':
            # A provided guess already belongs to the old canonical order;
            # replacing endpoint row order alone does not change its meaning.
            if not (record.input.guess and record.input.guess.kind == 'provided'
                    and correspondences['reactant'] is not None
                    and record.input.reaction.reactant_smiles == updated.reaction.reactant_smiles
                    and record.input.reaction.product_smiles == updated.reaction.product_smiles):
                updated.guess = None
    projections = {}
    for role, permutation in correspondences.items():
        projection = _canonical_file_projection(record, updated, role, permutation)
        if projection is not None:
            projections[role] = projection
    reaction_fields = changes.reaction.model_fields_set if changes.reaction else set()
    guidance = changes.conformers.guidance if changes.conformers else None
    guidance_fields = guidance.model_fields_set if guidance else set()

    def translate(index, role):
        projection = projections.get(role)
        if projection is None:
            return index
        if index < 0 or index >= len(projection['inverse']):
            raise ValueError(f'{role}: explicit atom reference is outside its raw source atom table')
        return projection['inverse'][index]

    if updated.reaction.atom_map and 'atom_map' in reaction_fields:
        raw_map = updated.reaction.atom_map
        product = projections.get('product')
        if product and len(product['inverse']) != len(raw_map):
            raise ValueError('explicit atom_map does not cover its raw product atom table')
        canonical_map = [0] * len(raw_map)
        for raw_product, raw_reactant in enumerate(raw_map):
            canonical_map[translate(raw_product, 'product')] = translate(raw_reactant, 'reactant')
        updated.reaction.atom_map = canonical_map
    if 'reaction_center' in reaction_fields:
        updated.reaction.reaction_center = [tuple(translate(index, 'reactant') for index in pair)
                                             for pair in updated.reaction.reaction_center]
    if 'ring_order' in guidance_fields:
        updated.conformers.guidance.ring_order = [translate(index, 'reactant') for index in updated.conformers.guidance.ring_order]
    if 'distance_filters' in guidance_fields:
        for window in updated.conformers.guidance.distance_filters:
            window.atoms = [translate(index, 'reactant') for index in window.atoms]
    if updated.guess and updated.guess.kind == 'scan' and 'guess' in changes.model_fields_set:
        for coordinate in [*updated.guess.scans, *updated.guess.freeze]:
            coordinate.atoms = [translate(index, 'reactant') for index in coordinate.atoms]
    source = updated.conformers.product
    if source and source.kind == 'rotate_about_bond' and changes.conformers and 'product' in changes.conformers.model_fields_set:
        source.atoms = tuple(translate(index, 'reactant') for index in source.atoms)
    if updated.guess and updated.guess.kind == 'provided' and 'guess' in changes.model_fields_set:
        _project_provided_guess(record, updated, projections)
    _refresh_canonical_bindings(record, updated, changes, projections)
    if hashes != _revision_source_hashes(record, apply_input_changes(record.input, changes)):
        raise ValueError('source changed during input revision; use ts_inspect and redeclare the source')
    return updated, projections


def _project_provided_guess(record, updated, projections):
    """A new XYZ guess needs concrete proof of which endpoint order it uses."""
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_process import _workspace_input_path

    projection = projections.get('reactant')
    if projection is None or projection['inverse'] == list(range(len(projection['inverse']))):
        return
    path = _workspace_input_path(record, updated.guess.xyz_path)
    before = path.read_bytes()
    rows = before.decode('utf-8').splitlines(keepends=True)
    atoms = read_xyz_atoms(str(path))
    raw_rows = projection['before']['xyz'].decode('utf-8').splitlines()
    raw_atoms = [(row.split()[0], [float(v) for v in row.split()[1:4]])
                 for row in raw_rows[2:2 + len(projection['inverse'])]]
    table = record.structures['reactant']
    old = Path(record.run_dir) / 'build' / f"input_{table['input_revision']:04d}" / 'reactant' / 'seed.xyz'

    def identity_tags(source_rows):
        return [tuple(token for token in row.split()[4:] if token.startswith('in:'))
                for row in source_rows[2:2 + len(atoms)]]

    tags = identity_tags(rows)
    if atoms == read_xyz_atoms(str(old)) and tags == identity_tags(old.read_text().splitlines()):
        return
    if atoms != raw_atoms or tags != identity_tags(raw_rows):
        raise ValueError('new provided guess atom-order association is unproved; first resume the source normalization, then submit the guess using the current canonical atom table')
    order = projection['table']['normalization']['canonical_to_source']
    after = ''.join([*rows[:2], *[rows[index + 1] for index in order], *rows[len(order) + 2:]]).encode('utf-8')
    projections['guess'] = dict(paths={'xyz': str(path)}, before={'xyz': before}, after={'xyz': after})


def _apply_revision_input(record, changes):
    return _project_revision_input(record, changes)[0]


def _revision_protected_paths(record):
    """Collect immutable artifact paths without reinterpreting historical input."""
    data = record.model_dump(mode='json') if hasattr(record, 'model_dump') else record
    protected = set()
    root = Path(data.get('workspace_dir') or '.')

    def retain(paths):
        protected.update((root / path).resolve() for path in paths if isinstance(path, str) and path)

    for checkpoint in [data, *data.get('attempt_history', [])]:
        for step in [*checkpoint.get('job_steps', []), *([checkpoint['scan_step']] if checkpoint.get('scan_step') else [])]:
            retain([step.get('input_path')])
            source = step.get('external_source') or {}
            retain(source.get('artifact_hashes', {}))
        for stage in checkpoint.get('stage_records', []):
            retain(stage.get('artifacts', []))
    retain([data.get(field) for field in ('current_seed_xyz_path', 'current_seed_mol_path',
        'product_seed_xyz_path', 'product_seed_mol_path', 'current_ts_guess_path')])
    retain(data.get('evidence_candidates', []))
    return protected


def _revision_rewrite_files(record, projections, *, protected_paths=(), protected_runs=()):
    """Only current mutable sources may be overwritten; history is immutable."""
    protected = {Path(path).resolve() for path in protected_paths if path}
    protected.update(_revision_protected_paths(record))
    runs = [Path(record.run_dir).resolve(), *[Path(path).resolve() for path in protected_runs]]
    files = {}
    for projection in projections.values():
        for name, path in projection['paths'].items():
            before, after = projection['before'][name], projection['after'][name]
            resolved = Path(path).resolve()
            if resolved in protected or any(resolved.is_relative_to(run / directory)
                for run in runs for directory in ('jobs', 'path', 'verdict', 'build')):
                if before != after:
                    raise ValueError(f'cannot normalize immutable calculation input or evidence: {path}; supply a mutable current source')
            item = dict(path=path, before=before.decode('utf-8'), after=after.decode('utf-8'))
            if path in files and files[path] != item:
                raise ValueError('same source path has conflicting canonical atom orders across roles')
            files[path] = item
    return list(files.values())


def resume_revised_process(record, request, *, event_sink=None):
    """Use the tested existing ledger transaction, then the existing driver."""
    from cloudra.infra.flocks import locked
    from cloudra.services.ts_pipeline_context import pipeline_database, require_pipeline_producer, use_pipeline_database
    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process, get_revision_receipt
    from cloudra.tools.core.ts_pipeline_driver import advance_process
    from cloudra.tools.core.ts_process import TsProcessRecord, _emit
    require_pipeline_producer(record.owner_conversation_id, record.owner_session_id)
    if not record.pipeline_id:
        raise ValueError('durable TS revisions require a ledger-bound run')
    db = pipeline_database()
    with locked(str(Path(record.run_dir) / '.pipeline.lock')), use_pipeline_database(db):
        accepted = get_revision_receipt(db, process_id=record.pipeline_id, request_key=request.request_key)
        if accepted:
            if accepted.request_digest != revision_request_digest(request):
                raise ValueError('revision request key conflict')
            return TsProcessRecord.model_validate(get_process(db, record.pipeline_id)['record'])
        state = get_process(db, record.pipeline_id)
        if state is None or state['record'] is None:
            raise ValueError('process checkpoint missing')
        if state['revision'] != request.expected_revision:
            raise ValueError('stale process revision; use ts_inspect')
        current = TsProcessRecord.model_validate(state['record'])
        if (current.owner_conversation_id, current.owner_session_id) != (record.owner_conversation_id, record.owner_session_id):
            raise ValueError('process owner mismatch')
        current.revision = state['revision']
        from cloudra.tools.core.ts_process import _step_state
        for step in [*current.job_steps, *([current.scan_step] if current.scan_step else [])]:
            step.state = _step_state(current, step)
        if current.waiting_for and all(s.state not in ('ready', 'running', 'cancel_requested') for s in [*current.job_steps, *([current.scan_step] if current.scan_step else [])]):
            current.waiting_for = ''
        if (request.scan_recovery is None and request.changes.model_fields_set and apply_input_changes(current.input,request.changes) == current.input
                and not any(_file_source_drift(current, role) or _missing_source_arrived(current, role)
                            for role in ('reactant', 'product'))):
            return current
        receipt = plan_input_revision(current, request)
        revised = revise_record(current, request, receipt)
        commit_input_revision(db, process_id=record.pipeline_id, request=request, record=revised.model_dump(mode='json'), receipt=receipt)
    # Accepted checkpoint is durable before the driver can submit anything.
    state = advance_process(db, record.pipeline_id)
    current = TsProcessRecord.model_validate(state['record'])
    if event_sink:
        _emit(event_sink, current)
    return current
