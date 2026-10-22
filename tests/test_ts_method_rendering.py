from pathlib import Path

import pytest

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.molecule import read_molecule
from tests.ts_fixtures import calculation_input

pytestmark = pytest.mark.usefixtures("ts_producer_authority")


@pytest.mark.parametrize('basis, expected', [
    ('def2-SVP', 'def2SVP'), ('DEF2-svp', 'def2SVP'),
    ('def2-TZVP', 'def2TZVP'), ('def2-TZVPP', 'def2TZVPP'),
    ('def2-QZVP', 'def2QZVP'), ('def2-QZVPP', 'def2QZVPP'),
    (' def2-SVP ', 'def2SVP'), ('def2SVP', 'def2SVP'),
    ('6-31+G(d,p)', '6-31+G(d,p)'), ('aug-cc-pVDZ', 'aug-cc-pVDZ'),
    ('GenECP', 'GenECP'), ('def2-TZVPD', 'def2-TZVPD'),
    ('ma-def2-SVP', 'ma-def2-SVP'), ('', ''),
])
def test_gaussian_writer_renders_known_basis_aliases_only(basis, expected):
    request = QmInputWriter_input_schema(
        charge=0, engine='gaussian', source_type='xyz_file', source_value='unused.xyz',
        output_path='unused.gjf', method='B3LYP', basis_set=basis,
        task_type=[{'opt': None}, {'freq': None}],
        keywords='EmpiricalDispersion=GD3BJ Int(UltraFine) SCF=Tight',
    )
    method = 'B3LYP' + (f'/{expected}' if expected else '')
    assert QmInputWriter._build_route(request) == (
        f'#p opt freq {method} EmpiricalDispersion=GD3BJ Int(UltraFine) SCF=Tight'
    )
    assert request.basis_set == basis.strip()


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_gaussian_writer_saves_native_basis_without_changing_declaration(tmp_path):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    source = tmp_path / 'water.xyz'
    source.write_text('3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n')
    target = tmp_path / 'optfreq.gjf'
    request = QmInputWriter_input_schema(
        charge=0, engine='gaussian', source_type='xyz_file', source_value=str(source),
        output_path=str(target), method='B3LYP', basis_set='def2-SVP',
        task_type=[{'opt': None}, {'freq': None}], mem='10GB', nproc=8,
        keywords='EmpiricalDispersion=GD3BJ Int(UltraFine) SCF=Tight',
    )
    result = await QmInputWriter().tool_call(request, None)
    assert result.is_success, result.message
    content = target.read_text()
    assert '#p opt freq B3LYP/def2SVP EmpiricalDispersion=GD3BJ Int(UltraFine) SCF=Tight\n' in content
    assert '%mem=10GB\n' in content and '%nproc=8\n' in content
    assert result.calculation.basis_set == 'def2-SVP'
    assert result.calculation.method == 'B3LYP'
    assert result.calculation.keywords == "opt freq " + request.keywords
    assert request.keywords == "EmpiricalDispersion=GD3BJ Int(UltraFine) SCF=Tight"
    assert compare_calculation_input(content, result.calculation.model_dump(), charge=0, multiplicity=1) == []


@pytest.mark.usefixtures('rdkit_chemistry')
def test_gaussian_scan_renders_native_basis_and_preserves_keywords(tmp_path):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    target = tmp_path / 'scan.gjf'
    request = TsGuess_input_schema(
        charge=0,  mode='scan_prepare', engine='gaussian',
        input_text='3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n',
        output_path=str(target), method='B3LYP', basis_set='def2-SVP',
        keywords='Opt=ModRedundant EmpiricalDispersion=GD3BJ SCF=Tight SCRF=(CPCM,Solvent=Water)',
        scans=[{'atoms': [1, 2], 'scan_end': 2, 'scan_steps': 4}],
    )
    result = TsGuess()._scan_prepare(request)
    assert result.is_success, result.message
    content = target.read_text()
    assert ('#p B3LYP/def2SVP Opt=ModRedundant '
            'EmpiricalDispersion=GD3BJ SCF=Tight SCRF=(CPCM,Solvent=Water)\n') in content
    assert 'B 1 2 S 4 0.250000\n' in content
    assert request.basis_set == 'def2-SVP'


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize('basis, expected', [
    ('def2svp', 'def2-SVP'), ('DEF2TZVPP', 'def2-TZVPP'),
    (' def2svp ', 'def2-SVP'), ('\tDEF2TZVPP\n', 'def2-TZVPP'),
    ('def2-SVP', 'def2-SVP'), ('cc-pVDZ', 'cc-pVDZ'), ('', ''),
])
def test_orca_writer_renders_basis_alias_and_preserves_declared_keywords(basis, expected):
    request = QmInputWriter_input_schema(
        charge=0, engine='orca', source_type='xyz_file', source_value='unused.xyz',
        output_path='unused.inp', method='b3lyp', basis_set=basis, task_type=[{'opt': 'ts'}],
        keywords='D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)',
    )
    header = QmInputWriter._build_orca_input(request, read_molecule(input_text='1\n\nH 0 0 0\n')).splitlines()[0].split()
    assert header == ['!', 'OptTS', 'b3lyp', *([expected] if expected else []),
                      'D3BJ', 'RIJCOSX', 'def2/J', 'TightSCF', 'CPCM(DCM)']
    assert request.basis_set == basis.strip()


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
    extras = 'D3BJ RIJCOSX def2/J TightSCF CPCM(DCM)'
    declaration = calculation_input(basis_set='def2svp',
        engine='orca', reactant_smiles='O', product_smiles='O', method='b3lyp', keywords=extras,
        scan={'basis_set': 'def2svp', 'method': 'b3lyp', 'keywords': 'Opt ' + extras,
              'scans': [{'atoms': [0, 1], 'scan_end': 2, 'scan_steps': 5}]},
    )
    declaration.ts_optimization.keywords = 'OptTS ' + extras
    declaration.verification.frequency.keywords = 'Freq ' + extras
    declaration.verification.irc.keywords = 'IRC ' + extras
    for endpoint in (declaration.verification.reactant_endpoint, declaration.verification.product_endpoint):
        endpoint.optimization.keywords = 'Opt ' + extras
        endpoint.frequency.keywords = 'Freq ' + extras
    record = process.TsProcessRecord(run_id='scan', run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        input=declaration, owner_conversation_id='test', stage='guess')
    from cloudra.tools.core.reaction_state import ReactionStructures
    record.structures = ReactionStructures(reactant=mol, product=mol, product_to_reactant=(0, 1, 2))
    monkeypatch.setattr(process, '_submit_step', lambda *_: ('', 42))
    process._guess(record)
    paths = [(record.scan_step.input_path, 'Opt')]
    record.structures.candidate = Chem.Mol(mol)
    record.path_kind = 'scan'
    opt_dir = tmp_path / 'opt'
    opt_dir.mkdir()
    error, path = process._write_refinement_input(record, str(opt_dir))
    assert error == ''
    paths.append((path, 'OptTS'))
    step = process.TsJobStep(purpose='ts_opt', job_id=43, input_path=path, state='done')
    record.job_steps.append(step)
    log = Path(process._refinement_log_path(record, step))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('O   R   C   A\nTHE OPTIMIZATION HAS CONVERGED\n'
                   'FINAL ENERGY EVALUATION AT THE STATIONARY POINT\n'
                   'CARTESIAN COORDINATES (ANGSTROEM)\n'
                   '---------------------------------\nO 0 0 0\nH 1 0 0\nH 0 1 0\n\nORCA TERMINATED NORMALLY\n')
    freq_dir = tmp_path / 'freq'
    freq_dir.mkdir()
    error, path = process._write_frequency_input(record, str(freq_dir))
    assert error == ''
    paths.append((path, 'Freq'))
    record.job_steps.append(process.TsJobStep(purpose='frequency', job_id=44, input_path=path, state='done'))
    irc_dir = tmp_path / 'irc'
    irc_dir.mkdir()
    error, path = process._write_irc_input(record, str(irc_dir))
    assert error == ''
    paths.append((path, 'IRC'))
    for role in ('reactant', 'product'):
        from cloudra.tools.core.ts_inputs import EndpointSeed
        evidence=tmp_path/'seed-provenance.txt'
        evidence.write_text('fixture provenance')
        getattr(record.input.verification,role+'_endpoint').seed=EndpointSeed(kind='file',xyz_path=str(xyz),evidence_refs=[str(evidence)])
        endpoint_dir = tmp_path / role
        endpoint_dir.mkdir()
        error, path = process._write_endpoint_input(record, str(endpoint_dir), role, 'opt')
        assert error == ''
        paths.append((path, 'Opt'))
        record.job_steps.append(process.TsJobStep(purpose=role+'_opt', job_id=45, input_path=path, state='done',
            endpoint_source=process.EndpointSource.model_validate_json((endpoint_dir/'endpoint_source.json').read_text())))
        monkeypatch.setattr(process, '_endpoint_opt_frame', lambda *_: (xyz.read_text(), ''))
        endpoint_freq_dir = tmp_path / (role+'_freq')
        endpoint_freq_dir.mkdir()
        error, path = process._write_endpoint_input(record, str(endpoint_freq_dir), role, 'frequency')
        assert error == ''
        paths.append((path, 'Freq'))
    for path, task in paths:
        header = next(line for line in Path(path).read_text().splitlines() if line.startswith('!')).split()
        assert header == ['!', 'b3lyp', 'def2-SVP', task, 'D3BJ', 'RIJCOSX', 'def2/J', 'TightSCF', 'CPCM(DCM)'], path
    assert record.input.ts_optimization.method == 'b3lyp'
    assert record.input.ts_optimization.basis_set == 'def2svp'
    assert record.input.ts_optimization.keywords == 'OptTS ' + extras


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize('method,basis_set,keywords,expected', [
    ('b3lyp', 'def2svp', 'Opt RIJCOSX def2/J', '! b3lyp def2-SVP Opt RIJCOSX def2/J'),
    ('b3lyp', 'def2svp', 'Opt RIJK def2/JK', '! b3lyp def2-SVP Opt RIJK def2/JK'),
    ('MP2', 'cc-pVDZ', 'Opt cc-pVDZ/C', '! MP2 cc-pVDZ Opt cc-pVDZ/C'),
])
def test_scan_keeps_auxiliary_basis_slashes(tmp_path, method, basis_set, keywords, expected):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    xyz = tmp_path / 'water.xyz'
    xyz.write_text('3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n')
    target = tmp_path / 'scan.inp'
    result = TsGuess()._scan_prepare(TsGuess_input_schema(charge=0, mode='scan_prepare', engine='orca',
        input_path=str(xyz), method=method, basis_set=basis_set, keywords=keywords, output_path=str(target),
        scans=[{'atoms': [0, 1], 'scan_end': 2, 'scan_steps': 3}]))
    assert result.is_success
    assert target.read_text().splitlines()[0] == expected
