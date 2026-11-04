"""Python supervisor for one bounded QuickJS guest program per js_exec call.

``JavaScriptRuntime.execute`` consumes the outer ``js_exec`` ToolCall (wire
identity included) and returns exactly one ToolResult for that exchange; it
never re-enters the turn pipeline or calls the model.  Nested ``tools.*``
requests are real tool calls through ``InvocationService`` (durable request
-> policy -> executor -> durable raw result -> post hooks -> durable
finish), so both invocation protocols share one lifecycle.

Authority rules:
- Python binds project/session/run identity to this supervisor; host frames
  cannot choose scope or mint event ids (request ids are local correlation
  keys only, actual call ids are ``new_id("tc")`` assigned here).
- ``program.submitted`` (original code + SHA-256) is durable before launch,
  ``program.started`` before the start frame, and a ToolResponse crosses the
  bridge only after the invocation's terminal event is durable.
- No automatic replay: a failed/cancelled program returns one ordinary
  failed exchange; durable-storage failures propagate as
  ``EventPersistenceError`` (the runner fails the run without retry).
- Cancellation kills only the JS host process (2s grace) and bridge
  waiters; scheduler/guard/QM jobs are never touched here.

The security boundary is QuickJS-WASM plus a killable process and a
hostile-input-checked bridge — not an OS sandbox (residual Node/engine
risk; see the spec's threat model).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import signal
import tempfile
import time
from pathlib import Path
from typing import Any

from cloudra.runtime_v2.event_writer import EventWriter
from cloudra.runtime_v2.invocation import InvocationService, image_paths_from_tool_result
from cloudra.runtime_v2.invocation_types import InvocationOutcome
from cloudra.runtime_v2.js_protocol import (
    ProgramLimits,
    ProtocolError,
    decode_host_frame,
    encode_start_frame,
    encode_tool_error_frame,
    encode_tool_result_frame,
)
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
from cloudra.runtime_v2.schemas import InvocationProtocol, new_id
from cloudra.runtime_v2.tool_catalog import guest_tool_names, validate_wire_route

logger = logging.getLogger(__name__)

_ERROR_KEYS = ("code", "message", "call_id", "tool_name", "line", "column", "effect_state", "stage")
_STDERR_CAP_BYTES = 64 * 1024


async def filter_history(expression: str, entries: list[dict]) -> list[bool]:
    """Run a predicate in a one-shot QuickJS process with no tool or output bridge."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("The history filter requires the Node/QuickJS runtime.")
    host = Path(__file__).resolve().parent / "js_host" / "predicate.mjs"
    limits = ProgramLimits(eval_ms=500)
    if len(expression.encode("utf-8", "replace")) > limits.source_bytes:
        raise ValueError("History filter exceeds its source size limit.")
    payload = json.dumps({
        "expression": expression, "entries": entries, "limits": limits.to_wire(),
    }).encode()
    try:
        proc = await asyncio.create_subprocess_exec(
            node, "--max-old-space-size=128", str(host),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env={},
        )
    except OSError as exc:
        raise RuntimeError("The history filter could not start the Node/QuickJS runtime.") from exc
    try:
        output, _ = await asyncio.wait_for(
            proc.communicate(payload), (limits.startup_timeout_ms + limits.eval_ms) / 1000,
        )
    except (TimeoutError, asyncio.CancelledError) as exc:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        await proc.wait()
        if isinstance(exc, TimeoutError):
            raise ValueError("History filter exceeded its execution budget.") from exc
        raise
    if proc.returncode:
        raise RuntimeError("The history filter requires the Node/QuickJS runtime.")
    result = json.loads(output)
    if "error" in result:
        raise ValueError(result["error"])
    return result["matches"]


def _sanitize_host_error(raw: Any) -> dict[str, Any] | None:
    """Keep only the documented error keys with coerced types (no tracebacks)."""
    if not isinstance(raw, dict):
        return None
    error: dict[str, Any] = {}
    for key in _ERROR_KEYS:
        value = raw.get(key)
        if value is None:
            continue
        if key in ("line", "column"):
            if isinstance(value, int) and value > 0:
                error[key] = value
        elif isinstance(value, str) and value:
            error[key] = value[:2000]
    if not error.get("code"):
        error["code"] = "guest_error"
    if not error.get("message"):
        error["message"] = "guest program failed"
    return error


def _envelope(outcome: InvocationOutcome, call_id: str) -> dict[str, Any]:
    """The documented ToolResponse envelope, built from a settled invocation."""
    result = outcome.result
    return {
        "call_id": call_id,
        "is_success": bool(result.is_success) if result is not None else False,
        "summary": result.summary if result is not None else "",
        "data": json.loads(json.dumps(result.data or {}, ensure_ascii=False, default=str))
        if result is not None
        else {},
        "duration_ms": result.duration_ms if result is not None else 0,
    }


def _format_program_output(value: Any) -> str:
    """Render one explicit ``text()`` value for the next model turn.

    Guest strings are already model-readable.  Every other JSON value keeps
    its structure through JSON serialization so arrays, objects, booleans and
    null are unambiguous in the plain-text tool history projection.
    """
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


def _payload_bytes(frame: dict[str, Any], line_bytes: int, key: str) -> int:
    """Measure the wire payload without changing the host's number encoding.

    Host frames use compact JSON. Replacing the payload with null yields the
    fixed string-only metadata size; any extra host whitespace or escaping
    consumes budget as well.
    """
    metadata = json.dumps({**frame, key: None}, ensure_ascii=False, separators=(",", ":"))
    return line_bytes - len(metadata.encode("utf-8", "backslashreplace")) + len(b"null")


def _summary_with_program_outputs(summary: str, outputs: list[Any]) -> str:
    """Append bounded guest output to the single JS result summary boundary."""
    if not outputs:
        return summary
    lines = [summary.rstrip(), "JavaScript program output:"]
    lines.extend(
        f"Output {index}: {_format_program_output(value)}"
        for index, value in enumerate(outputs, start=1)
    )
    return "\n".join(lines)


class JavaScriptRuntime:
    def __init__(
        self,
        *,
        event_writer: EventWriter,
        invocations: InvocationService,
        host_path: Path | None = None,
        limits: ProgramLimits | None = None,
        node_binary: str = "node",
    ) -> None:
        self.event_writer = event_writer
        self.invocations = invocations
        self.host_path = host_path or Path(__file__).resolve().parent / "js_host" / "host.mjs"
        self.limits = limits or ProgramLimits()
        self.node_binary = node_binary
        # 活动 host 登记表（execution_id -> process）：取消单个程序走 execute
        # 的 finally/_converse 取消路径；aclose（服务关闭）据此终止并 reap
        # 全部剩余 host（停止语义契约 3/6）。
        self._active: dict[str, asyncio.subprocess.Process] = {}

    def active_executions(self) -> dict[str, asyncio.subprocess.Process]:
        """当前登记在册的 host 进程快照（execution_id -> process）。"""
        return dict(self._active)

    async def aclose(self) -> None:
        """终止并 reap 全部登记 host（走既有 _terminate_process：SIGTERM →
        有界等待 → SIGKILL → reap）。只碰本 runtime 启动的 JS host，
        绝不触碰 scheduler/guard/QM 计算进程。"""
        procs = list(self._active.values())
        if not procs:
            return
        await asyncio.gather(
            *(self._terminate_process(proc) for proc in procs),
            return_exceptions=True,
        )

    async def _commit_program(self, ctx: PipelineContext, type_: str, data: dict[str, Any]):
        from cloudra.runtime_v2.effects import EventDraft

        return await self.event_writer.commit(
            EventDraft(type_, "agent", ctx.agent.project_id, ctx.agent.id, ctx.run_id, data)
        )

    async def _check_prerequisites(self) -> str | None:
        """Return an English error message when the JS host cannot run, else None."""
        install_hint = (
            "install Node >= 22 and run: npm ci --prefix cloudra/runtime_v2/js_host "
            "--ignore-scripts --no-audit --no-fund"
        )
        node = shutil.which(self.node_binary)
        if node is None:
            return f"JavaScript runtime prerequisites are unavailable; {install_hint}"
        version_out = b""
        try:
            proc = await asyncio.create_subprocess_exec(
                node, "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            version_out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            major = int(version_out.decode("utf-8", "replace").strip().lstrip("v").split(".")[0])
        except Exception:
            return f"JavaScript runtime prerequisites are unavailable; {install_hint}"
        if major < 22:
            return f"JavaScript runtime prerequisites are unavailable (Node >= 22 required); {install_hint}"
        if not self.host_path.is_file():
            return "JavaScript runtime prerequisites are unavailable (host entrypoint missing)."
        dependency = self.host_path.parent / "node_modules" / "quickjs-emscripten" / "package.json"
        if not dependency.is_file():
            return f"JavaScript runtime prerequisites are unavailable; {install_hint}"
        return None

    async def _launch(self, node: str, cwd: str) -> asyncio.subprocess.Process:
        env = {"PATH": os.environ.get("PATH", "")}
        for key in ("LANG", "LC_ALL", "LC_CTYPE", "TZ"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        return await asyncio.create_subprocess_exec(
            node,
            "--max-old-space-size=128",
            str(self.host_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
            limit=self.limits.rpc_line_bytes + 4096,
        )

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        """SIGTERM the host session, SIGKILL after the kill grace, then reap."""
        if proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                proc.terminate()
            except ProcessLookupError:
                return
        try:
            await asyncio.wait_for(proc.wait(), timeout=self.limits.kill_grace_ms / 1000)
            return
        except asyncio.TimeoutError:
            pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except ProcessLookupError:
                return
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("js host pid %s did not exit after SIGKILL", proc.pid)

    async def execute(self, ctx: PipelineContext, call: ToolCall) -> ToolResult:
        started = time.monotonic()
        # 1. Admission: the sole wire argument is the program source.
        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        code = arguments.get("code")
        if set(arguments) != {"code"} or not isinstance(code, str):
            return ToolResult(
                False,
                "js_exec requires exactly one argument: code (a JavaScript source string)",
            )
        source_bytes = code.encode("utf-8")
        if len(source_bytes) > self.limits.source_bytes:
            return ToolResult(
                False,
                f"program source of {len(source_bytes)} bytes exceeds the "
                f"{self.limits.source_bytes} byte limit",
            )

        execution_id = new_id("exec")
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        base = {"execution_id": execution_id, "outer_tool_call_id": call.id}

        # 2. The program fact is durable before any launch side effect.
        await self._commit_program(
            ctx, "program.submitted", {**base, "code": code, "source_hash": source_hash}
        )

        async def finish(status, error, receipts, control_decision=None):
            data = {
                **base,
                "status": status,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "error": error,
                "calls": receipts,
            }
            if control_decision is not None:
                data["control_decision"] = control_decision
            await self._commit_program(ctx, "program.finished", data)

        # 3. Prerequisites: no fallback and no unsafe evaluation when missing.
        problem = await self._check_prerequisites()
        if problem is not None:
            error = {"code": "runtime_unavailable", "message": problem}
            await finish("failed", error, [])
            return ToolResult(
                False,
                f"JavaScript runtime unavailable: {problem}",
                {"execution_id": execution_id, "status": "failed", "error": error,
                 "outputs": [], "calls": []},
            )
        node = shutil.which(self.node_binary) or self.node_binary

        outputs: list[Any] = []
        receipts: list[dict[str, Any]] = []
        child_images: list[str] = []
        tmpdir = tempfile.TemporaryDirectory(prefix="cloudra-js-")
        proc = await self._launch(node, tmpdir.name)
        self._active[execution_id] = proc
        stderr_tail: list[bytes] = []

        async def _drain_stderr() -> None:
            try:
                while True:
                    chunk = await proc.stderr.readline()
                    if not chunk:
                        return
                    if sum(len(c) for c in stderr_tail) < _STDERR_CAP_BYTES:
                        stderr_tail.append(chunk)
            except Exception:
                return

        stderr_task = asyncio.create_task(_drain_stderr())
        try:
            return await self._converse(
                ctx, proc,
                execution_id=execution_id, code=code, base=base,
                outputs=outputs, receipts=receipts, child_images=child_images,
                finish=finish, stderr_tail=stderr_tail,
            )
        finally:
            await self._terminate_process(proc)
            self._active.pop(execution_id, None)
            stderr_task.cancel()
            try:
                await stderr_task
            except (asyncio.CancelledError, Exception):
                pass
            tmpdir.cleanup()

    async def _read_frame(self, proc, timeout_s: float) -> tuple[dict[str, Any], int]:
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_s)
        except ValueError as exc:
            # StreamReader rejects extreme lines before the JSON decoder runs.
            raise ProtocolError(
                f"bridge frame exceeds rpc_line_bytes {self.limits.rpc_line_bytes}"
            ) from exc
        if not line:
            raise _HostDied("host closed stdout without a finished frame")
        line = line.rstrip(b"\n")
        return decode_host_frame(line, limits=self.limits), len(line)

    async def _send(self, proc, payload: bytes) -> None:
        try:
            proc.stdin.write(payload + b"\n")
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise _HostDied("host stdin is closed") from exc

    async def _converse(
        self, ctx, proc, *, execution_id, code, base, outputs, receipts,
        child_images, finish, stderr_tail,
    ) -> ToolResult:
        document_sources = []
        limits = self.limits
        guest_names = set(
            guest_tool_names(
                ctx.capabilities.tools,
                visual_mode=ctx.settings.visual_mode,
                orchestration_mode=ctx.settings.orchestration_mode,
                role_id=ctx.agent.role_id,
            )
        )
        watchdog_s = limits.watchdog_ms / 1000
        program_error: dict[str, Any] | None = None
        program_status = "failed"
        control_decision: str | None = None
        outstanding: dict[str, dict[str, Any]] = {}  # request_id -> receipt (unreplied)
        seen_request_ids: set[str] = set()
        active_receipt: dict[str, Any] | None = None  # in-flight invocation

        def stderr_note() -> str:
            tail = b"".join(stderr_tail).decode("utf-8", "replace").strip()
            return f" ({tail[-300:]})" if tail else ""

        try:
            # 4. Handshake, then durable program.started, then the start frame.
            try:
                ready, _ = await self._read_frame(proc, limits.startup_timeout_ms / 1000)
            except asyncio.TimeoutError as exc:
                raise _HostDied("host startup handshake timed out") from exc
            if ready.get("type") != "ready":
                raise ProtocolError(f"first host frame must be ready, got {ready.get('type')!r}")
            await self._commit_program(ctx, "program.started", dict(base))
            await self._send(
                proc, encode_start_frame(execution_id, code, sorted(guest_names), limits=limits)
            )

            output_index = 0
            output_bytes = 0
            while program_error is None:
                try:
                    frame, line_bytes = await self._read_frame(proc, watchdog_s)
                except asyncio.TimeoutError:
                    program_error = {
                        "code": "watchdog_timeout",
                        "message": f"host produced no frame for {limits.watchdog_ms} ms "
                        "with no tool outstanding",
                    }
                    break
                type_ = frame["type"]
                if type_ == "output":
                    next_bytes = output_bytes + _payload_bytes(frame, line_bytes, "value")
                    if output_index >= limits.output_entries or next_bytes > limits.output_bytes:
                        program_error = {
                            "code": "output_limit_exceeded",
                            "message": f"program output exceeds the {limits.output_entries} "
                            f"entries / {limits.output_bytes} bytes budget",
                        }
                        break
                    await self._commit_program(
                        ctx, "program.output",
                        {**base, "output_index": output_index, "value": frame["value"]},
                    )
                    output_index += 1
                    output_bytes = next_bytes
                    outputs.append(json.loads(json.dumps(frame["value"], default=str)))
                    continue
                if type_ == "finished":
                    program_status = frame["status"]
                    program_error = _sanitize_host_error(frame.get("error"))
                    if program_status == "completed":
                        program_error = None
                    break
                if type_ != "tool_call":
                    program_error = {
                        "code": "protocol_error",
                        "message": f"unexpected host frame type {type_!r}",
                    }
                    break

                # 5. One tool request: validate, then the full invocation lifecycle.
                request_id = frame["request_id"]
                if request_id in seen_request_ids:
                    program_error = {
                        "code": "protocol_error",
                        "message": f"duplicate request_id {request_id!r}",
                    }
                    break
                seen_request_ids.add(request_id)
                if len(seen_request_ids) > limits.tool_requests:
                    program_error = {
                        "code": "tool_request_limit_exceeded",
                        "message": f"program exceeded the {limits.tool_requests} tool request budget",
                    }
                    break
                if _payload_bytes(frame, line_bytes, "arguments") > limits.argument_bytes:
                    program_error = {
                        "code": "argument_too_large",
                        "message": f"tool call arguments exceed argument_bytes {limits.argument_bytes}",
                    }
                    break
                name = frame["name"]
                tc_id = new_id("tc")
                receipt: dict[str, Any] = {
                    "call_id": tc_id, "tool_name": name, "status": "queued",
                    "effect_state": "not_started", "raw_result_event_id": None,
                }
                receipts.append(receipt)
                outstanding[request_id] = receipt

                route_error = validate_wire_route(
                    InvocationProtocol.JAVASCRIPT, name, origin="guest"
                ) or (
                    None if name in guest_names else
                    f"protocol_error[unknown_guest_tool]: {name!r} was not "
                    "announced to this program"
                )
                if route_error is not None:
                    receipt.update(status="blocked", effect_state="not_started")
                    outstanding.pop(request_id, None)
                    await self._send(proc, encode_tool_error_frame(request_id, {
                        "code": "protocol_error", "message": route_error,
                        "call_id": tc_id, "tool_name": name, "effect_state": "not_started",
                    }))
                    continue

                active_receipt = receipt
                outcome = await self.invocations.invoke(
                    ctx, ToolCall(tc_id, name, frame["arguments"]), execution_id=execution_id
                )
                active_receipt = None
                outstanding.pop(request_id, None)
                if outcome.result is not None:
                    child_images.extend(image_paths_from_tool_result(outcome.result))
                    if name == 'get_tool_docs' and outcome.result.is_success:
                        document_sources.extend((outcome.result.data or {}).get('documents', []))
                _apply_outcome(receipt, outcome)

                if outcome.decision == "wait_approval":
                    # The JS heap cannot pause across an approval: end the
                    # program with a terminal policy_wait; the run waits and a
                    # later turn may rerun a repaired program (no auto rerun).
                    control_decision = "wait_approval"
                    program_error = {
                        "code": "policy_wait",
                        "message": outcome.error.message if outcome.error else "waiting for approval",
                        "call_id": tc_id,
                        "tool_name": name,
                        "effect_state": "not_started",
                        **({"stage": outcome.error.stage}
                           if outcome.error and outcome.error.stage else {}),
                    }
                    break

                if outcome.error is not None:
                    error_payload = {
                        "code": outcome.error.code,
                        "message": outcome.error.message,
                        "call_id": tc_id,
                        "tool_name": name,
                        "effect_state": outcome.error.effect_state,
                        **({"stage": outcome.error.stage} if outcome.error.stage else {}),
                    }
                    await self._send(proc, encode_tool_error_frame(request_id, error_payload))
                    continue
                try:
                    await self._send(
                        proc, encode_tool_result_frame(
                            request_id, _envelope(outcome, tc_id), limits=limits
                        )
                    )
                except ProtocolError:
                    await self._send(proc, encode_tool_error_frame(request_id, {
                        "code": "result_too_large",
                        "message": f"tool result data exceeds the {limits.tool_result_bytes} "
                        "byte bridge limit; the raw result stays in its "
                        "tool.result_recorded event",
                        "call_id": tc_id,
                        "tool_name": name,
                        "effect_state": "completed",
                        "raw_result_event_id": outcome.raw_result_event_id,
                    }))
        except _HostDied as exc:
            program_error = {"code": "host_error", "message": f"{exc}{stderr_note()}"}
        except ProtocolError as exc:
            program_error = {"code": "protocol_error", "message": str(exc)[:2000]}
        except asyncio.CancelledError:
            for receipt in outstanding.values():
                receipt.update(status="cancelled", effect_state="not_started")
            if active_receipt is not None:
                # The in-flight tool may have run; its effect is unknown.
                active_receipt.update(status="cancelled", effect_state="unknown")
            await self._terminate_process(proc)
            await finish("cancelled", {"code": "cancelled", "message": "run cancelled"}, receipts)
            raise

        # 6. Close every accepted child, then the program (single finished fact).
        for receipt in outstanding.values():
            receipt.update(status="cancelled", effect_state="not_started")
        outstanding.clear()
        await finish(
            "failed" if program_error is not None else program_status,
            program_error, receipts,
            control_decision=control_decision,
        )

        failed_children = sum(1 for r in receipts if r["status"] != "completed")
        final_status = "failed" if program_error is not None else program_status
        summary = (
            f"JavaScript program {final_status}: "
            f"{len(outputs)} output(s), {len(receipts)} tool call(s)"
            + (f" ({failed_children} not completed)" if failed_children else "")
            + (f"; error: {program_error['message']}" if program_error else "")
        )
        summary_prefix = summary
        summary = _summary_with_program_outputs(summary, outputs)
        data: dict[str, Any] = {
            "execution_id": execution_id,
            "status": final_status,
            "outputs": outputs,
            "calls": receipts,
            "error": program_error,
        }
        if document_sources:
            data['tool_documents'] = [
                {'name': doc['name'], 'revision': doc['revision']} for doc in document_sources
            ]
            from cloudra.tools.documentation import compact_document_outputs
            compact_outputs = compact_document_outputs(outputs, document_sources)
            # Even transformed documents may share output with evidence. An
            # unchanged alternative preserves that output instead of allowing
            # the document tag to collapse the complete mixed tool message.
            data['tool_document_compact_content'] = _summary_with_program_outputs(summary_prefix, compact_outputs)
        if child_images:
            data["image_paths"] = child_images
        if control_decision is not None:
            data["control_decision"] = control_decision
        return ToolResult(
            program_error is None and program_status == "completed", summary, data
        )


class _HostDied(Exception):
    """The host process ended the conversation without a finished frame."""


def _apply_outcome(receipt: dict[str, Any], outcome: InvocationOutcome) -> None:
    """Project a settled invocation onto its child receipt."""
    if outcome.decision == "wait_approval":
        receipt.update(status="waiting", effect_state="not_started")
        return
    error = outcome.error
    if error is not None:
        status = "blocked" if error.code == "policy_blocked" else "failed"
        receipt.update(
            status=status,
            effect_state=error.effect_state,
            raw_result_event_id=outcome.raw_result_event_id,
        )
        return
    result = outcome.result
    receipt.update(
        status="completed" if (result is not None and result.is_success) else "failed",
        effect_state="completed",
        raw_result_event_id=outcome.raw_result_event_id,
    )
