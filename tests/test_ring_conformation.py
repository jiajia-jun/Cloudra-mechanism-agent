import numpy as np
import pytest


def ring(z):
    angles = np.arange(6) * np.pi / 3
    return np.column_stack((np.cos(angles), np.sin(angles), z))


@pytest.mark.parametrize('family,z', [
    ('chair', [0.2,-0.2,0.2,-0.2,0.2,-0.2]),
    ('envelope', [0.2,0,0,0,0,0]),
    ('half_chair', [0.2,-0.2,0,0,0,0]),
    ('boat', 0.2*np.cos(2*np.arange(6)*np.pi/3)),
    ('twist_boat', 0.2*np.cos(2*np.arange(6)*np.pi/3+np.pi/6)),
])
def test_ring_shape_from_geometry_is_rigid_and_numbering_invariant(family, z):
    from cloudra.tools.core.ring_conformation import describe_ring_shape
    pos = ring(z)
    for ids in [list(range(6)), [2,3,4,5,0,1], [5,4,3,2,1,0]]:
        shape = describe_ring_shape(pos, ids, ring_kind='covalent_ring')
        assert shape['nearest_family'] == family
        rotated = pos @ np.array([[0,1,0],[0,0,1],[1,0,0]]) + [12,3,-7]
        assert describe_ring_shape(rotated, ids, ring_kind='covalent_ring')['nearest_family'] == family


def test_planar_and_unsupported_rings_do_not_get_false_chair_labels():
    from cloudra.tools.core.ring_conformation import describe_ring_shape
    assert describe_ring_shape(ring(np.zeros(6)), list(range(6)), ring_kind='prospective_ring')['status'] == 'indeterminate'
    assert describe_ring_shape(ring(np.zeros(6)), list(range(5)), ring_kind='covalent_ring')['status'] == 'unsupported'
