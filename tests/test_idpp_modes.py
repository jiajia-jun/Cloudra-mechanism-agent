"""Small deterministic geometry tests: no QM or model calls."""
import numpy as np
import pytest
from ase import Atoms
from ase.mep import NEB
from ase.mep.neb import idpp_interpolate

from cloudra.tools.Chemtool.ts_guess import TsGuess_input_schema, _idpp_relax


def band():
    start = np.array([[0., 0., 0.], [1.2, 0., 0.], [0., 1.1, .2]])
    end = np.array([[0., 0., 0.], [1.5, .3, 0.], [.2, 1.4, .4]])
    return np.linspace(start, end, 5)


def test_default_mode_and_enum():
    request = TsGuess_input_schema(mode='interpolate', reactant_text='r', product_text='p')
    assert request.idpp_mode == 'standard'
    with pytest.raises(ValueError):
        TsGuess_input_schema(mode='interpolate', reactant_text='r', product_text='p', idpp_mode='bad')


def test_standard_matches_official_ase():
    initial = band()
    expected = [Atoms('H3', positions=p) for p in initial]
    idpp_interpolate(NEB(expected, method='improvedtangent'), traj=None, log=None, steps=8, fmax=1e-7)
    actual, report = _idpp_relax(initial, max_iter=8, tol=1e-7)
    np.testing.assert_allclose(actual, [a.positions for a in expected], atol=1e-13)
    np.testing.assert_array_equal(actual[[0, -1]], initial[[0, -1]])
    assert report['idpp_mode'] == 'standard'
    assert report['converged'] is False
    assert report['termination'] == 'max_steps'
    assert report['steps'] == 8


def test_zero_budget_is_not_convergence():
    _, report = _idpp_relax(band(), max_iter=0, tol=1e-12)
    assert report['converged'] is False
    assert report['steps'] == 0


def test_two_endpoints_do_not_claim_relaxation():
    actual, report = _idpp_relax(band()[[0, -1]])
    assert len(actual) == 2
    assert report['converged'] is None
    assert report['termination'] == 'not_required'


def test_colliding_standard_band_fails_loud():
    initial = band()
    initial[2, 1] = initial[2, 0]
    with pytest.raises(ValueError, match='coincident'):
        _idpp_relax(initial)


@pytest.mark.parametrize('steps', [0, 8, 4000])
def test_light_matches_pre_change_numerical_fixture(steps):
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parent / 'fixtures/idpp_light_reference.json').read_text())
    expected = next(c['expected'] for c in data['cases'] if c['steps'] == steps)
    actual, report = _idpp_relax(data['images'], mode='light', **({} if steps == 4000 else {'max_iter': steps}))
    np.testing.assert_array_equal(actual, expected)
    assert report['idpp_mode'] == 'light'
    assert report['objective'] == 'fixed_target_distance^-4'
    if steps == 0:
        assert report['converged'] is False
        assert report['termination'] == 'max_steps'


def test_light_already_relaxed():
    initial = np.repeat(band()[:1], 4, axis=0)
    actual, report = _idpp_relax(initial, mode='light')
    np.testing.assert_array_equal(actual, initial)
    assert report['steps'] == 0
    assert report['converged'] is True


def test_old_results_do_not_invent_method_or_convergence():
    from cloudra.tools.Chemtool.ts_guess import TsGuess_output_schema
    result = TsGuess_output_schema.model_validate({'is_success': True, 'images_dir': 'old'})
    assert result.interpolation is None


@pytest.mark.parametrize('mode', ['standard', 'light'])
def test_generated_but_unconverged_is_recorded(tmp_path, monkeypatch, mode):
    import importlib
    import json

    Chem = pytest.importorskip("rdkit.Chem")
    module = importlib.import_module('cloudra.tools.Chemtool.ts_guess')
    relax = module._idpp_relax
    monkeypatch.setattr(module, '_idpp_relax', lambda images, mode: relax(images, mode=mode, max_iter=0, tol=1e-12))
    molecules = []
    for positions in (band()[0], band()[-1]):
        mol = Chem.MolFromSmiles('COF')
        conf = Chem.Conformer(3)
        for index, position in enumerate(positions):
            conf.SetAtomPosition(index, position)
        mol.AddConformer(conf)
        molecules.append(mol)
    result = module.TsGuess()._interpolate_molecules(
        TsGuess_input_schema(mode='interpolate', reactant_text='r', product_text='p',
                             n_images=5, idpp_mode=mode, output_dir=str(tmp_path)), *molecules)
    assert result.is_success is True
    assert result.interpolation['converged'] is False
    assert result.interpolation['termination'] == 'max_steps'
    assert json.loads((tmp_path / 'interpolation.json').read_text()) == result.interpolation
    assert len(list(tmp_path.glob('img_*.xyz'))) == 5
    assert 'not convergence or TS verification' in result.message


def test_identical_colliding_standard_band_also_fails():
    initial = np.zeros((4, 3, 3))
    with pytest.raises(ValueError, match='coincident'):
        _idpp_relax(initial)


@pytest.mark.parametrize('mode', ['standard', 'light'])
def test_nonfinite_input_fails(mode):
    initial = band()
    initial[2, 0, 0] = np.nan
    with pytest.raises(ValueError, match='finite'):
        _idpp_relax(initial, mode=mode)
