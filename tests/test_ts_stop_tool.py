"""Explicit TS stop control keeps its public and project boundaries small."""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from cloudra.tools.Chemtool import ts_search_process as tools
from cloudra.tools.core.permission_model import Permission
from cloudra.tools.core.ts_process import TsProcessRecord
from tests.test_ts_inputs import input_payload


def test_stop_is_registered_as_a_scientific_write_control():
    from cloudra.tools.registry import TOOL_REGISTRY

    registration = next((entry for entry in TOOL_REGISTRY if entry.tool_name == "ts_stop"), None)
    assert registration is not None
    assert registration.class_name == "TsStop"
    assert registration.role_allowlist == next(entry.role_allowlist for entry in TOOL_REGISTRY
                                             if entry.tool_name == "ts_resume")
    assert registration.dag_observe is False
    assert tools.TsStop().tool_permission_all() == Permission.WRITE


def test_stop_schema_has_only_required_run_id_and_reason():
    assert hasattr(tools, "TsStop_input_schema")
    schema = tools.TsStop_input_schema.to_parameters_schema()
    assert set(schema["properties"]) == {"run_id", "reason"}
    assert set(schema["required"]) == {"run_id", "reason"}
    assert schema["additionalProperties"] is False
    request = tools.TsStop_input_schema(run_id=" ts_0001 ", reason=" Change the planned calculation ")
    assert request.model_dump() == {"run_id": "ts_0001", "reason": "Change the planned calculation"}


@pytest.mark.parametrize("arguments", [
    {},
    {"run_id": "ts_0001"},
    {"reason": "Stop this path"},
    {"run_id": "", "reason": "Stop this path"},
    {"run_id": " ", "reason": "Stop this path"},
    {"run_id": "ts_0001", "reason": ""},
    {"run_id": "ts_0001", "reason": " \n "},
    {"run_id": "ts_0001", "reason": "Stop this path", "expected_revision": 4},
])
def test_stop_rejects_missing_blank_or_internal_arguments(arguments):
    assert hasattr(tools, "TsStop_input_schema")
    with pytest.raises(ValidationError):
        tools.TsStop_input_schema.model_validate(arguments)


def owned_tool(workspace, *, permissions=Permission.WRITE, project="project"):
    return tools.TsStop(subagent=SimpleNamespace(conversation_id=project,
        working_directory=str(workspace) if workspace else None, permission_all=lambda: permissions))


@pytest.mark.asyncio
async def test_stop_requires_write_permission_before_reading_process(tmp_path, monkeypatch):
    def unexpected_read(*args):
        raise AssertionError("read-only caller must not enter process mutation")

    monkeypatch.setattr(tools, "_read_resume_record", unexpected_read)
    result = await owned_tool(tmp_path, permissions=Permission.READ).tool_call(
        tools.TsStop_input_schema(run_id="ts_0001", reason="Stop this path"), None,
    )
    assert not result.is_success
    assert result.run_id == "ts_0001"
    assert "write permission" in result.message


@pytest.mark.asyncio
async def test_stop_reports_missing_bound_workspace():
    result = await owned_tool(None).tool_call(
        tools.TsStop_input_schema(run_id="ts_0001", reason="Stop this path"), None,
    )
    assert not result.is_success
    assert "working directory" in result.message


@pytest.mark.asyncio
async def test_stop_rejects_another_project_before_backend_call(tmp_path, monkeypatch):
    def unexpected_stop(*args):
        raise AssertionError("foreign project must not reach the backend")

    monkeypatch.setattr(tools, "_read_resume_record", lambda *args: SimpleNamespace(owner_conversation_id="foreign"))
    monkeypatch.setattr("cloudra.tools.core.ts_process.stop", unexpected_stop, raising=False)
    result = await owned_tool(tmp_path).tool_call(
        tools.TsStop_input_schema(run_id="ts_0001", reason="Stop this path"), None,
    )
    assert not result.is_success
    assert "different project" in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["other_project", "other_workspace"])
async def test_stop_reads_only_the_authorized_project_and_workspace(tmp_path, scope):
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from tests.test_ts_inspect import process_fixture

    db, _, workspace, record = await asyncio.to_thread(process_fixture, tmp_path)
    tool = owned_tool(tmp_path if scope == "other_workspace" else workspace,
                      project="foreign" if scope == "other_project" else "project")
    with use_pipeline_database(db):
        result = await tool.tool_call(
            tools.TsStop_input_schema(run_id=record["run_id"], reason="Stop this path"), None,
        )
    assert not result.is_success
    assert result.run_id == record["run_id"]
    assert "authorized project and workspace" in result.message


@pytest.mark.asyncio
async def test_stop_forwards_scoped_record_in_worker_and_returns_process_view(tmp_path, monkeypatch):
    worker_thread = threading.get_ident()
    record = TsProcessRecord(run_id="ts_0001", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        owner_conversation_id="project", owner_session_id="owner", input=input_payload())
    stopped = record.model_copy(deep=True, update={"revision": 7})

    def read_record(db, workspace, run_id, project):
        assert threading.get_ident() != worker_thread
        assert (workspace, run_id, project) == (str(tmp_path), "ts_0001", "project")
        return record

    def stop_record(current, reason):
        assert threading.get_ident() != worker_thread
        assert current is record
        assert reason == "Change the planned calculation"
        return stopped

    monkeypatch.setattr(tools, "_read_resume_record", read_record)
    monkeypatch.setattr("cloudra.tools.core.ts_process.stop", stop_record, raising=False)
    result = await owned_tool(tmp_path).tool_call(
        tools.TsStop_input_schema(run_id="ts_0001", reason="Change the planned calculation"),
        SimpleNamespace(id="owner"),
    )
    assert result.is_success
    assert result.run_id == "ts_0001" and result.revision == 7
    assert result.result is None


@pytest.mark.asyncio
async def test_stop_successor_adopts_same_project_process(tmp_path, monkeypatch):
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import get_process
    from tests.test_ts_inspect import process_fixture

    db, process_id, workspace, record = await asyncio.to_thread(process_fixture, tmp_path)

    def stop_record(current, reason):
        assert current.owner_session_id == "successor"
        assert reason == "Stop before revising this run"
        return current

    monkeypatch.setattr("cloudra.tools.core.ts_process.stop", stop_record, raising=False)
    with use_pipeline_database(db):
        result = await owned_tool(workspace).tool_call(
            tools.TsStop_input_schema(run_id=record["run_id"], reason="Stop before revising this run"),
            SimpleNamespace(id="successor"),
        )
    assert result.is_success and result.run_id == record["run_id"]
    current = await asyncio.to_thread(get_process, db, process_id)
    assert current["payload"]["owner_id"] == "successor"
    assert current["record"]["owner_session_id"] == "successor"
