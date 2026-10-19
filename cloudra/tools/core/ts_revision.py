"""Revise one owned molecular state while preserving immutable source evidence."""
from pathlib import Path

from cloudra.services.ts_pipeline_store import TsEvidenceReference, TsRevisionReceipt, revision_request_digest
from cloudra.tools.core.molecule import renumber_atoms
from cloudra.tools.core.ts_inputs import TsResumeRequest, apply_input_changes

_FORMAL = ('ts_opt', 'frequency', 'irc', 'reactant_opt', 'reactant_frequency', 'product_opt', 'product_frequency')
_DEPENDENTS = {
    'ts_opt': set(_FORMAL), 'frequency': set(_FORMAL[1:]), 'irc': set(_FORMAL[2:]),
    'reactant_opt': {'reactant_opt', 'reactant_frequency'}, 'reactant_frequency': {'reactant_frequency'},
    'product_opt': {'product_opt', 'product_frequency'}, 'product_frequency': {'product_frequency'},
    'guess': {'path', 'scan', *_FORMAL},
    'build': {'candidate_opt', 'candidate_evaluation', 'product_seed_opt', 'path', 'scan', *_FORMAL},
}


def _calculation_change_path(path):
    parts = path.split('.')
    if parts[0] in ('calculations', 'ts_optimization'):
        return True
    if parts[:2] == ['guess', 'calculation']:
        return True
    if parts[0] == 'conformers' and len(parts) > 2 and parts[2] == 'optimization':
        return True
    if parts[0] == 'verification' and len(parts) > 1:
        return (parts[1] in ('frequency', 'irc')
                or (parts[1].endswith('_endpoint') and len(parts) > 2 and parts[2] in ('optimization', 'frequency')))
    return False


def _changed_calculations(record, updated):
    from cloudra.tools.core.ts_process import stage_calculation

    after = record.model_copy(update={'input': updated})
    purposes = (*_FORMAL, 'scan', 'path', 'candidate_opt', 'candidate_evaluation', 'product_seed_opt')
    return {purpose for purpose in purposes if stage_calculation(record, purpose) != stage_calculation(after, purpose)}


def _calculation_dependents(purpose):
    if purpose in ('scan', 'path'):
        return _DEPENDENTS['guess']
    if purpose in ('candidate_opt', 'candidate_evaluation'):
        return {'candidate_opt', 'candidate_evaluation', *_DEPENDENTS['guess']}
    if purpose == 'product_seed_opt':
        return {'product_seed_opt', *_DEPENDENTS['guess']}
    return _DEPENDENTS[purpose]


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


def _source_redeclared(record, changes, role):
    """A locator patch means import, including explicitly reusing the same path."""
    if changes.conformers is None or role not in changes.conformers.model_fields_set:
        return False
    source = getattr(changes.conformers, role)
    before = getattr(record.input.conformers, role)
    if source is None:
        return before is not None
    fields = source.model_fields_set
    if 'kind' in fields and (before is None or source.kind != before.kind):
        return True
    return bool(fields & {'xyz_path', 'mol_path', 'catalog_id', 'candidate_id', 'generation', 'seed', 'atoms', 'degrees'})


def _input_revision_differences(record, updated, changes):
    differences = _differences(record.input.model_dump(mode='json'), updated.model_dump(mode='json'))
    for role in ('reactant', 'product'):
        if _source_redeclared(record, changes, role):
            differences.append(f'conformers.{role}')
    if _provided_guess_redeclared(changes):
        differences.append('guess')
    return sorted(set(differences))


def _provided_guess_redeclared(changes):
    return changes.guess is not None and changes.guess.kind == 'provided'


def _graph_atom_permutation(old, new, *, same_rows):
    """Require an exact, unique full molecular graph correspondence."""
    from rdkit import Chem

    from cloudra.tools.Chemtool.reaction_mapping import _mapped_label_permutation

    if old.GetNumAtoms() != new.GetNumAtoms() or old.GetNumBonds() != new.GetNumBonds():
        return None
    if not same_rows:
        # If supplied, labels are authoritative and must cover all atoms,
        # including hydrogens. Conflicting/partial labels cannot be guessed.
        try:
            _mapped_label_permutation(old, new)
        except ValueError:
            return None
    old, new = Chem.Mol(old), Chem.Mol(new)
    atom_property, bond_property = '_cloudra_revision_atom', '_cloudra_revision_bond'
    for mol in (old, new):
        for atom in mol.GetAtoms():
            atom.SetProp(atom_property, repr((atom.GetAtomicNum(), atom.GetIsotope(),
                atom.GetFormalCharge(), atom.GetNumRadicalElectrons(), atom.GetIsAromatic(),
                atom.GetAtomMapNum(), atom.GetProp('cloudra_atom_id') if atom.HasProp('cloudra_atom_id') else None,
                atom.GetIdx() if same_rows else None)))
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


def _revise_structures(record, revised, changes):
    from cloudra.tools.core.reaction_state import heavy_binding, import_file_structure, set_heavy_binding

    species_changed = {role for role in ('reactant', 'product') if
        getattr(record.input.reaction, role + '_smiles') != getattr(revised.input.reaction, role + '_smiles')}
    electronic_changed = any(getattr(record.input.reaction, field) != getattr(revised.input.reaction, field)
        for field in ('charge', 'multiplicity', 'electronic_character'))
    correspondences = {role: [] for role in ('reactant', 'product')}
    incoming_reactant = None
    for role in correspondences:
        if not _source_redeclared(record, changes, role):
            continue
        source = getattr(revised.input.conformers, role)
        old = getattr(record.structures, role)
        try:
            new = import_file_structure(revised, role, source) if source and source.kind == 'file' else None
        except FileNotFoundError:
            new = None
        if role == 'reactant':
            incoming_reactant = new
        permutation = None
        if old is not None and new is not None and role not in species_changed and not electronic_changed:
            same_rows = ([atom.GetSymbol() for atom in old.GetAtoms()] == [atom.GetSymbol() for atom in new.GetAtoms()]
                and old.GetNumConformers() and new.GetNumConformers()
                and old.GetConformer().GetPositions().tolist() == new.GetConformer().GetPositions().tolist())
            permutation = _graph_atom_permutation(old, new, same_rows=same_rows)
            if permutation is not None:
                new = renumber_atoms(new, permutation)
                new = set_heavy_binding(new, heavy_binding(old))
        correspondences[role] = permutation
        setattr(revised.structures, role, new)
    unknown = {role for role, permutation in correspondences.items() if permutation is None} | species_changed
    if unknown or electronic_changed or record.input.reaction.selected_candidate != revised.input.reaction.selected_candidate:
        revised.structures.product_to_reactant = None
    for role in ('reactant', 'product'):
        source = getattr(revised.input.conformers, role)
        if (role in species_changed or electronic_changed) and (source is None or source.kind == 'generate'):
            setattr(revised.structures, role, None)
        elif role in species_changed:
            mol = getattr(revised.structures, role)
            if mol is not None:
                setattr(revised.structures, role, set_heavy_binding(mol, []))
    reaction_fields = changes.reaction.model_fields_set if changes.reaction else set()
    if (unknown or electronic_changed) and 'selected_candidate' not in reaction_fields:
        revised.input.reaction.selected_candidate = None
    guidance = changes.conformers.guidance if changes.conformers else None
    guidance_fields = guidance.model_fields_set if guidance else set()
    explicit_guess = changes.guess is not None and 'guess' in changes.model_fields_set
    if revised.input.guess and revised.input.guess.kind == 'scan':
        explicit_guess = explicit_guess and 'scans' in changes.guess.model_fields_set
    if 'reactant' in unknown:
        if 'reaction_center' not in reaction_fields:
            revised.input.reaction.reaction_center = []
        for name in ('ring_order', 'distance_filters'):
            if name not in guidance_fields:
                setattr(revised.input.conformers.guidance, name, [])
        product = revised.input.conformers.product
        if product and product.kind == 'rotate_about_bond':
            revised.structures.product = None
            revised.structures.product_to_reactant = None
            declared = changes.conformers.product if changes.conformers else None
            if declared is None or 'atoms' not in declared.model_fields_set:
                revised.input.conformers.product = None
        guess = revised.input.guess
        if guess is not None and (guess.kind in ('provided', 'scan') or species_changed) and not explicit_guess:
            revised.input.guess = None
    elif species_changed and not explicit_guess:
        revised.input.guess = None
    product = revised.input.conformers.product
    if correspondences['reactant'] and product and product.kind == 'rotate_about_bond':
        revised.structures.product = None
        revised.structures.product_to_reactant = None
    _translate_explicit_atoms(revised.input, changes, correspondences)
    if (changes.guess is not None and 'xyz_path' in changes.guess.model_fields_set
            and revised.input.guess is not None and revised.input.guess.kind == 'provided'):
        _import_reordered_candidate(record, revised, correspondences['reactant'], incoming_reactant)


def _import_reordered_candidate(record, revised, permutation, incoming):
    """Bind a simultaneously supplied XYZ without changing its source file."""
    if not permutation or permutation == list(range(len(permutation))):
        return
    from cloudra.tools.core.molecule import read_molecule, to_xyz, with_positions
    from cloudra.tools.core.ts_process import _workspace_input_path, _write_immutable_input

    path = _workspace_input_path(revised, revised.input.guess.xyz_path)
    data = path.read_text()
    geometry = read_molecule(input_text=data, input_format='xyz', charge=revised.input.reaction.charge)

    def same_rows(reference):
        if reference is None or reference.GetNumAtoms() != geometry.GetNumAtoms():
            return False
        if [atom.GetSymbol() for atom in reference.GetAtoms()] != [atom.GetSymbol() for atom in geometry.GetAtoms()]:
            return False
        return reference.GetConformer().GetPositions().tolist() == geometry.GetConformer().GetPositions().tolist()

    if same_rows(record.structures.reactant):
        canonical = geometry
    elif same_rows(incoming):
        canonical = renumber_atoms(geometry, permutation)
    else:
        raise ValueError('provided guess atom-order association is unproved; import the endpoint source first, '
                         'then supply the guess in the current canonical atom order')
    candidate = with_positions(revised.structures.reactant, canonical.GetConformer().GetPositions())
    target = Path(revised.run_dir) / 'path' / f'input_{revised.declaration_revision:04d}' / 'provided_canonical.xyz'
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_immutable_input(str(target), to_xyz(candidate))
    if str(path) not in revised.input.guess.evidence_refs:
        revised.input.guess.evidence_refs.append(str(path))
    revised.input.guess.xyz_path = str(target)


def _translate_explicit_atoms(updated, changes, correspondences):
    """Current state stays canonical; only newly declared raw indices convert."""
    inverses = {}
    for role, permutation in correspondences.items():
        if permutation:
            inverse = [0] * len(permutation)
            for canonical, raw in enumerate(permutation):
                inverse[raw] = canonical
            inverses[role] = inverse

    def translate(index, role='reactant'):
        if role not in inverses:
            return index
        inverse = inverses[role]
        if index < 0 or index >= len(inverse):
            raise ValueError(f'{role}: explicit atom reference is outside its source atom table')
        return inverse[index]

    if changes.reaction and 'reaction_center' in changes.reaction.model_fields_set:
        updated.reaction.reaction_center = [tuple(translate(index) for index in pair)
            for pair in updated.reaction.reaction_center]
    guidance = changes.conformers.guidance if changes.conformers else None
    if guidance and 'ring_order' in guidance.model_fields_set:
        updated.conformers.guidance.ring_order = [translate(index) for index in updated.conformers.guidance.ring_order]
    if guidance and 'distance_filters' in guidance.model_fields_set:
        for window in updated.conformers.guidance.distance_filters:
            window.atoms = [translate(index) for index in window.atoms]
    if updated.guess and updated.guess.kind == 'scan' and changes.guess is not None:
        for name in ('scans', 'freeze'):
            if name in changes.guess.model_fields_set:
                for coordinate in getattr(updated.guess, name):
                    coordinate.atoms = [translate(index) for index in coordinate.atoms]
    source = updated.conformers.product
    declared = changes.conformers.product if changes.conformers else None
    if source and source.kind == 'rotate_about_bond' and declared and 'atoms' in declared.model_fields_set:
        source.atoms = tuple(translate(index) for index in source.atoms)


def plan_input_revision(record, request: TsResumeRequest) -> TsRevisionReceipt:
    """Return affected job references; do not mutate record, files or ledger."""
    steps = list(record.job_steps) + ([record.scan_step] if record.scan_step else [])
    if any(step.state in ('running', 'cancel_requested') for step in steps):
        raise ValueError('active compute jobs prevent input revisions; use ts_inspect')
    updated = apply_input_changes(record.input, request.changes)
    differences = _input_revision_differences(record, updated, request.changes)
    failed = _failed_step(record)
    if not differences and failed is None and record.stop_reason is None:
        raise ValueError('no input change or failed attempt to retry; use ts_inspect')
    before_limits, after_limits = record.input.execution.limits, updated.execution.limits
    if before_limits:
        if after_limits is None or before_limits.source != after_limits.source:
            raise ValueError('authorized limits cannot be removed or change source')
        for field in ('max_compute_actions', 'max_model_calls'):
            before, after = getattr(before_limits, field), getattr(after_limits, field)
            if before is not None and (after is None or after > before):
                raise ValueError('input revision cannot raise authorized limits')
    invalidated = set()
    for purpose in _changed_calculations(record, updated):
        invalidated.update(_calculation_dependents(purpose))
    for path in differences:
        if _calculation_change_path(path):
            continue
        if path.startswith(('reaction.reactant_smiles', 'reaction.product_smiles', 'reaction.charge', 'reaction.multiplicity', 'reaction.electronic_character', 'reaction.reaction_center', 'conformers.')):
            invalidated.update(_DEPENDENTS['build'])
        elif path.startswith(('reaction.selected_candidate', 'guess')):
            invalidated.update(_DEPENDENTS['guess'])
        elif path.startswith('ts_optimization'):
            invalidated.update(_DEPENDENTS['ts_opt'])
        elif path.startswith('verification.'):
            field = path.split('.')[1]
            if field.endswith('_endpoint'):
                side = field.removesuffix('_endpoint')
                task = path.split('.')[2]
                if task == 'component_logs':
                    continue
                purpose = side + ('_frequency' if task == 'frequency' else '_opt')
            else:
                purpose = 'irc' if field == 'irc_log' else field
            invalidated.update(_DEPENDENTS[purpose])
    separated_products = bool(updated.verification.product_endpoint.component_logs) or (
        isinstance(updated.reaction.product_smiles, list) and len(updated.reaction.product_smiles) > 1)
    if failed is not None and not (separated_products and failed.purpose in ('product_opt', 'product_frequency')):
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
        released_action_keys=released)


def revise_record(record, request, receipt):
    """Import explicitly changed sources once; never rewrite caller files."""
    from cloudra.tools.core.ts_process import STAGE_ORDER, TsAttemptHistory
    revised = record.model_copy(deep=True)
    revised.attempt_history.append(TsAttemptHistory(declaration_revision=record.declaration_revision,
        selected_candidate_id=record.selected_candidate_id, job_steps=[*record.job_steps, *([record.scan_step] if record.scan_step else [])], stage_records=record.stage_records,
        input=record.input, terminal=record.terminal, blocked=record.blocked, failed_attempt=record.failed_attempt,
        stop_reason=record.stop_reason, structures=record.structures.model_copy(deep=True),
        provided_guess_binding=record.provided_guess_binding,
        reason=request.reason))
    revised.input = apply_input_changes(record.input, request.changes)
    revised.declaration_revision = receipt.input_revision
    revised.revision = receipt.revision
    _revise_structures(record, revised, request.changes)
    if (_provided_guess_redeclared(request.changes)
            or revised.input.guess is None or revised.input.guess.kind != 'provided'):
        revised.provided_guess_binding = None
    invalid_refs = {(ref.stage_key, ref.job_id) for ref in receipt.invalidated}
    invalid = {step.purpose for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]
        if (step.stage_key or step.purpose, step.job_id) in invalid_refs}
    restart = []
    changed_calculations = _changed_calculations(record, revised.input)
    for purpose in changed_calculations:
        restart.append('build' if purpose in ('candidate_opt', 'candidate_evaluation', 'product_seed_opt')
                       else 'guess' if purpose in ('scan', 'path') else 'submit' if purpose == 'ts_opt' else 'refine')
    for path in receipt.changes:
        if _calculation_change_path(path):
            continue
        if path.startswith(('reaction.reactant_smiles', 'reaction.product_smiles', 'reaction.charge', 'reaction.multiplicity', 'reaction.electronic_character')):
            restart.append('declare')
        elif path.startswith('conformers.'):
            restart.append('build')
        elif path.startswith('reaction.selected_candidate'):
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
        revised.structures.candidate = None
        revised.path_kind = 'not_attempted'
        revised.job_id, revised.job_input_path = None, ''
    elif 'ts_opt' in invalid or any(path.startswith('ts_optimization') for path in receipt.changes):
        revised.job_id, revised.job_input_path = None, ''
    if STAGE_ORDER.index(revised.stage) <= STAGE_ORDER.index('build'):
        revised.active_attempt_dir, revised.guidance_manifest_path = '', ''
        if (_source_redeclared(record, request.changes, 'reactant')
                or changed_calculations & {'candidate_opt', 'candidate_evaluation'}):
            revised.catalog_id = revised.partition_revision = revised.selected_candidate_id = None
            revised.cards_path = ''
        if _source_redeclared(record, request.changes, 'product') or 'product_seed_opt' in changed_calculations:
            revised.product_seed_candidate_id = None
        if (any(path.startswith(('reaction.', 'conformers.reactant', 'conformers.guidance')) for path in receipt.changes)
                or changed_calculations & {'candidate_opt', 'candidate_evaluation'}):
            revised.optimization_checkpoints = {}
    if failed is not None and failed.purpose == 'candidate_evaluation':
        revised.optimization_checkpoints = {}
    revised.evidence_candidates = [artifact for row in revised.stage_records for artifact in row.artifacts]
    revised.terminal, revised.blocked = None, None
    revised.stop_reason = None
    retained_steps = [*revised.job_steps, *([revised.scan_step] if revised.scan_step else [])]
    revised.waiting_for = record.waiting_for if any(
        record.waiting_for == f'job:{step.job_id}' for step in retained_steps) else ''
    revised.failed_attempt = None
    revised.intervention_count += 1
    return revised


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
        if (current.stop_reason is None and _failed_step(current) is None and request.changes.model_fields_set and apply_input_changes(current.input,request.changes) == current.input
                and not _provided_guess_redeclared(request.changes)
                and not any(_source_redeclared(current, request.changes, role) for role in ('reactant', 'product'))):
            return current
        commit_input_revision(db, process_id=record.pipeline_id, request=request)
    # Accepted checkpoint is durable before the driver can submit anything.
    state = advance_process(db, record.pipeline_id)
    current = TsProcessRecord.model_validate(state['record'])
    if event_sink:
        _emit(event_sink, current)
    return current
