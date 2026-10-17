"""Launch one authorized standalone research project on the frozen runtime."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import socket
import subprocess
import time
import urllib.request

RUN = Path(__file__).parent.resolve()
META = json.loads((RUN / 'provenance.json').read_text())
SOURCE = Path(META['source_worktree'])
PYTHON = '/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/.venv/bin/python'


def save(name, value):
    (RUN / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    if (RUN / 'launch.json').exists():
        raise SystemExit('Already launched; use the saved launch record.')
    for port in (8915, 8015):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip()
    assert actual == META['source_commit']
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=SOURCE, text=True).strip()
    env = dict(os.environ, PYTHONPATH=str(SOURCE), PYTHONDONTWRITEBYTECODE='1',
               CLOUDRA_CONFIG_FILE=META['config_copy'], CLOUDRA_DATA_DIR=META['data_dir'],
               CLOUDRA_RUNTIME_STORE=str(RUN / 'runtime/runtime-v2.db'),
               CLOUDRA_API_BIND_HOST='127.0.0.1')
    env.pop('CLOUDRA_API_TOKEN', None)
    command = [PYTHON, '-u', '-m', 'uvicorn', 'cloudra.services.api_v2:create_default_v2_app',
               '--factory', '--host', '127.0.0.1', '--port', '8915', '--log-level', 'warning']
    with (RUN / 'runtime.log').open('ab') as output:
        worker = subprocess.Popen(command, cwd=SOURCE, env=env, stdout=output,
                                  stderr=subprocess.STDOUT, start_new_session=True)
    launch = {'pid': worker.pid, 'command': command, 'run_dir': str(RUN),
              'source_worktree': str(SOURCE), 'source_commit': actual,
              'launched_at': datetime.now(ZoneInfo('Asia/Singapore')).isoformat(),
              'api_url': META['api_url'], 'viewer_url': META['viewer_url'],
              'kind': 'standalone_research_followup', 'benchmark': False}
    save('launch.json', launch)
    for _ in range(40):
        try:
            with urllib.request.urlopen(META['api_url'] + '/api/v2/runtime/health', timeout=2):
                break
        except OSError:
            if worker.poll() is not None:
                raise RuntimeError('New research runtime exited; see runtime.log')
            time.sleep(0.5)
    else:
        raise RuntimeError('Runtime health not ready; inspect saved process, do not relaunch.')
    token = (RUN / 'runtime/.api_token').read_text().strip()

    def post(path, body, filename):
        request = urllib.request.Request(META['api_url'] + path,
                    data=json.dumps(body).encode(), method='POST',
                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        save(filename, result)
        return result['data']

    project = post('/api/v2/projects', {
        'name': 'NU3 开链到四元环独立验证', 'workspace_dir': META['workspace'],
        'settings': {'orchestration_mode': 'dag_guided',
                     'defaults': {'clean_context': True, 'unattended': True, 'yolo': True}},
    }, 'project-created.json')
    launch['project_id'] = project['id']
    save('launch.json', launch)
    agent = post('/api/v2/projects/' + project['id'] + '/agents', {
        'role_id': 'coordinator', 'query': (RUN / 'query.txt').read_text(), 'language': 'zh',
    }, 'agent-created.json')
    launch['session_id'] = agent['id']
    save('launch.json', launch)
    for filename, key in [('observer.py', 'observer_pid'), ('viewer.py', 'viewer_pid')]:
        with (RUN / filename.replace('.py', '.log')).open('ab') as output:
            process = subprocess.Popen([PYTHON, '-u', str(RUN / filename)], cwd=SOURCE,
                       env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        launch[key] = process.pid
        save('launch.json', launch)
    save('provenance.json', dict(META, launch_state='started', project_id=project['id'],
                                session_id=agent['id'], started_at=launch['launched_at']))
    print(json.dumps({key: launch[key] for key in ('pid', 'project_id', 'session_id',
        'observer_pid', 'viewer_pid', 'viewer_url')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
