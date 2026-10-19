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
from cloudra.tools.core import gaussian_frames, irc_evidence
from cloudra.tools.core.irc_path import xyz_block
from tests.test_gaussian_irc_evidence import _audit, _bundle


async def main():
    records = []
    for variant in ('normal', 'error_termination', 'no_termination'):
        directory = Path(tempfile.mkdtemp(prefix='irc_verify_audit_', dir="/tmp"))
        bundle = await asyncio.to_thread(_bundle, directory)
        irc = bundle['irc']
        text = await asyncio.to_thread(irc.read_text)
        if variant == 'error_termination':
            text = text.replace('Normal termination', 'Error termination')
        elif variant == 'no_termination':
            text = '\n'.join(line for line in text.splitlines() if 'Normal termination' not in line)
        await asyncio.to_thread(irc.write_text, text)
        reactant = await asyncio.to_thread(irc_evidence.probe_log, bundle['reactant_freq'])
        product = await asyncio.to_thread(irc_evidence.probe_log, bundle['product_freq'])
        args = TsGuess_input_schema(mode='verify', strict=True, freq_log=str(bundle['ts']),
            irc_log=str(irc), reactant_text=xyz_block(*reactant[1]), product_text=xyz_block(*product[1]),
            reactant_logs=[str(bundle['reactant_opt']), str(bundle['reactant_freq'])],
            product_logs=[str(bundle['product_opt']), str(bundle['product_freq'])],
            output_dir=str(directory / 'verify'))
        result = await TsGuess(subagent=SimpleNamespace(working_directory=str(directory))).tool_call(args, None)
        report = await asyncio.to_thread(_audit, directory, bundle)
        records.append(dict(variant=variant, directory=str(directory),
            irc_native_normal=gaussian_frames.normal_termination(text),
            is_success=result.is_success, ts_guess_status=result.verification_status,
            verdict=result.verdict, benchmark_consistency=report.passed,
            strict_details=result.checks[-3:]))
    print(json.dumps(records, ensure_ascii=False, indent=2))

asyncio.run(main())
