"""Adapters from the existing tool/LLM code into runtime_v2 protocols.

These are thin protocol bridges, not business logic: each adapter translates
one shape.  They are replaced stage by stage as the underlying capability
becomes native to runtime_v2.
"""

from __future__ import annotations

import copy
import inspect
import json
import logging
from typing import Any, Iterable

from pydantic import ValidationError

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema as LegacyInputSchema
from cloudra.infra.config import get_config
from cloudra.infra.llm_client import LLMClient
from cloudra.infra.streaming import _aiter_chunks, _ChunkPumper, dynamic_deep_merge
from cloudra.infra.tool_errors import validation_feedback
from cloudra.infra.yolo_guard import reset_session_yolo, set_session_yolo
from cloudra.persistence.paths import project_workspace_dir
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentSession, RuntimeSettings
from cloudra.runtime_v2.turn_pipeline import DeltaSink, LLMResponse
from cloudra.tools.capabilities import visual_tools
from cloudra.tools.name_hints import hint_unknown_tool, is_retired_tool_name


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


# DeepSeek Responses 端把名为 ``search`` 的本地 function 视为与 server 端
# web_search 冲突（400 invalid_request_error: "The tool search in your request
# conflicts with server side web_search calls"）。原生搜索启用（deepseek）时
# 发送 schema 改名为 ``search_sources`` 避开保留名，响应侧再映射回 ``search``
# 交回 harness——工具注册与执行语义不变，仅请求线缆名隔离。
DEEPSEEK_WIRE_SEARCH_NAME = "search_sources"


def unwire_search_name(calls: list[ToolCall], *, rename_search: bool) -> list[ToolCall]:
    """把响应里 ``search_sources`` 调用名还原为 ``search``（未启用改名时原样返回）。"""
    if not rename_search:
        return calls
    return [
        ToolCall(
            id=call.id,
            name="search" if call.name == DEEPSEEK_WIRE_SEARCH_NAME else call.name,
            arguments=call.arguments,
        )
        for call in calls
    ]


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
    # native_search 的 v2 默认值就是 "auto"，无法区分"显式 auto"与默认值；
    # 桥接规则：仍是默认时取 legacy 槽位的配置（含 "off" 与自定义参数）。
    if settings.native_search == "auto":
        settings.native_search = legacy.native_search
    if not settings.native_search_params:
        settings.native_search_params = dict(legacy.native_search_params)
    # Kimi Coding 订阅端点只接受 temperature=1，其余值直接 400 拒绝
    if "kimi-for-coding" in (settings.model or ""):
        settings.temperature = 1.0
    return settings


def _native_search_adapter_for(settings: RuntimeSettings):
    """解析模型端原生网页搜索适配器（None = 关闭/不可用）。"""
    from cloudra.infra.web_search_native import resolve_native_search

    return resolve_native_search(
        base_url=settings.base_url or "",
        model=settings.model or "",
        mode=settings.native_search,
        params=settings.native_search_params,
    )


def apply_native_search_to_schemas(
    schemas: list[dict], native_on: bool, rename_search: bool = False
) -> list[dict]:
    """If native_on, mutate search.source to arxiv|openalex (default arxiv).
    Never drop the tool.

    ``rename_search`` additionally renames the wire function to
    ``search_sources`` — required on DeepSeek Responses, whose server-side
    web_search tool rejects a local function named ``search``; the response
    name is mapped back by :func:`unwire_search_name`.
    """
    if not native_on:
        return schemas
    out: list[dict] = []
    for schema in schemas:
        name = (schema.get("function") or {}).get("name")
        if name != "search":
            out.append(schema)
            continue
        schema = copy.deepcopy(schema)
        function = schema.get("function") or {}
        if rename_search:
            function["name"] = DEEPSEEK_WIRE_SEARCH_NAME
        properties = (function.get("parameters") or {}).get("properties") or {}
        source = properties.get("source")
        if isinstance(source, dict):
            source["enum"] = ["arxiv", "openalex"]
            source["default"] = "arxiv"
        description = function.get("description") or ""
        note = "Web search is provided natively; use source=arxiv or source=openalex."
        if note not in description:
            function["description"] = f"{description} {note}".strip()
        out.append(schema)
    return out


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

        from cloudra.runtime.prompt_assembler import PromptAssembler

        def assemble() -> list[dict[str, Any]]:
            is_coordinator = agent.role_id == "coordinator"
            assembler = PromptAssembler(
                prompt_name=agent.role_id,
                custom_prompt=None,
                conversation_id=agent.project_id,
                working_directory=workspace_dir or str(project_workspace_dir(agent.project_id)),
                include_memory=is_coordinator,
                include_agents_md=is_coordinator,
                observer_id=agent.id,
            )
            # 有联网搜索能力（模型端原生搜索或外置 search 工具）时，
            # system prompt 注入「联网搜索（重要）」段，要求先搜再答。
            settings = legacy_default_settings(agent)
            web_search_available = (
                _native_search_adapter_for(settings) is not None or "search" in tool_names
            )
            assembly = assembler.assemble(
                capability_names=tool_names,
                web_search_available=web_search_available,
            )
            return [*assembly.identity_messages, *assembly.observation_messages]

        return await asyncio.to_thread(assemble)


def _to_api_message(message: dict[str, Any]) -> dict[str, Any]:
    """Convert internal history entries to valid OpenAI wire messages.

    Internal tool exchanges carry structured ``tool_calls`` (id/name/arguments)
    on the assistant entry; the wire format requires function-typed tool_calls
    with JSON-string arguments, and tool messages referencing a tool_call_id.
    """
    out: dict[str, Any] = {"role": message.get("role", "user"), "content": message.get("content") or ""}
    if message.get("name"):
        out["name"] = message["name"]
    reasoning = message.get("reasoning_content")
    if reasoning:
        # Thinking-mode endpoints (DeepSeek etc.) require the previous
        # assistant turn's reasoning_content to be echoed on the next call.
        out["reasoning_content"] = reasoning
    calls = message.get("tool_calls")
    if calls:
        out["tool_calls"] = [
            {
                "id": str(call.get("id") or f"tc_{i}"),
                "type": "function",
                "function": {
                    "name": str(call.get("name") or "unknown"),
                    "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False),
                },
            }
            for i, call in enumerate(calls)
        ]
        if not out["content"]:
            out["content"] = None
    if out["role"] == "tool" and message.get("tool_call_id"):
        out["tool_call_id"] = str(message["tool_call_id"])
    return out


class LegacyLLMProvider:
    """Streaming bridge over the existing LLMClient.

    Token deltas are forwarded through the optional ``on_delta`` sink as they
    arrive (throttled); the assembled LLMResponse keeps the same shape as the
    old non-streaming path, so the turn pipeline contract is unchanged.
    """

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

    def supports_vision(self, agent: AgentSession) -> bool:
        """Whether the agent's effective LLM config accepts image input.

        Vision capability lives on the legacy per-role LLMConfig slots; the
        slot is selected by role id exactly like ``legacy_default_settings``.
        """
        cfg = get_config()
        legacy = cfg.coordinator if agent.role_id == "coordinator" else cfg.follower
        return bool(legacy.supports_vision)

    async def complete(
        self,
        agent: AgentSession,
        messages: list[dict[str, Any]],
        tools: list[str],
        on_delta: DeltaSink | None = None,
    ) -> LLMResponse:
        settings = legacy_default_settings(agent)
        client = self._make_client(settings)
        native_adapter = _native_search_adapter_for(settings)
        rename_search = native_adapter is not None and native_adapter.name == "deepseek"
        from cloudra.runtime_v2.schemas import (
            InvocationProtocol,
            effective_invocation_protocol,
        )
        from cloudra.runtime_v2.tool_catalog import (
            javascript_instructions,
            wire_tool_schemas,
        )

        if effective_invocation_protocol(agent) is InvocationProtocol.JAVASCRIPT:
            # Deterministic JS contract message (envelope, serialization,
            # serial backend, limits, direct-only controls); generated
            # declarations use canonical local tool names.
            messages = [
                *messages,
                {
                    "role": "system",
                    "content": javascript_instructions(
                        tools, visual_mode=settings.visual_mode
                    ),
                },
            ]
        tool_schemas = apply_native_search_to_schemas(
            wire_tool_schemas(agent, tools),
            native_adapter is not None,
            rename_search=rename_search,
        )
        if not settings.visual_mode:
            # visual 模式关闭时剥掉视觉工具 schema，模型不可见即不会调用。
            gated = visual_tools()
            tool_schemas = [
                schema
                for schema in tool_schemas
                if (schema.get("function") or {}).get("name") not in gated
            ]
        kwargs: dict[str, Any] = {
            "model": settings.model,
            "messages": [_to_api_message(m) for m in messages],
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
            "stream": True,
        }
        if settings.top_p is not None:
            kwargs["top_p"] = settings.top_p
        if tool_schemas:
            kwargs["tools"] = tool_schemas
        if native_adapter is not None:
            kwargs = native_adapter.inject(kwargs, settings.native_search_params)
        if native_adapter is not None and native_adapter.transport == "responses":
            # DeepSeek 的原生搜索只在 Responses API 支持
            response = await client.create_responses_with_retry(**kwargs)
        else:
            response = await client.create_with_retry(**kwargs)
        pumper = None
        if on_delta is not None:
            pumper = _ChunkPumper(lambda _type, data: on_delta(data["stream"], data["delta"]))
        content = ""
        reasoning_content = ""
        tool_call_buffer: dict[int, dict[str, Any]] = {}
        tool_calls: list[ToolCall] = []
        finish_reason = None
        try:
            async for chunk in _aiter_chunks(response):
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                choice = choices[0]
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                reason = getattr(choice, "finish_reason", None)
                if reason:
                    finish_reason = reason
                token = getattr(delta, "content", None)
                if token:
                    content += token
                    if pumper is not None:
                        await pumper.add("content", token)
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    reasoning_content += reasoning
                    if pumper is not None:
                        await pumper.add("reasoning", reasoning)
                for tc_chunk in getattr(delta, "tool_calls", None) or []:
                    chunk_dict = (
                        tc_chunk.model_dump(exclude_none=True)
                        if hasattr(tc_chunk, "model_dump")
                        else {k: v for k, v in vars(tc_chunk).items() if v is not None}
                    )
                    idx = chunk_dict.get("index", 0)
                    tool_call_buffer[idx] = dynamic_deep_merge(tool_call_buffer.get(idx, {}), chunk_dict)
                if reason == "tool_calls" or (reason == "stop" and tool_call_buffer):
                    tool_calls.extend(_parse_merged_tool_calls(tool_call_buffer.values()))
                    tool_call_buffer.clear()
        except Exception:
            await _close_stream(response)
            raise
        if pumper is not None:
            await pumper.flush()
        # A non-empty leftover buffer means the tool_call JSON was cut off
        # mid-stream; parse what arrived (broken JSON degrades to {}).
        if tool_call_buffer:
            tool_calls.extend(_parse_merged_tool_calls(tool_call_buffer.values()))
        usage = client.last_usage or {}
        return LLMResponse(
            content=content,
            tool_calls=unwire_search_name(tool_calls, rename_search=rename_search),
            stop_requested=False,
            usage=dict(usage) if isinstance(usage, dict) else {},
            finish_reason=finish_reason,
            reasoning=reasoning_content,
        )


def _parse_merged_tool_calls(merged: Iterable[dict[str, Any]]) -> list[ToolCall]:
    """ToolCalls from stream-merged tool_call chunks (wire-shaped dicts)."""
    calls = []
    for raw in merged:
        function = raw.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(
            ToolCall(
                id=str(raw.get("id") or f"tc_{len(calls)}"),
                name=str(function.get("name") or "unknown"),
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return calls


async def _close_stream(response: Any) -> None:
    close = getattr(response, "aclose", None) or getattr(response, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


class _LegacyAgentBridge:
    """Duck-typed old-Agent surface required by existing tool classes."""

    def __init__(self, agent: AgentSession, workspace_dir: str | None) -> None:
        self.id = agent.id
        self.name = agent.role_id
        self.type = "coordinator" if agent.role_id == "coordinator" else "follower"
        self.conversation_id = agent.project_id
        # workspace_dir=None 的存量项目不能落 None：read/write/bash 会把裸相对
        # 路径解析到进程 cwd，串到别的任务目录（GH #24）——统一兜底到
        # per-project 默认工作区，与 project.create 的缺省推导同一事实源。
        self.working_directory = workspace_dir or str(project_workspace_dir(agent.project_id))
        self.orchestration_mode = agent.settings.orchestration_mode.value
        self.session_id = agent.id
        self._permissions = agent.capabilities.permissions

    def permission_all(self):
        """Legacy IntFlag projection of the v2 capability permission set."""
        from cloudra.tools.core.permission_model import Permission

        perms = Permission.NONE
        granted = self._permissions
        if granted.read:
            perms |= Permission.READ
        if granted.write:
            perms |= Permission.WRITE
        if granted.manage:
            perms |= Permission.MANAGE
        if granted.script:
            perms |= Permission.SCRIPT
        if granted.destructive:
            perms |= Permission.DESTRUCTIVE
        return perms


class LegacyToolExecutor:
    """Execute calls through the existing tool registry.

    Destructive tools keep their own approval path; this bridge only sets the
    session-level YOLO context from the agent's live settings.      The Managetool
    dispatch tools (subagent_launcher/subagent_swarm/get_subagent_report) are
    reimplemented on the v2 kernel — see runtime_v2/subagent_bridge.py; the
    agent_hub forum likewise — see runtime_v2/hub_bridge.py; ``schedule``
    reminders — see runtime_v2/reminders.py.
    """

    def __init__(self, core) -> None:
        self.core = core

    async def execute(self, agent: AgentSession, call: ToolCall) -> ToolResult:
        from cloudra.runtime_v2.subagent_bridge import NATIVE_TOOL_NAMES, handle_native_tool
        from cloudra.tools import get_tools_lst

        if call.name in NATIVE_TOOL_NAMES:
            return await handle_native_tool(self.core, agent, call)
        if call.name == "agent_hub":
            from cloudra.runtime_v2.hub_bridge import handle_hub_tool

            return await handle_hub_tool(self.core, agent, call)
        if call.name == "schedule":
            return await self.core.reminders.handle(agent, call)

        if is_retired_tool_name(call.name):
            return ToolResult(
                is_success=False,
                summary=hint_unknown_tool(call.name),
            )

        if call.name == "search":
            source = (call.arguments or {}).get("source") or "web"
            if source == "web" and _native_search_adapter_for(agent.settings) is not None:
                return ToolResult(
                    is_success=False,
                    summary=(
                        "Web search is provided natively by the model. "
                        "Call search with source='arxiv' or source='openalex' instead."
                    ),
                )

        entry = next((e for e in get_tools_lst() if e.tool_name == call.name), None)
        if entry is None:
            return ToolResult(
                is_success=False,
                summary=hint_unknown_tool(call.name),
            )
        project = self.core.require_project(agent.project_id)
        bridge = _LegacyAgentBridge(agent, project.workspace_dir)
        # Several tool classes narrow the `subagent` field to the legacy Agent
        # type, so pydantic construction with the duck-typed bridge fails
        # (dag_*, goal_set, todo, bash, ...).  Construct bare and
        # attach the bridge past validation instead.
        tool = entry.instantiate()
        object.__setattr__(tool, "subagent", bridge)
        schema_cls = entry.input_schema or LegacyInputSchema
        try:
            parsed = schema_cls.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolResult(is_success=False, summary=validation_feedback(exc))
        token = set_session_yolo(agent.settings.yolo)
        try:
            # v2-native user decisions: destructive-tool approvals and ask_user
            # questions go to the kernel PendingBroker (events + futures)
            # instead of the legacy conversation SQLite / event bus.
            async def _approval(**fields):
                return await self.core.pending.request_approval(agent, **fields)

            async def _interaction(prompt: str) -> str:
                return await self.core.pending.request_interaction(agent, prompt)

            from cloudra.base.tools_class import use_approval_handler
            from cloudra.tools.Interactool.ask_user import use_input_handler

            with use_approval_handler(_approval), use_input_handler(_interaction):
                output = await tool.safe_call(parsed, Session(id=agent.id, path=""))
        except Exception:
            # An unexpected safe_call fault is not a business failure: package
            # it as structured tool_exception metadata so the invocation
            # service closes the lifecycle with effect_state=unknown.
            # Validation errors above stay ordinary unsuccessful results.
            from cloudra.runtime_v2.invocation_types import InvocationError

            logging.getLogger(__name__).exception("Tool execution failed: %s", call.name)
            message = "Tool execution failed internally. The error was logged; report the tool call instead of inspecting application source."
            return ToolResult(
                is_success=False,
                summary=message,
                error=InvocationError(code="tool_exception", message=message, effect_state="unknown"),
            )
        finally:
            reset_session_yolo(token)
        data = output.toJson() if hasattr(output, "toJson") else output.model_dump(mode="json")
        is_success = bool(data.get("is_success", True))
        summary = json.dumps(data, ensure_ascii=False, default=str)
        return ToolResult(is_success=is_success, summary=summary, data=data)
