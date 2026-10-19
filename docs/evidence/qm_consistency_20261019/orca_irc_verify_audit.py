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

from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
from cloudra.tools.core import irc_evidence, orca_frames
from cloudra.tools.core.irc_path import xyz_block
from tests.test_irc_endpoint_optimization import check_bundle, write_lineage_bundle


async def main():
    records = []
    for variant in ('normal', 'error_termination', 'no_termination'):
        directory = Path(tempfile.mkdtemp(prefix='orca_irc_audit_', dir="/tmp"))
        paths = await asyncio.to_thread(write_lineage_bundle, directory)
        text = await asyncio.to_thread(paths['irc'].read_text)
        if variant == 'error_termination':
            text = text.replace('ORCA TERMINATED NORMALLY', 'ORCA finished by error termination')
        elif variant == 'no_termination':
            text = text.replace('****ORCA TERMINATED NORMALLY****', '')
        await asyncio.to_thread(paths['irc'].write_text, text)
        reactant = await asyncio.to_thread(irc_evidence.probe_log, paths['reactant_freq'])
        product = await asyncio.to_thread(irc_evidence.probe_log, paths['product_freq'])
        args = TsGuess_input_schema(mode='verify', strict=True, freq_log=str(paths['ts']),
            irc_log=str(paths['irc']), reactant_text=xyz_block(*reactant[1]), product_text=xyz_block(*product[1]),
            reactant_logs=[str(paths['reactant_opt']), str(paths['reactant_freq'])],
            product_logs=[str(paths['product_opt']), str(paths['product_freq'])],
            output_dir=str(directory / 'verify'))
        result = await TsGuess(subagent=SimpleNamespace(working_directory=str(directory))).tool_call(args, None)
        direct = await asyncio.to_thread(check_bundle, paths)
        paired = await asyncio.to_thread(check_bundle, paths, paired=True)
        records.append(dict(variant=variant, directory=str(directory),
            irc_native_normal=orca_frames.normal_termination(text),
            ts_guess_status=result.verification_status, direct=direct[0], paired=paired[0]))
    print(json.dumps(records, indent=2))

asyncio.run(main())
