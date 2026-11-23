"""Host-mode bridge: let external agents use Cloudra's local tools and compute watchdog.

Unlike ``cloudra-subagent`` (which delegates full tasks to Cloudra's own
``runtime_v2`` agents), host mode lets an external agent (Antigravity, Codex,
Claude Code, etc.) act as the reasoning brain while reusing Cloudra's
authoritative chemistry/compute tools, detached job scheduler/guards, optional
DAG ledger, and compute-job claim watchdog.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from cloudra.base.session_class import Session
from cloudra.infra.tool_errors import validation_feedback
from cloudra.persistence.database import ComputeDB
from cloudra.persistence.paths import project_workspace_dir
from cloudra.services.compute_store import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    claim_terminal_job,
    list_session_compute_jobs,
)
from cloudra.tools import ToolEntry, get_tools_lst
from cloudra.tools.Chemtool.query_compute_job import _row_to_dict
from cloudra.tools.core.permission_model import Permission

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import Project

HOST_SESSION_PREFIX = "host:"
DEFAULT_HOST_OWNER = "default"
HostToolDomain = Literal["all", "qm", "md", "periodic", "dag"]

_MD_TOOLS: frozenset[str] = frozenset(
    {
        "md_box",
        "md_energy",
        "md_trajectory",
        "md_rmsd",
        "md_rmsf",
        "md_rdf",
        "md_msd",
        "pdb_inspect",
        "pdb_clean",
    }
)

_PERIODIC_TOOLS: frozenset[str] = frozenset(
    {
        "periodic_model",
        "periodic_ts",
    }
)

_COMMON_HOST_TOOLS: frozenset[str] = frozenset(
    {
        "get_tool_docs",
        "submit_compute_job",
        "query_compute_job",
        "query_compute_queue",
        "cancel_compute_job",
        "mark_compute_job_failed",
        "format_converter",
        "log_parser",
        "pymol_render",
    }
)

# General-purpose / internal runtime orchestration tools that belong to the
# host agent itself or Cloudra's internal multi-agent kernel rather than the
# chemistry/compute toolkit exposed to external hosts.
_HOST_EXCLUDED_TOOLS: frozenset[str] = frozenset(
    {
        "bash",
        "browser",
        "read",
        "write",
        "edit",
        "search",
        "stop",
        "ask_user",
        "schedule",
        "get_skill",
        "subagent_launcher",
        "subagent_swarm",
        "get_subagent_report",
        "agent_hub",
        "GoalSet",
        "TodoWrite",
        "update_memory",
        "email_reader",
        "email_sender",
    }
)

# Supervisor-only DAG review tools remain internal to Cloudra's own supervision flow.
_HOST_EXCLUDED_DAG_TOOLS: frozenset[str] = frozenset(
    {
        "dag_message_supervisor",
        "dag_review_step",
        "dag_review_species",
        "dag_accept_mechanism",
        "dag_review_call",
        "dag_review_evidence",
    }
)


def is_host_session_id(session_id: str | None) -> bool:
    return isinstance(session_id, str) and session_id.startswith(HOST_SESSION_PREFIX)


def format_host_session_id(owner_id: str | None = None) -> str:
    """Normalize an external host owner identifier into a compute session_id."""
    if owner_id is None:
        return f"{HOST_SESSION_PREFIX}{DEFAULT_HOST_OWNER}"
    cleaned = owner_id.strip()
    if cleaned.startswith(HOST_SESSION_PREFIX):
        cleaned = cleaned[len(HOST_SESSION_PREFIX):]
    if not cleaned:
        return f"{HOST_SESSION_PREFIX}{DEFAULT_HOST_OWNER}"
    if not cleaned.isascii() or not cleaned.replace("_", "").replace("-", "").replace(":", "").isalnum():
        raise ValueError("owner_id must contain only ASCII letters, digits, '_', '-', or ':'")
    return f"{HOST_SESSION_PREFIX}{cleaned}"


def _is_dag_tool(tool_name: str) -> bool:
    return tool_name.startswith("dag_")


def classify_host_tool_domain(tool_name: str) -> Literal["common", "qm", "md", "periodic", "dag"]:
    """Classify an exposed host tool into its primary technical stack."""
    if _is_dag_tool(tool_name):
        return "dag"
    if tool_name in _COMMON_HOST_TOOLS:
        return "common"
    if tool_name in _MD_TOOLS:
        return "md"
    if tool_name in _PERIODIC_TOOLS:
        return "periodic"
    return "qm"


def _host_tool_entries(
    *,
    domain: HostToolDomain = "all",
    include_dag: bool = False,
) -> list[ToolEntry]:
    if domain not in {"all", "qm", "md", "periodic", "dag"}:
        raise ValueError(f"Unsupported host tool domain: {domain!r}")
    entries: list[ToolEntry] = []
    for entry in get_tools_lst():
        name = entry.tool_name
        if name in _HOST_EXCLUDED_TOOLS or name in _HOST_EXCLUDED_DAG_TOOLS:
            continue
        if entry.cls is None:
            continue
        tool_domain = classify_host_tool_domain(name)
        if domain == "dag":
            if tool_domain != "dag":
                continue
        elif domain == "all":
            if tool_domain == "dag" and not include_dag:
                continue
        else:
            if tool_domain == "dag":
                if not include_dag:
                    continue
            elif tool_domain not in {"common", domain}:
                continue
        entries.append(entry)
    return entries


def list_host_tools(
    *,
    domain: HostToolDomain = "all",
    include_dag: bool = False,
    include_schemas: bool = True,
) -> list[dict[str, Any]]:
    """Project Cloudra's authoritative tool catalog for external host agents."""
    out: list[dict[str, Any]] = []
    for entry in _host_tool_entries(domain=domain, include_dag=include_dag):
        tool_domain = classify_host_tool_domain(entry.tool_name)
        item: dict[str, Any] = {
            "name": entry.tool_name,
            "domain": tool_domain,
            "summary": entry.summary or entry.tool_description[:160],
            "description": entry.tool_description,
            "dag_only": tool_domain == "dag",
        }
        if include_schemas:
            item["input_schema"] = (
                entry.input_json_schema()
                if isinstance(entry.input_schema, dict)
                else entry.input_schema.to_parameters_schema()
            )
        out.append(item)
    return out


class _HostActorContext:
    """Minimal ToolActorContext adapter for an external host calling a Cloudra tool."""

    def __init__(self, project: "Project", *, session_id: str) -> None:
        from types import SimpleNamespace

        from cloudra.runtime_v2.schemas import AgentCapabilities, PermissionSet, RuntimeSettings

        self.id = session_id
        self.session_id = session_id
        self.name = "coordinator"
        self.type = "coordinator"
        self.conversation_id = project.id
        self.working_directory = project.workspace_dir or str(project_workspace_dir(project.id))
        self.orchestration_mode = project.settings.orchestration_mode.value
        self.final_review_request_id = None
        include_dag = project.settings.orchestration_mode.value != "standard"
        self._runtime_agent = SimpleNamespace(
            id=session_id,
            project_id=project.id,
            role_id="coordinator",
            settings=RuntimeSettings(
                orchestration_mode=project.settings.orchestration_mode,
                visual_mode=False,
            ),
            capabilities=AgentCapabilities(
                permissions=PermissionSet(
                    read=True,
                    write=True,
                    manage=True,
                    script=True,
                    destructive=False,
                ),
                tools=[e.tool_name for e in _host_tool_entries(include_dag=include_dag)],
            ),
        )

    def known_file_sha256(self, _absolute_path: str) -> str | None:
        return None

    def permission_all(self) -> Permission:
        return Permission.READ | Permission.WRITE | Permission.SCRIPT | Permission.MANAGE


async def execute_host_tool(
    core: "RuntimeCore",
    *,
    project_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Execute one authoritative Cloudra tool in a project context for an external host."""
    project = core.require_project(project_id)
    if project.archived:
        raise ValueError("Project is archived.")
    if tool_name in _HOST_EXCLUDED_TOOLS or tool_name in _HOST_EXCLUDED_DAG_TOOLS:
        raise PermissionError(f"Tool {tool_name!r} is not exposed in host mode.")
    if _is_dag_tool(tool_name) and project.settings.orchestration_mode.value == "standard":
        raise ValueError(
            f"Tool {tool_name!r} requires DAG mode, which is optional and currently disabled "
            f"for project {project_id!r}. Enable DAG mode on the project first."
        )

    entry = next((e for e in _host_tool_entries(include_dag=True) if e.tool_name == tool_name), None)
    if entry is None:
        raise KeyError(f"Unknown Cloudra host tool: {tool_name!r}")

    session_id = format_host_session_id(owner_id)
    actor = _HostActorContext(project, session_id=session_id)
    if "subagent" in getattr(entry.cls, "model_fields", {}):
        tool = entry.instantiate(subagent=actor)
    else:
        tool = entry.instantiate()

    try:
        parsed = entry.input_schema.model_validate(arguments)
    except ValidationError as exc:
        return {
            "tool_name": tool_name,
            "is_success": False,
            "data": {},
            "summary": validation_feedback(exc, schema=entry.input_schema),
        }

    from cloudra.services.ts_pipeline_context import use_runtime_authority

    with use_runtime_authority(core):
        output = await tool.safe_call(parsed, Session(id=session_id, path=""))
    if not isinstance(output, entry.output_schema):
        raise TypeError(f"Tool {tool_name!r} returned an undeclared output schema")
    data = output.model_dump(mode="json")
    is_success = bool(data.get("is_success", True))
    summary = json.dumps(data, ensure_ascii=False, allow_nan=False)
    return {
        "tool_name": tool_name,
        "is_success": is_success,
        "data": data,
        "summary": summary,
    }


def _host_job_record(row: dict[str, Any]) -> dict[str, Any]:
    record = dict(_row_to_dict(row))
    record["project_id"] = row["conversation_id"]
    record["session_id"] = row["session_id"] or ""
    return record


def inspect_host_compute(
    db: ComputeDB,
    *,
    project_id: str | None = None,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Inspect active and unclaimed terminal compute jobs owned by external host sessions."""
    session_id = format_host_session_id(owner_id) if owner_id is not None else None
    prefix = None if session_id is not None else HOST_SESSION_PREFIX
    active_rows = list_session_compute_jobs(
        db,
        session_id=session_id,
        session_prefix=prefix,
        conversation_id=project_id,
        states=ACTIVE_STATES,
    )
    unclaimed_rows = list_session_compute_jobs(
        db,
        session_id=session_id,
        session_prefix=prefix,
        conversation_id=project_id,
        states=TERMINAL_STATES,
        unclaimed_only=True,
    )
    return {
        "active_jobs": [_host_job_record(row) for row in active_rows],
        "unclaimed_terminal_jobs": [_host_job_record(row) for row in unclaimed_rows],
    }


def claim_host_compute(
    db: ComputeDB,
    *,
    project_id: str | None = None,
    owner_id: str | None = None,
    job_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Atomically claim unclaimed terminal compute jobs (sets notified_at via CAS)."""
    session_id = format_host_session_id(owner_id) if owner_id is not None else None
    prefix = None if session_id is not None else HOST_SESSION_PREFIX
    unclaimed_rows = list_session_compute_jobs(
        db,
        session_id=session_id,
        session_prefix=prefix,
        conversation_id=project_id,
        states=TERMINAL_STATES,
        unclaimed_only=True,
    )
    allowed_ids = set(job_ids) if job_ids is not None else None
    claimed: list[dict[str, Any]] = []
    for row in unclaimed_rows:
        if allowed_ids is not None and row["id"] not in allowed_ids:
            continue
        if claim_terminal_job(db, row["id"]):
            claimed.append(_host_job_record(row))

    active_rows = list_session_compute_jobs(
        db,
        session_id=session_id,
        session_prefix=prefix,
        conversation_id=project_id,
        states=ACTIVE_STATES,
    )
    return {
        "claimed_jobs": claimed,
        "active_jobs": [_host_job_record(row) for row in active_rows],
    }


async def ainspect_host_compute(
    db: ComputeDB,
    *,
    project_id: str | None = None,
    owner_id: str | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        inspect_host_compute, db, project_id=project_id, owner_id=owner_id
    )


async def aclaim_host_compute(
    db: ComputeDB,
    *,
    project_id: str | None = None,
    owner_id: str | None = None,
    job_ids: list[int] | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        claim_host_compute, db, project_id=project_id, owner_id=owner_id, job_ids=job_ids
    )
