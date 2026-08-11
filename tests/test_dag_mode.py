import json

import pytest
from click.testing import CliRunner

from cloudra.cli import cli
from cloudra.core.agent import Coordinator
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.services.service import CloudraService, SessionRunner


def test_orchestration_mode_defaults_and_rejects_booleanish_aliases():
    try:
        from cloudra.dag.models import OrchestrationMode, normalize_orchestration_mode
    except ModuleNotFoundError as exc:
        pytest.fail(f"DAG mode module is missing: {exc}")

    assert normalize_orchestration_mode(None) is OrchestrationMode.STANDARD
    assert normalize_orchestration_mode("standard") is OrchestrationMode.STANDARD
    assert normalize_orchestration_mode("dag_record") is OrchestrationMode.DAG_RECORD
    assert normalize_orchestration_mode("dag_guided") is OrchestrationMode.DAG_GUIDED
    with pytest.raises(ValueError):
        normalize_orchestration_mode("on")


def test_coordinator_retains_session_orchestration_mode():
    agent = Coordinator(
        query="mechanism",
        conversation_id="agent-mode",
        orchestration_mode="dag_guided",
    )
    assert agent.orchestration_mode.value == "dag_guided"


def test_cli_exposes_explicit_orchestration_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "run",
            "mechanism",
            "--new",
            "--dry-run",
            "--orchestration-mode",
            "dag_record",
        ],
    )

    assert result.exit_code == 0
    assert "Orchestration Mode: dag_record" in result.output


def test_cli_rejects_unknown_orchestration_mode():
    result = CliRunner().invoke(
        cli,
        ["run", "mechanism", "--dry-run", "--orchestration-mode", "on"],
    )
    assert result.exit_code == 2
    assert "Invalid value for '--orchestration-mode'" in result.output


def test_queued_session_persists_mode_and_reproducibility_snapshot(tmp_path):
    db = ConversationDB("dag-mode", data_dir=tmp_path).init()
    snapshot = {
        "graph_policy_revision": "sha256:policy",
        "supervisor_prompt_revision": "sha256:prompt",
    }

    session_store.insert_queued_session(
        db,
        session_id="s-guided",
        agent_id="a-0",
        agent_type="coordinator",
        query="study Claisen",
        orchestration_mode="dag_guided",
        orchestration_config=snapshot,
    )

    with db.connect() as con:
        row = con.execute(
            "SELECT orchestration_mode, orchestration_config "
            "FROM session WHERE session_id='s-guided'"
        ).fetchone()
    assert row[0] == "dag_guided"
    assert '"graph_policy_revision":"sha256:policy"' in row[1]
    assert '"supervisor_prompt_revision":"sha256:prompt"' in row[1]


def test_legacy_session_rows_default_to_standard(tmp_path):
    db = ConversationDB("legacy-mode", data_dir=tmp_path).init()
    session_store.insert_queued_session(
        db,
        session_id="s-legacy",
        agent_id="a-0",
        agent_type="coordinator",
        query="ordinary task",
    )

    with db.connect() as con:
        row = con.execute(
            "SELECT orchestration_mode, orchestration_config "
            "FROM session WHERE session_id='s-legacy'"
        ).fetchone()
    assert row == ("standard", "{}")


def test_direct_react_session_creation_persists_mode(tmp_path):
    db = ConversationDB("direct-mode", data_dir=tmp_path).init()

    session_store.create_session_record(
        db,
        session_id="s-direct",
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="mechanism",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode="dag_record",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )

    with db.connect() as con:
        row = con.execute(
            "SELECT orchestration_mode, orchestration_config "
            "FROM session WHERE session_id='s-direct'"
        ).fetchone()
    assert row == (
        "dag_record",
        '{"graph_policy_revision":"sha256:policy"}',
    )


def test_session_runner_record_returns_persisted_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    runner = SessionRunner(service=object())

    record, created = runner._prepare_submission(
        "mechanism",
        "runner-mode",
        "s-runner",
        orchestration_mode="dag_guided",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )

    assert created is True
    assert record.orchestration_mode == "dag_guided"
    assert record.orchestration_config == '{"graph_policy_revision":"sha256:policy"}'


def test_guided_submission_snapshots_supervisor_and_policy_revisions(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    runner = SessionRunner(service=object())

    record, _ = runner._prepare_submission(
        "mechanism",
        "runner-snapshot",
        "s-snapshot",
        orchestration_mode="dag_guided",
    )

    snapshot = json.loads(record.orchestration_config)
    assert snapshot["orchestration_mode"] == "dag_guided"
    assert snapshot["graph_policy_revision"].startswith("sha256:")
    assert snapshot["supervisor_prompt_revision"].startswith("sha256:")
    assert snapshot["supervisor_model"] == get_config().follower.model


@pytest.mark.asyncio
async def test_session_runner_threads_mode_into_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    runner = SessionRunner(service=object())
    captured = {}

    async def fake_execute(
        query,
        conversation_id,
        session_id,
        working_directory=None,
        yolo=False,
        orchestration_mode="standard",
        orchestration_config=None,
    ):
        captured["mode"] = getattr(orchestration_mode, "value", orchestration_mode)
        captured["config"] = orchestration_config

    runner._execute = fake_execute
    record = runner.submit(
        "mechanism",
        "runner-execute-mode",
        orchestration_mode="dag_record",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )
    await runner._running[("runner-execute-mode", record.session_id)]

    assert captured == {
        "mode": "dag_record",
        "config": {"graph_policy_revision": "sha256:policy"},
    }


@pytest.mark.asyncio
async def test_session_runner_async_threads_mode_into_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    runner = SessionRunner(service=object())
    captured = {}

    async def fake_execute(
        query,
        conversation_id,
        session_id,
        working_directory=None,
        yolo=False,
        orchestration_mode="standard",
        orchestration_config=None,
    ):
        captured["mode"] = getattr(orchestration_mode, "value", orchestration_mode)
        captured["config"] = orchestration_config

    runner._execute = fake_execute
    record = await runner.submit_async(
        "mechanism",
        "runner-async-mode",
        orchestration_mode="dag_guided",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )
    await runner._running[("runner-async-mode", record.session_id)]

    assert captured == {
        "mode": "dag_guided",
        "config": {"graph_policy_revision": "sha256:policy"},
    }


@pytest.mark.asyncio
async def test_session_runner_executes_with_generated_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    runner = SessionRunner(service=object())
    captured = {}

    async def fake_execute(
        query,
        conversation_id,
        session_id,
        working_directory=None,
        yolo=False,
        orchestration_mode="standard",
        orchestration_config=None,
    ):
        captured["config"] = orchestration_config

    runner._execute = fake_execute
    record = await runner.submit_async(
        "mechanism",
        "runner-generated-snapshot",
        orchestration_mode="dag_guided",
    )
    await runner._running[("runner-generated-snapshot", record.session_id)]

    assert captured["config"]["orchestration_mode"] == "dag_guided"
    assert captured["config"]["graph_policy_revision"].startswith("sha256:")


@pytest.mark.asyncio
async def test_service_threads_mode_for_sync_and_async_submissions():
    captured = []

    class CaptureRunner:
        def submit(self, query, conversation_id, **kwargs):
            captured.append(("sync", kwargs))
            return "sync-record"

        async def submit_async(self, query, conversation_id, **kwargs):
            captured.append(("async", kwargs))
            return "async-record"

    service = CloudraService.__new__(CloudraService)
    service.session_runner = CaptureRunner()

    _, sync_record = service.submit_session(
        "mechanism", "service-mode",
        orchestration_mode="dag_guided",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )
    _, async_record = await service.submit_session_async(
        "mechanism", "service-mode",
        orchestration_mode="dag_record",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )

    assert sync_record == "sync-record"
    assert async_record == "async-record"
    assert captured == [
        ("sync", {
            "working_directory": None,
            "yolo": False,
            "orchestration_mode": "dag_guided",
            "orchestration_config": {"graph_policy_revision": "sha256:policy"},
        }),
        ("async", {
            "working_directory": None,
            "yolo": False,
            "orchestration_mode": "dag_record",
            "orchestration_config": {"graph_policy_revision": "sha256:policy"},
        }),
    ]


def test_idempotent_session_command_threads_orchestration_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    captured = {}
    record = object()

    class CaptureRunner:
        def get(self, *args):
            return None

        def submit(self, query, conversation_id, **kwargs):
            captured.update(kwargs)
            return record

        def _emit(self, *args, **kwargs):
            pass

    service = CloudraService.__new__(CloudraService)
    service.session_runner = CaptureRunner()

    _, returned = service.submit_session_command(
        command_id="cmd-dag-mode",
        query="mechanism",
        conversation_id="command-mode",
        orchestration_mode="dag_guided",
    )

    assert returned is record
    assert captured["orchestration_mode"] == "dag_guided"
    assert captured["orchestration_config"]["graph_policy_revision"].startswith("sha256:")


@pytest.mark.asyncio
async def test_service_run_task_threads_mode_to_runtime(monkeypatch):
    captured = {}

    async def fake_run_task_async(query, **kwargs):
        captured.update(kwargs)
        return "done"

    monkeypatch.setattr("cloudra.services.service.run_task_async", fake_run_task_async)
    service = CloudraService.__new__(CloudraService)

    result = await service.run_task(
        "mechanism",
        conversation_id="runtime-mode",
        session_id="s-runtime",
        orchestration_mode="dag_guided",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )

    assert result == "done"
    assert captured["orchestration_mode"] == "dag_guided"
    assert captured["orchestration_config"] == {
        "graph_policy_revision": "sha256:policy",
    }


@pytest.mark.asyncio
async def test_session_execution_passes_persisted_mode_to_service():
    captured = {}

    class CaptureService:
        async def run_task(self, query, conversation_id, **kwargs):
            captured.update(kwargs)
            return "done"

    runner = SessionRunner(CaptureService())
    runner._claim = lambda *args: True
    runner._update = lambda *args, **kwargs: None
    runner._emit = lambda *args, **kwargs: None

    async def idle_heartbeat(*args):
        await __import__("asyncio").Event().wait()

    runner._heartbeat = idle_heartbeat
    await runner._execute(
        "mechanism",
        "execution-mode",
        "s-execution",
        orchestration_mode="dag_record",
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )

    assert captured["orchestration_mode"] == "dag_record"
    assert captured["orchestration_config"] == {
        "graph_policy_revision": "sha256:policy",
    }


@pytest.mark.asyncio
async def test_runtime_constructs_coordinator_with_session_mode(tmp_path, monkeypatch):
    from cloudra.runtime import runner as runtime_runner

    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    captured = {}

    class FakeConversation:
        def __init__(self, conv_id=None):
            self.id = conv_id or "runtime-conversation"
            self.state = "active"

        def touch(self):
            pass

        def set_state(self, state):
            self.state = state

    class FakeCoordinator:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.query = kwargs["query"]

        async def get_context(self):
            return [{"role": "user", "content": self.query}]

        async def update_context(self, block):
            raise AssertionError("query should already be present")

    class FakeReact:
        def __init__(self, agent, session_id=None):
            self.agent = agent

        async def run(self):
            return "done"

        async def _record_phase(self, phase):
            pass

        async def drain_pending_external_events(self):
            return False

    async def no_wait(*args, **kwargs):
        return None

    monkeypatch.setattr(runtime_runner, "Conversation", FakeConversation)
    monkeypatch.setattr(runtime_runner, "Coordinator", FakeCoordinator)
    monkeypatch.setattr(runtime_runner, "Coordinator_reAct", FakeReact)
    monkeypatch.setattr(runtime_runner, "ensure_listener", no_wait)
    monkeypatch.setattr(runtime_runner, "_wait_for_background_tasks", no_wait)
    monkeypatch.setattr(runtime_runner, "is_mobile_runtime", lambda: True)

    result = await runtime_runner.run_task_async(
        "mechanism",
        conv_id="runtime-conversation",
        verbose=False,
        session_id="s-runtime",
        orchestration_mode="dag_guided",
    )

    assert result == "done"
    assert captured["orchestration_mode"] == "dag_guided"
    assert captured["orchestration_config"]["orchestration_mode"] == "dag_guided"
    assert captured["orchestration_config"]["graph_policy_revision"].startswith(
        "sha256:"
    )
    assert captured["orchestration_config"]["supervisor_prompt_revision"].startswith(
        "sha256:"
    )
    assert captured["orchestration_config"]["supervisor_model"]


@pytest.mark.parametrize(
    ("mode", "expected_calls"),
    [("standard", 0), ("dag_record", 0), ("dag_guided", 1)],
)
def test_react_constructs_supervisor_only_in_guided_mode(
    mode,
    expected_calls,
    tmp_path,
    monkeypatch,
):
    from cloudra.core import react as react_module

    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    calls = []
    sentinel = object()

    def fake_get_supervisor(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(react_module, "get_supervisor", fake_get_supervisor)
    conversation_id = f"react-{mode.replace('_', '-')}"
    ConversationDB(conversation_id).init()
    agent = Coordinator(
        query="mechanism",
        conversation_id=conversation_id,
        orchestration_mode=mode,
        orchestration_config={"graph_policy_revision": "sha256:policy"},
    )
    react = react_module.reAct(agent, session_id=f"s-{mode}")

    assert len(calls) == expected_calls
    assert react.supervisor is (sentinel if expected_calls else None)
    with ConversationDB(conversation_id).connect() as con:
        row = con.execute(
            "SELECT orchestration_mode, orchestration_config FROM session "
            "WHERE session_id=?",
            (f"s-{mode}",),
        ).fetchone()
    assert row == (mode, '{"graph_policy_revision":"sha256:policy"}')


@pytest.mark.asyncio
async def test_guided_react_does_not_poll_supervisor_by_step_count(monkeypatch):
    from types import SimpleNamespace

    from cloudra.core import react as react_module

    class NoPeriodicSupervisor:
        def should_review(self, step):
            raise AssertionError("Supervisor must be event-driven, not step-driven")

    async def no_op(*args, **kwargs):
        return None

    async def context():
        return [{"role": "assistant", "content": "done"}]

    loop = react_module.reAct.__new__(react_module.reAct)
    loop._continue = True
    loop.session = SimpleNamespace(id="s-guided", state="sleeping")
    loop.step_count = 14
    loop.supervisor = NoPeriodicSupervisor()
    loop.agent = SimpleNamespace(
        id="a-0",
        _has_goal_anchor=lambda: False,
        get_context=context,
    )
    loop.database_path = "unused.db"
    loop._record_phase = no_op
    loop._consume_external_events = no_op
    loop._check_cancel_event = lambda: None
    loop.reasoning = lambda: _async_value([{"tool": "stop"}])
    loop.act_result = lambda calls: _async_value(True)
    loop._persist_case = no_op
    monkeypatch.setattr(react_module.session_store, "afinalize_session", no_op)

    result = await loop._run_loop()

    assert result == "done"


async def _async_value(value):
    return value
