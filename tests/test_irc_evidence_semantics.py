"""Regression tests for strict IRC evidence semantics."""

from __future__ import annotations

import numpy as np

from cloudra.dag.fact_adapters import ts_guess_facts
from cloudra.dag.models import GraphRef
from cloudra.tools.core.irc_path import prove_irc_endpoint_direction


def _ref() -> GraphRef:
    return GraphRef(ref_type="tool_result", ref_id="call_irc")


def test_direction_proof_accepts_existing_reference_geometry_without_provenance():
    symbols = ["C", "N", "H"]
    ts = [[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 1.0]]
    endpoint_a = [[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 0.7]]
    endpoint_b = [[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 1.3]]
    reference_a = [[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 0.1]]
    reference_b = [[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 1.9]]

    result = prove_irc_endpoint_direction(
        symbols,
        ts,
        (symbols, endpoint_a),
        (symbols, endpoint_b),
        (symbols, reference_a),
        (symbols, reference_b),
        [[1, 3], [2, 3]],
    )

    assert result["is_decidable"] is True
    assert result["is_match"] is True


def test_direction_proof_rejects_close_but_wrong_direction_geometry():
    """Distance similarity alone must not act as endpoint optimization evidence."""
    symbols = ["C", "N", "H"]
    ts = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 1.0]])
    endpoint_a = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 0.8]])
    endpoint_b = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 1.2]])
    reference_a = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 1.3]])
    reference_b = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 0.0, 1.7]])

    result = prove_irc_endpoint_direction(
        symbols,
        ts,
        (symbols, endpoint_a),
        (symbols, endpoint_b),
        (symbols, reference_a),
        (symbols, reference_b),
        [[1, 3], [2, 3]],
    )

    assert result["is_decidable"] is True
    assert result["is_match"] is False


def test_strict_non_pass_with_endpoint_files_is_not_path_support():
    payload = {
        "arguments": {"strict": True, "irc_log": "irc.log"},
        "result": {
            "is_success": True,
            "verdict": "fail: path direction is inconsistent",
            "irc_end_a_path": "end_a.xyz",
            "irc_end_b_path": "end_b.xyz",
            "n_imag": 1,
        },
    }

    facts = ts_guess_facts(payload, _ref())

    assert not any(f.check == "path" and f.outcome == "supports" for f in facts)
    assert any(f.check == "path" and f.outcome == "inconclusive" for f in facts)


def _symmetric_saddle():
    symbols = ["C", "Cl", "Cl", "H", "H", "H"]
    positions = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 2.0],
        [0.0, 0.0, -2.0],
        [1.0, 0.0, 0.0],
        [-0.5, np.sqrt(3) / 2, 0.0],
        [-0.5, -np.sqrt(3) / 2, 0.0],
    ])
    return symbols, positions


def test_same_geometry_accepts_reordered_symmetric_atoms():
    from cloudra.tools.core.irc_path import same_geometry

    symbols, positions = _symmetric_saddle()
    reordered = positions[[0, 1, 2, 3, 5, 4]]

    assert same_geometry((symbols, positions), (symbols, reordered))


def test_same_geometry_accepts_rotated_reordered_symmetric_atoms():
    from cloudra.tools.core.irc_path import same_geometry

    symbols, positions = _symmetric_saddle()
    rotation, _ = np.linalg.qr(np.array([[1.0, 2.0, 3.0], [-2.0, 1.0, 4.0], [3.0, -1.0, 2.0]]))
    assert np.linalg.det(rotation) > 0
    reordered = positions[[0, 1, 2, 3, 5, 4]] @ rotation + [3.0, -2.0, 1.0]

    assert same_geometry((symbols, positions), (symbols, reordered))


def test_same_geometry_preserves_xyz_rounding_bound_with_reordered_symmetry():
    from cloudra.tools.core.irc_path import same_geometry

    symbols, positions = _symmetric_saddle()
    reordered = positions[[0, 1, 2, 3, 5, 4]].copy()
    reordered[0, 0] += 0.5e-6

    assert same_geometry((symbols, positions), (symbols, reordered))
    reordered[0, 0] += 1e-5
    assert not same_geometry((symbols, positions), (symbols, reordered))


def test_same_geometry_rejects_reflection_even_with_identical_distances():
    from cloudra.tools.core.irc_path import same_geometry

    symbols = ["C", "H", "F", "Cl", "Br"]
    positions = np.array([[0, 0, 0], [1, 1, 1], [-1, -1, 1], [-1, 1, -1], [1, -1, -1]])
    reflected = positions * [-1, 1, 1]

    assert not same_geometry((symbols, positions), (symbols, reflected))


def test_short_irc_accepts_symmetric_reordered_starting_saddle(monkeypatch):
    """Mock parser boundaries only; the starting-anchor and interval gates are real."""
    from cloudra.tools.core import irc_evidence

    symbols, ts = _symmetric_saddle()
    reactant = ts.copy()
    reactant[1, 2], reactant[2, 2] = 1.5, -3.0
    product = ts.copy()
    product[1, 2], product[2, 2] = 3.0, -1.5
    logs = {
        "ts": (1, (symbols, ts)),
        "reactant": (0, (symbols, reactant)),
        "product": (0, (symbols, product)),
    }
    monkeypatch.setattr(irc_evidence, "probe_log", lambda path, **_: logs[path])
    monkeypatch.setattr(irc_evidence, "irc_endpoint_geometries", lambda *_, **__: (
        (symbols, (ts + reactant) / 2), (symbols, (ts + product) / 2),
    ))
    monkeypatch.setattr(irc_evidence, "irc_start_geometry", lambda _: (
        symbols, ts[[0, 1, 2, 3, 5, 4]],
    ))

    passed, details = irc_evidence.verify_short_irc_direction(
        "irc", ["ts"], ["product"], ["reactant"],
    )

    assert passed, details
