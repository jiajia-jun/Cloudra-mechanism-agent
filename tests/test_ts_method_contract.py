import pytest

from cloudra.tools.core import calculation_intent as intent
from cloudra.tools.core.molecule import read_molecule


@pytest.mark.parametrize('solvent', ['DCM', 'Water', 'DMSO'])
def test_cpcm_ts_submission_keeps_native_settings_and_bound_job(tmp_path, monkeypatch, solvent):
    """Synthetic coordinates exercise submission contracts, without running an engine."""
    from pathlib import Path

    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.compute_store import get_compute_job
    from cloudra.services.ts_pipeline_context import use_pipeline_authority, use_pipeline_database
    from cloudra.services.ts_pipeline_store import create_process, verify_stage_input
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core.ts_inputs import QmCalculation
    from cloudra.tools.core.ts_process import _submit_step
    from tests.test_ts_pipeline_store import payload
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path)
    record.input.execution.cpus = 2
    record.input.execution.memory_mb = 2048
    keywords = f'D3BJ RIJCOSX def2/J TightSCF CPCM({solvent})'
    calculation = QmCalculation(basis_set='def2svp', engine='orca', method='B3LYP', keywords=keywords)
    record.input.ts_optimization = calculation
    source = tmp_path / 'ts.inp'
    request = QmInputWriter_input_schema(engine='orca', source_type='xyz_file', source_value='unused.xyz',
        method='B3LYP', basis_set='def2svp', task_type=[{'opt': 'ts'}], keywords=keywords,
        nproc=record.compute_cpus, mem=f'{record.compute_memory_mb}MB', output_path=str(source))
    native = QmInputWriter._build_orca_input(request, read_molecule(input_text='1\n\nO 0 0 0\n'))
    source.write_text(native)
    policy = MethodPolicy(allowed_methods=['b3lyp/def2svp'],
        calculation_contracts={'ts_opt': calculation.model_dump(mode='json')})
    admissions = []

    def admit(**parameters):
        admissions.append(parameters)
        return AdmissionOutcome(ok=True, node_id='fixture', scheduler='local')

    monkeypatch.setattr('cloudra.services.compute_admission.admit_job', admit)
    db = ComputeDB().init()
    record.pipeline_id = create_process(db, request_key=f'cpcm-{solvent}',
        payload=payload(workspace_dir=str(tmp_path), input=record.input.model_dump()))['process_id']
    with use_pipeline_database(db), use_pipeline_authority(lambda *_: (True, policy)):
        error, job_id = _submit_step(record, 'ts_opt', str(source), 'orca')
    assert not error and job_id > 0
    assert admissions == [dict(input_file=str(source), job_type='orca', cpus=2, memory_mb=2048,
                               execution_backend='auto')]
    job = get_compute_job(db, job_id)
    assert (job['state'], job['jobtype'], job['req_cpus'], job['req_memory_mb']) == ('ready', 'orca', 2, 2048)
    assert Path(job['path']).read_text() == native
    tokens, blocks = intent.orca_directives(native)
    assert set(tokens) >= set(keywords.lower().split())
    assert blocks['pal'] == ['nprocs', '2', 'end']
    assert blocks['maxcore'] == ['1024']
    assert intent.compare_calculation_input(native, calculation.model_dump(), charge=0, multiplicity=1) == []
    assert verify_stage_input(db, job_id) is not None
    assert record.method_checks[str(source)]['matched'] is True


def test_ordinary_ts_submission_needs_no_method_policy(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_inputs import QmCalculation
    from cloudra.tools.core.ts_process import _submit_step
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path)
    record.input.ts_optimization = QmCalculation(basis_set='def2-TZVP', engine="orca", method='PBE0', keywords="")
    source = tmp_path / "ts.inp"
    source.write_text("! OptTS PBE0 def2-TZVP\n* xyz 0 1\nO 0 0 0\n*\n")
    monkeypatch.setattr("cloudra.services.compute_admission.admit_job", lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"))
    with use_pipeline_authority(lambda project, owner: (True, None)):
        error, job_id = _submit_step(record, "ts_opt", str(source), "orca")
    assert not error and job_id > 0
    assert record.method_checks[str(source)]["matched"]


def test_runtime_method_authority_is_benchmark_only(tmp_path):
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import AgentSession, MethodPolicy, Project, ProjectSettings
    from cloudra.services.ts_pipeline_context import require_pipeline_authority, use_runtime_authority

    core = RuntimeCore()
    policy = MethodPolicy(allowed_methods=["xtb"])
    project = Project(id="project", name="ordinary", settings=ProjectSettings(method_policy=policy))
    agent = AgentSession(id="owner", project_id=project.id, role_id="small_mol", display_name="owner")
    agent.capabilities.permissions.write = True
    core.projects[project.id] = project
    core.agents[agent.id] = agent
    with use_runtime_authority(core):
        assert require_pipeline_authority(project.id, agent.id) is None
        project.settings.benchmark_task_id = "fixture"
        assert require_pipeline_authority(project.id, agent.id) == policy
        project.settings.method_policy = None
        import pytest
        with pytest.raises(ValueError, match="Benchmark"):
            require_pipeline_authority(project.id, agent.id)
        project.settings.benchmark_task_id = None
        agent.capabilities.permissions.write = False
        with pytest.raises(ValueError, match="write permission"):
            require_pipeline_authority(project.id, agent.id)


def test_ordinary_ts_records_native_declaration_differences(tmp_path):

    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_process import _check_calculation_submission
    from tests.test_ts_stage_inputs import record_fixture

    source = tmp_path / "ts.inp"
    source.write_text("! OptTS PBE0 def2-TZVP\n* xyz 0 1\nO 0 0 0\n*\n")
    record = record_fixture(tmp_path)
    with use_pipeline_authority(lambda project, owner: (True, None)):
        _check_calculation_submission(record, "ts_opt", str(source), "orca")
    assert not record.method_checks[str(source)]['matched']
    assert any(item['field'] == 'method' for item in record.warnings)


def expected(engine='orca', **changes):
    return dict(basis_set='def2-SVP', engine=engine, method='B3LYP', keywords='D3BJ CPCM(water)', frequency_mode='auto', orca_blocks=None, end_setting='', **changes)


def test_missing_required_keywords_and_actual_charge_spin_are_differences():
    differences = intent.compare_calculation_input('! OptTS B3LYP def2SVP\n* xyz -1 3\nO 0 0 0\n*\n', expected(), charge=0, multiplicity=1)
    assert {entry.field for entry in differences} >= {'keywords', 'charge', 'multiplicity'}


def test_equivalent_basis_spelling_and_multiline_native_input():
    text = '! OptTS B3LYP\n! def2SVP D3BJ CPCM(water)\n%pal nprocs 2 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert intent.compare_calculation_input(text, expected(), charge=0, multiplicity=1) == []
    gaussian = '#p opt=(ts, calcfc) B3LYP/def2svp\n emp=gd3bj scrf=(solvent=water)\n\ntitle\n\n0 1\nO 0 0 0\n\n'
    declaration = dict(basis_set='def2-SVP', engine='gaussian', method='B3LYP', keywords='emp=gd3bj scrf=(solvent=water)', frequency_mode='auto', orca_blocks=None, end_setting='')
    assert intent.compare_calculation_input(gaussian, declaration, charge=0, multiplicity=1) == []


def test_unknown_extra_method_or_settings_do_not_pass():
    text = '! OptTS B3LYP def2SVP D3BJ CPCM(water) PBE0\n%cpcm epsilon 20 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert {entry.field for entry in intent.compare_calculation_input(text, expected(), charge=0, multiplicity=1)} >= {'keywords', 'orca_blocks'}


def test_native_blocks_and_gaussian_links_are_all_checked():
    declaration = dict(basis_set='def2svp', engine='orca', method='B3LYP', keywords='', frequency_mode='auto', orca_blocks='%cpcm\n epsilon 20\nend', end_setting='')
    text = '! Freq B3LYP def2-SVP\n%cpcm epsilon 30 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert any(d.field == 'orca_blocks' for d in intent.compare_calculation_input(text, declaration, charge=0, multiplicity=1))
    gaussian = '#p B3LYP/def2svp freq\n\ntitle\n\n0 1\nO 0 0 0\n\n--Link1--\n#p PBE0/def2svp freq\n\ntitle\n\n0 1\nO 0 0 0\n\n'
    declaration = dict(basis_set='def2svp', engine='gaussian', method='B3LYP', keywords='', frequency_mode='auto', end_setting='')
    assert any(d.field == 'method' for d in intent.compare_calculation_input(gaussian, declaration, charge=0, multiplicity=1))


def test_trusted_method_is_enforced_while_declared_keyword_differences_warn(tmp_path, monkeypatch):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_process import _check_calculation_submission, _submit_step
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path)
    source = tmp_path / 'ts.inp'
    source.write_text('! OptTS B3LYP def2SVP\n* xyz 0 1\nO 0 0 0\n*\n')
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job', lambda **_: (_ for _ in ()).throw(AssertionError('must reject before admission')))
    with use_pipeline_authority(lambda project, owner: (True, MethodPolicy(allowed_methods=['b3lyp/def2svp']))):
        _check_calculation_submission(record, 'ts_opt', str(source), 'orca')
    assert any(item['field'] == 'keywords' for item in record.warnings)
    source.write_text('! OptTS B3LYP def2SVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n')
    with use_pipeline_authority(lambda project, owner: (True, MethodPolicy(allowed_methods=['xtb']))):
        error, job_id = _submit_step(record, 'ts_opt', str(source), 'orca')
    assert job_id == -1 and 'allowed_methods' in error


def test_authorized_semiempirical_scan_differs_from_formal_method(tmp_path, monkeypatch):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_process import _submit_step
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path)
    source = tmp_path / 'scan.inp'
    source.write_text('! Opt GFN2-xTB\n%geom Scan B 0 1 = 1.0, 2.0, 7 end end\n* xyz 0 1\nO 0 0 0\n*\n')
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job', lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    with use_pipeline_authority(lambda project, owner: (True, MethodPolicy(allowed_methods=['xtb','b3lyp/def2svp']))):
        error, job_id = _submit_step(record, 'scan', str(source), 'orca')
    assert not error and job_id > 0
    assert record.input.ts_optimization.method != record.input.guess.calculation.method


def test_unknown_trusted_method_source_is_a_checkpoint(tmp_path):
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_process import _submit_step
    from tests.test_ts_stage_inputs import record_fixture
    source = tmp_path / 'ts.inp'
    source.write_text('! OptTS B3LYP def2SVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n')
    with use_pipeline_authority(None):
        error, job_id = _submit_step(record_fixture(tmp_path), 'ts_opt', str(source), 'orca')
    assert job_id == -1 and 'authorization' in error


def test_undeclared_frequency_block_and_gaussian_trailing_settings_are_differences():
    declaration=dict(basis_set='STO-3G', engine='orca',method='HF',keywords='',orca_blocks=None,end_setting='')
    text='! HF STO-3G Freq\n%freq Temp 999 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert intent.compare_calculation_input(text,declaration,charge=0,multiplicity=1)
    declaration['engine']='gaussian'
    text='#p HF/STO-3G Freq\n\ntitle\n\n0 1\nO 0 0 0\n\nHidden scientific setting\n'
    assert intent.compare_calculation_input(text,declaration,charge=0,multiplicity=1)


def test_unrequested_hessian_setting_is_a_real_native_difference():
    declaration=dict(basis_set='STO-3G', engine='orca',method='HF',keywords='',orca_blocks='%geom MaxIter 200 end',end_setting='')
    text='! HF STO-3G OptTS\n%geom Calc_Hess true end\n%geom MaxIter 200 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert any(item.field == 'orca_blocks' for item in
        intent.compare_calculation_input(text,declaration,charge=0,multiplicity=1))


def test_whitelist_checks_complete_native_method_and_explicit_basis(tmp_path):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_inputs import QmCalculation
    from cloudra.tools.core.ts_process import _check_calculation_submission
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path)
    record.input.ts_optimization = QmCalculation(basis_set='def2-SVP', engine="orca", method="B3LYP", keywords="D3BJ")
    source = tmp_path / "ts.inp"
    source.write_text("! OptTS B3LYP def2-SVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n")
    policy = MethodPolicy(allowed_methods=["b3lyp/def2svp"])
    with use_pipeline_authority(lambda project, owner: (True, policy)):
        _check_calculation_submission(record, "ts_opt", str(source), "orca")
    assert record.method_checks[str(source)]["matched"]
    for basis_set, keywords, text in [
        ("", "D3BJ", "! OptTS B3LYP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n"),
        ("def2-TZVP", "D3BJ", "! OptTS B3LYP def2-TZVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n"),
        ("def2-SVP", "D3BJ PBE0", "! OptTS B3LYP PBE0 def2-SVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n"),
    ]:
        record.input.ts_optimization = QmCalculation(basis_set=basis_set, engine="orca", method="B3LYP", keywords=keywords)
        source.write_text(text)
        with use_pipeline_authority(lambda project, owner: (True, policy)):
            import pytest
            with pytest.raises(ValueError, match="allowed_methods"):
                _check_calculation_submission(record, "ts_opt", str(source), "orca")


def test_native_whitelist_recognizes_explicit_hf_instead_of_discarding_it():
    from cloudra.runtime_v2.method_policy import check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    text = "! OptTS HF STO-3G\n* xyz 0 1\nO 0 0 0\n*\n"
    assert check_input_content(text, MethodPolicy(allowed_methods=["hf/sto3g"]), filename="ts.inp", strict=True).allowed
    assert not check_input_content(text, MethodPolicy(allowed_methods=["b3lyp/def2svp"]), filename="ts.inp", strict=True).allowed
    mixed = "! OptTS B3LYP HF def2-SVP\n* xyz 0 1\nO 0 0 0\n*\n"
    assert not check_input_content(mixed, MethodPolicy(allowed_methods=["b3lyp/def2svp"]), filename="ts.inp", strict=True).allowed
