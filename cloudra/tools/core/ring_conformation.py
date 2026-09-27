"""Six-ring Cremer–Pople geometry descriptors; nearest family is not an acceptance gate.

Reference: Cremer & Pople, JACS 97 (1975), 1354–1358, doi:10.1021/ja00839a011.
All inputs and detailed artifact atom indices are internal (0-based).
"""
import math

import numpy as np


def _puckering(z):
    angle = np.arange(6) * 2 * np.pi / 3
    return np.array([np.dot(z, np.cos(angle)) / np.sqrt(3),
                     -np.dot(z, np.sin(angle)) / np.sqrt(3),
                     np.dot(z, (-1.) ** np.arange(6)) / np.sqrt(6)])


def describe_ring_shape(positions, ring_atoms, *, ring_kind):
    result = {"ring_atoms": list(ring_atoms), "ring_kind": ring_kind,
              "status": "unsupported", "nearest_family": None}
    if len(ring_atoms) != 6:
        return result
    result["status"] = "indeterminate"
    if len(set(ring_atoms)) != 6 or any(type(i) is not int or i < 0 or i >= len(positions) for i in ring_atoms):
        return result
    xyz = np.asarray(positions, dtype=float)[ring_atoms]
    if xyz.shape != (6, 3) or not np.isfinite(xyz).all():
        return result
    xyz = xyz - xyz.mean(axis=0)
    angles = np.arange(6) * np.pi / 3
    normal = np.cross(np.sin(angles) @ xyz, np.cos(angles) @ xyz)
    norm = np.linalg.norm(normal)
    scale = max(1., float(np.linalg.norm(xyz)))
    eps = np.finfo(float).eps * scale * 64
    if norm <= eps * scale:
        return result
    z = xyz @ (normal / norm)
    q = _puckering(z)
    amplitude = float(np.linalg.norm(q))
    result["puckering"] = {"Q_ang": amplitude}
    if amplitude <= eps:
        return result
    unit = q / amplitude
    result["puckering"].update(theta_deg=math.degrees(math.acos(float(np.clip(unit[2], -1, 1)))),
                               phi_deg=math.degrees(math.atan2(q[1], q[0])) % 360)
    # Complete symmetry families: cyclic renumbering, reversal and plane-normal sign.
    templates = {
        "chair": (-1.) ** np.arange(6),
        "boat": np.cos(2 * angles),
        "twist_boat": np.cos(2 * angles + np.pi / 6),
        "envelope": np.array([1., 0, 0, 0, 0, 0]),
        "half_chair": np.array([1., -1., 0, 0, 0, 0]),
    }
    distances = {}
    for family, template in templates.items():
        candidates = []
        for flip in (template, template[::-1]):
            for offset in range(6):
                ref = _puckering(np.roll(flip, offset))
                ref /= np.linalg.norm(ref)
                candidates.extend([float(np.linalg.norm(unit - ref)), float(np.linalg.norm(unit + ref))])
        distances[family] = min(candidates)
    ranked = sorted(distances, key=distances.get)
    result.update(status="described", nearest_family=ranked[0], reference_distances=distances,
                  second_family=ranked[1])
    return result


def describe_structure_rings(graph, positions, ring_order=()):
    """Describe covalent rings and an optional prospective cycle, without filtering."""
    rings = list(graph.GetRingInfo().AtomRings())
    result = [describe_ring_shape(positions, list(atoms), ring_kind="covalent_ring") for atoms in rings]
    if ring_order and not any(set(atoms) == set(ring_order) for atoms in rings):
        result.append(describe_ring_shape(positions, list(ring_order), ring_kind="prospective_ring"))
    return result


def ring_summaries(descriptions, *, base=1):
    return [{"ring_atoms": [i + base for i in row["ring_atoms"]], "ring_kind": row["ring_kind"],
             "shape": (row["nearest_family"] + "-like") if row["nearest_family"] else row["status"]}
            for row in descriptions]
