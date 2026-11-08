"""Turn pipeline: the fixed per-turn skeleton shared by every agent.

LLM and tool execution are injected protocols, so tests run without network or
external programs.  Harness behaviour is added exclusively through PolicyStage
instances; this module never special-cases a tool or orchestration mode.

Tool calls no longer execute here: every call goes through
``InvocationService`` (durable request -> policy -> executor -> durable raw
result -> post hooks -> durable finish), so traditional dispatch and the JS
runtime share one lifecycle.  The loop guard moved with it
(``invocation.InvocationService``); it stays deliberately volatile per-run
shell state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

from cloudra.runtime_v2.event_writer import EventWriter
from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.js_runtime import JavaScriptRuntime
from cloudra.runtime_v2.policies.base import (
    PipelineContext,
    PolicyStage,
    ToolCall,
    ToolResult,
)
from cloudra.runtime_v2.policies.goal_stage import read_goal
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    EventEnvelope,
    InvocationProtocol,
    RuntimeSettings,
    effective_invocation_protocol,
)
from cloudra.runtime_v2.tool_catalog import JS_EXEC_NAME, validate_wire_route
from cloudra.tools.capabilities import is_direct_only

logger = logging.getLogger(__name__)

# Streaming delta sink: (kind, text) where kind is "content" or "reasoning".
DeltaSink = Callable[[str, str], Awaitable[None]]


class ContextBudgetError(ValueError):
    """The configured window cannot hold the prepared input and output reserve."""

    status_code = 400


class ContextPrefix(Protocol):
    """Per-context owner of the installed prompt prefix and dynamic snapshots.

    缓存连续性契约（计划 2026-09-13-harness-cache-continuity Task 2/4）：
    ``install()`` 在上下文初始化时恰好运行一次（静态协议 + 首份动态快照），
    产出的消息经 context.prefix_installed 事件进会话级上下文投影，成为
    后续请求的完整前缀；``refresh()`` 每轮只读复查动态源，变化只以追加
    消息表达。owner 由 runner 按 run 创建，但状态从会话投影回灌
    （``restored``），跨 run/重启不重装。
    """

    def matches(self, history: list[dict[str, Any]]) -> bool: ...

    async def install(self) -> list[dict[str, Any]]: ...

    async def refresh(self) -> list[dict[str, Any]]: ...


async def resolve_media_references(
    messages: list[dict[str, Any]], *, vision_enabled: bool
) -> list[dict[str, Any]]:
    """把上下文投影里的 ``image_ref`` 部件解析为发送形态（返回新列表）。

    投影只存稳定引用（路径 + 创建时写入的 fallback 文本），不重嵌 base64：
    vision 开时校验快照并解析为 ``image_url``（data URL）；关闭时使用文本 fallback。
    解析后全部是文本部件时内容坍缩回纯字符串（与历史线缆形态一致）。
    引用指向入历史时保存的不可变快照；原文件变化/删除不改变历史。
    快照缺失或损坏时拒绝发送。不含 image_ref 的消息原样共享（不拷贝）。
    """
    from cloudra.infra.media import encode_image_reference

    out: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list) or not any(
            isinstance(part, dict) and part.get("type") == "image_ref" for part in content
        ):
            out.append(message)
            continue
        parts: list[dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_ref":
                parts.append(part)
                continue
            fallback = str(part.get("fallback") or f"[Image: {part.get('path')}]")
            url = None
            if vision_enabled:
                url = await asyncio.to_thread(
                    encode_image_reference, part
                )
            if url:
                parts.append({"type": "image_url", "image_url": {"url": url}})
            else:
                parts.append({"type": "text", "text": fallback})
        if all(isinstance(part, dict) and part.get("type") == "text" for part in parts):
            # 全部降级为文本时坍缩回纯字符串（与视觉关闭时的历史线缆形态一致）
            out.append(
                {**message, "content": "\n".join(str(part.get("text") or "") for part in parts)}
            )
            continue
        out.append({**message, "content": parts})
    return out


@dataclass(frozen=True)
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_requested: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    # 本次 LLM 调用的完整 reasoning（thinking）文本；流式 delta 走 llm.chunk
    # 不进事件日志，这里在每轮落一条 agent.thinking，保证历史轮次的 thinking
    # 在重进会话/刷新后仍可见。
    reasoning: str = ""


class LLMProvider(Protocol):
    """LLM 调用面；可选钩子 ``resolve_effective_settings(agent)`` 供遥测
    解析生效模型（空快照模型由 provider 桥接补全的场合）。"""

    async def complete(
        self,
        agent: AgentSession,
        messages: list[dict[str, Any]],
        tools: list[str],
        on_delta: DeltaSink | None = None,
    ) -> LLMResponse: ...

    async def select_tool_names(self, agent: AgentSession, messages: list[dict[str, Any]],
                               *, resolved_settings: RuntimeSettings) -> LLMResponse: ...


class ToolExecutor(Protocol):
    async def execute(self, agent: AgentSession, call: ToolCall) -> ToolResult: ...


@dataclass(frozen=True)
class TurnOutcome:
    decision: Literal["continue", "stop", "wait_input", "wait_approval"]
    content: str = ""
    message: str = ""
    tool_exchanges: tuple[tuple[ToolCall, ToolResult], ...] = ()
    blocked_call: ToolCall | None = None
    # Thinking-mode models require this on the next request's assistant turn.
    reasoning: str = ""


class TurnPipeline:
    def __init__(
        self,
        *,
        event_log: EventLog,
        stages: list[PolicyStage],
        llm: LLMProvider,
        tools: ToolExecutor,
        stop_tool: str = "stop",
        prompt_provider=None,
        event_hub=None,
        notices=None,
        goal_reader=read_goal,
        event_writer: EventWriter | None = None,
        invocations: InvocationService | None = None,
        js_runtime: JavaScriptRuntime | None = None,
    ) -> None:
        self.event_log = event_log
        self.stages = list(stages)
        self.llm = llm
        self.tools = tools
        self.stop_tool = stop_tool
        self.prompt_provider = prompt_provider
        self.event_hub = event_hub
        self.notices = notices
        # Shell-side goal IO: ``goal_reader(agent) -> dict | None`` reads the
        # persisted goal anchor (sync file IO, offloaded per turn) so stages
        # receive it read-only via PipelineContext.goal and stay IO-free.
        # The default is the built-in file reader; pass None to disable goal
        # injection entirely, or a custom callable to source it elsewhere.
        self.goal_reader = goal_reader
        # Single tool lifecycle for this pipeline.  Real wiring passes the
        # shared core EventWriter (API/benchmark); standalone tests get a
        # memory-only writer on the same log.
        self.event_writer = event_writer or (invocations.event_writer if invocations else None)
        if self.event_writer is None:
            self.event_writer = EventWriter(event_log, event_hub)
        self.invocations = invocations or InvocationService(
            event_writer=self.event_writer, stages=self.stages, tools=tools
        )
        # JS protocol shell: shares the same writer/lifecycle; js_exec is a
        # protocol execution request, never registered as a normal tool.
        self.js_runtime = js_runtime or JavaScriptRuntime(
            event_writer=self.event_writer, invocations=self.invocations
        )

    def _emitter(self, agent: AgentSession, run_id: str):
        def emit(type: str, data: dict[str, Any] | None = None) -> None:
            self.event_log.append(
                type,
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data=data or {},
            )

        return emit

    async def _publish(self, _envelope: EventEnvelope) -> None:
        # Narration must reach the UI immediately, through the same durable
        # writer as tool events. Streaming chunks remain transient hub events.
        await self.event_writer.flush()

    async def _initial_tool_documents(self, agent, run_id, inputs, broker, owner):
        from uuid import uuid4

        from cloudra.infra.config import get_config
        from cloudra.runtime_v2.schemas import InvocationProtocol, effective_invocation_protocol
        from cloudra.runtime_v2.tool_catalog import guest_tool_names
        from cloudra.runtime_v2.tool_selection import ToolDocumentSelector, ToolSelectionRecord
        from cloudra.tools import get_tools_lst
        from cloudra.tools.documentation import build_tool_documents, catalog_revision, tool_capability_summaries

        if effective_invocation_protocol(agent) is not InvocationProtocol.JAVASCRIPT:
            return
        state = broker.prefix_state(agent.id) or {}
        previous = (state.get('meta') or {}).get('tool_selection')
        if previous:
            record = ToolSelectionRecord.model_validate(previous)
            if record.status == 'started':
                record = record.model_copy(update={'status':'failed','error_code':'selection_interrupted'})
                await broker.record_tool_selection(agent=agent,run_id=run_id,record=record,messages=[{
                    'role':'system','content':'Initial document selection was interrupted. Read tool contracts on demand.'}])
            known_versions = dict((state.get('meta') or {}).get('tool_document_revisions') or {})
            known_versions = {**record.document_revisions, **known_versions}
            if known_versions:
                def current_versions():
                    entries = get_tools_lst()
                    allowed = guest_tool_names(agent.capabilities.tools,visual_mode=agent.settings.visual_mode,
                        orchestration_mode=agent.settings.orchestration_mode,role_id=agent.role_id)
                    names = [name for name in known_versions if name in allowed]
                    return {doc.name:doc.revision for doc in build_tool_documents(names,allowed_names=allowed,entries=entries)}
                versions = await asyncio.to_thread(current_versions)
                if versions != known_versions:
                    record = record.model_copy(update={'document_revisions': {
                        name: revision for name, revision in versions.items() if name in record.names}})
                    await broker.record_tool_selection(agent=agent,run_id=run_id,record=record,messages=[{
                        'role':'system','content':'Previously loaded tool contracts or availability changed. '
                        'Earlier versions are superseded. Read current contracts with get_tool_docs. '
                        'Current available versions: '+str(versions),
                        'tool_document_revisions': versions}])
            if owner is not None:
                owner.set_tool_selection(record.model_dump(mode='json'))
            return
        # The input may already be durable if a process stopped immediately
        # before selection_started. Recover the original task, never a later
        # inbox message or an interface summary.
        first_ids = set((state.get('meta') or {}).get('tool_document_task_message_ids') or [])
        stored_inputs = [message for message in broker.current_messages(agent.id)
            if message.get('role') == 'user' and message.get('message_id') in first_ids]
        inputs = stored_inputs or inputs
        if not inputs:
            return
        config = await asyncio.to_thread(lambda: get_config().tool_document_loading.model_copy(deep=True))
        resolver = getattr(self.llm,'resolve_effective_settings',None)
        settings = await asyncio.to_thread(resolver,agent) if resolver is not None else agent.settings.model_copy(deep=True)
        def candidate_data():
            entries = get_tools_lst()
            allowed = guest_tool_names(agent.capabilities.tools, visual_mode=agent.settings.visual_mode,
                orchestration_mode=agent.settings.orchestration_mode, role_id=agent.role_id)
            return entries, allowed, tool_capability_summaries(allowed,entries=entries)
        entries, allowed, summaries = await asyncio.to_thread(candidate_data)
        source = 'llm' if config.strategy == 'llm' else config.semantic_backend
        record = ToolSelectionRecord(status='started',selection_id=uuid4().hex,source=source,
            catalog_revision=catalog_revision(summaries),model=settings.model if source=='llm' else getattr(config,source).model,
            task_message_ids=tuple(str(item['message_id']) for item in inputs if item.get('message_id')))
        await broker.record_tool_selection(agent=agent,run_id=run_id,record=record,messages=[])
        if owner is not None:
            owner.set_tool_selection(record.model_dump(mode='json'))
        result = await ToolDocumentSelector(self.llm).select(agent=agent,task_messages=inputs,
            resolved_settings=settings,candidates=summaries,config=config)
        changes = result.model_dump()
        docs = ()
        if result.status=='selected':
            try:
                docs = await asyncio.to_thread(build_tool_documents,result.names,allowed_names=allowed,entries=entries)
            except ValueError:
                changes.update(status='failed',names=(),error_code='document_unavailable')
        record = record.model_copy(update=changes)
        messages=[]
        if docs:
            record = record.model_copy(update={'document_revisions':{doc.name:doc.revision for doc in docs}})
            messages=[{'role':'system','content':'Initial tool contracts. These documents do not grant permissions.\n\n'+
                '\n\n'.join(doc.content for doc in docs),
                'tool_documents':[{'name':doc.name,'revision':doc.revision} for doc in docs]}]
        elif record.status=='failed':
            messages=[{'role':'system','content':f'Initial tool documentation preload failed ({record.error_code}). '
                'Use the capability directory and get_tool_docs to read contracts as needed.'}]
        await broker.record_tool_selection(agent=agent,run_id=run_id,record=record,messages=messages)
        if owner is not None:
            owner.set_tool_selection(record.model_dump(mode='json'))

    async def estimate_prompt_tokens(self, agent: AgentSession, messages: list[dict]) -> int:
        """Count the prepared messages and, when available, the provider's wire tools."""
        from cloudra.runtime_v2.compaction import estimate_messages_tokens

        estimator = getattr(self.llm, "estimate_prompt_tokens", None)
        if estimator is not None:
            return await asyncio.to_thread(estimator, agent, messages, agent.capabilities.tools)
        return await asyncio.to_thread(estimate_messages_tokens, messages)

    async def run_turn(
        self,
        *,
        agent: AgentSession,
        run_id: str,
        settings: RuntimeSettings,
        capabilities: AgentCapabilities,
        inbox_messages: list[dict[str, Any]],
        history: list[dict[str, Any]] | None = None,
        workspace_dir: str | None = None,
        notices=None,
        context_prefix: ContextPrefix | None = None,
        context_broker=None,
        vision_enabled: bool = True,
        prepare_context: Callable[[list[dict], int], Awaitable[list[dict]]] | None = None,
    ) -> TurnOutcome:
        emit = self._emitter(agent, run_id)
        notice_sink = notices if notices is not None else self.notices
        goal = None
        if self.goal_reader is not None:
            goal = await asyncio.to_thread(self.goal_reader, agent)
        ctx = PipelineContext(
            agent=agent,
            run_id=run_id,
            settings_snapshot=settings,
            capabilities=capabilities,
            inbox_messages=inbox_messages,
            emit=emit,
            workspace_dir=workspace_dir,
            notices=notice_sink,
            goal=goal,
        )

        messages: list[dict[str, Any]] = []
        prefix_owner = context_prefix
        if prefix_owner is None and self.prompt_provider is not None:
            # 不经 runner 的直接调用方（测试等）：按次建立 owner，单轮调用
            # 等价于初始安装；跨轮前缀稳定需要调用方持有同一个 owner 并
            # 把 install/refresh 产出的消息持久化进 history（runner 的做法）。
            begin_context = getattr(self.prompt_provider, "begin_context", None)
            if begin_context is not None:
                prefix_owner = begin_context(
                    agent=agent,
                    workspace_dir=workspace_dir,
                    tool_names=capabilities.tools,
                )
        if context_broker is not None:
            # 会话级上下文投影（Task 4）：历史来自投影而非调用方；已进入
            # 投影的 inbox 消息（重试/重启重放）按 message_id 剔除。
            history = context_broker.current_messages(agent.id)
            inbox_messages = context_broker.filter_pending_input(agent.id, inbox_messages)
        history = history or []
        # context_fresh：本轮是否处于新上下文边界（初始安装 / compact 后前缀
        # 不在 history 头部 / 无前缀 owner 时的空 history 起点）。通知批次
        # 据此在全量渲染与增量变更间切换（见 NoticeManager.collect_batch）。
        context_fresh = False
        if prefix_owner is not None:
            if prefix_owner.matches(history):
                # 前缀已安装：动态源变化只以追加消息出现在尾部。
                messages.extend(history)
                messages.extend(await prefix_owner.refresh())
            else:
                # 上下文初始化（或 compact/重试后前缀不在 history 头部）：
                # 静态协议与首份动态快照整体安装到最前。
                context_fresh = True
                messages.extend(await prefix_owner.install())
                messages.extend(history)
        else:
            context_fresh = not history
            messages.extend(history)
        # 输入消息只成形一次：请求与会话上下文投影里的条目逐字节一致
        # （message_id 是重试/重启去重锚点，随条目进投影；线缆投影由
        # adapters._to_api_message 丢弃该内部键）。
        input_user_messages = [
            {
                "role": "user",
                "content": item.get("content", ""),
                **(
                    {"message_id": str(item["message_id"])}
                    if item.get("message_id")
                    else {}
                ),
            }
            for item in inbox_messages
        ]
        messages.extend(input_user_messages)
        # Only messages that are actually entering the model context count as
        # consumed.  AgentHub-targeted mentions/replies carry a text marker.
        for item in inbox_messages:
            content = str(item.get("content") or "")
            if "AgentHub" in content or "mentioned you in AgentHub" in content or "replied to your AgentHub" in content:
                self.event_log.append(
                    "hub.notification_consumed",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={
                        "session_id": agent.id,
                        "message_id": str(item.get("message_id") or ""),
                        "post_id": str(item.get("post_id") or ""),
                        "consumed_at": __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat(),
                        "content": content[:200],
                    },
                )
        for stage in self.stages:
            await stage.before_llm(ctx, messages)
        if notice_sink is not None:
            # 通知按「未应用变更按顺序追加」消费：批次 park 为 pending，
            # 消息写进上下文投影（commit_input）后才推进消费游标。
            messages.extend(notice_sink.collect_batch(agent.id, fresh=context_fresh))

        if context_broker is not None:
            # 发送前：本轮输入（前缀安装/动态增量/inbox/通知批次）原子落进
            # 会话上下文投影并持久化；持久化失败抛 EventPersistenceError，
            # 请求不会发出（不发送未持久化的状态）。
            await context_broker.commit_input(
                agent=agent,
                run_id=run_id,
                context_prefix=prefix_owner,
                notices=notice_sink,
                user_messages=input_user_messages,
            )
        if context_broker is not None:
            await self._initial_tool_documents(agent, run_id, input_user_messages,
                context_broker, prefix_owner)
            messages = context_broker.current_messages(agent.id)
        # 投影里的媒体是稳定引用（image_ref：路径 + fallback 文本）；
        # 发送前解析为 data URL 或文本降级，投影不重嵌 base64。
        messages = await resolve_media_references(messages, vision_enabled=vision_enabled)
        estimated_prompt_tokens = await self.estimate_prompt_tokens(agent, messages)
        if prepare_context is not None:
            prepared = await prepare_context(messages, estimated_prompt_tokens)
            if prepared is not messages:
                messages = await resolve_media_references(prepared, vision_enabled=vision_enabled)
                estimated_prompt_tokens = await self.estimate_prompt_tokens(agent, messages)

        # settings 是 spawn 快照：model 未显式覆盖时为空串，真实生效值由
        # provider 侧桥接填充（LegacyLLMProvider 从 config 槽位补全）。遥测
        # 要记的是生效模型，经 provider 的可选钩子解析；无钩子的 provider
        # （测试 fake 等）原样记快照值。
        model = settings.model
        if not model:
            resolver = getattr(self.llm, "resolve_effective_settings", None)
            if resolver is not None:
                model = resolver(agent).model
        request_event = self.event_log.append(
            "llm.request_started",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"model": model},
        )
        started = time.monotonic()
        on_delta: DeltaSink | None = None
        if self.event_hub is not None:

            async def on_delta(kind: str, delta: str) -> None:
                # Transient hub-only event: never appended to the event log,
                # so it is neither replayed nor persisted.  seq 0 keeps SSE
                # client cursors anchored to real log events.
                await self.event_hub.publish(
                    EventEnvelope(
                        stream="agent",
                        project_id=agent.project_id,
                        session_id=agent.id,
                        run_id=run_id,
                        seq=0,
                        type="llm.chunk",
                        data={"kind": kind, "delta": delta},
                    )
                )

        # Open the next stream before transient chunks arrive.
        await self._publish(request_event)
        try:
            response = await self.llm.complete(agent, messages, capabilities.tools, on_delta=on_delta)
        except Exception as exc:
            self.event_log.append(
                "llm.failed",
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data={"error": str(exc), "latency_ms": int((time.monotonic() - started) * 1000)},
            )
            raise
        self.event_log.append(
            "llm.completed",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={
                "model": model,
                "usage": response.usage,
                "estimated_prompt_tokens": estimated_prompt_tokens,
                "finish_reason": response.finish_reason,
                "latency_ms": int((time.monotonic() - started) * 1000),
            },
        )
        if response.reasoning:
            await self._publish(
                self.event_log.append(
                    "agent.thinking",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={"content": response.reasoning},
                )
            )

        async def emit_text(content: str, *, reasoning: str = "") -> None:
            if not content:
                return
            if context_broker is not None:
                await context_broker.emit_assistant(
                    agent=agent, run_id=run_id, content=content, reasoning=reasoning,
                )
            else:
                await self._publish(self.event_log.append(
                    "agent.message_emitted", stream="agent", project_id=agent.project_id,
                    session_id=agent.id, run_id=run_id,
                    data={"sender": agent.role_id, "content": content},
                ))

        # Text is conversation, not proof of task completion. Commit it before
        # tools or exit audits can block/cancel the turn. The same durable event
        # updates the transcript and the context; never substitute system text.
        await emit_text(response.content, reasoning=response.reasoning if not response.tool_calls else "")

        if not response.tool_calls:
            # 无工具调用的纯文本最终回复只是结束*意向*：是否允许结束由 runner
            # 收尾前的统一结束门禁裁决（与显式 stop 同一边界，Task 4A）。
            return TurnOutcome(
                decision="stop", content=response.content, reasoning=response.reasoning
            )

        exchanges: list[tuple[ToolCall, ToolResult]] = []
        protocol = effective_invocation_protocol(agent)
        if protocol is InvocationProtocol.JAVASCRIPT and response.tool_calls:
            names = [call.name for call in response.tool_calls]
            has_direct = any(is_direct_only(name) for name in names)
            if JS_EXEC_NAME in names and has_direct:
                # Never partially execute a mixed program/control response:
                # every wire call gets matching feedback, nothing runs.
                reason = (
                    "protocol_error[mixed_program_and_controls]: a response "
                    "combining js_exec with direct controls is rejected; "
                    "issue them in separate responses"
                )
                exchanges = [(call, ToolResult(False, reason)) for call in response.tool_calls]
                return TurnOutcome(
                    decision="continue",
                    content=response.content,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
        # Do not project the assistant tool_calls here.  The runner appends the
        # assistant message and every matching tool result in one durable event
        # only after this turn returns.  Cancellation or a crash therefore
        # cannot expose a half-pair to the next provider request.
        js_programs_run = 0
        for call in response.tool_calls:
            route_error = validate_wire_route(protocol, call.name)
            if route_error is not None:
                # Misrouted calls never execute; the message is model feedback.
                exchanges.append((call, ToolResult(False, route_error)))
                continue
            if protocol is InvocationProtocol.JAVASCRIPT and call.name == JS_EXEC_NAME:
                js_programs_run += 1
                if js_programs_run > 1:
                    exchanges.append((
                        call,
                        ToolResult(
                            False,
                        "protocol_error[multiple_programs]: only one js_exec "
                        "call runs per model response; the first program was "
                        "already processed and this later program was not executed. "
                        "Repair only the unexecuted program; do not replay the first one.",
                        ),
                    ))
                    continue
                result = await self.js_runtime.execute(ctx, call)
                exchanges.append((call, result))
                control = (result.data or {}).get("control_decision")
                if control == "wait_approval":
                    error = (result.data or {}).get("error") or {}
                    return TurnOutcome(
                        decision="wait_approval",
                        content=response.content,
                        message=str(error.get("message") or ""),
                        tool_exchanges=tuple(exchanges),
                        reasoning=response.reasoning,
                    )
                continue
            # The full lifecycle (requested -> policy -> started -> raw result
            # -> post hooks -> finished) lives in the InvocationService; this
            # loop only translates outcomes into turn decisions.
            outcome = await self.invocations.invoke(ctx, call)
            if outcome.decision == "wait_approval":
                return TurnOutcome(
                    decision="wait_approval",
                    content=response.content,
                    message=outcome.error.message if outcome.error else "",
                    blocked_call=outcome.call,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
            if outcome.error is not None and outcome.error.code == "policy_blocked":
                return TurnOutcome(
                    decision="continue",
                    content=response.content,
                    message=outcome.error.message,
                    blocked_call=outcome.call,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
            result = outcome.result
            if result is None:
                # Only wait_approval returns result=None (handled above).
                continue
            exchanges.append((outcome.call, result))
            if outcome.call.name == self.stop_tool:
                # Carry a candidate answer to the runner. A tool receipt is
                # never a final answer or authorization to stop.
                final_text = str(outcome.call.arguments.get("final_answer") or response.content)
                if final_text and final_text != response.content:
                    await emit_text(final_text)
                return TurnOutcome(
                    decision="stop",
                    content=final_text,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
        return TurnOutcome(
            decision="continue",
            content=response.content,
            tool_exchanges=tuple(exchanges),
            reasoning=response.reasoning,
        )
