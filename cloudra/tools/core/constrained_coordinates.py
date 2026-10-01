"""Cartesian constraint derivatives and rigid-motion removal for RFO.

Coordinates use Angstrom. Frozen atoms are removed, not restrained. Distance
windows are inactive in their interior; equal bounds express an equality.
"""
from __future__ import annotations

import numpy as np


class CoordinateError(ValueError):
    pass


def distance_derivatives(positions, atoms):
    points = np.asarray(positions, dtype=float)
    left, right = atoms
    vector = points[left] - points[right]
    distance = float(np.linalg.norm(vector))
    if distance <= np.finfo(float).eps:
        raise CoordinateError('singular distance coordinate: coincident atoms')
    direction = vector / distance
    jacobian = np.zeros(points.size)
    jacobian[3 * left:3 * left + 3] = direction
    jacobian[3 * right:3 * right + 3] = -direction
    return distance, jacobian


def null_space(matrix, columns):
    values = np.asarray(matrix, dtype=float).reshape((-1, columns))
    if not len(values):
        return np.eye(columns)
    _, singular, vectors = np.linalg.svd(values, full_matrices=True)
    # Rank threshold follows autodE's DIC coordinate rank threshold.
    rank = int(np.sum(singular > 1e-10))
    return vectors[rank:].T


def movable_basis(positions, frozen_atoms):
    points = np.asarray(positions, dtype=float)
    dimensions = points.size
    frozen = [3 * atom + axis for atom in frozen_atoms for axis in range(3)]
    free = [index for index in range(dimensions) if index not in frozen]
    if not free:
        return np.zeros((dimensions, 0))
    rigid = np.zeros((dimensions, 6))
    centered = points - points.mean(axis=0)
    for atom, position in enumerate(centered):
        for axis in range(3):
            rigid[3 * atom:3 * atom + 3, axis] = np.eye(3)[axis]
            rigid[3 * atom:3 * atom + 3, axis + 3] = np.cross(np.eye(3)[axis], position)
    allowed_rigid = rigid @ null_space(rigid[frozen], 6)
    internal = null_space(allowed_rigid[free].T, len(free))
    basis = np.zeros((dimensions, internal.shape[1]))
    basis[free] = internal
    return basis


def constraint_residuals(request, positions):
    rows = []
    for item in request.distance_constraints:
        distance, _ = distance_derivatives(positions, item.atoms)
        rows.append(dict(atoms=list(item.atoms), distance_angstrom=distance,
            lower_residual=max(0.0, item.min_ang - distance),
            upper_residual=max(0.0, distance - item.max_ang)))
    return rows


def validate_constraints(request, positions):
    # Numerical equality tolerance from autodE's constrained primitives.
    return all(max(row['lower_residual'], row['upper_residual']) < 1e-4
               for row in constraint_residuals(request, positions))


def active_constraints(request, positions, proposed_step):
    rows, residuals, labels = [], [], []
    step = np.asarray(proposed_step).reshape(-1)
    for index, item in enumerate(request.distance_constraints):
        distance, row = distance_derivatives(positions, item.atoms)
        trial = distance + float(row @ step)
        if item.min_ang == item.max_ang:
            target = item.min_ang
            label = 'equality'
        elif distance < item.min_ang or trial < item.min_ang:
            target = item.min_ang
            label = 'lower'
        elif distance > item.max_ang or trial > item.max_ang:
            target = item.max_ang
            label = 'upper'
        else:
            continue
        rows.append(row)
        residuals.append(distance - target)
        labels.append(f'{index}:{label}')
    return np.asarray(rows).reshape((-1, len(step))), np.asarray(residuals), labels


def retract_active_distances(request, original, proposed, move, labels):
    """Newton back-transform of active primitive targets; freezes stay exact.

    The 50 inner iterations / 1e-10 residual follow the reference DIC numeric
    back-transform, and are not a total optimization limit.
    """
    if not labels:
        return proposed
    points = np.asarray(proposed, dtype=float).copy()
    fixed = [3 * atom + axis for atom in request.frozen_atoms for axis in range(3)]
    targets, constraints = [], []
    for label in labels:
        index_text, side = label.split(':')
        item = request.distance_constraints[int(index_text)]
        distance, row = distance_derivatives(original, item.atoms)
        target = distance + float(row @ move)
        if item.min_ang <= target <= item.max_ang:
            if side == 'upper' and item.min_ang != item.max_ang:
                target = min(target, np.nextafter(item.max_ang, item.min_ang))
            elif side == 'lower' and item.min_ang != item.max_ang:
                target = max(target, np.nextafter(item.min_ang, item.max_ang))
        targets.append(target)
        constraints.append(item)
    for _ in range(50):
        rows, errors = [], []
        strict = True
        for item, target in zip(constraints, targets):
            distance, row = distance_derivatives(points, item.atoms)
            row[fixed] = 0
            rows.append(row)
            errors.append(distance - target)
            if item.min_ang <= target <= item.max_ang and item.min_ang != item.max_ang:
                strict = strict and item.min_ang <= distance <= item.max_ang
        if np.sqrt(np.mean(np.square(errors))) < 1e-10 and strict:
            return points
        correction, _, rank, _ = np.linalg.lstsq(np.asarray(rows), -np.asarray(errors), rcond=1e-10)
        if rank != len(constraints):
            raise CoordinateError('singular active-distance back-transform')
        points += correction.reshape((-1, 3))
    raise CoordinateError('active-distance back-transform did not converge')
