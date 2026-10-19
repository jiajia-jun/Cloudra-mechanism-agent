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
import shutil
import tempfile

root = Path(tempfile.mkdtemp(prefix='cloudra-irc-neighbor-', dir="/tmp"))
os.environ['CLOUDRA_CONFIG_FILE'] = str(root/'absent.yaml')
os.environ['CLOUDRA_DATA_DIR'] = str(root/'runtime')
from cloudra.benchmark.integrity import EvidenceFile
from cloudra.benchmark.selfconsistency import _LogProbe
from cloudra.dag.evidence_ingest import snapshot_evidence_file
from cloudra.tools.core.irc_evidence import irc_endpoint_geometries, normal_log

native = (REPO_ROOT / 'tests/fixtures/gaussian/hcn_ts_irc_g16.log').read_bytes()
a = root/'first.log'
b = root/'second.log'
a.write_bytes(native)
b.write_bytes(native + b'\n')  # A parser byte-variant; no computed result is invented.
first_snapshot = snapshot_evidence_file(a, root)
print('before_neighbor', normal_log(b), irc_endpoint_geometries(b) is not None,
      snapshot_evidence_file(b, root).engine)
probe = _LogProbe(root, {b.name: EvidenceFile(path=b.name, kind='gaussian')})
print('binding_before_neighbor', probe.irc_atom_binding(b.name))
# Reuse the valid manifest the real snapshot writer generated for first.log.
shutil.copy2(first_snapshot.metadata['irc_manifest']['snapshot_path'], root/'irc_endpoints.json')
print('first_log_still_valid', snapshot_evidence_file(a, root).engine)
for name, action in [('snapshot_second', lambda: snapshot_evidence_file(b, root)),
                     ('probe_second_binding', lambda: probe.irc_atom_binding(b.name))]:
    try:
        action()
    except Exception as exc:
        print(name, type(exc).__name__, str(exc))
print('second_native_still_valid', normal_log(b), irc_endpoint_geometries(b) is not None)
print('workspace', root)
