"""Offline efficiency metrics for DAG-guided runs.

Reads event JSON, compute-job JSON and review rows (events/jobs/reviews) and
produces a summary dict. Any source may be missing (None); the output then
marks it ``unavailable`` instead of fabricating zeros. All latency figures are
returned together with their denominators (sample counts) so that missing
data is never confused with zero latency.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

SUPERVISOR_ROLE = "supervisor"
CONSUMPTION_EVENT_TYPES = frozenset({"hub.notification_consumed"})
POST_EVENT_TYPES = frozenset({"hub.posted"})
TERMINAL_RUN_OUTCOMES = frozenset({"succeeded", "failed", "cancelled"})


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _event_data(event: dict) -> dict:
    data = event.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _dedup_events(events: list[dict]) -> tuple[list[dict], int]:
    seen: set[str] = set()
    unique: list[dict] = []
    for event in events:
        event_id = event.get("event_id")
        if event_id is not None:
            if event_id in seen:
                continue
            seen.add(event_id)
        unique.append(event)
    return unique, len(events) - len(unique)


def _supervisor_session_ids(events: list[dict]) -> set[str]:
    ids: set[str] = set()
    for event in events:
        if event.get("type") == "agent.spawned":
            data = _event_data(event)
            if data.get("role_id") == SUPERVISOR_ROLE and data.get("id"):
                ids.add(data["id"])
    return ids


def _run_intervals(events: list[dict], session_ids: set[str]) -> tuple[list[float], int, int]:
    """Sum run.started -> run.finished intervals for the given sessions.

    Returns (durations_seconds, started_count, finished_count).
    """
    starts: dict[tuple[str, str], datetime] = {}
    durations: list[float] = []
    finished_count = 0
    for event in events:
        if event.get("session_id") not in session_ids:
            continue
        etype = event.get("type")
        if etype not in ("run.started", "run.finished"):
            continue
        key = (event.get("session_id"), event.get("run_id"))
        ts = _parse_ts(event.get("created_at"))
        if ts is None:
            continue
        if etype == "run.started":
            starts[key] = ts
        else:
            finished_count += 1
            start = starts.pop(key, None)
            if start is not None and ts >= start:
                durations.append((ts - start).total_seconds())
    return durations, len(starts) + len(durations), finished_count


def _consumption_latency(events: list[dict]) -> tuple[float | None, int, int]:
    """Mean latency from hub.posted to hub.notification_consumed.

    Returns (mean_seconds_or_None, sample_count, unmatched_consumption_count).
    No consumption events means None -- never zero.
    """
    posted: dict[str, datetime] = {}
    for event in events:
        if event.get("type") in POST_EVENT_TYPES:
            data = _event_data(event)
            post_id = data.get("post_id") or data.get("id")
            ts = _parse_ts(event.get("created_at"))
            if post_id and ts is not None:
                posted[str(post_id)] = ts
    samples: list[float] = []
    unmatched = 0
    for event in events:
        if event.get("type") not in CONSUMPTION_EVENT_TYPES:
            continue
        data = _event_data(event)
        consumed_at = _parse_ts(data.get("consumed_at")) or _parse_ts(event.get("created_at"))
        post_id = data.get("post_id")
        posted_at = posted.get(str(post_id)) if post_id is not None else None
        if consumed_at is None or posted_at is None:
            unmatched += 1
            continue
        if consumed_at >= posted_at:
            samples.append((consumed_at - posted_at).total_seconds())
        else:
            unmatched += 1
    if not samples:
        return None, 0, unmatched
    return sum(samples) / len(samples), len(samples), unmatched


def _job_summary(jobs: list[dict]) -> dict:
    by_state = Counter(str(job.get("state")) for job in jobs)
    groups: Counter = Counter()
    for job in jobs:
        key = (job.get("conversation_id"), job.get("path"), job.get("jobtype"))
        groups[key] += 1
    repeated_groups = sum(1 for n in groups.values() if n > 1)
    repeated_attempts = sum(n - 1 for n in groups.values() if n > 1)
    return {
        "total": len(jobs),
        "by_state": dict(by_state),
        "repeated_groups": repeated_groups,
        "repeated_attempts": repeated_attempts,
    }


def _review_summary(reviews: list[dict]) -> dict:
    by_state = Counter(str(review.get("state")) for review in reviews)
    total = len(reviews)
    ignored = by_state.get("ignored", 0)
    return {
        "total": total,
        "by_state": dict(by_state),
        "ignored_count": ignored,
        "ignored_ratio": (ignored / total) if total else None,
    }


def summarize_run(
    events: list[dict] | None,
    jobs: list[dict] | None,
    reviews: list[dict] | None,
) -> dict:
    """Summarize one run's efficiency counters and latencies.

    Each source may be None (unavailable) or a list of row dicts. The result
    always carries the statistics window, counters, latency denominators and
    the list of missing fields.
    """
    unavailable = [
        name
        for name, source in (("events", events), ("jobs", jobs), ("reviews", reviews))
        if source is None
    ]
    missing_fields: list[str] = []
    result: dict[str, Any] = {
        "window": None,
        "unavailable": unavailable,
        "missing_fields": missing_fields,
        "events": None,
        "jobs": None,
        "reviews": None,
        "supervisor": None,
        "message_consumption_latency_seconds": None,
        "consumption_sample_count": 0,
    }

    if jobs is not None:
        result["jobs"] = _job_summary(jobs)
    if reviews is not None:
        result["reviews"] = _review_summary(reviews)
    if events is None:
        return result

    unique_events, duplicates_removed = _dedup_events(events)
    result["events"] = {
        "total": len(unique_events),
        "duplicates_removed": duplicates_removed,
        "by_type": dict(Counter(e.get("type") for e in unique_events)),
    }

    timestamps = [
        ts for ts in (_parse_ts(e.get("created_at")) for e in unique_events) if ts is not None
    ]
    if timestamps:
        start, end = min(timestamps), max(timestamps)
        terminal_seen = any(
            e.get("type") == "run.finished"
            and _event_data(e).get("outcome") in TERMINAL_RUN_OUTCOMES
            and e.get("session_id")
            and e.get("run_id")
            for e in unique_events
        )
        # A window is complete only when the last event is a terminal run
        # finish; anything else means the capture was cut mid-run.
        last_event = max(unique_events, key=lambda e: _parse_ts(e.get("created_at")) or datetime.min.replace(tzinfo=end.tzinfo))
        last_is_terminal = (
            last_event.get("type") == "run.finished"
            and _event_data(last_event).get("outcome") in TERMINAL_RUN_OUTCOMES
        )
        result["window"] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_seconds": (end - start).total_seconds(),
            "complete": bool(terminal_seen and last_is_terminal),
        }
    elif unique_events:
        missing_fields.append("event_timestamps")

    supervisor_ids = _supervisor_session_ids(unique_events)
    durations, started_count, finished_count = _run_intervals(unique_events, supervisor_ids)
    unmatched_runs = started_count - len(durations)
    if unmatched_runs:
        missing_fields.append("supervisor_run_intervals_incomplete")
    wall_clock = result["window"]["duration_seconds"] if result["window"] else None
    result["supervisor"] = {
        "session_count": len(supervisor_ids),
        "run_count": started_count,
        "cumulative_seconds": sum(durations) if durations else (0.0 if started_count == 0 else None),
        "wall_clock_seconds": wall_clock,
    }
    if started_count and not durations:
        missing_fields.append("supervisor_cumulative_seconds")

    mean_latency, sample_count, unmatched_consumption = _consumption_latency(unique_events)
    result["message_consumption_latency_seconds"] = mean_latency
    result["consumption_sample_count"] = sample_count
    if unmatched_consumption:
        missing_fields.append("consumption_events_without_matching_post")

    return result


def main() -> None:  # pragma: no cover - CLI convenience
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", help="Path to events JSON (list of event rows)")
    parser.add_argument("--jobs", help="Path to compute jobs JSON")
    parser.add_argument("--reviews", help="Path to call-review rows JSON")
    args = parser.parse_args()

    def load(path: str | None) -> list[dict] | None:
        if not path:
            return None
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else None

    summary = summarize_run(load(args.events), load(args.jobs), load(args.reviews))
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":  # pragma: no cover
    main()
