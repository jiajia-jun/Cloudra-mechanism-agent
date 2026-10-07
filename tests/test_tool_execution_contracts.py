"""Tool discovery and result failures stay inside the real execution boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cloudra.base.tools_class import output_schema
from cloudra.runtime_v2.adapters import LegacyLLMProvider, LegacyToolExecutor, legacy_tool_schemas
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall
from cloudra.runtime_v2.schemas import AgentSession, Command, RuntimeSettings
from cloudra.runtime_v2.tool_catalog import wire_tool_schemas
from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_output_schema


@pytest.mark.parametrize("names", [None, []])
def test_empty_capabilities_never_expand_to_all_registered_tools(names):
    assert legacy_tool_schemas(names) == []
    agent = AgentSession(
        id="contract-agent", project_id="contract-project", role_id="coordinator",
        display_name="contract", settings=RuntimeSettings(invocation_protocol="traditional"),
    )
    assert wire_tool_schemas(agent, names) == []


def test_wildcard_discovery_still_expands_explicitly():
    schemas = legacy_tool_schemas(["*"])
    assert schemas
    assert "stop" in {schema["function"]["name"] for schema in schemas}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["none", "wrong_schema", "nonfinite", "non_json"])
async def test_invalid_tool_outputs_record_failure_instead_of_raw_success(failure, monkeypatch):
    async def broken_output(*args):
        if failure == "none":
            return None
        if failure == "wrong_schema":
            return output_schema()
        if failure == "nonfinite":
            return LogParser_output_schema(is_success=True, scf_energy_hartree=float("nan"))
        return LogParser_output_schema(is_success=True, imaginary_modes=[{"unserializable": object()}])

    monkeypatch.setattr(LogParser, "tool_call", broken_output)

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "output contract"}))
    project = next(iter(core.projects.values()))
    spawned = await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator"},
    ))
    agent = spawned.data
    service = InvocationService(
        event_writer=core.event_writer, stages=[], tools=LegacyToolExecutor(core),
    )
    outcome = await service.invoke(
        PipelineContext(
            agent=agent, run_id="output-contract", settings_snapshot=agent.settings,
            capabilities=agent.capabilities, inbox_messages=[], emit=lambda *args: None,
        ),
        ToolCall(id="invalid-output", name="log_parser", arguments={"log_path": "unused.out"}),
    )
    result = outcome.result
    assert result is not None
    assert result.is_success is False
    assert result.data == {}
    assert result.error is not None
    assert result.error.code == "tool_exception"
    assert result.error.effect_state == "unknown"
    events = [event for event in core.event_log if event.data.get("tool_call_id") == "invalid-output"]
    assert [event.type for event in events] == [
        "tool.requested", "tool.started", "tool.progress", "tool.finished",
    ]
    assert events[-1].data["status"] == "failed"
    assert events[-1].data["effect_state"] == "unknown"
    assert events[-1].data["is_success"] is False
    assert events[-1].data["raw_result_event_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason", ["tool_calls", None])
async def test_provider_rejects_malformed_stream_arguments_and_closes_resources(
    finish_reason, monkeypatch,
):
    class BrokenStream:
        closed = False

        def __init__(self):
            self.chunks = iter([SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(tool_calls=[SimpleNamespace(
                    index=0, id="broken-stream", type="function",
                    function={"name": "stop", "arguments": '{"reason":'},
                )]), finish_reason=finish_reason,
            )])])

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.chunks)
            except StopIteration:
                raise StopAsyncIteration

        async def aclose(self):
            self.closed = True

    stream = BrokenStream()

    class Client:
        last_usage = {}
        closed = False

        async def create_with_retry(self, **kwargs):
            return stream

        async def aclose(self):
            self.closed = True

    async def no_accounting(*args):
        return None

    monkeypatch.setattr(
        "cloudra.services.conformer_model_budget.ModelRequestAccounting.for_agent", no_accounting,
    )
    client = Client()
    agent = SimpleNamespace(
        role_id="coordinator", current_run=None,
        settings=RuntimeSettings(
            model="contract-model", base_url="https://example.invalid/",
            api_key="unused", invocation_protocol="traditional",
        ),
    )
    provider = LegacyLLMProvider(client_factory=lambda settings: client)
    with pytest.raises(ValueError):
        await provider.complete(agent, [{"role": "user", "content": "go"}], ["stop"])
    assert stream.closed is True
    assert client.closed is True
