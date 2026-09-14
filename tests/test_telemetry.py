"""LLM 遥测：聚合纯函数、导出往返、API 只读路由与认证、model 修复回归。

测试数据用临时 runtime-v2.db（RuntimeStore 真实写入）；conftest 已隔离
data_dir，API 认证默认 off（专项用例内显式覆盖）。
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from cloudra.infra.config import _reset_for_tests
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import EventEnvelope
from cloudra.services import telemetry
from cloudra.services.api_v2 import create_v2_app


def _ev(
    type_,
    data=None,
    *,
    session="s1",
    project="p1",
    run="r1",
    ts="2026-09-10T00:00:00+00:00",
):
    return {
        "event_id": "evt_x",
        "stream": "agent",
        "project_id": project,
        "session_id": session,
        "run_id": run,
        "seq": 1,
        "session_seq": 1,
        "type": type_,
        "data": data or {},
        "created_at": ts,
    }


def _completed(
    prompt,
    completion,
    cached=None,
    *,
    session="s1",
    project="p1",
    model="m1",
    ts="2026-09-10T00:00:00+00:00",
    anthropic_style=False,
):
    usage = {"prompt_tokens": prompt, "completion_tokens": completion,
             "total_tokens": prompt + completion}
    if cached is not None:
        if anthropic_style:
            usage["prompt_cache_hit_tokens"] = cached
        else:
            usage["prompt_tokens_details"] = {"cached_tokens": cached}
    return _ev("llm.completed", {"model": model, "usage": usage, "finish_reason": "stop"},
               session=session, project=project, ts=ts)


# ---------------------------------------------------------------------------
# usage 归一化
# ---------------------------------------------------------------------------


def test_cached_tokens_openai_style():
    call = telemetry.llm_call_from_event(_completed(100, 10, cached=40))
    assert call["cached_tokens"] == 40
    assert call["missed_tokens"] == 60


def test_cached_tokens_anthropic_style():
    call = telemetry.llm_call_from_event(_completed(100, 10, cached=30, anthropic_style=True))
    assert call["cached_tokens"] == 30


def test_llm_call_missing_usage_tolerated():
    call = telemetry.llm_call_from_event(_ev("llm.completed", {"model": "m", "usage": {}}))
    assert call is not None
    assert call["prompt_tokens"] == 0 and call["has_usage"] is False
    # 非 dict usage / 缺 model 同样容错进 unknown 桶
    call = telemetry.llm_call_from_event(_ev("llm.completed", {"usage": "broken"}))
    assert call["model"] == telemetry.UNKNOWN_MODEL
    assert call["has_usage"] is False


def test_llm_call_ignores_other_event_types():
    assert telemetry.llm_call_from_event(_ev("llm.request_started", {"model": "m"})) is None
    assert telemetry.llm_call_from_event(_ev("tool.finished", {})) is None


# ---------------------------------------------------------------------------
# token 聚合
# ---------------------------------------------------------------------------


def test_aggregate_tokens_by_agent_and_project():
    events = [
        _completed(100, 10, cached=50, session="s1", project="p1",
                   ts="2026-09-10T01:00:00+00:00"),
        _completed(200, 20, cached=100, session="s1", project="p1",
                   ts="2026-09-10T02:00:00+00:00"),
        _completed(300, 30, cached=0, session="s2", project="p1", model="m2",
                   ts="2026-09-11T01:00:00+00:00"),
        _completed(400, 40, cached=200, session="s3", project="p2",
                   ts="2026-09-12T01:00:00+00:00"),
    ]
    report = telemetry.aggregate_tokens(events)

    totals = report["totals"]
    assert totals["requests"] == 4
    assert totals["sessions"] == 3 and totals["projects"] == 2
    assert totals["prompt_tokens"] == 1000 and totals["cached_tokens"] == 350
    assert totals["completion_tokens"] == 100
    assert abs(totals["hit_rate"] - 0.35) < 1e-9

    agents = {a["session_id"]: a for a in report["agents"]}
    assert agents["s1"]["requests"] == 2 and agents["s1"]["prompt_tokens"] == 300
    assert agents["s1"]["first_request_at"] == "2026-09-10T01:00:00+00:00"
    assert agents["s1"]["last_request_at"] == "2026-09-10T02:00:00+00:00"
    assert abs(agents["s1"]["hit_rate"] - 0.5) < 1e-9

    projects = {p["project_id"]: p for p in report["projects"]}
    assert projects["p1"]["sessions"] == 2 and projects["p1"]["requests"] == 3
    assert projects["p2"]["sessions"] == 1


def test_aggregate_tokens_time_range_filter():
    events = [
        _completed(100, 10, ts="2026-09-10T00:00:00+00:00"),
        _completed(200, 20, ts="2026-09-11T00:00:00+00:00"),
        _completed(400, 40, ts="2026-09-12T00:00:00+00:00"),
    ]
    report = telemetry.aggregate_tokens(
        events, since="2026-09-11T00:00:00+00:00", until="2026-09-11T23:59:59+00:00"
    )
    assert report["totals"]["requests"] == 1
    assert report["totals"]["prompt_tokens"] == 200


def test_aggregate_tokens_empty_events():
    report = telemetry.aggregate_tokens([])
    assert report["totals"]["requests"] == 0
    assert report["totals"]["hit_rate"] == 0.0
    assert report["agents"] == [] and report["projects"] == []


# ---------------------------------------------------------------------------
# 缓存分析
# ---------------------------------------------------------------------------


def _session_calls(session, count, *, prompt=100, cached=50, day="2026-09-10"):
    return [
        _completed(prompt, 10, cached=cached, session=session,
                   ts=f"{day}T{i % 24:02d}:00:00+00:00")
        for i in range(count)
    ]


def test_analyze_cache_request_buckets_and_models():
    events = []
    events += _session_calls("s_short", 2)                       # 1-4 桶
    events += _session_calls("s_mid", 7)                         # 5-9 桶
    events += _session_calls("s_long", 12)                       # 10-19 桶
    events += _session_calls("s_xlong", 25)                      # 20-49 桶
    events += _session_calls("s_huge", 60)                       # 50+ 桶
    # model 缺失的历史数据进 unknown 桶
    events.append(_ev("llm.completed", {"usage": {"prompt_tokens": 80, "completion_tokens": 5}},
                      session="s_short"))

    report = telemetry.analyze_cache(events)
    buckets = {b["bucket"]: b for b in report["by_request_bucket"]}
    assert buckets["1-4"]["sessions"] == 1 and buckets["1-4"]["requests"] == 3
    assert buckets["5-9"]["requests"] == 7
    assert buckets["10-19"]["requests"] == 12
    assert buckets["20-49"]["requests"] == 25
    assert buckets["50+"]["sessions"] == 1 and buckets["50+"]["requests"] == 60
    # 1-4 桶命中率：cached 2*50 / prompt (2*100 + 80)
    assert abs(buckets["1-4"]["hit_rate"] - 100 / 280) < 1e-9

    models = {m["model"]: m for m in report["by_model"]}
    assert models["m1"]["requests"] == 106
    assert models[telemetry.UNKNOWN_MODEL]["requests"] == 1

    overall = report["overall"]
    assert overall["requests"] == 107


def test_analyze_cache_by_day_and_miss_distribution():
    events = (
        _session_calls("s1", 3, day="2026-09-10")
        + _session_calls("s2", 2, prompt=200, cached=0, day="2026-09-11")
    )
    report = telemetry.analyze_cache(events)
    days = {d["day"]: d for d in report["by_day"]}
    assert days["2026-09-10"]["requests"] == 3
    assert days["2026-09-11"]["hit_rate"] == 0.0

    # 每请求未命中量：s1 三条各 50，s2 两条各 200
    dist = report["miss_distribution"]
    assert dist["count"] == 5
    assert dist["median"] == 50.0
    assert dist["max"] == 200
    assert dist["p90"] > dist["median"]

    top = report["top_misses"]
    assert top[0]["missed_tokens"] == 200 and top[0]["session_id"] == "s2"
    assert top[-1]["missed_tokens"] == 50


def test_analyze_cache_empty():
    report = telemetry.analyze_cache([])
    assert report["overall"]["requests"] == 0
    assert report["miss_distribution"]["count"] == 0
    assert report["top_misses"] == []


# ---------------------------------------------------------------------------
# 导出往返（临时 RuntimeStore）
# ---------------------------------------------------------------------------


def _envelope(seq, type_, data, *, session="s1", project="p1"):
    return EventEnvelope(
        stream="agent",
        project_id=project,
        session_id=session,
        run_id="r1",
        seq=seq,
        session_seq=seq,
        type=type_,
        data=data,
        created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )


@pytest.fixture
def store(tmp_path):
    return RuntimeStore(tmp_path / "runtime-v2.db")


def test_session_export_roundtrip(store, tmp_path):
    store.append_event(_envelope(1, "agent.spawned", {
        "id": "s1", "role_id": "coordinator", "display_name": "Coordinator",
        "parent_session_id": None, "created_at": "2026-09-10T00:00:00Z",
    }))
    store.append_event(_envelope(2, "context.prefix_installed",
                                 {"messages": [{"role": "system", "content": "prefix"}]}))
    store.append_event(_envelope(3, "context.appended",
                                 {"messages": [{"role": "user", "content": "hello"}]}))
    store.append_event(_envelope(4, "llm.completed", {
        "model": "m1",
        "usage": {"prompt_tokens": 100, "completion_tokens": 10,
                  "prompt_tokens_details": {"cached_tokens": 60}},
    }))
    store.append_event(_envelope(5, "context.compacted",
                                 {"messages": [{"role": "system", "content": "compacted"}]}))
    store.append_event(_envelope(6, "context.appended",
                                 {"messages": [{"role": "assistant", "content": "after"}]}))

    out = tmp_path / "s1.jsonl"
    count = telemetry.write_session_jsonl(store.path, "s1", out)
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert count == len(records)

    meta = records[0]
    assert meta["type"] == "meta" and meta["session_id"] == "s1"
    assert meta["project_id"] == "p1"
    assert meta["agent"]["role_id"] == "coordinator"
    assert meta["event_count"] == 6 and meta["llm_calls"] == 1

    events = [r for r in records if r["type"] == "event"]
    assert [e["event_type"] for e in events] == [
        "agent.spawned", "context.prefix_installed", "context.appended",
        "llm.completed", "context.compacted", "context.appended",
    ]
    assert [e["seq"] for e in events] == [1, 2, 3, 4, 5, 6]

    context = next(r for r in records if r["type"] == "context")
    # compacted 原子替换后只剩 compact 快照 + 其后的 append
    assert [m["content"] for m in context["messages"]] == ["compacted", "after"]
    assert context["message_count"] == 2

    usage = [r for r in records if r["type"] == "usage"]
    assert len(usage) == 1
    assert usage[0]["cached_tokens"] == 60 and usage[0]["missed_tokens"] == 40


def test_rebuild_context_reset_clears():
    events = [
        _ev("context.prefix_installed", {"messages": [{"role": "system", "content": "a"}]}),
        _ev("agent.context_reset", {}),
        _ev("context.appended", {"messages": [{"role": "user", "content": "b"}]}),
    ]
    assert [m["content"] for m in telemetry.rebuild_context(events)] == ["b"]


def test_project_export_zip_roundtrip(store, tmp_path):
    for seq, sid in ((1, "s1"), (2, "s2")):
        store.append_event(_envelope(seq, "llm.completed", {
            "model": "m1", "usage": {"prompt_tokens": 10, "completion_tokens": 1},
        }, session=sid))
    store.append_event(_envelope(3, "llm.completed", {
        "model": "m1", "usage": {"prompt_tokens": 5, "completion_tokens": 1},
    }, session="other", project="p2"))

    out = tmp_path / "p1.zip"
    report = telemetry.write_project_zip(store.path, "p1", out)
    assert report["sessions"] == 2
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == ["s1.jsonl", "s2.jsonl"]
        records = [json.loads(line) for line in zf.read("s1.jsonl").decode().splitlines()]
    assert records[0]["type"] == "meta" and records[0]["session_id"] == "s1"


def test_export_unknown_ids_raise(store, tmp_path):
    with pytest.raises(telemetry.TelemetryError):
        telemetry.build_session_export(store.path, "nope")
    with pytest.raises(telemetry.TelemetryError):
        telemetry.write_project_zip(store.path, "nope", tmp_path / "x.zip")
    with pytest.raises(telemetry.TelemetryError):
        telemetry.resolve_export_target(store.path, "nope")
    store.append_event(_envelope(1, "llm.completed", {"usage": {}}, session="s1"))
    assert telemetry.resolve_export_target(store.path, "s1") == "session"
    assert telemetry.resolve_export_target(store.path, "p1") == "project"


def test_missing_db_raises(tmp_path):
    with pytest.raises(telemetry.TelemetryError):
        telemetry.load_events(tmp_path / "absent.db")


def test_token_and_cache_summary_on_empty_db(store):
    assert telemetry.token_summary(store.path)["totals"]["requests"] == 0
    assert telemetry.cache_summary(store.path)["overall"]["requests"] == 0


def test_readonly_connection_does_not_create_db(tmp_path):
    missing = tmp_path / "ro.db"
    with pytest.raises(telemetry.TelemetryError):
        telemetry.load_events(missing)
    assert not missing.exists()


def test_readonly_connection_sets_busy_timeout(store):
    """只读连接也要 busy_timeout：库被写者短暂持锁时等待而非 5s 后报
    database is locked。"""
    con = telemetry._connect_readonly(store.path)
    try:
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 60000
    finally:
        con.close()


def test_reader_not_blocked_by_open_write_transaction(store):
    """WAL 下只读全表扫不被未提交写事务阻塞（回滚日志模式会 database is
    locked，正是 telemetry 面板拖垮会话的机理）。"""
    writer = sqlite3.connect(store.path, timeout=5.0)
    try:
        writer.execute("BEGIN IMMEDIATE")
        assert telemetry.load_events(store.path) == []
    finally:
        writer.rollback()
        writer.close()


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------


@pytest.fixture
def populated_store(tmp_path):
    store = RuntimeStore(tmp_path / "runtime-v2.db")
    store.append_event(_envelope(1, "context.prefix_installed",
                                 {"messages": [{"role": "system", "content": "p"}]}))
    store.append_event(_envelope(2, "llm.completed", {
        "model": "m1",
        "usage": {"prompt_tokens": 100, "completion_tokens": 10,
                  "prompt_cache_hit_tokens": 40},
    }))
    return store


def test_api_tokens_and_cache(populated_store):
    client = TestClient(create_v2_app(store_path=populated_store.path))
    resp = client.get("/api/v2/telemetry/tokens")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["requests"] == 1
    assert body["totals"]["cached_tokens"] == 40
    assert body["agents"][0]["session_id"] == "s1"

    resp = client.get("/api/v2/telemetry/cache")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall"]["requests"] == 1
    assert body["by_model"][0]["model"] == "m1"
    assert body["by_request_bucket"][0]["bucket"] == "1-4"


def test_api_export_session_download(populated_store):
    client = TestClient(create_v2_app(store_path=populated_store.path))
    resp = client.get("/api/v2/telemetry/export/session/s1")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert "s1.jsonl" in resp.headers["content-disposition"]
    records = [json.loads(line) for line in resp.text.splitlines()]
    assert records[0]["type"] == "meta"
    assert any(r["type"] == "usage" for r in records)

    resp = client.get("/api/v2/telemetry/export/session/absent")
    assert resp.status_code == 404


def test_api_export_project_download(populated_store):
    client = TestClient(create_v2_app(store_path=populated_store.path))
    resp = client.get("/api/v2/telemetry/export/project/p1")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].endswith('"p1.zip"')
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert zf.namelist() == ["s1.jsonl"]
    assert client.get("/api/v2/telemetry/export/project/absent").status_code == 404


def test_api_telemetry_auth_enforced(populated_store, monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "telemetry-secret")
    try:
        client = TestClient(create_v2_app(store_path=populated_store.path))
        assert client.get("/api/v2/telemetry/tokens").status_code == 401
        assert client.get("/api/v2/telemetry/cache").status_code == 401
        assert client.get("/api/v2/telemetry/export/session/s1").status_code == 401
        headers = {"Authorization": "Bearer telemetry-secret"}
        assert client.get("/api/v2/telemetry/tokens", headers=headers).status_code == 200
        # ?token= query 兜底（下载链接无法带 Authorization 头）
        assert client.get("/api/v2/telemetry/export/session/s1?token=telemetry-secret").status_code == 200
    finally:
        _reset_for_tests()


# ---------------------------------------------------------------------------
# model 修复回归：llm.request_started / llm.completed 记录生效模型
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_records_effective_model_via_provider_hook():
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.schemas import (
        AgentCapabilities,
        Command,
        InvocationProtocol,
        PermissionSet,
        RuntimeSettings,
    )
    from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

    core = RuntimeCore(strict_events=True)
    await CommandBus(core).execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    agent = next(iter(core.agents.values()))
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    assert agent.settings.model == ""  # spawn 快照为空：生产 bug 的现场

    class BridgeLLM:
        """模拟 LegacyLLMProvider：空快照模型由桥接层从配置补全。"""

        def resolve_effective_settings(self, agent):
            return RuntimeSettings(model="resolved-model")

        async def complete(self, agent, messages, tools, **_kwargs):
            return LLMResponse(content="done", stop_requested=True,
                               usage={"prompt_tokens": 1})

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=BridgeLLM(),
        tools=None,
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_model",
        settings=agent.settings.model_copy(deep=True),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[], can_spawn=False),
        inbox_messages=[{"content": "hi"}],
    )
    events = list(core.event_log.query_session(agent.id))
    started = next(e for e in events if e.type == "llm.request_started")
    completed = next(e for e in events if e.type == "llm.completed")
    assert started.data["model"] == "resolved-model"
    assert completed.data["model"] == "resolved-model"


@pytest.mark.asyncio
async def test_run_turn_without_hook_keeps_snapshot_model():
    """无钩子的 provider（测试 fake）原样记快照值——显式 model 不被覆盖。"""
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.schemas import (
        AgentCapabilities,
        Command,
        InvocationProtocol,
        PermissionSet,
        RuntimeSettings,
    )
    from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

    core = RuntimeCore(strict_events=True)
    await CommandBus(core).execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    agent = next(iter(core.agents.values()))
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL

    class PlainLLM:
        async def complete(self, agent, messages, tools, **_kwargs):
            return LLMResponse(content="done", stop_requested=True)

    pipeline = TurnPipeline(
        event_log=core.event_log, stages=default_stages(), llm=PlainLLM(), tools=None
    )
    await pipeline.run_turn(
        agent=agent,
        run_id="run_plain",
        settings=RuntimeSettings(model="explicit-model"),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[], can_spawn=False),
        inbox_messages=[{"content": "hi"}],
    )
    events = list(core.event_log.query_session(agent.id))
    started = next(e for e in events if e.type == "llm.request_started")
    assert started.data["model"] == "explicit-model"
