"""Compute-job claim watchdog for external host agent lifecycle hooks.

Designed for Antigravity ``hooks.json`` (``Stop`` and ``PreInvocation``) and any
other host that runs a shell hook with JSON stdin/stdout.

Behavior:
- Completely silent / allow-by-default when Cloudra is not running or when there
  are no compute jobs owned by the host. Non-chemistry tasks incur zero friction.
- On ``Stop`` (only for normal ``NO_TOOL_CALL`` completion):
  - If there are unclaimed terminal compute jobs, block stop (``continue``) and
    instruct the host agent to call ``claim_compute_jobs`` and inspect outputs.
  - If there are active compute jobs and the host reports ``fullyIdle=true``
    (no background wait/timer scheduled), block stop (``continue``) so running
    calculations are not silently abandoned.
  - If ``fullyIdle=false`` and only active jobs remain, allow the host to park
    while its own background timer/trigger waits.
- On ``PreInvocation``:
  - If unclaimed terminal compute jobs exist, inject one concise ephemeral
    reminder; otherwise emit ``{}``.
"""

from __future__ import annotations

from typing import Any

import httpx

from cloudra.services.local_api_client import resolve_connection


def _format_job_brief(job: dict[str, Any]) -> str:
    parts = [
        f"job_id={job.get('job_id')}",
        f"state={job.get('state')}",
        f"project={job.get('project_id')}",
    ]
    if job.get("jobtype"):
        parts.append(f"type={job['jobtype']}")
    if job.get("log_path"):
        parts.append(f"log={job['log_path']}")
    elif job.get("path"):
        parts.append(f"path={job['path']}")
    if job.get("last_error"):
        parts.append(f"error={str(job['last_error'])[:120]}")
    return ", ".join(parts)


def fetch_watchdog_status(
    *,
    api_url: str | None = None,
    project_id: str | None = None,
    owner_id: str | None = None,
    timeout: float = 5.0,
) -> dict[str, Any] | None:
    """Query the running Cloudra service for host-owned compute jobs.

    Returns ``None`` if no Cloudra service is reachable (fail-open so ordinary
    non-Cloudra chats are never blocked).
    """
    try:
        base_url, token = resolve_connection(api_url)
    except RuntimeError:
        return None
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    params: dict[str, str] = {}
    if project_id:
        params["project_id"] = project_id
    if owner_id:
        params["owner_id"] = owner_id
    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=timeout, trust_env=False) as client:
            response = client.get("/api/v2/host/compute/watchdog", params=params)
            if not response.is_success:
                return None
            payload = response.json()
            return payload if isinstance(payload, dict) else None
    except (httpx.HTTPError, ValueError):
        return None


def evaluate_stop_hook(
    hook_input: dict[str, Any],
    *,
    status: dict[str, Any] | None,
) -> dict[str, Any]:
    """Produce an Antigravity ``Stop`` hook decision from watchdog status."""
    reason = hook_input.get("terminationReason")
    if isinstance(reason, str) and reason and reason != "NO_TOOL_CALL":
        return {"decision": "allow"}
    if not status:
        return {"decision": "allow"}

    unclaimed = status.get("unclaimed_terminal_jobs") or []
    active = status.get("active_jobs") or []

    if unclaimed:
        summary = "; ".join(_format_job_brief(job) for job in unclaimed[:5])
        extra = f" (+{len(unclaimed) - 5} more)" if len(unclaimed) > 5 else ""
        return {
            "decision": "continue",
            "reason": (
                f"Cloudra compute watchdog: {len(unclaimed)} finished compute job(s) "
                f"are waiting to be claimed ({summary}{extra}). "
                "Call `claim_compute_jobs` on the `cloudra` MCP server to claim them "
                "and process their results before finishing."
            ),
        }

    fully_idle = hook_input.get("fullyIdle", True)
    if active and fully_idle:
        summary = "; ".join(_format_job_brief(job) for job in active[:5])
        extra = f" (+{len(active) - 5} more)" if len(active) > 5 else ""
        return {
            "decision": "continue",
            "reason": (
                f"Cloudra compute watchdog: {len(active)} compute job(s) are still active "
                f"in Cloudra's detached scheduler ({summary}{extra}), and no background wait "
                "is scheduled. Schedule a periodic check/timer (or wait and claim once finished) "
                "rather than abandoning active calculations. Do not kill running compute jobs."
            ),
        }

    return {"decision": "allow"}


def evaluate_pre_invocation_hook(
    _hook_input: dict[str, Any],
    *,
    status: dict[str, Any] | None,
) -> dict[str, Any]:
    """Produce an Antigravity ``PreInvocation`` hook payload if jobs await claim."""
    if not status:
        return {}
    unclaimed = status.get("unclaimed_terminal_jobs") or []
    if not unclaimed:
        return {}
    summary = "; ".join(_format_job_brief(job) for job in unclaimed[:5])
    extra = f" (+{len(unclaimed) - 5} more)" if len(unclaimed) > 5 else ""
    return {
        "injectSteps": [
            {
                "ephemeralMessage": (
                    f"Cloudra compute watchdog: {len(unclaimed)} finished compute job(s) "
                    f"await claiming ({summary}{extra}). Call `claim_compute_jobs` on the "
                    "`cloudra` MCP server to claim and inspect them."
                )
            }
        ]
    }
