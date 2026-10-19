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
import logging
import traceback
from tempfile import mkdtemp

from cloudra.benchmark.graph_similarity import GedConfig
from cloudra.benchmark.integrity import EvidenceFile, audit_integrity
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import GoldMechanismGraph, GoldSpec, PromptSpec, SystemSpec, TaskSpec
from cloudra.benchmark.selfconsistency import _LogProbe
from tests.test_gaussian_irc_evidence import _audit, _bundle, _native_log

logging.disable(logging.CRITICAL)
root = Path(mkdtemp(prefix='cloudra-unrelated-parse-failure-', dir="/tmp"))
print('ROOT', root, flush=True)

def caught(label, call):
    try:
        value = call()
        print(label, 'returned', value, flush=True)
    except Exception as exc:
        print(label, type(exc).__name__, str(exc), flush=True)
        print('TRACE', ' -> '.join(f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}'
            for frame in traceback.extract_tb(exc.__traceback__)), flush=True)

def bad_log(directory):
    path = _native_log(directory / 'aaa_unrelated.log', (['H', 'H'], [[0., 0., 0.], [0., 0., .74]]), imaginary=False)
    path.write_text(path.read_text().replace('0.000000000000', '**************', 1))
    return path

irc_dir = root / 'irc'
irc_dir.mkdir()
bundle = _bundle(irc_dir)
print('valid IRC baseline', _audit(irc_dir, bundle).passed, flush=True)
bad = bad_log(irc_dir)
extra = EvidenceFile(path=bad.name, kind='gaussian', size=bad.stat().st_size)
print('LogProbe bad candidate', _LogProbe(irc_dir, {bad.name: extra})._parse(bad.name), flush=True)
caught('audit_self_consistency + unrelated malformed candidate', lambda: _audit(irc_dir, bundle, extra_files=[extra]))

score_dir = root / 'score'
score_dir.mkdir()
water = (REPO_ROOT / 'tests/fixtures/gaussian/water_opt_freq_g16.out')
(score_dir / 'water.log').write_bytes(water.read_bytes())
graph = GoldMechanismGraph.model_validate({'nodes': [
    {'id': 'R', 'role': 'reactant', 'smiles': ['O'], 'properties': {'evidence_log': 'water.log'}}], 'edges': []})
(score_dir / 'mechanism_graph.json').write_text(json.dumps(graph.model_dump(mode='json', by_alias=True)))
task = TaskSpec(task_id='unrelated_bad_output', tier='easy', prompt=PromptSpec(query='water'),
    system=SystemSpec(reactants=['O']), gold=GoldSpec(mechanism_graph=graph))
runner = BenchmarkRunner.__new__(BenchmarkRunner)
runner.ged_config = GedConfig()
print('valid score baseline', runner.score_sandbox(task, score_dir).final_score, flush=True)
bad_log(score_dir)
caught('audit_integrity + unrelated malformed candidate', lambda: audit_integrity(score_dir))
caught('score_sandbox + unrelated malformed candidate', lambda: runner.score_sandbox(task, score_dir))
