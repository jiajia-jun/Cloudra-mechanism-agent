"""Restricted tool execution for the scientific Supervisor.

The Supervisor reviews claims against evidence; it does not do research work.
Its tool surface is therefore a small, capability-gated subset declared in
``tools/registry.py`` (``supervisor_access``) and projected exclusively through
``tools/capabilities.py``:

- ``evidence_read``: restricted text reads, log parsing and identity checks
  inside the project workspace and the immutable artifact root;
- ``skill_read``: the skill loader (same loader as research agents);
- ``hub``: AgentHub via the runtime_v2 native bridge (search/browse/read/
  directory/post/call, with the same peer-call behavior as other agents);
- ``review_decision``: DAG verdict tools (draft adjudication, call reviews,
  coverage contract).
- ``process_write``: ordinary file tools restricted to project-root PROCESS.md.

Everything else — research-file writes, compute submission, ad-hoc Python or
Bash, unknown tools — is rejected at the execution layer, not just hidden
from the prompt. This module enforces; it does not re-declare the allow-list.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import ValidationError

from cloudra.infra.tool_errors import validation_feedback
from cloudra.persistence.workspace import WorkspaceError, WorkspaceService
from cloudra.tools import capabilities

logger = logging.getLogger(__name__)

_READ_MAX_CHARS = 30_000
_HUB_ACTIONS = frozenset({"search", "browse", "read", "directory", "post", "call"})
# Path-carrying arguments of evidence_read tools that must stay inside the
# allowed roots. Tools not listed here receive no path arguments.
_PATH_FIELDS = {
    "log_parser": ("log_path",),
    "reaction_mapping": ("reactant_path", "product_path"),
}


def _error(message: str) -> dict[str, Any]:
    return {"is_success": False, "message": message}


class SupervisorToolExecutor:
    """Executes supervisor-allowed tools with capability and path gating.

    Constructed with the runtime core (optional; required for AgentHub), the
    project id, the project workspace root and the immutable artifact root.
    ``bind_run`` attaches the per-run Supervisor agent and session used when
    instantiating DAG verdict tools.
    """

    def __init__(
        self,
        *,
        core: Any = None,
        project_id: str | None = None,
        workspace_root: str | None = None,
        artifact_root: str | None = None,
    ):
        self._core = core
        self._project_id = project_id
        self._workspace_root = (
            Path(workspace_root).expanduser().resolve() if workspace_root else None
        )
        self._artifact_root = (
            Path(artifact_root).expanduser().resolve() if artifact_root else None
        )
        self._agent: Any = None
        self._session: Any = None

    def bind_run(self, *, agent: Any, session: Any) -> None:
        self._agent = agent
        self._session = session

    @staticmethod
    def allowed_tools() -> dict[str, str]:
        """tool_name -> supervisor_access; discovery and execution share this."""
        return capabilities.supervisor_allowed_tools()

    def _allowed_roots(self) -> list[Path]:
        # Check the global artifact root first when roots overlap; otherwise a
        # broad workspace root could bypass per-project artifact ownership.
        return [root for root in (self._artifact_root, self._workspace_root) if root]

    def _resolve_evidence_path(self, raw_path: str) -> Path:
        """Resolve a user-supplied path and require containment in an allowed root.

        ``Path.resolve`` follows symlinks of existing components, so a symlink
        inside the workspace that points outside fails the containment check.
        """
        if not raw_path or "\x00" in raw_path:
            raise WorkspaceError("Evidence path must not be empty or contain NUL characters")
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            if self._workspace_root is None:
                raise WorkspaceError("Relative evidence paths require a workspace root")
            candidate = self._workspace_root / candidate
        resolved = candidate.resolve(strict=False)
        for root in self._allowed_roots():
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            if self._artifact_root is not None and root == self._artifact_root:
                return self._validate_registered_artifact(candidate, resolved, root)
            return resolved
        raise WorkspaceError(
            f"Evidence path escapes the project workspace and artifact root: {raw_path}"
        )

    def _validate_registered_artifact(self, candidate: Path, resolved: Path, root: Path) -> Path:
        """Allow only this project's immutable, registered artifact snapshot."""
        try:
            relative = candidate.relative_to(root)
        except ValueError as exc:
            raise WorkspaceError("Evidence path is not inside the artifact root") from exc
        if not relative.parts:
            raise WorkspaceError("An artifact id is required")
        # Reject symlinks anywhere in the artifact path, including a symlinked
        # file that resolves back inside the global root.
        for index in range(1, len(relative.parts) + 1):
            if (root.joinpath(*relative.parts[:index])).is_symlink():
                raise WorkspaceError("symlinked artifact paths are not allowed")
        if self._project_id is None:
            raise WorkspaceError("artifact evidence requires a project id")
        from cloudra.persistence.artifacts import ArtifactService

        artifact = ArtifactService(data_dir=root.parent).get(
            self._project_id, relative.parts[0]
        )
        if artifact is None:
            raise WorkspaceError(
                f"artifact {relative.parts[0]!r} is not registered for this project"
            )
        stored = (root / artifact.storage_path).resolve(strict=False)
        if stored != resolved or not stored.is_file() or stored.is_symlink():
            raise WorkspaceError("artifact storage path does not match its registered snapshot")
        digest = hashlib.sha256(stored.read_bytes()).hexdigest()
        if digest != artifact.sha256:
            raise WorkspaceError("registered artifact content hash does not match storage")
        return resolved

    def _normalize_path_arguments(self, name: str, arguments: dict[str, Any]) -> str | None:
        """Containment-check path arguments and rewrite them to resolved absolute
        paths, so the underlying tool (which resolves against the process cwd)
        opens exactly the file the Supervisor was allowed to see."""
        for field in _PATH_FIELDS.get(name, ()):
            value = arguments.get(field)
            if not value:
                continue
            try:
                arguments[field] = str(self._resolve_evidence_path(str(value)))
            except WorkspaceError as exc:
                return f"[permission denied] {name}: {exc}"
        return None

    def _execute_read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from cloudra.tools.Searchtool.read import Read_input_schema

        try:
            arguments = Read_input_schema.model_validate(arguments).model_dump()
        except ValidationError as exc:
            return _error(validation_feedback(exc))
        raw_path = str(arguments.get("path") or "")
        try:
            resolved = self._resolve_evidence_path(raw_path)
        except WorkspaceError as exc:
            return _error(f"[permission denied] read: {exc}")
        root = next(root for root in self._allowed_roots() if resolved.is_relative_to(root))
        relative = resolved.relative_to(root).as_posix()
        service = WorkspaceService(root)
        offset = arguments.get("offset")
        limit = arguments.get("limit")
        start = max(int(offset) - 1, 0) if offset else 0
        try:
            snapshot, content, total, actual_start, actual_end = service.read_text(
                relative, start, (start + int(limit)) if limit else -1
            )
        except (WorkspaceError, OSError) as exc:
            return _error(f"read failed: {exc}")
        truncated = False
        if len(content) > _READ_MAX_CHARS:
            content = content[:_READ_MAX_CHARS]
            truncated = True
        message = (
            f"Truncated to {_READ_MAX_CHARS} characters; page with offset/limit."
            if truncated
            else ""
        )
        return {
            "is_success": True,
            "path": str(resolved),
            "kind": "text",
            "content": content,
            "sha256": snapshot.sha256,
            "total_lines": total,
            "offset": actual_start + 1,
            "limit": actual_end - actual_start,
            "truncated": truncated,
            "message": message,
        }

    async def _execute_hub(self, arguments: dict[str, Any], *, session_id: str | None) -> dict[str, Any]:
        action = str(arguments.get("action") or "").strip().lower()
        if action not in _HUB_ACTIONS:
            return _error(
                f"[permission denied] agent_hub action {action!r} is not available to the "
                "Supervisor; allowed actions: search / browse / read / directory / post / call."
            )
        if self._core is None or self._project_id is None:
            return _error(
                "AgentHub is unavailable in this supervisor context "
                "(no runtime core bound); decide from the local evidence instead."
            )
        from cloudra.runtime_v2 import hub_bridge
        from cloudra.runtime_v2.policies.base import ToolCall

        if hasattr(self._core, "require_agent"):
            if not session_id:
                return _error("AgentHub call requires a Supervisor session id.")
            author = self._core.require_agent(session_id)
            if author.project_id != self._project_id or author.role_id != "supervisor":
                return _error("AgentHub Supervisor session does not belong to this project.")
        else:
            author = SimpleNamespace(
                id=session_id or "supervisor",
                project_id=self._project_id,
                role_id="supervisor",
            )
        call = ToolCall(id=f"supervisor-hub-{action}", name="agent_hub", arguments=arguments)
        result = await hub_bridge.handle_hub_tool(self._core, author, call)
        payload = dict(result.data or {})
        payload.setdefault("is_success", result.is_success)
        payload.setdefault("message", result.summary)
        return payload

    async def _run_tool_entry(
        self, name: str, arguments: dict[str, Any], *, session_id: str | None
    ) -> dict[str, Any]:
        from cloudra.tools import get_tools_lst

        entry = next((item for item in get_tools_lst() if item.tool_name == name), None)
        if entry is None:
            return _error(f"[permission denied] Tool {name!r} is not registered.")
        try:
            input_obj = entry.input_schema(**arguments)
        except ValidationError as exc:
            return _error(validation_feedback(exc))
        session = self._session or SimpleNamespace(id=session_id or "supervisor")
        # Several tool classes narrow the `subagent` field to the legacy Agent
        # type (dag_* verdict tools among them), so pydantic construction with
        # a duck-typed runtime_v2 bridge fails; construct bare and attach the
        # bound agent past validation, exactly like LegacyToolExecutor.
        tool = entry.instantiate()
        if self._agent is not None:
            object.__setattr__(tool, "subagent", self._agent)
        output = await tool.tool_call(input_obj, session)
        return output.model_dump(mode="json")

    async def execute(
        self, name: str, arguments: dict[str, Any], *, session_id: str | None = None
    ) -> dict[str, Any]:
        """Execute one supervisor-allowed tool; returns the usual tool result shape."""
        access = capabilities.supervisor_access_for(name)
        if access == "none":
            return _error(
                f"[permission denied] Tool {name!r} is not available to the Supervisor. "
                "Allowed capabilities: evidence read (read/log_parser/reaction_mapping/"
                "dag_view/dag_view_evidence/dag_delivery_report), get_skill, agent_hub, "
                "and the dag_* review-decision tools."
            )
        if access == "hub":
            return await self._execute_hub(arguments, session_id=session_id)
        if access == "process_write":
            try:
                path = await asyncio.to_thread(self._resolve_evidence_path, str(arguments.get('path') or ''))
            except WorkspaceError as exc:
                return _error(f'[permission denied] {name}: {exc}')
            if self._workspace_root is None or path != self._workspace_root / 'PROCESS.md':
                return _error('[permission denied] The Supervisor may write only project-root PROCESS.md.')
            arguments = {**arguments, 'path': 'PROCESS.md'}
        if name == "read":
            return await asyncio.to_thread(self._execute_read, arguments)
        if access == "evidence_read" and not name.startswith("dag_"):
            denied = await asyncio.to_thread(self._normalize_path_arguments, name, arguments)
            if denied:
                return _error(denied)
        try:
            if access == 'process_write':
                from cloudra.base.tools_class import use_approval_handler
                from cloudra.infra.yolo_guard import reset_session_yolo, set_session_yolo

                async def approve_note(**_fields):
                    # The path above is already restricted to the authorized notebook.
                    return True, ''

                token = set_session_yolo(False)
                try:
                    with use_approval_handler(approve_note):
                        return await self._run_tool_entry(name, arguments, session_id=session_id)
                finally:
                    reset_session_yolo(token)
            return await self._run_tool_entry(name, arguments, session_id=session_id)
        except Exception as exc:
            # Tool-layer failures go back to the model as an error result
            # instead of ending the supervisor run.
            logger.warning("[Supervisor] %s failed: %s", name, exc)
            return _error(f"[System error] {name} failed: {exc}")


def dumps_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
