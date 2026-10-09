import pytest

from cloudra.runtime_v2.method_policy import check_input_content, check_method, intercept
from cloudra.runtime_v2.schemas import MethodPolicy


@pytest.mark.parametrize('entry', ['structured', 'orca', 'gaussian', 'unknown', 'missing_method', 'missing_input'])
def test_method_rejection_identifies_current_benchmark_without_selecting_replacement(entry):
    policy = MethodPolicy(allowed_methods=['xtb', 'b3lyp/def2svp'])
    if entry == 'structured':
        verdict = check_method('PBE0', policy, basis='def2-SVP')
    elif entry == 'orca':
        verdict = check_input_content('! Opt PBE0 def2-SVP\n* xyz 0 1\nO 0 0 0\n*\n', policy, filename='job.inp', strict=True)
    elif entry == 'gaussian':
        verdict = check_input_content('#p PBE0/def2-SVP opt\n\njob\n\n0 1\nO 0 0 0\n\n', policy, filename='job.gjf', strict=True)
    elif entry == 'unknown':
        verdict = check_input_content('3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n', policy, filename='job.xyz', strict=True)
    elif entry == 'missing_method':
        verdict = intercept('qm_input_writer', {'basis_set': 'def2-SVP'}, policy)
    else:
        verdict = intercept('submit_compute_job', {'job_type': 'orca'}, policy)
    assert not verdict.allowed
    assert 'current Benchmark task' in verdict.reason
    assert 'fall back' not in verdict.reason and 'e.g.' not in verdict.reason
    assert policy.allowed_methods == ['xtb', 'b3lyp/def2svp']


def test_empty_benchmark_whitelist_returns_rejection_without_choosing_a_method():
    policy = MethodPolicy(allowed_methods=[])
    verdict = check_method('PBE0', policy, basis='def2-SVP')
    assert not verdict.allowed and verdict.method == 'PBE0'
    assert 'allowed_methods []' in verdict.reason
    assert 'current Benchmark task' in verdict.reason


def test_scan_hint_keeps_user_method_and_scopes_whitelist_to_benchmark(tmp_path):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    source = tmp_path / 'h2.xyz'
    source.write_text('2\nH2\nH 0 0 0\nH 0 0 .74\n')
    target = tmp_path / 'scan.gjf'
    request = TsGuess_input_schema(mode='scan_prepare', engine='gaussian',
        input_path=str(source), method='B3LYP/def2svp', extra_route='emp=gd3bj',
        output_path=str(target), scans=[{'atoms': [1, 2], 'scan_end': 1.2, 'scan_steps': 5}])
    result = TsGuess()._scan_prepare(request)
    assert result.is_success
    assert 'Benchmark' in result.run_hint and 'ordinary' in result.run_hint
    assert 'MethodPolicy-permitted' not in result.run_hint
    assert request.method == 'B3LYP/def2svp' and request.extra_route == 'emp=gd3bj'
    assert 'B3LYP/def2svp' in target.read_text() and 'emp=gd3bj' in target.read_text()
