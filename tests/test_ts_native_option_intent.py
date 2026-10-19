"""Native scientific choices survive TS stages and immutable IRC reuse."""
from pathlib import Path

import pytest

from cloudra.tools.core import ts_process as process
from cloudra.tools.core.qm_calculation import QmCalculation
from tests.test_ts_stage_inputs import owned_fixture_structure, record_fixture
from tests.ts_fixtures import calculation_input

pytestmark = pytest.mark.usefixtures('ts_producer_authority', 'rdkit_chemistry')


def native_record(tmp_path, engine, keywords='', blocks=None):
    inputs = calculation_input(reactant_smiles='O', product_smiles='O', method='HF',
        basis_set='STO-3G', engine=engine, keywords=keywords)
    inputs.ts_optimization.orca_blocks = blocks
    inputs.verification.irc.orca_blocks = blocks
    record = record_fixture(tmp_path, input=inputs)
    xyz = tmp_path / 'water.xyz'
    xyz.write_text('3\nTS frame\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n')
    owned_fixture_structure(record, xyz, 'O')
    from rdkit import Chem
    record.structures.candidate = Chem.Mol(record.structures.reactant)
    frequency = tmp_path / 'frequency'
    frequency.mkdir()
    (frequency / 'optimized.xyz').write_text(xyz.read_text())
    freq = frequency / ('freq.inp' if engine == 'orca' else 'freq.gjf')
    freq.write_text('bound frequency fixture')
    record.job_steps.append(process.TsJobStep(purpose='frequency', job_id=99,
        state='done', input_path=str(freq), actual_calculation=inputs.verification.frequency))
    return record


@pytest.mark.parametrize('engine,keywords,expected', [
    ('gaussian', '', 'opt=TS'),
    ('gaussian', 'opt=(ts,calcfc)', 'opt=(ts,calcfc)'),
    ('gaussian', 'opt=(tight,maxstep=4)', 'opt=(tight,maxstep=4)'),
    ('gaussian', 'Force', 'Force'),
    ('orca', '', '! OptTS HF STO-3G'),
    ('orca', 'Opt TightSCF', '! HF STO-3G Opt TightSCF'),
    ('orca', 'EnGrad', '! HF STO-3G EnGrad'),
])
def test_ts_refinement_preserves_explicit_native_tasks_without_solver_additions(tmp_path, engine, keywords, expected):
    record = native_record(tmp_path, engine, keywords)
    folder = tmp_path / 'refine'
    folder.mkdir()
    error, path = process._write_refinement_input(record, str(folder))
    assert not error, error
    content = Path(path).read_text()
    assert expected in content
    if not keywords:
        assert all(token not in content.lower() for token in ('calcfc', 'noeigen', 'calc_hess'))
    if keywords in {'opt=(tight,maxstep=4)', 'Force', 'Opt TightSCF', 'EnGrad'}:
        assert 'optts' not in content.lower() and 'opt=ts' not in content.lower()
        process._check_calculation_submission(record, 'ts_opt', path, engine)
        assert any(item['code'] == 'purpose_task_mismatch' for item in record.warnings)
        assert not record.method_checks[path]['matched']


@pytest.mark.parametrize('engine,keywords,blocks', [
    ('gaussian', '', None),
    ('gaussian', 'irc=(maxpoints=40,stepsize=10)', None),
    ('gaussian', 'irc=(readfc,reverse)', None),
    ('orca', '', None),
    ('orca', 'IRC', '%irc\n Direction backward\n InitHess identity\nend'),
])
def test_irc_uses_only_declared_scientific_settings(tmp_path, engine, keywords, blocks):
    record = native_record(tmp_path, engine, keywords, blocks)
    Path(record.job_steps[-1].input_path).with_suffix('.hess').write_text('$hessian')
    folder = tmp_path / 'irc'
    folder.mkdir()
    error, path = process._write_irc_input(record, str(folder))
    assert not error, error
    content = Path(path).read_text()
    assert all(token not in content.lower() for token in ('calcfc', 'calc_numfreq', 'hess_filename'))
    if engine == 'orca':
        assert ('%irc' in content) == bool(blocks)
        if blocks:
            assert blocks in content
        else:
            assert 'direction' not in content.lower() and 'inithess' not in content.lower()
    if keywords:
        assert keywords in content
    process._check_calculation_submission(record, 'irc', path, engine)
    assert record.method_checks[path]['matched']


def test_native_advice_is_durable_and_visible_to_model(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view
    record = native_record(tmp_path, 'gaussian', 'opt=ts')
    folder = tmp_path / 'refine'
    folder.mkdir()
    error, path = process._write_refinement_input(record, str(folder))
    assert not error
    assert record.warnings and all(item['severity'] == 'warning' for item in record.warnings)
    assert any(item['code'] == 'initial_hessian_unspecified' for item in record.warnings)
    restored = process.TsProcessRecord.model_validate_json(record.model_dump_json())
    view = build_process_view(restored.model_dump(mode='json'), [], can_write=True)
    assert view.warnings == [{key: value for key, value in item.items() if key not in {'source', 'input_revision'}} for item in record.warnings]
    assert all(item['input_path'] == path and item['purpose'] == 'ts_opt' for item in view.warnings)


def test_submission_reports_native_difference_without_rewriting(tmp_path):
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    record = native_record(tmp_path, 'orca', 'TightSCF')
    target = tmp_path / 'native.inp'
    target.write_text('! Opt HF STO-3G LooseSCF\n* xyz 0 1\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n*\n')
    before = target.read_bytes()
    with use_pipeline_authority(lambda *_: (True, None)):
        process._check_calculation_submission(record, 'ts_opt', str(target), 'orca')
    assert target.read_bytes() == before
    assert not record.method_checks[str(target)]['matched']
    assert record.method_checks[str(target)]['differences']
    assert {item['code'] for item in record.warnings} >= {'purpose_task_mismatch', 'native_calculation_difference'}


def test_trusted_benchmark_contract_remains_enforced(tmp_path):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    record = native_record(tmp_path, 'orca')
    target = tmp_path / 'native.inp'
    target.write_text('! Opt HF STO-3G LooseSCF\n* xyz 0 1\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n*\n')
    policy = MethodPolicy(allowed_methods=['hf/sto3g'], calculation_contracts={'ts_opt': {
        **QmCalculation(engine='orca', method='HF', basis_set='STO-3G', keywords='TightSCF').model_dump(),
        'task_type': [{'opt': 'ts'}]}})
    with use_pipeline_authority(lambda *_: (True, policy)), pytest.raises(ValueError, match='trusted'):
        process._check_calculation_submission(record, 'ts_opt', str(target), 'orca')


@pytest.mark.parametrize('absolute_name,trajectory', [(False, False), (True, True)])
def test_reused_orca_irc_consumes_only_hashed_endpoint_snapshots(tmp_path, absolute_name, trajectory):
    import json
    import shutil

    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process
    from cloudra.tools.Chemtool.ts_guess import TsGuess
    from cloudra.tools.core import orca_frames
    record = native_record(tmp_path, 'orca')
    original = tmp_path / 'prior'
    original.mkdir()
    source = original / 'irc.inp'
    source.write_text('! IRC HF STO-3G\n* xyz 0 1\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n*\n')
    db = ComputeDB().init()
    prior = create_process(db, request_key='prior', payload=dict(project_id='project', owner_id='owner',
        workspace_dir=str(tmp_path), input=record.input.model_dump(mode='json')))['process_id']
    job = bind_stage_job(db, process_id=prior, declaration_revision=1, stage_key='irc', attempt=1,
        job_payload=dict(conversation_id='project', session_id='owner', path=str(source), state='ready', jobtype='orca', node_id='fixture'))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
    log = Path(resolve_log_path(str(source), job_type='orca', task_id=job))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f'O   R   C   A\nNAME = {source if absolute_name else source.name}\n* FORWARD IRC *\n 0 -1.0 0.0 0.1 0.1\n* BACKWARD IRC *\n 0 -1.0 0.0 0.1 0.1\nORCA TERMINATED NORMALLY\n')
    seed = (Path(record.job_steps[-1].input_path).parent / 'optimized.xyz').read_text()
    for suffix, xyz in [('F', seed), ('B', seed.replace('H .96', 'H 1.06'))]:
        name = f'irc_IRC_{suffix}' + ('_trj.xyz' if trajectory else '.xyz')
        (original / name).write_text(seed + xyz if trajectory else xyz)
    record.input.verification.irc_log = str(log)
    step = process._reuse_existing_irc(record)
    record.job_steps.append(step)
    copied_log = step.external_source['log_path']
    shutil.rmtree(original)
    extracted = TsGuess._extract_irc_endpoints(copied_log, [], engine='orca',
        output_dir=str(tmp_path / 'verify'), require_two_sides=True)
    assert extracted is not None
    manifest_path = Path(copied_log).with_name('irc_endpoints.json')
    manifest = json.loads(manifest_path.read_text())
    bound = step.external_source['artifact_hashes']
    assert str(manifest_path) in bound
    assert manifest['atom_binding'] == step.atom_binding
    for endpoint in manifest['endpoints'].values():
        assert str(manifest_path.parent / endpoint['filename']) in bound
    endpoint_dir = tmp_path / 'endpoint'
    endpoint_dir.mkdir()
    error, path = process._write_endpoint_input(record, str(endpoint_dir), 'reactant', 'opt')
    assert not error and Path(path).is_file()
    assert process._step_state(record, step) == 'done'
    snapshot = manifest_path.parent / manifest['endpoints']['forward']['filename']
    snapshot.write_text(seed.replace('H .96', 'H 9.96'))
    assert process._step_state(record, step) == 'missing'
    with pytest.raises(ValueError, match='hash'):
        orca_frames.extract_irc_endpoints(copied_log)


@pytest.mark.parametrize('engine,keywords,blocks', [
    ('gaussian', 'opt=(ts', None),
    ('orca', 'OptTS TightSCF(', None),
    ('orca', 'OptTS', '%geom\n MaxIter 50'),
])
def test_native_lexical_advice_does_not_reject_or_rewrite_stage_input(tmp_path, engine, keywords, blocks):
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    record = native_record(tmp_path, engine, keywords, blocks)
    folder = tmp_path / 'refine'
    folder.mkdir()
    with use_pipeline_authority(lambda *_: (True, None)):
        error, path = process._write_refinement_input(record, str(folder))
        assert not error, error
        before = Path(path).read_bytes()
        assert keywords in before.decode()
        if blocks:
            assert blocks in before.decode()
        process._check_calculation_submission(record, 'ts_opt', path, engine)
    assert Path(path).read_bytes() == before
    assert record.warnings
    assert any(item['code'] in {'malformed_native_keywords', 'malformed_native_blocks'} for item in record.warnings)


def test_tool_receipt_replaces_resolved_advice_and_hides_stale_revisions(tmp_path):
    from cloudra.tools.Chemtool.ts_search_process import _to_output
    record = native_record(tmp_path, 'gaussian', 'opt=ts')
    folder = tmp_path / 'refine'
    folder.mkdir()
    error, _ = process._write_refinement_input(record, str(folder))
    assert not error and _to_output(record).warnings
    # Unchanged input re-rendering cannot duplicate receipt warnings.
    error, _ = process._write_refinement_input(record, str(folder))
    assert not error
    assert len(record.warnings) == len(_to_output(record).warnings)
    record.declaration_revision += 1
    record.input.ts_optimization.keywords = 'opt=(ts,calcfc)'
    assert not _to_output(record).warnings
    revised = tmp_path / 'revised'
    revised.mkdir()
    error, _ = process._write_refinement_input(record, str(revised))
    assert not error
    assert not _to_output(record).warnings


@pytest.mark.parametrize('engine,keywords', [('gaussian', 'opt=(ts'), ('orca', 'OptTS TightSCF(')])
def test_native_option_warnings_do_not_bypass_charge_identity(tmp_path, engine, keywords):
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    record = native_record(tmp_path, engine, keywords)
    folder = tmp_path / 'refine'
    folder.mkdir()
    with use_pipeline_authority(lambda *_: (True, None)):
        error, path = process._write_refinement_input(record, str(folder))
        assert not error, error
        target = Path(path)
        content = target.read_text()
        target.write_text(content.replace('* xyz 0 1', '* xyz 1 1') if engine == 'orca'
            else content.replace('\n0 1\n', '\n1 1\n'))
        with pytest.raises(ValueError, match='charge'):
            process._check_calculation_submission(record, 'ts_opt', path, engine)


@pytest.mark.parametrize('keywords', ['', 'opt=(modredundant,maxstep=4)', 'opt=(tight,maxstep=4)'])
def test_scan_does_not_choose_or_override_native_optimizer_settings(tmp_path, keywords):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    target = tmp_path / 'scan.gjf'
    request = TsGuess_input_schema(charge=0, mode='scan_prepare', engine='gaussian', method='HF',
        basis_set='STO-3G', keywords=keywords, input_text='3\nwater\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n',
        scans=[dict(atoms=[1, 2], scan_end=2, scan_steps=4)], output_path=str(target))
    result = TsGuess()._scan_prepare(request)
    assert result.is_success, result.message
    content = target.read_text()
    assert 'maxstep=10' not in content.lower()
    if keywords:
        assert keywords in content
        assert content.lower().count('opt=') == 1
    else:
        assert '#p opt=modredundant ' in content
    if keywords == 'opt=(tight,maxstep=4)':
        assert any(item['code'] == 'purpose_task_mismatch' for item in result.warnings)


@pytest.mark.parametrize('blocks', ['%geom\n MaxIter (\nend', '%geom Constraints { B x 1 1.0 C } end end'])
def test_unknown_native_option_classification_is_advice(tmp_path, blocks):
    record = native_record(tmp_path, 'orca', 'OptTS', blocks)
    directory = tmp_path / 'refine'
    directory.mkdir()
    error, path = process._write_refinement_input(record, str(directory))
    assert not error, error
    assert blocks in Path(path).read_text()
    assert any(item['code'] in {'native_task_uncertain', 'native_constraint_parameters'} for item in record.warnings)


@pytest.mark.parametrize('dropped', ['OptTS', 'TightSCF'])
def test_ts_renderer_cannot_silently_drop_declared_tasks_or_options(tmp_path, monkeypatch, dropped):
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter
    record = native_record(tmp_path, 'orca', 'OptTS TightSCF')
    directory = tmp_path / 'refine'
    directory.mkdir()
    original = QmInputWriter.render_input
    monkeypatch.setattr(QmInputWriter, 'render_input', staticmethod(lambda *args: original(*args).replace(dropped, '')))
    error, path = process._write_refinement_input(record, str(directory))
    assert error and not path
    assert 'internal' in error.lower()
    assert not (directory / 'refine.inp').exists()


@pytest.mark.parametrize('engine,keywords,contract_task', [
    ('gaussian', 'opt=ts', {'opt': 'ts,readfc'}),
    ('orca', 'OptTS', {'EnGrad': None}),
])
def test_trusted_contract_includes_exact_native_task_parameters(tmp_path, engine, keywords, contract_task):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    record = native_record(tmp_path, engine, keywords)
    directory = tmp_path / 'refine'
    directory.mkdir()
    error, path = process._write_refinement_input(record, str(directory))
    assert not error
    policy = MethodPolicy(allowed_methods=['hf/sto3g'], calculation_contracts={'ts_opt': {
        **QmCalculation(engine=engine, method='HF', basis_set='STO-3G').model_dump(),
        'task_type': [contract_task]}})
    with use_pipeline_authority(lambda *_: (True, policy)), pytest.raises(ValueError, match='trusted'):
        process._check_calculation_submission(record, 'ts_opt', path, engine)


def test_scan_renderer_cannot_silently_drop_declared_options(tmp_path, monkeypatch):
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    target = tmp_path / 'scan.gjf'
    request = TsGuess_input_schema(charge=0, mode='scan_prepare', engine='gaussian', method='HF',
        basis_set='STO-3G', keywords='SCF=Tight', input_text='3\nwater\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n',
        scans=[dict(atoms=[1, 2], scan_end=2, scan_steps=4)], output_path=str(target))
    original = QmInputWriter.render_input
    monkeypatch.setattr(QmInputWriter, 'render_input', staticmethod(lambda *args: original(*args).replace('SCF=Tight', '')))
    result = TsGuess()._scan_prepare(request)
    assert not result.is_success
    assert 'internal' in result.message.lower()
    assert not target.exists()


@pytest.mark.parametrize('engine,settings,warning', [
    ('orca', {'end_setting': 'SCF=Tight'}, 'gaussian_only_field'),
    ('gaussian', {'orca_blocks': '%scf MaxIter 50 end'}, 'orca_only_field'),
    ('orca', {'orca_blocks': '%geom\n MaxIter (\nend'}, 'malformed_native_blocks'),
    ('orca', {'orca_blocks': '%geom MaxIter 50 end'}, 'scan_native_geometry_block'),
    ('orca', {'frequency_mode': 'numeric'}, 'frequency_mode_without_frequency'),
])
def test_scan_preserves_native_advice_instead_of_early_rejection(tmp_path, engine, settings, warning):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    target = tmp_path / ('scan.inp' if engine == 'orca' else 'scan.gjf')
    request = TsGuess_input_schema(charge=0, mode='scan_prepare', engine=engine, method='HF',
        basis_set='STO-3G', input_text='3\nwater\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n',
        scans=[dict(atoms=[0, 1] if engine == 'orca' else [1, 2], scan_end=2, scan_steps=4)],
        output_path=str(target), **settings)
    result = TsGuess()._scan_prepare(request)
    assert result.is_success, result.message
    content = target.read_text()
    for field in ('end_setting', 'orca_blocks'):
        if settings.get(field):
            assert settings[field] in content
    assert any(item['code'] == warning and item['severity'] == 'warning' for item in result.warnings)
    if engine == 'orca':
        assert 'Scan' in content and 'B 0 1' in content
    else:
        assert 'B 1 2 S 4' in content


def test_scan_preserves_native_resource_blocks_for_shared_engineering_admission(tmp_path):
    from cloudra.services.compute_admission import _read_declared_requirements
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    target = tmp_path / 'scan.inp'
    native = '%pal nprocs 2 end'
    request = TsGuess_input_schema(charge=0, mode='scan_prepare', engine='orca', method='HF',
        basis_set='STO-3G', nproc=1, orca_blocks=native,
        input_text='3\nwater\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n',
        scans=[dict(atoms=[0, 1], scan_end=2, scan_steps=4)], output_path=str(target))
    result = TsGuess()._scan_prepare(request)
    assert result.is_success, result.message
    assert native in target.read_text()
    with pytest.raises(ValueError, match='Conflicting resource declarations'):
        _read_declared_requirements('orca', str(target))
