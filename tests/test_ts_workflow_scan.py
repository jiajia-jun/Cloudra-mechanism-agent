
from pathlib import Path

import pytest

from tests.ts_fixtures import calculation_input


def test_scan_workflow_waits_without_duplicate_submission_and_accepts_only_internal_peak(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as process
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_output_schema
    payload = dict(basis_set='STO-3G', reactant_smiles='O', product_smiles='O', method='HF', engine='orca',
                   scan={'basis_set': 'STO-3G', 'method':'HF','scans':[{'atoms':[0,1],'scan_end':2,'scan_steps':5}]})
    decl = calculation_input(**payload)
    record = process.TsProcessRecord(run_id='scan', run_dir=str(tmp_path), input=decl,
                                    owner_conversation_id='test', stage='guess')
    xyz = tmp_path/'r.xyz'
    xyz.write_text('3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n')
    monkeypatch.setattr(process, '_read_built_xyz', lambda *_: (['O','H','H'], [[0,0,0],[1,0,0],[0,1,0]], str(xyz), ''))
    submissions = []
    monkeypatch.setattr(process, '_submit_step', lambda *args: (submissions.append(args) or ('',42)))
    monkeypatch.setattr(process, '_read_job_state', lambda *_: 'running')
    process._guess(record)
    assert record.waiting_for == 'job:42'
    process._guess(record)
    assert len(submissions) == 1
    monkeypatch.setattr(process, '_read_job_state', lambda *_: 'done')
    monkeypatch.setattr(TsGuess, '_scan_parse', lambda *_: TsGuess_output_schema(is_success=True, scan_has_internal_peak=False))
    process._guess(record)
    assert record.blocked.failure_class == 'scan_no_candidate'
    assert not record.current_ts_guess_path
    assert len(submissions) == 1




def test_scan_and_refinement_keep_distinct_declared_solvation(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as process

    xyz = tmp_path / 'water.xyz'
    xyz.write_text('3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n')
    declaration = calculation_input(basis_set='def2-SVP',
        reactant_smiles='O', product_smiles='O', method='B3LYP',
        keywords='CPCM(Water)',
        scan={'basis_set': '', 'method': 'GFN2-xTB', 'keywords': 'ALPB(Water)',
              'scans': [{'atoms': [0, 1], 'scan_end': 2, 'scan_steps': 5}]},
    )
    record = process.TsProcessRecord(
        run_id='scan', run_dir=str(tmp_path), input=declaration,
        owner_conversation_id='test', stage='guess',
    )
    monkeypatch.setattr(process, '_read_built_xyz', lambda *_: (['O', 'H', 'H'], [], str(xyz), ''))
    monkeypatch.setattr(process, '_submit_step', lambda *_: ('', 42))
    monkeypatch.setattr(process, '_read_job_state', lambda *_: 'running')

    process._guess(record)
    assert record.blocked is None
    assert record.scan_step is not None
    scan_text = Path(record.scan_step.input_path).read_text()
    assert 'ALPB(Water)' in scan_text
    assert 'CPCM(Water)' not in scan_text

    record.current_ts_guess_path = str(xyz)
    job_dir = tmp_path / 'job'
    job_dir.mkdir()
    error, path = process._write_refinement_input(record, str(job_dir))
    assert error == ''
    refine_text = Path(path).read_text()
    assert 'CPCM(Water)' in refine_text
    assert 'ALPB(Water)' not in refine_text






def test_completed_scan_with_missing_log_is_recoverably_blocked(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as p
    from cloudra.tools.Chemtool.ts_guess import TsGuess
    record = p.TsProcessRecord(run_id='r', run_dir=str(tmp_path),
        input=calculation_input(basis_set='', reactant_smiles='O', product_smiles='O', method='HF',
            scan={'basis_set': '', 'method':'HF','scans':[{'atoms':[0,1],'scan_end':2,'scan_steps':5}]}),
        stage='guess', waiting_for='job:42',
        scan_step=p.TsJobStep(purpose='scan', job_id=42, input_path=str(tmp_path/'scan.inp')))
    monkeypatch.setattr(p, '_read_job_state', lambda *_: 'done')
    def missing(*_):
        raise ValueError('scan log missing')
    monkeypatch.setattr(TsGuess, '_scan_parse', missing)
    p._guess(record)
    assert record.blocked.failure_class == 'scan_parse_failed'
    assert record.waiting_for == ''
    assert record.blocked.needs == ['guess']


def test_scan_peak_must_preserve_atom_identity(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as p
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_output_schema
    record = p.TsProcessRecord(run_id='r', run_dir=str(tmp_path),
        input=calculation_input(basis_set='', reactant_smiles='O', product_smiles='O', method='HF',
            scan={'basis_set': '', 'method':'HF','scans':[{'atoms':[0,1],'scan_end':2,'scan_steps':5}]}),
        stage='guess', scan_step=p.TsJobStep(purpose='scan', job_id=42, input_path=str(tmp_path/'scan.inp')))
    peak = tmp_path/'peak.xyz'
    peak.write_text('1\nwrong geometry\nHe 0 0 0\n')
    monkeypatch.setattr(p, '_read_job_state', lambda *_: 'done')
    monkeypatch.setattr(p, '_read_built_xyz', lambda *_: (['O','H','H'], [], '', ''))
    monkeypatch.setattr(TsGuess, '_scan_parse', lambda *_: TsGuess_output_schema(
        is_success=True, scan_has_internal_peak=True, ts_candidate_path=str(peak)))
    p._guess(record)
    assert record.blocked.failure_class == 'scan_invalid_geometry'


def test_failed_scan_exposes_native_log_and_requests_diagnosis(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as process

    record = process.TsProcessRecord(run_id="failed-scan", run_dir=str(tmp_path),
        input=calculation_input(basis_set='', reactant_smiles="O", product_smiles="O", method="HF", engine="orca",
            scan={'basis_set': '', "method": "HF", "scans": [{"atoms": [0, 1], "scan_end": 2, "scan_steps": 7}]}),
        stage="guess", waiting_for="job:42",
        scan_step=process.TsJobStep(purpose="scan", job_id=42, input_path=str(tmp_path / "scan.inp")))
    log = Path(process._refinement_log_path(record, record.scan_step))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("THE OPTIMIZATION HAS CONVERGED\n" * 8
        + "The optimization did not converge but reached the maximum number of optimization cycles.\n"
        + "ERROR (SHARK): Failed to read input file scan.SHARKINP.tmp\n"
        + "Primary job terminated normally, but 1 process returned a non-zero exit code.\n"
        + "ORCA finished by error termination in PROPERTIES\n")
    monkeypatch.setattr(process, "_read_job_state", lambda *_: "failed")
    result = process._guess(record)
    assert result.blocked.failure_class == "scan_job_failed"
    assert result.waiting_for == ""
    assert result.scan_step.job_id == 42
    assert result.current_ts_guess_path == ""
    assert result.blocked.needs == ["compute_artifacts"]
    details = "\n".join(result.blocked.atom_details)
    assert str(log) in details
    assert "ERROR (SHARK): Failed to read input file" in details
    assert "ORCA finished by error termination in PROPERTIES" in details

pytestmark = pytest.mark.usefixtures("ts_producer_authority")
