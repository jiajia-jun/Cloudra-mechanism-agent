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


def validate_recovery(record, request: TsResumeRequest) -> None:
    """Read ledger-backed repair evidence; never clear a failure or submit work."""
    failed = _failed_step(record)
    if failed is None:
        if request.recovery:
            raise ValueError('recovery does not bind an actual failed attempt')
        return
    recovery = request.recovery
    if recovery is None:
        raise ValueError('failed computation requires relevant recovery evidence; reason or scan point count alone cannot authorize retry')
    expected = f'{failed.source_input_revision}:{failed.purpose}:{failed.job_id}'
    if recovery.failed_attempt != expected:
        raise ValueError(f'recovery must bind failed_attempt {expected}')
    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.services.ts_pipeline_context import pipeline_database
    root = Path(record.workspace_dir).resolve()
    supplied = set()
    for reference in recovery.evidence_refs:
        path = Path(reference).resolve()
        path.relative_to(root)
        if not path.is_file():
            raise ValueError('recovery artifact missing')
        supplied.add(str(path))
    with pipeline_database().connect() as con:
        jobs = con.execute("SELECT id,path,jobtype FROM compute_jobs WHERE conversation_id=? AND state='done' AND id>?",
                           (record.owner_conversation_id, failed.job_id or 0)).fetchall()
    old = Path(failed.input_path)
    digest = hashlib.sha256(old.read_bytes()).hexdigest() if old.is_file() else None
    # An execution repair is distinct from a scientifically invalid result.
    # Require native normal termination even when the authoritative ledger says done.
    execution_failure = failed.state in ('failed', 'cancelled', 'missing') and (
        not record.failed_attempt or record.failed_attempt['failure_class'] in (
            'scan_job_failed', 'unclassified_failure', 'conformer_optimization_failed'))
    for job_id, path, engine in jobs:
        input_path = Path(path).resolve()
        log_path = Path(resolve_log_path(path, job_type=engine, task_id=job_id)).resolve()
        if not execution_failure or not supplied & {str(input_path), str(log_path)} or digest is None:
            continue
        if engine not in ('orca', 'gaussian') or not input_path.is_file() or hashlib.sha256(input_path.read_bytes()).hexdigest() != digest:
            continue
        frames = __import__('cloudra.tools.core.' + ('orca_frames' if engine == 'orca' else 'gaussian_frames'), fromlist=['normal_termination'])
        if log_path.is_file() and frames.normal_termination(log_path.read_text()):
            return
    updated = apply_input_changes(record.input, request.changes)
    from cloudra.tools.core.calculation_intent import native_input_geometry
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_process import _check_calculation_submission, _step_calculation, stage_calculation
    trial = record.model_copy(deep=True)
    trial.input = updated
    # Changing the search route is a new exploration attempt, not an assertion
    # that the old scan succeeded. Bind the old failure and inspect the new inputs.
    if failed.purpose in ('scan', 'path') and updated.guess and record.input.guess and updated.guess.kind != record.input.guess.kind:
        from cloudra.tools.core.ts_process import _bound_input_structure, _read_built_xyz
        failure_refs = {str(old.resolve())}
        if record.failed_attempt:
            failure_refs.update(str(Path(ref).resolve()) for ref in record.failed_attempt['evidence_refs'])
        if supplied & failure_refs:
            guess = updated.guess
            if guess.kind == 'provided':
                candidate = Path(guess.xyz_path).resolve()
                candidate.relative_to(root)
                atoms = read_xyz_atoms(str(candidate))
                built = _read_built_xyz(record, 'reactant')
                refs = {str(Path(ref).resolve()) for ref in guess.evidence_refs}
                if built and [symbol for symbol, _ in atoms] == built[0] and str(candidate) in supplied and refs and refs <= supplied:
                    return
            elif guess.kind == 'xtb_path' and guess.method == 'GFN2-xTB':
                # Both concrete endpoints must retain their checked species and
                # full mapping; the normal driver then applies live method policy.
                for role in ('reactant', 'product'):
                    built = _read_built_xyz(record, role)
                    if built is None or str(Path(built[2]).resolve()) not in supplied:
                        break
                    _bound_input_structure(trial, role, persist_artifact=False)
                else:
                    reactant, product = _read_built_xyz(record, 'reactant'), _read_built_xyz(record, 'product')
                    mapping = record.input.reaction.atom_map
                    if sorted(mapping) == list(range(len(reactant[0]))) and len(product[0]) == len(mapping) and all(product[0][i] == reactant[0][j] for i, j in enumerate(mapping)):
                        return
    # A new seed must have archived qualification, or native successful evidence
    # at that seed and the explicitly revised calculation. Free text is never proof.
    for role in ('reactant', 'product'):
        source = getattr(updated.conformers, role)
        if source and source.kind == 'catalog' and source != getattr(record.input.conformers, role):
            from cloudra.services.conformer_store import get_region_snapshot, list_candidates
            snapshot = get_region_snapshot(pipeline_database(), source.catalog_id, source.partition_revision,
                project_id=record.owner_conversation_id, owner_id=record.owner_session_id)
            candidate = next((c for c in list_candidates(pipeline_database(), source.catalog_id,
                project_id=record.owner_conversation_id, owner_id=record.owner_session_id) if c.candidate_id == source.candidate_id), None)
            if candidate and candidate.candidate_id in snapshot.descriptors and candidate.qualification.status == 'qualified' and str(Path(candidate.geometry_ref).resolve()) in supplied:
                candidate.verify_artifact()
                return
    calculation = stage_calculation(trial, failed.purpose)
    seed = None
    if failed.purpose.startswith(('reactant_', 'product_')):
        side = failed.purpose.split('_')[0]
        replacement = getattr(updated.verification, side + '_endpoint').seed
        if replacement:
            seed = replacement.xyz_path
    if failed.purpose in ('candidate_opt', 'product_seed_opt'):
        source = getattr(updated.conformers, 'reactant' if failed.purpose == 'candidate_opt' else 'product')
        if source and source.kind == 'file':
            seed = source.xyz_path
    def canonical(atoms):
        return [(symbol, tuple(format(float(x), '.8f') for x in point)) for symbol, point in atoms]
    if calculation and calculation.engine in ('orca', 'gaussian'):
        try:
            target_geometry = canonical(read_xyz_atoms(seed)) if seed else canonical(native_input_geometry(old.read_text(), engine=_step_calculation(record, failed).engine))
        except (OSError, ValueError):
            target_geometry = None
        for job_id, path, engine in jobs:
            input_path = Path(path).resolve()
            log_path = Path(resolve_log_path(path, job_type=engine, task_id=job_id)).resolve()
            if not supplied & {str(input_path), str(log_path)} or engine != calculation.engine or target_geometry is None:
                continue
            try:
                content = input_path.read_text()
                _check_calculation_submission(trial, failed.purpose, str(input_path), engine)
                frames = __import__('cloudra.tools.core.' + ('orca_frames' if engine == 'orca' else 'gaussian_frames'), fromlist=['normal_termination'])
                if not frames.normal_termination(log_path.read_text()) or canonical(native_input_geometry(content, engine=engine)) != target_geometry:
                    continue
                if failed.purpose in ('frequency', 'reactant_frequency', 'product_frequency'):
                    from cloudra.dag.evidence_ingest import _extract_qm_log
                    _, _, frequencies, imaginary, _, _ = _extract_qm_log(log_path)
                    if frequencies is None and imaginary is None:
                        continue
                    imaginary = imaginary if imaginary is not None else [f for f in frequencies if f < 0]
                    if len(imaginary) != (1 if failed.purpose == 'frequency' else 0):
                        continue
                elif record.failed_attempt and record.failed_attempt['failure_class'] in ('wrong_mode', 'endpoint_unconfirmed', 'scan_no_candidate', 'scan_invalid_geometry'):
                    # These outcomes require their specific scientific proof; a
                    # generic normal termination cannot certify their repair.
                    continue
                return
            except (ValueError, OSError):
                continue
    raise ValueError('recovery evidence must reference an authoritative successful relevant calculation or a changed qualified catalog seed; unrelated artifacts cannot authorize retry')


def plan_input_revision(record, request: TsResumeRequest) -> TsRevisionReceipt:
    """Return affected job references; do not mutate record, files or ledger."""
    steps = list(record.job_steps) + ([record.scan_step] if record.scan_step else [])
    if record.waiting_for or any(step.state in ('ready', 'running', 'cancel_requested') for step in steps):
        raise ValueError('active compute jobs prevent input revisions; use ts_inspect')
    updated = apply_input_changes(record.input, request.changes)
    differences = _differences(record.input.model_dump(mode='json'), updated.model_dump(mode='json'))
    if not differences and request.recovery is None:
        raise ValueError('no input change or recovery action; use ts_inspect')
    validate_recovery(record, request)
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
    if request.recovery:
        failed = _failed_step(record)
        if failed is None:
            raise ValueError('recovery does not bind a failed attempt')
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
        changes=differences, retained=retained, invalidated=invalid, recovery=request.recovery,
        released_action_keys=released)


def revise_record(record, request, receipt):
    """Construct a new checkpoint on a deep copy; no writes or submissions."""
    from cloudra.tools.core.ts_process import STAGE_ORDER, TsAttemptHistory
    revised = record.model_copy(deep=True)
    revised.attempt_history.append(TsAttemptHistory(declaration_revision=record.declaration_revision,
        selected_candidate_id=record.selected_candidate_id, job_steps=record.job_steps, stage_records=record.stage_records,
        input=record.input, terminal=record.terminal, blocked=record.blocked, failed_attempt=record.failed_attempt, reason=request.reason))
    revised.input = apply_input_changes(record.input, request.changes)
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
    if request.recovery:
        restart.append(record.blocked.stage if record.blocked else record.stage)
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
    if STAGE_ORDER.index(revised.stage) <= STAGE_ORDER.index('build'):
        revised.current_seed_xyz_path, revised.current_seed_mol_path = '', ''
        revised.product_seed_xyz_path, revised.product_seed_mol_path = '', ''
        revised.current_reactant_prepared_path = ''
        revised.active_attempt_dir, revised.guidance_manifest_path = '', ''
        revised.effective_reaction_center = []
        if any(path.startswith(('reaction.', 'conformers.reactant', 'conformers.guidance')) for path in receipt.changes):
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
        if request.changes.model_fields_set and request.recovery is None and apply_input_changes(current.input,request.changes) == current.input:
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
