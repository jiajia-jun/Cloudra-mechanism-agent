"""System-owned TS progression; no LLM calls and no second computation queue."""
from __future__ import annotations

import os

from cloudra.infra.flocks import locked
from cloudra.persistence.database import ComputeDB
from cloudra.services.ts_pipeline_context import use_pipeline_database
from cloudra.services.ts_pipeline_store import get_process, list_unfinished_processes, process_for_job


def advance_process(db: ComputeDB, process_id: str) -> dict:
    from cloudra.tools.core.ts_process import TsProcessRecord, advance, save_record
    state = get_process(db, process_id)
    if state is None or state['record'] is None:
        raise ValueError('process checkpoint missing')
    if state['record'].get('format_version') != 6:
        return dict(state, status='isolated', isolation_reason='Unsupported TS input format; existing jobs remain intact')
    directory = state['record']['run_dir']
    os.makedirs(directory, exist_ok=True)
    with locked(os.path.join(directory, '.pipeline.lock')), use_pipeline_database(db):
        state = get_process(db, process_id)
        record = TsProcessRecord.model_validate(state['record'])
        from cloudra.services.exploration_budget_store import settle_process_jobs
        settle_process_jobs(db, process_id)
        if record.is_terminal or record.blocked:
            return state
        if record.waiting_for:
            from cloudra.services.compute_store import TERMINAL_STATES
            token = record.waiting_for.partition(':')
            if token[0] != 'job' or not token[2].isdigit():
                raise ValueError('invalid waiting job reference')
            with db.connect() as con:
                job = con.execute('SELECT state FROM compute_jobs WHERE id=?', (int(token[2]),)).fetchone()
            if job is None:
                raise ValueError('bound waiting job missing')
            if job[0] not in TERMINAL_STATES:
                return state
            from pathlib import Path

            from cloudra.services.ts_pipeline_store import commit_stage_result, verify_stage_input
            try:
                digest=verify_stage_input(db,int(token[2]))
            except (OSError,ValueError) as exc:
                from cloudra.tools.core.ts_process import _block
                record=_block(record,record.stage,'stage_input_changed',str(exc),needs=['compute_artifacts'])
                save_record(record)
                return get_process(db,process_id)
            with db.connect() as con:
                binding=con.execute('SELECT declaration_revision,stage_key,attempt,evidence FROM ts_pipeline_stages WHERE job_id=?',(int(token[2]),)).fetchone()
                path=con.execute('SELECT path FROM compute_jobs WHERE id=?',(int(token[2]),)).fetchone()[0]
            if binding and binding[0]==record.declaration_revision and binding[3] is None:
                artifacts=[path]
                helper_result=str(Path(path).with_suffix('.chem-result.json'))
                if Path(helper_result).is_file():
                    artifacts.append(helper_result)
                state=get_process(db,process_id)
                committed=commit_stage_result(db,process_id=process_id,expected_revision=state['revision'],
                    stage_key=binding[1],attempt=binding[2],evidence=dict(status='done' if job[0]=='done' else 'failed',
                        artifacts=artifacts,input_hash=digest or '',detail='Authoritative execution state: '+job[0]+'. Scientific qualification is a separate stage.'))
                if not committed:
                    raise ValueError('stage result checkpoint changed concurrently')
            record.waiting_for = ''
        record = advance(record)
        save_record(record)
        return get_process(db, process_id)


def handle_process_job_terminal(db: ComputeDB, job_id: int) -> dict | None:
    process = process_for_job(db, job_id)
    return advance_process(db, process) if process else None


def reconcile_processes(db: ComputeDB, project_id: str) -> list[dict]:
    return [advance_process(db, pid) for pid in list_unfinished_processes(db, project_id)
            if get_process(db,pid)['record'] is not None]
