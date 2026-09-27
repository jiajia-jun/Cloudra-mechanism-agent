

def test_scan_workflow_waits_without_duplicate_submission_and_accepts_only_internal_peak(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as process
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_output_schema
    payload = dict(reactant_smiles='O', product_smiles='O', method='HF/STO-3G', engine='orca',
                   scan={'method':'HF/STO-3G','scans':[{'atoms':[0,1],'scan_end':2,'scan_steps':5}]})
    decl = process.TsDeclaration(**payload)
    record = process.TsProcessRecord(run_id='scan', run_dir=str(tmp_path), declaration=decl,
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


def test_scan_is_visible_in_public_schema():
    from cloudra.tools.core.ts_process import TsDeclaration
    assert 'scan' in TsDeclaration.model_json_schema()['properties']


def test_geometry_correction_invalidates_finished_scan(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as p
    declaration = p.TsDeclaration(reactant_smiles='O',product_smiles='O',method='HF',
        scan={'method':'HF','scans':[{'atoms':[0,1],'scan_end':2,'scan_steps':5}]})
    record = p.TsProcessRecord(run_id='r',run_dir=str(tmp_path), declaration=declaration,
        stage='guess', scan_step=p.TsJobStep(purpose='scan',job_id=42,state='done'))
    monkeypatch.setattr(p,'advance',lambda record: record)
    p.resume(record, p.TsAdjustment(distance_filters=[{'atoms':[0,1],'min_ang':0.8,'max_ang':1.2}]))
    assert record.scan_step is None
    assert record.stage == 'build'


def test_scan_adjustment_cannot_skip_mapping(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as p
    record = p.TsProcessRecord(run_id='r', run_dir=str(tmp_path),
        declaration=p.TsDeclaration(reactant_smiles='O', product_smiles='O', method='HF'), stage='map')
    monkeypatch.setattr(p, 'advance', lambda record: record)
    p.resume(record, p.TsAdjustment(scan={'method':'HF','scans':[{'atoms':[0,1],'scan_end':2,'scan_steps':5}]}))
    assert record.stage == 'map'


def test_completed_scan_with_missing_log_is_recoverably_blocked(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as p
    from cloudra.tools.Chemtool.ts_guess import TsGuess
    record = p.TsProcessRecord(run_id='r', run_dir=str(tmp_path),
        declaration=p.TsDeclaration(reactant_smiles='O', product_smiles='O', method='HF',
            scan={'method':'HF','scans':[{'atoms':[0,1],'scan_end':2,'scan_steps':5}]}),
        stage='guess', waiting_for='job:42',
        scan_step=p.TsJobStep(purpose='scan', job_id=42, input_path=str(tmp_path/'scan.inp')))
    monkeypatch.setattr(p, '_read_job_state', lambda *_: 'done')
    def missing(*_):
        raise ValueError('scan log missing')
    monkeypatch.setattr(TsGuess, '_scan_parse', missing)
    p._guess(record)
    assert record.blocked.failure_class == 'scan_parse_failed'
    assert record.waiting_for == ''
    assert record.blocked.needs == ['scan']


def test_scan_peak_must_preserve_atom_identity(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as p
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_output_schema
    record = p.TsProcessRecord(run_id='r', run_dir=str(tmp_path),
        declaration=p.TsDeclaration(reactant_smiles='O', product_smiles='O', method='HF',
            scan={'method':'HF','scans':[{'atoms':[0,1],'scan_end':2,'scan_steps':5}]}),
        stage='guess', scan_step=p.TsJobStep(purpose='scan', job_id=42, input_path=str(tmp_path/'scan.inp')))
    peak = tmp_path/'peak.xyz'
    peak.write_text('1\nwrong geometry\nHe 0 0 0\n')
    monkeypatch.setattr(p, '_read_job_state', lambda *_: 'done')
    monkeypatch.setattr(p, '_read_built_xyz', lambda *_: (['O','H','H'], [], '', ''))
    monkeypatch.setattr(TsGuess, '_scan_parse', lambda *_: TsGuess_output_schema(
        is_success=True, scan_has_internal_peak=True, ts_candidate_path=str(peak)))
    p._guess(record)
    assert record.blocked.failure_class == 'scan_invalid_geometry'
