"""Pure TS revision planning on the fixed scientific dependency chain."""
import hashlib
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


def _source_identity(source):
    if source is None:
        return None
    fields = {'file': ('xyz_path', 'mol_path'), 'catalog': ('catalog_id', 'candidate_id', 'partition_revision'),
              'generate': ('generation', 'seed'), 'rotate_about_bond': ()}[source.kind]
    return (source.kind, *(getattr(source, field) for field in fields))


def _file_source_drift(record, role):
    source = getattr(record.input.conformers, role)
    if source is None or source.kind != 'file' or role not in record.structures:
        return False
    source_revision = record.structures[role]['input_revision']
    snapshot = Path(record.run_dir) / 'build' / f'input_{source_revision:04d}' / role
    for name, source_path in (('seed.xyz', source.xyz_path), ('seed.mol', source.mol_path)):
        if source_path is None:
            continue
        old = snapshot / name
        current = Path(source_path)
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


def _stale_atom_references(record, updated, changes):
    identity_changed = any(
        getattr(record.input.reaction, field) != getattr(updated.reaction, field)
        for field in ('reactant_smiles', 'product_smiles')
    ) or any(
        _source_identity(getattr(record.input.conformers, role)) !=
        _source_identity(getattr(updated.conformers, role)) or _file_source_drift(record, role)
        or _missing_source_arrived(record, role)
        for role in ('reactant', 'product')
    )
    if not identity_changed:
        return []
    reaction_fields = changes.reaction.model_fields_set if changes.reaction is not None else set()
    conformers = changes.conformers
    guidance = conformers.guidance if conformers is not None else None
    guidance_fields = guidance.model_fields_set if guidance is not None else set()
    stale = []
    if record.input.reaction.atom_map and 'atom_map' not in reaction_fields:
        stale.append('reaction.atom_map')
    if record.input.reaction.reaction_center and 'reaction_center' not in reaction_fields:
        stale.append('reaction.reaction_center')
    existing_guidance = record.input.conformers.guidance
    if existing_guidance.ring_order and 'ring_order' not in guidance_fields:
        stale.append('conformers.guidance.ring_order')
    if existing_guidance.distance_filters and 'distance_filters' not in guidance_fields:
        stale.append('conformers.guidance.distance_filters')
    if record.input.guess is not None and 'guess' not in changes.model_fields_set:
        stale.append('guess')
    return stale


def plan_input_revision(record, request: TsResumeRequest) -> TsRevisionReceipt:
    """Return affected job references; do not mutate record, files or ledger."""
    steps = list(record.job_steps) + ([record.scan_step] if record.scan_step else [])
    if record.waiting_for or any(step.state in ('ready', 'running', 'cancel_requested') for step in steps):
        raise ValueError('active compute jobs prevent input revisions; use ts_inspect')
    updated = apply_input_changes(record.input, request.changes)
    differences = _differences(record.input.model_dump(mode='json'), updated.model_dump(mode='json'))
    differences.extend(_stale_atom_references(record, updated, request.changes))
    for role in ('reactant', 'product'):
        if _file_source_drift(record, role) or _missing_source_arrived(record, role):
            differences.append(f'conformers.{role}.xyz_path')
    differences = sorted(set(differences))
    failed = _failed_step(record)
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
        if path.startswith(('reaction.reactant_smiles', 'reaction.product_smiles', 'reaction.charge', 'reaction.multiplicity', 'reaction.reaction_center', 'conformers.')):
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
        released_action_keys=released)


def revise_record(record, request, receipt):
    """Construct a new checkpoint on a deep copy; no writes or submissions."""
    from cloudra.tools.core.ts_process import STAGE_ORDER, TsAttemptHistory
    revised = record.model_copy(deep=True)
    revised.attempt_history.append(TsAttemptHistory(declaration_revision=record.declaration_revision,
        selected_candidate_id=record.selected_candidate_id, job_steps=[*record.job_steps, *([record.scan_step] if record.scan_step else [])], stage_records=record.stage_records,
        input=record.input, terminal=record.terminal, blocked=record.blocked, failed_attempt=record.failed_attempt, reason=request.reason))
    revised.input = apply_input_changes(record.input, request.changes)
    stale = _stale_atom_references(record, revised.input, request.changes)
    if 'reaction.atom_map' in stale:
        revised.input.reaction.atom_map = []
    if 'reaction.reaction_center' in stale:
        revised.input.reaction.reaction_center = []
    if 'conformers.guidance.ring_order' in stale:
        revised.input.conformers.guidance.ring_order = []
    if 'conformers.guidance.distance_filters' in stale:
        revised.input.conformers.guidance.distance_filters = []
    if 'guess' in stale:
        revised.input.guess = None
    revised.declaration_revision = receipt.input_revision
    revised.revision = receipt.revision
    invalid_refs = {(ref.stage_key, ref.job_id) for ref in receipt.invalidated}
    invalid = {step.purpose for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]
        if (step.stage_key or step.purpose, step.job_id) in invalid_refs}
    restart = []
    for path in receipt.changes:
        if path.startswith(('reaction.reactant_smiles', 'reaction.product_smiles', 'reaction.charge', 'reaction.multiplicity')):
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
        revised.structures = {}
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
        if (request.changes.model_fields_set and apply_input_changes(current.input,request.changes) == current.input
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
