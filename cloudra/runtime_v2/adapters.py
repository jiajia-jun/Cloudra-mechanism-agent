"""Adapters from the existing tool/LLM code into runtime_v2 protocols.

These are thin protocol bridges, not business logic: each adapter translates
one shape.  They are replaced stage by stage as the underlying capability
becomes native to runtime_v2.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import logging
import math
from typing import Any, Iterable

from pydantic import ValidationError

from cloudra.base.session_class import Session
from cloudra.base.tools_class import input_schema as LegacyInputSchema
from cloudra.infra.config import get_config
from cloudra.infra.llm_client import LLMClient, first_prefix_divergence, request_fingerprint
from cloudra.infra.providers import detect_provider_from_url
from cloudra.infra.streaming import _aiter_chunks, _ChunkPumper, dynamic_deep_merge
from cloudra.infra.tool_errors import validation_feedback
from cloudra.infra.yolo_guard import reset_session_yolo, set_session_yolo
from cloudra.persistence.paths import project_workspace_dir
from cloudra.runtime import prompt_assembler as prompt_assembler_labels
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentSession,
    InvocationProtocol,
    RuntimeSettings,
    effective_invocation_protocol,
)
from cloudra.runtime_v2.tool_catalog import javascript_instructions
from cloudra.runtime_v2.turn_pipeline import DeltaSink, LLMResponse
from cloudra.tools.capabilities import is_direct_only, supervisor_access_for, visual_tools
from cloudra.tools.name_hints import hint_unknown_tool, is_retired_tool_name

logger = logging.getLogger(__name__)


def legacy_tool_schemas(tool_names: list[str] | None = None) -> list[dict[str, Any]]:
    """Schemas for explicit capabilities; only ``*`` expands the registry."""
    from cloudra.tools import get_tools_lst

    if not tool_names:
        return []
    wanted = None if "*" in tool_names else set(tool_names)
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
    settings.reasoning_effort = settings.reasoning_effort or legacy.reasoning_effort
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


# 动态源更新/撤销消息的标签：在原快照标签前标明来源与替代关系。
# 键对应 PromptSource.kind（memory / agents_md / workspace）。
_SNAPSHOT_UPDATE_LABELS = {
    "memory": (
        "[Updated long-term memory — MEMORY.md changed]",
        "This snapshot replaces the earlier MEMORY.md snapshot above; follow this version.",
    ),
    "agents_md": (
        "[Updated user instructions — AGENTS.md changed]",
        "This snapshot replaces the earlier AGENTS.md snapshot above; the user's "
        "instructions keep full authority — follow this version.",
    ),
    "workspace": (
        "[Workspace observation — update]",
        "The workspace changed since the earlier observation; this is the current "
        "observation data and replaces the earlier one above.",
    ),
}

_SNAPSHOT_RETRACTIONS = {
    "memory": (
        "[Long-term memory retracted — MEMORY.md no longer exists]\n\n"
        "The earlier MEMORY.md snapshot above is retracted; do not follow it."
    ),
    "agents_md": (
        "[User instructions retracted — AGENTS.md no longer exists]\n\n"
        "The earlier AGENTS.md snapshot above is retracted; do not follow it."
    ),
}

# 动态源快照的原标签（与 prompt_assembler 的快照构造器一一对应）。
_SNAPSHOT_BASE_LABELS = {
    "memory": prompt_assembler_labels.MEMORY_SNAPSHOT_LABEL,
    "agents_md": prompt_assembler_labels.AGENTS_SNAPSHOT_LABEL,
    "workspace": prompt_assembler_labels.WORKSPACE_OBSERVATION_LABEL,
}


class LegacyContextPrefix:
    """Per-run owner of the installed prompt prefix and dynamic source snapshots.

    缓存连续性契约：``install()`` 只在上下文初始化（或 compact/重置后前缀
    不在投影头部）时运行一次，产出静态协议（角色身份、JS 调用协议）与
    首份动态快照；``refresh()`` 每轮只读复查动态源，只有真实变化才追加
    标明来源与替代关系的新消息，无变化返回空——已发送的旧消息绝不重写。

    跨 run/重启：runner 每个 run 重建本对象，但经 ``restored``（会话投影
    的 prefix_meta + 头部消息）回灌后 matches() 直接命中，前缀不重装。
    ``pending_install`` / ``pending_appends`` 记录最近一次 install/refresh
    产出但尚未由 ContextBroker 持久化进投影的消息；``drain_pending`` 在
    commit_input 里被调用恰好一次。
    """

    def __init__(
        self,
        *,
        agent: AgentSession,
        workspace_dir: str | None,
        tool_names: Iterable[str],
        restored: dict | None = None,
    ) -> None:
        self._agent = agent
        self._tool_names = [name for name in tool_names if name]
        settings = legacy_default_settings(agent)
        self._settings = settings
        is_coordinator = agent.role_id == "coordinator"
        from cloudra.runtime.prompt_assembler import PromptAssembler

        # 构造只做纯字段记录与 is_application_checkout 的两个 is_file 探测
        # （与 PromptAssembler 既有构造开销相同）；真正读盘在 install/refresh
        # 的 to_thread 里。
        self._assembler = PromptAssembler(
            prompt_name=agent.role_id,
            custom_prompt=None,
            conversation_id=agent.project_id,
            working_directory=workspace_dir or str(project_workspace_dir(agent.project_id)),
            include_memory=is_coordinator and not agent.settings.clean_context,
            include_agents_md=is_coordinator and not agent.settings.clean_context,
            observer_id=agent.id,
        )
        # 有联网搜索能力（模型端原生搜索或外置 search 工具）时，
        # system prompt 注入「联网搜索（重要）」段，要求先搜再答。
        self._web_search_available = (
            _native_search_adapter_for(settings) is not None or "search" in self._tool_names
        )
        self._initial: list[dict[str, Any]] | None = None
        self._revisions: dict[str, str | None] = {}
        self._prompt_revision = ""
        self._capability_revision = ""
        self._js_revision = ""
        self._tool_selection = None
        self._pending_install: tuple[dict[str, Any], ...] = ()
        self._pending_appends: tuple[dict[str, Any], ...] = ()
        # 跨 run/重启回灌（Task 4）：会话上下文投影的头部即上次安装的前缀，
        # 安装元数据（revisions/静态 revision/前缀长度）随
        # context.prefix_installed 事件持久化。回灌后 matches() 直接命中
        # 投影头部，跨 run 不重装、不重发。
        if restored:
            meta = dict(restored.get("meta") or {})
            self._tool_selection = meta.get("tool_selection")
            prefix_len = int(meta.get("prefix_len") or 0)
            messages = list(restored.get("messages") or [])
            if prefix_len and len(messages) >= prefix_len:
                self._initial = [dict(message) for message in messages[:prefix_len]]
                self._revisions = dict(meta.get("revisions") or {})
                self._prompt_revision = str(meta.get("prompt_revision") or "")
                self._capability_revision = str(meta.get("capability_revision") or "")
                self._js_revision = str(meta.get('js_revision') or '')

    # ------------------------------------------------------------- pipeline 协议

    def matches(self, history: list[dict[str, Any]]) -> bool:
        """history 以本 owner 安装的初始前缀开头（逐字节相等）。"""
        initial = self._initial
        if initial is None or len(history) < len(initial):
            return False
        return list(history[: len(initial)]) == initial

    async def install(self) -> list[dict[str, Any]]:
        """上下文初始化：安装静态协议与首份动态快照（同一上下文恰好一次）。"""
        assembly, js_message = await asyncio.to_thread(self._assemble)
        messages = [*assembly.identity_messages]
        if js_message is not None:
            messages.append(js_message)
        messages.extend(assembly.observation_messages)
        self._initial = messages
        self._revisions = self._dynamic_revisions(assembly)
        self._prompt_revision = assembly.prompt_revision
        self._capability_revision = assembly.capability_revision
        self._js_revision = self._js_message_revision(js_message)
        self._pending_install = tuple(messages)
        self._pending_appends = ()
        return messages

    async def refresh(self) -> list[dict[str, Any]]:
        """每轮只读复查动态源：变化追加带来源/替代关系的新消息，不变返回空。"""
        assembly, js_message = await asyncio.to_thread(self._assemble)
        appends: list[dict[str, Any]] = []
        # 静态边界：角色 prompt / 技能清单 / 工具协议在 run 内真实变化时是
        # 新的冷启动边界——记录原因并以追加消息表达，不重写已发送的前缀，
        # 也不为了冻结前缀向模型隐瞒最新规则。
        if (
            assembly.prompt_revision != self._prompt_revision
            or assembly.capability_revision != self._capability_revision
        ):
            logger.info(
                "context prefix static boundary agent=%s prompt_revision %s -> %s "
                "capability_revision %s -> %s",
                getattr(self._agent, "id", "?"),
                self._prompt_revision[:20],
                assembly.prompt_revision[:20],
                self._capability_revision[:20],
                assembly.capability_revision[:20],
            )
            appends.append(
                {
                    "role": "system",
                    "content": (
                        "[Protocol boundary — static prompt changed]\n\n"
                        "The role prompt, skill manifest, or tool protocol changed "
                        "during this run (the reason is recorded in the server logs). "
                        "The updated static protocol snapshot below supersedes the "
                        "earlier one above:\n\n"
                        + str(assembly.identity_messages[0].get("content") or "")
                    ),
                }
            )
            self._prompt_revision = assembly.prompt_revision
            self._capability_revision = assembly.capability_revision
        js_revision = self._js_message_revision(js_message)
        if js_revision != self._js_revision:
            if js_message is not None:
                appends.append({'role': 'system', 'content':
                    '[Tool directory update]\nThe current directory and reader protocol below '
                    'supersedes earlier versions. Read current contracts before calling tools.\n\n'
                    + str(js_message['content'])})
            self._js_revision = js_revision
        new_revisions = self._dynamic_revisions(assembly)
        new_messages = {
            source.kind: message
            for source, message in zip(
                assembly.observation_sources, assembly.observation_messages
            )
        }
        for kind in ("memory", "agents_md", "workspace"):
            old_revision = self._revisions.get(kind)
            new_revision = new_revisions.get(kind)
            if new_revision == old_revision:
                # 无实际观察变化：不发消息（避免「上一轮变化列表→本轮无新
                # 变化」的无价值消息模式）。
                continue
            message = new_messages.get(kind)
            if message is not None:
                appends.append(
                    {"role": "system", "content": self._as_update(kind, str(message.get("content") or ""))}
                    if old_revision is not None
                    else dict(message)
                )
            elif kind in _SNAPSHOT_RETRACTIONS:
                appends.append(
                    {"role": "system", "content": _SNAPSHOT_RETRACTIONS[kind]}
                )
            self._revisions[kind] = new_revision
        self._pending_install = ()
        self._pending_appends = tuple(appends)
        return appends

    def drain_pending(self) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
        """取出并清空待持久化消息（install, appends）；由 ContextBroker 在
        commit_input 里恰好调用一次。"""
        pending = (self._pending_install, self._pending_appends)
        self._pending_install = ()
        self._pending_appends = ()
        return pending

    def set_tool_selection(self, record: dict) -> None:
        self._tool_selection = dict(record)

    def snapshot_meta(self) -> dict:
        """随 context.prefix_installed 事件持久化的安装元数据（回灌用）。"""
        return {
            "prefix_len": len(self._initial or []),
            "tool_selection": self._tool_selection,
            "revisions": dict(self._revisions),
            "prompt_revision": self._prompt_revision,
            "capability_revision": self._capability_revision,
            'js_revision': self._js_revision,
        }

    async def current_prefix(self) -> tuple[list[dict[str, Any]], dict]:
        """compact 边界用：按当前状态重新装配前缀（动态快照取最新），
        返回 (消息, 安装元数据)；不触碰 pending/游标。"""
        assembly, js_message = await asyncio.to_thread(self._assemble)
        messages = [*assembly.identity_messages]
        if js_message is not None:
            messages.append(js_message)
        messages.extend(assembly.observation_messages)
        meta = {
            "prefix_len": len(messages),
            "tool_selection": self._tool_selection,
            "revisions": self._dynamic_revisions(assembly),
            "prompt_revision": assembly.prompt_revision,
            "capability_revision": assembly.capability_revision,
            'js_revision': self._js_message_revision(js_message),
        }
        return messages, meta

    def adopt(self, messages: list[dict[str, Any]], meta: dict) -> None:
        """compact 安装后采纳新头部：后续轮次 matches() 命中，不重装。"""
        self._initial = list(messages)
        self._tool_selection = meta.get("tool_selection")
        self._revisions = dict(meta.get("revisions") or {})
        self._prompt_revision = str(meta.get("prompt_revision") or "")
        self._capability_revision = str(meta.get("capability_revision") or "")
        self._js_revision = str(meta.get('js_revision') or '')

    # ------------------------------------------------------------------ 内部

    def _assemble(self):
        """同步装配（install/refresh 的调用方负责 to_thread）。"""
        assembly = self._assembler.assemble(
            capability_names=self._tool_names,
            web_search_available=self._web_search_available,
        )
        js_message = None
        if effective_invocation_protocol(self._agent) is InvocationProtocol.JAVASCRIPT:
            # JS 调用协议是静态前缀的一部分：上下文初始化时安装一次，
            # adapter 不再每轮追加到请求尾部。
            js_message = {
                "role": "system",
                "content": javascript_instructions(
                    self._tool_names,
                    visual_mode=self._settings.visual_mode,
                    orchestration_mode=self._settings.orchestration_mode,
                    role_id=self._agent.role_id,
                ),
            }
        return assembly, js_message

    @staticmethod
    def _js_message_revision(message: dict | None) -> str:
        return hashlib.sha256(json.dumps(message, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

    @staticmethod
    def _dynamic_revisions(assembly) -> dict[str, str | None]:
        return {
            source.kind: source.revision for source in assembly.observation_sources
        }

    @staticmethod
    def _as_update(kind: str, content: str) -> str:
        """把 initial 形态的快照内容换成更新形态（标签替换，其余逐字节保留）。"""
        base_label = _SNAPSHOT_BASE_LABELS[kind]
        if not content.startswith(base_label):
            raise ValueError(f"snapshot content for {kind} lacks its base label")
        label, note = _SNAPSHOT_UPDATE_LABELS[kind]
        return f"{label}\n\n{note}\n\n{content[len(base_label):]}"


class LegacyPromptProvider:
    """Vend per-run context-prefix owners backed by the existing PromptAssembler.

    缓存连续性要求静态前缀在同一会话上下文内只安装一次：runner 每个 run
    调 ``begin_context`` 建立一个 owner，并以会话投影的 prefix_meta 回灌
    （``restored``），跨 run/重启不重装；TurnPipeline 每轮经 owner 区分
    「初始安装」与「增量复查」。
    """

    def begin_context(
        self,
        *,
        agent: AgentSession,
        workspace_dir: str | None,
        tool_names: Iterable[str],
        restored: dict | None = None,
    ) -> LegacyContextPrefix:
        return LegacyContextPrefix(
            agent=agent,
            workspace_dir=workspace_dir,
            tool_names=tool_names,
            restored=restored,
        )


def _extract_delta_reasoning(delta: Any) -> str | None:
    """从流式 chunk 的 delta 中兼容提取 reasoning/thinking 文本。

    兼容多服务商与代理网关格式：
    - DeepSeek / 官方兼容接口: delta.reasoning_content
    - OpenRouter / vLLM / Ollama: delta.reasoning
    - Anthropic 第三方网关: delta.thinking
    - Pydantic v2 model_extra 字典
    - 字典形态 delta
    """
    for attr in ("reasoning_content", "reasoning", "thinking"):
        val = None
        if isinstance(delta, dict):
            val = delta.get(attr)
        else:
            val = getattr(delta, attr, None)
            if val is None and hasattr(delta, "model_extra") and isinstance(delta.model_extra, dict):
                val = delta.model_extra.get(attr)
        if val:
            if isinstance(val, str):
                return val
            if isinstance(val, list):
                parts = []
                for item in val:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text") or item.get("summary") or item.get("content") or ""
                        if text:
                            parts.append(str(text))
                if parts:
                    return "".join(parts)
            return str(val)
    return None


def _to_api_message(message: dict[str, Any]) -> dict[str, Any]:
    """Convert internal history entries to valid OpenAI wire messages.

    Internal tool exchanges carry structured ``tool_calls`` (id/name/arguments)
    on the assistant entry; the wire format requires function-typed tool_calls
    with JSON-string arguments, and tool messages referencing a tool_call_id.
    """
    out: dict[str, Any] = {"role": message.get("role", "user"), "content": message.get("content") or ""}
    if message.get("name"):
        out["name"] = message["name"]
    reasoning = message.get("reasoning_content") or message.get("reasoning")
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


def _requires_reasoning_echo(settings: RuntimeSettings) -> bool:
    """DeepSeek 思考模式要求历史里每条 assistant 消息都回传 reasoning_content。

    压缩摘要等 harness 生成的 assistant 消息没有思考内容，缺一条即 400
    （"The `reasoning_content` in the thinking mode must be passed back"）；
    空串同样被拒，回填时注入单个空格。只在思考模式开启
    （reasoning_effort 非空）时适用。
    """
    if not settings.reasoning_effort:
        return False
    preset = detect_provider_from_url(settings.base_url or "")
    return preset is not None and preset.id == "deepseek"


class LegacyLLMProvider:
    """Streaming bridge over the existing LLMClient.

    Token deltas are forwarded through the optional ``on_delta`` sink as they
    arrive (throttled); the assembled LLMResponse keeps the same shape as the
    old non-streaming path, so the turn pipeline contract is unchanged.
    """

    def __init__(self, client_factory=None) -> None:
        self._client_factory = client_factory
        # 前缀连续性诊断：agent.id -> 上一条实际发送请求的逐消息哈希/模型。
        # 只存哈希与模型名，绝不存消息原文。
        self._request_hashes: dict[str, list[str]] = {}
        self._request_models: dict[str, str] = {}

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

    def resolve_effective_settings(self, agent: AgentSession) -> RuntimeSettings:
        """``complete()`` 实际使用的 settings（legacy 槽位补全空字段）。

        遥测钩子：turn pipeline 的 llm.request_started / llm.completed 用它
        记录生效模型——agent.settings 是 spawn 快照，未显式覆盖时 model 为
        空串，而真实模型在这个桥接层才解析出来。
        """
        return legacy_default_settings(agent)

    async def select_tool_names(self, agent, messages, *, resolved_settings):
        """A no-tool auxiliary request using the current effective model."""
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.conformer_model_budget import ModelRequestAccounting
        settings = resolved_settings.model_copy(deep=True)
        client = self._make_client(settings)
        accounting = None
        succeeded = False
        try:
            database = await asyncio.to_thread(ComputeDB)
            accounting = await ModelRequestAccounting.for_agent(database, agent.project_id, agent.id)
            client.request_accounting = accounting
            kwargs = dict(model=settings.model, messages=messages, stream=False,
                temperature=settings.temperature, max_tokens=settings.max_tokens)
            if settings.reasoning_effort:
                kwargs['reasoning_effort'] = settings.reasoning_effort
            self._log_request_fingerprint(agent, kwargs, kind='tool_selection')
            response = await asyncio.wait_for(client.create(**kwargs), timeout=settings.timeout or 300)
            message = response.choices[0].message
            succeeded = True
            return LLMResponse(content=message.content or '',
                tool_calls=list(getattr(message, 'tool_calls', None) or []),
                usage=dict(client.last_usage or {}))
        finally:
            try:
                if accounting is not None:
                    await accounting.finish(success=succeeded, usage=client.last_usage)
            finally:
                await client.aclose()

    async def complete(
        self,
        agent: AgentSession,
        messages: list[dict[str, Any]],
        tools: list[str],
        on_delta: DeltaSink | None = None,
    ) -> LLMResponse:
        settings = legacy_default_settings(agent)
        client = self._make_client(settings)
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.conformer_model_budget import ModelRequestAccounting
        accounting = None
        succeeded = False
        try:
            accounting = await ModelRequestAccounting.for_agent(ComputeDB(), getattr(agent, 'project_id', ''), getattr(agent, 'id', ''))
            client.request_accounting = accounting
            result = await asyncio.wait_for(
                self._complete_with_client(
                    agent, client, settings, messages, tools, on_delta
                ),
                timeout=settings.timeout,
            )
            succeeded = True
            return result
        except TimeoutError as exc:
            logger.error(
                "llm complete timed out after %ss agent=%s model=%s",
                settings.timeout,
                getattr(agent, "id", "?"),
                settings.model,
            )
            raise TimeoutError(
                f"LLM request timed out after {settings.timeout}s "
                f"(agent={getattr(agent, 'id', '?')} model={settings.model})"
            ) from exc
        finally:
            try:
                if accounting is not None:
                    await accounting.finish(success=succeeded, usage=client.last_usage)
            finally:
                # Always close the per-request pool, including accounting failures.
                aclose = getattr(client, "aclose", None)
                if aclose is not None:
                    try:
                        await aclose()
                    except Exception:
                        pass

    def _log_request_fingerprint(
        self, agent: AgentSession, kwargs: dict[str, Any], *, kind: str
    ) -> None:
        """请求指纹/首差异诊断：只记哈希与下标，不记原文、参数或密钥。

        ``kind`` 区分主 agent 请求与摘要请求（摘要路径在
        ``compaction.summarize_with_agent_settings`` 单独打 kind="summary"），
        便于分组统计缓存连续性。
        """
        fingerprint = request_fingerprint(kwargs)
        agent_id = str(getattr(agent, "id", "") or "?")
        previous = self._request_hashes.get(agent_id)
        previous_model = self._request_models.get(agent_id)
        if previous is None:
            # 首请求/重启后首请求是冷启动，不参与前缀分歧统计。
            diff: Any = "cold"
        else:
            divergence = first_prefix_divergence(previous, fingerprint["message_hashes"])
            diff = divergence if divergence is not None else "-"
        self._request_hashes[agent_id] = fingerprint["message_hashes"]
        self._request_models[agent_id] = fingerprint["model"]
        logger.info(
            "llm request fingerprint kind=%s agent=%s model=%s messages=%d "
            "tools=%s first_diff=%s",
            kind,
            agent_id,
            fingerprint["model"],
            fingerprint["message_count"],
            fingerprint["tools_hash"][:12],
            diff,
        )
        if previous_model is not None and previous_model != fingerprint["model"]:
            # 模型变化是新的冷启动边界：记录原因，不伪称跨模型缓存连续。
            logger.info(
                "llm request boundary kind=%s agent=%s reason=model_changed %s -> %s",
                kind,
                agent_id,
                previous_model,
                fingerprint["model"],
            )

    def _request_kwargs(
        self,
        agent: AgentSession,
        settings: RuntimeSettings,
        messages: list[dict[str, Any]],
        tools: list[str],
    ) -> dict[str, Any]:
        native_adapter = _native_search_adapter_for(settings)
        rename_search = native_adapter is not None and native_adapter.name == "deepseek"
        from cloudra.runtime_v2.tool_catalog import wire_tool_schemas

        # JS 调用协议消息不再在这里追加到请求尾部：它属于静态前缀，由
        # LegacyContextPrefix 在上下文初始化时安装一次（见 begin_context）。
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
        api_messages = [_to_api_message(m) for m in messages]
        if _requires_reasoning_echo(settings):
            for msg in api_messages:
                if msg.get("role") == "assistant" and not msg.get("reasoning_content"):
                    msg["reasoning_content"] = " "
        kwargs: dict[str, Any] = {
            "model": settings.model,
            "messages": api_messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
            "stream": True,
        }
        if settings.top_p is not None:
            kwargs["top_p"] = settings.top_p
        if settings.reasoning_effort:
            kwargs["reasoning_effort"] = settings.reasoning_effort
        if tool_schemas:
            kwargs["tools"] = tool_schemas
        if native_adapter is not None:
            kwargs = native_adapter.inject(kwargs, settings.native_search_params)
        # JS programs are deliberately single top-level calls. Ask compatible
        # chat endpoints to enforce that contract server-side as well. Some
        # OpenAI-compatible gateways reject the newer parameter; retry the
        # same request without it only when the client rejects the keyword
        # before sending, preserving traditional protocol behavior.
        js_protocol = effective_invocation_protocol(agent) is InvocationProtocol.JAVASCRIPT
        if js_protocol:
            kwargs["parallel_tool_calls"] = False
        return kwargs

    def estimate_prompt_tokens(self, agent: AgentSession, messages: list[dict], tools: list[str]) -> int:
        """Use the same request projection for budgeting and sending."""
        from cloudra.infra.token_estimator import TokenEstimator

        kwargs = self._request_kwargs(agent, legacy_default_settings(agent), messages, tools)
        tokens = TokenEstimator.count_messages(kwargs["messages"])
        if kwargs.get("tools"):
            tokens += TokenEstimator.count_text(json.dumps(kwargs["tools"], ensure_ascii=False))
        return tokens

    async def _complete_with_client(
        self,
        agent: AgentSession,
        client: LLMClient,
        settings: RuntimeSettings,
        messages: list[dict[str, Any]],
        tools: list[str],
        on_delta: DeltaSink | None,
    ) -> LLMResponse:
        native_adapter = _native_search_adapter_for(settings)
        rename_search = native_adapter is not None and native_adapter.name == "deepseek"
        kwargs = await asyncio.to_thread(self._request_kwargs, agent, settings, messages, tools)
        js_protocol = effective_invocation_protocol(agent) is InvocationProtocol.JAVASCRIPT
        self._log_request_fingerprint(agent, kwargs, kind="agent")
        try:
            if native_adapter is not None and native_adapter.transport == "responses":
                # DeepSeek 的原生搜索只在 Responses API 支持
                response = await client.create_responses_with_retry(**kwargs)
            else:
                response = await client.create_with_retry(**kwargs)
        except TypeError as exc:
            if not js_protocol or "unexpected keyword argument 'parallel_tool_calls'" not in str(exc):
                raise
            kwargs.pop("parallel_tool_calls", None)
            if native_adapter is not None and native_adapter.transport == "responses":
                response = await client.create_responses_with_retry(**kwargs)
            else:
                response = await client.create_with_retry(**kwargs)
        pumper = None
        if on_delta is not None:
            pumper = _ChunkPumper(lambda _type, data: on_delta(data["stream"], data["delta"]))
        content = ""
        reasoning_content = ""
        final_message_reasoning = ""
        tool_call_buffer: dict[int, dict[str, Any]] = {}
        tool_calls: list[ToolCall] = []
        finish_reason = None
        try:
            async for chunk in _aiter_chunks(response):
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                choice = choices[0]
                # Some thinking-mode endpoints (DeepSeek) put reasoning_content
                # on choice.message of the last chunk, not on delta. Skip that
                # and the next tool turn 400s: "reasoning_content ... must be
                # passed back to the API."
                message = getattr(choice, "message", None)
                if message is not None:
                    extracted = _extract_delta_reasoning(message)
                    if extracted:
                        final_message_reasoning = extracted
                reason = getattr(choice, "finish_reason", None)
                if reason:
                    finish_reason = reason
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                token = getattr(delta, "content", None)
                if token:
                    content += token
                    if pumper is not None:
                        await pumper.add("content", token)
                reasoning = _extract_delta_reasoning(delta)
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
            # A leftover buffer may contain a truncated call; keep validation
            # inside the stream boundary so parse failures also close it.
            if tool_call_buffer:
                tool_calls.extend(_parse_merged_tool_calls(tool_call_buffer.values()))
        except asyncio.CancelledError:
            # 取消不是普通异常：也必须关流（停止语义契约 4），然后原样上抛。
            await _close_stream(response)
            raise
        except Exception:
            await _close_stream(response)
            raise
        if pumper is not None:
            await pumper.flush()
        if not reasoning_content and final_message_reasoning:
            reasoning_content = final_message_reasoning
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
    """Parse wire calls without inventing identities or repairing arguments."""
    def reject_constant(value: str) -> None:
        raise ValueError("tool call arguments cannot contain non-finite numbers")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            reject_constant(value)
        return number

    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("tool call arguments cannot contain duplicate object keys")
            result[key] = value
        return result

    calls = []
    for raw in merged:
        if not isinstance(raw, dict):
            raise ValueError("tool call must be a JSON object")
        call_id = raw.get("id")
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("tool call id must be a non-empty string")
        function = raw.get("function")
        if not isinstance(function, dict):
            raise ValueError("tool call function must be a JSON object")
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("tool name must be a non-empty string")
        serialized_arguments = function.get("arguments")
        if not isinstance(serialized_arguments, str):
            raise ValueError("tool call arguments must be a JSON object string")
        arguments = json.loads(
            serialized_arguments, parse_constant=reject_constant,
            parse_float=finite_float, object_pairs_hook=unique_keys,
        )
        if not isinstance(arguments, dict):
            raise ValueError("tool call arguments must be a JSON object")
        calls.append(
            ToolCall(
                id=call_id,
                name=name,
                arguments=arguments,
            )
        )
    return calls


async def _close_stream(response: Any) -> None:
    close = getattr(response, "aclose", None) or getattr(response, "close", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:
        # 关流是尽力而为（同步生成器可能正被 to_thread 消费，close 会抛
        # ValueError）；绝不能掩盖正在传播的 CancelledError/原异常。
        pass


class _LegacyAgentBridge:
    """Duck-typed old-Agent surface required by existing tool classes."""

    def __init__(self, agent: AgentSession, workspace_dir: str | None) -> None:
        self._runtime_agent = agent
        self.id = agent.id
        self.name = agent.role_id
        # dag_* 工具的 _actor() 依 type=="supervisor" 判 GraphActor.SUPERVISOR
        # （裁决权限的唯一入口）；督导不再是 follower。
        self.type = (
            "coordinator"
            if agent.role_id == "coordinator"
            else "supervisor"
            if agent.role_id == "supervisor"
            else "follower"
        )
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

    async def _execute_supervisor(self, agent: AgentSession, call: ToolCall) -> ToolResult:
        """Route one Supervisor business call through the restricted executor.

        The Supervisor's tools run inside the same InvocationService
        lifecycle as every agent; only the executor differs:
        ``dag/supervisor_tools.py`` re-checks the ``supervisor_access``
        projection and enforces the path/action guards (evidence reads stay
        inside the workspace/artifact roots, hub actions are whitelisted,
        hub call can create an independent peer). Top-level tools with a
        Supervisor capability still use this executor; lifecycle controls
        without one (stop) take the normal path below.
        """
        from cloudra.dag.supervisor_tools import SupervisorToolExecutor, dumps_result
        from cloudra.persistence.paths import data_dir

        project = self.core.require_project(agent.project_id)
        workspace = project.workspace_dir or str(project_workspace_dir(agent.project_id))
        executor = SupervisorToolExecutor(
            core=self.core,
            project_id=agent.project_id,
            workspace_root=workspace,
            artifact_root=str(data_dir() / "artifacts"),
        )
        executor.bind_run(
            agent=_LegacyAgentBridge(agent, workspace),
            session=Session(id=agent.id, path=""),
        )
        payload = await executor.execute(call.name, call.arguments, session_id=agent.id)
        return ToolResult(
            is_success=bool(payload.get("is_success", True)),
            summary=dumps_result(payload),
            data=payload,
        )

    async def execute(self, agent: AgentSession, call: ToolCall) -> ToolResult:
        from cloudra.runtime_v2.subagent_bridge import NATIVE_TOOL_NAMES, handle_native_tool
        from cloudra.tools import get_tools_lst

        if agent.role_id == "supervisor" and (
            not is_direct_only(call.name) or supervisor_access_for(call.name) != "none"
        ):
            return await self._execute_supervisor(agent, call)

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
        # 工具字段的类型是 ToolActorContext（Protocol），声明了该字段的工具直接
        # 经构造器拿到调用者身份（不再需要 object.__setattr__ 绕过 pydantic 校验）；
        # 不声明它的工具（log_parser 等无状态工具）按原样构造。
        if "subagent" in getattr(entry.cls, "model_fields", {}):
            actor = _LegacyAgentBridge(agent, project.workspace_dir)
            tool = entry.instantiate(subagent=actor)
        else:
            tool = entry.instantiate()
        from cloudra.tools.core.permission_model import check_permission
        if not check_permission(_LegacyAgentBridge(agent, project.workspace_dir).permission_all(), tool.tool_permission_all()):
            return ToolResult(is_success=False, summary="Tool requires permissions absent from this task")
        schema_cls = entry.input_schema or LegacyInputSchema
        try:
            parsed = schema_cls.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolResult(is_success=False, summary=validation_feedback(exc))
        from cloudra.runtime_v2.invocation_context import report_tool_progress
        from cloudra.runtime_v2.schemas import ToolProgress

        await report_tool_progress(ToolProgress(
            phase="executing", message="Validated tool inputs; entering tool execution",
            effective_arguments=parsed.model_dump(mode="json"),
        ))
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
            from cloudra.services.ts_pipeline_context import use_runtime_authority
            from cloudra.tools.Interactool.ask_user import use_input_handler
            with use_approval_handler(_approval), use_input_handler(_interaction), use_runtime_authority(self.core):
                output = await tool.safe_call(parsed, Session(id=agent.id, path=""))
            if not isinstance(output, entry.output_schema):
                raise TypeError(f"Tool {call.name!r} returned an undeclared output schema")
            data = output.model_dump(mode="json")
            is_success = bool(data.get("is_success", True))
            if call.name == "bash":
                is_success = is_success and data.get("exit_code", 1) == 0
            summary = json.dumps(data, ensure_ascii=False, allow_nan=False)
        except Exception as exc:
            # An unexpected safe_call fault is not a business failure: package
            # it as structured tool_exception metadata so the invocation
            # service closes the lifecycle with effect_state=unknown.
            # Validation errors above stay ordinary unsuccessful results.
            from cloudra.runtime_v2.event_writer import EventPersistenceError
            from cloudra.runtime_v2.invocation_types import InvocationError

            # safe_call wraps tool exceptions; a failed durable progress write
            # must retain the runtime's non-retryable persistence semantics.
            cause = exc
            while cause is not None:
                if isinstance(cause, EventPersistenceError):
                    raise cause
                cause = cause.__cause__

            logging.getLogger(__name__).exception("Tool execution failed: %s", call.name)
            message = "Tool execution failed internally. The error was logged; report the tool call instead of inspecting application source."
            return ToolResult(
                is_success=False,
                summary=message,
                error=InvocationError(code="tool_exception", message=message, effect_state="unknown"),
            )
        finally:
            reset_session_yolo(token)
        return ToolResult(is_success=is_success, summary=summary, data=data)
