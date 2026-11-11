"""Run local GROMACS analysis commands without a shell."""

import os
import shutil
import subprocess
from collections import deque


class GromacsError(RuntimeError):
    """A GROMACS analysis command could not be started or interpreted."""


def _command(args: list[str]) -> list[str]:
    executable = shutil.which('gmx') or shutil.which('gmx_mpi')
    if executable is None:
        raise GromacsError('GROMACS is required on the Cloudra host. Add gmx or gmx_mpi to PATH.')
    return [executable, *args]


def run_gromacs(args: list[str], *, selection: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            _command(args), input=selection or '', stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors='replace', env={**os.environ, 'LC_ALL': 'C'},
        )
    except OSError as exc:
        raise GromacsError(f'Could not run GROMACS: {exc}') from exc


def start_gromacs(args: list[str]) -> subprocess.Popen[str]:
    try:
        return subprocess.Popen(
            _command(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors='replace', env={**os.environ, 'LC_ALL': 'C'},
        )
    except OSError as exc:
        raise GromacsError(f'Could not run GROMACS: {exc}') from exc


def gromacs_failure(report: str) -> str:
    for marker in ('Fatal error:\n', 'Error in user input:\n'):
        _, found, detail = report.partition(marker)
        if found:
            return detail.strip().split('\n\n', 1)[0]
    return report.strip()[-2000:]


def read_gromacs_atom_count(args: list[str]) -> int:
    """Read the first atom count from a TPR or trajectory dump."""
    tail: deque[str] = deque(maxlen=30)
    with start_gromacs(args) as process:
        for line in process.stdout:
            key, separator, value = line.partition('=')
            if separator and key.strip() == 'natoms':
                # The dump is a read-only probe. Stop printing coordinates after its header.
                process.terminate()
                return int(value.split()[0])
            tail.append(line)
    detail = gromacs_failure(''.join(tail))
    raise GromacsError(f'Could not read the GROMACS atom count.\n{detail}')
