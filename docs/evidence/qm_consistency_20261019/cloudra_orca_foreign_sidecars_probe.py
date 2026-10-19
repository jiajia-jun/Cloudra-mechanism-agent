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

import os
import tempfile

root = Path(tempfile.mkdtemp(prefix='cloudra-orca-foreign-', dir="/tmp"))
os.environ['CLOUDRA_CONFIG_FILE'] = str(root/'absent.yaml')
os.environ['CLOUDRA_DATA_DIR'] = str(root/'runtime')
from cloudra.dag.evidence_ingest import snapshot_evidence_file
from cloudra.tools.core import orca_frames

log = root/'detached.out'
log.write_bytes((REPO_ROOT / 'tests/fixtures/orca/hcn_irc_orca60.out').read_bytes())
try:
    snapshot_evidence_file(log, root)
except Exception as exc:
    print('without_neighbors', type(exc).__name__, str(exc))
for side in ('F', 'B'):
    # Existing real captured sidecars from a different, larger molecule.
    (root/f'other_job_IRC_{side}.xyz').write_bytes((REPO_ROOT / f'tests/fixtures/benchmark_nu3/ts2_irc/irc_IRC_{side}.xyz').read_bytes())
endpoints = orca_frames.extract_irc_endpoints(str(log))
for name, endpoint in endpoints.items():
    print(name, endpoint['origin'], Path(endpoint['geometry_ref']).name)
snapshot = snapshot_evidence_file(log, root)
print('snapshot_accepted', snapshot.engine, [Path(side['snapshot_path']).name for side in snapshot.metadata['irc_sidecars']])
print('workspace', root)
