"""Python-side bridge protocol validation (js_protocol) — bounded JSON frames."""

from __future__ import annotations

import json

import pytest

from cloudra.runtime_v2.js_protocol import (
    MAX_REQUEST_ID_LENGTH,
    ProgramLimits,
    ProtocolError,
    decode_host_frame,
    encode_start_frame,
    encode_tool_error_frame,
    encode_tool_result_frame,
)


def _line(frame: dict) -> bytes:
    return json.dumps(frame).encode("utf-8")


# --------------------------------------------------------------------- limits


def test_start_frame_sends_guest_limits_only() -> None:
    limits = ProgramLimits(source_bytes=128, eval_ms=50)
    wire = json.loads(encode_start_frame("exec-1", "text(1)", [], limits=limits))["limits"]
    assert wire["source_bytes"] == 128
    assert wire["eval_ms"] == 50
    # startup/watchdog/kill-grace are Python-side only, never sent to the host
    assert "startup_timeout_ms" not in wire
    assert "watchdog_ms" not in wire
    assert "kill_grace_ms" not in wire


# -------------------------------------------------------------- host decoding


def test_decode_ready_ok() -> None:
    frame = decode_host_frame(_line({"type": "ready", "version": 1}))
    assert frame["type"] == "ready"


@pytest.mark.parametrize("version", [True, 1.0, "1", None, [], {}])
def test_decode_ready_rejects_non_integer_version(version) -> None:
    with pytest.raises(ProtocolError, match="version"):
        decode_host_frame(_line({"type": "ready", "version": version}))


def test_decode_tool_call_ok() -> None:
    frame = decode_host_frame(
        _line({"type": "tool_call", "request_id": "r1", "name": "echo", "arguments": {"a": 1}})
    )
    assert frame["arguments"] == {"a": 1}


def test_decode_finished_requires_known_status() -> None:
    for status in ("completed", "failed", "cancelled", "interrupted"):
        decode_host_frame(_line({"type": "finished", "status": status, "error": None}))
    with pytest.raises(ProtocolError, match="status"):
        decode_host_frame(_line({"type": "finished", "status": "maybe", "error": None}))


@pytest.mark.parametrize("status", [None, 1, True, [], {}])
def test_decode_finished_rejects_non_string_status(status) -> None:
    with pytest.raises(ProtocolError, match="status"):
        decode_host_frame(_line({"type": "finished", "status": status}))


def test_decode_rejects_unknown_type() -> None:
    with pytest.raises(ProtocolError, match="unknown host frame type"):
        decode_host_frame(_line({"type": "hack", "version": 1}))


def test_decode_rejects_identity_claims_and_unexpected_fields() -> None:
    with pytest.raises(ProtocolError, match="unexpected fields"):
        decode_host_frame(_line({"type": "ready", "version": 1, "project_id": "p"}))
    with pytest.raises(ProtocolError, match="unexpected fields"):
        decode_host_frame(
            _line(
                {
                    "type": "tool_call",
                    "request_id": "r1",
                    "name": "echo",
                    "arguments": {},
                    "run_id": "r",
                }
            )
        )


def test_decode_rejects_missing_fields() -> None:
    with pytest.raises(ProtocolError, match="missing fields"):
        decode_host_frame(_line({"type": "tool_call", "request_id": "r1", "name": "echo"}))


def test_decode_rejects_bad_request_id() -> None:
    with pytest.raises(ProtocolError, match="request_id"):
        decode_host_frame(
            _line({"type": "tool_call", "request_id": "", "name": "echo", "arguments": {}})
        )
    with pytest.raises(ProtocolError, match="request_id"):
        decode_host_frame(
            _line(
                {
                    "type": "tool_call",
                    "request_id": "x" * (MAX_REQUEST_ID_LENGTH + 1),
                    "name": "echo",
                    "arguments": {},
                }
            )
        )


def test_decode_rejects_non_finite_numbers() -> None:
    with pytest.raises(ProtocolError, match="non-finite"):
        decode_host_frame(b'{"type": "output", "value": NaN}')
    with pytest.raises(ProtocolError, match="non-finite"):
        decode_host_frame(b'{"type": "output", "value": Infinity}')


@pytest.mark.parametrize("value", [b"1e309", b"-1e309"])
def test_decode_rejects_float_overflow(value) -> None:
    with pytest.raises(ProtocolError, match="non-finite"):
        decode_host_frame(b'{"type": "output", "value": ' + value + b'}')


def test_decode_rejects_parser_recursion_as_protocol_error() -> None:
    value = b"[" * 2000 + b"0" + b"]" * 2000
    with pytest.raises(ProtocolError, match="depth"):
        decode_host_frame(b'{"type": "output", "value": ' + value + b'}')


def test_decode_rejects_duplicate_keys() -> None:
    with pytest.raises(ProtocolError, match="duplicate object key"):
        decode_host_frame(b'{"type": "output", "value": 1, "value": 2}')


def test_decode_rejects_deep_nesting() -> None:
    nested: list = []
    current = nested
    for _ in range(70):
        child: list = []
        current.append(child)
        current = child
    with pytest.raises(ProtocolError, match="depth"):
        decode_host_frame(_line({"type": "output", "value": nested}))


def test_decode_rejects_oversized_and_non_utf8_lines() -> None:
    limits = ProgramLimits(rpc_line_bytes=64)
    with pytest.raises(ProtocolError, match="rpc_line_bytes"):
        decode_host_frame(b"x" * 65, limits=limits)
    with pytest.raises(ProtocolError, match="UTF-8"):
        decode_host_frame(b'{"type": "output", "value": "\xff"}')


def test_decode_rejects_non_object_and_bad_json() -> None:
    with pytest.raises(ProtocolError, match="JSON object"):
        decode_host_frame(b"[1, 2]")
    with pytest.raises(ProtocolError, match="not valid JSON"):
        decode_host_frame(b"{nope")


def test_decode_arguments_may_carry_dunder_proto_key() -> None:
    # Business payloads are cloned as data; __proto__ is an ordinary key here.
    frame = decode_host_frame(
        _line(
            {
                "type": "tool_call",
                "request_id": "r1",
                "name": "echo",
                "arguments": {"__proto__": {"polluted": True}},
            }
        )
    )
    assert frame["arguments"]["__proto__"] == {"polluted": True}


# ------------------------------------------------------------- start encoding


def test_encode_start_frame_includes_identity_and_tools() -> None:
    line = encode_start_frame("exec-1", "text(1)", ["echo"])
    frame = json.loads(line)
    assert frame["type"] == "start"
    assert frame["version"] == 1
    assert frame["execution_id"] == "exec-1"
    assert frame["tools"] == ["echo"]
    assert isinstance(frame["limits"], dict)


# ------------------------------------------------------------------- encoding


def test_encode_start_enforces_source_cap() -> None:
    limits = ProgramLimits(source_bytes=8)
    with pytest.raises(ProtocolError, match="source_bytes"):
        encode_start_frame("e", "x" * 9, [], limits=limits)


def test_encode_tool_result_round_trip_and_data_cap() -> None:
    result = {
        "call_id": "tc1",
        "is_success": True,
        "summary": "ok",
        "data": {"v": 1},
        "duration_ms": 3,
    }
    frame = json.loads(encode_tool_result_frame("r1", result))
    assert frame["type"] == "tool_result"
    assert frame["request_id"] == "r1"
    assert frame["result"]["data"] == {"v": 1}

    limits = ProgramLimits(tool_result_bytes=16)
    big = {"data": {"blob": "x" * 64}}
    with pytest.raises(ProtocolError, match="tool_result_bytes"):
        encode_tool_result_frame("r1", big, limits=limits)


def test_encode_tool_error_round_trip() -> None:
    frame = json.loads(
        encode_tool_error_frame("r2", {"code": "policy_blocked", "message": "no"})
    )
    assert frame["type"] == "tool_error"
    assert frame["error"]["code"] == "policy_blocked"


def test_encode_rejects_non_finite_values() -> None:
    with pytest.raises((ProtocolError, ValueError)):
        encode_tool_result_frame("r1", {"data": {"x": float("nan")}})


def test_encode_frames_are_single_lines() -> None:
    line = encode_start_frame("e", "text(1)", ["a", "b"])
    assert b"\n" not in line
    line = encode_tool_error_frame("r1", {"code": "x", "message": "m"})
    assert b"\n" not in line
