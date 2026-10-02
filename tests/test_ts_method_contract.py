from cloudra.tools.core import calculation_intent as intent


def expected(engine='orca', **changes):
    return dict(engine=engine, method='B3LYP/def2-SVP', keywords='D3BJ CPCM(water)', frequency_mode='auto', orca_blocks=None, end_setting='', **changes)


def test_missing_required_keywords_and_actual_charge_spin_are_differences():
    differences = intent.compare_calculation_input('! OptTS B3LYP def2SVP\n* xyz -1 3\nO 0 0 0\n*\n', expected(), charge=0, multiplicity=1)
    assert {entry.field for entry in differences} >= {'keywords', 'charge', 'multiplicity'}


def test_equivalent_basis_spelling_and_multiline_native_input():
    text = '! OptTS B3LYP\n! def2SVP D3BJ CPCM(water)\n%pal nprocs 2 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert intent.compare_calculation_input(text, expected(), charge=0, multiplicity=1) == []
    gaussian = '#p opt=(ts, calcfc) B3LYP/def2svp\n emp=gd3bj scrf=(solvent=water)\n\ntitle\n\n0 1\nO 0 0 0\n\n'
    declaration = dict(engine='gaussian', method='B3LYP/def2-SVP', keywords='emp=gd3bj scrf=(solvent=water)', frequency_mode='auto', orca_blocks=None, end_setting='')
    assert intent.compare_calculation_input(gaussian, declaration, charge=0, multiplicity=1) == []


def test_unknown_extra_method_or_settings_do_not_pass():
    text = '! OptTS B3LYP def2SVP D3BJ CPCM(water) PBE0\n%cpcm epsilon 20 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert {entry.field for entry in intent.compare_calculation_input(text, expected(), charge=0, multiplicity=1)} >= {'keywords', 'orca_blocks'}


def test_native_blocks_and_gaussian_links_are_all_checked():
    declaration = dict(engine='orca', method='B3LYP/def2svp', keywords='', frequency_mode='auto', orca_blocks='%cpcm\n epsilon 20\nend', end_setting='')
    text = '! Freq B3LYP def2-SVP\n%cpcm epsilon 30 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert any(d.field == 'orca_blocks' for d in intent.compare_calculation_input(text, declaration, charge=0, multiplicity=1))
    gaussian = '#p B3LYP/def2svp freq\n\ntitle\n\n0 1\nO 0 0 0\n\n--Link1--\n#p PBE0/def2svp freq\n\ntitle\n\n0 1\nO 0 0 0\n\n'
    declaration = dict(engine='gaussian', method='B3LYP/def2svp', keywords='', frequency_mode='auto', end_setting='')
    assert any(d.field == 'method' for d in intent.compare_calculation_input(gaussian, declaration, charge=0, multiplicity=1))


def test_unauthorized_method_and_missing_keyword_block_before_ready(tmp_path, monkeypatch):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_process import _submit_step
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path)
    source = tmp_path / 'ts.inp'
    source.write_text('! OptTS B3LYP def2SVP\n* xyz 0 1\nO 0 0 0\n*\n')
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job', lambda **_: (_ for _ in ()).throw(AssertionError('must reject before admission')))
    with use_pipeline_authority(lambda project, owner: (True, MethodPolicy(allowed_methods=['b3lyp/def2svp']))):
        error, job_id = _submit_step(record, 'ts_opt', str(source), 'orca')
    assert job_id == -1 and 'keywords' in error
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
    declaration=dict(engine='orca',method='HF/STO-3G',keywords='',orca_blocks=None,end_setting='')
    text='! HF STO-3G Freq\n%freq Temp 999 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert intent.compare_calculation_input(text,declaration,charge=0,multiplicity=1)
    declaration['engine']='gaussian'
    text='#p HF/STO-3G Freq\n\ntitle\n\n0 1\nO 0 0 0\n\nHidden scientific setting\n'
    assert intent.compare_calculation_input(text,declaration,charge=0,multiplicity=1)


def test_explicit_geometry_block_can_coexist_with_writer_hessian():
    declaration=dict(engine='orca',method='HF/STO-3G',keywords='',orca_blocks='%geom MaxIter 200 end',end_setting='')
    text='! HF STO-3G OptTS\n%geom Calc_Hess true end\n%geom MaxIter 200 end\n* xyz 0 1\nO 0 0 0\n*\n'
    assert intent.compare_calculation_input(text,declaration,charge=0,multiplicity=1)==[]


def test_whitelist_checks_complete_native_method_when_basis_is_in_keywords(tmp_path):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_inputs import TsCalculation
    from cloudra.tools.core.ts_process import _check_calculation_submission
    from tests.test_ts_stage_inputs import record_fixture

    record = record_fixture(tmp_path)
    record.input.ts_optimization = TsCalculation(engine="orca", method="B3LYP", keywords="D3BJ def2-SVP")
    source = tmp_path / "ts.inp"
    source.write_text("! OptTS B3LYP def2-SVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n")
    policy = MethodPolicy(allowed_methods=["b3lyp/def2svp"])
    with use_pipeline_authority(lambda project, owner: (True, policy)):
        _check_calculation_submission(record, "ts_opt", str(source), "orca")
    assert record.method_checks[str(source)]["matched"]
    for keywords, text in [
        ("D3BJ", "! OptTS B3LYP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n"),
        ("D3BJ def2-TZVP", "! OptTS B3LYP def2-TZVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n"),
        ("D3BJ def2-SVP PBE0", "! OptTS B3LYP PBE0 def2-SVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n"),
    ]:
        record.input.ts_optimization = TsCalculation(engine="orca", method="B3LYP", keywords=keywords)
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
