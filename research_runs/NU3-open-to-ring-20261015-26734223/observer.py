"""Sample this research run every 30 seconds; never drive agents or calculations."""
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from cloudra.persistence.paths import compute_db_path, conversation_db_path, runtime_db_path

RUN = Path(__file__).resolve().parent
JOB_TERMINAL = {'done', 'failed', 'cancelled'}
AGENT_TERMINAL = {'succeeded', 'failed', 'cancelled'}
PUBLIC_EVENTS = (
    'agent.spawned', 'agent.state_changed', 'run.finished',
    'tool.requested', 'tool.finished', 'program.finished', 'agent.completion_gate',
)


def read_rows(path, sql, args=()):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(sql, args)]


def lock_held(path):
    # Same flock semantics as infra/flocks.py, without O_CREAT or directory writes.
    try:
        with path.open('rb') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
    except FileNotFoundError:
        return False
    return False


def sample(launch):
    runtime = RUN / 'runtime'
    project = launch['project_id']
    state = {'checked_at': datetime.now(timezone.utc).isoformat(), 'run_dir': str(RUN),
             'project_id': project, 'session_id': launch['session_id'], 'pid': launch['pid'],
             'scientific_completion': 'not_assessed', 'status': 'watching'}
    marks = ','.join('?' for _ in PUBLIC_EVENTS)
    rows = read_rows(runtime_db_path(runtime),
                     f'SELECT type,session_id,data,created_at FROM events WHERE project_id=? '
                     f'AND type IN ({marks}) ORDER BY rowid', (project, *PUBLIC_EVENTS))
    agents, recent = {}, []
    coordinator_gate = {}
    for row in rows:
        payload = json.loads(row['data'])
        session = row['session_id']
        kind = row['type']
        if kind == 'agent.spawned':
            agents[session] = {'role_id': payload['role_id'], 'state': payload['state']}
        elif kind == 'agent.state_changed':
            agents.setdefault(session, {})['state'] = payload['to']
        if kind == 'agent.completion_gate' and session == launch['session_id']:
            coordinator_gate = {key: payload.get(key) for key in ('action', 'source', 'basis', 'request_id')}
        recent.append({'event': kind, 'session_id': session, 'at': row['created_at'],
                       **{key: payload[key] for key in ('tool_name', 'status', 'outcome', 'action')
                          if key in payload}})
    state.update(agents=agents, event_counts=dict(Counter(row['type'] for row in rows)),
                 recent_events=recent[-20:])
    jobs = read_rows(compute_db_path(runtime),
                     'SELECT id,session_id,state,path,node_id,notified_at FROM compute_jobs '
                     'WHERE conversation_id=? ORDER BY id', (project,)) if compute_db_path(runtime).exists() else []
    for job in jobs:
        # compute_utils lock paths are .cloudra/{calc,guard}-{id}.lock; its helpers
        # mkdir the directory, so this read-only observer only constructs the paths.
        directory = Path(job['path']).parent / '.cloudra'
        job['locks'] = {kind: lock_held(directory / f'{kind}-{job["id"]}.lock')
                        for kind in ('calc', 'guard')}
    pending_compute = [job['id'] for job in jobs
                       if job['state'] in JOB_TERMINAL and job['notified_at'] is None]
    dag_path = conversation_db_path(project, runtime)
    pending_review = []
    if dag_path.exists():
        tables = read_rows(dag_path, "SELECT name FROM sqlite_master WHERE type='table'")
        if any(row['name'] == 'dag_review_notifications' for row in tables):
            pending_review = read_rows(dag_path,
                                      "SELECT notification_id,kind,state FROM dag_review_notifications "
                                      "WHERE state='pending'")
    state.update(compute_jobs=jobs, pending_compute_notifications=pending_compute,
                 pending_review_notifications=pending_review)
    notes = RUN / 'workspace' / 'PROCESS.md'
    if notes.is_file():
        data = notes.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        archive = RUN / 'diagnosis' / 'process-notes'
        archive.mkdir(parents=True, exist_ok=True)
        target = archive / f'{digest}.md'
        if not target.exists():
            target.write_bytes(data)
        state['process_notes'] = {'sha256': digest, 'bytes': len(data), 'snapshot': str(target)}
    state['coordinator_completion_gate'] = coordinator_gate
    state['nonterminal_agents'] = [session for session, agent in agents.items()
                                   if agent.get('state') not in AGENT_TERMINAL]
    # A succeeded run may only have parked the Coordinator while children/reviews
    # finish; do not exit in the gap before its delivery continuation wakes.
    coordinator_parked = (
        agents.get(launch['session_id'], {}).get('state') == 'succeeded'
        and coordinator_gate.get('action') in {'wait_background', 'wait_review'}
    )
    state['runtime_finished'] = (
        agents.get(launch['session_id'], {}).get('state') in AGENT_TERMINAL
        and not state['nonterminal_agents'] and not coordinator_parked
        and all(job['state'] in JOB_TERMINAL and not any(job['locks'].values()) for job in jobs)
        and not pending_compute and pending_review == []
    )
    if state['runtime_finished']:
        state['status'] = 'runtime_finished'
    return state


def main():
    launch = json.loads((RUN / 'launch.json').read_text())
    while True:
        try:
            state = sample(launch)
        except Exception as exc:
            state = {'checked_at': datetime.now(timezone.utc).isoformat(),
                     'status': 'observer_error', 'error': str(exc), 'runtime_finished': False}
        temporary = RUN / 'latest-status.tmp'
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(RUN / 'latest-status.json')
        with (RUN / 'observations.jsonl').open('a') as output:
            output.write(json.dumps(state, ensure_ascii=False) + '\n')
        if state['runtime_finished']:
            return
        time.sleep(30)


if __name__ == '__main__':
    main()
