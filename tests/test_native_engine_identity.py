"""Native program identity follows the input rather than an arbitrary filename."""

import pytest

from cloudra.runtime_v2.method_policy import _detect_input_engine, check_input_content
from cloudra.runtime_v2.schemas import MethodPolicy

GAUSSIAN = '#p HF/STO-3G sp\n\nhelium\n\n0 1\nHe 0 0 0\n\n'
ORCA = '! HF STO-3G SP\n* xyz 0 1\nHe 0 0 0\n*\n'


@pytest.mark.parametrize('filename,content,expected', [
    ('gaussian.inp', GAUSSIAN, 'gaussian'),
    ('orca.gjf', ORCA, 'orca'),
    ('orca.com', '# previous trial\n%pal\n nprocs 2\nend\n' + ORCA, 'orca'),
    ('orca.gjf', '# Previous /path/with/slashes\n' + ORCA, 'orca'),
    ('orca.gjf', '# previous /path/with/slashes\n%method Method HF end\n* xyz 0 1\nHe 0 0 0\n*\n', 'orca'),
    ('renamed.gjf', '%method Method HF end\n* xyzfile 0 1 "coords.xyz"\n', 'orca'),
    ('', '%method Method HF end\n* int 0 1\nHe 0 0 0 0 0 0\n*\n', 'orca'),
    ('', '%coords CTyp xyz Charge 0 Mult 1\ncoords\nHe 0 0 0\nend\nend\n', 'orca'),
    ('', GAUSSIAN.replace('HF/STO-3G sp', 'FutureMethod FutureTask'), 'gaussian'),
    ('renamed.inp', '%chk=restart.chk\n#p AM1 Geom=AllCheck\n\n', 'gaussian'),
    ('renamed.inp', '%chk=restart.chk\n#p HF/STO-3G Geom=AllCheck\n! Gaussian route comment\n\n', 'gaussian'),
    ('', ORCA.replace('HF STO-3G SP', 'FutureMethod FutureBasis FutureTask'), 'orca'),
    ('', '# compute barrier with mace\necho done\n', None),
    ('job.sh', '#!/bin/sh\necho done\n', None),
    ('unknown.inp', 'unclassified native declaration', 'orca'),
])
def test_determinate_native_content_takes_priority_over_filename(filename, content, expected):
    assert _detect_input_engine(filename, content) == expected


@pytest.mark.parametrize('filename,content', [('job.inp', GAUSSIAN), ('job.gjf', ORCA)])
def test_method_contract_uses_the_program_actually_declared(filename, content):
    policy = MethodPolicy(allowed_methods=['hf/sto3g'])
    assert check_input_content(content, policy, filename=filename, strict=True).allowed
    changed = content.replace('HF', 'PBE0')
    assert not check_input_content(changed, policy, filename=filename, strict=True).allowed
