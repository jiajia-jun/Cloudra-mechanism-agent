from copy import deepcopy

import pytest
from pydantic import ValidationError


def calculation(**changes):
    return {'engine': 'orca', 'method': 'B3LYP', 'basis_set': 'def2-SVP',
            'keywords': 'D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)',
            'orca_blocks': '%scf MaxIter 200 end', **changes}


def payload():
    return {'reaction': {'reactant_smiles': 'O', 'product_smiles': 'O',
                         'charge': 0, 'multiplicity': 1},
            'guess': {'kind': 'scan', 'calculation': calculation(),
                      'scans': [{'atoms': [0, 1], 'scan_end': 2., 'scan_steps': 7}]},
            'ts_optimization': calculation()}


def revise(current, changes):
    from cloudra.tools.core.ts_inputs import TsInputChanges, apply_input_changes

    return apply_input_changes(current, TsInputChanges.model_validate(changes))


def test_reentering_same_method_keeps_omitted_keywords_and_blocks():
    from cloudra.tools.core.ts_inputs import TsInput

    current = TsInput.model_validate(payload())
    updated = revise(current, {'ts_optimization': {'engine': 'orca', 'method': 'B3LYP'}})
    assert updated.ts_optimization == current.ts_optimization
    spaced = revise(current, {'ts_optimization': {'method': ' B3LYP ', 'basis_set': ' def2-SVP '}})
    assert spaced.ts_optimization == current.ts_optimization


@pytest.mark.parametrize('method,basis', [('hf', 'def2-SVP'), ('HF', 'def2svp'), ('hf', 'DEF2SVP')])
def test_partial_equivalent_method_and_basis_reentry_preserves_original_spelling(method, basis):
    from cloudra.tools.core.ts_inputs import TsInput

    data = payload()
    data['ts_optimization']['method'] = 'HF'
    current = TsInput.model_validate(data)
    updated = revise(current, {'ts_optimization': {'method': method, 'basis_set': basis}})
    assert updated.ts_optimization == current.ts_optimization
    assert updated.ts_optimization.method == 'HF' and updated.ts_optimization.basis_set == 'def2-SVP'


def test_partial_keywords_replace_the_string_and_null_clears_only_blocks():
    from cloudra.tools.core.ts_inputs import TsInput

    current = TsInput.model_validate(payload())
    updated = revise(current, {'ts_optimization': {'keywords': 'TightSCF', 'orca_blocks': None}})
    assert updated.ts_optimization.keywords == 'TightSCF'
    assert updated.ts_optimization.orca_blocks is None
    assert updated.ts_optimization.method == current.ts_optimization.method
    assert updated.ts_optimization.basis_set == current.ts_optimization.basis_set
    cleared = revise(updated, {'ts_optimization': {'keywords': ''}})
    assert cleared.ts_optimization.keywords == ''


def test_coordinate_only_scan_revision_keeps_complete_scientific_settings():
    from cloudra.tools.core.ts_inputs import TsInput

    current = TsInput.model_validate(payload())
    updated = revise(current, {'guess': {'scans': [{'atoms': [0, 1], 'scan_end': 2., 'scan_steps': 8}]}})
    assert updated.guess.scans[0].scan_steps == 8
    assert updated.guess.calculation == current.guess.calculation


@pytest.mark.parametrize('change', [{'engine': 'gaussian'}, {'method': 'PBE0'},
                                   {'basis_set': 'def2-TZVP'}])
def test_method_identity_changes_require_explicit_replacement(change):
    from cloudra.tools.core.ts_inputs import TsInput

    with pytest.raises(ValueError, match='replace'):
        revise(TsInput.model_validate(payload()), {'ts_optimization': change})


def test_explicit_cross_engine_replacement_does_not_carry_orca_blocks():
    from cloudra.tools.core.ts_inputs import TsInput

    current = TsInput.model_validate(payload())
    updated = revise(current, {'ts_optimization': {'replace': {
        'engine': 'gaussian', 'method': 'B3LYP', 'basis_set': 'def2-SVP', 'keywords': 'SCRF=(Solvent=Water)'}}})
    assert updated.ts_optimization.engine == 'gaussian'
    assert updated.ts_optimization.orca_blocks is None
    assert updated.ts_optimization.keywords == 'SCRF=(Solvent=Water)'


def referenced_payload():
    result = payload()
    result['calculations'] = {'formal': calculation(),
                              'exploration': calculation(method='GFN2-xTB', basis_set='', keywords='', orca_blocks=None)}
    result['ts_optimization'] = {'ref': 'formal'}
    result['guess']['calculation'] = {'ref': 'exploration'}
    result['verification'] = {'frequency': {'ref': 'formal'}, 'irc': {'ref': 'formal'},
                              'reactant_endpoint': {'optimization': {'ref': 'formal'}, 'frequency': {'ref': 'formal'}},
                              'product_endpoint': {'optimization': {'ref': 'formal'}, 'frequency': {'ref': 'formal'}}}
    return result


def test_seven_formal_stages_share_one_explicit_configuration_without_overwriting_exploration():
    from cloudra.tools.core.ts_inputs import TsInput, resolve_calculation

    value = TsInput.model_validate(referenced_payload())
    stages = [value.ts_optimization, value.verification.frequency, value.verification.irc]
    for side in ('reactant', 'product'):
        endpoint = getattr(value.verification, side + '_endpoint')
        stages.extend([endpoint.optimization, endpoint.frequency])
    assert len(stages) == 7
    assert all(resolve_calculation(stage, value.calculations) == value.calculations['formal'] for stage in stages)
    assert resolve_calculation(value.guess.calculation, value.calculations).method == 'GFN2-xTB'
    resolved = resolve_calculation(value.ts_optimization, value.calculations)
    resolved.keywords = ''
    assert value.calculations['formal'].keywords


def test_unknown_references_and_reference_cycles_are_rejected():
    from cloudra.tools.core.ts_inputs import TsInput

    value = referenced_payload()
    value['ts_optimization'] = {'ref': 'unknown'}
    with pytest.raises(ValidationError, match='unknown'):
        TsInput.model_validate(value)
    value = referenced_payload()
    value['calculations']['formal'] = {'ref': 'formal'}
    with pytest.raises(ValidationError):
        TsInput.model_validate(value)


def test_profile_patch_preserves_other_profiles_and_references():
    from cloudra.tools.core.ts_inputs import TsInput, resolve_calculation

    current = TsInput.model_validate(referenced_payload())
    updated = revise(current, {'calculations': {'formal': {'keywords': 'D3BJ TightSCF'}}})
    assert resolve_calculation(updated.ts_optimization, updated.calculations).keywords == 'D3BJ TightSCF'
    assert updated.calculations['formal'].orca_blocks == current.calculations['formal'].orca_blocks
    assert updated.calculations['exploration'] == current.calculations['exploration']
    assert current.calculations['formal'].keywords != updated.calculations['formal'].keywords


def test_profile_removal_is_explicit_and_cannot_remove_a_used_definition():
    from cloudra.tools.core.ts_inputs import TsInput

    data = referenced_payload()
    data['calculations']['unused'] = deepcopy(data['calculations']['formal'])
    current = TsInput.model_validate(data)
    updated = revise(current, {'calculations': {'unused': None}})
    assert 'unused' not in updated.calculations
    with pytest.raises(ValidationError, match='formal'):
        revise(current, {'calculations': {'formal': None}})


def test_stage_reference_replacement_is_explicit_and_patch_does_not_detach_it():
    from cloudra.tools.core.ts_inputs import TsInput

    current = TsInput.model_validate(referenced_payload())
    with pytest.raises(ValueError, match='referenced'):
        revise(current, {'ts_optimization': {'keywords': 'TightSCF'}})
    updated = revise(current, {'ts_optimization': {'replace': {'ref': 'exploration'}}})
    assert updated.ts_optimization.ref == 'exploration'


def test_referenced_scan_validation_and_atom_numbering_use_resolved_engine():
    from cloudra.tools.core.ts_inputs import TsInput, normalize_ts_input_atoms

    data = referenced_payload()
    data['calculations']['exploration']['engine'] = 'gaussian'
    data['guess']['scans'][0]['atoms'] = [1, 2]
    normalized = normalize_ts_input_atoms(TsInput.model_validate(data), atom_tables={'reactant': ['O', 'H', 'H']})
    assert normalized.guess.scans[0].atoms == [0, 1]
    data['calculations']['exploration']['engine'] = 'xtb'
    with pytest.raises(ValidationError, match='force_constant'):
        TsInput.model_validate(data)


def test_partial_scan_atom_numbering_uses_current_referenced_configuration():
    from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, normalize_ts_input_atoms

    data = referenced_payload()
    data['calculations']['exploration']['engine'] = 'gaussian'
    current = TsInput.model_validate(data)
    changes = TsInputChanges.model_validate({'guess': {'scans': [{'atoms': [1, 2], 'scan_end': 2., 'scan_steps': 8}]}})
    normalized = normalize_ts_input_atoms(changes, atom_tables={'reactant': ['O', 'H', 'H']}, current_input=current)
    assert normalized.guess.scans[0].atoms == [0, 1]
    assert normalized.guess.calculation is None
    updated = revise(current, normalized.model_dump(exclude_unset=True))
    assert updated.guess.calculation == current.guess.calculation


def historical_record(tmp_path, data=None):
    from cloudra.tools.core.ts_inputs import TsInput
    from cloudra.tools.core.ts_process import TsJobStep, stage_calculation
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path, input=TsInput.model_validate(data or referenced_payload()), stage='verdict')
    for index, purpose in enumerate(('ts_opt', 'frequency', 'irc', 'reactant_opt', 'reactant_frequency',
                                     'product_opt', 'product_frequency'), start=1):
        record.job_steps.append(TsJobStep(purpose=purpose, job_id=index, state='done',
            input_path=str(tmp_path / f'{purpose}.inp'), actual_calculation=stage_calculation(record, purpose)))
    record.scan_step = TsJobStep(purpose='scan', job_id=8, state='done', input_path=str(tmp_path / 'scan.inp'),
                                actual_calculation=stage_calculation(record, 'scan'))
    return record


def revision(record, changes):
    from cloudra.tools.core.ts_inputs import TsResumeRequest

    return TsResumeRequest(changes=changes, reason='explicit declared setting update',
                           request_key='test', expected_revision=record.revision)


def test_formal_profile_change_invalidates_its_stages_and_preserves_scan_snapshot(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record = historical_record(tmp_path)
    request = revision(record, {'calculations': {'formal': {'keywords': 'D3BJ TightSCF'}}})
    receipt = plan_input_revision(record, request)
    assert {ref.stage_key for ref in receipt.invalidated} == {step.purpose for step in record.job_steps}
    assert [ref.stage_key for ref in receipt.retained] == ['scan']
    updated = revise_record(record, request, receipt)
    assert updated.stage == 'submit'
    assert updated.scan_step.actual_calculation == record.scan_step.actual_calculation
    assert updated.attempt_history[0].job_steps[0].actual_calculation.keywords == calculation()['keywords']
    assert record.input.calculations['formal'].keywords == calculation()['keywords']


def test_endpoint_only_profile_change_preserves_other_formal_evidence(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    data = referenced_payload()
    data['calculations']['endpoint'] = calculation()
    data['verification']['reactant_endpoint'] = {'optimization': {'ref': 'endpoint'}, 'frequency': {'ref': 'endpoint'}}
    record = historical_record(tmp_path, data)
    request = revision(record, {'calculations': {'endpoint': {'keywords': 'D3BJ TightSCF'}}})
    receipt = plan_input_revision(record, request)
    assert {ref.stage_key for ref in receipt.invalidated} == {'reactant_opt', 'reactant_frequency'}
    updated = revise_record(record, request, receipt)
    assert updated.stage == 'refine'
    assert {step.purpose for step in updated.job_steps} == {'ts_opt', 'frequency', 'irc', 'product_opt', 'product_frequency'}


def test_unused_profile_change_does_not_invalidate_or_restart_computations(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    data = referenced_payload()
    data['calculations']['unused'] = calculation()
    record = historical_record(tmp_path, data)
    request = revision(record, {'calculations': {'unused': {'keywords': 'TightSCF'}}})
    receipt = plan_input_revision(record, request)
    assert not receipt.invalidated
    updated = revise_record(record, request, receipt)
    assert updated.stage == record.stage
    assert updated.job_steps == record.job_steps and updated.scan_step == record.scan_step


@pytest.mark.parametrize('changed_role', ['reactant', 'product'])
def test_seed_profile_revision_retains_independent_preparation_evidence(tmp_path, changed_role):
    from cloudra.tools.core.ts_process import TsJobStep, stage_calculation
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    data = referenced_payload()
    for role in ('reactant', 'product'):
        data['calculations'][role + '_seed'] = calculation()
        data.setdefault('conformers', {})[role] = {'kind': 'generate', 'generation': 'ETKDGv3', 'seed': 42,
                                                  'optimization': {'ref': role + '_seed'}}
    record = historical_record(tmp_path, data)
    for index, purpose in enumerate(('candidate_opt', 'product_seed_opt'), start=9):
        record.job_steps.insert(0, TsJobStep(purpose=purpose, job_id=index, state='done',
            input_path=str(tmp_path / (purpose + '.inp')), actual_calculation=stage_calculation(record, purpose)))
    original = record.model_copy(deep=True)
    request = revision(record, {'calculations': {changed_role + '_seed': {'keywords': 'D3BJ TightSCF'}}})
    receipt = plan_input_revision(record, request)
    changed = 'candidate_opt' if changed_role == 'reactant' else 'product_seed_opt'
    retained = 'product_seed_opt' if changed_role == 'reactant' else 'candidate_opt'
    assert {ref.stage_key for ref in receipt.invalidated} == {changed, 'scan', *[step.purpose for step in record.job_steps if step.purpose not in ('candidate_opt', 'product_seed_opt')]}
    assert [ref.stage_key for ref in receipt.retained] == [retained]
    updated = revise_record(record, request, receipt)
    assert updated.stage == 'build'
    assert [step.purpose for step in updated.job_steps] == [retained]
    assert updated.job_steps[0] == next(step for step in original.job_steps if step.purpose == retained)
    assert updated.job_steps[0].source_input_revision == 1
    assert record == original


def test_product_seed_revision_retains_reactant_derivatives_and_checkpoint(tmp_path, monkeypatch):
    from cloudra.tools.core.constrained_optimization import OptimizationRequest, initialize_constrained_state
    from cloudra.tools.core.geometry_optimization import OptimizationCheckpoint
    from cloudra.tools.core.ts_process import TsJobStep, _optimize_conformer_source, stage_calculation
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    data = referenced_payload()
    data['calculations']['reactant_seed'] = {'engine': 'xtb', 'method': 'GFN2-xTB', 'basis_set': ''}
    data['calculations']['product_seed'] = calculation()
    data['conformers'] = {role: {'kind': 'generate', 'generation': 'ETKDGv3', 'seed': 42,
                                'optimization': {'ref': role + '_seed'}} for role in ('reactant', 'product')}
    record = historical_record(tmp_path, data)
    for index, purpose in enumerate(('candidate_opt', 'candidate_evaluation', 'product_seed_opt'), start=9):
        record.job_steps.insert(0, TsJobStep(purpose=purpose, job_id=index, state='done',
            input_path=str(tmp_path / (purpose + '.json')), actual_calculation=stage_calculation(record, purpose)))
    geometry = OptimizationRequest(symbols=['O', 'H', 'H'], positions=[[0., 0., 0.], [.96, 0., 0.], [-.24, .93, 0.]],
                                   method_fingerprint='GFN2-xTB')
    record.optimization_checkpoints['reactant-checkpoint'] = OptimizationCheckpoint(
        state=initialize_constrained_state(geometry), directory=str(tmp_path / 'checkpoint'), job_ids=[10])
    request = revision(record, {'calculations': {'product_seed': {'keywords': 'D3BJ TightSCF'}}})
    receipt = plan_input_revision(record, request)
    assert {ref.stage_key for ref in receipt.retained} == {'candidate_opt', 'candidate_evaluation'}
    updated = revise_record(record, request, receipt)
    assert updated.optimization_checkpoints == record.optimization_checkpoints
    assert {step.purpose for step in updated.job_steps} == {'candidate_opt', 'candidate_evaluation'}
    assert all(step.source_input_revision == 1 for step in updated.job_steps)
    assert all(step.actual_calculation.method == 'GFN2-xTB' for step in updated.job_steps)
    seed = tmp_path / 'retained-seed.xyz'
    seed.write_text('3\nRetained converged seed fixture\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n')
    old_input = tmp_path / 'candidate_opt.json'
    old_input.write_text('Immutable original preparation input fixture')
    before = old_input.read_bytes()
    monkeypatch.setattr('cloudra.tools.core.ts_process._read_built_xyz', lambda *_: (geometry.symbols, geometry.positions, str(seed), ''))
    monkeypatch.setattr('cloudra.tools.core.ts_process._bound_input_structure', lambda *_: None)
    monkeypatch.setattr('cloudra.tools.core.ts_process._step_state', lambda *_: 'done')
    monkeypatch.setattr('cloudra.runtime.chem_task.read_task_result', lambda *_: ({'result': {
        'normal_termination': True, 'optimization_converged': True, 'optimized_xyz': str(seed)}}, None))
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step',
                        lambda *_: (_ for _ in ()).throw(AssertionError('unchanged preparation must reuse its retained job')))
    _optimize_conformer_source(updated, 'reactant')
    assert old_input.read_bytes() == before
    assert {step.job_id for step in updated.job_steps} == {9, 10}
    assert updated.current_seed_xyz_path
