"""Deterministic scientific requirements for contract_version=2 claims.

This module decides what a ClaimSpec needs and whether a set of typed
EvidenceFacts satisfies it.  It is intentionally separate from the delivery
stage bookkeeping: stage binds record "which result was attached where",
while requirements evaluate "does the collected evidence support the claimed
scientific statement".

Core helpers:
- ``identity_result`` keeps species identity and concrete-atom mapping as two
  independent checks.  A symmetric molecule can have an inconclusive atom
  mapping without refuting the species identity.
- ``evaluate_claim`` aggregates supports/refutes/inconclusive facts for a
  ClaimSpec.  Missing positive evidence and unresolved contradictions both
  leave the claim ``unresolved``; a claim with no required checks is
  ``out_of_scope`` rather than being promoted to supported.
"""

from __future__ import annotations

from typing import Any, Literal

from cloudra.dag.evidence_facts import EvidenceFact
from cloudra.dag.models import ClaimSpec

Outcome = Literal["supports", "refutes", "inconclusive", "not_required"]
ScientificStatus = Literal["supported", "unresolved", "out_of_scope"]


def _identity_outcome(identity: str) -> Outcome:
    if identity == "match":
        return "supports"
    if identity == "mismatch":
        return "refutes"
    # not_provided / inconclusive / any unexpected legacy string are not proof.
    return "inconclusive"


def identity_result(
    identity: str,
    binding: str,
    *,
    needs_mapping: bool,
) -> dict[str, str]:
    """Evaluate one endpoint's identity and mapping checks independently.

    identity values used by reaction_mapping:
      match, mismatch, inconclusive, not_provided
    binding values used by reaction_mapping:
      complete, inconclusive, not_requested

    A concrete atom mapping is only required when the claim has to reason
    about explicit atom correspondence (bond changes, stereochemistry,
    isotope fate).  Symmetry may make mapping inconclusive while the species
    identity still supports the endpoint claim.
    """
    identity_check = _identity_outcome(identity)
    if not needs_mapping:
        mapping_check: Outcome = "not_required"
    elif binding == "complete":
        mapping_check = "supports"
    elif binding in ("inconclusive", "not_requested", ""):
        mapping_check = "inconclusive"
    else:
        # Defensive: an unknown binding string must not be treated as support.
        mapping_check = "inconclusive"
    return {
        "identity_check": identity_check,
        "mapping_check": mapping_check,
    }


def _check_requirement_met(facts: list[EvidenceFact], check: str) -> bool:
    """A required check is satisfied only by an explicit supports fact.

    Unknown / inconclusive / not_provided never count as support.  Refutes
    are handled separately as contradictions and do not satisfy a check.
    """
    return any(fact.check == check and fact.outcome == "supports" for fact in facts)


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


# Minimal deterministic requirement templates for common ClaimSpec kinds.
# These are advisory defaults; an accepted claim's required_checks remain the
# authoritative scope.  They exist so future Supervisor/review code can show
# a stable gap set without inventing check names at runtime.
_REQUIREMENT_TEMPLATES: dict[str, set[str]] = {
    "mechanism": {"stationary_point", "curvature", "path", "identity"},
    "electronic_barrier": {"stationary_point", "curvature", "energy", "identity"},
    "free_energy_barrier": {
        "stationary_point",
        "curvature",
        "energy",
        "thermochemistry",
        "identity",
    },
    "selectivity": {"stationary_point", "curvature", "energy", "identity"},
    "property": {"stationary_point", "identity"},
}


def template_for_claim(claim: ClaimSpec) -> set[str]:
    """Return the default requirement set for a claim kind.

    The accepted ClaimSpec's own required_checks override/augment this set;
    the template is only used to help users see what kind typically implies.
    """
    return set(_REQUIREMENT_TEMPLATES.get(claim.kind.value, set()))
