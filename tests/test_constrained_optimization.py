import json

import numpy as np
import pytest

from cloudra.tools.core.conformer_catalog import content_digest
from cloudra.tools.core.constrained_optimization import (
    OptimizationRequest,
    initialize_constrained_state,
    step_constrained_state,
)


def problem(*, distance=1.5, desired=1.2, bounds=None):
    request = OptimizationRequest(symbols=['H', 'H'], positions=[[0, 0, 0], [distance, 0, 0]],
        frozen_atoms=[0], distance_constraints=[] if bounds is None else [{'atoms': [0, 1], 'min_ang': bounds[0], 'max_ang': bounds[1]}])
    def evaluate(state):
        points = np.array(state['positions'])
        vector = points[1] - points[0]
        value = np.linalg.norm(vector)
        unit = vector / value
        delta = value - desired
        block = np.outer(unit, unit) + delta / value * (np.eye(3) - np.outer(unit, unit))
        hessian = np.block([[block, -block], [-block, block]])
        return dict(input_hash=content_digest(state['positions']), energy_hartree=0.5 * delta ** 2,
            gradient_hartree_per_angstrom=[(-delta * unit).tolist(), (delta * unit).tolist()],
            hessian_hartree_per_angstrom2=hessian.tolist() if state['status'] == 'need_hessian' else None,
            method_fingerprint='GFN2-xTB', artifact_refs=['synthetic analytic quadratic'])
    return initialize_constrained_state(request), evaluate


def solve(state, evaluation):
    for _ in range(100):  # fixture bound, never an optimizer run limit
        state = step_constrained_state(state, evaluation(state))
        if state['status'] in ('converged', 'blocked'):
            break
    assert state['status'] == 'converged', state
    return state


def test_known_minimum_and_frozen_cartesian_coordinates():
    state, evaluation = problem()
    final = solve(state, evaluation)
    assert final['positions'][0] == [0, 0, 0]
    assert final['positions'][1][0] == pytest.approx(1.2, abs=1e-4)
    assert 'max_iterations' not in final and 'deadline' not in final


@pytest.mark.parametrize('bounds,desired,answer', [((1, 2), 1.2, 1.2), ((1, 2), 0.8, 1), ((1, 2), 2.2, 2)])
def test_interval_has_no_midpoint_attraction_and_keeps_active_boundary(bounds, desired, answer):
    state, evaluation = problem(desired=desired, bounds=bounds)
    final = solve(state, evaluation)
    assert final['positions'][1][0] == pytest.approx(answer, abs=1e-4)


def test_outside_window_moves_toward_nearest_boundary_without_budget_limit():
    state, evaluation = problem(distance=2.5, desired=2.7, bounds=(1, 2))
    final = solve(state, evaluation)
    assert final['positions'][1][0] == pytest.approx(2, abs=1e-4)


def test_restart_serialization_gives_identical_next_step():
    state, evaluation = problem(bounds=(1, 2), desired=0.8)
    state = step_constrained_state(state, evaluation(state))
    restored = json.loads(json.dumps(state))
    assert step_constrained_state(state, evaluation(state)) == step_constrained_state(restored, evaluation(restored))


def test_wrong_point_or_method_gradient_rejected():
    state, evaluation = problem()
    data = evaluation(state)
    with pytest.raises(ValueError, match='input'):
        step_constrained_state(state, {**data, 'input_hash': 'wrong point'})
    with pytest.raises(ValueError, match='method'):
        step_constrained_state(state, {**data, 'method_fingerprint': 'other method'})


def test_duplicate_conflicting_constraint_rejected():
    with pytest.raises(ValueError, match='duplicate'):
        OptimizationRequest(symbols=['H', 'H'], positions=[[0, 0, 0], [1, 0, 0]], distance_constraints=[
            {'atoms': [0, 1], 'min_ang': 1, 'max_ang': 2}, {'atoms': [1, 0], 'min_ang': 2, 'max_ang': 3}])


def test_multidimensional_curved_boundary_converges_to_known_solution():
    anchors = [[0, 0, 0], [0, 3, 0], [0, 0, 3]]
    desired = np.array([2.0, 0.3, 0.2])
    request = OptimizationRequest(symbols=['C'] * 4, positions=[*anchors, [1.5, 0.2, 0.3]], frozen_atoms=[0, 1, 2],
        distance_constraints=[{'atoms': [0, 3], 'min_ang': 0.5, 'max_ang': 1}])
    state = initialize_constrained_state(request)
    def evaluate(state):
        point = np.array(state['positions'][-1])
        delta = point - desired
        hessian = np.zeros((12, 12))
        hessian[-3:, -3:] = np.eye(3)
        return dict(input_hash=content_digest(state['positions']), energy_hartree=float(0.5 * delta @ delta),
            gradient_hartree_per_angstrom=[[0, 0, 0]] * 3 + [delta.tolist()],
            hessian_hartree_per_angstrom2=hessian.tolist() if state['status'] == 'need_hessian' else None,
            method_fingerprint='GFN2-xTB', artifact_refs=['analytic anchored sphere problem'])
    final = solve(state, evaluate)
    assert np.linalg.norm(final['positions'][-1]) <= 1.0
    assert np.allclose(final['positions'][-1], desired / np.linalg.norm(desired), atol=5e-4)
    assert final['positions'][:3] == anchors


def test_singular_constraint_keeps_explicit_numerical_failure():
    state, evaluate = problem(distance=1.5, bounds=(1, 2))
    state['positions'][1] = [0.0, 0.0, 0.0]
    data = dict(input_hash=content_digest(state['positions']), energy_hartree=0,
        gradient_hartree_per_angstrom=[[0, 0, 0]] * 2, hessian_hartree_per_angstrom2=np.eye(6).tolist(),
        method_fingerprint='GFN2-xTB', artifact_refs=['singular fixture'])
    final = step_constrained_state(state, data)
    assert final['status'] == 'blocked' and 'singular' in final['error']
