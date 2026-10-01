"""RFO augmented-Hessian step and positive-definite BFGS/Null updates.

Adapted from autodE RFOptimiser and BFGSPDUpdate; source/license details in
 docs/licenses/autode-derived-code.md. No run-budget limits live here.
"""
from __future__ import annotations

import numpy as np


def update_hessian(hessian, displacement, gradient_change):
    matrix = np.asarray(hessian, dtype=float)
    step = np.asarray(displacement, dtype=float).reshape(-1)
    change = np.asarray(gradient_change, dtype=float).reshape(-1)
    product = matrix @ step
    curvature = float(step @ change)
    predicted = float(step @ product)
    if curvature <= 0 or predicted <= 0 or np.linalg.norm(step) <= np.finfo(float).eps:
        return matrix.copy(), 'NullUpdate'
    updated = matrix + np.outer(change, change) / curvature - np.outer(product, product) / predicted
    return (updated + updated.T) / 2, 'BFGSPDUpdate'


def rfo_step(hessian, gradient, jacobian=None, residual=None):
    matrix = np.asarray(hessian, dtype=float)
    vector = np.asarray(gradient, dtype=float)
    size = len(vector)
    if not size:
        return np.zeros(0)
    constraints = np.empty((0, size)) if jacobian is None else np.asarray(jacobian).reshape((-1, size))
    count = len(constraints)
    augmented = np.zeros((size + 1, size + 1))
    augmented[:size, :size] = matrix
    augmented[-1, :size] = augmented[:size, -1] = vector
    shift = min(0.0, float(np.linalg.eigvalsh(augmented)[0]))
    shifted = matrix - shift * np.eye(size)
    if not count:
        if not np.any(vector):
            return np.zeros(size)
        return np.linalg.solve(shifted, -vector)
    system = np.block([[shifted, constraints.T], [constraints, np.zeros((count, count))]])
    right = -np.concatenate([vector, np.asarray(residual)])
    return np.linalg.solve(system, right)[:size]
