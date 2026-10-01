"""Atomic reservations for new exploration actions; never controls engine lifetime.

Existing-job association is accounting only. New TS job creation requires the
TS pipeline's shared stage transaction adapter.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import Field

from cloudra.persistence.database import ComputeDB, retry_on_locked
from cloudra.tools.core.conformer_catalog import CatalogModel, content_digest


class ExplorationBudget(CatalogModel):
    source: str = Field(min_length=1)
    max_compute_actions: int | None = Field(default=None, ge=0)
    estimated_cpu_hours: float | None = Field(default=None, ge=0)
    max_model_calls: int | None = Field(default=None, ge=0)


class CostEstimate(CatalogModel):
    action_key: str = Field(min_length=1)
    action_kind: Literal['optimization', 'gradient', 'path', 'ts', 'frequency', 'irc', 'endpoint', 'sampling', 'model']
    cpu_hours: float | None = Field(default=None, ge=0)
    source: str = Field(min_length=1)
    uncertainty: str = 'unspecified'
    model_cost: float | None = Field(default=None, ge=0)


class Reservation(CatalogModel):
    reservation_id: str
    process_id: str
    decision_id: str
    action_keys: list[str]


class ActualCost(CatalogModel):
    job_id: int | None = None
    terminal_state: Literal['done', 'failed', 'cancelled']
    allocated_cpu_hours: float | None = Field(default=None, ge=0)
    measurement_source: str
    model_calls: int | None = Field(default=None, ge=0)
    model_tokens: int | None = Field(default=None, ge=0)
    monetary_cost: float | None = Field(default=None, ge=0)


class BudgetUsage(CatalogModel):
    compute_actions: int
    model_calls: int
    cpu_hours: float
    unknown_cpu_actions: int


def configure_budget(db: ComputeDB, *, process_id: str, project_id: str, owner_id: str,
                     budget: ExplorationBudget) -> None:
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT project_id,owner_id,payload FROM exploration_budgets WHERE process_id=?',
                              (process_id,)).fetchone()
            values = (project_id, owner_id, budget.model_dump_json())
            if row and row != values:
                raise ValueError('budget configuration conflict; explicit revision required')
            con.execute('INSERT OR IGNORE INTO exploration_budgets VALUES (?,?,?,?)', (process_id, *values))
    retry_on_locked(operation)


def _usage(con, process_id: str) -> BudgetUsage:
    rows = con.execute('SELECT a.estimate,a.actual,a.job_id,j.state FROM exploration_actions a '
                       'LEFT JOIN compute_jobs j ON j.id=a.job_id LEFT JOIN exploration_released_actions r '
                       'ON r.process_id=a.process_id AND r.action_key=a.action_key '
                       'WHERE a.process_id=? AND r.action_key IS NULL', (process_id,)).fetchall()
    compute, models, cpu, unknown = 0, 0, 0., 0
    for estimate_text, actual_text, job_id, job_state in rows:
        estimate = CostEstimate.model_validate_json(estimate_text)
        actual = ActualCost.model_validate_json(actual_text) if actual_text else None
        if estimate.action_kind == 'model':
            models += max(1, actual.model_calls or 0) if actual else 1
        else:
            compute += 1
            if job_id is not None and (actual is None or job_state != actual.terminal_state):
                amount = estimate.cpu_hours
                if amount is not None and actual and actual.allocated_cpu_hours is not None:
                    amount = max(amount, actual.allocated_cpu_hours)
            else:
                amount = actual.allocated_cpu_hours if actual and actual.allocated_cpu_hours is not None else estimate.cpu_hours
            if amount is None:
                unknown += 1
            else:
                cpu += amount
    return BudgetUsage(compute_actions=compute,model_calls=models,cpu_hours=cpu,unknown_cpu_actions=unknown)


def budget_usage(db: ComputeDB, process_id: str) -> BudgetUsage:
    with db.connect() as con:
        return _usage(con,process_id)


def reserve_actions(db: ComputeDB, *, process_id: str, decision_id: str,
                    estimates: list[CostEstimate]) -> Reservation:
    if not estimates or len({e.action_key for e in estimates}) != len(estimates):
        raise ValueError('nonempty unique action keys required')
    payload = json.dumps([e.model_dump() for e in estimates],sort_keys=True)
    reservation = Reservation(reservation_id=content_digest([process_id,decision_id]),process_id=process_id,
                              decision_id=decision_id,action_keys=[e.action_key for e in estimates])
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT payload FROM exploration_reservations WHERE reservation_id=?',
                              (reservation.reservation_id,)).fetchone()
            if old:
                if old[0] != payload:
                    raise ValueError('decision reservation conflict')
                released = con.execute(
                    'SELECT 1 FROM exploration_released_actions r '
                    'JOIN exploration_actions a ON a.process_id=r.process_id '
                    'AND a.action_key=r.action_key WHERE a.reservation_id=? LIMIT 1',
                    (reservation.reservation_id,),
                ).fetchone()
                if released:
                    raise ValueError('decision reservation has been released')
                return reservation
            configured = con.execute('SELECT payload FROM exploration_budgets WHERE process_id=?',(process_id,)).fetchone()
            if configured is None:
                raise ValueError('budget scope must be configured explicitly')
            budget = ExplorationBudget.model_validate_json(configured[0])
            usage = _usage(con,process_id)
            new_compute = sum(e.action_kind != 'model' for e in estimates)
            new_models = len(estimates)-new_compute
            unknown = usage.unknown_cpu_actions + sum(e.cpu_hours is None for e in estimates if e.action_kind != 'model')
            cpu = usage.cpu_hours + sum(e.cpu_hours or 0 for e in estimates if e.action_kind != 'model')
            if budget.estimated_cpu_hours is not None and unknown:
                raise ValueError('unknown CPU estimate under configured cap')
            if ((budget.max_compute_actions is not None and usage.compute_actions+new_compute > budget.max_compute_actions)
                or (budget.max_model_calls is not None and usage.model_calls+new_models > budget.max_model_calls)
                or (budget.estimated_cpu_hours is not None and cpu > budget.estimated_cpu_hours)):
                raise ValueError('exploration budget exhausted')
            con.execute('INSERT INTO exploration_reservations VALUES (?,?,?,?)',
                        (reservation.reservation_id,process_id,decision_id,payload))
            for estimate in estimates:
                con.execute('INSERT INTO exploration_actions VALUES (?,?,?,?,NULL,NULL)',
                            (process_id,estimate.action_key,reservation.reservation_id,estimate.model_dump_json()))
            return reservation
    return retry_on_locked(operation)


def attach_existing_job(db: ComputeDB, reservation_id: str, action_key: str, job_id: int) -> None:
    """Associate an already admitted job. This cannot create or resubmit a job."""
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            scope = con.execute('SELECT b.project_id,b.owner_id,a.job_id,a.actual FROM exploration_actions a '
                                'JOIN exploration_budgets b ON b.process_id=a.process_id '
                                'WHERE a.reservation_id=? AND a.action_key=?',(reservation_id,action_key)).fetchone()
            job = con.execute('SELECT conversation_id,session_id FROM compute_jobs WHERE id=?',(job_id,)).fetchone()
            if scope is None or job != scope[:2]:
                raise ValueError('existing job ownership mismatch')
            released = con.execute('SELECT 1 FROM exploration_released_actions r JOIN exploration_actions a '
                                   'ON r.process_id=a.process_id AND r.action_key=a.action_key '
                                   'WHERE a.reservation_id=? AND a.action_key=?', (reservation_id,action_key)).fetchone()
            if released:
                raise ValueError('action has been released')
            if scope[3] is not None and scope[2] != job_id:
                raise ValueError('cannot bind another job to a settled action')
            if scope[2] is not None and scope[2] != job_id:
                raise ValueError('action already bound to another job')
            other = con.execute('SELECT reservation_id,action_key FROM exploration_actions WHERE job_id=?',(job_id,)).fetchone()
            if other and other != (reservation_id,action_key):
                raise ValueError('existing job already accounted')
            con.execute('UPDATE exploration_actions SET job_id=? WHERE reservation_id=? AND action_key=?',
                        (job_id,reservation_id,action_key))
    retry_on_locked(operation)


def bind_reserved_job(db: ComputeDB, *, reservation_id: str, action_key: str, stage_job_payload: dict) -> int:
    from cloudra.services.ts_pipeline_store import StageBindingRequest, bind_stage_job
    request = StageBindingRequest.model_validate(stage_job_payload)
    return bind_stage_job(db, **request.model_dump(), reservation_id=reservation_id, action_key=action_key)


def settle_action(db: ComputeDB, *, process_id: str, action_key: str, actual: ActualCost) -> None:
    def operation():
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT job_id,actual FROM exploration_actions WHERE process_id=? AND action_key=?',
                              (process_id,action_key)).fetchone()
            if row is None or (actual.job_id is not None and actual.job_id != row[0]):
                raise ValueError('action/job missing or mismatched')
            if row[0] is not None:
                if actual.job_id != row[0]:
                    raise ValueError('bound action requires actual job ID')
                job = con.execute('SELECT state FROM compute_jobs WHERE id=?', (row[0],)).fetchone()
                if job is None or job[0] != actual.terminal_state:
                    raise ValueError('authoritative job terminal state mismatches settlement')
            if row[1] and row[1] != actual.model_dump_json():
                raise ValueError('actual cost immutable conflict')
            con.execute('UPDATE exploration_actions SET actual=? WHERE process_id=? AND action_key=?',
                        (actual.model_dump_json(),process_id,action_key))
    retry_on_locked(operation)


def reconcile_reservations(db: ComputeDB, process_id: str) -> None:
    """Check bindings; never expire reservations or cancel active compute jobs."""
    with db.connect() as con:
        rows = con.execute('SELECT a.job_id,j.id FROM exploration_actions a LEFT JOIN compute_jobs j ON a.job_id=j.id '
                           'WHERE a.process_id=? AND a.job_id IS NOT NULL',(process_id,)).fetchall()
        if any(job is None for _,job in rows):
            raise ValueError('bound compute job missing; accounting requires reconciliation')


def release_unbound_actions(db: ComputeDB, *, process_id: str, action_keys: list[str], reason: str) -> list[str]:
    """Append release evidence for unused future work; bound jobs are untouched."""
    if not reason.strip():
        raise ValueError('release reason required')
    def operation():
        released=[]
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            for key in sorted(set(action_keys)):
                row=con.execute('SELECT job_id,actual FROM exploration_actions WHERE process_id=? AND action_key=?',(process_id,key)).fetchone()
                if row is None:
                    raise ValueError('release action missing')
                if row != (None,None):
                    continue
                con.execute('INSERT OR IGNORE INTO exploration_released_actions VALUES (?,?,?)',(process_id,key,reason))
                released.append(key)
        return released
    return retry_on_locked(operation)


def settle_process_jobs(db: ComputeDB, process_id: str) -> None:
    """Reconcile actual allocation costs from authoritative terminal job rows."""
    with db.connect() as con:
        rows = con.execute('SELECT a.action_key,j.id,j.state,j.req_cpus,j.start_timestamp,j.end_timestamp '
                           'FROM exploration_actions a JOIN compute_jobs j ON j.id=a.job_id '
                           'WHERE a.process_id=? AND a.actual IS NULL AND j.state IN (?,?,?)',
                           (process_id,'done','failed','cancelled')).fetchall()
    for key, job_id, state, cpus, start, end in rows:
        measured = cpus is not None and cpus > 0 and start is not None and start > 0 and end is not None and end >= start
        settle_action(db, action_key=key, process_id=process_id, actual=ActualCost(job_id=job_id,
            terminal_state=state, allocated_cpu_hours=cpus*(end-start)/3600 if measured else None,
            measurement_source='allocated_cpus_times_ledger_runtime' if measured else 'runtime_or_allocation_unavailable'))
