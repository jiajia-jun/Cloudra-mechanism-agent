import numpy as np
import pytest

from cloudra.tools.core.constrained_coordinates import distance_derivatives, movable_basis
from cloudra.tools.core.constrained_hessian import update_hessian


def test_distance_jacobian_matches_finite_difference():
    points = np.array([[0.1, -0.3, 0.4], [1.1, 0.5, -0.2]])
    _, jacobian = distance_derivatives(points, [0, 1])
    for index in range(points.size):
        upper, lower = points.copy().reshape(-1), points.copy().reshape(-1)
        upper[index] += 1e-6
        lower[index] -= 1e-6
        finite = (distance_derivatives(upper.reshape((-1, 3)), [0, 1])[0] -
                  distance_derivatives(lower.reshape((-1, 3)), [0, 1])[0]) / 2e-6
        assert jacobian[index] == pytest.approx(finite, abs=1e-8)


def test_linear_dimer_has_one_internal_degree_of_freedom():
    basis = movable_basis([[0, 0, 0], [1, 0, 0]], [])
    assert basis.shape == (6, 1)
    assert np.allclose(basis.T @ basis, np.eye(1))


def test_frozen_atom_rows_are_zero():
    basis = movable_basis([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [0, 1])
    assert np.array_equal(basis[:6], np.zeros_like(basis[:6]))


def test_bfgs_update_satisfies_secant_condition_and_null_update_preserves_hessian():
    hessian = np.eye(3)
    step = np.array([0.1, 0.2, 0.3])
    change = np.diag([1, 2, 3]) @ step
    updated, method = update_hessian(hessian, step, change)
    assert method == 'BFGSPDUpdate'
    assert np.allclose(updated @ step, change)
    assert np.linalg.eigvalsh(updated).min() > 0
    unchanged, method = update_hessian(hessian, step, -change)
    assert method == 'NullUpdate' and np.array_equal(unchanged, hessian)
