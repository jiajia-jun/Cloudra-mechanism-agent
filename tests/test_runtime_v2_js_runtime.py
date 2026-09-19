"""JavaScriptRuntime: real-host integration over the shared invocation lifecycle.

These tests spawn the real Node/QuickJS host (no network, fake tools) and
assert the durable event trail, the ToolResponse envelope, quota/terminal
semantics, cancellation and the no-replay rule.  They skip only when the
optional host prerequisites are genuinely absent.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.event_writer import EventWriter
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.js_protocol import ProgramLimits
from cloudra.runtime_v2.js_runtime import JavaScriptRuntime
from cloudra.runtime_v2.policies.base import (
    PipelineContext,
    PolicyResult,
    ToolCall,
    ToolResult,
)
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    PermissionSet,
    RuntimeSettings,
)

HOST_DIR = Path(__file__).resolve().parent.parent / "cloudra" / "runtime_v2" / "js_host"
HOST_AVAILABLE = (
    shutil.which("node") is not None
    and (HOST_DIR / "node_modules" / "quickjs-emscripten" / "package.json").is_file()
)
SKIP_REASON = "optional JS host prerequisites missing (node >= 22 or quickjs-emscripten)"

pytestmark = pytest.mark.skipif(not HOST_AVAILABLE, reason=SKIP_REASON)


def _agent() -> AgentSession:
    return AgentSession(id="a", project_id="p", role_id="explorer", display_name="explorer")


def _ctx(agent: AgentSession, *, tools=None) -> PipelineContext:
    caps = AgentCapabilities(permissions=PermissionSet(read=True), tools=tools or ["echo"])
    return PipelineContext(
        agent=agent,
        run_id="r",
        settings_snapshot=RuntimeSettings(),
        capabilities=caps,
        inbox_messages=[],
        emit=lambda *args: None,
    )


class EchoExecutor:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []
        self.intervals: list[tuple[float, float]] = []
        self.delay = 0.0

    async def execute(self, agent, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        start = time.monotonic()
        if self.delay:
            await asyncio.sleep(self.delay)
        self.intervals.append((start, time.monotonic()))
        return ToolResult(True, "ok", {"value": call.arguments.get("value")})


def _runtime(core: RuntimeCore, *, stages=None, tools=None, limits=None):
    writer = EventWriter(core.event_log)
    service = InvocationService(
        event_writer=writer, stages=stages or [], tools=tools or EchoExecutor()
    )
    return JavaScriptRuntime(event_writer=writer, invocations=service, limits=limits)


def _events(core: RuntimeCore, type_: str) -> list:
    return [e for e in core.event_log if e.type == type_]


@pytest.mark.asyncio
async def test_dependency_chain_records_full_lifecycle():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    executor = EchoExecutor()
    runtime = _runtime(core, tools=executor)
    code = (
        "const first = await tools.echo({value: 3});\n"
        "const second = await tools.echo({value: first.data.value + 1});\n"
        "text(second.data.value);"
    )
    result = await runtime.execute(ctx, ToolCall("wire-1", "js_exec", {"code": code}))

    assert result.is_success
    assert result.data["outputs"] == [4]
    assert "JavaScript program output:" in result.summary
    assert "Output 1: 4" in result.summary
    assert result.data["error"] is None
    # Two distinct Python-assigned call ids; request order preserved.
    call_ids = [call.id for call in executor.calls]
    assert len(call_ids) == 2 and call_ids[0] != call_ids[1]
    assert executor.calls[0].arguments == {"value": 3}
    assert executor.calls[1].arguments == {"value": 4}
    # requested is durable before started for each child.
    types = [e.type for e in core.event_log]
    for call_id in call_ids:
        requested = next(i for i, e in enumerate(core.event_log)
                         if e.type == "tool.requested" and e.data["tool_call_id"] == call_id)
        started = next(i for i, e in enumerate(core.event_log)
                       if e.type == "tool.started" and e.data["tool_call_id"] == call_id)
        assert requested < started
    assert types[0] == "program.submitted"
    assert "program.started" in types[:2]
    # Original code and sha256 are captured before launch.
    submitted = _events(core, "program.submitted")[0]
    assert submitted.data["code"] == code
    assert submitted.data["outer_tool_call_id"] == "wire-1"
    import hashlib

    assert submitted.data["source_hash"] == hashlib.sha256(code.encode("utf-8")).hexdigest()
    # Children carry the execution id; the program closes completed.
    assert all(
        e.data.get("execution_id") == submitted.data["execution_id"]
        for e in core.event_log
        if e.type.startswith("tool.")
    )
    finished = _events(core, "program.finished")[0]
    assert finished.data["status"] == "completed"
    assert [c["status"] for c in finished.data["calls"]] == ["completed", "completed"]
    assert all(c["raw_result_event_id"] for c in finished.data["calls"])


@pytest.mark.asyncio
async def test_caught_tool_error_lets_program_continue():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)

    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, agent, call):
            self.calls += 1
            if call.arguments.get("fail"):
                raise RuntimeError("boom")
            return ToolResult(True, "ok", {"value": 1})

    runtime = _runtime(core, tools=Flaky())
    code = (
        "let caught = null;\n"
        "try { await tools.echo({fail: true}); } catch (e) { caught = [e.code, e.effect_state]; }\n"
        "const after = await tools.echo({});\n"
        "text([caught, after.is_success]);"
    )
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert result.is_success
    assert result.data["outputs"] == [[["tool_exception", "unknown"], True]]
    statuses = [c["status"] for c in result.data["calls"]]
    assert statuses == ["failed", "completed"]


@pytest.mark.asyncio
async def test_uncaught_error_fails_program_preserving_outputs_and_receipts():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    runtime = _runtime(core)
    code = (
        "const r = await tools.echo({value: 1});\n"
        "text(r.data.value);\n"
        "throw new Error('late boom');"
    )
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert not result.is_success
    assert result.data["outputs"] == [1]
    assert "Output 1: 1" in result.summary
    assert result.data["error"]["code"] == "guest_error"
    assert result.data["error"]["line"] == 3
    assert [c["status"] for c in result.data["calls"]] == ["completed"]
    finished = _events(core, "program.finished")[0]
    assert finished.data["status"] == "failed"


@pytest.mark.asyncio
async def test_program_summary_formats_strings_and_json_outputs():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    runtime = _runtime(core)
    result = await runtime.execute(
        ctx,
        ToolCall(
            "w",
            "js_exec",
            {"code": 'text("hello-orient-53"); text({"answer": 42, "ok": true});'},
        ),
    )

    assert result.is_success
    assert "Output 1: hello-orient-53" in result.summary
    assert 'Output 2: {"answer": 42, "ok": true}' in result.summary
    assert result.summary.index("Output 1:") < result.summary.index("Output 2:")


@pytest.mark.asyncio
async def test_business_failure_resolves_envelope_not_exception():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)

    class BusinessFail:
        async def execute(self, agent, call):
            return ToolResult(False, "no molecules found", {"hits": 0})

    runtime = _runtime(core, tools=BusinessFail())
    code = (
        "const r = await tools.echo({});\n"
        "text([r.is_success, r.summary, r.data.hits]);"
    )
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert result.is_success
    assert result.data["outputs"] == [[False, "no molecules found", 0]]
    # A normal unsuccessful business result: failed status, completed effect.
    assert [(c["status"], c["effect_state"]) for c in result.data["calls"]] == [
        ("failed", "completed")
    ]


class _BlockStage:
    name = "blocker"

    def __init__(self) -> None:
        self.checked = 0

    async def before_tool(self, ctx, call):
        self.checked += 1
        return PolicyResult.block("method not allowed by project policy")

    async def after_tool(self, ctx, call, result) -> None:
        return None

    async def before_llm(self, ctx, messages) -> None:
        return None


@pytest.mark.asyncio
async def test_policy_block_rejects_and_catching_grants_no_authority():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    stage = _BlockStage()
    executor = EchoExecutor()
    runtime = _runtime(core, stages=[stage], tools=executor)
    code = (
        "let codes = [];\n"
        "for (let i = 0; i < 2; i++) {\n"
        "  try { await tools.echo({i}); } catch (e) { codes.push([e.code, e.effect_state]); }\n"
        "}\n"
        "text(codes);"
    )
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert result.is_success  # guest caught both denials and finished cleanly
    assert result.data["outputs"] == [
        [["policy_blocked", "not_started"], ["policy_blocked", "not_started"]]
    ]
    # The executor never ran, and every attempt re-hit the policy stage.
    assert executor.calls == []
    assert stage.checked == 2
    assert all(e.type != "tool.started" for e in core.event_log)


@pytest.mark.asyncio
async def test_direct_controls_are_not_exposed_to_the_guest():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent, tools=["echo", "stop", "ask_user", "schedule"])
    runtime = _runtime(core)
    code = "text([typeof tools.echo, typeof tools.stop, typeof tools.ask_user, typeof tools.schedule]);"
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert result.is_success
    assert result.data["outputs"] == [["function", "undefined", "undefined", "undefined"]]


@pytest.mark.asyncio
async def test_promise_all_still_executes_serially():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    executor = EchoExecutor()
    executor.delay = 0.05
    runtime = _runtime(core, tools=executor)
    code = (
        "const [a, b] = await Promise.all([\n"
        "  tools.echo({value: 1}), tools.echo({value: 2}),\n"
        "]);\n"
        "text([a.data.value, b.data.value]);"
    )
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert result.is_success
    assert result.data["outputs"] == [[1, 2]]
    assert len(executor.intervals) == 2
    first, second = executor.intervals
    assert first[1] <= second[0]  # no overlap: serial backend preserved


@pytest.mark.asyncio
async def test_result_too_large_keeps_raw_event_reference():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)

    class BigResult:
        async def execute(self, agent, call):
            return ToolResult(True, "ok", {"blob": "x" * 4096})

    limits = ProgramLimits(tool_result_bytes=512)
    runtime = _runtime(core, tools=BigResult(), limits=limits)
    code = (
        "try { await tools.echo({}); }\n"
        "catch (e) { text([e.code, e.effect_state, typeof e.raw_result_event_id]); }"
    )
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert result.is_success
    code_, effect_state, has_ref = result.data["outputs"][0]
    assert (code_, effect_state) == ("result_too_large", "completed")
    assert has_ref == "string"
    receipt = result.data["calls"][0]
    assert receipt["raw_result_event_id"]
    recorded = _events(core, "tool.result_recorded")[0]
    assert recorded.event_id == receipt["raw_result_event_id"]


class _AskStage:
    name = "asker"

    async def before_tool(self, ctx, call):
        return PolicyResult.ask("needs DAG review approval")

    async def after_tool(self, ctx, call, result) -> None:
        return None

    async def before_llm(self, ctx, messages) -> None:
        return None


@pytest.mark.asyncio
async def test_wait_approval_ends_program_with_control_decision():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    runtime = _runtime(core, stages=[_AskStage()])
    code = "const r = await tools.echo({value: 1});\ntext('never reached');"
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert not result.is_success
    assert result.data["control_decision"] == "wait_approval"
    assert result.data["error"]["code"] == "policy_wait"
    assert result.data["outputs"] == []
    assert [(c["status"], c["effect_state"]) for c in result.data["calls"]] == [
        ("waiting", "not_started")
    ]
    finished = _events(core, "program.finished")[0]
    assert finished.data["control_decision"] == "wait_approval"
    assert finished.data["status"] == "failed"


@pytest.mark.asyncio
async def test_cancellation_kills_host_without_program_replay():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)

    class NeverSettles:
        def __init__(self) -> None:
            self.calls = 0
            self.entered = asyncio.Event()

        async def execute(self, agent, call):
            self.calls += 1
            self.entered.set()
            await asyncio.Event().wait()

    executor = NeverSettles()
    runtime = _runtime(core, tools=executor)
    code = "await tools.echo({value: 1});"
    task = asyncio.create_task(runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code})))
    await asyncio.wait_for(executor.entered.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert executor.calls == 1  # no replay of the interrupted call or program
    finished = _events(core, "program.finished")
    assert len(finished) == 1
    assert finished[0].data["status"] == "cancelled"
    assert [(c["status"], c["effect_state"]) for c in finished[0].data["calls"]] == [
        ("cancelled", "unknown")
    ]


@pytest.mark.asyncio
async def test_runtime_unavailable_when_node_missing():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    writer = EventWriter(core.event_log)
    service = InvocationService(event_writer=writer, stages=[], tools=EchoExecutor())
    runtime = JavaScriptRuntime(
        event_writer=writer, invocations=service, node_binary="cloudra-node-definitely-missing"
    )
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": "text(1);"}))
    assert not result.is_success
    assert result.data["error"]["code"] == "runtime_unavailable"
    # The protocol choice stands; only program facts were recorded, no start.
    assert [e.type for e in core.event_log] == ["program.submitted", "program.finished"]


@pytest.mark.asyncio
async def test_admission_validation_rejects_bad_arguments_without_events():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    runtime = _runtime(core)
    for arguments in ({}, {"code": 42}, {"code": "text(1)", "extra": 1}):
        result = await runtime.execute(ctx, ToolCall("w", "js_exec", arguments))
        assert not result.is_success
    big = {"code": "x" * (64 * 1024 + 1)}
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", big))
    assert not result.is_success
    assert "exceeds" in result.summary
    assert list(core.event_log) == []  # no program facts for invalid admissions


def _fake_host(tmp_path: Path, frames: list[dict]) -> Path:
    import json

    host = tmp_path / "fake_host.mjs"
    host.write_text(
        "import readline from 'node:readline';\n"
        "const rl = readline.createInterface({ input: process.stdin });\n"
        "console.log(JSON.stringify({ type: 'ready', version: 1 }));\n"
        "const frames = " + json.dumps(frames) + ";\n"
        "rl.on('line', (line) => {\n"
        "  if (JSON.parse(line).type === 'start') {\n"
        "    for (const out of frames) console.log(JSON.stringify(out));\n"
        "  }\n"
        "});\n"
    )
    # The prerequisite check anchors the quickjs dependency next to the host.
    dep = tmp_path / "node_modules" / "quickjs-emscripten"
    dep.mkdir(parents=True)
    (dep / "package.json").write_text('{"name": "quickjs-emscripten", "version": "0.32.0"}')
    return host


@pytest.mark.asyncio
async def test_duplicate_request_id_is_protocol_error(tmp_path):
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    executor = EchoExecutor()
    writer = EventWriter(core.event_log)
    service = InvocationService(event_writer=writer, stages=[], tools=executor)
    host = _fake_host(tmp_path, [
        {"type": "tool_call", "request_id": "r1", "name": "echo", "arguments": {}},
        {"type": "tool_call", "request_id": "r1", "name": "echo", "arguments": {}},
    ])
    runtime = JavaScriptRuntime(event_writer=writer, invocations=service, host_path=host)
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": "text(1);"}))
    assert not result.is_success
    assert result.data["error"]["code"] == "protocol_error"
    assert "duplicate request_id" in result.data["error"]["message"]
    assert len(executor.calls) == 1  # the second, duplicated request never ran


@pytest.mark.asyncio
async def test_identity_forgery_frame_is_protocol_error(tmp_path):
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    executor = EchoExecutor()
    writer = EventWriter(core.event_log)
    service = InvocationService(event_writer=writer, stages=[], tools=executor)
    host = _fake_host(tmp_path, [
        {"type": "tool_call", "request_id": "r1", "name": "echo", "arguments": {},
         "project_id": "other-project"},
    ])
    runtime = JavaScriptRuntime(event_writer=writer, invocations=service, host_path=host)
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": "text(1);"}))
    assert not result.is_success
    assert result.data["error"]["code"] == "protocol_error"
    assert executor.calls == []


@pytest.mark.asyncio
async def test_output_limit_preserves_prior_outputs():
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    limits = ProgramLimits(output_entries=2)
    runtime = _runtime(core, limits=limits)
    code = "text(1); text(2); text(3);"
    result = await runtime.execute(ctx, ToolCall("w", "js_exec", {"code": code}))
    assert not result.is_success
    assert result.data["error"]["code"] == "output_limit_exceeded"
    assert result.data["outputs"] == [1, 2]
    assert "Output 1: 1" in result.summary
    assert "Output 2: 2" in result.summary
    outputs = _events(core, "program.output")
    assert [e.data["output_index"] for e in outputs] == [0, 1]


@pytest.mark.asyncio
async def test_active_executions_registered_during_run_and_reaped():
    """停止语义契约 3/6：host 进程在执行期间登记进 active_executions，
    结束后出登记并被 reap（returncode 落位）。"""
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)

    class NeverSettles:
        def __init__(self) -> None:
            self.entered = asyncio.Event()

        async def execute(self, agent, call, **_kwargs):
            self.entered.set()
            await asyncio.Event().wait()

    executor = NeverSettles()
    runtime = _runtime(core, tools=executor)
    task = asyncio.create_task(
        runtime.execute(ctx, ToolCall("w", "js_exec", {"code": "await tools.echo({value: 1});"}))
    )
    try:
        await asyncio.wait_for(executor.entered.wait(), timeout=10)
        active = runtime.active_executions()
        assert len(active) == 1
        proc = next(iter(active.values()))
        assert proc.returncode is None
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # 取消路径终止并 reap host，且出登记。
        assert proc.returncode is not None
        assert runtime.active_executions() == {}
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.aclose()


@pytest.mark.asyncio
async def test_aclose_terminates_registered_hosts():
    """RuntimeCore 关闭路径（core.aclose -> runtime.aclose）：不取消 execute
    任务本身也能终止并 reap 全部登记 host；execute 以 host_error 失败返回。"""
    core = RuntimeCore(strict_events=True)
    agent = _agent()
    ctx = _ctx(agent)
    limits = ProgramLimits(eval_ms=60000, watchdog_ms=60000)
    runtime = _runtime(core, limits=limits)
    # 纯计算死循环：host 忙在 guest eval 里，Python 侧停在等帧上。
    task = asyncio.create_task(
        runtime.execute(ctx, ToolCall("w", "js_exec", {"code": "while (true) {}"}))
    )
    try:
        deadline = asyncio.get_running_loop().time() + 10
        while not runtime.active_executions():
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("host was never registered")
            await asyncio.sleep(0.01)
        await runtime.aclose()
        result = await asyncio.wait_for(task, timeout=10)
        assert not result.is_success
        assert result.data["error"]["code"] == "host_error"
        assert runtime.active_executions() == {}
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.aclose()


_HOST_ORPHAN_CHILD = r'''
import json
import subprocess
import sys
from pathlib import Path

host = Path(sys.argv[1])
proc = subprocess.Popen(
    ["node", "--max-old-space-size=128", str(host)],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
)
# handshake
ready = proc.stdout.readline()
start = {
    "type": "start",
    "version": 1,
    "execution_id": "orphan-probe",
    "code": "await tools.sleep({});",
    "tools": ["sleep"],
    "limits": {},
}
proc.stdin.write(json.dumps(start) + "\n")
proc.stdin.flush()
# the host asks for the tool and parks waiting for the reply on stdin
line = proc.stdout.readline()
frame = json.loads(line)
assert frame["type"] == "tool_call", frame
print(f"HOST_PID {proc.pid}", flush=True)
proc.wait()
print(f"HOST_EXITED {proc.returncode}", flush=True)
'''


@pytest.mark.asyncio
async def test_host_exits_when_parent_is_sigkilled():
    """父进程被 SIGKILL 时 finally 不会执行——JS host 的兜底自清理是
    stdin 管道 EOF（宿主在等工具回复时读到 stdin 关闭即退出）。

    本子测试：子进程驱动真实 host 并停在工具回复等待上；SIGKILL 子进程
    （finally 不执行），断言 host 在有界时间内自行退出。若 host 未退出，
    测试按 pid 精确 SIGKILL 收束，绝不留孤儿。
    """
    import os
    import signal
    import sys

    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _HOST_ORPHAN_CHILD,
        str(HOST_DIR / "host.mjs"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    host_pid: int | None = None
    try:
        line = await asyncio.wait_for(child.stdout.readline(), timeout=15)
        assert line.startswith(b"HOST_PID"), line
        host_pid = int(line.split()[1])
        os.kill(child.pid, signal.SIGKILL)  # finally in the child never runs
        await asyncio.wait_for(child.wait(), timeout=10)

        def host_gone() -> bool:
            try:
                os.kill(host_pid, 0)
            except ProcessLookupError:
                return True
            return False

        deadline = asyncio.get_running_loop().time() + 10
        while not host_gone():
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(
                    "js host survived parent SIGKILL (stdin EOF self-cleanup failed)"
                )
            await asyncio.sleep(0.05)
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
        if host_pid is not None:
            try:
                os.kill(host_pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
