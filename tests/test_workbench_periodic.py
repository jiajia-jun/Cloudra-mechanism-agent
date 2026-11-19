"""Periodic workbench input preserves native frame geometry through the API."""

import asyncio
from io import StringIO

import pytest
import pytest_asyncio
from ase.io import read
from httpx import ASGITransport, AsyncClient

from cloudra.persistence.artifacts import ArtifactService
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Project
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.session_store import ensure_session_record

BASE = '/api/v2/projects/p/workbench'

PERIODIC_XYZ = (
    '2\nLattice="3 0 0 1 4 0 .5 .3 9" pbc="T T F" Properties=pos:R:3:species:S:1:move_mask:L:1\n'
    '0.12345678901234567 .2 .3 Si F\n1 2 3 O T\n'
    '1\nLattice="5 0 0 2 7 0 0 0 11" pbc="F F F" Properties=species:S:1:pos:R:3\n'
    'Al 4 5 6\n'
)
POSCAR = (
    'Triclinic SiO\n1.0\n3 0 0\n1 4 0\n0.5 0.3 9\nSi O\n1 1\n'
    'Selective dynamics\nDirect\n.12345678901234567 .25 .5 F T T\n.2 .3 .4 F F F\n'
)
CIF = """data_SiO
_cell_length_a 3
_cell_length_b 4
_cell_length_c 9
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Si1 Si 0.12345678901234567 0.25 0.5
O1 O 0.2 0.3 0.4
"""


@pytest_asyncio.fixture
async def client(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.projects['p'] = Project(id='p', name='Cell geometry', workspace_dir=str(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url='http://testserver') as client:
        yield client
    await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('extension', ['extxyz', 'xyz'])
async def test_periodic_xyz_open_text_frames_and_preview_keep_each_native_cell(tmp_path, client, extension):
    source = tmp_path / f'trajectory.{extension}'
    source.write_text(PERIODIC_XYZ)
    opened = await client.post(f'{BASE}/open', json={'path': source.name})
    assert opened.status_code == 200, opened.text
    document = opened.json()
    assert document['selected_frame'] == 1
    assert document['frames'] == [{'index': i, 'step': i, 'has_geometry': True} for i in range(2)]
    assert document['settings'] == {}
    assert document['geometry']['pbc'] == [False, False, False]
    assert document['geometry']['cell'] == [[5., 0., 0.], [2., 7., 0.], [0., 0., 11.]]
    assert document['geometry']['atoms'] == [{'index': 1, 'symbol': 'Al', 'x': 4., 'y': 5., 'z': 6.}]

    response = await client.get(f'{BASE}/documents/{document["document_id"]}/frames/0')
    assert response.status_code == 200, response.text
    first = response.json()
    assert first['graph_status'] == 'periodic'
    assert first['molecule'] == '' and first['bonds'] == []
    assert first['cell'] == [[3., 0., 0.], [1., 4., 0.], [.5, .3, 9.]]
    assert first['pbc'] == [True, True, False]
    assert first['atoms'] == [
        {'index': 1, 'symbol': 'Si', 'x': .12345678901234567, 'y': .2, 'z': .3},
        {'index': 2, 'symbol': 'O', 'x': 1., 'y': 2., 'z': 3.},
    ]
    assert first['xyz'].splitlines()[2].split()[0] == 'Si'
    assert first['extxyz'] == ''.join(PERIODIC_XYZ.splitlines(keepends=True)[:4])
    assert read(StringIO(first['extxyz']), format='extxyz').constraints[0].get_indices().tolist() == [0]

    preview = await client.post(f'{BASE}/preview', json={'path': source.name, 'frame_index': 0})
    assert preview.status_code == 200, preview.text
    assert preview.json()['frame_count'] == 2
    assert preview.json()['selected_frame_facts'] == document['frames'][0]
    for key in ('xyz', 'cell', 'pbc', 'atoms', 'bonds', 'graph_status'):
        assert preview.json()[key] == first[key]

    inline = await client.post(f'{BASE}/open', json={
        'input_text': PERIODIC_XYZ, 'input_format': extension.upper(), 'frame_index': 0,
    })
    assert inline.status_code == 200, inline.text
    assert inline.json()['geometry'] == first


@pytest.mark.asyncio
@pytest.mark.parametrize(('filename', 'input_format', 'text'), [
    ('POSCAR', 'poscar', POSCAR), ('CONTCAR', 'contcar', POSCAR),
    ('result.vasp', 'vasp', POSCAR), ('crystal.cif', 'cif', CIF),
], ids=['POSCAR', 'CONTCAR', 'VASP', 'CIF'])
async def test_native_periodic_products_open_with_exact_extxyz_export(tmp_path, client, filename, input_format, text):
    source = tmp_path / filename
    source.write_text(text)
    await asyncio.to_thread(ensure_session_record, ConversationDB('p'), 'user', None)
    artifact = await asyncio.to_thread(ArtifactService().register_file,
                                       conversation_id='p', session_id='user', source=source, allowed_root=tmp_path)

    listing = await client.get(f'{BASE}/products')
    assert listing.status_code == 200, listing.text
    product = next(p for p in listing.json()['products'] if p['artifact_id'] == artifact.artifact_id)
    assert product['title'] == filename and product['can_open'] is True

    for request in ({'path': filename}, {'artifact_id': artifact.artifact_id},
                    {'input_text': text, 'input_format': input_format}):
        response = await client.post(f'{BASE}/open', json=request)
        assert response.status_code == 200, response.text
        document = response.json()
        geometry = document['geometry']
        assert document['task_type'] == 'structure'
        assert document['settings'] == {}
        assert geometry['pbc'] == [True, True, True]
        assert [atom['symbol'] for atom in geometry['atoms']] == ['Si', 'O']
        assert geometry['bonds'] == [] and geometry['graph_status'] == 'periodic'
        if input_format == 'cif':
            assert geometry['cell'] == [[3., 0., 0.], [0., 4., 0.], [0., 0., 9.]]
            assert geometry['atoms'][0]['x'] == pytest.approx(.370370367037037)
            assert not geometry['warnings']
        else:
            assert geometry['cell'] == [[3., 0., 0.], [1., 4., 0.], [.5, .3, 9.]]
            assert geometry['atoms'][0]['x'] == pytest.approx(.870370367037037)
            assert geometry['warnings'] and 'native atom constraints' in geometry['warnings'][0]
        exported = read(StringIO(geometry['extxyz']), format='extxyz')
        assert exported.cell.tolist() == geometry['cell']
        assert exported.pbc.tolist() == geometry['pbc']
        assert exported.positions.tolist() == [[atom[axis] for axis in 'xyz'] for atom in geometry['atoms']]
        if input_format != 'cif':
            assert exported.constraints[0].get_indices().tolist() == [1]


@pytest.mark.asyncio
async def test_xyz_with_periodic_and_plain_frames_does_not_infer_cell_or_graph_on_plain_frame(client):
    response = await client.post(f'{BASE}/open', json={
        'input_text': PERIODIC_XYZ + '1\nmolecule\nHe 1 0 0\n',
    })
    assert response.status_code == 200, response.text
    document = response.json()
    assert document['selected_frame'] == 2
    geometry = document['geometry']
    assert geometry['graph_status'] == 'unresolved' and geometry['molecule']
    assert 'cell' not in geometry and 'pbc' not in geometry


@pytest.mark.asyncio
async def test_periodic_xyz_can_have_only_two_defined_cell_vectors(client):
    response = await client.post(f'{BASE}/open', json={
        'input_text': '1\nLattice="3 0 0 1 4 0 0 0 0" pbc="T T F"\nHe 0 0 1\n',
        'input_format': 'extxyz',
    })
    assert response.status_code == 200, response.text
    geometry = response.json()['geometry']
    assert geometry['cell'] == [[3., 0., 0.], [1., 4., 0.], [0., 0., 0.]]
    assert geometry['pbc'] == [True, True, False]


@pytest.mark.asyncio
async def test_disordered_cif_is_not_exported_as_an_ordered_structure(client):
    disordered = CIF.replace('_atom_site_fract_z\n', '_atom_site_fract_z\n_atom_site_occupancy\n')
    disordered = disordered.replace('0.25 0.5', '0.25 0.5 0.5').replace('0.3 0.4', '0.3 0.4 1.0')
    response = await client.post(f'{BASE}/open', json={'input_text': disordered, 'input_format': 'cif'})
    assert response.status_code == 400, response.text
    assert 'Partial or mixed site occupancy' in response.json()['detail']


@pytest.mark.asyncio
async def test_vasp_open_requires_symbols_in_the_requested_source(tmp_path, client):
    source = POSCAR.replace('Triclinic SiO', 'Generated').replace('Si O\n1 1', '1 1')
    (tmp_path / 'POSCAR').write_text(source)
    (tmp_path / 'POTCAR').write_text('TITEL = PAW_PBE Si\nTITEL = PAW_PBE O\n')
    response = await client.post(f'{BASE}/open', json={'path': 'POSCAR'})
    assert response.status_code == 400, response.text
    assert 'must declare its element symbols' in response.json()['detail']
