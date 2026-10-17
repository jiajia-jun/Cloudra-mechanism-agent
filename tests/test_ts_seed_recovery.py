"""The model can discover and cancel an optional seed pre-optimization."""
import pytest


@pytest.mark.parametrize('tool_name', ['ts_prepare', 'ts_resume'])
def test_file_seed_recovery_description_reaches_both_tool_contracts(tool_name):
    from cloudra.runtime_v2.adapters import legacy_tool_schemas
    from cloudra.tools import get_tools_lst
    from cloudra.tools.documentation import build_tool_documents

    schema = legacy_tool_schemas([tool_name])[0]['function']['parameters']['$defs']['FileConformer']
    field = schema['properties']['optimization']
    assert field['default'] is None and 'optimization' not in schema['required']
    description = field.get('description', '')
    assert 'as-is' in description
    assert 'complete file source' in description
    assert 'endpoint verification' in description
    document, = build_tool_documents([tool_name], allowed_names=[tool_name], entries=get_tools_lst())
    assert description in document.content


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('engine,state', [('orca', 'failed'), ('orca', 'done'), ('xtb', 'done')])
def test_seed_failure_view_explains_how_to_remove_optional_preoptimization(tmp_path, monkeypatch, engine, state):
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_inputs import FileConformer, QmCalculation
    from cloudra.tools.core.ts_state_view import build_process_view
    from tests.test_ts_stage_inputs import record_fixture
    from tests.ts_fixtures import calculation_input

    seed = tmp_path / 'water.xyz'
    seed.write_text('3\nExisting seed\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n')
    inputs = calculation_input(reactant_smiles='O', product_smiles='O', method='HF/STO-3G')
    inputs.conformers.reactant = inputs.conformers.product = FileConformer(kind='file', xyz_path=str(seed))
    record = record_fixture(tmp_path, input=inputs)
    ts_process._build(record)
    assert record.blocked is None
    record.input.conformers.product.optimization = QmCalculation(
        engine=engine, method='GFN2-xTB' if engine == 'xtb' else 'HF',
        basis_set='' if engine == 'xtb' else 'STO-3G')
    input_path = tmp_path / 'seed-opt.inp'
    input_path.write_text('Original failed seed input')
    record.job_steps = [ts_process.TsJobStep(purpose='product_seed_opt', job_id=41,
                                            input_path=str(input_path), state=state)]
    monkeypatch.setattr(ts_process, '_step_state', lambda *_: state)
    monkeypatch.setattr(ts_process, '_xtb_state_checkpoint', lambda *_: False)
    monkeypatch.setattr(ts_process, '_endpoint_opt_frame', lambda *_: ('', 'Native displacement criterion did not converge'))
    monkeypatch.setattr('cloudra.runtime.chem_task.read_task_result',
                        lambda *_: ({'result': {'normal_termination': True, 'optimization_converged': False}}, None))

    ts_process._optimize_conformer_source(record, 'product')
    view = build_process_view(record.model_dump(mode='json'), [], can_write=True)

    assert view.blocked['failure_class'] == 'conformer_optimization_failed'
    assert view.next['action'] == 'resume'
    assert view.next['required_inputs'] == ['conformers.product']
    assert 'changes.conformers.product' in view.message
    assert '"optimization": null' in view.message
    assert 'complete file source' in view.message
    assert 'endpoint verification' in view.message
    assert record.failed_attempt['job_id'] == 41
    assert view.result is None
