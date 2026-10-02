"""Durable TS processes and stage bindings in the existing compute ledger."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from cloudra.persistence.database import ComputeDB, retry_on_locked
from cloudra.services.exploration_budget_store import ExplorationBudget
from cloudra.tools.core.conformer_catalog import CatalogModel, content_digest
from cloudra.tools.core.ts_inputs import TsInput, TsRecovery, TsResumeRequest


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
    recovery: TsRecovery | None = None
    released_action_keys: list[str] = Field(default_factory=list)
    status: Literal['accepted'] = 'accepted'


def revision_request_digest(request: TsResumeRequest) -> str:
    return content_digest(request.model_dump(mode='json', exclude_unset=True))


def get_revision_receipt(db: ComputeDB, *, process_id: str, request_key: str) -> TsRevisionReceipt | None:
    with db.connect() as con:
        row = con.execute('SELECT payload FROM ts_pipeline_revision_receipts WHERE process_id=? AND request_key=?',
                          (process_id, request_key)).fetchone()
    return TsRevisionReceipt.model_validate_json(row[0]) if row else None


def commit_input_revision(db: ComputeDB, *, process_id: str, request: TsResumeRequest,
                          record: dict, receipt: TsRevisionReceipt) -> TsRevisionReceipt:
    """Accept once, before any new work, without modifying historical jobs."""
    digest = revision_request_digest(request)

    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT payload FROM ts_pipeline_revision_receipts WHERE process_id=? AND request_key=?',
                              (process_id, request.request_key)).fetchone()
            # A response-loss replay is legal even after the run has advanced.
            if old:
                accepted = TsRevisionReceipt.model_validate_json(old[0])
                if accepted.request_digest != digest:
                    raise ValueError('revision request key conflict')
                return accepted
            scope = con.execute('SELECT project_id,owner_id,revision,declaration_revision FROM ts_pipeline_processes '
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
                                 "WHERE s.process_id=? AND j.state NOT IN ('done','failed','cancelled') LIMIT 1",
                                 (process_id,)).fetchone()
            if active:
                raise ValueError('active stage job prevents input revision')
            value = TsInput.model_validate(record['input'])
            from cloudra.tools.core.ts_inputs import apply_input_changes
            from cloudra.tools.core.ts_process import TsProcessRecord
            prior_input = con.execute('SELECT payload FROM ts_pipeline_declarations WHERE process_id=? AND declaration_revision=?',
                                      (process_id, scope[3])).fetchone()
            expected_input = apply_input_changes(TsInput.model_validate_json(prior_input[0]), request.changes)
            if value != expected_input:
                raise ValueError('revision input differs from the accepted request')
            validated_record = TsProcessRecord.model_validate(record)
            validated_record.revision = receipt.revision
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
            limits = value.execution.limits
            if limits:
                budget = ExplorationBudget(source=limits.source, max_compute_actions=limits.max_compute_actions,
                                           max_model_calls=limits.max_model_calls)
                old_budget = con.execute('SELECT payload FROM exploration_budgets WHERE process_id=?', (process_id,)).fetchone()
                if old_budget:
                    previous = ExplorationBudget.model_validate_json(old_budget[0])
                    if previous.source != budget.source:
                        raise ValueError('budget source mismatch')
                    for field in ('max_compute_actions', 'max_model_calls'):
                        before, after = getattr(previous, field), getattr(budget, field)
                        if before is not None and (after is None or after > before):
                            raise ValueError('revision cannot raise an authorized hard budget')
                con.execute('INSERT INTO exploration_budgets VALUES (?,?,?,?) ON CONFLICT(process_id) '
                            'DO UPDATE SET payload=excluded.payload', (process_id, *scope[:2], budget.model_dump_json()))
            elif con.execute('SELECT 1 FROM exploration_budgets WHERE process_id=?', (process_id,)).fetchone():
                raise ValueError('revision cannot remove an authorized hard budget')
            status = 'blocked' if record.get('blocked') else 'waiting' if record.get('waiting_for') else 'running'
            con.execute('INSERT INTO ts_pipeline_declarations VALUES (?,?,?)',
                        (process_id, receipt.input_revision, value.model_dump_json()))
            con.execute('UPDATE ts_pipeline_processes SET declaration_revision=?,revision=?,record=?,status=? WHERE process_id=?',
                        (receipt.input_revision, receipt.revision, json.dumps(accepted_record, sort_keys=True), status, process_id))
            for key in receipt.released_action_keys:
                con.execute('INSERT OR IGNORE INTO exploration_released_actions SELECT process_id,action_key,? '
                            'FROM exploration_actions WHERE process_id=? AND action_key=? AND job_id IS NULL AND actual IS NULL',
                            ('input revised', process_id, key))
            con.execute('INSERT INTO ts_pipeline_revision_receipts VALUES (?,?,?)',
                        (process_id, request.request_key, receipt.model_dump_json()))
            return receipt
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
    status: Literal['done', 'failed', 'blocked']
    artifacts: list[str]
    input_hash: str
    detail: str = ''


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
    with db.connect() as con:
        row = con.execute('SELECT process_id,payload,declaration_revision,revision,status,record '
                          'FROM ts_pipeline_processes WHERE process_id=?', (process_id,)).fetchone()
    if row is None:
        return None
    return dict(process_id=row[0], payload=json.loads(row[1]), declaration_revision=row[2], revision=row[3],
                status=row[4], record=json.loads(row[5]) if row[5] else None)


def read_process_snapshot(db: ComputeDB, *, project_id: str, run_id: str, workspace_dir: str) -> tuple[dict, list[dict]]:
    """Read process and jobs in one snapshot; ownership restricts writes, not project reads."""
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
                           's.declaration_revision,s.attempt,s.evidence FROM ts_pipeline_stages s '
                           'JOIN compute_jobs j ON j.id=s.job_id WHERE s.process_id=? ORDER BY j.id', (row[0],)).fetchall()
        keys = ('job_id', 'purpose', 'state', 'req_cpus', 'req_memory_mb', 'start_timestamp', 'end_timestamp',
                'source_input_revision', 'attempt', 'evidence')
        jobs = [dict(zip(keys, values, strict=True)) for values in rows]
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
            scope = con.execute('SELECT project_id,owner_id,declaration_revision FROM ts_pipeline_processes '
                                'WHERE process_id=?', (process_id,)).fetchone()
            if scope is None or scope[:2] != (job.conversation_id, job.session_id):
                raise ValueError('stage job owner mismatch')
            if scope[2] != declaration_revision:
                raise ValueError('stale declaration revision')
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
                        attempt: int, evidence: dict) -> bool:
    result = StageEvidence.model_validate(evidence)
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT declaration_revision,revision FROM ts_pipeline_processes WHERE process_id=?',
                              (process_id,)).fetchone()
            if row is None or row[1] != expected_revision:
                return False
            key = (process_id, row[0], stage_key, attempt)
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


def save_process_record(db: ComputeDB, *, process_id: str, record: dict,
                        expected_revision: int | None = None) -> bool:
    from cloudra.tools.core.ts_process import TsProcessRecord
    state = TsProcessRecord.model_validate(record)
    if state.pipeline_id != process_id:
        raise ValueError('record process mismatch')
    status = 'completed' if state.terminal == 'verified' else 'failed' if state.terminal else 'blocked' if state.blocked else 'waiting' if state.waiting_for else 'running'
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
