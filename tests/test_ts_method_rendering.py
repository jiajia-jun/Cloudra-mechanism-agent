from pathlib import Path

import pytest

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from tests.ts_fixtures import calculation_input

pytestmark = pytest.mark.usefixtures("ts_producer_authority")


@pytest.mark.parametrize('basis, expected', [
    ('def2svp', 'def2-SVP'), ('DEF2TZVPP', 'def2-TZVPP'),
    (' def2svp ', 'def2-SVP'), ('\tDEF2TZVPP\n', 'def2-TZVPP'),
    ('def2-SVP', 'def2-SVP'), ('cc-pVDZ', 'cc-pVDZ'), ('', ''),
])
def test_orca_writer_renders_basis_alias_and_preserves_declared_keywords(basis, expected):
    request = QmInputWriter_input_schema(
        engine='orca', source_type='xyz_file', source_value='unused.xyz',
        output_path='unused.inp', method='b3lyp', basis_set=basis, task_type=[{'opt': 'ts'}],
        extra_keywords='D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)',
    )
    header = QmInputWriter._build_orca_input(request, 'H 0 0 0').splitlines()[0].split()
    assert header == ['!', 'OptTS', 'b3lyp', *([expected] if expected else []),
                      'D3BJ', 'RIJCOSX', 'def2/J', 'TightSCF', 'CPCM(DCM)']
    assert request.basis_set == basis


def test_scan_to_ts_followups_keep_declared_method_basis_and_keywords(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as process

    xyz = tmp_path / 'water.xyz'
    xyz.write_text('3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n')
    Chem = pytest.importorskip('rdkit.Chem')
    mol=Chem.AddHs(Chem.MolFromSmiles('O'))
    conf=Chem.Conformer(3)
    positions=[[0,0,0],[1,0,0],[0,1,0]]
    for i,position in enumerate(positions):
        conf.SetAtomPosition(i,position)
    mol.AddConformer(conf)
    graph=tmp_path/'water.mol'
    graph.write_text(Chem.MolToMolBlock(mol))
    extras = 'D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)'
    declaration = calculation_input(
        engine='orca', reactant_smiles='O', product_smiles='O', method='b3lyp/def2svp', extra_keywords=extras, atom_map=[0,1,2],
        scan={'method': 'b3lyp/def2svp', 'extra_route': extras,
              'scans': [{'atoms': [0, 1], 'scan_end': 2, 'scan_steps': 5}]},
    )
    record = process.TsProcessRecord(run_id='scan', run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        input=declaration, owner_conversation_id='test', stage='guess')
    monkeypatch.setattr(process, '_read_built_xyz', lambda *_: (['O', 'H', 'H'], positions, str(xyz), str(graph)))
    monkeypatch.setattr(process, '_submit_step', lambda *_: ('', 42))
    process._guess(record)
    paths = [record.scan_step.input_path]
    record.current_ts_guess_path = str(xyz)
    record.path_kind = 'scan'
    opt_dir = tmp_path / 'opt'
    opt_dir.mkdir()
    error, path = process._write_refinement_input(record, str(opt_dir))
    assert error == ''
    paths.append(path)
    step = process.TsJobStep(purpose='ts_opt', job_id=43, input_path=path, state='done')
    record.job_steps.append(step)
    log = Path(process._refinement_log_path(record, step))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('CARTESIAN COORDINATES (ANGSTROEM)\n'
                   '---------------------------------\nO 0 0 0\nH 1 0 0\nH 0 1 0\n\n')
    freq_dir = tmp_path / 'freq'
    freq_dir.mkdir()
    error, path = process._write_frequency_input(record, str(freq_dir))
    assert error == ''
    paths.append(path)
    record.job_steps.append(process.TsJobStep(purpose='frequency', job_id=44, input_path=path, state='done'))
    irc_dir = tmp_path / 'irc'
    irc_dir.mkdir()
    error, path = process._write_irc_input(record, str(irc_dir))
    assert error == ''
    paths.append(path)
    for role in ('reactant', 'product'):
        from cloudra.tools.core.ts_inputs import EndpointSeed
        evidence=tmp_path/'seed-provenance.txt'
        evidence.write_text('fixture provenance')
        getattr(record.input.verification,role+'_endpoint').seed=EndpointSeed(kind='file',xyz_path=str(xyz),evidence_refs=[str(evidence)])
        endpoint_dir = tmp_path / role
        endpoint_dir.mkdir()
        error, path = process._write_endpoint_input(record, str(endpoint_dir), role, 'opt')
        assert error == ''
        paths.append(path)
        record.job_steps.append(process.TsJobStep(purpose=role+'_opt', job_id=45, input_path=path, state='done'))
        monkeypatch.setattr(process, '_endpoint_opt_frame', lambda *_: (xyz.read_text(), ''))
        endpoint_freq_dir = tmp_path / (role+'_freq')
        endpoint_freq_dir.mkdir()
        error, path = process._write_endpoint_input(record, str(endpoint_freq_dir), role, 'frequency')
        assert error == ''
        paths.append(path)
    for path in paths:
        header = next(line for line in Path(path).read_text().splitlines() if line.startswith('!')).split()
        assert header[2:] == ['b3lyp', 'def2-SVP', 'D3BJ', 'RIJCOSX', 'def2/J', 'TightSCF', 'CPCM(DCM)'], path
    assert record.input.ts_optimization.method == 'b3lyp/def2svp'
    assert record.input.ts_optimization.keywords == extras


@pytest.mark.parametrize('method, expected', [
    ('b3lyp / def2svp RIJCOSX def2/J', '! OPT b3lyp def2-SVP RIJCOSX def2/J'),
    ('b3lyp /def2svp RIJCOSX def2/J', '! OPT b3lyp def2-SVP RIJCOSX def2/J'),
    ('b3lyp/ def2svp RIJCOSX def2/J', '! OPT b3lyp def2-SVP RIJCOSX def2/J'),
    ('b3lyp/def2svp RIJCOSX def2/J', '! OPT b3lyp def2-SVP RIJCOSX def2/J'),
    ('b3lyp def2svp RIJK def2/JK', '! OPT b3lyp def2-SVP RIJK def2/JK'),
    ('MP2/cc-pVDZ cc-pVDZ/C', '! OPT MP2 cc-pVDZ cc-pVDZ/C'),
])
def test_scan_keeps_auxiliary_basis_slashes(tmp_path, method, expected):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    xyz = tmp_path / 'water.xyz'
    xyz.write_text('3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n')
    target = tmp_path / 'scan.inp'
    result = TsGuess()._scan_prepare(TsGuess_input_schema(mode='scan_prepare', engine='orca',
        input_path=str(xyz), method=method, output_path=str(target),
        scans=[{'atoms': [0, 1], 'scan_end': 2, 'scan_steps': 3}]))
    assert result.is_success
    assert target.read_text().splitlines()[0] == expected
