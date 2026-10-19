"""Archived audit probe; synthetic materials are identified in the report."""
# ruff: noqa: E402 -- initialize isolated config before importing Cloudra.


# Audit bootstrap: locate the checkout and keep generated files/configuration in /tmp.
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.dont_write_bytecode = True
_AUDIT_CONTEXT = Path(tempfile.mkdtemp(prefix="cloudra-audit-context-", dir="/tmp"))
os.environ["CLOUDRA_CONFIG_FILE"] = str(_AUDIT_CONTEXT / "absent.yaml")
os.environ["CLOUDRA_DATA_DIR"] = str(_AUDIT_CONTEXT / "runtime")
os.environ["CLOUDRA_DAEMON_WATCHDOG"] = "off"
os.chdir(_AUDIT_CONTEXT)

import json
import shutil
import subprocess

root = Path(tempfile.mkdtemp(prefix='ts-native-dependency-audit-', dir='/tmp'))
os.environ['CLOUDRA_CONFIG_FILE'] = str(root / 'no-config.yaml')
os.environ['CLOUDRA_DAEMON_WATCHDOG'] = 'off'
from cloudra.infra.config import get_config

get_config().data_dir = root / 'data'
from cloudra.infra.compute_utils import build_calculator_cmd
from cloudra.runtime.remote_compute import _stage_native_paths
from cloudra.services.ts_pipeline_context import use_pipeline_authority
from cloudra.tools.core import ts_process as process
from cloudra.tools.core.qm_calculation import QmCalculation
from tests.test_ts_native_option_intent import native_record

report = {'root': str(root), 'engine_binaries': {name: shutil.which(name) for name in ['g16', 'g09', 'g26', 'orca']}, 'qm_calculation_fields': list(QmCalculation.model_fields)}
for engine in ['gaussian', 'orca']:
    folder = root / engine
    folder.mkdir()
    keywords = 'irc=(readfc,reverse)' if engine == 'gaussian' else 'IRC'
    record = native_record(folder, engine, keywords)
    freq_input = Path(record.job_steps[-1].input_path)
    suffix = '.chk' if engine == 'gaussian' else '.hess'
    dependency = freq_input.with_suffix(suffix)
    dependency.write_text('SYNTHETIC DEPENDENCY BYTES: NOT QM EVIDENCE\n')
    if engine == 'orca':
        record.input.verification.irc.orca_blocks = '%irc\n InitHess read\n Hess_Filename "' + str(dependency) + '"\nend'
    irc_dir = folder / 'irc'
    irc_dir.mkdir()
    with use_pipeline_authority(lambda *_: (True, None)):
        error, path = process._write_irc_input(record, str(irc_dir))
        assert not error, error
        process._check_calculation_submission(record, 'irc', path, engine)
    stage = _stage_native_paths(Path(path), irc_dir, 123, engine)
    manifest = json.loads((irc_dir / '.cloudra/remote-123/path-map.json').read_text())
    report[engine] = {'input': Path(path).read_text(), 'input_path': path, 'warnings': record.warnings, 'method_check': record.method_checks[path], 'frequency_dependency': str(dependency), 'frequency_dependency_exists': dependency.exists(), 'irc_checkpoint_exists': Path(path).with_suffix('.chk').exists(), 'staged_input': (stage / Path(path).name).read_text(), 'staged_files': manifest['files']}
    if engine == 'gaussian':
        spy_dir = root / 'spy-bin'
        spy_dir.mkdir()
        spy = spy_dir / 'g16'
        spy.write_text('#!/bin/bash\n# Dry-run spy only. Does not run Gaussian or emit native success.\nprintf "SPY_CWD=%s\\nSPY_INPUT=%s\\n" "$PWD" "$1"\ncat "$1"\nexit 42\n')
        spy.chmod(0o700)
        ok, cmd, error = build_calculator_cmd(path, 'gaussian')
        assert ok, error
        dry_env = dict(os.environ, PATH=str(spy_dir) + os.pathsep + os.environ['PATH'])
        dry = subprocess.run(cmd, cwd=irc_dir, env=dry_env, capture_output=True, text=True)
        report[engine]['calculator_dry_run'] = {'cmd': cmd, 'returncode': dry.returncode, 'stdout': dry.stdout, 'stderr': dry.stderr}
output = root / 'report.json'
output.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
print('REPORT_PATH=' + str(output))
