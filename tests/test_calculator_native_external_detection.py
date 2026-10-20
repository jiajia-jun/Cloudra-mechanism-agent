"""The real calculator sees native ORCA controls; its engine is a local fake."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(('native', 'external'), [
    ('! HF STO-3G\n', False),
    ('# Previous trial used ProgExt\n! HF STO-3G\n', False),
    ('! HF STO-3G # ExtOpt\n', False),
    ('! HF # ExtOpt # STO-3G\n', False),
    ('%method Ext_Params "ProgExt ExtOpt # quoted" end\n! HF STO-3G\n', False),
    ('%moinp "ExtOpt.gbw"\n! HF STO-3G\n', False),
    ('%scf UserOption ProgExt end\n! HF STO-3G\n', False),
    ('! ExtOptExtra HF STO-3G\n', False),
    ('! "ExtOpt" HF STO-3G\n', False),
    ('! ExtOpt Opt\n', True),
    ('! extopt opt\n', True),
    ('!eXtOpT opt\n', True),
    ('! # previous provider # extopt opt\n', True),
    ('%method\n ProgExt "/mock/provider"\nend\n', True),
    ('%METHOD progext="/mock/provider" end\n', True),
    ('%method # previous trial # progext "/mock/provider#1" end\n', True),
])
def test_calculator_injects_external_environment_only_for_native_controls(tmp_path, native, external):
    """Removing native parsing recreates false injections and missed lowercase routes."""
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    binary = bindir / 'orca'
    binary.write_text(
        '#!/bin/bash\n'
        'printf "OMP_NUM_THREADS=%s\\nKMP_DUPLICATE_LIB_OK=%s\\n" '
        '"$OMP_NUM_THREADS" "$KMP_DUPLICATE_LIB_OK"\n',
        encoding='utf-8',
    )
    binary.chmod(0o755)
    source = tmp_path / 'job.inp'
    original = (native + '* xyz 0 1\nHe 0 0 0\n*\n').encode()
    source.write_bytes(original)
    calculator = Path(__file__).resolve().parents[1] / 'cloudra/calculator.sh'
    completed = subprocess.run(
        ['/bin/bash', str(calculator), str(source), 'orca'],
        cwd=tmp_path,
        env={'PATH': str(bindir) + os.pathsep + os.defpath,
             'OMP_NUM_THREADS': '8', 'KMP_DUPLICATE_LIB_OK': 'FALSE'},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    received = dict(line.split('=', 1) for line in completed.stdout.splitlines())
    assert received == {
        'OMP_NUM_THREADS': '1' if external else '8',
        'KMP_DUPLICATE_LIB_OK': 'TRUE' if external else 'FALSE',
    }
    assert ('MLIP external route detected' in completed.stderr) is external
    assert source.read_bytes() == original
