"""Stdio MCP adapters for an already running Cloudra API.

Two complementary server modes share one running Cloudra service:

- ``host`` (server name ``cloudra``, default for ``cloudra mcp``):
  Lets an external agent (Antigravity, Codex, Claude Code, etc.) act as the
  reasoning brain while directly calling Cloudra's authoritative chemistry /
  compute tools, optional DAG mode, and compute-job claim watchdog.
- ``subagent`` (server name ``cloudra-subagent``, ``cloudra mcp --mode subagent``):
  Delegates full mechanism research tasks to Cloudra's own ``runtime_v2``
  agents and retrieves progress, interactions, and final verified outcomes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal, TypeVar, get_args
from urllib.parse import urlsplit

import httpx
from mcp.server import MCPServer
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, ErrorData, ResourceTemplate, TextContent, Tool, ToolAnnotations
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    TypeAdapter,
    ValidationError,
)
from typing_extensions import TypedDict

from cloudra.services.delegation_schema import (
    MAX_RESULT_WAIT,
    AgentContext,
    AnswerAccepted,
    CurrentResult,
    ErrorCode,
    HistoryLimit,
    MessageBatch,
    MessageDeliveries,
    NonBlank,
    ProjectList,
    ProjectName,
    ProjectProgress,
    TaskRef,
    TranscriptFilter,
)
from cloudra.services.local_api_client import LOOPBACK_HOSTS, resolve_connection

_ERROR_CODES = frozenset(get_args(ErrorCode))
_ARTIFACT_URI = "cloudra://projects/{project_id}/artifacts/{artifact_id}"
_API_ERRORS = {
    400: ("invalid_request", "Cloudra rejected the request."),
    401: ("forbidden", "Cloudra API authentication failed."),
    403: ("forbidden", "Cloudra denied access."),
    404: ("not_found", "Cloudra could not find the requested record."),
    409: ("state_conflict", "Cloudra could not apply the request in its current state."),
    422: ("invalid_request", "Cloudra rejected the request arguments."),
}
_UNAVAILABLE = ("unavailable", "The Cloudra API is unavailable or returned an unexpected response.")


def _check_id(value: str) -> str:
    if not value.isascii() or not value.replace("_", "").replace("-", "").isalnum():
        raise ValueError("expected a Cloudra ID")
    return value


def _check_owner_id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("owner_id must not be blank")
    if not cleaned.isascii() or not cleaned.replace("_", "").replace("-", "").replace(":", "").isalnum():
        raise ValueError("owner_id must contain only ASCII letters, digits, '_', '-', or ':'")
    return cleaned


_Id = Annotated[NonBlank, AfterValidator(_check_id)]
_OwnerId = Annotated[NonBlank, AfterValidator(_check_owner_id)]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Project(_Input):
    project_id: _Id


class _Agent(_Project):
    session_id: _Id


class _StartNew(_Input):
    name: ProjectName
    task: NonBlank
    workspace_dir: NonBlank | None = None


class _ResumeStart(_Project):
    task: NonBlank


class _StartTask(RootModel[_StartNew | _ResumeStart]):
    @classmethod
    def model_json_schema(cls, **kwargs):
        schema = super().model_json_schema(**kwargs)
        schema["type"] = "object"
        schema["oneOf"] = schema.pop("anyOf")
        return schema


class _Message(_Project, MessageBatch):
    pass


class _Answer(_Project):
    interaction_id: _Id
    response: NonBlank


class _Progress(_Project):
    include_process: bool = True


class _AgentProgress(_Agent):
    limit: HistoryLimit = 1
    filter: TranscriptFilter | None = Field(default=None, description=(
        "JavaScript boolean expression over entry.kind, entry.text, entry.tool_name, entry.status, "
        "entry.at, entry.event_id, and entry.truncated. Scans up to 500 recent entries before applying limit."
    ))
    include_reasoning: bool = False


class _Result(_Agent):
    wait_seconds: Annotated[int, Field(ge=0, le=MAX_RESULT_WAIT)] = 0


class _Artifact(_Project):
    artifact_id: _Id


# ---- Host-mode input / output schemas ----

class _CreateProject(_Input):
    name: ProjectName
    workspace_dir: NonBlank | None = None
    enable_dag: bool = False


class _SetProjectDagMode(_Project):
    enable_dag: bool


class _ListCloudraTools(_Input):
    domain: Literal["all", "qm", "md", "periodic", "dag"] = "all"
    include_dag: bool = False
    include_schemas: bool = False


class _RunCloudraTool(_Project):
    tool_name: NonBlank
    arguments: dict[str, Any] = Field(default_factory=dict)
    owner_id: _OwnerId | None = None


class _WatchdogStatus(_Input):
    project_id: _Id | None = None
    owner_id: _OwnerId | None = None


class _ClaimComputeJobs(_Input):
    project_id: _Id | None = None
    owner_id: _OwnerId | None = None
    job_ids: list[int] | None = None


class HostProjectInfo(TypedDict):
    project_id: str
    name: str
    workspace_dir: str | None
    orchestration_mode: str


class HostToolCatalog(TypedDict):
    tools: list[dict[str, Any]]


class HostToolExecution(TypedDict):
    tool_name: str
    is_success: bool
    data: dict[str, Any]
    summary: str


class HostWatchdogSnapshot(TypedDict):
    active_jobs: list[dict[str, Any]]
    unclaimed_terminal_jobs: list[dict[str, Any]]


class HostClaimResult(TypedDict):
    claimed_jobs: list[dict[str, Any]]
    active_jobs: list[dict[str, Any]]


class _ApiError(Exception):
    def __init__(self, code: str, message: str, *, project_id: str | None = None):
        self.info = {"code": code, "message": message}
        if project_id is not None:
            self.info["project_id"] = project_id
        super().__init__(message)


def _reply(data: dict[str, Any], *, error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
        structured_content=data,
        is_error=error,
    )


def _validate_response(response: httpx.Response) -> httpx.Response:
    if response.is_success:
        return response
    code, message = _API_ERRORS.get(response.status_code, _UNAVAILABLE)
    project_id = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail", payload.get("error", payload))
        detail_code = detail.get("code") if isinstance(detail, dict) else None
        if isinstance(detail_code, str) and detail_code in _ERROR_CODES:
            code = detail_code
            if isinstance(detail.get("message"), str):
                message = detail["message"]
                bearer = response.request.headers.get("authorization", "").removeprefix("Bearer ")
                if bearer:
                    message = message.replace(bearer, "[redacted]")
            if isinstance(detail.get("project_id"), str):
                project_id = detail["project_id"]
    raise _ApiError(code, message, project_id=project_id)


_Arguments = TypeVar("_Arguments", bound=BaseModel)


class _CloudraMCP(MCPServer):
    def __init__(self, client: httpx.AsyncClient, *, server_name: str = "cloudra"):
        super().__init__(server_name, subscriptions=False)
        self.client = client
        self.tools: dict[str, tuple[Tool, type[BaseModel], TypeAdapter, Callable[..., Awaitable[Any]]]] = {}

    def operation(self, arguments: type[_Arguments], result_type: Any, *, read_only: bool = False):
        def register(handler: Callable[[_Arguments], Awaitable[Any]]):
            result = TypeAdapter(result_type)
            tool = Tool(
                name=handler.__name__,
                description=handler.__doc__,
                input_schema=arguments.model_json_schema(),
                output_schema={"type": "object", **result.json_schema()},
                annotations=ToolAnnotations(read_only_hint=read_only),
            )
            self.tools[tool.name] = (tool, arguments, result, handler)
            return handler

        return register

    async def list_tools(self) -> list[Tool]:
        return [tool for tool, _, _, _ in self.tools.values()]

    async def call_tool(self, name: str, arguments: dict[str, Any], context=None) -> CallToolResult:
        operation = self.tools.get(name)
        if operation is None:
            return _reply({"code": "not_found", "message": "Unknown Cloudra tool."}, error=True)
        _, model, result, handler = operation
        try:
            data = model.model_validate(arguments)
        except ValidationError as exc:
            issues = exc.errors(include_url=False, include_context=False, include_input=False)
            messages = [
                issue["msg"] if issue["type"] == "extra_forbidden"
                else f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}"
                for issue in issues
            ]
            return _reply({"code": "invalid_request", "message": " ".join(messages)}, error=True)
        try:
            return _reply(result.validate_python(await handler(data), strict=True))
        except _ApiError as exc:
            return _reply(exc.info, error=True)
        except ValidationError:
            code, message = _UNAVAILABLE
            return _reply({"code": code, "message": message}, error=True)

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise _ApiError(*_UNAVAILABLE) from None
        return _validate_response(response)

    async def json_request(self, method: str, path: str, **kwargs) -> Any:
        response = await self.request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError:
            raise _ApiError(*_UNAVAILABLE) from None

    async def list_resource_templates(self) -> list[ResourceTemplate]:
        return [ResourceTemplate(uri_template=_ARTIFACT_URI, name="Cloudra result artifact")]

    async def read_resource(self, uri, context=None) -> list[ReadResourceContents]:
        location = urlsplit(str(uri))
        parts = location.path.split("/")
        if (
            location.scheme != "cloudra" or location.netloc != "projects"
            or location.query or location.fragment or len(parts) != 4 or parts[2] != "artifacts"
        ):
            raise MCPError(ErrorData(code=-32002, message="Unknown Cloudra resource."))
        try:
            args = _Artifact(project_id=parts[1], artifact_id=parts[3])
            response = await self.request(
                "GET", f"/api/v2/artifacts/{args.artifact_id}/download",
                params={"project_id": args.project_id},
            )
        except ValidationError:
            raise MCPError(ErrorData(code=-32002, message="Invalid Cloudra resource URI.")) from None
        except _ApiError as exc:
            raise MCPError(ErrorData(code=-32002, message=str(exc), data=exc.info)) from None
        mime_type = response.headers.get("content-type", "application/octet-stream")
        media_type = mime_type.partition(";")[0]
        is_text = media_type.startswith("text/") or media_type == "application/json"
        return [ReadResourceContents(content=response.text if is_text else response.content, mime_type=mime_type)]


def _project_path(args: _Project) -> str:
    return f"/api/v2/projects/{args.project_id}"


def _agent_path(args: _Agent) -> str:
    return f"{_project_path(args)}/agents/{args.session_id}"


def build_subagent_server(client: httpx.AsyncClient) -> MCPServer:
    """Build the ``cloudra-subagent`` MCP server for delegating tasks to Cloudra."""
    server = _CloudraMCP(client, server_name="cloudra-subagent")

    @server.operation(_Input, ProjectList, read_only=True)
    async def list_projects(_args: _Input) -> ProjectList:
        """List active Cloudra projects and their creation times."""
        projects = await server.json_request("GET", "/api/v2/projects")
        return {"projects": [
            {"project_id": project["id"], "name": project["name"], "created_at": project["created_at"]}
            for project in projects
        ]}

    @server.operation(_StartTask, TaskRef)
    async def start_task(args: _StartTask) -> TaskRef:
        """Start research with a Coordinator. Use a name for a new project or a project_id for an unstarted one."""
        if isinstance(args.root, _StartNew) and args.root.workspace_dir and client.base_url.host not in LOOPBACK_HOSTS:
            raise _ApiError("forbidden", "A remote Cloudra connection uses the service-assigned workspace.")
        return await server.json_request(
            "POST", "/api/v2/tasks", json=args.root.model_dump(exclude_none=True),
        )

    @server.operation(_Progress, ProjectProgress, read_only=True)
    async def get_progress(args: _Progress) -> ProjectProgress:
        """Inspect a project's Agent instances, pending interactions and process notes."""
        return await server.json_request(
            "GET", f"{_project_path(args)}/progress", params={"include_process": args.include_process},
        )

    @server.operation(_AgentProgress, AgentContext, read_only=True)
    async def get_agent_progress(args: _AgentProgress) -> AgentContext:
        """Read recent Agent output. A JavaScript filter can inspect entry; reasoning is opt-in."""
        return await server.json_request(
            "POST", f"{_agent_path(args)}/progress",
            json=args.model_dump(exclude={"project_id", "session_id"}, exclude_none=True),
        )

    @server.operation(_Result, CurrentResult, read_only=True)
    async def get_result(args: _Result) -> CurrentResult:
        """Read the current delivery or pending activity. Optionally wait up to 20 seconds."""
        return await server.json_request(
            "GET", f"{_agent_path(args)}/result", params={"wait_seconds": args.wait_seconds},
        )

    @server.operation(_Message, MessageDeliveries)
    async def send_message(args: _Message) -> MessageDeliveries:
        """Send a message to specific Agent instances and report delivery for each recipient."""
        return await server.json_request(
            "POST", f"{_project_path(args)}/messages",
            json={"recipients": args.recipients, "content": args.content},
        )

    @server.operation(_Answer, AnswerAccepted)
    async def answer_question(args: _Answer) -> AnswerAccepted:
        """Reply to a pending question. Relay a user's confirmed decision for scientific choices."""
        await server.json_request(
            "POST", f"{_project_path(args)}/interactions/{args.interaction_id}/response",
            json={"response": args.response},
        )
        return {"accepted": True}

    return server


def build_host_server(client: httpx.AsyncClient, *, owner_id: str | None = None) -> MCPServer:
    """Build the ``cloudra`` host-mode MCP server (tools + optional DAG + compute claim watchdog)."""
    server = _CloudraMCP(client, server_name="cloudra")

    @server.operation(_Input, ProjectList, read_only=True)
    async def list_projects(_args: _Input) -> ProjectList:
        """List active Cloudra projects and their creation times."""
        projects = await server.json_request("GET", "/api/v2/projects")
        return {"projects": [
            {"project_id": project["id"], "name": project["name"], "created_at": project["created_at"]}
            for project in projects
        ]}

    @server.operation(_CreateProject, HostProjectInfo)
    async def create_project(args: _CreateProject) -> HostProjectInfo:
        """Create a Cloudra project workspace. DAG mode is optional and defaults to off (standard)."""
        if args.workspace_dir and client.base_url.host not in LOOPBACK_HOSTS:
            raise _ApiError("forbidden", "A remote Cloudra connection uses the service-assigned workspace.")
        payload: dict[str, Any] = {
            "name": args.name,
            "settings": {
                "orchestration_mode": "dag_guided" if args.enable_dag else "standard",
            },
        }
        if args.workspace_dir is not None:
            payload["workspace_dir"] = args.workspace_dir
        response = await server.json_request("POST", "/api/v2/projects", json=payload)
        project = response.get("data", response)
        settings = project.get("settings") or {}
        return {
            "project_id": project["id"],
            "name": project["name"],
            "workspace_dir": project.get("workspace_dir"),
            "orchestration_mode": settings.get("orchestration_mode", "standard"),
        }

    @server.operation(_SetProjectDagMode, HostProjectInfo)
    async def set_project_dag_mode(args: _SetProjectDagMode) -> HostProjectInfo:
        """Enable or disable optional DAG mode for an existing Cloudra project."""
        mode = "dag_guided" if args.enable_dag else "standard"
        await server.json_request(
            "PATCH",
            _project_path(args),
            json={"settings": {"orchestration_mode": mode}},
        )
        project = await server.json_request("GET", _project_path(args))
        settings = project.get("settings") or {}
        return {
            "project_id": project["id"],
            "name": project["name"],
            "workspace_dir": project.get("workspace_dir"),
            "orchestration_mode": settings.get("orchestration_mode", mode),
        }

    @server.operation(_ListCloudraTools, HostToolCatalog, read_only=True)
    async def list_cloudra_tools(args: _ListCloudraTools) -> HostToolCatalog:
        """List available Cloudra tools, optionally filtered by domain ('qm', 'md', 'periodic', 'dag', or 'all')."""
        return await server.json_request(
            "GET",
            "/api/v2/host/tools",
            params={
                "domain": args.domain,
                "include_dag": args.include_dag,
                "include_schemas": args.include_schemas,
            },
        )

    @server.operation(_RunCloudraTool, HostToolExecution)
    async def run_cloudra_tool(args: _RunCloudraTool) -> HostToolExecution:
        """Execute an authoritative Cloudra tool in a project context (compute jobs are tracked for claiming)."""
        effective_owner = args.owner_id or owner_id
        payload: dict[str, Any] = {"arguments": args.arguments}
        if effective_owner is not None:
            payload["owner_id"] = effective_owner
        return await server.json_request(
            "POST",
            f"{_project_path(args)}/host/tools/{args.tool_name}",
            json=payload,
        )

    @server.operation(_WatchdogStatus, HostWatchdogSnapshot, read_only=True)
    async def watchdog_compute_status(args: _WatchdogStatus) -> HostWatchdogSnapshot:
        """Inspect active compute jobs and finished jobs awaiting claim (read-only)."""
        params: dict[str, str] = {}
        if args.project_id is not None:
            params["project_id"] = args.project_id
        effective_owner = args.owner_id or owner_id
        if effective_owner is not None:
            params["owner_id"] = effective_owner
        return await server.json_request("GET", "/api/v2/host/compute/watchdog", params=params)

    @server.operation(_ClaimComputeJobs, HostClaimResult)
    async def claim_compute_jobs(args: _ClaimComputeJobs) -> HostClaimResult:
        """Atomically claim finished compute jobs owned by this host and return their logs and status."""
        payload: dict[str, Any] = {}
        if args.project_id is not None:
            payload["project_id"] = args.project_id
        effective_owner = args.owner_id or owner_id
        if effective_owner is not None:
            payload["owner_id"] = effective_owner
        if args.job_ids is not None:
            payload["job_ids"] = args.job_ids
        return await server.json_request("POST", "/api/v2/host/compute/claim", json=payload)

    return server


def build_server(
    client: httpx.AsyncClient,
    *,
    mode: Literal["host", "subagent"] = "host",
    owner_id: str | None = None,
) -> MCPServer:
    if mode == "subagent":
        return build_subagent_server(client)
    if mode == "host":
        return build_host_server(client, owner_id=owner_id)
    raise ValueError(f"Unsupported MCP mode: {mode!r}")


async def run(
    api_url: str | None = None,
    *,
    mode: Literal["host", "subagent"] = "host",
    owner_id: str | None = None,
) -> None:
    base_url, token = await asyncio.to_thread(resolve_connection, api_url)
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=60, trust_env=False) as client:
        await build_server(client, mode=mode, owner_id=owner_id).run_stdio_async()
