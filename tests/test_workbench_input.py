import pytest

pytest.importorskip('rdkit')
from cloudra.tools.core.molecule import read_molecule
from cloudra.tools.core.workbench_input import render_workbench_input

XYZ = '3\n\nO 0 0 0\nH 1 0 0\nH 0 1 0\n'


def settings(engine):
    return dict(engine=engine, method='HF', basis_set='STO-3G', charge=0, multiplicity=1)


@pytest.mark.parametrize('engine,freeze,scan', [
    ('gaussian', 'B 1 2 1.100000 F', 'B 1 3 S 3 0.200000'),
    ('orca', '{ B 0 1 1.100000 C }', 'B 0 2 = 1.000000, 1.600000, 3'),
])
def test_confirmed_freeze_targets_and_scans_use_native_numbering(engine, freeze, scan, tmp_path):
    mol = read_molecule(input_text=XYZ, input_format='xyz')
    content = render_workbench_input(mol, settings(engine),
        [dict(coord_type='bond', atoms=[1, 2], value=1.1)],
        [dict(coord_type='bond', atoms=[1, 3], scan_end=1.6, scan_steps=3)],
        str(tmp_path / ('input.gjf' if engine == 'gaussian' else 'input.inp')))
    assert freeze in content and scan in content
    assert not list(tmp_path.iterdir())


def test_orca_multiple_coordinates_are_independent_pes_and_preserve_native_blocks(tmp_path):
    content = render_workbench_input(read_molecule(input_text=XYZ, input_format='xyz'),
        settings('orca') | dict(keywords='TightSCF', orca_blocks='%scf MaxIter 300 end'), [],
        [dict(coord_type='bond', atoms=[1, 2], scan_end=2, scan_steps=3),
         dict(coord_type='bond', atoms=[1, 3], scan_end=2, scan_steps=5)], str(tmp_path / 'input.inp'))
    assert 'TightSCF' in content and '%scf MaxIter 300 end' in content
    assert 'Simul_Scan' not in content and 'B 0 1' in content and 'B 0 2' in content


@pytest.mark.parametrize('missing', ['engine', 'method', 'basis_set', 'charge', 'multiplicity'])
def test_generation_requires_explicit_scientific_inputs(missing, tmp_path):
    values = settings('gaussian')
    values.pop(missing)
    with pytest.raises(ValueError, match=missing):
        render_workbench_input(read_molecule(input_text=XYZ, input_format='xyz'), values, [], [], str(tmp_path / 'x.gjf'))


def test_gaussian_refuses_scan_start_different_from_actual_geometry(tmp_path):
    with pytest.raises(ValueError, match='start_geometry_mismatch'):
        render_workbench_input(read_molecule(input_text=XYZ, input_format='xyz'), settings('gaussian'), [],
            [dict(coord_type='bond', atoms=[1, 2], scan_start=1.5, scan_end=2, scan_steps=3)],
            str(tmp_path / 'x.gjf'))


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_freeze_refuses_frequency_only_instead_of_switching_task(engine, tmp_path):
    with pytest.raises(ValueError, match='optimization task'):
        render_workbench_input(read_molecule(input_text=XYZ, input_format='xyz'),
            settings(engine) | {'task_type': [{'freq': None}]},
            [dict(coord_type='bond', atoms=[1, 2], value=1.1)], [], str(tmp_path / 'input'))


@pytest.mark.parametrize('engine,expected', [
    ('gaussian', 'opt=(TS,CalcFC,ModRedundant)'), ('orca', 'OptTS CalcFC'),
])
def test_freeze_preserves_explicit_ts_task_and_options(engine, expected, tmp_path):
    content = render_workbench_input(read_molecule(input_text=XYZ, input_format='xyz'),
        settings(engine) | {'task_type': [{'opt': 'TS,CalcFC'}, {'freq': None}]},
        [dict(coord_type='bond', atoms=[1, 2], value=1.1)], [], str(tmp_path / 'input'))
    assert expected in content and ('freq' in content.lower())


@pytest.mark.parametrize('engine,task', [('gaussian', [{'freq': None}]), ('orca', [{'opt': 'ts'}])])
def test_scan_refuses_conflicting_explicit_tasks(engine, task, tmp_path):
    with pytest.raises(ValueError, match='conflicts'):
        render_workbench_input(read_molecule(input_text=XYZ, input_format='xyz'),
            settings(engine) | {'task_type': task}, [],
            [dict(coord_type='bond', atoms=[1, 2], scan_end=1.5, scan_steps=3)], str(tmp_path / 'input'))


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_native_frequency_declaration_does_not_add_default_optimization(engine, tmp_path):
    content = render_workbench_input(read_molecule(input_text=XYZ, input_format='xyz'),
        settings(engine) | {'keywords': 'Freq'}, [], [], str(tmp_path / 'input'))
    assert 'freq' in content.lower() and 'opt' not in content.lower()


@pytest.mark.parametrize('engine,keywords', [('gaussian', 'Opt=(TS,CalcFC,ModRedundant) Int=UltraFine'),
                                           ('orca', 'OptTS TightOpt')])
def test_native_ts_keywords_are_preserved_with_freeze(engine, keywords, tmp_path):
    content = render_workbench_input(read_molecule(input_text=XYZ, input_format='xyz'),
        settings(engine) | {'keywords': keywords},
        [dict(coord_type='bond', atoms=[1, 2], value=1.1)], [], str(tmp_path / 'input'))
    assert keywords in content
    assert content.lower().count('optts' if engine == 'orca' else 'opt=') == 1
