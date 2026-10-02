"""The single live entry point for actual tool calls (traditional and JS).

``InvocationService.invoke`` owns the whole lifecycle: durable request ->
policy stages -> executor -> durable raw result -> post hooks/artifacts ->
durable finish.  Both the traditional turn pipeline and the JS runtime's
RPC bridge await this method; nothing else may execute tools, and no tool
runs during ``apply_event``/replay.

State rules:
- Per-agent async locks serialize the full lifecycle (one active tool per
  agent); no authorization is cached while queued — settings/capabilities
  are re-derived from the live agent at actual admission (``agents``
  registry present), with the run-frozen invocation protocol retained.
- The loop-guard counter is deliberately volatile per-run shell state
  (runs never cross processes), same semantics as the old pipeline guard.
- Durable storage failures propagate as ``EventPersistenceError``: dispatch
  stops, no terminal success is fabricated, and the runner treats it as
  non-retryable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.event_writer import EventPersistenceError, EventWriter
from cloudra.runtime_v2.invocation_context import (
    InvocationScope,
    reset_invocation_scope,
    set_invocation_scope,
)
from cloudra.runtime_v2.invocation_types import (
    InvocationError,
    InvocationOutcome,
    decide_invocation,
)
from cloudra.runtime_v2.policies.base import (
    PipelineContext,
    PolicyStage,
    ToolCall,
    ToolResult,
)
from cloudra.runtime_v2.schemas import AgentSession

logger = logging.getLogger(__name__)

# Consecutive identical tool calls (same name + normalized arguments) within
# one run that trigger the loop.detected guard.
LOOP_DETECTION_THRESHOLD = 3


def register_workspace_image_artifact(
    *,
    project_id: str,
    session_id: str,
    agent_id: str | None,
    workspace_root: str,
    image_path: str,
) -> str | None:
    """Best-effort artifact registration for one workspace image (sync — offload it).

    Returns the artifact_id, or None when the path escapes the workspace, the
    file is missing, or registration fails (registration must never break the
    tool loop).  v2 agents have no legacy ``session`` row, so one is ensured
    first — ArtifactService refuses to register against a missing session.
    ``conversation_id`` is the project id, matching the v2 artifact reads.
    """
    from cloudra.persistence.artifacts import ArtifactService
    from cloudra.persistence.database import ConversationDB
    from cloudra.services import session_store

    try:
        root = Path(workspace_root).expanduser().resolve()
        source = Path(image_path).expanduser().resolve()
        if not source.is_file():
            return None
        source.relative_to(root)
    except (OSError, ValueError):
        return None
    try:
        db = ConversationDB(project_id)
        session_store.ensure_session_record(db, session_id, agent_id)
        artifact = ArtifactService().register_file(
            conversation_id=project_id,
            session_id=session_id,
            source=source,
            allowed_root=root,
        )
        return artifact.artifact_id
    except Exception:
        logger.exception("artifact registration failed for %s", image_path)
        return None


def image_paths_from_tool_result(result: ToolResult) -> list[str]:
    """Collect every injectable image path from a tool result (no cap).

    ``image_paths`` wins when it is a list; otherwise a non-empty
    ``image_path`` string is treated as a one-element list.
    """
    data = result.data if isinstance(result.data, dict) else {}
    raw = data.get("image_paths")
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, str) and p]
    path = data.get("image_path")
    if isinstance(path, str) and path:
        return [path]
    return []


def tool_result_context_content(agent: AgentSession, result: ToolResult) -> object:
    """Context content for one tool result, with image re-injection.

    A result carrying image paths gets one stable ``image_ref`` part per path
    (no base64 in the projection); resolution to data URLs happens at send
    time.  There is no N-image cap.  Shared by incremental persist and the
    runner's end-of-turn commit so both write the same payload.
    """
    from cloudra.infra.media import snapshot_image_reference

    summary = result.summary
    paths = image_paths_from_tool_result(result)
    if not paths:
        return summary
    parts: list[dict] = [{"type": "text", "text": summary or ""}]
    parts.extend(
        snapshot_image_reference(
            path,
            conv_id=agent.project_id,
            fallback=(
                f"[Image rendered at: {path} — the configured model has no "
                "vision support or the file is unavailable; inspect the "
                "file directly if needed.]"
            ),
        )
        for path in paths
    )
    return parts


def _detach_json(value: Any) -> Any:
    """Best-effort deep JSON clone for event payloads (never shares references)."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


class InvocationService:
    def __init__(
        self,
        *,
        event_writer: EventWriter,
        stages: list[PolicyStage],
        tools,
        artifact_registrar: Callable[..., str | None] = register_workspace_image_artifact,
        agents: Mapping[str, AgentSession] | None = None,
    ) -> None:
        self.event_writer = event_writer
        self.stages = list(stages)
        self.tools = tools
        self._artifact_registrar = artifact_registrar
        # Optional live-session registry.  When present, admission re-derives
        # settings/capabilities from the trusted live agent so policy changes
        # between queued calls are honored; standalone contexts (tests) pass
        # no registry and keep their explicit PipelineContext snapshot.
        self._agents = agents
        self._agent_locks: dict[str, asyncio.Lock] = {}
        # Loop guard, keyed by session id: (run_id, call signature, streak).
        self._loop_guard: dict[str, tuple[str, str, int]] = {}

    # ------------------------------------------------------------------ public

    async def invoke(
        self, ctx: PipelineContext, call: ToolCall, *, execution_id: str | None = None
    ) -> InvocationOutcome:
        lock = self._agent_locks.setdefault(ctx.agent.id, asyncio.Lock())
        async with lock:
            return await self._invoke_admitted(ctx, call, execution_id=execution_id)

    # ----------------------------------------------------------------- private

    def _refresh_context(self, ctx: PipelineContext) -> None:
        """Re-derive settings/capabilities from the live agent at admission."""
        if self._agents is None:
            return
        live = self._agents.get(ctx.agent.id)
        if live is None:
            return
        ctx.agent = live
        ctx.settings = live.settings.model_copy(deep=True)
        if live.current_run is not None:
            # The protocol is run-fixed: a mid-run settings change must not
            # leak into the refreshed snapshot.
            ctx.settings.invocation_protocol = live.current_run.invocation_protocol
        ctx.capabilities = live.capabilities

    def _track_tool_call(self, session_id: str, run_id: str, call: ToolCall) -> int:
        """Count consecutive repeats of the same call within one run."""
        signature = f"{call.name}:{json.dumps(call.arguments, sort_keys=True, default=str)}"
        last = self._loop_guard.get(session_id)
        count = last[2] + 1 if last is not None and last[:2] == (run_id, signature) else 1
        self._loop_guard[session_id] = (run_id, signature, count)
        return count

    async def _commit(self, draft: EventDraft):
        return await self.event_writer.commit(draft)

    def _draft(self, type: str, ctx: PipelineContext, data: dict[str, Any]) -> EventDraft:
        from cloudra.runtime_v2.invocation_context import current_invocation_scope

        scope = current_invocation_scope()
        if scope is not None and scope.request_event_id is not None:
            data = {**data, "request_event_id": scope.request_event_id}
        return EventDraft(type, "agent", ctx.agent.project_id, ctx.agent.id, ctx.run_id, data)

    async def _commit_finished(
        self,
        ctx: PipelineContext,
        call: ToolCall,
        *,
        execution_id: str | None,
        status: str,
        effect_state: str,
        is_success: bool,
        result_summary: str,
        duration_ms: int = 0,
        raw_result_event_id: str | None = None,
        error: InvocationError | None = None,
        artifact_id: str | None = None,
        image_paths: list[str] | None = None,
        cancelled: bool = False,
    ):
        data: dict[str, Any] = {
            "tool_call_id": call.id,
            "tool_name": call.name,
            "execution_id": execution_id,
            "status": status,
            "effect_state": effect_state,
            "is_success": is_success,
            "result_summary": result_summary,
            "duration_ms": duration_ms,
            "raw_result_event_id": raw_result_event_id,
            "error": (
                {
                    "code": error.code,
                    "message": error.message,
                    **({"stage": error.stage} if error.stage else {}),
                }
                if error
                else None
            ),
        }
        if artifact_id:
            # The frontend builds the timeline download URL from this id.
            data["artifact_id"] = artifact_id
        if image_paths:
            data["image_path"] = image_paths[0]
            data["image_paths"] = image_paths
        if cancelled:
            data["cancelled"] = True
        return await self._commit(self._draft("tool.finished", ctx, data))

    async def _invoke_admitted(
        self, ctx: PipelineContext, call: ToolCall, *, execution_id: str | None
    ) -> InvocationOutcome:
        # 1. The request is a durable fact before any policy/tool effect.
        draft, effect = decide_invocation(ctx, call, execution_id=execution_id)
        requested = await self._commit(draft)
        call = effect.call
        self._refresh_context(ctx)
        active = True

        async def report(progress):
            if not active:
                raise RuntimeError("cannot report progress after invocation ended")
            await self._commit(self._draft("tool.progress", ctx, {
                **_detach_json(progress.model_dump(mode="json")),
                "tool_call_id": call.id, "tool_name": call.name,
                "execution_id": execution_id, "request_event_id": requested.event_id,
            }))

        scope = InvocationScope(call.id, call.name, execution_id, report, requested.event_id)
        token = set_invocation_scope(scope)
        try:
            return await self._invoke_scoped(ctx, call, execution_id=execution_id)
        finally:
            active = False
            reset_invocation_scope(token)

    async def _invoke_scoped(
        self, ctx: PipelineContext, call: ToolCall, *, execution_id: str | None
    ) -> InvocationOutcome:
        agent = ctx.agent
        # 2. Policy gates, in their existing order.
        for stage in self.stages:
            policy = await stage.before_tool(ctx, call)
            if policy.outcome == "block":
                error = InvocationError("policy_blocked", policy.message, "not_started", stage.name)
                await self._commit(
                    self._draft(
                        "tool.blocked",
                        ctx,
                        {
                            "tool_call_id": call.id,
                            "tool_name": call.name,
                            "execution_id": execution_id,
                            "stage": stage.name,
                            "message": policy.message,
                        },
                    )
                )
                await self._commit_finished(
                    ctx,
                    call,
                    execution_id=execution_id,
                    status="blocked",
                    effect_state="not_started",
                    is_success=False,
                    result_summary=policy.message or "blocked by policy",
                    error=error,
                )
                return InvocationOutcome(
                    call=call,
                    result=ToolResult(False, policy.message or "blocked by policy"),
                    error=error,
                )
            if policy.outcome == "ask":
                error = InvocationError("policy_wait", policy.message, "not_started", stage.name)
                await self._commit(
                    self._draft(
                        "tool.approval_requested",
                        ctx,
                        {
                            "tool_call_id": call.id,
                            "tool_name": call.name,
                            "execution_id": execution_id,
                            "message": policy.message,
                        },
                    )
                )
                await self._commit_finished(
                    ctx,
                    call,
                    execution_id=execution_id,
                    status="waiting",
                    effect_state="not_started",
                    is_success=False,
                    result_summary=policy.message or "waiting for approval",
                    error=error,
                )
                return InvocationOutcome(call=call, result=None, decision="wait_approval", error=error)
            if policy.outcome == "warn":
                ctx.emit("agent.warning", {"code": f"{stage.name}.warn", "message": policy.message})

        # 3. Admitted: the started fact is durable before the executor runs.
        await self._commit(
            self._draft(
                "tool.started",
                ctx,
                {
                    "tool_call_id": call.id,
                    "tool_name": call.name,
                    "arguments_summary": call.arguments,
                    "execution_id": execution_id,
                },
            )
        )
        repeat = self._track_tool_call(agent.id, ctx.run_id, call)
        if repeat >= LOOP_DETECTION_THRESHOLD:
            # Soft guard: the call still executes, but the loop is audited and
            # the model is told to change approach on the next turn.
            ctx.emit("loop.detected", {"tool_name": call.name, "repeat": repeat})
            if ctx.notices is not None:
                ctx.notices.push(
                    agent.id,
                    f"[Guard] Loop detected: `{call.name}` has been called {repeat} "
                    "times in a row with identical arguments in this run. Repeating "
                    "the same call will not produce new information — change your "
                    "approach: vary the arguments, use a different tool, or report "
                    "the blocker instead of retrying.",
                )

        # 4. Execute exactly once.
        started_call = time.monotonic()
        try:
            raw = await self.tools.execute(agent, call)
        except asyncio.CancelledError:
            try:
                await self._commit_finished(
                    ctx,
                    call,
                    execution_id=execution_id,
                    status="cancelled",
                    effect_state="unknown",
                    is_success=False,
                    result_summary="interrupted: run cancelled",
                    duration_ms=int((time.monotonic() - started_call) * 1000),
                    error=InvocationError("cancelled", "run cancelled", "unknown"),
                    cancelled=True,
                )
            except EventPersistenceError:
                raise
            except Exception:
                logger.exception("failed to record tool cancellation for %s", call.id)
            raise
        except EventPersistenceError:
            raise
        except Exception as exc:
            error = InvocationError("tool_exception", str(exc), "unknown")
            await self._commit_finished(
                ctx,
                call,
                execution_id=execution_id,
                status="failed",
                effect_state="unknown",
                is_success=False,
                result_summary=f"tool crashed: {exc}",
                duration_ms=int((time.monotonic() - started_call) * 1000),
                error=error,
            )
            return InvocationOutcome(
                call=call,
                result=ToolResult(False, f"tool crashed: {exc}", error=error),
                error=error,
            )
        result = ToolResult(
            is_success=raw.is_success,
            summary=raw.summary,
            data=raw.data,
            duration_ms=int((time.monotonic() - started_call) * 1000),
            error=raw.error,
        )

        if result.error is not None:
            # The executor caught a fault and packaged it as a result: treat
            # it as a terminal unknown-effect failure, not a business result.
            await self._commit_finished(
                ctx,
                call,
                execution_id=execution_id,
                status="failed",
                effect_state=result.error.effect_state,
                is_success=False,
                result_summary=result.summary,
                duration_ms=result.duration_ms,
                error=result.error,
            )
            return InvocationOutcome(call=call, result=result, error=result.error)

        # 5. The raw result is durable before any post-processing hook sees it.
        recorded = await self._commit(
            self._draft(
                "tool.result_recorded",
                ctx,
                {
                    "tool_call_id": call.id,
                    "tool_name": call.name,
                    "execution_id": execution_id,
                    "result": {
                        "is_success": result.is_success,
                        "summary": result.summary,
                        "data": _detach_json(result.data),
                        "duration_ms": result.duration_ms,
                    },
                },
            )
        )

        # 6. Post hooks and artifact registration, exactly once.
        post_error: InvocationError | None = None
        artifact_id: str | None = None
        try:
            for stage in self.stages:
                await stage.after_tool(ctx, call, result)
            artifact_id = await self._register_tool_image(ctx, result)
        except Exception as exc:
            post_error = InvocationError("postprocessing_failed", str(exc), "completed")
            logger.exception("post-tool processing failed for %s", call.id)

        # 7. Durable terminal fact, then resolve the caller.
        image_paths = image_paths_from_tool_result(result)
        await self._commit_finished(
            ctx,
            call,
            execution_id=execution_id,
            status=("failed" if (post_error or not result.is_success) else "completed"),
            effect_state="completed",
            is_success=result.is_success,
            result_summary=result.summary,
            duration_ms=result.duration_ms,
            raw_result_event_id=recorded.event_id,
            error=post_error,
            artifact_id=artifact_id,
            image_paths=image_paths or None,
        )
        return InvocationOutcome(
            call=call,
            result=result,
            error=post_error,
            raw_result_event_id=recorded.event_id,
        )

    async def _register_tool_image(self, ctx: PipelineContext, result: ToolResult) -> str | None:
        """Register every workspace image on a successful result as an artifact.

        Returns the last registered artifact id so ``tool.finished`` can keep a
        single ``artifact_id`` slot.
        """
        if not result.is_success or not ctx.workspace_dir:
            return None
        paths = image_paths_from_tool_result(result)
        if not paths:
            return None
        workspace_root = ctx.workspace_dir
        project_id = ctx.agent.project_id
        session_id = ctx.agent.id
        agent_id = ctx.agent.role_id
        registrar = self._artifact_registrar

        def _register_all() -> str | None:
            last_id: str | None = None
            for image_path in paths:
                artifact_id = registrar(
                    project_id=project_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    workspace_root=workspace_root,
                    image_path=image_path,
                )
                if artifact_id:
                    last_id = artifact_id
            return last_id

        return await asyncio.to_thread(_register_all)
