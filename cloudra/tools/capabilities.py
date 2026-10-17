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


def config_disabled_tools() -> frozenset[str]:
    """Tools whose declared config gate (``config_gate``) is currently false.

    The wire projection hides them; the tool's own call path hard-fails as
    the second line of defense.  Gate resolution is the registry entry's
    ``"<section>.<field>"`` dot-path evaluated against ``get_config()``.
    """
    if not any(reg.config_gate for reg in TOOL_REGISTRY):
        return frozenset()
    from cloudra.infra.config import get_config, resolve_config_attr
    cfg = get_config()
    disabled = set()
    for name, reg in _named().items():
        if not reg.config_gate:
            continue
        target, final_key = resolve_config_attr(cfg, reg.config_gate)
        if target is None:
            # Gate references a non-existent config path: fail closed.
            disabled.add(name)
        elif not bool(getattr(target, final_key)):
            disabled.add(name)
    return frozenset(disabled)


def visual_tools() -> frozenset[str]:
    """Tools gated behind the per-agent visual_mode setting."""
    return frozenset(name for name, reg in _named().items() if reg.visual)


def role_hidden_tools(role_id: str | None) -> frozenset[str]:
    """Tools whose declared ``role_allowlist`` excludes the given role.

    The wire projection hides them from that role's agent and PermissionStage
    hard-fails the call (the config_gate two-line pattern).  An empty
    allowlist means every role may use the tool; a None/unknown role_id is
    treated literally (absent from every non-empty allowlist).
    """
    if not any(reg.role_allowlist for reg in TOOL_REGISTRY):
        return frozenset()
    return frozenset(
        name
        for name, reg in _named().items()
        if reg.role_allowlist and role_id not in reg.role_allowlist
    )


def dag_tools() -> frozenset[str]:
    """DAG orchestration tools (the dag_tools package).

    Meaningful only when the agent's orchestration_mode is not standard; the
    wire projection hides them otherwise (they hard-fail at call time anyway).
    """
    return frozenset(
        name
        for name, reg in _named().items()
        if reg.module.startswith("cloudra.tools.Plantool.dag_tools.")
    )


def dag_review_decision_tools() -> frozenset[str]:
    """Supervisor verdict tools (supervisor_access="review_decision").

    Usable only in dag_guided — in dag_record the Supervisor is offline and
    these tools reject every call, so the wire projection hides them there.
    """
    return frozenset(
        name
        for name, reg in _named().items()
        if reg.supervisor_access == "review_decision"
    )


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
    {"none", "evidence_read", "skill_read", "hub", "review_decision", "process_write"}
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
