"""Shell submissions use the ordinary admission, ledger and terminal inbox."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.services.compute_store import aget_compute_job, list_compute_jobs
from cloudra.tools.Chemtool.submit_compute_job import (
    SubmitComputeJob,
    SubmitComputeJob_input_schema,
)
from tests.test_runtime_v2_compute_notify import (
    _delivered_content,
    _insert_terminal_job,
    _notified_at,
    _setup_core,
)


@pytest.fixture
def shell_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "shell project"
    workspace.mkdir()
    registry = tmp_path / "nodes.json"
    registry.write_text(json.dumps({
        "default_node_id": "shell-local",
        "nodes": [{
            "node_id": "shell-local",
            "workspaces": [{"workspace_id": "scripts", "path": str(workspace)}],
            "resources": {"cpus": 4, "memory_mb": 8192, "max_concurrent": 2},
        }],
    }), encoding="utf-8")
    monkeypatch.setenv("CLOUDRA_NODE_REGISTRY_FILE", str(registry))
    script = workspace / "run.sh"
    script.write_text(
        "#!/bin/bash\n"
        "# %nprocshared=99 %mem=999GB\n"
        "# %pal nprocs 99 end %maxcore 999999\n"
        "printf 'shell result\\n' > result.txt\n",
        encoding="utf-8",
    )
    return workspace, script


@pytest.mark.asyncio
@pytest.mark.parametrize("resources,want_cpus,want_memory", [
    ({}, 1, None),
    ({"cpus": 2, "memory_mb": 512}, 2, 512),
])
async def test_shell_submission_records_declared_resources_without_parsing_script(
    shell_workspace, resources, want_cpus, want_memory,
):
    """Rejecting shell or inferring chemistry resources prevents a real queued row."""
    workspace, script = shell_workspace
    tool = SubmitComputeJob(subagent=SimpleNamespace(
        conversation_id="shell-project", working_directory=str(workspace),
    ))
    result = await tool.tool_call(SubmitComputeJob_input_schema(
        input_file=script.name, job_type="shell", is_async=True, priority=3,
        **resources,
    ), session=SimpleNamespace(id="shell-agent"))

    assert result.is_success, result.message
    assert result.state == "ready"
    assert result.job_dir == str(workspace)
    row = await aget_compute_job(ComputeDB(), result.job_id)
    assert row["path"] == str(script)
    assert row["jobtype"] == "shell"
    assert row["conversation_id"] == "shell-project"
    assert row["session_id"] == "shell-agent"
    assert row["node_id"] == "shell-local"
    assert row["scheduler"] == "local"
    assert row["priority"] == 3
    assert row["req_cpus"] == want_cpus
    assert row["req_memory_mb"] == want_memory
    assert not (workspace / "result.txt").exists()


@pytest.mark.asyncio
async def test_shell_submission_obeys_node_capacity(shell_workspace):
    """Shell must not bypass the shared node admission before ledger insertion."""
    workspace, script = shell_workspace
    db = await ComputeDB().ainit()
    tool = SubmitComputeJob(subagent=SimpleNamespace(
        conversation_id="shell-project", working_directory=str(workspace),
    ))
    result = await tool.tool_call(SubmitComputeJob_input_schema(
        input_file=script.name, job_type="shell", cpus=5, is_async=True,
    ), session=None)

    assert not result.is_success
    assert "exceeds node capacity" in result.message
    assert await asyncio.to_thread(list_compute_jobs, db) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state,last_error", [
    ("done", None),
    ("failed", "Shell process exited with code 7"),
    ("cancelled", None),
])
async def test_shell_terminal_notice_points_to_log_and_working_directory(
    tmp_path, state, last_error,
):
    """Shell results must not instruct agents to parse a chemistry native log."""
    core, project, coordinator = await _setup_core()
    script = tmp_path / "workflow.sh"
    script.write_text("#!/bin/bash\nprintf 'done\\n'\n", encoding="utf-8")
    job_id = await asyncio.to_thread(
        _insert_terminal_job, project.id, session_id=coordinator.id,
        state=state, last_error=last_error, path=str(script), jobtype="shell",
    )
    log = tmp_path / ".cloudra" / f"calc-{job_id}.out.log"
    log.parent.mkdir()
    log.write_text("script output\n", encoding="utf-8")
    broker = ComputeNotifyBroker(core)

    await broker._poll_project(project.id)

    content = _delivered_content(core, coordinator.id)
    assert f"state={state}" in content
    assert str(log) in content
    assert f"Working directory: {tmp_path}" in content
    assert "log_parser" not in content
    assert "frequencies" not in content
    if last_error:
        assert last_error in content
    if state == "cancelled":
        assert "Do not resubmit or restart" in content
    assert await asyncio.to_thread(_notified_at, job_id) is not None
