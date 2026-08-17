"""Read-only projections over the explicit tool manifest.

Downstream policy modules (DAG substantive gate, runtime profiles, evidence
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


def substantive_tools() -> frozenset[str]:
    return frozenset(name for name, reg in _named().items() if reg.dag_substantive)


def is_substantive_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    """Whether a tool call counts as substantive work for the DAG gate.

    Entries without a declaration are non-substantive, so new tools default to
    the safe "structure/read" bucket until the author opts them in.
    """
    reg = _named().get(tool_name)
    if reg is None:
        return False
    if reg.substantive_predicate:
        return bool(_load(reg.substantive_predicate)(arguments or {}))
    return reg.dag_substantive


def is_dag_observable(tool_name: str) -> bool:
    """Whether a tool call should be recorded as an observed process node."""
    reg = _named().get(tool_name)
    # Unregistered/test-injected tools are observed by default.
    return reg.dag_observe if reg is not None else True


def supervisor_evidence_tools() -> frozenset[str]:
    return frozenset(name for name, reg in _named().items() if reg.supervisor_evidence)


def is_dag_reviewed(tool_name: str) -> bool:
    """Whether a finished call enters the CallReview inbox (D5 throttle)."""
    reg = _named().get(tool_name)
    return bool(reg.dag_review) if reg is not None else False


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


def evidence_deriver_for(tool_name: str) -> EvidenceDeriver | None:
    reg = _named().get(tool_name)
    if reg is None or not reg.evidence_deriver:
        return None
    return _load(reg.evidence_deriver)
