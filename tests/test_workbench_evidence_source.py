"""Canonical DAG evidence opens the recorded immutable file, never an ID pathname."""

import hashlib

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.dag.evidence_ingest import FileEvidenceSnapshot
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Project
from cloudra.services.api_v2 import create_v2_app


@pytest.fixture
def evidence_source(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    original = root / 'geometry.xyz'
    original.write_text('2\nrecorded\nH 0 0 0\nH 0 0 0.74\n')
    snapshot = tmp_path / 'archive' / 'geometry.xyz'
    snapshot.parent.mkdir()
    snapshot.write_bytes(original.read_bytes())
    store = DagStore(ConversationDB('p').init())
    evidence = FileEvidenceSnapshot(original_path=str(original), snapshot_path=str(snapshot),
                                    sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(), file_size=snapshot.stat().st_size)
    ref = store.register_evidence('user', original.name, evidence.model_dump(mode='json'), source_type='file')
    core = RuntimeCore(strict_events=True)
    core.projects['p'] = Project(id='p', name='Evidence', workspace_dir=str(root))
    core.projects['other'] = Project(id='other', name='Other', workspace_dir=str(tmp_path / 'other'))
    return core, original, snapshot, ref.model_dump(mode='json')


@pytest.mark.asyncio
async def test_open_file_evidence_uses_immutable_snapshot_even_outside_workspace(evidence_source):
    core, original, _snapshot, ref = evidence_source
    original.write_text('1\nchanged\nHe 0 0 0\n')
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/workbench/open', json={'file_evidence': ref})
        assert response.status_code == 200, response.text
        result = response.json()
        assert [atom['symbol'] for atom in result['geometry']['atoms']] == ['H', 'H']
        preview = await client.post('/api/v2/projects/p/workbench/preview', json={'file_evidence': ref})
        assert preview.status_code == 200, preview.text
        assert [atom['symbol'] for atom in preview.json()['atoms']] == ['H', 'H']
    await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['wrong_hash', 'missing', 'changed', 'other_project'])
async def test_open_file_evidence_rejects_invalid_or_foreign_snapshots(evidence_source, failure):
    core, _original, snapshot, ref = evidence_source
    project = 'p'
    if failure == 'wrong_hash':
        ref['content_hash'] = 'sha256:wrong'
    elif failure == 'missing':
        snapshot.unlink()
    elif failure == 'changed':
        snapshot.write_text('1\ntampered\nHe 0 0 0\n')
    else:
        project = 'other'
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post(f'/api/v2/projects/{project}/workbench/open', json={'file_evidence': ref})
        assert response.status_code in {400, 404}, response.text
    await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['open', 'preview'])
@pytest.mark.parametrize('source', ['path', 'artifact_id', 'input_text', 'smiles'])
@pytest.mark.parametrize('value', ['', ' \t\n', 'another-source'])
async def test_file_evidence_rejects_additional_string_sources_even_when_blank(evidence_source, endpoint, source, value):
    core, _original, _snapshot, ref = evidence_source
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post(f'/api/v2/projects/p/workbench/{endpoint}', json={'file_evidence': ref, source: value})
        assert response.status_code == 422, response.text
    await core.aclose()


@pytest.mark.asyncio
async def test_file_evidence_only_accepts_file_references(evidence_source):
    core, _original, _snapshot, ref = evidence_source
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/workbench/open', json={'file_evidence': {**ref, 'ref_type': 'tool_result'}})
        assert response.status_code == 422, response.text
    await core.aclose()
