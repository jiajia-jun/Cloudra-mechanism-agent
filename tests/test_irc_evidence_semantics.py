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
