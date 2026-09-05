"""Integration acceptance: both invocation protocols share one lifecycle.

The same fake business operation runs through the traditional wire (direct
top-level tool call) and the JavaScript wire (one ``js_exec`` program whose
nested ``tools.*`` call performs the operation), against a real
``InvocationService`` with the real ``default_stages`` policy chain.  Both
paths must produce identical admission decisions and identical durable
raw-result facts; the JS path adds only the program.* wrapper events.

Node-dependent cases skip only when the optional host prerequisites are
genuinely absent; everything else (including the traditional mode) runs
without Node or the host dependencies installed.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.event_writer import EventWriter
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.js_runtime import JavaScriptRuntime
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    InvocationProtocol,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST_DIR = REPO_ROOT / "cloudra" / "runtime_v2" / "js_host"
HOST_AVAILABLE = (
    shutil.which("node") is not None
    and (HOST_DIR / "node_modules" / "quickjs-emscripten" / "package.json").is_file()
)
JS_REASON = "optional JS host prerequisites missing (node >= 22 or quickjs-emscripten)"

_METHOD_POLICY = {
    "allowed_methods": ["mace-omol25", "xtb"],
    "intercept_layers": ["bash", "submit_compute_job", "qm_input_writer"],
}
_B3LYP_GJF = "#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\n"

_MODES = [
    pytest.param("traditional", id="traditional"),
    pytest.param(
        "javascript",
        id="javascript",
        marks=pytest.mark.skipif(not HOST_AVAILABLE, reason=JS_REASON),
    ),
]


class _FakeLLM:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response

    async def complete(self, agent, messages, tools, **_kwargs):
        return self.response


class _RecordingTools:
    """Fake executor: the business op doubles ``value``; no other side effect."""

    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    async def execute(self, agent, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        if call.name == "echo_business":
            return ToolResult(True, "ok", {"value": call.arguments["value"] * 2})
        return ToolResult(True, "ok", {})


async def _spawn(core: RuntimeCore, tmp_path, *, settings=None, protocol=InvocationProtocol.TRADITIONAL):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    payload: dict = {"name": "p", "workspace_dir": str(tmp_path)}
    if settings:
        payload["settings"] = settings
    await CommandBus(core).execute(Command(type="project.create", payload=payload))
    project = next(iter(core.projects.values()))
    await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    agent = next(iter(core.agents.values()))
    agent.settings.invocation_protocol = protocol
    return agent


async def _run_turn(core: RuntimeCore, agent, tmp_path, response, tools, *, tool_names, run_id="run_acc"):
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=_FakeLLM(response),
        tools=tools,
    )
    return await pipeline.run_turn(
        agent=agent,
        run_id=run_id,
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=tool_names),
        inbox_messages=[{"content": "go"}],
        workspace_dir=str(tmp_path),
    )


def _ctx(agent, tmp_path, *, tool_names) -> PipelineContext:
    return PipelineContext(
        agent=agent,
        run_id="run_direct",
        settings_snapshot=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=tool_names),
        inbox_messages=[],
        emit=lambda *args: None,
        workspace_dir=str(tmp_path),
    )


def _protocol(mode: str) -> InvocationProtocol:
    return InvocationProtocol.TRADITIONAL if mode == "traditional" else InvocationProtocol.JAVASCRIPT


def _events(core: RuntimeCore, type_: str, tool_name: str | None = None) -> list:
    return [
        e
        for e in core.event_log
        if e.type == type_ and (tool_name is None or e.data.get("tool_name") == tool_name)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_same_business_operation_behaves_identically(mode: str, tmp_path):
    core = RuntimeCore(strict_events=True)
    agent = await _spawn(core, tmp_path, protocol=_protocol(mode))
    tools = _RecordingTools()
    if mode == "traditional":
        wire = ToolCall("t1", "echo_business", {"value": 21})
    else:
        wire = ToolCall(
            "w1",
            "js_exec",
            {"code": "const r = await tools.echo_business({value: 21});\n"
                     "text({value: r.data.value, ok: r.is_success, call_id: r.call_id});"},
        )
    outcome = await _run_turn(
        core, agent, tmp_path, LLMResponse(tool_calls=[wire]), tools, tool_names=["echo_business"]
    )
    assert outcome.decision == "continue"
    # Exactly one executor call with identical arguments on both wires.
    assert [(call.name, call.arguments) for call in tools.calls] == [("echo_business", {"value": 21})]
    # Identical durable lifecycle facts, in order, on both wires.
    ordered = [e.type for e in core.event_log if e.data.get("tool_name") == "echo_business"]
    assert ordered == ["tool.requested", "tool.started", "tool.result_recorded", "tool.finished"]
    recorded = _events(core, "tool.result_recorded", "echo_business")[0]
    assert recorded.data["result"]["is_success"] is True
    assert recorded.data["result"]["data"] == {"value": 42}
    finished = _events(core, "tool.finished", "echo_business")[0]
    assert finished.data["status"] == "completed"
    assert finished.data["effect_state"] == "completed"
    assert finished.data["raw_result_event_id"] == recorded.event_id
    # The result surfaces identically at the wire boundary.
    exchange_result = outcome.tool_exchanges[0][1]
    assert exchange_result.is_success
    if mode == "traditional":
        assert exchange_result.data == {"value": 42}
    else:
        data = exchange_result.data
        assert data["status"] == "completed"
        assert data["error"] is None
        assert data["outputs"] == [
            {"value": 42, "ok": True, "call_id": recorded.data["tool_call_id"]}
        ]
        assert [(r["tool_name"], r["status"], r["raw_result_event_id"]) for r in data["calls"]] == [
            ("echo_business", "completed", recorded.event_id)
        ]
        program_finished = _events(core, "program.finished")[0]
        assert program_finished.data["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_method_policy_denial_reaches_both_paths_without_launching_compute(mode: str, tmp_path):
    (tmp_path / "evil.gjf").write_text(_B3LYP_GJF)
    core = RuntimeCore(strict_events=True)
    agent = await _spawn(
        core, tmp_path, settings={"method_policy": _METHOD_POLICY}, protocol=_protocol(mode)
    )
    tools = _RecordingTools()
    if mode == "traditional":
        wire = ToolCall("t1", "submit_compute_job", {"input_file": "evil.gjf"})
    else:
        wire = ToolCall(
            "w1",
            "js_exec",
            {"code": "try {\n"
                     "  await tools.submit_compute_job({input_file: 'evil.gjf'});\n"
                     "  text('EXECUTED');\n"
                     "} catch (e) {\n"
                     "  text(e.code);\n"
                     "}"},
        )
    outcome = await _run_turn(
        core, agent, tmp_path, LLMResponse(tool_calls=[wire]), tools, tool_names=["submit_compute_job"]
    )
    assert outcome.decision == "continue"
    # No compute was launched on either wire.
    assert tools.calls == []
    # Identical durable denial facts: blocked at the method_policy stage,
    # never started, never recorded.
    blocked = _events(core, "tool.blocked")
    assert len(blocked) == 1
    assert blocked[0].data["stage"] == "method_policy"
    assert blocked[0].data["tool_name"] == "submit_compute_job"
    assert _events(core, "tool.started") == []
    assert _events(core, "tool.result_recorded") == []
    finished = _events(core, "tool.finished")
    assert len(finished) == 1
    assert finished[0].data["status"] == "blocked"
    assert finished[0].data["effect_state"] == "not_started"
    assert finished[0].data["error"]["code"] == "policy_blocked"
    assert "b3lyp" in finished[0].data["error"]["message"]
    if mode == "traditional":
        assert outcome.blocked_call is not None
        assert outcome.blocked_call.name == "submit_compute_job"
    else:
        data = outcome.tool_exchanges[0][1].data
        # The denial crosses the bridge as a guest-visible rejection; the
        # program itself handles it and completes.
        assert data["status"] == "completed"
        assert data["outputs"] == ["policy_blocked"]
        assert [(r["tool_name"], r["status"], r["effect_state"]) for r in data["calls"]] == [
            ("submit_compute_job", "blocked", "not_started")
        ]


@pytest.mark.skipif(not HOST_AVAILABLE, reason=JS_REASON)
@pytest.mark.asyncio
async def test_host_resources_resolve_from_package_and_launch_from_any_cwd(monkeypatch, tmp_path):
    import cloudra

    package_root = Path(cloudra.__file__).resolve().parent
    for rel in (
        "runtime_v2/js_host/host.mjs",
        "runtime_v2/js_host/sandbox.mjs",
        "runtime_v2/js_host/package.json",
        "runtime_v2/js_host/package-lock.json",
    ):
        assert (package_root / rel).is_file(), f"installed resource missing: {rel}"

    core = RuntimeCore(strict_events=True)
    agent = await _spawn(core, tmp_path)
    writer = EventWriter(core.event_log)
    service = InvocationService(event_writer=writer, stages=[], tools=_RecordingTools())
    runtime = JavaScriptRuntime(event_writer=writer, invocations=service)
    assert runtime.host_path == package_root / "runtime_v2" / "js_host" / "host.mjs"
    # Hostile cwd: no repo files, no node_modules — launch must not depend on it.
    monkeypatch.chdir(tmp_path)
    result = await runtime.execute(
        _ctx(agent, tmp_path, tool_names=[]), ToolCall("w1", "js_exec", {"code": "text(40 + 2);"})
    )
    assert result.is_success
    assert result.data["outputs"] == [42]


@pytest.mark.asyncio
async def test_missing_node_disables_only_the_js_protocol(tmp_path):
    core = RuntimeCore(strict_events=True)
    agent = await _spawn(core, tmp_path)
    writer = EventWriter(core.event_log)
    tools = _RecordingTools()
    service = InvocationService(event_writer=writer, stages=default_stages(core), tools=tools)
    runtime = JavaScriptRuntime(
        event_writer=writer,
        invocations=service,
        node_binary="cloudra-definitely-missing-node-binary",
    )
    ctx = _ctx(agent, tmp_path, tool_names=["echo_business"])
    result = await runtime.execute(ctx, ToolCall("w1", "js_exec", {"code": "text(1);"}))
    # No fallback execution and no exception: one ordinary failed exchange.
    assert not result.is_success
    assert result.data["error"]["code"] == "runtime_unavailable"
    finished = _events(core, "program.finished")
    assert len(finished) == 1
    assert finished[0].data["status"] == "failed"
    assert finished[0].data["error"]["code"] == "runtime_unavailable"
    # The same lifecycle keeps serving traditional calls without Node or the
    # host dependencies installed.
    outcome = await service.invoke(ctx, ToolCall("t1", "echo_business", {"value": 5}))
    assert outcome.error is None
    assert outcome.result.data == {"value": 10}
    assert [call.name for call in tools.calls] == ["echo_business"]


@pytest.mark.skipif(not HOST_AVAILABLE, reason=JS_REASON)
@pytest.mark.asyncio
async def test_host_launch_invokes_node_directly_never_npm(monkeypatch, tmp_path):
    spawned: list[tuple] = []
    real_exec = asyncio.create_subprocess_exec

    async def recording_exec(*args, **kwargs):
        spawned.append(tuple(args))
        return await real_exec(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", recording_exec)
    core = RuntimeCore(strict_events=True)
    agent = await _spawn(core, tmp_path)
    writer = EventWriter(core.event_log)
    service = InvocationService(event_writer=writer, stages=[], tools=_RecordingTools())
    runtime = JavaScriptRuntime(event_writer=writer, invocations=service)
    result = await runtime.execute(
        _ctx(agent, tmp_path, tool_names=[]), ToolCall("w1", "js_exec", {"code": "text(7);"})
    )
    assert result.is_success
    assert spawned, "the host process was never spawned"
    # Every spawned process is node itself (prereq --version plus the host);
    # installation is a documented manual step, never a runtime side effect.
    for argv in spawned:
        assert Path(str(argv[0])).name == "node"
    names = {Path(str(arg)).name for argv in spawned for arg in argv}
    assert "npm" not in names
    assert "npx" not in names


def test_wheel_carries_the_js_host_package_data(tmp_path):
    try:
        import pip  # noqa: F401
    except ImportError:
        pytest.skip("pip unavailable; cannot exercise the existing setuptools wheel path")
    build = subprocess.run(
        [
            sys.executable, "-m", "pip", "wheel",
            "--no-deps", "--no-build-isolation",
            "-w", str(tmp_path), str(REPO_ROOT),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if build.returncode != 0:
        pytest.skip(
            "setuptools wheel build unavailable in this environment: "
            f"{build.stderr.strip()[-400:]}"
        )
    wheel = next(tmp_path.glob("cloudra-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    for rel in (
        "cloudra/runtime_v2/js_host/host.mjs",
        "cloudra/runtime_v2/js_host/sandbox.mjs",
        "cloudra/runtime_v2/js_host/package.json",
        "cloudra/runtime_v2/js_host/package-lock.json",
    ):
        assert rel in names, f"wheel is missing {rel}"
    # Guest dependencies are installed out-of-band (npm ci); they are never
    # vendored into the Python distribution.
    assert not any("node_modules" in name for name in names)
