from scripts.analyze_dag_efficiency import summarize_run


def _event(event_id, etype, created_at, data=None, session_id=None, run_id=None):
    return {
        "event_id": event_id,
        "type": etype,
        "created_at": created_at,
        "data": data or {},
        "session_id": session_id,
        "run_id": run_id,
    }


def test_missing_consumption_is_not_zero_latency():
    result = summarize_run(events=[], jobs=[], reviews=[])
    assert result["message_consumption_latency_seconds"] is None
    assert result["consumption_sample_count"] == 0


def test_unavailable_sources_are_marked_not_zeroed():
    result = summarize_run(events=None, jobs=None, reviews=None)
    assert result["unavailable"] == ["events", "jobs", "reviews"]
    assert result["jobs"] is None
    assert result["reviews"] is None
    assert result["window"] is None


def test_duplicate_events_are_deduplicated():
    events = [
        _event("evt_1", "hub.posted", "2026-09-04T04:00:00+00:00"),
        _event("evt_1", "hub.posted", "2026-09-04T04:00:00+00:00"),
        _event("evt_2", "run.started", "2026-09-04T04:00:01+00:00"),
    ]
    result = summarize_run(events=events, jobs=[], reviews=[])
    assert result["events"]["total"] == 2
    assert result["events"]["duplicates_removed"] == 1
    assert result["events"]["by_type"] == {"hub.posted": 1, "run.started": 1}


def test_incomplete_window_is_not_reported_complete():
    events = [
        _event("evt_1", "run.started", "2026-09-04T04:00:00+00:00",
               session_id="as_1", run_id="run_1"),
        _event("evt_2", "agent.thinking", "2026-09-04T04:05:00+00:00",
               session_id="as_1", run_id="run_1"),
    ]
    result = summarize_run(events=events, jobs=[], reviews=[])
    assert result["window"]["complete"] is False
    assert result["window"]["duration_seconds"] == 300.0


def test_complete_window_requires_terminal_last_event():
    events = [
        _event("evt_1", "run.started", "2026-09-04T04:00:00+00:00",
               session_id="as_1", run_id="run_1"),
        _event("evt_2", "run.finished", "2026-09-04T04:10:00+00:00",
               data={"outcome": "succeeded"}, session_id="as_1", run_id="run_1"),
    ]
    result = summarize_run(events=events, jobs=[], reviews=[])
    assert result["window"]["complete"] is True


def test_supervisor_cumulative_time_is_separate_from_wall_clock():
    events = [
        _event("evt_0", "agent.spawned", "2026-09-04T04:00:00+00:00",
               data={"id": "as_sup", "role_id": "supervisor"}),
        _event("evt_1", "run.started", "2026-09-04T04:00:10+00:00",
               session_id="as_sup", run_id="run_1"),
        _event("evt_2", "run.finished", "2026-09-04T04:00:40+00:00",
               data={"outcome": "succeeded"}, session_id="as_sup", run_id="run_1"),
        _event("evt_3", "run.started", "2026-09-04T04:05:00+00:00",
               session_id="as_sup", run_id="run_2"),
        _event("evt_4", "run.finished", "2026-09-04T04:05:20+00:00",
               data={"outcome": "succeeded"}, session_id="as_sup", run_id="run_2"),
    ]
    result = summarize_run(events=events, jobs=[], reviews=[])
    supervisor = result["supervisor"]
    assert supervisor["session_count"] == 1
    assert supervisor["run_count"] == 2
    assert supervisor["cumulative_seconds"] == 50.0
    assert supervisor["wall_clock_seconds"] == 320.0
    assert supervisor["cumulative_seconds"] != supervisor["wall_clock_seconds"]


def test_consumption_latency_uses_matching_pairs_only():
    events = [
        _event("evt_1", "hub.posted", "2026-09-04T04:00:00+00:00",
               data={"post_id": "p1"}),
        _event("evt_2", "hub.notification_consumed", "2026-09-04T04:00:30+00:00",
               data={"post_id": "p1", "consumed_at": "2026-09-04T04:00:30+00:00"}),
        _event("evt_3", "hub.notification_consumed", "2026-09-04T04:01:00+00:00",
               data={"post_id": "p_unknown"}),
    ]
    result = summarize_run(events=events, jobs=[], reviews=[])
    assert result["consumption_sample_count"] == 1
    assert result["message_consumption_latency_seconds"] == 30.0
    assert "consumption_events_without_matching_post" in result["missing_fields"]


def test_review_and_job_counters_expose_denominators():
    jobs = [
        {"state": "done", "conversation_id": "p", "path": "a.inp", "jobtype": "orca"},
        {"state": "failed", "conversation_id": "p", "path": "a.inp", "jobtype": "orca"},
        {"state": "done", "conversation_id": "p", "path": "b.inp", "jobtype": "orca"},
    ]
    reviews = [
        {"state": "ignored"},
        {"state": "ignored"},
        {"state": "reviewed"},
        {"state": "pending"},
    ]
    result = summarize_run(events=[], jobs=jobs, reviews=reviews)
    assert result["jobs"]["total"] == 3
    assert result["jobs"]["repeated_groups"] == 1
    assert result["jobs"]["repeated_attempts"] == 1
    assert result["reviews"]["total"] == 4
    assert result["reviews"]["ignored_count"] == 2
    assert result["reviews"]["ignored_ratio"] == 0.5
