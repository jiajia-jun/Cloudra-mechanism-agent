"""Replay real multi-project VM event headers without chat or chemistry payloads."""

import gzip
import json
from pathlib import Path

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.persistence import RuntimeStore


def test_real_l1_m17_private_snapshot_cannot_reset_old_project_sequence(tmp_path):
    source = Path(__file__).parent / "fixtures/runtime_v2/benchmark_resume_20261020/event_headers.json.gz"
    with gzip.open(source, "rt") as handle:
        case = json.load(handle)
    store = RuntimeStore(tmp_path / "runtime.db")
    columns = ("event_id", "stream", "project_id", "session_id", "run_id", "seq", "session_seq", "type", "created_at")
    with store._connect() as con:
        con.executemany(
            "INSERT INTO events(event_id,stream,project_id,session_id,run_id,seq,session_seq,type,created_at,data) "
            "VALUES (?,?,?,?,?,?,?,?,?,'{}')",
            [tuple(row[column] for column in columns) for row in case["event_headers"]],
        )
        con.execute(
            "INSERT INTO objects(kind,obj_id,data) VALUES ('snapshot','state',?)",
            (json.dumps({"event_metadata": case["old_snapshot_metadata"]}),),
        )

    count, projects, sessions = store.event_metadata()
    assert count == case["expected_count"]
    assert projects == case["expected_project_watermarks"]
    expected_sessions = {}
    for row in case["event_headers"]:
        if row["session_id"] is not None:
            sid = row["session_id"]
            expected_sessions[sid] = max(expected_sessions.get(sid, 0), row["session_seq"] or 0)
    assert sessions == expected_sessions

    log = EventLog(strict=True)
    log.restore_from_store(store)
    resumed = log.append("agent.warning", stream="agent", project_id="prj_98e5a7a37fef499a",
                         session_id="as_4f095f88e2c042bf", data={"message": "resume fixture"})
    assert resumed.seq == 5804
    assert resumed.session_seq == expected_sessions[resumed.session_id] + 1
