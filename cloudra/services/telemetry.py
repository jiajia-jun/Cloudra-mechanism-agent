"""LLM 遥测：runtime-v2.db 事件流上的只读聚合与导出。

数据基础：``events`` 表里每次 LLM 调用落一条 ``llm.completed``
（``data.usage`` 原样携带 provider 缓存细项）与 ``llm.request_started``；
会话上下文投影由 ``context.prefix_installed`` / ``context.appended`` /
``context.compacted`` / ``agent.context_reset`` 事件溯源，可离线重建。

聚合核心是纯函数（吃 events 字典列表 → 出聚合结果），SQLite 读取集中
在 ``load_events``，且一律用 ``mode=ro`` 只读连接——导出/统计绝不给
运行中的库加写锁。CLI（``cloudra stats``）与 api_v2 遥测路由都只是
本模块的薄壳。本模块只做同步 IO，事件循环内调用方一律
``asyncio.to_thread``。
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

UNKNOWN_MODEL = "unknown"

# 按 session 请求数分桶（区分"短会话冷启动摊不掉"与"长会话 TTL 过期"）。
REQUEST_COUNT_BUCKETS: tuple[tuple[str, int, Optional[int]], ...] = (
    ("1-4", 1, 4),
    ("5-9", 5, 9),
    ("10-19", 10, 19),
    ("20-49", 20, 49),
    ("50+", 50, None),
)

_EVENT_COLUMNS = (
    "event_id", "stream", "project_id", "session_id", "run_id",
    "seq", "session_seq", "type", "data", "created_at",
)


class TelemetryError(Exception):
    """遥测只读查询的结构化失败（缺库 / 未知 session 或 project）。"""


# ---------------------------------------------------------------------------
# 纯函数：usage 归一化与事件提取
# ---------------------------------------------------------------------------


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def cached_tokens_of(usage: dict[str, Any]) -> int:
    """归一化两种 provider 缓存细项形态。

    - Anthropic 风格：``prompt_cache_hit_tokens`` 顶层字段；
    - OpenAI 风格：``prompt_tokens_details.cached_tokens`` 嵌套。
    """
    hit = _to_int(usage.get("prompt_cache_hit_tokens"))
    if hit is not None:
        return hit
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached = _to_int(details.get("cached_tokens"))
        if cached is not None:
            return cached
    return 0


def llm_call_from_event(event: dict[str, Any]) -> Optional[dict[str, Any]]:
    """``llm.completed`` 事件 → 归一化调用记录；其它类型返回 None。

    缺/坏 usage 容错：token 字段按 0 计，``has_usage=False``；model 缺失
    （历史数据 bug 期）归进 ``unknown`` 桶。
    """
    if event.get("type") != "llm.completed":
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        data = {}
    usage = data.get("usage")
    has_usage = isinstance(usage, dict) and bool(usage)
    usage = usage if isinstance(usage, dict) else {}
    prompt = _to_int(usage.get("prompt_tokens")) or 0
    completion = _to_int(usage.get("completion_tokens")) or 0
    cached = cached_tokens_of(usage)
    model = data.get("model")
    return {
        "session_id": event.get("session_id"),
        "project_id": event.get("project_id"),
        "run_id": event.get("run_id"),
        "created_at": event.get("created_at"),
        "model": model if isinstance(model, str) and model else UNKNOWN_MODEL,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "missed_tokens": max(prompt - cached, 0),
        "total_tokens": _to_int(usage.get("total_tokens")) or (prompt + completion),
        "latency_ms": _to_int(data.get("latency_ms")),
        "finish_reason": data.get("finish_reason"),
        "has_usage": has_usage,
    }


def extract_llm_calls(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [call for call in (llm_call_from_event(e) for e in events) if call is not None]


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _in_range(call: dict[str, Any], since: Optional[str], until: Optional[str]) -> bool:
    ts = _parse_iso(call.get("created_at"))
    if ts is None:
        # 无时间戳的记录不被时间过滤误杀（仍计入全量聚合）。
        return since is None and until is None
    if since is not None:
        bound = _parse_iso(since)
        if bound is not None and ts < bound:
            return False
    if until is not None:
        bound = _parse_iso(until)
        if bound is not None and ts > bound:
            return False
    return True


def _percentile(sorted_values: list[int], q: float) -> float:
    """线性插值分位数（与 numpy 默认口径一致）；空列表由调用方拦截。"""
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    frac = pos - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * frac


def _aggregate_group(calls: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = sum(c["prompt_tokens"] for c in calls)
    cached = sum(c["cached_tokens"] for c in calls)
    timestamps = sorted(
        c["created_at"] for c in calls if isinstance(c.get("created_at"), str) and c["created_at"]
    )
    return {
        "requests": len(calls),
        "prompt_tokens": prompt,
        "completion_tokens": sum(c["completion_tokens"] for c in calls),
        "cached_tokens": cached,
        "total_tokens": sum(c["total_tokens"] for c in calls),
        "hit_rate": (cached / prompt) if prompt else 0.0,
        "first_request_at": timestamps[0] if timestamps else None,
        "last_request_at": timestamps[-1] if timestamps else None,
    }


# ---------------------------------------------------------------------------
# 纯函数：token 聚合
# ---------------------------------------------------------------------------


def aggregate_tokens(
    events: Iterable[dict[str, Any]],
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict[str, Any]:
    """按 agent（session）与 project 聚合 token 用量。"""
    calls = [c for c in extract_llm_calls(events) if _in_range(c, since, until)]

    by_session: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        by_session.setdefault(str(call.get("session_id") or "unknown"), []).append(call)

    agents = []
    for session_id, group in by_session.items():
        entry = {"session_id": session_id, "project_id": group[0].get("project_id")}
        entry.update(_aggregate_group(group))
        agents.append(entry)
    agents.sort(key=lambda a: -a["prompt_tokens"])

    by_project: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        by_project.setdefault(str(call.get("project_id") or "unknown"), []).append(call)

    projects = []
    for project_id, group in by_project.items():
        entry = {
            "project_id": project_id,
            "sessions": len({str(c.get("session_id")) for c in group}),
        }
        entry.update(_aggregate_group(group))
        projects.append(entry)
    projects.sort(key=lambda p: -p["prompt_tokens"])

    totals = _aggregate_group(calls)
    totals["sessions"] = len(by_session)
    totals["projects"] = len(by_project)
    return {"since": since, "until": until, "totals": totals, "agents": agents, "projects": projects}


# ---------------------------------------------------------------------------
# 纯函数：缓存分析
# ---------------------------------------------------------------------------


def analyze_cache(
    events: Iterable[dict[str, Any]],
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """缓存命中分析：总体/按日/按 session 请求数分桶/按模型 + 未命中分布。"""
    calls = [c for c in extract_llm_calls(events) if _in_range(c, since, until)]

    overall = _aggregate_group(calls)

    by_day: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        created = call.get("created_at")
        day = created.partition("T")[0] if isinstance(created, str) else ""
        by_day.setdefault(day or "unknown", []).append(call)
    days = [
        {"day": day, **_aggregate_group(group)}
        for day, group in sorted(by_day.items())
    ]

    # session 请求数分桶：先数每个 session 的请求数，再把该 session 的全部
    # 调用归入对应桶（桶内命中率 = 桶内总 cached / 总 prompt）。
    session_counts: dict[str, int] = {}
    for call in calls:
        key = str(call.get("session_id") or "unknown")
        session_counts[key] = session_counts.get(key, 0) + 1
    bucket_calls: dict[str, list[dict[str, Any]]] = {label: [] for label, _, _ in REQUEST_COUNT_BUCKETS}
    bucket_sessions: dict[str, set[str]] = {label: set() for label, _, _ in REQUEST_COUNT_BUCKETS}
    for call in calls:
        session_key = str(call.get("session_id") or "unknown")
        count = session_counts[session_key]
        for label, low, high in REQUEST_COUNT_BUCKETS:
            if count >= low and (high is None or count <= high):
                bucket_calls[label].append(call)
                bucket_sessions[label].add(session_key)
                break
    buckets = [
        {"bucket": label, "sessions": len(bucket_sessions[label]), **_aggregate_group(bucket_calls[label])}
        for label, _, _ in REQUEST_COUNT_BUCKETS
    ]

    by_model: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        by_model.setdefault(str(call["model"]), []).append(call)
    models = [
        {"model": model, **_aggregate_group(group)}
        for model, group in by_model.items()
    ]
    models.sort(key=lambda m: -m["prompt_tokens"])

    missed = sorted(c["missed_tokens"] for c in calls if c["prompt_tokens"] > 0)
    if missed:
        miss_distribution = {
            "count": len(missed),
            "median": _percentile(missed, 0.5),
            "p90": _percentile(missed, 0.9),
            "p99": _percentile(missed, 0.99),
            "max": missed[-1],
        }
    else:
        miss_distribution = {"count": 0, "median": 0.0, "p90": 0.0, "p99": 0.0, "max": 0}

    top_misses = sorted(
        (c for c in calls if c["missed_tokens"] > 0),
        key=lambda c: -c["missed_tokens"],
    )[: max(top_n, 0)]
    top_miss_records = [
        {
            "created_at": c.get("created_at"),
            "session_id": c.get("session_id"),
            "project_id": c.get("project_id"),
            "model": c["model"],
            "prompt_tokens": c["prompt_tokens"],
            "cached_tokens": c["cached_tokens"],
            "missed_tokens": c["missed_tokens"],
        }
        for c in top_misses
    ]

    return {
        "since": since,
        "until": until,
        "overall": overall,
        "by_day": days,
        "by_request_bucket": buckets,
        "miss_distribution": miss_distribution,
        "top_misses": top_miss_records,
        "by_model": models,
    }


# ---------------------------------------------------------------------------
# 只读 SQLite 读取
# ---------------------------------------------------------------------------


def _connect_readonly(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.is_file():
        raise TelemetryError(f"runtime database not found: {path}")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def load_events(
    db_path: Path | str,
    *,
    session_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """按 rowid（全局追加序）读出事件流；data 反序列化为 dict。"""
    clauses: list[str] = []
    params: list[Any] = []
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(session_id)
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(project_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect_readonly(db_path) as con:
        rows = con.execute(
            f"SELECT {', '.join(_EVENT_COLUMNS)} FROM events {where} ORDER BY rowid",
            params,
        ).fetchall()
    events = []
    for row in rows:
        record = dict(zip(_EVENT_COLUMNS, row))
        try:
            record["data"] = json.loads(record["data"])
        except (json.JSONDecodeError, TypeError):
            record["data"] = {}
        events.append(record)
    return events


def list_session_ids(db_path: Path | str, *, project_id: Optional[str] = None) -> list[str]:
    clauses = "WHERE session_id IS NOT NULL"
    params: list[Any] = []
    if project_id is not None:
        clauses += " AND project_id = ?"
        params.append(project_id)
    with _connect_readonly(db_path) as con:
        rows = con.execute(
            f"SELECT DISTINCT session_id FROM events {clauses} ORDER BY session_id",
            params,
        ).fetchall()
    return [row[0] for row in rows]


def _session_exists(db_path: Path | str, session_id: str) -> bool:
    with _connect_readonly(db_path) as con:
        row = con.execute(
            "SELECT 1 FROM events WHERE session_id = ? LIMIT 1", (session_id,)
        ).fetchone()
    return row is not None


def _project_exists(db_path: Path | str, project_id: str) -> bool:
    with _connect_readonly(db_path) as con:
        row = con.execute(
            "SELECT 1 FROM events WHERE project_id = ? LIMIT 1", (project_id,)
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# 服务层入口（CLI / API 共用）
# ---------------------------------------------------------------------------


def token_summary(
    db_path: Path | str, *, since: Optional[str] = None, until: Optional[str] = None
) -> dict[str, Any]:
    return aggregate_tokens(load_events(db_path), since=since, until=until)


def cache_summary(
    db_path: Path | str,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    top_n: int = 20,
) -> dict[str, Any]:
    return analyze_cache(load_events(db_path), since=since, until=until, top_n=top_n)


# ---------------------------------------------------------------------------
# 导出（全量 context 分析包）
# ---------------------------------------------------------------------------


def rebuild_context(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """从投影事件重放重建最终上下文快照（与 runtime_v2 apply 同一语义）。"""
    messages: list[dict[str, Any]] = []
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        etype = event.get("type")
        if etype == "context.prefix_installed":
            installed = [dict(m) for m in data.get("messages") or [] if isinstance(m, dict)]
            messages = [*installed, *messages]
        elif etype == "context.appended":
            messages.extend(dict(m) for m in data.get("messages") or [] if isinstance(m, dict))
        elif etype == "context.compacted":
            messages = [dict(m) for m in data.get("messages") or [] if isinstance(m, dict)]
        elif etype == "agent.context_reset":
            messages = []
    return messages


def build_session_export(db_path: Path | str, session_id: str) -> list[dict[str, Any]]:
    """一个 session 的完整分析包记录（meta → events → context → usage）。"""
    events = load_events(db_path, session_id=session_id)
    if not events:
        raise TelemetryError(f"unknown session: {session_id}")
    project_id = events[0].get("project_id")

    agent_meta: dict[str, Any] = {}
    for event in events:
        if event["type"] == "agent.spawned" and isinstance(event.get("data"), dict):
            data = event["data"]
            agent_meta = {
                "role_id": data.get("role_id"),
                "display_name": data.get("display_name"),
                "parent_session_id": data.get("parent_session_id"),
                "created_at": data.get("created_at"),
            }
            break

    context = rebuild_context(events)
    usage_records = extract_llm_calls(events)

    records: list[dict[str, Any]] = [
        {
            "type": "meta",
            "kind": "session",
            "session_id": session_id,
            "project_id": project_id,
            "agent": agent_meta,
            "event_count": len(events),
            "llm_calls": len(usage_records),
            "context_messages": len(context),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    records.extend(
        {
            "type": "event",
            "event_type": event["type"],
            **{k: v for k, v in event.items() if k != "type"},
        }
        for event in events
    )
    records.append(
        {"type": "context", "session_id": session_id, "message_count": len(context), "messages": context}
    )
    records.extend({"type": "usage", **call} for call in usage_records)
    return records


def write_session_jsonl(db_path: Path | str, session_id: str, out_path: Path | str) -> int:
    """导出单个 session 为 JSONL；返回记录条数。"""
    records = build_session_export(db_path, session_id)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)


def build_project_zip_bytes(db_path: Path | str, project_id: str) -> bytes:
    """一个 project 下所有 session 的分析包（每 session 一个 JSONL，打成 zip）。"""
    import io

    if not _project_exists(db_path, project_id):
        raise TelemetryError(f"unknown project: {project_id}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for sid in list_session_ids(db_path, project_id=project_id):
            records = build_session_export(db_path, sid)
            payload = "".join(
                json.dumps(record, ensure_ascii=False) + "\n" for record in records
            )
            zf.writestr(f"{sid}.jsonl", payload)
    return buffer.getvalue()


def write_project_zip(db_path: Path | str, project_id: str, out_path: Path | str) -> dict[str, int]:
    """导出一个 project 下所有 session 的包（每 session 一个 JSONL，打成 zip）。"""
    payload = build_project_zip_bytes(db_path, project_id)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    return {"sessions": len(list_session_ids(db_path, project_id=project_id))}


def resolve_export_target(db_path: Path | str, ident: str) -> str:
    """把 CLI/API 传入的 id 解析为 'session' 或 'project'；都不存在则报错。"""
    if _session_exists(db_path, ident):
        return "session"
    if _project_exists(db_path, ident):
        return "project"
    raise TelemetryError(f"unknown session or project: {ident}")
