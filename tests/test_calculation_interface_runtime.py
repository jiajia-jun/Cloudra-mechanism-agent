"""Shared configurations reach real writers and compiled native job manifests."""

from pathlib import Path

import pytest

from cloudra.runtime.chem_task import ChemTask
from cloudra.tools.core.qm_calculation import QmCalculation
from cloudra.tools.core.ts_inputs import CalculationRef, FileConformer, ScanGuess, TsInput
from cloudra.tools.core.ts_process import TsProcessRecord, _guess_scan, _write_refinement_input, stage_calculation


def _record(tmp_path, *, calculation=None):
    calculation = calculation or QmCalculation(engine='orca', method='B3LYP', basis_set='def2svp',
        keywords='D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)')
    source = tmp_path / 'seed.xyz'
    source.write_text('2\nH2 synthetic geometry\nH 0 0 0\nH 0 0 .74\n')
    reference = {'ref': 'formal'}
    inputs = TsInput.model_validate(dict(calculations={'formal': calculation.model_dump()},
        reaction=dict(reactant_smiles='[H][H]', product_smiles='[H][H]', charge=0, multiplicity=1),
        conformers=dict(reactant=FileConformer(kind='file', xyz_path=str(source)).model_dump()),
        ts_optimization=reference, verification=dict(frequency=reference, irc=reference,
            reactant_endpoint=dict(optimization=reference, frequency=reference),
            product_endpoint=dict(optimization=reference, frequency=reference))))
    from cloudra.tools.Chemtool.reaction_mapping import _read_structure
    molecule = _read_structure(str(source), None, 'xyz', 0, 'reactant')
    return TsProcessRecord(run_id='shared', run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        owner_conversation_id='fixture', owner_session_id='owner', input=inputs,
        structures={'reactant': molecule, 'product': molecule, 'candidate': molecule, 'product_to_reactant': (0, 1)}, path_kind='provided'), source


def test_formal_stages_explicitly_reuse_one_complete_definition(tmp_path):
    record, _ = _record(tmp_path)
    configuration = record.input.calculations['formal']
    for purpose in ('ts_opt', 'frequency', 'irc', 'reactant_opt', 'reactant_frequency', 'product_opt', 'product_frequency'):
        resolved = stage_calculation(record, purpose)
        assert resolved == configuration and resolved is not configuration
    resolved.keywords = 'Changed local snapshot'
    assert configuration.keywords == 'D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)'
    assert isinstance(record.input.ts_optimization, CalculationRef)


def test_refinement_writer_consumes_resolved_canonical_fields(tmp_path):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    record, _ = _record(tmp_path)
    directory = tmp_path / 'refinement'
    directory.mkdir()
    error, path = _write_refinement_input(record, str(directory))
    assert error == ''
    native = Path(path).read_text()
    # Explicit native settings are preserved, not supplemented with a TS task.
    assert next(line for line in native.splitlines() if line.startswith('!')) == '! B3LYP def2-SVP D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)'
    assert compare_calculation_input(native, record.input.calculations['formal'].model_dump(), charge=0, multiplicity=1) == []


@pytest.mark.parametrize('engine', ['orca', 'xtb'])
def test_scan_submission_resolves_reference_and_freezes_actual_configuration(tmp_path, monkeypatch, engine):
    configuration = (QmCalculation(engine='xtb', method='GFN2-xTB', basis_set='') if engine == 'xtb'
                     else QmCalculation(engine='orca', method='B3LYP', basis_set='def2svp', keywords='D3BJ CPCM(DCM)'))
    record, source = _record(tmp_path, calculation=configuration)
    record.input.guess = ScanGuess(kind='scan', calculation=CalculationRef(ref='formal'),
        scans=[dict(coord_type='bond', atoms=[0, 1], scan_start=.74, scan_end=1.2, scan_steps=3)],
        **({'force_constant': .5} if engine == 'xtb' else {}))
    monkeypatch.setattr('cloudra.tools.core.ts_process._read_built_xyz',
                        lambda *_: (['H', 'H'], [[0., 0., 0.], [0., 0., .74]], str(source), ''))
    captured = []

    def submit(_record, purpose, input_path, job_type):
        captured.append((purpose, job_type, Path(input_path).read_text()))
        return '', 101

    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step', submit)
    monkeypatch.setattr('cloudra.tools.core.ts_process._step_state', lambda *_: 'ready')
    _guess_scan(record)
    assert record.blocked is None and record.waiting_for == 'job:101'
    assert record.scan_step.actual_calculation == configuration
    record.input.calculations['formal'].keywords = 'Later declaration change'
    assert record.scan_step.actual_calculation.keywords == configuration.keywords
    if engine == 'xtb':
        assert captured[0][1] == 'chem_task'
        task = ChemTask.model_validate_json(captured[0][2])
        assert isinstance(task.scan.calculation, QmCalculation)
        assert task.scan.calculation == configuration
    else:
        assert captured[0][1] == 'orca'
        assert captured[0][2].splitlines()[0] == '! B3LYP def2-SVP D3BJ CPCM(DCM)'


def test_native_scan_manifest_cannot_carry_an_unresolved_definition(tmp_path):
    with pytest.raises(ValueError):
        ChemTask(task='xtb_scan', reactant_xyz='2\nH2\nH 0 0 0\nH 0 0 .74\n', cpus=1,
            scan=dict(kind='scan', calculation={'ref': 'somewhere'}, force_constant=.5,
                scans=[dict(atoms=[0, 1], scan_start=.74, scan_end=1.2, scan_steps=3)]))
