"""Human molecular edits retain their source without inheriting chemical claims."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentSession, Project
from cloudra.services.api_v2 import create_v2_app
from cloudra.tools.core.molecule import serialize_molecule


def _molecule():
    from rdkit import Chem

    mol = Chem.MolFromSmiles('CO')
    conf = Chem.Conformer(2)
    conf.SetAtomPosition(0, (0, 0, 0))
    conf.SetAtomPosition(1, (1.4, 0, 0))
    mol.AddConformer(conf)
    return serialize_molecule(mol)


def _core(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    core = RuntimeCore(strict_events=True)
    core.projects['p'] = Project(id='p', name='Chemistry', workspace_dir=str(root))
    core.agents['a'] = AgentSession(id='a', project_id='p', role_id='coordinator', display_name='Coordinator')
    return core, root


@pytest.mark.asyncio
async def test_manual_builder_round_trip_from_blank_to_saved_structure(tmp_path):
    core, _root = _core(tmp_path)
    base = '/api/v2/projects/p/workbench'
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        async def edit(**body):
            response = await client.post(f'{base}/edit', json=body)
            assert response.status_code == 200, response.text
            return response.json()

        seed = await edit(action='add_atom', element='N')
        nitrogen = seed['atoms'][0]
        assert nitrogen['symbol'] == 'N' and not seed['bonds']
        declared = await edit(action='atom_state', molecule=seed['molecule'], atoms=[1], formal_charge=1, valence=4)
        ammonium = await edit(action='fill_valence', molecule=declared['molecule'], atoms=[1])
        assert [atom['symbol'] for atom in ammonium['atoms']] == ['N', 'H', 'H', 'H', 'H']
        assert ammonium['atoms'][0]['bond_valence'] == 4
        assert ammonium['atoms'][0]['atom_id'] == nitrogen['atom_id']
        assert len(ammonium['bonds']) == 4

        response = await client.post(f'{base}/save', json={'title': 'Ammonium', 'molecule': ammonium['molecule']})
        assert response.status_code == 200, response.text
        saved = response.json()
        assert Path(saved['files']['mol']).is_file()
        reopened = await client.post(f'{base}/open', json={'path': saved['path']})
        assert reopened.status_code == 200, reopened.text
        geometry = reopened.json()['geometry']
        assert geometry['atoms'] == ammonium['atoms']
        assert geometry['bonds'] == ammonium['bonds']
        assert geometry['atoms'][0]['formal_charge'] == 1
        assert geometry['atoms'][0]['target_valence'] == 4

        empty = await edit(action='delete_atom', molecule=geometry['molecule'], atoms=[1, 2, 3, 4, 5])
        assert empty['atoms'] == [] and empty['bonds'] == []
        rejected = await client.post(f'{base}/save', json={'molecule': empty['molecule']})
        assert rejected.status_code == 400
    await core.aclose()


def _dag_store():
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    store = DagStore(ConversationDB('p').init())
    store.ensure_bundle('user')
    return store


def _add_node(store, refs=()):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import MutationBatch

    result = DagEngine(store).apply_batch(MutationBatch.model_validate({
        'session_id': 'user', 'actor': 'user', 'actor_id': 'user',
        'base_revisions': store.load_bundle().revisions,
        'operations': [{'op': 'add_node', 'graph': 'delivery', 'node': {
            'node_id': 'sp_a', 'node_type': 'species', 'name': 'A', 'label': 'A',
            'refs': [ref.model_dump(mode='json') for ref in refs],
        }}],
    }))
    assert result.accepted, result


@pytest.mark.asyncio
async def test_saved_structure_exposes_valid_canonical_reference_for_manual_association(tmp_path):
    core, _root = _core(tmp_path)
    store = _dag_store()
    _add_node(store)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        saved = (await client.post('/api/v2/projects/p/workbench/save', json={'molecule': _molecule()})).json()
        listing = (await client.get('/api/v2/projects/p/workbench/products')).json()
        product = next(item for item in listing['products'] if item['path'] == saved['path'])
        assert not product['associations']
        assert listing['objects'] == [{'kind': 'node', 'id': 'sp_a', 'label': 'A'}]
        reference = product['association_ref']
        assert reference['ref_type'] == 'artifact' and reference['content_hash']
        attached = await client.post('/api/v2/projects/p/dag/mutations', json={
            'base_revisions': store.load_bundle().revisions,
            'operations': [{'op': 'attach_ref', 'graph': 'delivery', 'target_type': 'node',
                            'target_id': 'sp_a', 'ref': reference}],
            'rationale': 'User explicitly associates this edited candidate',
        })
        assert attached.status_code == 200 and attached.json()['accepted'], attached.text
        result = (await client.get('/api/v2/projects/p/workbench/products')).json()
        assert next(item for item in result['products'] if item['path'] == saved['path'])['associations'][0]['id'] == 'sp_a'
        node = store.load_snapshot().delivery.nodes[0]
        assert node.evidence_level == 'proposed'
    await core.aclose()


@pytest.mark.asyncio
async def test_native_file_evidence_resolves_to_calculation_and_snapshot_without_inheriting_changed_file(tmp_path):
    import hashlib

    from cloudra.dag.evidence_ingest import FileEvidenceSnapshot
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import insert_compute_job

    core, root = _core(tmp_path)
    input_path = root / 'run.gjf'
    input_path.write_text('input')
    output = root / 'run.log'
    output.write_text('original native output')
    snapshot = root / '.cloudra' / 'evidence' / 'original.log'
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(output.read_bytes())
    store = _dag_store()
    evidence = FileEvidenceSnapshot(original_path=str(output), snapshot_path=str(snapshot),
                                    sha256=hashlib.sha256(output.read_bytes()).hexdigest(), file_size=output.stat().st_size)
    ref = store.register_evidence('user', 'run.log', evidence.model_dump(mode='json'), source_type='file')
    _add_node(store, [ref])
    insert_compute_job(ComputeDB().init(), node_id='node-local', conversation_id='p', session_id='a',
                       path=str(input_path), state='done', jobtype='gaussian', scheduler='local')
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        listing = (await client.get('/api/v2/projects/p/workbench/products')).json()['products']
        job = next(item for item in listing if item['kind'] == 'calculation')
        assert job['path'] == str(output)
        assert job['associations'][0]['ref_id'] == ref.ref_id
        assert job['associations'][0]['id'] == 'sp_a'
        output.write_text('a different later calculation')
        listing = (await client.get('/api/v2/projects/p/workbench/products')).json()['products']
        assert not next(item for item in listing if item['kind'] == 'calculation')['associations']
        preserved = next(item for item in listing if item['path'] == str(snapshot))
        assert preserved['associations'][0]['id'] == 'sp_a'
        assert preserved['association_ref']['ref_id'] == ref.ref_id
    await core.aclose()


@pytest.mark.asyncio
async def test_open_stays_inside_project_and_unknown_project_is_404(tmp_path):
    core, root = _core(tmp_path)
    (root / 'structure.xyz').write_text('2\nsource\nC 0 0 0\nO 1.4 0 0\n')
    outside = tmp_path / 'other.xyz'
    outside.write_text('1\nother\nH 0 0 0\n')
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/workbench/open', json={'path': str(outside)})
        assert response.status_code == 400
        response = await client.post('/api/v2/projects/missing/workbench/open', json={'path': 'structure.xyz'})
        assert response.status_code == 404
        response = await client.post('/api/v2/projects/p/workbench/open', json={'path': 'structure.xyz'})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['geometry']['atoms'][1]['index'] == 2
        assert body['selected_frame'] == 0
    await core.aclose()


@pytest.mark.asyncio
async def test_save_preserves_selected_frame_and_notifies_without_inheriting_identity(tmp_path):
    core, root = _core(tmp_path)
    source = root / 'original.xyz'
    source.write_text(''.join(f'2\nframe {i}\nC 0 0 0\nO {1.1 + i * .1} 0 0\n' for i in range(4)))
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/workbench/save', json={
            'title': 'Human geometry', 'molecule': _molecule(),
            'source_path': str(source), 'source_frame': 3,
            'settings': {}, 'frozen_coordinates': [], 'scan_coordinates': [],
            'generate_input': False,
        })
        assert response.status_code == 200, response.text
        saved = response.json()
        target = Path(saved['path'])
        assert target.is_relative_to(root / '.cloudra')
        state = json.loads(target.read_text())
        assert state['source_path'] == str(source)
        assert state['source_frame'] == 3
        assert not any(key in state for key in ('species_id', 'node_id', 'evidence_level'))
        assert 'molecule' in state
        assert Path(saved['files']['xyz']).is_file()
        assert Path(saved['files']['mol']).is_file()
        posts = core.event_log.query_project('p', types={'hub.posted'})
        assert len(posts) == 1
        assert str(target) in posts[0].data['content']
        assert '4' in posts[0].data['content']
        delivered = core.event_log.query_session('a', types={'agent.message_injected'})
        assert delivered
        reopened = await client.post('/api/v2/projects/p/workbench/open', json={'path': str(target)})
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()['geometry']['atoms'][1]['x'] == pytest.approx(1.4)
        products = (await client.get('/api/v2/projects/p/workbench/products')).json()['products']
        assert any(item.get('path') == str(target) and not item['associations'] for item in products)
    await core.aclose()


@pytest.mark.asyncio
async def test_multiframe_csv_and_preview_share_real_geometry(tmp_path):
    core, root = _core(tmp_path)
    (root / 'opt.xyz').write_text('2\nfirst\nC 0 0 0\nO 1.5 0 0\n2\nsecond\nC 0 0 0\nO 1.3 0 0\n')
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        body = (await client.post('/api/v2/projects/p/workbench/open', json={'path': 'opt.xyz'})).json()
        assert body['selected_frame'] == 1
        assert body['geometry']['atoms'][1]['x'] == pytest.approx(1.3)
        document = body['document_id']
        first = await client.get(f'/api/v2/projects/p/workbench/documents/{document}/frames/0')
        assert first.json()['atoms'][1]['x'] == pytest.approx(1.5)
        csv = await client.get(f'/api/v2/projects/p/workbench/documents/{document}/csv')
        assert csv.status_code == 200 and 'text/csv' in csv.headers['content-type']
        assert len(csv.text.splitlines()) == 3
        preview = (await client.post('/api/v2/projects/p/workbench/preview', json={'path': 'opt.xyz'})).json()
        assert preview['xyz'] == body['geometry']['xyz']
    await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,native_freeze', [('gaussian', 'B 1 2 1.300000 F'), ('orca', '{ B 0 1 1.300000 C }')])
async def test_save_native_input_uses_confirmed_freeze_and_keeps_original(tmp_path, engine, native_freeze):
    core, root = _core(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/workbench/save', json={
            'molecule': _molecule(), 'settings': {'engine': engine, 'method': 'HF', 'basis_set': 'STO-3G', 'charge': 0, 'multiplicity': 1},
            'frozen_coordinates': [{'coord_type': 'bond', 'atoms': [1, 2], 'value': 1.3}], 'generate_input': True,
        })
        assert response.status_code == 200, response.text
        saved = response.json()
        assert native_freeze in Path(saved['files']['input']).read_text()
        assert saved['geometry']['atoms'][1]['x'] == pytest.approx(1.4)
    await core.aclose()


@pytest.mark.asyncio
async def test_shared_fragment_history_prefers_current_project(tmp_path):
    core, root = _core(tmp_path)
    core.projects['q'] = Project(id='q', name='Other', workspace_dir=str(root.parent / 'other'))
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        for _ in range(2):
            assert (await client.post('/api/v2/projects/q/workbench/fragments', json={'smiles': '[*]Cl'})).status_code == 200
        assert (await client.post('/api/v2/projects/p/workbench/fragments', json={'smiles': '[*]F'})).status_code == 200
        entries = (await client.get('/api/v2/projects/p/workbench/fragments')).json()['fragments']
        assert entries[0]['project_use_count'] == 1
        assert entries[0]['use_count'] == 1
        assert entries[1]['project_use_count'] == 0 and entries[1]['use_count'] == 2
    await core.aclose()


@pytest.mark.asyncio
async def test_marked_fragment_preview_uses_fragment_builder_without_recording_history(tmp_path):
    core, _root = _core(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/workbench/fragments/preview', json={'smiles': '[*]F'})
        assert response.status_code == 200, response.text
        assert response.json()['atoms'][0]['symbol'] == 'F'
        assert not (await client.get('/api/v2/projects/p/workbench/fragments')).json()['fragments']
    await core.aclose()


@pytest.mark.asyncio
async def test_edit_is_same_backend_geometry_operation_and_keeps_source_state(tmp_path):
    core, _root = _core(tmp_path)
    original = _molecule()
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/workbench/edit', json={
            'molecule': original, 'action': 'coordinate', 'atoms': [1, 2], 'value': 1.8,
        })
        assert response.status_code == 200, response.text
        assert response.json()['atoms'][0]['x'] == pytest.approx(0)
        assert response.json()['atoms'][1]['x'] == pytest.approx(1.8)
        switched = await client.post('/api/v2/projects/p/workbench/edit', json={
            'molecule': original, 'action': 'coordinate', 'atoms': [1, 2], 'value': 1.8, 'fixed_side': 'last',
        })
        assert switched.json()['atoms'][1]['x'] == pytest.approx(1.4)
        assert switched.json()['atoms'][0]['x'] == pytest.approx(-.4)
    await core.aclose()


@pytest.mark.asyncio
async def test_generate_requires_explicit_scientific_inputs(tmp_path):
    core, root = _core(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/workbench/save', json={
            'title': 'Missing method', 'molecule': _molecule(), 'settings': {'engine': 'orca'},
            'generate_input': True,
        })
        assert response.status_code == 400, response.text
        assert 'method' in response.text
        assert not list((root / '.cloudra' / 'structures').glob('*/structure.json'))
    await core.aclose()
