"""Reaction guesses use confirmed endpoint state rather than copied atom maps."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema


def endpoint_text(*, product=False, shuffled=False):
    Chem = pytest.importorskip('rdkit.Chem')
    mol = Chem.MolFromSmiles('[H:1][O:2][F:3]', sanitize=False)
    Chem.SanitizeMol(mol)
    conf = Chem.Conformer(3)
    for index, position in enumerate([(0., 0., 0.), (1. if product else 1.8, 0., 0.), (2.8, .3, 0.)]):
        conf.SetAtomPosition(index, position)
    mol.AddConformer(conf)
    if shuffled:
        mol = Chem.RenumberAtoms(mol, [2, 0, 1])
    return Chem.MolToMolBlock(mol)


@pytest.mark.parametrize('mode', ['xtb_path', 'interpolate', 'scan', 'provided'])
def test_run_guess_schema_reads_run_without_endpoint_transport(mode):
    request = TsGuess_input_schema(mode=mode, run_id='ts_0007')
    assert request.run_id == 'ts_0007'
    assert 'atom_map' not in request.to_parameters_schema()['properties']
    jsonschema = pytest.importorskip('jsonschema')
    jsonschema.Draft202012Validator(request.to_parameters_schema()).validate(
        {'mode': mode, 'run_id': 'ts_0007'})


@pytest.mark.parametrize('override', [
    {'reactant_path': 'reactant.mol'}, {'product_text': 'MOL'},
    {'input_path': 'replacement.xyz'}, {'charge': 0}, {'multiplicity': 1},
    {'output_dir': 'another-run'},
])
def test_run_guess_refuses_a_second_endpoint_or_resource_source(override):
    with pytest.raises(ValidationError):
        TsGuess_input_schema(mode='xtb_path', run_id='ts_0007', **override)


def test_geometry_guess_rejects_public_atom_map_transport():
    with pytest.raises(ValidationError, match='atom_map'):
        TsGuess_input_schema(mode='interpolate', reactant_text=endpoint_text(),
                             product_text=endpoint_text(product=True), atom_map=[1, 2, 3])


@pytest.mark.asyncio
async def test_independent_interpolation_uses_proved_concrete_mapping(tmp_path):
    import numpy as np

    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    tool = TsGuess()
    outputs = []
    for shuffled, directory in [(False, 'ordered'), (True, 'shuffled')]:
        outputs.append(await tool.tool_call(TsGuess_input_schema(
            mode='interpolate', reactant_text=endpoint_text(),
            product_text=endpoint_text(product=True, shuffled=shuffled),
            n_images=4, interp_method='linear', output_dir=str(tmp_path / directory)), None))
    assert all(result.is_success for result in outputs), [result.message for result in outputs]
    assert outputs[0].distance_table == outputs[1].distance_table
    ordered = read_xyz_atoms(str(tmp_path / 'ordered' / 'img_03.xyz'))
    shuffled = read_xyz_atoms(str(tmp_path / 'shuffled' / 'img_03.xyz'))
    assert [row[0] for row in shuffled] == ['H', 'O', 'F']
    np.testing.assert_allclose([row[1] for row in shuffled], [row[1] for row in ordered])


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_unresolved_xyz_does_not_establish_endpoint_identity(tmp_path):
    xyz = '3\nunknown graph\nH 0 0 0\nO 1 0 0\nF 2.8 .3 0\n'
    result = await TsGuess().tool_call(TsGuess_input_schema(mode='interpolate',
        reactant_text=xyz, product_text=xyz, output_dir=str(tmp_path)), None)
    assert not result.is_success
    assert 'MOL' in result.message or 'unresolved' in result.message
    assert not list(tmp_path.glob('img_*.xyz'))


@pytest.mark.asyncio
async def test_independent_mapping_ambiguity_uses_ranked_default_and_allows_override(tmp_path):
    Chem = pytest.importorskip('rdkit.Chem')
    mol = Chem.AddHs(Chem.MolFromSmiles('CC'))
    conf = Chem.Conformer(mol.GetNumAtoms())
    for index in range(mol.GetNumAtoms()):
        conf.SetAtomPosition(index, (float(index), float(index % 2), 0.))
    mol.AddConformer(conf)
    source = Chem.MolToMolBlock(mol)
    tool = TsGuess()
    automatic = await tool.tool_call(TsGuess_input_schema(mode='interpolate',
        reactant_text=source, product_text=source, n_images=2, interp_method='linear',
        output_dir=str(tmp_path / 'automatic')), None)
    assert automatic.is_success, automatic.message
    assert len(list((tmp_path / 'automatic').glob('img_*.xyz'))) == 2
    assert all(path.read_text().splitlines()[0] == '8'
               for path in (tmp_path / 'automatic').glob('img_*.xyz'))
    selected = await tool.tool_call(TsGuess_input_schema(mode='interpolate',
        reactant_text=source, product_text=source, selected_candidate=1, n_images=2,
        interp_method='linear', output_dir=str(tmp_path / 'selected')), None)
    assert selected.is_success, selected.message
    assert len(list((tmp_path / 'selected').glob('img_*.xyz'))) == 2


@pytest.mark.asyncio
async def test_xtb_failure_keeps_runner_diagnostics_and_original_message(tmp_path, monkeypatch):
    from cloudra.tools.core.xtb_path_runner import XtbPathResult

    directory = tmp_path / 'native-run'
    directory.mkdir()
    monkeypatch.setattr('cloudra.tools.core.xtb_path_runner.run_xtb_path', lambda request:
        XtbPathResult(run_dir=str(directory), termination_reason='failed', returncode=3,
            message='Native driver could not initialize the Hamiltonian',
            diagnostics=['Engine wrote partial frame xtbpath_12.xyz', 'See stderr.log for the native error']))
    result = await TsGuess().tool_call(TsGuess_input_schema(mode='xtb_path',
        reactant_text=endpoint_text(), product_text=endpoint_text(product=True),
        output_dir=str(tmp_path)), None)
    assert not result.is_success
    assert result.images_dir == str(directory)
    assert 'Native driver could not initialize the Hamiltonian' in result.message
    assert result.diagnostics == ['Engine wrote partial frame xtbpath_12.xyz', 'See stderr.log for the native error']


@pytest.mark.asyncio
async def test_xtb_missing_reuses_already_ordered_endpoints_for_interpolation(tmp_path, monkeypatch):
    from cloudra.tools.core.xtb_path_runner import XtbPathResult

    captured = []
    def missing(request):
        captured.append(request)
        return XtbPathResult(run_dir=str(tmp_path / 'missing'), termination_reason='executable_missing',
            message='xtb executable missing', diagnostics=['No engine was started'])
    monkeypatch.setattr('cloudra.tools.core.xtb_path_runner.run_xtb_path', missing)
    result = await TsGuess().tool_call(TsGuess_input_schema(mode='xtb_path',
        reactant_text=endpoint_text(), product_text=endpoint_text(product=True, shuffled=True),
        n_images=4, interp_method='linear', output_dir=str(tmp_path)), None)
    assert result.is_success, result.message
    assert result.path_kind == 'idpp_fallback'
    assert [line.split()[0] for line in captured[0].product_xyz.splitlines()[2:]] == ['H', 'O', 'F']
    assert Path(result.images_dir, 'img_03.xyz').read_text().splitlines()[2].split()[0] == 'H'
    assert result.diagnostics == ['No engine was started']


def run_fixture(directory):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import create_process, save_process_record
    from cloudra.tools.core.molecule import read_molecule
    from cloudra.tools.core.reaction_state import ReactionStructures
    from cloudra.tools.core.ts_inputs import TsInput
    from cloudra.tools.core.ts_process import TsProcessRecord

    reactant = read_molecule(input_text=endpoint_text())
    product = read_molecule(input_text=endpoint_text(product=True, shuffled=True))
    inputs = TsInput(reaction=dict(reactant_smiles='OF', product_smiles='OF', charge=0, multiplicity=1))
    db = ComputeDB(data_dir=directory / 'data').init()
    process = create_process(db, request_key='prepared-run', payload=dict(
        project_id='project', owner_id='owner', workspace_dir=str(directory), input=inputs.model_dump(mode='json')))
    record = TsProcessRecord(run_id='ts_0007', pipeline_id=process['process_id'],
        run_dir=str(directory / 'ts' / 'ts_0007'), workspace_dir=str(directory),
        owner_conversation_id='project', owner_session_id='owner', input=inputs, stage='guess',
        structures=ReactionStructures(reactant=reactant, product=product, product_to_reactant=(2, 0, 1)),
        blocked=dict(stage='guess', failure_class='missing_input', message='Choose a guess route', needs=['guess']))
    Path(record.run_dir).mkdir(parents=True)
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
    return db, record


def run_tool(directory, *, write=True):
    from types import SimpleNamespace

    from cloudra.tools.core.permission_model import Permission
    return TsGuess(subagent=SimpleNamespace(conversation_id='project', working_directory=str(directory),
        permission_all=lambda: Permission.WRITE if write else Permission.READ))


@pytest.mark.asyncio
@pytest.mark.usefixtures('ts_producer_authority')
async def test_run_path_uses_revision_and_existing_queue_without_direct_runner(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from cloudra.runtime_v2.invocation_context import InvocationScope, reset_invocation_scope, set_invocation_scope
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import get_process, get_revision_receipt

    db, record = await asyncio.to_thread(run_fixture, tmp_path)
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))
    def no_direct_runner(*_):
        raise AssertionError('run-based guesses must use the existing durable queue')
    monkeypatch.setattr('cloudra.tools.core.xtb_path_runner.run_xtb_path', no_direct_runner)
    token = set_invocation_scope(InvocationScope(tool_call_id='run-path-choice', tool_name='ts_guess'))
    try:
        with use_pipeline_database(db):
            result = await run_tool(tmp_path).tool_call(TsGuess_input_schema(
                mode='xtb_path', run_id=record.run_id, method='GFN2-xTB'), SimpleNamespace(id='owner'))
            replay = await run_tool(tmp_path).tool_call(TsGuess_input_schema(
                mode='xtb_path', run_id=record.run_id, method='GFN2-xTB'), SimpleNamespace(id='owner'))
    finally:
        reset_invocation_scope(token)
    assert result.is_success, result.message
    assert replay.is_success, replay.message
    assert replay.process['revision'] == result.process['revision']
    state = await asyncio.to_thread(get_process, db, record.pipeline_id)
    assert state['record']['input']['guess']['kind'] == 'xtb_path'
    assert state['record']['input']['guess']['method'] == 'GFN2-xTB'
    assert state['record']['declaration_revision'] == 2
    receipt = await asyncio.to_thread(get_revision_receipt, db,
        process_id=record.pipeline_id, request_key='run-path-choice')
    assert receipt is not None
    assert result.process['run_id'] == record.run_id
    def jobs():
        with db.connect() as con:
            return con.execute('SELECT state,jobtype FROM compute_jobs').fetchall()
    assert await asyncio.to_thread(jobs) == [('ready', 'chem_task')]


@pytest.mark.asyncio
@pytest.mark.usefixtures('ts_producer_authority')
async def test_run_path_missing_method_does_not_invent_science_or_write_state(tmp_path):
    import asyncio

    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import get_process

    db, record = await asyncio.to_thread(run_fixture, tmp_path)
    before = await asyncio.to_thread(get_process, db, record.pipeline_id)
    with use_pipeline_database(db):
        result = await run_tool(tmp_path).tool_call(TsGuess_input_schema(mode='xtb_path', run_id=record.run_id), None)
    assert not result.is_success and 'method' in result.message
    assert await asyncio.to_thread(get_process, db, record.pipeline_id) == before


@pytest.mark.asyncio
async def test_run_guess_checks_write_permission_before_loading_state(tmp_path, monkeypatch):
    def no_read(*_):
        raise AssertionError('a read-only caller must not load a mutable run')
    monkeypatch.setattr('cloudra.tools.Chemtool.ts_search_process._read_resume_record', no_read)
    result = await run_tool(tmp_path, write=False).tool_call(
        TsGuess_input_schema(mode='xtb_path', run_id='ts_0007'), None)
    assert not result.is_success and 'write permission' in result.message


@pytest.mark.asyncio
@pytest.mark.usefixtures('ts_producer_authority')
async def test_run_interpolation_commits_provided_candidate_and_keeps_science_unverified(tmp_path):
    import asyncio
    from types import SimpleNamespace

    from cloudra.runtime_v2.invocation_context import InvocationScope, reset_invocation_scope, set_invocation_scope
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import get_process

    db, record = await asyncio.to_thread(run_fixture, tmp_path)
    token = set_invocation_scope(InvocationScope(tool_call_id='interpolation-choice', tool_name='ts_guess'))
    try:
        with use_pipeline_database(db):
            result = await run_tool(tmp_path).tool_call(TsGuess_input_schema(
                mode='interpolate', run_id=record.run_id, n_images=4, interp_method='linear'), SimpleNamespace(id='owner'))
            replay = await run_tool(tmp_path).tool_call(TsGuess_input_schema(
                mode='interpolate', run_id=record.run_id, n_images=4, interp_method='linear'), SimpleNamespace(id='owner'))
    finally:
        reset_invocation_scope(token)
    assert result.is_success, result.message
    assert replay.is_success, replay.message
    assert replay.process['revision'] == result.process['revision']
    state = await asyncio.to_thread(get_process, db, record.pipeline_id)
    assert state['record']['input']['guess']['kind'] == 'provided'
    assert state['record']['declaration_revision'] == 2
    assert state['record']['structures']['candidate'] is not None
    assert state['record']['terminal'] is None
    assert state['record']['blocked']['needs'] == ['ts_optimization']
    assert result.process['result'] is None


@pytest.mark.asyncio
@pytest.mark.usefixtures('ts_producer_authority')
async def test_run_guess_does_not_apply_an_intent_assembled_from_a_stale_snapshot(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from cloudra.runtime_v2.invocation_context import InvocationScope, reset_invocation_scope, set_invocation_scope
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import get_process, save_process_record
    from cloudra.tools.Chemtool import ts_search_process

    db, record = await asyncio.to_thread(run_fixture, tmp_path)
    original = ts_search_process.revise_run
    async def concurrent_revision(*args, **kwargs):
        state = await asyncio.to_thread(get_process, db, record.pipeline_id)
        state['record']['blocked']['message'] = 'A newer research decision is now authoritative'
        await asyncio.to_thread(save_process_record, db, process_id=record.pipeline_id, record=state['record'])
        return await original(*args, **kwargs)
    monkeypatch.setattr(ts_search_process, 'revise_run', concurrent_revision)
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))
    token = set_invocation_scope(InvocationScope(tool_call_id='stale-guess', tool_name='ts_guess'))
    try:
        with use_pipeline_database(db):
            result = await run_tool(tmp_path).tool_call(TsGuess_input_schema(
                mode='xtb_path', run_id=record.run_id, method='GFN2-xTB'), SimpleNamespace(id='owner'))
    finally:
        reset_invocation_scope(token)
    assert not result.is_success
    assert 'stale' in result.message.lower()
    state = await asyncio.to_thread(get_process, db, record.pipeline_id)
    assert state['record']['input']['guess'] is None
    assert state['record']['declaration_revision'] == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures('ts_producer_authority')
async def test_run_scan_submits_existing_endpoint_with_explicit_scientific_settings(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from cloudra.runtime_v2.invocation_context import InvocationScope, reset_invocation_scope, set_invocation_scope
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import get_process

    db, record = await asyncio.to_thread(run_fixture, tmp_path)
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))
    token = set_invocation_scope(InvocationScope(tool_call_id='run-scan-choice', tool_name='ts_guess'))
    try:
        with use_pipeline_database(db):
            result = await run_tool(tmp_path).tool_call(TsGuess_input_schema(
                mode='scan', run_id=record.run_id, engine='orca', method='HF', basis_set='STO-3G',
                scans=[dict(atoms=[0, 1], scan_end=2.2, scan_steps=5)]), SimpleNamespace(id='owner'))
    finally:
        reset_invocation_scope(token)
    assert result.is_success, result.message
    state = await asyncio.to_thread(get_process, db, record.pipeline_id)
    guess = state['record']['input']['guess']
    assert guess['kind'] == 'scan'
    assert guess['calculation']['method'] == 'HF' and guess['calculation']['basis_set'] == 'STO-3G'
    assert guess['scans'][0]['atoms'] == [0, 1]
    assert state['record']['scan_step']['state'] == 'ready'


@pytest.mark.asyncio
@pytest.mark.usefixtures('ts_producer_authority')
async def test_run_provided_candidate_is_accepted_through_the_same_revision(tmp_path):
    import asyncio
    from types import SimpleNamespace

    from cloudra.runtime_v2.invocation_context import InvocationScope, reset_invocation_scope, set_invocation_scope
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core.molecule import to_xyz

    db, record = await asyncio.to_thread(run_fixture, tmp_path)
    candidate = tmp_path / 'candidate.xyz'
    await asyncio.to_thread(candidate.write_text, to_xyz(record.structures.reactant))
    token = set_invocation_scope(InvocationScope(tool_call_id='provided-choice', tool_name='ts_guess'))
    try:
        with use_pipeline_database(db):
            result = await run_tool(tmp_path).tool_call(TsGuess_input_schema(mode='provided',
                run_id=record.run_id, ts_candidate_path='candidate.xyz', evidence_refs=['candidate.xyz']),
                SimpleNamespace(id='owner'))
    finally:
        reset_invocation_scope(token)
    assert result.is_success, result.message
    state = await asyncio.to_thread(get_process, db, record.pipeline_id)
    assert state['record']['input']['guess']['kind'] == 'provided'
    assert state['record']['structures']['candidate'] is not None
    assert state['record']['declaration_revision'] == 2
