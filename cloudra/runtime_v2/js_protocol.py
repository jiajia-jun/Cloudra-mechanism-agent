"""Bounded JSON bridge protocol between Python and the QuickJS host (version 1).

Wire shape (one bounded JSON object per line, stdin/stdout):
- Python -> host: ``{type:"start",version:1,execution_id,code,tools,limits}``,
  ``{type:"tool_result",request_id,result}``, ``{type:"tool_error",request_id,error}``
- host -> Python: ``{type:"ready",version:1}``, ``{type:"tool_call",request_id,name,arguments}``,
  ``{type:"output",value}``, exactly one ``{type:"finished",status,error?}``

All limits are code constants (injectable smaller values in tests), never
user-editable LLM arguments.  Both sides validate frames independently; this
module is the Python-side validator/encoder and holds the shared constants.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1
MAX_REQUEST_ID_LENGTH = 128
MAX_JSON_DEPTH = 64

FINISHED_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})


class ProtocolError(ValueError):
    """A bridge frame violated the protocol (size, shape, identity, order)."""


@dataclass(frozen=True)
class ProgramLimits:
    """Fixed first-release engineering limits (not scientific thresholds)."""

    source_bytes: int = 64 * 1024  # program source, UTF-8
    argument_bytes: int = 64 * 1024  # one tool call's serialized arguments
    rpc_line_bytes: int = 2 * 1024 * 1024  # one bridge frame line
    tool_result_bytes: int = 1024 * 1024  # result data delivered into the guest
    output_bytes: int = 64 * 1024  # cumulative explicit program output
    output_entries: int = 256  # cumulative output events
    tool_requests: int = 64  # total tool requests per program
    pending_requests: int = 16  # concurrently outstanding tool requests
    heap_bytes: int = 64 * 1024 * 1024  # QuickJS heap
    stack_bytes: int = 512 * 1024  # QuickJS stack
    eval_ms: int = 5000  # cumulative active guest-evaluation wall time
    startup_timeout_ms: int = 10000  # host boot + handshake
    watchdog_ms: int = 15000  # stale host with no tool outstanding
    kill_grace_ms: int = 2000  # SIGTERM -> SIGKILL grace

    def to_wire(self) -> dict[str, Any]:
        """snake_case JSON payload for the start frame."""
        return {
            "source_bytes": self.source_bytes,
            "argument_bytes": self.argument_bytes,
            "rpc_line_bytes": self.rpc_line_bytes,
            "tool_result_bytes": self.tool_result_bytes,
            "output_bytes": self.output_bytes,
            "output_entries": self.output_entries,
            "tool_requests": self.tool_requests,
            "pending_requests": self.pending_requests,
            "heap_bytes": self.heap_bytes,
            "stack_bytes": self.stack_bytes,
            "eval_ms": self.eval_ms,
        }

# --------------------------------------------------------------- frame decoding


def _reject_constant(value: str) -> None:
    raise ProtocolError(f"non-finite number {value!r} is not valid bridge JSON")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        _reject_constant(value)
    return number


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ProtocolError(f"duplicate object key {key!r} in bridge frame")
        obj[key] = value
    return obj


def _check_depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ProtocolError(f"bridge frame exceeds maximum JSON depth {MAX_JSON_DEPTH}")
    if isinstance(value, dict):
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)


def _parse_line(line: bytes, *, limits: ProgramLimits) -> dict[str, Any]:
    if len(line) > limits.rpc_line_bytes:
        raise ProtocolError(
            f"bridge frame of {len(line)} bytes exceeds rpc_line_bytes {limits.rpc_line_bytes}"
        )
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError("bridge frame is not valid UTF-8") from exc
    try:
        frame = json.loads(
            text,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            object_pairs_hook=_no_duplicate_keys,
        )
    except ProtocolError:
        raise
    except RecursionError as exc:
        raise ProtocolError(f"bridge frame exceeds maximum JSON depth {MAX_JSON_DEPTH}") from exc
    except ValueError as exc:
        raise ProtocolError(f"bridge frame is not valid JSON: {exc}") from exc
    if not isinstance(frame, dict):
        raise ProtocolError("bridge frame must be a JSON object")
    _check_depth(frame)
    return frame


def _require_fields(
    frame: dict[str, Any],
    type_: str,
    fields: tuple[str, ...],
    required: tuple[str, ...] | None = None,
) -> None:
    unexpected = set(frame) - {"type", *fields}
    # Identity claims are never guest-selectable: any field outside the fixed
    # per-type set (including project/session/run/execution ids) is rejected.
    if unexpected:
        raise ProtocolError(
            f"{type_} frame carries unexpected fields {sorted(unexpected)}"
        )
    missing = [field for field in (required or fields) if field not in frame]
    if missing:
        raise ProtocolError(f"{type_} frame is missing fields {missing}")


def _require_request_id(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_REQUEST_ID_LENGTH:
        raise ProtocolError(
            f"request_id must be a string of 1..{MAX_REQUEST_ID_LENGTH} characters"
        )
    return value


def decode_host_frame(line: bytes, *, limits: ProgramLimits = ProgramLimits()) -> dict[str, Any]:
    """Validate one host -> Python frame; returns the checked frame dict."""
    frame = _parse_line(line, limits=limits)
    type_ = frame.get("type")
    if not isinstance(type_, str):
        raise ProtocolError("bridge frame has no string type")
    if type_ == "ready":
        _require_fields(frame, type_, ("version",))
        if type(frame["version"]) is not int or frame["version"] != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol version {frame['version']!r}")
    elif type_ == "tool_call":
        _require_fields(frame, type_, ("request_id", "name", "arguments"))
        _require_request_id(frame["request_id"])
        if not isinstance(frame["name"], str) or not frame["name"]:
            raise ProtocolError("tool_call frame name must be a non-empty string")
        if not isinstance(frame["arguments"], dict):
            raise ProtocolError("tool_call frame arguments must be a JSON object")
    elif type_ == "output":
        _require_fields(frame, type_, ("value",))
    elif type_ == "finished":
        _require_fields(frame, type_, ("status", "error"), required=("status",))
        if not isinstance(frame["status"], str) or frame["status"] not in FINISHED_STATUSES:
            raise ProtocolError(f"unknown finished status {frame['status']!r}")
        if frame.get("error") is not None and not isinstance(frame["error"], dict):
            raise ProtocolError("finished frame error must be an object or null")
    else:
        raise ProtocolError(f"unknown host frame type {type_!r}")
    return frame


# --------------------------------------------------------------- frame encoding


def _encode(frame: dict[str, Any], *, limits: ProgramLimits) -> bytes:
    line = json.dumps(frame, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(line) > limits.rpc_line_bytes:
        raise ProtocolError(
            f"outgoing frame of {len(line)} bytes exceeds rpc_line_bytes {limits.rpc_line_bytes}"
        )
    return line


def encode_start_frame(
    execution_id: str,
    code: str,
    tools: list[str],
    *,
    limits: ProgramLimits = ProgramLimits(),
) -> bytes:
    if len(code.encode("utf-8")) > limits.source_bytes:
        raise ProtocolError("program source exceeds source_bytes limit")
    return _encode(
        {
            "type": "start",
            "version": PROTOCOL_VERSION,
            "execution_id": execution_id,
            "code": code,
            "tools": list(tools),
            "limits": limits.to_wire(),
        },
        limits=limits,
    )


def encode_tool_result_frame(
    request_id: str, result: dict[str, Any], *, limits: ProgramLimits = ProgramLimits()
) -> bytes:
    """The documented ToolResponse envelope, JSON-cloned into the guest."""
    data_size = len(
        json.dumps(result.get("data"), ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")
    )
    if data_size > limits.tool_result_bytes:
        raise ProtocolError(
            f"tool result data of {data_size} bytes exceeds tool_result_bytes {limits.tool_result_bytes}"
        )
    return _encode({"type": "tool_result", "request_id": request_id, "result": result}, limits=limits)


def encode_tool_error_frame(
    request_id: str, error: dict[str, Any], *, limits: ProgramLimits = ProgramLimits()
) -> bytes:
    return _encode({"type": "tool_error", "request_id": request_id, "error": error}, limits=limits)
