"""Telemetry filters before materializing large audit payloads."""

from datetime import datetime, timezone

import pytest

from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import EventEnvelope
from cloudra.services import telemetry


@pytest.fixture
def telemetry_history(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path / "runtime.db")
    samples = [
        ("context.appended", {"messages": [{"content": "x" * 200000}]}, "2026-10-16T16:00:00+00:00"),
        ("run.started", {}, "2026-10-16T17:00:00+00:00"),
        ("llm.completed", {"usage": {"prompt_tokens": 10, "completion_tokens": 2}, "model": "m"}, "2026-10-17T01:00:00+08:00"),
        ("tool.finished", {"status": "completed", "result_summary": "y" * 200000}, "2026-10-16T18:00:00+00:00"),
        ("run.finished", {"outcome": "succeeded"}, "2026-10-16T19:00:00+00:00"),
    ]
    for index, (kind, data, ts) in enumerate(samples):
        store.append_event(EventEnvelope(event_id=f"e{index}", stream="agent", project_id="p", session_id="a",
                                         run_id="r", seq=index + 1, session_seq=index + 1, type=kind,
                                         data=data, created_at=datetime.fromisoformat(ts).astimezone(timezone.utc)))
    statements = []
    original = telemetry._connect_readonly

    def connect(path):
        con = original(path)
        con.set_trace_callback(statements.append)
        return con

    monkeypatch.setattr(telemetry, "_connect_readonly", connect)
    return store, statements


@pytest.mark.parametrize("summary", [telemetry.token_summary, telemetry.cache_summary])
def test_token_and_cache_queries_filter_types_and_time_in_sql(telemetry_history, summary):
    store, statements = telemetry_history
    expected = summary(store.path, since="2026-10-17T01:00:00+08:00", until="2026-10-16T17:00:00Z")
    assert expected["totals" if summary is telemetry.token_summary else "overall"]["requests"] == 1
    sql = next(sql for sql in statements if sql.startswith("SELECT event_id"))
    assert "type IN ('llm.completed')" in sql
    assert "julianday(created_at)" in sql
    assert "CASE" in sql


def test_agent_summary_keeps_event_metadata_without_large_payloads(telemetry_history):
    store, _ = telemetry_history
    full = telemetry.load_events(store.path)
    small = telemetry.load_events(store.path, metadata=True)
    assert telemetry.aggregate_agents(small) == telemetry.aggregate_agents(full)
    assert len(str(small)) < 10000
    # Full export keeps its original lossless behavior.
    assert full[0]["data"]["messages"][0]["content"] == "x" * 200000
    assert telemetry.agent_summary(store.path) == telemetry.aggregate_agents(full)
