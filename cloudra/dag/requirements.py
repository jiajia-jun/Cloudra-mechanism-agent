"""Deterministic scientific requirements for contract_version=2 claims.

This module decides whether a set of typed EvidenceFacts satisfies a
ClaimSpec.  It is intentionally separate from the delivery stage bookkeeping:
stage binds record "which result was attached where", while requirements
evaluate "does the collected evidence support the claimed scientific
statement".

``evaluate_claim`` aggregates supports/refutes/inconclusive facts for a
ClaimSpec.  Missing positive evidence and unresolved contradictions both
leave the claim ``unresolved``; a claim with no required checks is
``out_of_scope`` rather than being promoted to supported.
"""

from __future__ import annotations

from typing import Any, Literal

from cloudra.dag.evidence_facts import EvidenceFact
from cloudra.dag.models import ClaimSpec

ScientificStatus = Literal["supported", "unresolved", "out_of_scope"]


def evaluate_claim(
    claim: ClaimSpec,
    facts: list[EvidenceFact],
) -> dict[str, Any]:
    """Evaluate a claim against typed evidence facts.

    Returns:
    - checks: per-check summary.  Each value is one of
      supports / refutes / inconclusive / missing.
    - missing: required checks without a supports fact.
    - contradictions: refuting facts in the relevant check set.
    - scientific_status:
        * ``supported`` — every required check has at least one supports fact
          and no refuting fact is present;
        * ``unresolved`` — required evidence is missing or a contradiction
          exists;
        * ``out_of_scope`` — the claim declares no required checks, so there
          is nothing for deterministic evidence to certify.
    """
    relevant = [
        fact for fact in facts
        if fact.check in claim.required_checks or fact.check in claim.optional_checks
    ]
    if not claim.required_checks:
        return {
            "checks": {},
            "missing": [],
            "contradictions": [],
            "scientific_status": "out_of_scope",
        }

    supported = {
        fact.check for fact in relevant if fact.outcome == "supports"
    }
    contradicted = [
        fact for fact in relevant if fact.outcome == "refutes"
    ]
    inconclusive = {
        fact.check for fact in relevant if fact.outcome == "inconclusive"
    }
    missing = sorted(claim.required_checks - supported)
    checks: dict[str, str] = {}
    for check in sorted(claim.required_checks | claim.optional_checks):
        if check in supported:
            checks[check] = "supports"
        elif any(fact.check == check and fact.outcome == "refutes" for fact in contradicted):
            checks[check] = "refutes"
        elif check in inconclusive:
            checks[check] = "inconclusive"
        else:
            checks[check] = "missing"

    contradictions = [fact for fact in relevant if fact.outcome == "refutes"]
    status: ScientificStatus
    if contradictions or missing:
        status = "unresolved"
    else:
        status = "supported"
    return {
        "checks": checks,
        "missing": missing,
        "contradictions": contradictions,
        "scientific_status": status,
    }
