
from pathlib import Path

import pytest

from cloudra.tools.core.ts_inputs import TsInput
from tests.test_ts_inputs import input_payload


def record_fixture(tmp_path, **updates):
    from cloudra.tools.core.ts_process import TsProcessRecord

    data = dict(run_id="ts_0001", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
                owner_conversation_id="project", owner_session_id="owner", input=TsInput.model_validate(input_payload()))
    data.update(updates)
    return TsProcessRecord(**data)


def owned_fixture_structure(record, xyz_path, smiles):
    """One known fixture graph and atom order, materialized as the real owned state."""
    from rdkit import Chem

    from cloudra.tools.core.molecule import read_molecule, with_positions
    from cloudra.tools.core.reaction_state import ReactionStructures
    geometry = read_molecule(str(xyz_path), input_format='xyz')
    graph = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert [atom.GetSymbol() for atom in graph.GetAtoms()] == [atom.GetSymbol() for atom in geometry.GetAtoms()]
    graph.AddConformer(Chem.Conformer(graph.GetNumAtoms()))
    graph = with_positions(graph, geometry.GetConformer().GetPositions())
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = smiles
    record.structures = ReactionStructures(reactant=graph, product=Chem.Mol(graph),
        product_to_reactant=tuple(range(graph.GetNumAtoms())))


@pytest.mark.usefixtures("rdkit_chemistry")
def test_reused_irc_source_job_is_recorded_for_derived_endpoint(tmp_path, monkeypatch):
    from cloudra.tools.core import ts_process
    from tests.ts_fixtures import calculation_input
    seed = tmp_path / 'outer.xyz'
    seed.write_text('3\nouter\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n')
    log = tmp_path / 'irc.log'
    log.write_text('native IRC fixture')
    record = record_fixture(tmp_path, input=calculation_input(reactant_smiles='O', product_smiles='O', method='HF/STO-3G', engine='orca'))
    record.job_steps.append(ts_process.TsJobStep(purpose='irc', state='done', input_path=str(tmp_path/'existing.inp'),
        actual_calculation=record.input.verification.irc, external_source={'source_job_id': 77, 'log_path': str(log)}))
    monkeypatch.setattr('cloudra.tools.Chemtool.ts_guess.TsGuess._extract_irc_endpoints',
        lambda *_, **__: {'path_a': str(seed), 'path_b': str(seed)})
    owned_fixture_structure(record, seed, 'O')
    directory = tmp_path / 'endpoint'
    directory.mkdir()
    error, path = ts_process._write_endpoint_input(record, str(directory), 'reactant', 'opt')
    assert error == '' and Path(path).is_file()
    source = ts_process.EndpointSource.model_validate_json((directory/'endpoint_source.json').read_text())
    assert source.irc_job_id == 77


def test_stage_requires_its_own_calculation_without_fallback(tmp_path):
    from cloudra.tools.core.ts_process import _refine, stage_calculation

    record = record_fixture(tmp_path)
    assert stage_calculation(record, "scan").method == "GFN2-xTB"
    assert stage_calculation(record, "ts_opt").method == "b3lyp"
    assert stage_calculation(record, "ts_opt").basis_set == "def2svp"
    for purpose in ("frequency", "irc", "reactant_opt", "product_opt", "reactant_frequency", "product_frequency"):
        assert stage_calculation(record, purpose) is None
    from cloudra.tools.core.ts_process import TsJobStep
    record.job_steps = [TsJobStep(purpose="ts_opt", job_id=1, input_path="old.inp", state="done")]
    import unittest.mock
    with unittest.mock.patch("cloudra.tools.core.ts_process._read_job_state", return_value="done"):
        _refine(record)
    assert record.blocked.failure_class == "missing_input"
    assert record.blocked.needs == ["verification.frequency"]
    assert record.job_steps[0].job_id == 1


@pytest.mark.usefixtures("rdkit_chemistry")
def test_provided_candidate_skips_search_and_checks_atom_order(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_process import _guess

    candidate = tmp_path / "candidate.xyz"
    candidate.write_text("2\nprovided\nH 0 0 0\nH 0 0 0.74\n")
    log = tmp_path / "scan.log"
    log.write_text("recorded scan provenance")
    value = input_payload()
    value["guess"] = dict(kind="provided", xyz_path=str(candidate), evidence_refs=[str(log)])
    record = record_fixture(tmp_path, input=TsInput.model_validate(value))
    monkeypatch.setattr("cloudra.tools.core.ts_process._queued_path", lambda *args: (_ for _ in ()).throw(AssertionError("no path search")))
    owned_fixture_structure(record, candidate, '[H][H]')
    result = _guess(record)
    assert result.blocked is None
    from cloudra.tools.core.molecule import serialize_molecule
    accepted = serialize_molecule(result.structures.candidate)
    assert result.path_kind == "provided"
    candidate.write_text("2\nwrong atoms\nC 0 0 0\nH 0 0 0.74\n")
    assert _guess(record).blocked is None  # Bound bytes, rather than a later source edit, own this guess.
    assert serialize_molecule(result.structures.candidate) == accepted
    record.provided_guess_binding = None
    record.declaration_revision += 1
    assert _guess(record).blocked.failure_class == "provided_guess_invalid"


@pytest.mark.usefixtures("rdkit_chemistry")
def test_guided_source_uses_its_explicit_calculation_and_bound_windows(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.tools.core.ts_process import _optimize_conformer_source

    mol = Chem.AddHs(Chem.MolFromSmiles('[H][H]'))
    seed = tmp_path / 'seed.xyz'
    seed.write_text('2\nseed\nH 0 0 0\nH .74 0 0\n')
    mol_path = tmp_path / 'seed.mol'
    Chem.MolToMolFile(mol, str(mol_path))
    value = input_payload()
    value['reaction'].update(reactant_smiles='[H][H]', product_smiles='[H][H]')
    value['conformers'] = dict(reactant=dict(kind='file', xyz_path=str(seed), mol_path=str(mol_path),
        optimization=dict(engine='xtb', method='GFN2-xTB', basis_set='', keywords='')),
        guidance=dict(distance_filters=[dict(atoms=[0, 1], min_ang=.7, max_ang=1.)]))
    record = record_fixture(tmp_path, input=TsInput.model_validate(value))
    owned_fixture_structure(record, seed, '[H][H]')
    received = []
    def optimizer(state, key, request):
        received.append(request)
        return dict(symbols=request.symbols, positions=[[0., 0., 0.], [.8, 0., 0.]])
    monkeypatch.setattr('cloudra.tools.core.geometry_optimization.advance_optimization', optimizer)
    _optimize_conformer_source(record, 'reactant')
    assert received[0].method_fingerprint == 'GFN2-xTB'
    assert received[0].distance_constraints[0].atoms == [0, 1]
    assert record.structures.reactant.GetConformer().GetAtomPosition(1).x == .8
    assert seed.read_text().splitlines()[-1] == "H .74 0 0"


@pytest.mark.usefixtures("rdkit_chemistry")
def test_file_sources_are_immutable_and_omitted_sources_are_generated(tmp_path):
    from cloudra.tools.core.reaction_state import source_snapshot
    from cloudra.tools.core.ts_process import _build, _read_built_xyz

    seed = tmp_path / "seed.xyz"
    seed.write_text("2\nsource\nH 0 0 0\nH 0 0 0.74\n")
    value = input_payload()
    value["reaction"].update(reactant_smiles="[H][H]", product_smiles="[H][H]")
    value["conformers"] = dict(reactant=dict(kind="file", xyz_path=str(seed)), product=dict(kind="file", xyz_path=str(seed)))
    record = record_fixture(tmp_path, input=TsInput.model_validate(value))
    _build(record)
    assert record.blocked is None
    copied = _read_built_xyz(record, "reactant")[2]
    assert copied != str(seed)
    accepted_bytes = Path(copied).read_bytes()
    seed.write_text("source subsequently edited")
    assert Path(copied).read_bytes() == accepted_bytes
    record = record_fixture(tmp_path, input=TsInput.model_validate(dict(value, conformers={})))
    assert _build(record).blocked is None
    assert source_snapshot(record.structures.reactant)['kind'] == 'generate'
    assert record.input.conformers.reactant is None


@pytest.mark.usefixtures('rdkit_chemistry')
def test_relative_file_conformers_use_workspace_when_service_cwd_differs(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_inputs import EndpointVerification
    from cloudra.tools.core.ts_process import _build, _write_endpoint_input

    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    cwd = tmp_path / 'service'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    seed = workspace / 'seed.xyz'
    seed.write_text('2\nsource\nH 0 0 0\nH 0 0 .74\n')
    original_seed = seed.read_bytes()
    Chem.MolToMolFile(Chem.AddHs(Chem.MolFromSmiles('[H][H]')), str(workspace / 'seed.mol'))
    value = input_payload()
    value['reaction'].update(reactant_smiles='[H][H]', product_smiles='[H][H]')
    value['conformers'] = dict(reactant=dict(kind='file', xyz_path='seed.xyz', mol_path='seed.mol'),
                              product=dict(kind='file', xyz_path='seed.xyz', mol_path='seed.mol'))
    record = record_fixture(workspace, input=TsInput.model_validate(value))
    result = _build(record)
    assert result.blocked is None
    from cloudra.tools.core.reaction_state import source_snapshot
    assert source_snapshot(result.structures.reactant)['paths'] == {'xyz': str(seed), 'mol': str(workspace / 'seed.mol')}
    owned_fixture_structure(record, seed, '[H][H]')
    record.input.verification.reactant_endpoint = EndpointVerification(
        seed={'kind': 'file', 'xyz_path': 'seed.xyz', 'evidence_refs': ['seed.mol']},
        optimization={'engine': 'orca', 'method': 'HF', 'basis_set': 'STO-3G'},
    )
    job_dir = workspace / 'endpoint'
    job_dir.mkdir()
    error, input_path = _write_endpoint_input(record, str(job_dir), 'reactant', 'opt')
    assert error == '' and Path(input_path).is_file()
    assert read_xyz_atoms(job_dir / 'reactant_source.xyz') == read_xyz_atoms(seed)
    assert seed.read_bytes() == original_seed


@pytest.mark.parametrize('source_kind', ['parent', 'symlink', 'absolute'])
def test_file_conformer_cannot_escape_bound_workspace(tmp_path, source_kind):
    from cloudra.tools.core.ts_process import _build

    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    external = tmp_path / 'outside.xyz'
    external.write_text('2\nexternal\nH 0 0 0\nH 0 0 .74\n')
    link = workspace / 'linked.xyz'
    link.symlink_to(external)
    source = {'parent': '../outside.xyz', 'symlink': 'linked.xyz', 'absolute': str(external)}[source_kind]
    value = input_payload()
    value['conformers'] = {'reactant': {'kind': 'file', 'xyz_path': source}}
    record = record_fixture(workspace, input=TsInput.model_validate(value))
    result = _build(record)
    assert result.blocked.failure_class == 'conformer_source_invalid'
    assert result.structures.reactant is None and result.evidence_candidates == []


@pytest.mark.usefixtures("rdkit_chemistry")
def test_relative_provided_guess_and_provenance_use_workspace(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_process import _guess

    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    cwd = tmp_path / 'service'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    candidate = workspace / 'candidate.xyz'
    candidate.write_text('2\nprovided\nH 0 0 0\nH 0 0 .74\n')
    (workspace / 'scan.log').write_text('recorded scan provenance')
    value = input_payload()
    value['guess'] = dict(kind='provided', xyz_path='candidate.xyz', evidence_refs=['scan.log'])
    record = record_fixture(workspace, input=TsInput.model_validate(value))
    owned_fixture_structure(record, candidate, '[H][H]')
    result = _guess(record)
    assert result.blocked is None
    assert result.structures.candidate.GetConformer().GetPositions().tolist() == [[0., 0., 0.], [0., 0., .74]]
    provenance = next(Path(path) for path in record.stage_record('guess').artifacts if Path(path).name == 'provenance_0000.log')
    assert provenance.read_text() == 'recorded scan provenance'


@pytest.mark.usefixtures("rdkit_chemistry")
def test_no_hidden_xtb_to_interpolation_fallback(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_process import _guess
    from cloudra.tools.core.xtb_path_runner import XtbPathResult

    value = input_payload()
    value["guess"] = dict(kind="xtb_path", method="GFN2-xTB")
    record = record_fixture(tmp_path, input=TsInput.model_validate(value), pipeline_id="process")
    seed = tmp_path / 'seed.xyz'
    seed.write_text('2\nH2\nH 0 0 0\nH 0 0 .74\n')
    owned_fixture_structure(record, seed, '[H][H]')
    monkeypatch.setattr("cloudra.tools.core.ts_process._queued_path", lambda *args: (XtbPathResult(termination_reason="executable_missing", run_dir=str(tmp_path)), record))
    result = _guess(record)
    assert result.blocked is not None
    assert result.structures.candidate is None


@pytest.mark.usefixtures("rdkit_chemistry")
def test_explicit_generation_delivers_seed_without_hidden_force_field(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_process import _build, _read_built_xyz
    def forbidden(*args, **kwargs):
        raise AssertionError('No conformer optimization was declared')
    monkeypatch.setattr('cloudra.tools.core.structure_builder._optimize_component', forbidden)
    value = input_payload()
    value['reaction'].update(reactant_smiles='[F-].CCl', product_smiles='CF.[Cl-]', charge=-1)
    value['conformers'] = dict(reactant=dict(kind='generate', generation='ETKDGv3', seed=42),
                              product=dict(kind='generate', generation='ETKDGv3', seed=42))
    record = record_fixture(tmp_path, input=TsInput.model_validate(value))
    _build(record)
    assert record.blocked is None
    assert _read_built_xyz(record, 'reactant')[0] == ['F', 'C', 'Cl', 'H', 'H', 'H']
    assert _read_built_xyz(record, 'product')[0] == ['C', 'F', 'H', 'H', 'H', 'Cl']
    assert record.job_steps == []


@pytest.mark.usefixtures("rdkit_chemistry")
def test_one_prepare_advances_complete_declared_chain_without_agent_resume(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
    from tests.ts_fixtures import calculation_input

    seed = tmp_path / 'seed.xyz'
    seed.write_text('3\nWater seed\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n')
    provenance = tmp_path / 'guess.log'
    provenance.write_text('Explicit external candidate provenance')
    inputs = calculation_input(reactant_smiles='O',product_smiles='O',method='HF/STO-3G')
    from cloudra.tools.core.ts_inputs import FileConformer, ProvidedGuess
    inputs.conformers.reactant = FileConformer(kind='file',xyz_path=str(seed))
    inputs.conformers.product = FileConformer(kind='file',xyz_path=str(seed))
    inputs.guess = ProvidedGuess(kind='provided',xyz_path=str(seed),evidence_refs=[str(provenance)])
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    monkeypatch.setattr(ts_process,'resume',lambda *_: (_ for _ in ()).throw(AssertionError('System progression must not call resume')))
    def writer(record, directory, role=None, task=None):
        purpose = 'frequency' if role is None else role+'_'+task
        task_token = 'Freq' if purpose.endswith('frequency') else 'Opt'
        path = Path(directory) / (purpose+'.inp')
        path.write_text('! HF STO-3G '+task_token+'\n* xyz 0 1\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n*\n')
        (Path(directory) / 'optimized.xyz').write_text(seed.read_text())
        if role is not None:
            import hashlib
            source = ts_process.EndpointSource(kind='species_reference', label=role,
                source_path=str(seed), sha256=hashlib.sha256(seed.read_bytes()).hexdigest())
            (Path(directory) / 'endpoint_source.json').write_text(source.model_dump_json())
        return '',str(path)
    monkeypatch.setattr(ts_process,'_write_frequency_input',writer)
    monkeypatch.setattr(ts_process,'_write_endpoint_input',writer)
    monkeypatch.setattr(ts_process,'_validated_endpoint_minimum',lambda *_: ((['O','H','H'],[[0,0,0],[0.96,0,0],[-0.24,0.93,0]]),''))
    monkeypatch.setattr('cloudra.dag.evidence_ingest.snapshot_evidence_file',lambda *_,**__: SimpleNamespace(frequencies=[-100.,200.],imaginary_frequencies=[-100.]))
    first = ts_process.start(ts_process.TsStartRequest(input=inputs,workspace_dir=str(tmp_path),
        owner_conversation_id='project',owner_session_id='owner',request_key='complete-chain'))
    assert first.waiting_for
    db = ComputeDB()
    current, visits = first, []
    while current.waiting_for:
        job = int(current.waiting_for.partition(':')[2])
        step = next(s for s in current.job_steps if s.job_id == job)
        visits.append(step.purpose)
        log = Path(ts_process._refinement_log_path(current,step))
        log.parent.mkdir(parents=True,exist_ok=True)
        log.write_text('ORCA TERMINATED NORMALLY\nfixture calculation')
        with db.connect() as con:
            con.execute("UPDATE compute_jobs SET state='done' WHERE id=?",(job,))
        current = ts_process.TsProcessRecord.model_validate(handle_process_job_terminal(db,job)['record'])
        again = ts_process.TsProcessRecord.model_validate(handle_process_job_terminal(db,job)['record'])
        assert again.waiting_for == current.waiting_for
        assert len(visits) <= 7
    assert visits == ['ts_opt','frequency','irc','reactant_opt','reactant_frequency','product_opt','product_frequency']
    assert current.is_terminal and current.intervention_count == 0
    assert current.run_id == first.run_id
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 7


pytestmark = pytest.mark.usefixtures("ts_producer_authority")


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize('relative_source', [False, True])
def test_existing_irc_source_requires_authoritative_method_geometry_and_two_sides(tmp_path, monkeypatch, relative_source):
    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process
    from cloudra.tools.core.ts_process import TsJobStep, _reuse_existing_irc
    from tests.test_ts_pipeline_store import payload
    from tests.ts_fixtures import calculation_input
    inputs=calculation_input(reactant_smiles='O',product_smiles='O',method='HF/STO-3G')
    record=record_fixture(tmp_path,input=inputs)
    frequency=tmp_path/'frequency'
    frequency.mkdir()
    seed='3\nverified frequency frame\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n'
    (frequency/'optimized.xyz').write_text(seed)
    record.job_steps=[TsJobStep(purpose='frequency',job_id=99,input_path=str(frequency/'freq.inp'),state='done',actual_calculation=inputs.verification.frequency)]
    source=tmp_path/'existing.inp'
    source.write_text('! IRC HF STO-3G\n%irc Direction both end\n* xyz 0 1\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n*\n')
    db=ComputeDB().init()
    prior=create_process(db,request_key='source',payload=payload(workspace_dir=str(tmp_path)))['process_id']
    job=bind_stage_job(db,process_id=prior,declaration_revision=1,stage_key='irc',attempt=1,job_payload=dict(conversation_id='project',session_id='owner',path=str(source),state='ready',jobtype='orca',node_id='fixture'))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
    log=Path(resolve_log_path(str(source),job_type='orca',task_id=job))
    log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text('ORCA TERMINATED NORMALLY\n')
    cwd = tmp_path / 'service'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    record.input.verification.irc_log=str(log.relative_to(tmp_path)) if relative_source else str(log)
    monkeypatch.setattr('cloudra.tools.Chemtool.ts_guess.TsGuess._extract_irc_endpoints', lambda *_args,**_kwargs: {'path_a':str(frequency/'optimized.xyz'),'path_b':str(frequency/'optimized.xyz')})
    step=_reuse_existing_irc(record)
    assert step.state=='done' and step.job_id is None
    assert step.external_source['source_job_id']==job
    assert step.source_input_revision==record.declaration_revision
    assert step.input_path!=str(source)
    source.write_text(source.read_text().replace('H 0.96','H 1.96'))
    with pytest.raises(ValueError,match='geometry|input bytes'):
        _reuse_existing_irc(record)
    source.write_text(source.read_text().replace('H 1.96','H 0.96'))
    monkeypatch.setattr('cloudra.tools.Chemtool.ts_guess.TsGuess._extract_irc_endpoints',lambda *_args,**_kwargs: None)
    with pytest.raises(ValueError,match='two'):
        _reuse_existing_irc(record)
    record.input.verification.irc_log=str(tmp_path/'unregistered.out')
    (tmp_path/'unregistered.out').write_text('ORCA TERMINATED NORMALLY\n')
    with pytest.raises(ValueError,match='authoritative'):
        _reuse_existing_irc(record)
