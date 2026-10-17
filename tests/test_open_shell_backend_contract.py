"""Spin declarations must not be silently reduced to an incapable backend flag."""

import pytest

from cloudra.runtime.chem_task import ChemTask
from cloudra.tools.core.crest_runner import CrestRunRequest, build_crest_command, run_crest
from cloudra.tools.core.xtb_path_runner import XtbPathRequest, build_xtb_path_command, run_xtb_path

XYZ = '2\nO2\nO 0 0 0\nO 1.2 0 0\n'


@pytest.fixture
def o2_mol():
    Chem = pytest.importorskip('rdkit.Chem')
    mol = Chem.MolFromSmiles('O=O')
    for index, atom in enumerate(mol.GetAtoms(), start=1):
        atom.SetAtomMapNum(index)
    coordinates = Chem.Conformer(2)
    coordinates.SetAtomPosition(0, (0., 0., 0.))
    coordinates.SetAtomPosition(1, (1.2, 0., 0.))
    mol.AddConformer(coordinates)
    return Chem.MolToMolBlock(mol)


@pytest.mark.parametrize('backend', ['crest', 'xtb_path'])
def test_open_shell_singlet_is_refused_before_backend_launch(tmp_path, backend):
    with pytest.raises(ValueError) as error:
        if backend == 'crest':
            request = CrestRunRequest(xyz_text=XYZ, output_dir=str(tmp_path), multiplicity=1,
                                      electronic_character='open_shell')
            build_crest_command(request)
        else:
            request = XtbPathRequest(reactant_xyz=XYZ, product_xyz=XYZ, output_dir=str(tmp_path),
                                     multiplicity=1, electronic_character='open_shell')
            build_xtb_path_command(request)
    assert 'open-shell singlet' in str(error.value)


@pytest.mark.parametrize('backend', ['crest', 'xtb_path'])
@pytest.mark.parametrize('xyz', [XYZ, 'invalid XYZ'])
def test_unsupported_state_has_no_backend_artifacts_or_probes(tmp_path, monkeypatch, backend, xyz):
    module = 'crest_runner' if backend == 'crest' else 'xtb_path_runner'
    monkeypatch.setattr(f'cloudra.tools.core.{module}.capture_versions',
                        lambda *_: pytest.fail('Unsupported state probed an engine'))
    destination = tmp_path / 'unsupported'
    with pytest.raises(ValueError) as error:
        if backend == 'crest':
            run_crest(CrestRunRequest(xyz_text=xyz, output_dir=str(destination), multiplicity=1,
                                      electronic_character='open_shell'))
        else:
            run_xtb_path(XtbPathRequest(reactant_xyz=xyz, product_xyz=xyz, output_dir=str(destination),
                                        multiplicity=1, electronic_character='open_shell'))
    assert 'open-shell singlet' in str(error.value)
    assert not destination.exists()


@pytest.mark.parametrize('multiplicity,character,net_spin', [
    (1, 'closed_shell', '0'), (3, 'open_shell', '2'), (5, 'open_shell', '4'),
])
def test_backend_preserves_the_declared_total_spin(tmp_path, multiplicity, character, net_spin):
    request = XtbPathRequest(reactant_xyz=XYZ, product_xyz=XYZ, output_dir=str(tmp_path),
                             multiplicity=multiplicity, electronic_character=character)
    command = build_xtb_path_command(request)
    assert command[command.index('--uhf') + 1] == net_spin
    assert '--spinpol' not in command and '--tblite' not in command


@pytest.mark.parametrize('task', ['xtb_path', 'xtb_opt', 'xtb_gradient', 'xtb_hessian'])
def test_native_task_cannot_hide_open_shell_singlet_in_uhf_zero(task):
    with pytest.raises(ValueError) as error:
        ChemTask(task=task, reactant_xyz=XYZ, product_xyz=XYZ if task == 'xtb_path' else None,
                 cpus=1, multiplicity=1, electronic_character='open_shell')
    assert 'open-shell singlet' in str(error.value)


def test_ts_path_coupled_singlet_stops_before_path_queue(tmp_path, monkeypatch):
    pytest.importorskip('rdkit')
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_inputs import XtbPathGuess
    from tests.test_ts_open_shell_identity import _file_record

    record, _ = _file_record(tmp_path, '[CH2][CH2]', multiplicity=1)
    record.input.guess = XtbPathGuess(kind='xtb_path', method='GFN2-xTB')
    monkeypatch.setattr(ts_process, '_queued_path', lambda *_: pytest.fail('Unsupported state reached queue'))
    monkeypatch.setattr('cloudra.tools.core.xtb_path_runner.run_xtb_path', lambda *_: pytest.fail('Unsupported state launched xTB'))
    for stage in (ts_process._declare, ts_process._build, ts_process._map, ts_process._assemble):
        stage(record)
        assert record.blocked is None and record.terminal is None
    ts_process._guess(record)
    assert record.blocked.failure_class == 'electronic_state_backend_unsupported'
    assert not record.job_steps and not record.waiting_for


def test_ts_native_scan_coupled_singlet_stops_before_submit(tmp_path, monkeypatch):
    pytest.importorskip('rdkit')
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_inputs import QmCalculation, ScanGuess
    from tests.test_ts_open_shell_identity import _file_record

    record, _ = _file_record(tmp_path, '[CH2][CH2]', multiplicity=1)
    record.input.guess = ScanGuess(kind='scan', calculation=QmCalculation(basis_set='', engine='xtb', method='GFN2-xTB'),
        scans=[dict(coord_type='bond', atoms=[1, 2], scan_start=1.5, scan_end=2.0, scan_steps=5)], force_constant=0.1)
    monkeypatch.setattr(ts_process, '_submit_step', lambda *_: pytest.fail('Unsupported scan submitted a job'))
    for stage in (ts_process._declare, ts_process._build, ts_process._map, ts_process._assemble):
        stage(record)
        assert record.blocked is None and record.terminal is None
    ts_process._guess(record)
    assert record.blocked.failure_class == 'electronic_state_backend_unsupported'
    assert not record.scan_step and not record.waiting_for


@pytest.mark.parametrize('role', ['reactant', 'product'])
def test_ts_seed_singlet_stops_before_native_or_constrained_optimization(tmp_path, monkeypatch, role):
    pytest.importorskip('rdkit')
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_inputs import QmCalculation
    from tests.test_ts_open_shell_identity import _file_record

    record, _ = _file_record(tmp_path, '[CH2][CH2]', multiplicity=1)
    getattr(record.input.conformers, role).optimization = QmCalculation(basis_set='', engine='xtb', method='GFN2-xTB')
    monkeypatch.setattr(ts_process, '_read_built_xyz', lambda *_: pytest.fail('Unsupported state entered optimization'))
    monkeypatch.setattr(ts_process, '_submit_step', lambda *_: pytest.fail('Unsupported state submitted a job'))
    ts_process._optimize_conformer_source(record, role)
    assert record.blocked.failure_class == 'electronic_state_backend_unsupported'
    assert record.blocked.needs == [f'conformers.{role}.optimization']
    assert not record.job_steps and not record.waiting_for


def test_native_submission_requires_declared_electronic_character(tmp_path, monkeypatch):
    pytest.importorskip('rdkit')
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_inputs import QmCalculation
    from tests.test_ts_open_shell_identity import _file_record

    record, _ = _file_record(tmp_path, '[CH2][CH2]', multiplicity=3, electronic_character='open_shell')
    record.input.conformers.reactant.optimization = QmCalculation(basis_set='', engine='xtb', method='GFN2-xTB')
    monkeypatch.setattr('cloudra.services.ts_pipeline_context.require_pipeline_authority', lambda *_: None)
    task = ChemTask(task='xtb_opt', reactant_xyz=XYZ, charge=0, multiplicity=3, cpus=record.compute_cpus)
    manifest = tmp_path / 'task.json'
    manifest.write_text(task.model_dump_json())
    with pytest.raises(ValueError) as error:
        ts_process._check_calculation_submission(record, 'candidate_opt', str(manifest), 'chem_task')
    assert 'electronic' in str(error.value)


@pytest.mark.parametrize('purpose', ['candidate_opt', 'path', 'scan'])
def test_ts_native_manifests_preserve_electronic_declaration(tmp_path, monkeypatch, purpose):
    pytest.importorskip('rdkit')
    from pathlib import Path

    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_inputs import QmCalculation, ScanGuess, XtbPathGuess
    from tests.test_ts_open_shell_identity import _file_record

    record, _ = _file_record(tmp_path, multiplicity=2, electronic_character='open_shell')
    for stage in (ts_process._declare, ts_process._build, ts_process._map, ts_process._assemble):
        stage(record)
        assert record.blocked is None and record.terminal is None
    captured = []

    def capture_submission(_record, actual_purpose, manifest, job_type):
        captured.append((actual_purpose, job_type, ChemTask.model_validate_json(Path(manifest).read_text())))
        return 'Captured without creating a compute job', -1

    monkeypatch.setattr(ts_process, '_submit_step', capture_submission)
    if purpose == 'candidate_opt':
        record.input.conformers.reactant.optimization = QmCalculation(basis_set='', engine='xtb', method='GFN2-xTB')
        ts_process._optimize_conformer_source(record, 'reactant')
    elif purpose == 'path':
        record.pipeline_id = 'fixture'
        monkeypatch.setattr('cloudra.tools.core.xtb_path_runner.run_xtb_path',
                            lambda *_: pytest.fail('Manifest test launched an engine'))
        record.input.guess = XtbPathGuess(kind='xtb_path', method='GFN2-xTB')
        ts_process._guess(record)
    else:
        record.input.guess = ScanGuess(kind='scan', calculation=QmCalculation(basis_set='', engine='xtb', method='GFN2-xTB'),
            scans=[dict(coord_type='bond', atoms=[0, 1], scan_start=1.5, scan_end=2.0, scan_steps=5)], force_constant=0.1)
        ts_process._guess(record)
    assert len(captured) == 1
    actual_purpose, job_type, task = captured[0]
    assert (actual_purpose, job_type) == (purpose, 'chem_task')
    assert (task.charge, task.multiplicity, task.electronic_character) == (0, 2, 'open_shell')
    assert not record.job_steps and not record.waiting_for


@pytest.mark.parametrize('multiplicity,character', [(1, 'closed_shell'), (3, 'open_shell')])
def test_standalone_path_preserves_electronic_character(tmp_path, monkeypatch, multiplicity, character, o2_mol):
    pytest.importorskip('ase')
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    from cloudra.tools.core.xtb_path_runner import XtbPathResult

    def capture(request):
        assert request.electronic_character == character
        assert request.multiplicity == multiplicity
        return XtbPathResult(run_dir=str(tmp_path), termination_reason='failed')

    monkeypatch.setattr('cloudra.tools.core.xtb_path_runner.run_xtb_path', capture)
    result = TsGuess()._xtb_path(TsGuess_input_schema(mode='xtb_path', reactant_text=o2_mol,
        product_text=o2_mol, output_dir=str(tmp_path),
        multiplicity=multiplicity, electronic_character=character))
    assert result.is_success is False


def test_standalone_path_refuses_singlet_before_probe_and_artifact(tmp_path, monkeypatch, o2_mol):
    pytest.importorskip('ase')
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    monkeypatch.setattr('cloudra.tools.core.xtb_path_runner.capture_versions',
                        lambda *_: pytest.fail('Unsupported standalone path probed xTB'))
    destination = tmp_path / 'unsupported'
    with pytest.raises(ValueError) as error:
        TsGuess()._xtb_path(TsGuess_input_schema(mode='xtb_path', reactant_text=o2_mol,
            product_text=o2_mol, output_dir=str(destination),
            multiplicity=1, electronic_character='open_shell'))
    assert 'open-shell singlet' in str(error.value)
    assert not destination.exists()
