import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.services.api_v2 import create_v2_app
from tests.test_workbench_api import _core, _molecule


@pytest.mark.asyncio
async def test_visual_instruction_freezes_displayed_frame_and_periodic_images(tmp_path):
    core, root = _core(tmp_path)
    base = '/api/v2/projects/p/workbench'
    native = '1\nLattice="4 1 0 0 3 0 0 0 12" Properties=species:S:1:pos:R:3 pbc="T T F"\nAg 1 2 3\n'
    (root / 'slab.extxyz').write_text(native)
    request = {'extxyz': native, 'source_path': 'slab.extxyz', 'source_frame': 0, 'title': 'Ag',
               'view': 'source', 'camera': [0, 0, 0, 8, 0, 0, 0, 1],
               'markers': [{'label': 'B', 'kind': 'site', 'atoms': [
                   {'index': 1}, {'index': 1, 'image': [1, 0, 0]}]}]}
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post(f'{base}/snapshots', json=request)
        assert response.status_code == 200, response.text
        shot = response.json()
        (root / 'slab.extxyz').write_text(native.replace('Ag 1 2 3', 'Ag 0 0 0'))
        assert Path(shot['structure_path']).read_text() == native
        record = json.loads(Path(shot['annotations_path']).read_text())
        assert record['pbc'] == [True, True, False]
        assert record['camera'] == request['camera']
        assert record['markers'][0]['xyz_angstrom'] == [3, 2.5, 3]
        assert record['markers'][0]['atoms'][1]['xyz_angstrom'] == [5, 3, 3]
        assert record['markers'] == shot['markers']
        opened = await client.post(f'{base}/open', json={'path': shot['structure_path']})
        assert opened.json()['geometry']['atoms'][0]['x'] == 1
        request['markers'][0]['atoms'][1]['image'] = [0, 0, 1]
        response = await client.post(f'{base}/snapshots', json=request)
        assert response.status_code == 400
        assert not (root / '.cloudra' / 'structures').exists()


@pytest.mark.asyncio
async def test_unsaved_molecular_snapshot_keeps_graph_and_usable_files(tmp_path):
    core, root = _core(tmp_path)
    base = '/api/v2/projects/p/workbench'
    request = {'title': 'unsaved', 'view': 'draft', 'molecule': _molecule(), 'camera': [0, 0, 0, 0, 0, 0, 0, 1],
               'markers': [{'label': 'A', 'kind': 'atoms', 'atoms': [{'index': 2}]}],
               'settings': {'charge': 0}, 'frozen_coordinates': [{'coord_type': 'bond', 'atoms': [1, 2], 'value': 1.4}]}
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post(f'{base}/snapshots', json=request)
        assert response.status_code == 200, response.text
        shot = response.json()
        assert shot['markers'][0]['atoms'][0]['element'] == 'O'
        response = await client.post(f'{base}/open', json={'path': shot['structure_path']})
        assert response.status_code == 200, response.text
        opened = response.json()
        assert opened['settings'] == {'charge': 0}
        assert opened['frozen_coordinates'] == request['frozen_coordinates']
        assert len(opened['geometry']['bonds']) == 1
        assert Path(shot['structure_path']).with_suffix('.mol').is_file()
        request['markers'][0]['atoms'][0]['index'] = 3
        response = await client.post(f'{base}/snapshots', json=request)
        assert response.status_code == 400
        assert not (root / '.cloudra' / 'structures').exists()


@pytest.mark.asyncio
async def test_chat_screenshot_is_downloadable_without_becoming_a_research_product(tmp_path):
    from tests.test_runtime_v2_visual_media import _PNG_BYTES

    core, _root = _core(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        response = await client.post('/api/v2/projects/p/uploads', data={'workbench': 'true'},
                                     files={'file': ('workbench.png', _PNG_BYTES, 'image/png')})
        assert response.status_code == 201, response.text
        artifact = response.json()['artifact_id']
        downloaded = await client.get(f'/api/v2/artifacts/{artifact}/download', params={'project_id': 'p'})
        assert downloaded.content == _PNG_BYTES
        products = await client.get('/api/v2/projects/p/workbench/products')
        assert products.json()['products'] == []
