import pytest
from pydantic import ValidationError


def calculation(**changes):
    from cloudra.tools.core.qm_calculation import QmCalculation

    return QmCalculation(engine='orca', method='B3LYP', basis_set='def2-SVP', **changes)


@pytest.mark.parametrize('payload', [
    {'method': 'B3LYP', 'basis_set': 'def2-SVP'},
    {'engine': 'orca', 'basis_set': 'def2-SVP'},
    {'engine': 'orca', 'method': 'B3LYP'},
])
def test_complete_calculation_requires_explicit_engine_method_and_basis(payload):
    from cloudra.tools.core.qm_calculation import QmCalculation

    with pytest.raises(ValidationError):
        QmCalculation.model_validate(payload)


@pytest.mark.parametrize('method', ['B3LYP/def2-SVP', 'HF/STO-3G', 'HF/sto3g', 'B3LYP/ccpVDZ', 'B3LYP/6-31G(d)',
                                   'B3LYP def2-SVP', 'B3LYP\nD3BJ', 'def2-SVP'])
def test_method_preserves_inline_basis_or_native_route_text_for_tool_advice(method):
    from cloudra.tools.core.qm_calculation import QmCalculation

    assert QmCalculation(engine='orca', method=method, basis_set='def2-SVP').method == method


def test_method_requires_nonempty_structural_value():
    from cloudra.tools.core.qm_calculation import QmCalculation

    with pytest.raises(ValidationError, match='method'):
        QmCalculation(engine='orca', method=' ', basis_set='def2-SVP')


@pytest.mark.parametrize('engine,method', [('orca', 'B3LYP/G'), ('orca', 'ExtOpt'),
                                         ('gaussian', 'external'), ('orca', 'B97-3c'),
                                         ('xtb', 'GFN2-xTB')])
def test_native_no_basis_method_identity_is_preserved(engine, method):
    from cloudra.tools.core.qm_calculation import QmCalculation

    result = QmCalculation(engine=engine, method=method, basis_set='')
    assert result.method == method and result.basis_set == ''


@pytest.mark.parametrize('engine,settings', [
    ('xtb', {'keywords': 'TightSCF'}),
    ('xtb', {'basis_set': 'def2-SVP'}),
])
def test_engine_incompatible_scientific_fields_fail_loudly(engine, settings):
    from cloudra.tools.core.qm_calculation import QmCalculation

    payload = {'engine': engine, 'method': 'GFN2-xTB' if engine == 'xtb' else 'HF', 'basis_set': ''}
    with pytest.raises(ValidationError):
        QmCalculation.model_validate({**payload, **settings})


@pytest.mark.parametrize('engine,settings', [
    ('gaussian', {'orca_blocks': '%scf MaxIter 200 end'}),
    ('orca', {'end_setting': 'native trailing directives'}),
])
def test_other_engine_native_fields_are_retained_for_visible_tool_advice(engine, settings):
    from cloudra.tools.core.qm_calculation import QmCalculation

    value = QmCalculation(engine=engine, method='HF', basis_set='', **settings)
    for field, original in settings.items():
        assert getattr(value, field) == original


def test_shared_keyword_settings_are_preserved_without_policy_defaults():
    result = calculation(keywords='D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)',
                         orca_blocks='%scf MaxIter 200 end')
    assert result.keywords == 'D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)'
    assert result.orca_blocks == '%scf MaxIter 200 end'


def test_old_keyword_field_is_not_a_compatibility_alias():
    from cloudra.tools.core.qm_calculation import QmCalculation

    with pytest.raises(ValidationError):
        QmCalculation(engine='orca', method='B3LYP', basis_set='def2-SVP', extra_keywords='D3BJ')


def test_harmless_edge_whitespace_is_normalized_without_inferring_fields():
    from cloudra.tools.core.qm_calculation import QmCalculation

    value = QmCalculation(engine='orca', method=' B3LYP/G ', basis_set=' def2svp ')
    assert value.method == 'B3LYP/G' and value.basis_set == 'def2svp'


@pytest.mark.parametrize('basis_set', ['', 'def2-SVP'])
@pytest.mark.parametrize('keyword', ['def2-SVP', 'DEF2SVP', 'STO-3G', '6-31G(d)', 'cc-pVDZ', 'B3LYP/def2-SVP'])
def test_keywords_preserve_orbital_basis_for_tool_advice(basis_set, keyword):
    from cloudra.tools.core.qm_calculation import QmCalculation

    value = QmCalculation(engine='orca', method='B3LYP', basis_set=basis_set,
                          keywords=f'D3BJ {keyword} TightSCF')
    assert value.keywords == f'D3BJ {keyword} TightSCF'


@pytest.mark.parametrize('auxiliary', ['def2/J', 'def2/JK', 'def2/JKsmall', 'cc-pVDZ/C'])
def test_keywords_preserve_auxiliary_bases_and_native_solvent_settings(auxiliary):
    value = calculation(keywords=f'D3BJ RIJCOSX {auxiliary} TightSCF CPCM(DCM)')
    assert value.keywords == f'D3BJ RIJCOSX {auxiliary} TightSCF CPCM(DCM)'


def test_unknown_native_keywords_are_not_guessed_to_be_an_orbital_basis():
    value = calculation(keywords='UnknownNativeFeature CPCM(DCM)')
    assert value.keywords == 'UnknownNativeFeature CPCM(DCM)'
