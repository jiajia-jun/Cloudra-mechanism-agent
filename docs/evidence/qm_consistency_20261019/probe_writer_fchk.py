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

import asyncio
import json
from types import SimpleNamespace

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema


async def main():
    root = Path(tempfile.mkdtemp(prefix='cloudra-writer-fchk-', dir="/tmp"))
    source = root / 'water.xyz'
    source.write_text('3\nwater\nO 0 0 0.1173\nH 0 0.7572 -0.4692\nH 0 -0.7572 -0.4692\n')
    request = QmInputWriter_input_schema(
        engine='gaussian', method='HF', basis_set='STO-3G',
        source_type='xyz_file', source_value=str(source),
        charge=0, multiplicity=1, task_type=[{'single_point': None}],
        fchk_name=str(root / 'water.fchk'), output_path=str(root / 'water.gjf'),
    )
    result = await QmInputWriter(subagent=SimpleNamespace(working_directory=str(root))).tool_call(request, None)
    print(json.dumps({'is_success': result.is_success, 'message': result.message,
                      'warnings': result.warnings, 'unapplied_options': result.unapplied_options}, indent=2))
    text = Path(result.input_path).read_text()
    print(text)
    without_link0 = '\n'.join(line for line in text.split('\n') if not line.startswith('%'))
    print('VALIDATION_AFTER_REMOVING_ALL_LINK0 =', QmInputWriter.validate_rendered_input(request, without_link0, charge=0))
    print('ARTIFACT_DIR =', root)

asyncio.run(main())
