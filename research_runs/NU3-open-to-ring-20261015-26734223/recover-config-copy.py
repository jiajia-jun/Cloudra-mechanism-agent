"""Correct the local YAML copy format before the first scientific turn."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import urllib.request
import yaml

from cloudra.infra.config import CloudraConfig, _model_to_yaml_data, get_config

RUN = Path(__file__).parent.resolve()
meta = json.loads((RUN / 'provenance.json').read_text())
launch = json.loads((RUN / 'launch.json').read_text())
status = json.loads((RUN / 'latest-status.json').read_text())
assert status['runtime_finished'] and not status['compute_jobs']
with sqlite3.connect((RUN / 'runtime/compute.db').as_uri() + '?mode=ro', uri=True) as db:
    assert db.execute('SELECT count(*) FROM compute_jobs').fetchone()[0] == 0
cfg = get_config()
isolated = _model_to_yaml_data(cfg)
isolated['data_dir'] = meta['data_dir']
private = Path(meta['config_copy'])
private.write_text(yaml.safe_dump(isolated, allow_unicode=True))
os.chmod(private, 0o600)
verified = CloudraConfig(config_file=private)
assert verified.data_dir == Path(meta['data_dir'])
for role in ('coordinator', 'follower'):
    assert getattr(verified, role) == getattr(cfg, role)
token = (RUN / 'runtime/.api_token').read_text().strip()


def request(path, method, body):
    req = urllib.request.Request(meta['api_url'] + path,
            data=json.dumps(body).encode(), method=method,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


# Existing no-op configuration patch reloads the corrected YAML in place.
# No API, scheduler, guard or QM process is restarted or signalled.
live = request('/api/v2/runtime/config', 'PATCH', {'slot': 'coordinator', 'changes': {}})
report = {
    'at': datetime.now(timezone.utc).isoformat(),
    'cause': 'The launch helper wrote Pydantic internal top-level coordinator/follower fields; the YAML loader expects llm.coordinator/follower. Thus its first requests lacked the inherited authentication configuration.',
    'scope': 'Local isolated launch helper, not a frozen production source defect or scientific failure.',
    'first_attempt': status, 'calculations_submitted_before_recovery': 0,
    'recovery': 'Use the existing single YAML serializer and existing runtime configuration reload; retry the failed first Coordinator run once.',
    'configuration_equal_to_original': True,
    'frozen_source_changed': False, 'processes_restarted': [],
}
(RUN / 'diagnosis/config-copy-startup-recovery.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
result = request('/api/v2/agents/' + launch['session_id'] + '/restart', 'POST',
                 {'message': (RUN / 'query.txt').read_text()})
(RUN / 'agent-restarted.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
old_observer = launch['observer_pid']
env = dict(os.environ, PYTHONPATH=meta['source_worktree'], PYTHONDONTWRITEBYTECODE='1',
           CLOUDRA_CONFIG_FILE=meta['config_copy'], CLOUDRA_DATA_DIR=meta['data_dir'])
with (RUN / 'observer.log').open('ab') as output:
    observer = subprocess.Popen([str(Path(__import__('sys').executable)), '-u', str(RUN / 'observer.py')],
                cwd=meta['source_worktree'], env=env, stdout=output,
                stderr=subprocess.STDOUT, start_new_session=True)
launch['completed_startup_observer_pid'] = old_observer
launch['observer_pid'] = observer.pid
launch['startup_config_recovered_at'] = report['at']
(RUN / 'launch.json').write_text(json.dumps(launch, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'config_copy_corrected': True, 'same_project': launch['project_id'],
                  'same_session': launch['session_id'], 'observer_pid': observer.pid,
                  'no_process_restarted': True}, ensure_ascii=False))
