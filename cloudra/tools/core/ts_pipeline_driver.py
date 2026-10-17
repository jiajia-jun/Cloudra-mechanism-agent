"""System-owned TS progression; no LLM calls and no second computation queue."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from cloudra.infra.flocks import locked
from cloudra.persistence.database import ComputeDB
from cloudra.services.ts_pipeline_context import use_pipeline_database
from cloudra.services.ts_pipeline_store import get_process, process_for_job

logger = logging.getLogger(__name__)


def advance_process(db: ComputeDB, process_id: str) -> dict:
    from cloudra.tools.core.ts_process import TsProcessRecord, advance, save_record
    state = get_process(db, process_id)
    if state is None or state['record'] is None:
        raise ValueError('process checkpoint missing')
    if state['record'].get('format_version') != 7:
        return dict(state, status='isolated', isolation_reason='Unsupported TS input format; existing jobs remain intact')
    directory = state['record']['run_dir']
    os.makedirs(directory, exist_ok=True)
    with locked(os.path.join(directory, '.pipeline.lock')), use_pipeline_database(db):
        state = get_process(db, process_id)
        record = TsProcessRecord.model_validate(state['record'])
        from cloudra.services.exploration_budget_store import settle_process_jobs
        settle_process_jobs(db, process_id)
        if record.is_terminal or (record.blocked and not record.stop_reason):
            return state
        if record.stop_reason and not record.waiting_for:
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
                path, engine=con.execute('SELECT path,jobtype FROM compute_jobs WHERE id=?',(int(token[2]),)).fetchone()
            if binding and binding[3] is None:
                artifacts=[path]
                helper_result=str(Path(path).with_suffix('.chem-result.json'))
                if Path(helper_result).is_file():
                    artifacts.append(helper_result)
                state=get_process(db,process_id)
                import hashlib
                from copy import deepcopy

                from cloudra.infra.compute_utils import resolve_log_path
                log_path = Path(resolve_log_path(path, engine, int(token[2])))
                log_digest = hashlib.sha256(log_path.read_bytes()).hexdigest() if log_path.is_file() else None
                frozen_binding = None
                if binding[1] in {'ts_opt', 'frequency', 'irc'} and log_path.is_file():
                    bound_step = next((step for step in record.job_steps if step.job_id == int(token[2])), None)
                    frozen_binding = deepcopy(bound_step.atom_binding) if bound_step else None
                    if frozen_binding:
                        frozen_binding['declaration_revision'] = binding[0]
                        # 频率提交时日志尚不存在；完成后只补日志指纹，不重建已冻结的分子/映射。
                        if binding[1] == 'frequency':
                            frozen_binding['ts_log_sha256'] = log_digest
                committed=commit_stage_result(db,process_id=process_id,expected_revision=state['revision'],
                    stage_key=binding[1],attempt=binding[2],declaration_revision=binding[0],evidence=dict(status=job[0],
                        artifacts=artifacts,input_hash=digest or '',detail='Authoritative execution state: '+job[0]+'. Scientific qualification is a separate stage.',
                        atom_binding=frozen_binding, log_sha256=log_digest if frozen_binding else None))
                if not committed:
                    raise ValueError('stage result checkpoint changed concurrently')
            for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]:
                if step.job_id == int(token[2]):
                    step.state = job[0]
            record.waiting_for = ''
        record = advance(record)
        save_record(record)
        return get_process(db, process_id)


def handle_process_job_terminal(db: ComputeDB, job_id: int) -> dict | None:
    process = process_for_job(db, job_id)
    return advance_process(db, process) if process else None


def recover_project_jobs(db: ComputeDB, project_id: str, workspace_dir: str) -> None:
    """Recover file references once on project load; never enumerate pipeline rows."""
    from cloudra.tools.core.ts_process import PROCESS_JSON_NAME, TS_ROOT_NAME

    for path in (Path(workspace_dir) / TS_ROOT_NAME).glob(f'*/{PROCESS_JSON_NAME}'):
        try:
            reference = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(reference, dict):
                raise ValueError('TS recovery reference must be a JSON object')
            process_id = reference.get('pipeline_id')
        except (OSError, ValueError):
            logger.warning('Could not read TS recovery reference %s', path, exc_info=True)
            continue
        if not isinstance(process_id, str) or not process_id:
            continue
        # 导出文件只提供稳定编号；当前进度和等待对象始终按主键读权威账本。
        state = get_process(db, process_id)
        if state is None or state['payload']['project_id'] != project_id:
            continue
        record = state['record'] or {}
        if record.get('format_version') != 7 or record.get('terminal') or record.get('blocked'):
            continue
        token = record.get('waiting_for', '').partition(':')
        if token[0] != 'job' or not token[2].isdigit():
            continue
        with db.connect() as con:
            # 定点重挂既有通知队列；推进或通知失败、乃至重启，都沿原有机制重试。
            con.execute("UPDATE compute_jobs SET notified_at=NULL WHERE id=? AND conversation_id=? "
                        "AND state IN ('done','failed','cancelled') AND notified_at IS NOT NULL",
                        (int(token[2]), project_id))
