"""Serializable constrained RFO steps, independent of execution and job queues.

Cartesian RFO/KKT adaptation, not autodE's DIC implementation. Source numerical
parameters and adaptations are recorded in docs/licenses/autode-derived-code.md.
Scientific geometry qualification remains the caller's separate gate.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import ConfigDict, Field, StrictInt, model_validator

from cloudra.tools.core.conformer_catalog import CatalogModel, content_digest
from cloudra.tools.core.constrained_coordinates import (
    CoordinateError,
    active_constraints,
    movable_basis,
    retract_active_distances,
    validate_constraints,
)
from cloudra.tools.core.constrained_hessian import rfo_step, update_hessian
from cloudra.tools.core.geometry_inputs import DistanceWindowInput

BOHR_ANGSTROM = 0.529177210903
SOURCE = 'autodE/e7e71b33d8659fe921c16f877f9c1adddc4f9cff:RFOptimiser/CRFOptimiser/ConvergenceParams'


class OptimizationRequest(CatalogModel):
    symbols: list[str] = Field(min_length=1)
    positions: list[list[float]]
    frozen_atoms: list[StrictInt] = Field(default_factory=list)
    distance_constraints: list[DistanceWindowInput] = Field(default_factory=list)
    method_fingerprint: Literal['GFN2-xTB'] = 'GFN2-xTB'

    @model_validator(mode='after')
    def consistent(self):
        count = len(self.symbols)
        if len(self.positions) != count or any(len(row) != 3 for row in self.positions):
            raise ValueError('complete Cartesian coordinates required')
        if len(set(self.frozen_atoms)) != len(self.frozen_atoms) or any(type(i) is not int or not 0 <= i < count for i in self.frozen_atoms):
            raise ValueError('invalid frozen atom indices')
        pairs = [tuple(sorted(item.atoms)) for item in self.distance_constraints]
        if len(set(pairs)) != len(pairs):
            raise ValueError('duplicate distance constraints')
        if any(max(pair) >= count for pair in pairs):
            raise ValueError('distance constraint atoms outside geometry')
        return self


class OptimizationEvaluation(CatalogModel):
    input_hash: str
    method_fingerprint: str
    energy_hartree: float
    gradient_hartree_per_angstrom: list[list[float]]
    hessian_hartree_per_angstrom2: list[list[float]] | None = None
    artifact_refs: list[str] = Field(min_length=1)


class OptimizationState(CatalogModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=False, validate_assignment=True)
    request: OptimizationRequest
    positions: list[list[float]]
    status: Literal['need_hessian', 'need_gradient', 'converged', 'blocked'] = 'need_hessian'
    iteration: int = 0
    trust_radius_angstrom: float = 0.1
    hessian: list[list[float]] | None = None
    previous_positions: list[list[float]] | None = None
    previous_gradient: list[list[float]] | None = None
    previous_energy_hartree: float | None = None
    predicted_energy_change: float | None = None
    energy_hartree: float | None = None
    gradient_hartree_per_angstrom: list[list[float]] | None = None
    active_constraint_labels: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    hessian_update: str = ''
    error: str = ''
    numerical_source: str = SOURCE
    coordinate_backend: Literal['cartesian_rfo_kkt'] = 'cartesian_rfo_kkt'


def initialize_constrained_state(request):
    request = OptimizationRequest.model_validate(request)
    return OptimizationState(request=request, positions=request.positions).model_dump(mode='json')


def _converged(gradient, step, energy_change):
    values = np.array([abs(energy_change), np.sqrt(np.mean(gradient ** 2)) if len(gradient) else 0,
        np.max(np.abs(gradient)) if len(gradient) else 0,
        np.sqrt(np.mean(step ** 2)), np.max(np.abs(step))])
    limits = np.array([5e-6, 1e-4 / BOHR_ANGSTROM, 3e-4 / BOHR_ANGSTROM,
                       2e-3 * BOHR_ANGSTROM, 4e-3 * BOHR_ANGSTROM])
    # These alternatives are the reference normal preset's overachievement rules.
    return any(np.all(values <= limits * factors) for factors in (
        [1, 1, 1, 1, 1], [0.5, 0.5, 0.8, 3, 3],
        [1.5, 0.1, 0.2, 2, 2], [3, 0.7, 0.7, 1, 1],
    ))


def step_constrained_state(state, evaluation):
    current = OptimizationState.model_validate(state).model_copy(deep=True)
    if current.status in ('converged', 'blocked'):
        return current.model_dump(mode='json')
    result = OptimizationEvaluation.model_validate(evaluation)
    if result.input_hash != content_digest(current.positions):
        raise ValueError('evaluation input hash mismatch')
    if result.method_fingerprint != current.request.method_fingerprint:
        raise ValueError('evaluation method mismatch')
    dimensions = 3 * len(current.positions)
    gradient = np.asarray(result.gradient_hartree_per_angstrom, dtype=float)
    if gradient.shape != (len(current.positions), 3):
        raise ValueError('evaluation gradient dimensions mismatch')
    points = np.asarray(current.positions, dtype=float)
    try:
        basis = movable_basis(points, current.request.frozen_atoms)
        reduced_gradient = basis.T @ gradient.reshape(-1)
        if current.hessian is None:
            if result.hessian_hartree_per_angstrom2 is None:
                raise ValueError('initial same-method Hessian required')
            hessian = np.asarray(result.hessian_hartree_per_angstrom2, dtype=float)
            if hessian.shape != (dimensions, dimensions) or not np.allclose(hessian, hessian.T):
                raise ValueError('evaluation Hessian dimensions/symmetry mismatch')
        else:
            hessian = np.asarray(current.hessian)
        displacement = np.zeros(dimensions)
        energy_change = float('inf')
        if current.previous_positions is not None:
            displacement = (points - np.asarray(current.previous_positions)).reshape(-1)
            energy_change = result.energy_hartree - current.previous_energy_hartree
            predicted = current.predicted_energy_change
            if predicted is not None and abs(predicted) > np.finfo(float).eps:
                ratio = energy_change / predicted
                if ratio < 0.25 or ratio > 1.75:
                    current.trust_radius_angstrom = max(0.7 * current.trust_radius_angstrom, 0.01)
                elif 0.75 < ratio < 1.25 and abs(np.linalg.norm(displacement) - current.trust_radius_angstrom) / current.trust_radius_angstrom < 0.05:
                    current.trust_radius_angstrom = min(1.3 * current.trust_radius_angstrom, 0.2)
            hessian, current.hessian_update = update_hessian(hessian, displacement,
                gradient - np.asarray(current.previous_gradient))
        reduced_hessian = basis.T @ hessian @ basis
        unconstrained = basis @ rfo_step(reduced_hessian, reduced_gradient)
        jacobian, residual, labels = active_constraints(current.request, points, unconstrained)
        projected_jacobian = jacobian @ basis
        if len(jacobian) and np.linalg.matrix_rank(projected_jacobian, tol=1e-10) < len(jacobian):
            raise CoordinateError('singular or frozen-incompatible active constraints')
        from cloudra.tools.core.constrained_coordinates import null_space
        tangent = null_space(projected_jacobian, basis.shape[1]) if basis.shape[1] else np.zeros((0, 0))
        projected_gradient = basis @ tangent @ tangent.T @ reduced_gradient
        current.energy_hartree = result.energy_hartree
        current.gradient_hartree_per_angstrom = result.gradient_hartree_per_angstrom
        current.hessian = hessian.tolist()
        current.artifact_refs = list(dict.fromkeys([*current.artifact_refs, *result.artifact_refs]))
        current.active_constraint_labels = labels
        if validate_constraints(current.request, points) and current.previous_positions is not None and _converged(projected_gradient, displacement, energy_change):
            current.status = 'converged'
            return current.model_dump(mode='json')
        move = basis @ rfo_step(reduced_hessian, reduced_gradient, projected_jacobian, residual)
        length = np.linalg.norm(move)
        if length > current.trust_radius_angstrom:
            move *= current.trust_radius_angstrom / length
        maximum = np.max(np.linalg.norm(move.reshape((-1, 3)), axis=1))
        if maximum > 0.12:
            move *= 0.12 / maximum
        for _ in range(50):  # Inner back-transform, never an optimization run cap.
            next_points = retract_active_distances(current.request, points,
                points + move.reshape((-1, 3)), move, labels)
            actual_move = (next_points - points).reshape(-1)
            maximum = np.max(np.linalg.norm(actual_move.reshape((-1, 3)), axis=1))
            if maximum <= 0.12 + 1e-10:
                move = actual_move
                break
            move *= 0.12 / maximum
        else:
            raise CoordinateError('back-transform exceeded maximum atomic move')
        current.previous_positions = current.positions
        current.previous_gradient = result.gradient_hartree_per_angstrom
        current.previous_energy_hartree = result.energy_hartree
        current.predicted_energy_change = float(gradient.reshape(-1) @ move + 0.5 * move @ hessian @ move)
        current.positions = next_points.tolist()
        current.iteration += 1
        current.status = 'need_gradient'
    except (np.linalg.LinAlgError, CoordinateError, FloatingPointError) as exc:
        current.status = 'blocked'
        current.error = str(exc)
    return current.model_dump(mode='json')
