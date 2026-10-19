"""Native calculation controls do not change a trusted method declaration."""

import pytest

from cloudra.runtime_v2.method_policy import intercept
from cloudra.runtime_v2.schemas import MethodPolicy


@pytest.mark.parametrize('control', ['SOSCF', 'NoSOSCF', 'DIIS', 'NoDIIS', 'TRAH', 'NoTRAH', 'LooseSCF', 'EnGrad'])
def test_orca_native_controls_survive_prepared_input_submission(tmp_path, control):
    source = tmp_path / 'calculation.inp'
    source.write_text(f'! B3LYP def2-SVP {control}\n* xyz 0 1\nH 0 0 0\nH 0 0 .74\n*\n')
    policy = MethodPolicy(allowed_methods=['b3lyp/def2svp'])

    verdict = intercept('submit_compute_job', {'input_file': source.name, 'job_type': 'orca'},
                        policy, base_dir=tmp_path)

    assert verdict.allowed, verdict.reason
    assert verdict.method == 'b3lyp/def2svp'


@pytest.mark.parametrize('extra', ['PBE0', 'UnknownMethod'])
def test_native_scf_controls_do_not_hide_a_different_method(tmp_path, extra):
    source = tmp_path / 'calculation.inp'
    source.write_text(f'! B3LYP def2-SVP SOSCF {extra}\n* xyz 0 1\nH 0 0 0\nH 0 0 .74\n*\n')
    policy = MethodPolicy(allowed_methods=['b3lyp/def2svp'])

    verdict = intercept('submit_compute_job', {'input_file': source.name, 'job_type': 'orca'},
                        policy, base_dir=tmp_path)

    assert not verdict.allowed
    assert f'{extra.lower()}/def2svp' in verdict.matched_forbidden


def test_gaussian_scf_controls_leave_trusted_method_unchanged(tmp_path):
    source = tmp_path / 'calculation.gjf'
    source.write_text('#p B3LYP/def2SVP SCF=XQC\n\njob\n\n0 1\nH 0 0 0\nH 0 0 .74\n\n')

    verdict = intercept('submit_compute_job', {'input_file': source.name, 'job_type': 'gaussian'},
                        MethodPolicy(allowed_methods=['b3lyp/def2svp']), base_dir=tmp_path)

    assert verdict.allowed, verdict.reason
