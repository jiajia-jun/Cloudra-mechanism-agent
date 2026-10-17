"""Durable TS processes and stage bindings in the existing compute ledger."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Literal

from pydantic import Field

from cloudra.persistence.database import ComputeDB, retry_on_locked
from cloudra.services.exploration_budget_store import ExplorationBudget
from cloudra.tools.core.conformer_catalog import CatalogModel, content_digest
from cloudra.tools.core.ts_inputs import TsInput, TsResumeRequest


class TsEvidenceReference(CatalogModel):
    declaration_revision: int = Field(ge=1)
    stage_key: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    job_id: int | None = None


class TsRevisionReceipt(CatalogModel):
    request_key: str = Field(min_length=1)
    request_digest: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    previous_revision: int = Field(ge=0)
    revision: int = Field(ge=1)
    previous_input_revision: int = Field(ge=1)
    input_revision: int = Field(ge=2)
    changes: list[str]
    retained: list[TsEvidenceReference]
    invalidated: list[TsEvidenceReference]
    released_action_keys: list[str] = Field(default_factory=list)
    source_hashes: dict[str, dict[str, str]] = Field(default_factory=dict)
    status: Literal['accepted'] = 'accepted'


def revision_request_digest(request: TsResumeRequest) -> str:
    return content_digest(request.model_dump(mode='json', exclude_unset=True))


def get_revision_receipt(db: ComputeDB, *, process_id: str, request_key: str) -> TsRevisionReceipt | None:
    with _rewrite_lock(db):
        _recover_source_rewrite(db, process_id)
        with db.connect() as con:
            row = con.execute('SELECT payload FROM ts_pipeline_revision_receipts WHERE process_id=? AND request_key=?',
                              (process_id, request_key)).fetchone()
    return TsRevisionReceipt.model_validate_json(row[0]) if row else None


def _rewrite_lock(db):
    from cloudra.infra.flocks import locked

    db.ensure_dir()
    return locked(str(Path(db.path).with_suffix('.ts-source-rewrite.lock')))


class SourceRewriteRecoveryBlocked(ValueError):
    """The authoritative checkpoint is readable only as a blocked diagnostic."""

    def __init__(self, message, *, affected_roles):
        super().__init__(message)
        self.affected_roles = tuple(affected_roles)


def _check_revision_budget(con, process_id, value):
    limits = value.execution.limits
    old = con.execute('SELECT payload FROM exploration_budgets WHERE process_id=?', (process_id,)).fetchone()
    if limits is None:
        if old:
            raise ValueError('revision cannot remove an authorized hard budget')
        return None
    budget = ExplorationBudget(source=limits.source, max_compute_actions=limits.max_compute_actions,
                               max_model_calls=limits.max_model_calls)
    if old:
        previous = ExplorationBudget.model_validate_json(old[0])
        if previous.source != budget.source:
            raise ValueError('budget source mismatch')
        for field in ('max_compute_actions', 'max_model_calls'):
            before, after = getattr(previous, field), getattr(budget, field)
            if before is not None and (after is None or after > before):
                raise ValueError('revision cannot raise an authorized hard budget')
    return budget


def _persist_prepared_revision(con, process_id, record, receipt):
    """Commit an already checked rewrite intent using its captured declaration."""
    scope = con.execute('SELECT project_id,owner_id,revision,declaration_revision FROM ts_pipeline_processes '
                        'WHERE process_id=?', (process_id,)).fetchone()
    if scope is None or scope[2] != receipt.previous_revision or scope[3] != receipt.previous_input_revision:
        raise ValueError('stale process revision during source normalization')
    active = con.execute('SELECT 1 FROM ts_pipeline_stages s JOIN compute_jobs j ON j.id=s.job_id '
                         "WHERE s.process_id=? AND j.state IN ('running','cancel_requested') LIMIT 1",
                         (process_id,)).fetchone()
    if active:
        raise ValueError('active stage job prevents input revision')
    for ref in receipt.invalidated:
        if ref.job_id is not None:
            con.execute("UPDATE compute_jobs SET state='cancelled', end_timestamp=?, "
                        "last_error='superseded by TS input revision' WHERE id=? AND state='ready'",
                        (time.time(), ref.job_id))
    value = TsInput.model_validate(record['input'])
    budget = _check_revision_budget(con, process_id, value)
    if budget:
        con.execute('INSERT INTO exploration_budgets VALUES (?,?,?,?) ON CONFLICT(process_id) '
                    'DO UPDATE SET payload=excluded.payload', (process_id, *scope[:2], budget.model_dump_json()))
    status = 'blocked' if record.get('blocked') else 'waiting' if record.get('waiting_for') else 'running'
    con.execute('INSERT INTO ts_pipeline_declarations VALUES (?,?,?)',
                (process_id, receipt.input_revision, value.model_dump_json()))
    con.execute('UPDATE ts_pipeline_processes SET declaration_revision=?,revision=?,record=?,status=? WHERE process_id=?',
                (receipt.input_revision, receipt.revision, json.dumps(record, sort_keys=True), status, process_id))
    for key in receipt.released_action_keys:
        con.execute('INSERT OR IGNORE INTO exploration_released_actions SELECT process_id,action_key,? '
                    'FROM exploration_actions WHERE process_id=? AND action_key=? AND job_id IS NULL AND actual IS NULL',
                    ('input revised', process_id, key))
    con.execute('INSERT INTO ts_pipeline_revision_receipts VALUES (?,?,?)',
                (process_id, receipt.request_key, receipt.model_dump_json()))


def _write_revision_exports(record):
    """Refresh exports from accepted state without another ledger mutation."""
    from cloudra.persistence.fs_utils import atomic_write_text
    from cloudra.tools.core.ts_process import (
        BUILD_STAGE_DIR,
        DECLARE_JSON_NAME,
        PROCESS_JSON_NAME,
        TsProcessRecord,
        _write_immutable_input,
    )

    value = TsProcessRecord.model_validate(record)
    Path(value.run_dir).mkdir(parents=True, exist_ok=True)
    for role, table in value.structures.items():
        normalization = table.get('normalization')
        if not normalization or normalization['input_revision'] != value.declaration_revision:
            continue
        target = Path(value.run_dir) / BUILD_STAGE_DIR / f'input_{value.declaration_revision:04d}' / role
        target.mkdir(parents=True, exist_ok=True)
        for name, source in normalization['paths'].items():
            data = Path(source).read_bytes()
            if hashlib.sha256(data).hexdigest() != normalization['canonical_hashes'][name]:
                raise ValueError('canonical source changed before accepted export; redeclare the source')
            _write_immutable_input(str(target / f'seed.{name}'), data.decode('utf-8'))
    atomic_write_text(str(Path(value.run_dir) / PROCESS_JSON_NAME), value.model_dump_json(indent=2) + '\n')
    atomic_write_text(str(Path(value.run_dir) / DECLARE_JSON_NAME), value.input.model_dump_json(indent=2) + '\n')


def _recover_source_rewrite(db, process_id):
    """Finish an internal rewrite intent before any authoritative read succeeds."""
    from cloudra.persistence.fs_utils import atomic_write_bytes

    with db.connect() as con:
        row = con.execute('SELECT payload FROM ts_pipeline_source_rewrites WHERE process_id=?', (process_id,)).fetchone()
        checkpoint = con.execute('SELECT record FROM ts_pipeline_processes WHERE process_id=?', (process_id,)).fetchone() if row else None
    if row is None:
        return
    # Unsupported checkpoints and their pending intents are historical data.
    # Isolate before any file writes, revision commits or export validation.
    if checkpoint and checkpoint[0] and json.loads(checkpoint[0]).get('format_version') != 6:
        return
    intent = json.loads(row[0])
    if intent['record'].get('format_version') != 6:
        return
    receipt = TsRevisionReceipt.model_validate(intent['receipt'])
    roles = [role for role, table in intent['record'].get('structures', {}).items()
             if table.get('normalization', {}).get('input_revision') == receipt.input_revision]
    for item in intent['files']:
        path, before, after = Path(item['path']), item['before'].encode('utf-8'), item['after'].encode('utf-8')
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise SourceRewriteRecoveryBlocked('source normalization recovery blocked: current source is unavailable',
                                               affected_roles=roles) from exc
        if current not in (before, after):
            raise SourceRewriteRecoveryBlocked('source normalization recovery blocked: current file differs from captured source and canonical bytes',
                                               affected_roles=roles)
        if current != after:
            atomic_write_bytes(str(path), after)
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        accepted = con.execute('SELECT payload FROM ts_pipeline_revision_receipts WHERE process_id=? AND request_key=?',
                               (process_id, receipt.request_key)).fetchone()
        if accepted:
            if TsRevisionReceipt.model_validate_json(accepted[0]) != receipt:
                raise ValueError('source normalization recovery receipt conflict')
        else:
            _persist_prepared_revision(con, process_id, intent['record'], receipt)
    _write_revision_exports(intent['record'])
    with db.connect() as con:
        con.execute('DELETE FROM ts_pipeline_source_rewrites WHERE process_id=?', (process_id,))


def commit_input_revision(db: ComputeDB, *, process_id: str, request: TsResumeRequest,
                          record: dict, receipt: TsRevisionReceipt) -> TsRevisionReceipt:
    """Accept once, canonically overwrite current sources, and preserve history."""
    from cloudra.persistence.fs_utils import atomic_write_bytes
    from cloudra.tools.core.ts_inputs import apply_input_changes

    digest = revision_request_digest(request)

    def operation():
        _recover_source_rewrite(db, process_id)
        with db.connect() as con:
            # Prepare against one read snapshot; acquire the writer only for the intent.
            # A concurrent ledger commit makes the upgrade retry the entire preparation.
            con.execute('BEGIN')
            old = con.execute('SELECT payload FROM ts_pipeline_revision_receipts WHERE process_id=? AND request_key=?',
                              (process_id, request.request_key)).fetchone()
            if old:
                accepted = TsRevisionReceipt.model_validate_json(old[0])
                if accepted.request_digest != digest:
                    raise ValueError('revision request key conflict')
                return accepted
            scope = con.execute('SELECT project_id,owner_id,revision,declaration_revision,record FROM ts_pipeline_processes '
                                'WHERE process_id=?', (process_id,)).fetchone()
            if scope is None or scope[2] != request.expected_revision:
                raise ValueError('stale process revision')
            if (record['owner_conversation_id'], record['owner_session_id']) != scope[:2] or record['pipeline_id'] != process_id:
                raise ValueError('revision owner mismatch')
            if (receipt.request_key != request.request_key or receipt.request_digest != digest or receipt.reason != request.reason
                    or receipt.previous_revision != scope[2] or receipt.revision != scope[2] + 1
                    or receipt.previous_input_revision != scope[3] or receipt.input_revision != scope[3] + 1
                    or record['declaration_revision'] != receipt.input_revision):
                raise ValueError('revision receipt mismatch')
            active = con.execute('SELECT 1 FROM ts_pipeline_stages s JOIN compute_jobs j ON j.id=s.job_id '
                                 "WHERE s.process_id=? AND j.state IN ('running','cancel_requested') LIMIT 1",
                                 (process_id,)).fetchone()
            if active:
                raise ValueError('active stage job prevents input revision')
            value = TsInput.model_validate(record['input'])
            from cloudra.tools.core.ts_process import TsProcessRecord
            from cloudra.tools.core.ts_revision import (
                _project_revision_input,
                _revision_protected_paths,
                _revision_rewrite_files,
                _revision_source_hashes,
            )
            prior_input = con.execute('SELECT payload FROM ts_pipeline_declarations WHERE process_id=? AND declaration_revision=?',
                                      (process_id, scope[3])).fetchone()
            if scope[4] is None:
                raise ValueError('process checkpoint missing')
            prior_record = TsProcessRecord.model_validate_json(scope[4])
            if prior_record.input != TsInput.model_validate_json(prior_input[0]):
                raise ValueError('process checkpoint differs from its accepted declaration')
            raw_input = apply_input_changes(prior_record.input, request.changes)
            if receipt.source_hashes != _revision_source_hashes(prior_record, raw_input):
                raise ValueError('revision source changed since the accepted plan')
            expected_input, projections = _project_revision_input(prior_record, request.changes)
            if value != expected_input:
                raise ValueError('revision input differs from the accepted request')
            validated_record = TsProcessRecord.model_validate(record).model_copy(deep=True)
            validated_record.revision = receipt.revision
            for role, projection in projections.items():
                if role not in ('reactant', 'product'):
                    continue
                if validated_record.structures.get(role) != projection['table']:
                    raise ValueError('revision canonical structure differs from the accepted request')
                validated_record.structures[role]['normalization']['status'] = 'applied'
            accepted_record = validated_record.model_dump(mode='json')
            for ref in receipt.retained + receipt.invalidated:
                if ref.job_id is None:
                    previous_record = json.loads(con.execute('SELECT record FROM ts_pipeline_processes WHERE process_id=?', (process_id,)).fetchone()[0])
                    source = next((step for step in previous_record.get('job_steps', [])
                        if step.get('source_input_revision') == ref.declaration_revision and step.get('stage_key') == ref.stage_key and step.get('external_source')), None)
                    if source is None:
                        raise ValueError('revision external evidence binding mismatch')
                    for path, artifact_digest in (source['external_source']['artifact_hashes'].items() if ref in receipt.retained else []):
                        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != artifact_digest:
                            raise ValueError('revision external evidence artifact changed')
                    continue
                binding = con.execute('SELECT job_id FROM ts_pipeline_stages WHERE process_id=? AND '
                                      'declaration_revision=? AND stage_key=? AND attempt=?',
                                      (process_id, ref.declaration_revision, ref.stage_key, ref.attempt)).fetchone()
                if binding is None or binding[0] != ref.job_id:
                    raise ValueError('revision evidence binding mismatch')
            _check_revision_budget(con, process_id, value)
            protected, runs = [], []
            if any(projection['before'][name] != after
                   for projection in projections.values() for name, after in projection['after'].items()):
                from cloudra.infra.compute_utils import resolve_log_path
                jobs = con.execute('SELECT path,jobtype,id FROM compute_jobs').fetchall()
                protected.extend(path for path, _, _ in jobs)
                protected.extend(resolve_log_path(path, kind, job_id) for path, kind, job_id in jobs)
                suffixes = {'.xyz', '.mol', '.log', '.out', '.hess', '.chk', '.fchk', '.gbw'}
                for directory in {Path(path).parent.resolve() for path, _, _ in jobs}:
                    if directory.is_dir():
                        protected.extend(path for path in directory.iterdir() if path.suffix in suffixes)
                for row in con.execute('SELECT record FROM ts_pipeline_processes WHERE record IS NOT NULL'):
                    checkpoint = json.loads(row[0])
                    protected.extend(_revision_protected_paths(checkpoint))
                    if checkpoint.get('run_dir'):
                        runs.append(checkpoint['run_dir'])
            files = _revision_rewrite_files(prior_record, projections,
                                           protected_paths=protected, protected_runs=runs)
            intent = dict(files=files, record=accepted_record, receipt=receipt.model_dump(mode='json'))
            # This private ledger preimage is durable before the first file changes.
            con.execute('INSERT INTO ts_pipeline_source_rewrites VALUES (?,?,?)',
                        (process_id, request.request_key, json.dumps(intent, sort_keys=True)))
        committed = False
        try:
            for item in files:
                path = Path(item['path'])
                before, after = item['before'].encode('utf-8'), item['after'].encode('utf-8')
                if path.read_bytes() != before:
                    raise ValueError('source changed before canonical overwrite; redeclare the source')
                if before != after:
                    atomic_write_bytes(str(path), after)
            with db.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                _persist_prepared_revision(con, process_id, accepted_record, receipt)
            committed = True
            _write_revision_exports(accepted_record)
            with db.connect() as con:
                con.execute('DELETE FROM ts_pipeline_source_rewrites WHERE process_id=?', (process_id,))
            return receipt
        except Exception:
            if committed:
                # The durable receipt owns canonical bytes; recovery finishes exports.
                raise
            for item in reversed(files):
                path = Path(item['path'])
                before, after = item['before'].encode('utf-8'), item['after'].encode('utf-8')
                current = path.read_bytes()
                if current == after and before != after:
                    atomic_write_bytes(str(path), before)
                elif current != before:
                    raise ValueError('source normalization rollback blocked by external source changes')
            with db.connect() as con:
                con.execute('DELETE FROM ts_pipeline_source_rewrites WHERE process_id=?', (process_id,))
            raise
    with _rewrite_lock(db):
        return retry_on_locked(operation)


class ProcessPayload(CatalogModel):
    project_id: str = Field(min_length=1)
    owner_id: str | None = None
    workspace_dir: str = Field(min_length=1)
    input: TsInput



class StageJobPayload(CatalogModel):
    conversation_id: str
    session_id: str | None = None
    path: str = Field(min_length=1)
    state: Literal['ready'] = 'ready'
    jobtype: str
    node_id: str
    scheduler: str = 'local'
    scheduler_options: str = '{}'
    priority: int = 0
    req_cpus: int = Field(default=1, ge=1)
    req_memory_mb: int | None = Field(default=None, ge=1)
    charge: int = 0
    multiplicity: int = Field(default=1, ge=1)
    xtb_task: str = 'sp'
    xtb_solvent: str | None = None
    start_timestamp: float = -1


class StageBindingRequest(CatalogModel):
    process_id: str
    declaration_revision: int = Field(ge=1)
    stage_key: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    job_payload: StageJobPayload


class StageEvidence(CatalogModel):
    status: Literal['done', 'failed', 'blocked', 'cancelled']
    artifacts: list[str]
    input_hash: str
    detail: str = ''
    atom_binding: dict | None = None
    log_sha256: str | None = None


def create_process(db: ComputeDB, *, request_key: str, payload: dict) -> dict:
    if not request_key:
        raise ValueError('nonempty request key required')
    data = ProcessPayload.model_validate(payload)
    text = data.model_dump_json()
    pid = content_digest([data.project_id, data.owner_id, request_key])
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT payload FROM ts_pipeline_processes WHERE process_id=?', (pid,)).fetchone()
            if old and old[0] != text:
                raise ValueError('request key declaration/scope conflict')
            con.execute('INSERT OR IGNORE INTO ts_pipeline_processes VALUES (?,?,?,?,?,1,0,?,NULL)',
                        (pid, request_key, data.project_id, data.owner_id, text, 'running'))
            con.execute('INSERT OR IGNORE INTO ts_pipeline_declarations VALUES (?,1,?)',
                        (pid, data.input.model_dump_json()))
        return get_process(db, pid)
    return retry_on_locked(operation)


def get_process(db: ComputeDB, process_id: str) -> dict | None:
    with _rewrite_lock(db):
        _recover_source_rewrite(db, process_id)
        with db.connect() as con:
            row = con.execute('SELECT process_id,payload,declaration_revision,revision,status,record '
                              'FROM ts_pipeline_processes WHERE process_id=?', (process_id,)).fetchone()
    if row is None:
        return None
    return dict(process_id=row[0], payload=json.loads(row[1]), declaration_revision=row[2], revision=row[3],
                status=row[4], record=json.loads(row[5]) if row[5] else None)


def stop_process(db: ComputeDB, *, process_id: str, project_id: str,
                 owner_id: str | None, reason: str) -> dict:
    """Record a scoped stop and its job cancellations in one transaction."""
    from cloudra.persistence.fs_utils import atomic_write_json
    from cloudra.tools.core.ts_process import PROCESS_JSON_NAME, TsProcessRecord

    reason = reason.strip()
    if not reason:
        raise ValueError('stop reason required')

    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT project_id,owner_id,revision,record FROM ts_pipeline_processes '
                              'WHERE process_id=?', (process_id,)).fetchone()
            if row is None or row[:2] != (project_id, owner_id):
                raise ValueError('process owner mismatch')
            state = TsProcessRecord.model_validate_json(row[3])
            if state.is_terminal or state.stop_reason:
                return state.model_dump(mode='json')
            con.execute("UPDATE compute_jobs SET state='cancelled', end_timestamp=?, "
                        "last_error='TS pipeline stopped' WHERE state='ready' AND id IN "
                        '(SELECT job_id FROM ts_pipeline_stages WHERE process_id=?)',
                        (time.time(), process_id))
            con.execute("UPDATE compute_jobs SET state='cancel_requested' WHERE state='running' AND id IN "
                        '(SELECT job_id FROM ts_pipeline_stages WHERE process_id=?)', (process_id,))
            jobs = dict(con.execute('SELECT j.id,j.state FROM ts_pipeline_stages s '
                                    'JOIN compute_jobs j ON j.id=s.job_id WHERE s.process_id=?', (process_id,)))
            for step in [*state.job_steps, *([state.scan_step] if state.scan_step else [])]:
                if step.job_id in jobs:
                    step.state = jobs[step.job_id]
            state.stop_reason = reason
            state.revision = row[2] + 1
            con.execute("UPDATE ts_pipeline_processes SET record=?,status='stopped',revision=? WHERE process_id=?",
                        (state.model_dump_json(), state.revision, process_id))
            return state.model_dump(mode='json')

    with _rewrite_lock(db):
        _recover_source_rewrite(db, process_id)
        state = retry_on_locked(operation)
        atomic_write_json(str(Path(state['run_dir']) / PROCESS_JSON_NAME), state)
    return state


def read_process_snapshot(db: ComputeDB, *, project_id: str, run_id: str, workspace_dir: str) -> tuple[dict, list[dict]]:
    """Read process and jobs in one snapshot; ownership restricts writes, not project reads."""
    with _rewrite_lock(db):
        with db.connect() as con:
            row = con.execute('SELECT process_id FROM ts_pipeline_processes WHERE project_id=? '
                              "AND json_extract(record,'$.run_id')=? AND json_extract(payload,'$.workspace_dir')=?",
                              (project_id, run_id, workspace_dir)).fetchone()
        if row is None:
            raise ValueError('TS run not found in the authorized project and workspace')
        try:
            _recover_source_rewrite(db, row[0])
        except SourceRewriteRecoveryBlocked as exc:
            state, jobs = _read_process_snapshot(db, project_id=project_id, run_id=run_id, workspace_dir=workspace_dir)
            state['source_rewrite_recovery_blocked'] = True
            state['structures'] = {role: table for role, table in state.get('structures', {}).items()
                                   if role not in exc.affected_roles}
            state['terminal'] = None
            state['blocked'] = dict(failure_class='canonical_source_recovery_blocked', stage=state['stage'],
                message=str(exc), needs=[f'conformers.{role}' for role in exc.affected_roles],
                issues=[dict(code='source_normalization_recovery_blocked', role=role,
                    field=f'conformers.{role}') for role in exc.affected_roles])
            return state, jobs
        return _read_process_snapshot(db, project_id=project_id, run_id=run_id, workspace_dir=workspace_dir)


def _read_process_snapshot(db: ComputeDB, *, project_id: str, run_id: str, workspace_dir: str) -> tuple[dict, list[dict]]:
    with db.connect() as con:
        con.execute('BEGIN')
        row = con.execute('SELECT process_id,revision,record FROM ts_pipeline_processes WHERE project_id=? '
                          "AND json_extract(record,'$.run_id')=? AND json_extract(payload,'$.workspace_dir')=?",
                          (project_id, run_id, workspace_dir)).fetchone()
        if row is None:
            raise ValueError('TS run not found in the authorized project and workspace')
        state = json.loads(row[2])
        state['revision'] = row[1]
        rows = con.execute('SELECT j.id,s.stage_key,j.state,j.req_cpus,j.req_memory_mb,j.start_timestamp,j.end_timestamp,'
                           's.declaration_revision,s.attempt,s.evidence,j.path,j.jobtype FROM ts_pipeline_stages s '
                           'JOIN compute_jobs j ON j.id=s.job_id WHERE s.process_id=? ORDER BY j.id', (row[0],)).fetchall()
        keys = ('job_id', 'purpose', 'state', 'req_cpus', 'req_memory_mb', 'start_timestamp', 'end_timestamp',
                'source_input_revision', 'attempt', 'evidence', 'input_path', 'job_type')
        jobs = [dict(zip(keys, values, strict=True)) for values in rows]
    from cloudra.infra.compute_utils import resolve_log_path
    for job in jobs:
        if job["state"] == "done":
            log_path = resolve_log_path(job["input_path"], job["job_type"], job["job_id"])
            if Path(log_path).is_file() and Path(log_path).resolve().is_relative_to(Path(workspace_dir).resolve()):
                job["log_path"] = log_path
    return state, jobs


def bind_stage_job(db: ComputeDB, *, process_id: str, declaration_revision: int, stage_key: str,
                   attempt: int, job_payload: dict, reservation_id: str | None = None,
                   action_key: str | None = None) -> int:
    from cloudra.services.compute_store import insert_compute_job_in_transaction
    job = StageJobPayload.model_validate(job_payload)
    if not stage_key or declaration_revision < 1 or attempt < 1:
        raise ValueError('valid stage key, declaration revision and attempt required')
    if (reservation_id is None) != (action_key is None):
        raise ValueError('complete budget binding required')
    input_hash = hashlib.sha256(Path(job.path).read_bytes()).hexdigest()
    fingerprint = content_digest([job.model_dump(), input_hash, reservation_id, action_key])
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            scope = con.execute("SELECT project_id,owner_id,declaration_revision,json_extract(record,'$.stop_reason') FROM ts_pipeline_processes "
                                'WHERE process_id=?', (process_id,)).fetchone()
            if scope is None or scope[:2] != (job.conversation_id, job.session_id):
                raise ValueError('stage job owner mismatch')
            if scope[2] != declaration_revision:
                raise ValueError('stale declaration revision')
            if scope[3]:
                raise ValueError('TS pipeline is stopped; use ts_resume before submitting work')
            key = (process_id, declaration_revision, stage_key, attempt)
            existing = con.execute('SELECT job_id,input_hash FROM ts_pipeline_stages '
                                   'WHERE process_id=? AND declaration_revision=? AND stage_key=? AND attempt=?', key).fetchone()
            if existing:
                if existing[1] != fingerprint:
                    raise ValueError('immutable stage input conflict')
                return int(existing[0])
            if reservation_id is not None:
                released=con.execute('SELECT 1 FROM exploration_released_actions WHERE process_id=? AND action_key=?',(process_id,action_key)).fetchone()
                if released:
                    raise ValueError('reservation action released')
                accounting = con.execute('SELECT process_id,job_id,actual FROM exploration_actions '
                                         'WHERE reservation_id=? AND action_key=?', (reservation_id, action_key)).fetchone()
                if accounting is None or accounting[0] != process_id or accounting[1] is not None or accounting[2] is not None:
                    raise ValueError('reservation missing, foreign, consumed or settled')
            job_id = insert_compute_job_in_transaction(con, **job.model_dump())
            con.execute('INSERT INTO ts_pipeline_stages VALUES (?,?,?,?,?,?,NULL)', (*key, job_id, fingerprint))
            con.execute('INSERT INTO ts_pipeline_inputs VALUES (?,?)',(job_id,input_hash))
            if reservation_id is not None:
                con.execute('UPDATE exploration_actions SET job_id=? WHERE reservation_id=? AND action_key=?',
                            (job_id, reservation_id, action_key))
            con.execute('UPDATE ts_pipeline_processes SET revision=revision+1 WHERE process_id=?', (process_id,))
            return job_id
    return retry_on_locked(operation)


def commit_stage_result(db: ComputeDB, *, process_id: str, expected_revision: int, stage_key: str,
                        attempt: int, evidence: dict, declaration_revision: int | None = None) -> bool:
    result = StageEvidence.model_validate(evidence)
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT declaration_revision,revision FROM ts_pipeline_processes WHERE process_id=?',
                              (process_id,)).fetchone()
            if row is None or row[1] != expected_revision:
                return False
            key = (process_id, declaration_revision if declaration_revision is not None else row[0], stage_key, attempt)
            old = con.execute('SELECT evidence FROM ts_pipeline_stages WHERE process_id=? '
                              'AND declaration_revision=? AND stage_key=? AND attempt=?', key).fetchone()
            if old is None:
                raise ValueError('stage binding missing')
            if old[0] is not None:
                if old[0] != result.model_dump_json():
                    raise ValueError('immutable stage result conflict')
                return True
            con.execute('UPDATE ts_pipeline_stages SET evidence=? WHERE process_id=? AND declaration_revision=? '
                        'AND stage_key=? AND attempt=?', (result.model_dump_json(), *key))
            con.execute('UPDATE ts_pipeline_processes SET revision=revision+1 WHERE process_id=?', (process_id,))
            return True
    return retry_on_locked(operation)


def process_for_job(db: ComputeDB, job_id: int) -> str | None:
    with db.connect() as con:
        row = con.execute('SELECT process_id FROM ts_pipeline_stages WHERE job_id=?', (job_id,)).fetchone()
    return row[0] if row else None


def list_unfinished_processes(db: ComputeDB, project_id: str) -> list[str]:
    with db.connect() as con:
        return [row[0] for row in con.execute("SELECT process_id FROM ts_pipeline_processes WHERE project_id=? "
                                             "AND status NOT IN ('completed','failed','cancelled') ORDER BY process_id",
                                             (project_id,)).fetchall()]


def transfer_process_ownership(db: ComputeDB, *, process_id: str, project_id: str, new_owner_session_id: str) -> None:
    """Transfer ownership of a process and its child tables to a successor session within the same project."""
    if not process_id:
        return
    with _rewrite_lock(db):
        _recover_source_rewrite(db, process_id)

        def operation():
            with db.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                row = con.execute('SELECT project_id,owner_id,record,payload FROM ts_pipeline_processes WHERE process_id=?',
                                  (process_id,)).fetchone()
                if row is None:
                    raise ValueError('process not found')
                if row[0] != project_id:
                    raise ValueError(f'TS process belongs to a different project ({row[0]})')
                if row[1] == new_owner_session_id:
                    return
                record_data = json.loads(row[2]) if row[2] else {}
                if record_data:
                    record_data['owner_session_id'] = new_owner_session_id
                    catalog_id = record_data.get('catalog_id')
                    if catalog_id:
                        con.execute('UPDATE conformer_catalogs SET owner_id=? WHERE catalog_id=? AND project_id=?',
                                    (new_owner_session_id, catalog_id, project_id))
                new_payload = row[3]
                if row[3]:
                    try:
                        p_data = json.loads(row[3])
                        p_data['owner_id'] = new_owner_session_id
                        new_payload = json.dumps(p_data)
                    except (ValueError, TypeError):
                        pass
                con.execute('UPDATE ts_pipeline_processes SET owner_id=?, record=?, payload=? WHERE process_id=?',
                            (new_owner_session_id, json.dumps(record_data) if record_data else None, new_payload, process_id))
                con.execute('UPDATE exploration_budgets SET owner_id=? WHERE process_id=? AND project_id=?',
                            (new_owner_session_id, process_id, project_id))

        return retry_on_locked(operation)


def save_process_record(db: ComputeDB, *, process_id: str, record: dict,
                        expected_revision: int | None = None) -> bool:
    from cloudra.tools.core.ts_process import TsProcessRecord
    state = TsProcessRecord.model_validate(record)
    if state.pipeline_id != process_id:
        raise ValueError('record process mismatch')
    status = 'stopped' if state.stop_reason else 'completed' if state.terminal == 'verified' else 'failed' if state.terminal else 'blocked' if state.blocked else 'waiting' if state.waiting_for else 'running'
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            scope = con.execute('SELECT project_id,owner_id,revision,declaration_revision FROM ts_pipeline_processes WHERE process_id=?',
                                (process_id,)).fetchone()
            if scope is None or scope[:2] != (state.owner_conversation_id, state.owner_session_id):
                raise ValueError('record owner mismatch')
            if state.declaration_revision != scope[3]:
                raise ValueError('stale record declaration revision')
            if expected_revision is not None and scope[2] != expected_revision:
                return False
            state.revision = scope[2] + 1
            con.execute('UPDATE ts_pipeline_processes SET record=?,status=?,revision=revision+1 WHERE process_id=?',
                        (state.model_dump_json(), status, process_id))
            return True
    return retry_on_locked(operation)


def verify_stage_input(db: ComputeDB, job_id: int) -> str | None:
    """Check bytes only; the compute execution core never parses QM input."""
    with db.connect() as con:
        row = con.execute('SELECT j.path,i.input_digest FROM ts_pipeline_stages s '
            'JOIN compute_jobs j ON j.id=s.job_id LEFT JOIN ts_pipeline_inputs i ON i.job_id=j.id '
            'WHERE s.job_id=?',(job_id,)).fetchone()
    if row is None:
        return None
    if row[1] is None:
        raise ValueError('stage input digest missing')
    digest = hashlib.sha256(Path(row[0]).read_bytes()).hexdigest()
    if digest != row[1]:
        raise ValueError('stage input bytes changed after binding')
    return digest


def atom_binding_for_log(db: ComputeDB, log_path: str | Path, workspace_dir: str | Path) -> dict | None:
    """Use only a completed job's frozen binding, never a current process record."""
    if not Path(db.path).is_file():
        return None
    from cloudra.infra.compute_utils import resolve_log_path

    path = Path(log_path).resolve()
    workspace = str(Path(workspace_dir).resolve())
    with db.connect() as con:
        rows = con.execute("SELECT j.id,j.path,j.jobtype,s.process_id,s.declaration_revision,s.evidence "
            "FROM ts_pipeline_stages s JOIN compute_jobs j ON j.id=s.job_id "
            "JOIN ts_pipeline_processes p ON p.process_id=s.process_id "
            "WHERE j.state='done' AND s.evidence IS NOT NULL AND json_extract(p.payload,'$.workspace_dir')=?",
            (workspace,)).fetchall()
    for job_id, input_path, engine, process_id, revision, raw in rows:
        if Path(resolve_log_path(input_path, engine, job_id)).resolve() != path:
            continue
        evidence = StageEvidence.model_validate_json(raw)
        binding = evidence.atom_binding
        if binding is None:
            return None
        if binding.get('process_id') != process_id or binding.get('declaration_revision') != revision:
            raise ValueError('Stage atom binding belongs to a different TS declaration.')
        if evidence.log_sha256 != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Native log changed after its concrete atom binding was recorded.')
        return binding
    return None
