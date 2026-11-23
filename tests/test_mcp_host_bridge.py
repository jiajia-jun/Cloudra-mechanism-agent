from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from cloudra.cli import cli
from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2.app import create_v2_app
from cloudra.services.compute_store import ainsert_compute_job, get_compute_job
from cloudra.services.host_bridge import format_host_session_id
from cloudra.services.watchdog import evaluate_pre_invocation_hook, evaluate_stop_hook
from tests.agent_scenarios import ScenarioHarness


@pytest.mark.asyncio
async def test_host_tools_catalog_hides_dag_and_runtime_controls_by_default(tmp_path):
    harness = await ScenarioHarness.start(tmp_path)
    app = create_v2_app(core=harness.core)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 4000))
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=transport, base_url="http://localhost",
    ) as http:
        default_resp = await http.get("/api/v2/host/tools")
        assert default_resp.status_code == 200
        default_names = {t["name"] for t in default_resp.json()["tools"]}
        assert "submit_compute_job" in default_names
        assert "query_compute_job" in default_names
        assert "log_parser" in default_names
        assert "get_tool_docs" in default_names
        # Host-owned generic tools and internal orchestration stay hidden.
        assert "bash" not in default_names
        assert "get_skill" not in default_names
        assert "subagent_launcher" not in default_names
        # DAG tools are opt-in because DAG mode is optional.
        assert not any(name.startswith("dag_") for name in default_names)

        dag_resp = await http.get("/api/v2/host/tools", params={"include_dag": "true"})
        assert dag_resp.status_code == 200
        dag_names = {t["name"] for t in dag_resp.json()["tools"]}
        assert "dag_view" in dag_names
        assert "dag_review_step" not in dag_names

        # Domain filtering isolates QM, MD, Periodic, and DAG stacks while keeping common tools.
        qm_resp = await http.get("/api/v2/host/tools", params={"domain": "qm"})
        assert qm_resp.status_code == 200
        qm_names = {t["name"] for t in qm_resp.json()["tools"]}
        assert {"qm_input_writer", "ts_prepare", "submit_compute_job", "log_parser"} <= qm_names
        assert "md_box" not in qm_names
        assert "periodic_model" not in qm_names
        assert "dag_view" not in qm_names

        md_resp = await http.get("/api/v2/host/tools", params={"domain": "md"})
        assert md_resp.status_code == 200
        md_names = {t["name"] for t in md_resp.json()["tools"]}
        assert {"md_box", "md_rmsd", "pdb_clean", "submit_compute_job"} <= md_names
        assert "qm_input_writer" not in md_names
        assert "periodic_model" not in md_names

        periodic_resp = await http.get("/api/v2/host/tools", params={"domain": "periodic"})
        assert periodic_resp.status_code == 200
        periodic_names = {t["name"] for t in periodic_resp.json()["tools"]}
        assert {"periodic_model", "periodic_ts", "submit_compute_job", "format_converter"} <= periodic_names
        assert "qm_input_writer" not in periodic_names
        assert "md_box" not in periodic_names

        dag_only_resp = await http.get("/api/v2/host/tools", params={"domain": "dag"})
        assert dag_only_resp.status_code == 200
        dag_only_names = {t["name"] for t in dag_only_resp.json()["tools"]}
        assert "dag_view" in dag_only_names
        assert all(name.startswith("dag_") for name in dag_only_names)


@pytest.mark.asyncio
async def test_host_tool_execution_respects_optional_dag_mode(tmp_path):
    harness = await ScenarioHarness.start(tmp_path)
    created = await harness.bus.execute(Command(type="project.create", payload={"name": "ad-hoc"}))
    project_id = created.data.id

    app = create_v2_app(core=harness.core)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 4000))
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=transport, base_url="http://localhost",
    ) as http:
        # Ordinary Cloudra tool works immediately in standard (non-DAG) mode.
        docs_resp = await http.post(
            f"/api/v2/projects/{project_id}/host/tools/get_tool_docs",
            json={"arguments": {"names": ["log_parser"]}, "owner_id": "agy-1"},
        )
        assert docs_resp.status_code == 200
        body = docs_resp.json()
        assert body["tool_name"] == "get_tool_docs"
        assert body["is_success"] is True

        # Excluded runtime/shell tools are forbidden.
        forbidden = await http.post(
            f"/api/v2/projects/{project_id}/host/tools/bash",
            json={"arguments": {"command": "echo hi"}},
        )
        assert forbidden.status_code == 403

        # DAG tool is rejected while project stays in standard mode.
        dag_blocked = await http.post(
            f"/api/v2/projects/{project_id}/host/tools/dag_view",
            json={"arguments": {}},
        )
        assert dag_blocked.status_code == 409
        assert "DAG mode" in dag_blocked.json()["detail"]["message"]

        # Enabling optional DAG mode unlocks DAG tools on the same project.
        patch_resp = await http.patch(
            f"/api/v2/projects/{project_id}",
            json={"settings": {"orchestration_mode": "dag_guided"}},
        )
        assert patch_resp.status_code == 200
        dag_ok = await http.post(
            f"/api/v2/projects/{project_id}/host/tools/dag_view",
            json={"arguments": {}},
        )
        assert dag_ok.status_code == 200
        assert dag_ok.json()["tool_name"] == "dag_view"


@pytest.mark.asyncio
async def test_compute_watchdog_claims_atomically_and_notify_broker_does_not_steal_host_jobs(tmp_path):
    harness = await ScenarioHarness.start(tmp_path)
    # Even when a project ALSO has an internal Coordinator, host-owned compute jobs
    # must stay unclaimed until the external host claims them via the watchdog API.
    coordinator = await harness.spawn("coordinator", query="")
    project_id = coordinator.project_id
    host_session = format_host_session_id("agy-chat-42")

    db = await ComputeDB().ainit()
    active_id = await ainsert_compute_job(
        db,
        conversation_id=project_id,
        session_id=host_session,
        path=str(tmp_path / "running.gjf"),
        state="running",
        jobtype="gaussian",
        node_id="local",
    )
    done_id = await ainsert_compute_job(
        db,
        conversation_id=project_id,
        session_id=host_session,
        path=str(tmp_path / "finished.gjf"),
        state="done",
        jobtype="gaussian",
        node_id="local",
    )

    broker = ComputeNotifyBroker(harness.core)
    await broker._poll_project(project_id)

    # Broker must NOT have diverted the host job to the internal coordinator or set notified_at.
    assert get_compute_job(db, done_id)["notified_at"] is None
    assert not harness.core.event_log.query_session(coordinator.id, types={"agent.message_injected"})

    app = create_v2_app(core=harness.core)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 4000))
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=transport, base_url="http://localhost",
    ) as http:
        # Read-only watchdog inspection shows both active and unclaimed terminal jobs.
        snap = await http.get(
            "/api/v2/host/compute/watchdog",
            params={"project_id": project_id, "owner_id": "agy-chat-42"},
        )
        assert snap.status_code == 200
        snap_data = snap.json()
        assert [j["job_id"] for j in snap_data["active_jobs"]] == [active_id]
        assert [j["job_id"] for j in snap_data["unclaimed_terminal_jobs"]] == [done_id]
        assert get_compute_job(db, done_id)["notified_at"] is None

        # Atomic claim consumes the finished job once and leaves active jobs untouched.
        first_claim = await http.post(
            "/api/v2/host/compute/claim",
            json={"project_id": project_id, "owner_id": "agy-chat-42"},
        )
        assert first_claim.status_code == 200
        first_data = first_claim.json()
        assert [j["job_id"] for j in first_data["claimed_jobs"]] == [done_id]
        assert [j["job_id"] for j in first_data["active_jobs"]] == [active_id]
        assert get_compute_job(db, done_id)["notified_at"] is not None

        # Second claim is a no-op (CAS idempotency).
        second_claim = await http.post(
            "/api/v2/host/compute/claim",
            json={"project_id": project_id, "owner_id": "agy-chat-42"},
        )
        assert second_claim.status_code == 200
        assert second_claim.json()["claimed_jobs"] == []
        assert [j["job_id"] for j in second_claim.json()["active_jobs"]] == [active_id]


def test_watchdog_hook_decisions_stay_silent_for_non_compute_work_and_block_unclaimed_jobs():
    # Unreachable Cloudra or empty queue -> allow silently (zero friction on normal chats).
    assert evaluate_stop_hook({"terminationReason": "NO_TOOL_CALL", "fullyIdle": True}, status=None) == {
        "decision": "allow",
    }
    empty = {"active_jobs": [], "unclaimed_terminal_jobs": []}
    assert evaluate_stop_hook({"terminationReason": "NO_TOOL_CALL", "fullyIdle": True}, status=empty) == {
        "decision": "allow",
    }
    assert evaluate_pre_invocation_hook({}, status=empty) == {}

    # Unclaimed terminal job -> force continue on Stop + ephemeral reminder on PreInvocation.
    with_unclaimed = {
        "active_jobs": [],
        "unclaimed_terminal_jobs": [
            {"job_id": 12, "state": "done", "project_id": "P1", "jobtype": "orca", "log_path": "/tmp/a.out"},
        ],
    }
    stop_res = evaluate_stop_hook({"terminationReason": "NO_TOOL_CALL", "fullyIdle": True}, status=with_unclaimed)
    assert stop_res["decision"] == "continue"
    assert "claim_compute_jobs" in stop_res["reason"]
    assert "job_id=12" in stop_res["reason"]

    pre_res = evaluate_pre_invocation_hook({}, status=with_unclaimed)
    assert "injectSteps" in pre_res
    assert "job_id=12" in pre_res["injectSteps"][0]["ephemeralMessage"]

    # Active jobs only: block when fullyIdle=True, allow when host already has background wait.
    with_active = {
        "active_jobs": [{"job_id": 15, "state": "running", "project_id": "P1", "jobtype": "gaussian"}],
        "unclaimed_terminal_jobs": [],
    }
    assert evaluate_stop_hook({"terminationReason": "NO_TOOL_CALL", "fullyIdle": True}, status=with_active)["decision"] == "continue"
    assert evaluate_stop_hook({"terminationReason": "NO_TOOL_CALL", "fullyIdle": False}, status=with_active) == {
        "decision": "allow",
    }

    # Never trap user cancellations or errors.
    assert evaluate_stop_hook({"terminationReason": "USER_CANCELED", "fullyIdle": True}, status=with_unclaimed) == {
        "decision": "allow",
    }


def test_watchdog_cli_fails_open_when_cloudra_is_not_running(monkeypatch):
    from cloudra.services import local_api_client

    monkeypatch.setattr(local_api_client, "find_store_owner", lambda _: None)
    result = CliRunner().invoke(
        cli,
        ["watchdog", "--hook", "stop"],
        input=json.dumps({"terminationReason": "NO_TOOL_CALL", "fullyIdle": True}),
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"decision": "allow"}
