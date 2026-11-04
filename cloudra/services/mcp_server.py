"""Stdio MCP adapter for an already running Cloudra API."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, TypeVar, get_args
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

from cloudra.persistence import paths
from cloudra.services.api_token import resolve_api_token
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
from cloudra.services.runtime_ownership import find_store_owner

_ERROR_CODES = frozenset(get_args(ErrorCode))
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
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


_Id = Annotated[NonBlank, AfterValidator(_check_id)]


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
    def __init__(self, client: httpx.AsyncClient):
        super().__init__("cloudra", subscriptions=False)
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


def build_server(client: httpx.AsyncClient) -> MCPServer:
    server = _CloudraMCP(client)

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
        if isinstance(args.root, _StartNew) and args.root.workspace_dir and client.base_url.host not in _LOOPBACK:
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


def resolve_connection(api_url: str | None) -> tuple[str, str | None]:
    if api_url is None:
        store_path = os.environ.get("CLOUDRA_RUNTIME_STORE") or paths.runtime_db_path()
        owner = find_store_owner(store_path)
        if owner is None or owner.port is None:
            raise RuntimeError("No running Cloudra API owns this runtime store. Start Cloudra or set --api-url.")
        return f"http://127.0.0.1:{owner.port}", resolve_api_token(create=False)

    try:
        url = httpx.URL(api_url)
    except httpx.InvalidURL:
        raise RuntimeError("Cloudra API URL must be a valid HTTP or HTTPS base URL.") from None
    if url.scheme not in {"http", "https"} or not url.host or url.userinfo or url.query or url.fragment:
        raise RuntimeError("Cloudra API URL must be an HTTP or HTTPS base URL without credentials, query, or fragment.")
    if url.host in _LOOPBACK:
        return str(url), resolve_api_token(create=False)
    if url.scheme != "https":
        raise RuntimeError("A remote Cloudra API URL must use HTTPS.")
    token = os.environ.get("CLOUDRA_MCP_API_TOKEN", "").strip()
    if not token or token == "off":
        raise RuntimeError("Set CLOUDRA_MCP_API_TOKEN for the configured remote Cloudra API.")
    return str(url), token


async def run(api_url: str | None = None) -> None:
    base_url, token = await asyncio.to_thread(resolve_connection, api_url)
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30, trust_env=False) as client:
        await build_server(client).run_stdio_async()
