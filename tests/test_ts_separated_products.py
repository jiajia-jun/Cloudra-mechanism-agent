from pathlib import Path

import pytest

from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges
from tests.test_ts_inputs import input_payload
from tests.test_ts_stage_inputs import record_fixture


def test_separated_product_declaration_and_component_logs_preserve_their_meaning():
    payload = input_payload()
    payload['reaction']['product_smiles'] = ['C=O', 'O']
    payload['verification'] = {'product_endpoint': {
        'component_logs': ['formaldehyde.out', 'water.out'],
    }}

    value = TsInput.model_validate(payload)

    assert value.reaction.product_smiles == ['C=O', 'O']
    assert value.verification.product_endpoint.component_logs == ['formaldehyde.out', 'water.out']


@pytest.mark.parametrize('failed_complex', [False, True])
def test_component_evidence_revision_keeps_existing_ts_irc_and_complex_attempt(tmp_path, failed_complex):
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_process import TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record = record_fixture(tmp_path, terminal='candidate_only', stage='verdict')
    record.job_steps = [TsJobStep(purpose=purpose, job_id=index, state='done')
                        for index, purpose in enumerate((
                            'frequency', 'irc', 'reactant_opt', 'reactant_frequency',
                            'product_opt', 'product_frequency',
                        ), start=1)]
    if failed_complex:
        step = record.job_steps[-1]
        record.failed_attempt = {'attempt_id': f'{step.source_input_revision}:{step.purpose}:{step.job_id}'}
    request = TsResumeRequest(
        changes=TsInputChanges.model_validate({'verification': {'product_endpoint': {
            'component_logs': ['product_a.out', 'product_b.out'],
        }}}), reason='Verify the separated products without discarding the complex attempt',
        request_key='component-evidence', expected_revision=record.revision,
    )

    receipt = plan_input_revision(record, request)
    revised = revise_record(record, request, receipt)

    assert not receipt.invalidated
    assert [step.job_id for step in revised.job_steps] == [1, 2, 3, 4, 5, 6]
    assert revised.stage == 'refine'
    assert revised.terminal is None


def test_component_logs_are_snapshotted_and_reused_without_reading_mutable_sources(tmp_path):
    from cloudra.tools.core.ts_process import _product_component_logs

    record = record_fixture(tmp_path)
    source = tmp_path / 'product.out'
    source.write_text('immutable component evidence')
    record.input.verification.product_endpoint.component_logs = [str(source)]

    first = _product_component_logs(record)
    source.write_text('changed source')
    second = _product_component_logs(record)

    assert first == second
    assert Path(first[0]).read_text() == 'immutable component evidence'
    Path(first[0]).write_text('corrupted snapshot')
    with pytest.raises(ValueError, match='component evidence'):
        _product_component_logs(record)


def separated_record(tmp_path):
    import hashlib
    import shutil

    from rdkit import Chem

    from cloudra.tools.core.irc_path import xyz_block
    from cloudra.tools.core.ts_process import EndpointSource, TsJobStep, TsProcessRecord
    from tests.test_irc_separated_products import FIXTURE, MAP, PRODUCTS, materials

    native = tmp_path / 'native'
    shutil.copytree(FIXTURE, native)
    (native / 'reactant_opt.out').write_text((native / 'reactant.out').read_text().replace(
        '****ORCA TERMINATED NORMALLY****',
        'THE OPTIMIZATION HAS CONVERGED\n****ORCA TERMINATED NORMALLY****'))
    ends, ts, source, components, _binding = materials()
    payload = input_payload()
    reactant = Chem.MolFromMolFile(str(native / 'reactant.mol'), removeHs=False)
    product = Chem.MolFromMolFile(str(native / 'product.mol'), removeHs=False)
    payload['reaction'].update(reactant_smiles=Chem.MolToSmiles(Chem.RemoveHs(reactant)),
                               product_smiles=PRODUCTS)
    calculation = payload['ts_optimization']
    payload['verification'] = {'frequency': calculation, 'irc': calculation,
        'reactant_endpoint': {'optimization': calculation, 'frequency': calculation},
        'product_endpoint': {'component_logs': []}}
    for index, (symbols, positions) in enumerate(components):
        log = native / f'component_{index}.out'
        rows = '\n'.join(f'{symbol} {x:.10f} {y:.10f} {z:.10f}'
                         for symbol, (x, y, z) in zip(symbols, positions, strict=True))
        log.write_text('O   R   C   A\nCARTESIAN COORDINATES (ANGSTROEM)\n'
                       '---------------------------------\n' + rows +
                       '\n\nVIBRATIONAL FREQUENCIES\n 0: 100.00 cm**-1\n\n'
                       '****ORCA TERMINATED NORMALLY****\n')
        payload['verification']['product_endpoint']['component_logs'].append(str(log))
    record = TsProcessRecord(run_id='separated', run_dir=str(tmp_path / 'run'), workspace_dir=str(tmp_path),
        input=TsInput.model_validate(payload), structures=dict(reactant=reactant, product=product,
            product_to_reactant=tuple(index - 1 for index in MAP)))
    Path(record.run_dir).mkdir()
    source_path = native / 'reactant.xyz'
    source_path.write_text(xyz_block(*source))
    origin = EndpointSource(kind='species_reference', label='reactant', source_path=str(source_path),
        sha256=hashlib.sha256(source_path.read_bytes()).hexdigest())
    for index, (purpose, log_name, geometry) in enumerate((
        ('frequency', 'ts.out', ts), ('irc', 'irc.out', ts),
        ('reactant_opt', 'reactant_opt.out', source), ('reactant_frequency', 'reactant.out', source),
    ), start=1):
        directory = tmp_path / purpose
        directory.mkdir()
        (directory / 'optimized.xyz').write_text(xyz_block(*geometry))
        log = native / log_name
        record.job_steps.append(TsJobStep(purpose=purpose, job_id=index,
            input_path=str(directory / 'input.inp'), state='done',
            actual_calculation=record.input.verification.frequency,
            endpoint_source=origin if purpose.startswith('reactant_') else None,
            external_source={'log_path': str(log), 'source_job_id': index,
                'artifact_hashes': {str(log): hashlib.sha256(log.read_bytes()).hexdigest()}}))
    return record


@pytest.mark.parametrize('declaration', ['separated', 'complex'])
def test_process_accepts_real_separated_product_irc_without_verifying_complex(tmp_path, rdkit_chemistry, declaration):
    from cloudra.tools.core import ts_process

    record = separated_record(tmp_path)
    if declaration == 'complex':
        record.input.reaction.product_smiles = '.'.join(record.input.reaction.product_smiles)

    result = ts_process._verdict(record)

    assert result.terminal == 'verified', result.stage_record('verdict').detail
    assert 'separated products' in result.stage_record('verdict').detail.lower()
    assert 'C=C + O=[PH3]' in result.stage_record('verdict').detail
    assert 'complex C=C.O=[PH3] minimum remains UNVERIFIED' in result.stage_record('verdict').detail
    assert ts_process._validated_endpoint_minimum(result, 'product')[0] is None
    assert not any(step.purpose.startswith('product_') for step in result.job_steps)


def test_refine_uses_component_evidence_without_submitting_another_complex_optimization(tmp_path, rdkit_chemistry):
    from cloudra.tools.core import ts_process

    record = separated_record(tmp_path)
    original_jobs = [step.job_id for step in record.job_steps]

    result = ts_process._refine(record)

    assert result.blocked is None, result.blocked
    assert result.stage_record('refine').status == 'done'
    assert [step.job_id for step in result.job_steps] == original_jobs


@pytest.mark.parametrize('mutation', ['missing', 'imaginary', 'wrong_product'])
def test_process_rejects_incomplete_or_wrong_separated_product_evidence(tmp_path, rdkit_chemistry, mutation):
    from cloudra.tools.core import ts_process

    record = separated_record(tmp_path)
    logs = record.input.verification.product_endpoint.component_logs
    if mutation == 'missing':
        logs.pop()
    elif mutation == 'imaginary':
        path = Path(logs[0])
        path.write_text(path.read_text().replace('100.00 cm**-1', '-100.00 cm**-1'))
    else:
        record.input.reaction.product_smiles = ['CC', 'O=[PH3]']

    result = ts_process._verdict(record)

    assert result.terminal == 'candidate_only'
