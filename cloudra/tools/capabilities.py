"""Read-only projections over the explicit tool manifest.

Downstream policy modules (DAG compute-entry gate, runtime profiles, evidence
adapter) must query these helpers instead of keeping their own per-tool name
sets.  Adding semantics to a tool only requires editing ``TOOL_REGISTRY``.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from cloudra.tools.registry import TOOL_REGISTRY, ToolRegistration

EvidenceDeriver = Callable[..., dict[str, Any]]


def _named() -> dict[str, ToolRegistration]:
    """Entries that explicitly declare their wire tool_name."""
    return {reg.tool_name: reg for reg in TOOL_REGISTRY if reg.tool_name}


def _load(path: str) -> Callable:
    module_name, sep, func_name = path.partition(":")
    if not sep or not module_name or not func_name:
        raise ValueError(f"semantic callable path must be 'module:function', got {path!r}")
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def is_dag_observable(tool_name: str) -> bool:
    """Whether a tool call should be recorded as an observed process node."""
    reg = _named().get(tool_name)
    # Unregistered/test-injected tools are observed by default.
    return reg.dag_observe if reg is not None else True


def is_dag_evidence_producer(tool_name: str) -> bool:
    """Whether a finished call yields computational evidence.

    Registry-level "evidence producer" marker; its remaining consumer is the
    knowledge stage's compute-tool trigger.  §5: it no longer routes anything
    into the CallReview inbox — review submission is always explicit.
    """
    reg = _named().get(tool_name)
    return bool(reg.dag_evidence_producer) if reg is not None else False


def is_dag_compute_entry(tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    """Whether a call launches computation / writes compute inputs.

    The Phase-3 gate blocks these until a mechanism draft is accepted (D4).
    Entries without a declaration are not gated.
    """
    reg = _named().get(tool_name)
    if reg is None:
        return False
    if reg.dag_compute_predicate:
        return bool(_load(reg.dag_compute_predicate)(arguments or {}))
    return reg.dag_compute_entry


def android_tools() -> frozenset[str]:
    """Android allow-list; runtime availability stays opt-in per tool."""
    return frozenset(
        name for name, reg in _named().items() if "android" in reg.runtime_profiles
    )


def visual_tools() -> frozenset[str]:
    """Tools gated behind the per-agent visual_mode setting."""
    return frozenset(name for name, reg in _named().items() if reg.visual)


def is_direct_only(tool_name: str) -> bool:
    """Whether a tool is a direct wire control barred from JS guest programs.

    Unregistered/test-injected tools default to guest-callable (False), which
    keeps fake business tools usable in runtime tests.
    """
    reg = _named().get(tool_name)
    return bool(reg.invocation_direct_only) if reg is not None else False


def evidence_deriver_for(tool_name: str) -> EvidenceDeriver | None:
    reg = _named().get(tool_name)
    if reg is None or not reg.evidence_deriver:
        return None
    return _load(reg.evidence_deriver)


def fact_adapter_for(tool_name: str) -> Callable | None:
    """Declared EvidenceFact adapter for a tool (contract_version=2)."""
    reg = _named().get(tool_name)
    if reg is None or not reg.dag_fact_adapter:
        return None
    return _load(reg.dag_fact_adapter)


SUPERVISOR_ACCESS_LEVELS = frozenset(
    {"none", "evidence_read", "skill_read", "hub", "review_decision"}
)


def supervisor_access_for(tool_name: str) -> str:
    """Supervisor capability of one tool; unregistered tools get "none"."""
    reg = _named().get(tool_name)
    if reg is None:
        return "none"
    access = reg.supervisor_access or "none"
    if access not in SUPERVISOR_ACCESS_LEVELS:
        raise ValueError(
            f"unknown supervisor_access {access!r} declared for tool {tool_name!r}"
        )
    return access


def supervisor_allowed_tools() -> dict[str, str]:
    """tool_name -> supervisor_access for every tool the Supervisor may call.

    This projection is the single source of truth for Supervisor tool
    discovery AND execution gating; both paths must query it.
    """
    return {
        name: reg.supervisor_access
        for name, reg in _named().items()
        if reg.supervisor_access and reg.supervisor_access != "none"
    }


def supervisor_tool_names() -> list[str]:
    """The Supervisor role's capability list (AgentCapabilities.tools).

    Business tools come exclusively from the ``supervisor_access`` registry
    projection above — never re-declared here.  ``stop`` is the run-lifecycle
    direct control every agent needs to end a turn; it is a runtime control,
    not a supervised business capability, so it stays outside the access
    levels and is named here once.  ``ask_user``/``schedule`` are deliberately
    absent: the Supervisor neither questions the user nor self-schedules —
    it is woken by mailbox notifications.
    """
    return sorted(set(supervisor_allowed_tools()) | {"stop"})
