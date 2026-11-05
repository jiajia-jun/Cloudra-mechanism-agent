from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip('rdkit')
from cloudra.persistence.fragment_library import FragmentLibrary


def test_shared_project_priority_total_frequency_and_preview(tmp_path):
    store = FragmentLibrary(tmp_path)
    assert store.list_fragments('p1') == []
    a = store.use_fragment('p1', '[*]F', 'fluoro')
    for _ in range(3):
        store.use_fragment('p2', '[*]Cl')
    assert [item['smiles'] for item in store.list_fragments('p1')] == ['*F', '*Cl']
    assert [item['smiles'] for item in store.list_fragments('p2')] == ['*Cl', '*F']
    assert store.list_fragments('p1')[0]['project_use_count'] == 1
    assert store.list_fragments('p2')[1]['project_use_count'] == 0
    assert a['geometry']['atoms'] and a['attachment_atom'] == 1
    assert a['geometry']['atoms'][0]['x'] == pytest.approx(0)
    assert FragmentLibrary(tmp_path).list_fragments('p1')[0]['use_count'] == 1
    store.delete_fragment(a['id'])
    assert len(store.list_fragments('p1')) == 1


def test_invalid_or_unmarked_fragment_never_enters_history(tmp_path):
    store = FragmentLibrary(tmp_path)
    for smiles in ('invalid(', 'CC', '*C*'):
        with pytest.raises(ValueError):
            store.use_fragment('p', smiles)
    assert store.list_fragments('p') == []


def test_concurrent_confirmed_uses_are_not_lost(tmp_path):
    store = FragmentLibrary(tmp_path)
    store.use_fragment('p', '*F')
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: FragmentLibrary(tmp_path).use_fragment('p', '*F'), range(12)))
    entry = store.list_fragments('p')[0]
    assert entry['use_count'] == 13 and entry['project_use_count'] == 13
