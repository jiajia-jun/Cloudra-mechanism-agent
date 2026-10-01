"""Read xTB Turbomole derivative artifacts, retaining original units.

Format references: xtb-docs gradient/Hessian runtype documentation and the
fixed autodE XTB wrapper reference. Nothing here starts a calculation.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from cloudra.tools.core.constrained_optimization import BOHR_ANGSTROM


def _number(token):
    value = float(token.replace('D', 'E').replace('d', 'e'))
    if not math.isfinite(value):
        raise ValueError('nonfinite derivative value')
    return value


def read_gradient(path, symbols, positions=None):
    lines = [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]
    if not lines or lines[0] != '$grad':
        raise ValueError('incomplete Turbomole gradient block')
    body = lines[1:-1] if lines[-1] == '$end' else lines[1:]
    coordinates, coordinate_values, gradient = [], [], []
    for line in body:
        tokens = line.split()
        if tokens[0].lower() == 'cycle':
            continue
        if len(tokens) == 4:
            if gradient:
                raise ValueError('gradient coordinates out of order')
            coordinates.append(tokens[-1].capitalize())
            coordinate_values.append([_number(token) for token in tokens[:3]])
        elif len(tokens) == 3:
            gradient.append([_number(token) for token in tokens])
        else:
            raise ValueError('invalid Turbomole gradient row')
    if coordinates != symbols or len(gradient) != len(symbols):
        raise ValueError('gradient atom identity/count mismatch')
    if positions is not None and not np.allclose(np.asarray(coordinate_values)*BOHR_ANGSTROM, positions, rtol=1e-12, atol=1e-12):
        raise ValueError('gradient geometry does not match submitted input')
    raw = np.asarray(gradient)
    return dict(raw_gradient_unit='Ha/Bohr', raw_gradient=raw.tolist(),
                gradient_hartree_per_angstrom=(raw / BOHR_ANGSTROM).tolist())


def read_hessian(path, count):
    lines = [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]
    if not lines or lines[0] != '$hessian':
        raise ValueError('incomplete Turbomole Hessian block')
    body = lines[1:-1] if lines[-1] == '$end' else lines[1:]
    values = [_number(token) for line in body for token in line.split()]
    dimension = 3 * count
    if len(values) != dimension ** 2:
        raise ValueError('Hessian matrix dimensions mismatch')
    raw = np.asarray(values).reshape((dimension, dimension))
    if not np.allclose(raw, raw.T):
        raise ValueError('Hessian matrix is not symmetric')
    return dict(raw_hessian_unit='Ha/Bohr^2', raw_hessian=raw.tolist(),
                hessian_hartree_per_angstrom2=(raw / BOHR_ANGSTROM ** 2).tolist())
