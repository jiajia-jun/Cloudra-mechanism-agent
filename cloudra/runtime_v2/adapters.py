"""Adapters from the existing tool/LLM code into runtime_v2 protocols.

These are thin protocol bridges, not business logic: each adapter translates
one shape.  They are replaced stage by stage as the underlying capability
becomes native to runtime_v2.
"""

from __future__ import annotations

import json
from typing import Any

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema as LegacyInputSchema
from cloudra.infra.config import get_config
from cloudra.infra.llm_client import LLMClient
from cloudra.infra.yolo_guard import reset_session_yolo, set_session_yolo
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentSession, RuntimeSettings
from cloudra.runtime_v2.turn_pipeline import LLMResponse

_OPENAI_MAX_SUMMARY = 4000


def legacy_tool_schemas(tool_names: list[str] | None = None) -> list[dict[str, Any]]:
    """OpenAI tool schemas from the existing registry, filtered by names."""
    from cloudra.tools import get_tools_lst

    wanted = None if not tool_names or "*" in tool_names else set(tool_names)
    schemas = []
    for entry in get_tools_lst():
        if wanted is not None and entry.tool_name not in wanted:
            continue
        schemas.append(entry.instantiate().tool_schema_json())
    return schemas


def _parse_tool_calls(choice: Any) -> list[ToolCall]:
    calls = []
    for raw in getattr(getattr(choice, "message", None), "tool_calls", None) or []:
        function = getattr(raw, "function", None)
        if function is None:
            continue
        try:
            arguments = json.loads(getattr(function, "arguments", None) or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(
            ToolCall(
                id=getattr(raw, "id", "") or f"tc_{len(calls)}",
                name=getattr(function, "name", "") or "unknown",
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return calls


def legacy_default_settings(agent: AgentSession) -> RuntimeSettings:
    """Fill empty settings fields from the existing global config.

    Coordinator is selected by role id only because the legacy config has two
    named slots; this is a bridge detail, not a runtime privilege.
    """
    cfg = get_config()
    legacy = cfg.coordinator if agent.role_id == "coordinator" else cfg.follower
    settings = agent.settings.model_copy(deep=True)
    settings.model = settings.model or legacy.model
    settings.base_url = settings.base_url or legacy.url
    settings.api_key = settings.api_key or legacy.key
    settings.context_window = settings.context_window or legacy.context_window
    settings.timeout = settings.timeout or legacy.timeout
    return settings


def legacy_default_runtime_settings() -> RuntimeSettings:
    """Global defaults seeded from the existing config at startup."""
    cfg = get_config()
    legacy = cfg.coordinator
    return RuntimeSettings(
        model=legacy.model,
        base_url=legacy.url,
        api_key=legacy.key,
        context_window=legacy.context_window,
        timeout=legacy.timeout,
    )


class LegacyPromptProvider:
    """Build identity/observation messages with the existing PromptAssembler."""

    async def __call__(
        self,
        *,
        agent: AgentSession,
        workspace_dir: str | None,
        tool_names: list[str],
    ) -> list[dict[str, Any]]:
        import asyncio
        import os

        from cloudra.runtime.prompt_assembler import PromptAssembler

        def assemble() -> list[dict[str, Any]]:
            is_coordinator = agent.role_id == "coordinator"
            assembler = PromptAssembler(
                prompt_name=agent.role_id,
                custom_prompt=None,
                conversation_id=agent.project_id,
                working_directory=workspace_dir or os.getcwd(),
                include_memory=is_coordinator,
                include_agents_md=is_coordinator,
                observer_id=agent.id,
            )
            assembly = assembler.assemble(
                capability_names=tool_names,
                web_search_available=False,
            )
            return [*assembly.identity_messages, *assembly.observation_messages]

        return await asyncio.to_thread(assemble)


class LegacyLLMProvider:
    """Non-streaming bridge over the existing LLMClient."""

    def __init__(self, client_factory=None) -> None:
        self._client_factory = client_factory

    def _make_client(self, settings: RuntimeSettings) -> LLMClient:
        if self._client_factory is not None:
            return self._client_factory(settings)
        return LLMClient(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout,
        )

    async def complete(
        self,
        agent: AgentSession,
        messages: list[dict[str, Any]],
        tools: list[str],
    ) -> LLMResponse:
        settings = legacy_default_settings(agent)
        client = self._make_client(settings)
        tool_schemas = legacy_tool_schemas(tools)
        kwargs: dict[str, Any] = {
            "model": settings.model,
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
            "stream": False,
        }
        if settings.top_p is not None:
            kwargs["top_p"] = settings.top_p
        if tool_schemas:
            kwargs["tools"] = tool_schemas
        response = await client.create_with_retry(**kwargs)
        choices = getattr(response, "choices", None) or []
        choice = choices[0] if choices else None
        content = ""
        tool_calls: list[ToolCall] = []
        finish_reason = None
        if choice is not None:
            content = getattr(getattr(choice, "message", None), "content", None) or ""
            tool_calls = _parse_tool_calls(choice)
            finish_reason = getattr(choice, "finish_reason", None)
        usage = client.last_usage or {}
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_requested=False,
            usage=dict(usage) if isinstance(usage, dict) else {},
            finish_reason=finish_reason,
        )


class _LegacyAgentBridge:
    """Duck-typed old-Agent surface required by existing tool classes."""

    def __init__(self, agent: AgentSession, workspace_dir: str | None) -> None:
        self.id = agent.id
        self.name = agent.role_id
        self.type = "coordinator" if agent.role_id == "coordinator" else "follower"
        self.conversation_id = agent.project_id
        self.working_directory = workspace_dir
        self.orchestration_mode = agent.settings.orchestration_mode.value
        self.session_id = agent.id


class LegacyToolExecutor:
    """Execute calls through the existing tool registry.

    Destructive tools keep their own approval path; this bridge only sets the
    session-level YOLO context from the agent's live settings.
    """

    def __init__(self, core) -> None:
        self.core = core

    async def execute(self, agent: AgentSession, call: ToolCall) -> ToolResult:
        from cloudra.tools import get_tools_lst

        entry = next((e for e in get_tools_lst() if e.tool_name == call.name), None)
        if entry is None:
            return ToolResult(
                is_success=False,
                summary=f"[Tool error] unknown tool {call.name!r}. Choose an available tool and retry.",
            )
        project = self.core.require_project(agent.project_id)
        bridge = _LegacyAgentBridge(agent, project.workspace_dir)
        tool = entry.instantiate(subagent=bridge)
        schema_cls = entry.input_schema or LegacyInputSchema
        try:
            parsed = schema_cls.model_validate(call.arguments)
        except Exception as exc:
            return ToolResult(is_success=False, summary=f"[Tool error] invalid arguments: {exc}")
        token = set_session_yolo(agent.settings.yolo)
        try:
            output = await tool.safe_call(parsed, Session(id=agent.id, path=""))
        except Exception as exc:
            return ToolResult(is_success=False, summary=str(exc))
        finally:
            reset_session_yolo(token)
        data = output.toJson() if hasattr(output, "toJson") else output.model_dump(mode="json")
        is_success = bool(data.get("is_success", True))
        summary = json.dumps(data, ensure_ascii=False, default=str)[:_OPENAI_MAX_SUMMARY]
        return ToolResult(is_success=is_success, summary=summary, data=data)
