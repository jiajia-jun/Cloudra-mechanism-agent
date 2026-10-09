import pytest

from cloudra.runtime_v2.method_policy import check_input_content, check_method
from cloudra.runtime_v2.schemas import MethodPolicy
from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema


@pytest.mark.parametrize('entry,method,allowed', [
    ('b3lyp/def2svp', 'B3LYP', True),
    ('b3lyp/def2svp', 'B3LYP/G', False),
    ('b3lyp/g/def2svp', 'B3LYP/G', True),
    ('b3lyp/g/def2svp', 'B3LYP', False),
    ('b3lyp/g', 'B3LYP/G', True),
    ('b3lyp', 'B3LYP/G', False),
])
def test_structured_and_native_whitelist_keep_native_method_slash_identity(entry, method, allowed):
    policy = MethodPolicy(allowed_methods=[entry])
    request = QmInputWriter_input_schema(engine='orca', method=method, basis_set='def2-SVP',
        keywords='D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)',
        source_type='xyz_file', source_value='unused.xyz', output_path='unused.inp')
    native = QmInputWriter._build_orca_input(request, 'O 0 0 0')
    structured = check_method(request.method, policy, basis=request.basis_set)
    inspected = check_input_content(native, policy, filename='job.inp', strict=True)
    assert structured.allowed is allowed
    assert inspected.allowed is allowed


@pytest.mark.parametrize('method', ['B3LYP', 'B3LYP/G'])
@pytest.mark.parametrize('benchmark', [False, True])
@pytest.mark.asyncio
async def test_native_method_variant_is_restricted_only_in_current_benchmark(tmp_path, method, benchmark):
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies.base import ToolCall
    from tests.test_runtime_v2_method_policy import _blocked_events, _run_tool_turn, _spawn

    core = RuntimeCore(strict_events=True)
    settings = {'method_policy': {'allowed_methods': ['b3lyp/def2svp']}}
    if benchmark:
        settings['benchmark_task_id'] = 'native-method-fixture'
    _, agent = await _spawn(core, tmp_path, settings=settings)
    arguments = dict(engine='orca', method=method, basis_set='def2-SVP', keywords='D3BJ',
        source_type='xyz_file', source_value='unused.xyz', output_path='unused.inp')
    _, tools = await _run_tool_turn(core, agent, tmp_path,
        ToolCall(id='native-method', name='qm_input_writer', arguments=arguments))
    if benchmark and method == 'B3LYP/G':
        assert tools.calls == []
        assert _blocked_events(core, agent.id)
    else:
        assert tools.calls == ['qm_input_writer']
        assert not _blocked_events(core, agent.id)


def test_native_slash_method_still_requires_its_allowed_orbital_basis():
    policy = MethodPolicy(allowed_methods=['b3lyp/g/def2svp'])
    assert not check_method('B3LYP/G', policy).allowed
    assert not check_method('B3LYP/G', policy, basis='def2-TZVP').allowed
    text = '! B3LYP/G def2-TZVP RIJCOSX def2/J\n* xyz 0 1\nO 0 0 0\n*\n'
    assert not check_input_content(text, policy, filename='job.inp', strict=True).allowed


@pytest.mark.parametrize('basis_set', ['6-31G(d)', 'aug-cc-pVDZ', 'ma-def2-SVP', 'pc-4'])
@pytest.mark.parametrize('constrain_basis', [False, True])
@pytest.mark.parametrize('engine', ['orca', 'gaussian'])
def test_normalized_basis_does_not_turn_into_part_of_the_method_name(basis_set, constrain_basis, engine):
    entry = 'b3lyp/' + basis_set if constrain_basis else 'b3lyp'
    policy = MethodPolicy(allowed_methods=[entry])
    request = QmInputWriter_input_schema(engine=engine, method='B3LYP', basis_set=basis_set,
        source_type='xyz_file', source_value='unused.xyz', output_path='unused.inp')
    native = QmInputWriter._build_orca_input(request, 'O 0 0 0') if engine == 'orca' else QmInputWriter._build_gjf(request, 'O 0 0 0')
    assert check_method(request.method, policy, basis=request.basis_set).allowed
    assert check_input_content(native, policy, filename='job.inp' if engine == 'orca' else 'job.gjf', strict=True).allowed


@pytest.mark.parametrize('basis_set', ['gen', 'genecp', 'CustomBasisLabel'])
@pytest.mark.parametrize('constrain_basis', [False, True])
def test_gaussian_declared_basis_labels_keep_existing_combination_semantics(basis_set, constrain_basis):
    entry = 'b3lyp/' + basis_set if constrain_basis else 'b3lyp'
    policy = MethodPolicy(allowed_methods=[entry])
    native = '#p B3LYP/' + basis_set + ' opt\n\njob\n\n0 1\nO 0 0 0\n\n'
    assert check_method('B3LYP', policy, basis=basis_set).allowed
    assert check_input_content(native, policy, filename='job.gjf', strict=True).allowed
