"""Agent 行为遥测（评审 5.7）：纯事件聚合 + CLI/API 同口径。

数据用临时 runtime-v2.db（RuntimeStore 真实写入）；conftest 已隔离 data_dir。
断言只针对结构化字段，不依赖渲染文本；隐私断言确保工具原始结果/提示词文本
不被复制进聚合结果。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from cloudra.cli import cli
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import EventEnvelope
from cloudra.services import telemetry
from cloudra.services.api_v2 import create_v2_app

_BASE = datetime(2026, 9, 10, tzinfo=timezone.utc)


def _ev(type_, data=None, *, session="s1", project="p1", run="r1", offset_s=0):
    """纯函数吃的 dict 事件（形状同 telemetry.load_events 的输出）。"""
    return {
        "event_id": f"evt_{type_}_{offset_s}",
        "stream": "agent",
        "project_id": project,
        "session_id": session,
        "run_id": run,
        "seq": 1,
        "session_seq": 1,
        "type": type_,
        "data": data or {},
        "created_at": (_BASE + timedelta(seconds=offset_s)).isoformat(),
    }


def _llm(prompt, completion, *, kind="agent", offset_s=0, session="s1", run="r1"):
    return _ev(
        "llm.completed",
        {
            "model": "m1",
            "kind": kind,
            "latency_ms": 500,
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            },
        },
        offset_s=offset_s,
        session=session,
        run=run,
    )


def test_aggregate_agents_counts_runs_tools_and_failure_kinds():
    events = [
        _ev("run.started", {}, offset_s=0),
        _llm(100, 10, offset_s=1),
        _ev("tool.finished", {"tool_name": "bash", "status": "completed"}, offset_s=2),
        _ev("tool.finished", {"tool_name": "bash", "status": "failed"}, offset_s=3),
        _ev("tool.blocked", {"tool_name": "rm", "stage": "permission"}, offset_s=4),
        _ev("run.finished", {"outcome": "failed", "failure_kind": "pipeline_internal"}, offset_s=5),
        # 第二个 run：成功
        _ev("run.started", {}, run="r2", offset_s=6),
        _llm(50, 5, run="r2", offset_s=7),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, run="r2", offset_s=8),
    ]
    report = telemetry.aggregate_agents(events)

    totals = report["totals"]
    assert totals["sessions"] == 1
    assert totals["runs"]["total"] == 2
    assert totals["runs"]["succeeded"] == 1
    assert totals["runs"]["failed"] == 1
    assert totals["runs"]["failure_kinds"] == {"pipeline_internal": 1}
    assert totals["tools"]["calls"] == 2
    assert totals["tools"]["by_status"] == {"completed": 1, "failed": 1}
    assert totals["tools"]["blocked"] == 1
    assert totals["llm"]["total_tokens"] == 165

    assert len(report["agents"]) == 1
    assert report["agents"][0]["session_id"] == "s1"
    assert report["agents"][0]["metrics"]["runs"]["total"] == 2


def test_aggregate_agents_flags_high_token_runs_without_tool_progress():
    events = [
        _ev("run.started", {}, offset_s=0),
        _llm(5000, 500, offset_s=1),
        _llm(6000, 500, offset_s=2),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, offset_s=3),
        _ev("run.started", {}, run="r2", offset_s=4),
        _llm(10, 5, run="r2", offset_s=5),
        _ev("tool.finished", {"tool_name": "bash", "status": "completed"}, run="r2", offset_s=6),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, run="r2", offset_s=7),
    ]
    report = telemetry.aggregate_agents(events)
    rows = {row["run_id"]: row for row in report["runs"]}
    # token 降序：烧得最多又没工具进展的 run 排在第一条。
    assert [row["run_id"] for row in report["runs"]] == ["r1", "r2"]
    assert rows["r1"]["no_tool_progress"] is True
    assert rows["r2"]["no_tool_progress"] is False
    assert rows["r1"]["duration_ms"] == 3000
    assert rows["r1"]["outcome"] == "succeeded"


def test_aggregate_agents_counts_cancelled_run_without_run_finished():
    events = [
        _ev("run.started", {}, offset_s=0),
        _llm(10, 1, offset_s=1),
        _ev("agent.cancelled", {"session_id": "s1"}, offset_s=2),
    ]
    report = telemetry.aggregate_agents(events)
    assert report["totals"]["runs"]["total"] == 1
    assert report["totals"]["runs"]["cancelled"] == 1
    row = report["runs"][0]
    assert row["outcome"] == "cancelled"
    assert row["duration_ms"] == 2000


def test_aggregate_agents_separates_summary_from_agent_requests():
    events = [
        _ev("run.started", {}, offset_s=0),
        _llm(100, 10, offset_s=1),
        _llm(200, 20, kind="summary", offset_s=2),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, offset_s=3),
    ]
    llm = telemetry.aggregate_agents(events)["totals"]["llm"]
    assert llm["requests"] == 2
    assert llm["agent_requests"] == 1
    assert llm["summary_requests"] == 1
    # 压缩成本计入总量，但单列出来。
    assert llm["total_tokens"] == 330


def test_aggregate_agents_reports_gate_compaction_subagents_hub_and_waits():
    events = [
        _ev("run.started", {}, offset_s=0),
        _ev("agent.completion_gate", {"action": "continue_work", "basis": None}, offset_s=1),
        _ev("agent.completion_gate", {"action": "allow_final", "basis": "dag_verified"}, offset_s=2),
        _ev("compaction.finished", {"compacted": True, "trigger": "budget", "summary_tokens": 900,
                                    "clamped_sources": 2}, offset_s=3),
        _ev("compaction.finished", {"compacted": False, "reason": "summary_invalid",
                                    "trigger": "overflow"}, offset_s=4),
        _ev("agent.spawned", {"parent_session_id": "as_dispatcher", "role_id": "small_mol"}, offset_s=5),
        _ev("hub.posted", {"topic": "t"}, offset_s=6),
        _ev("hub.notification_consumed", {"post_id": "p"}, offset_s=7),
        _ev("agent.state_changed", {"to": "waiting_input"}, offset_s=8),
        _ev("agent.state_changed", {"to": "running"}, offset_s=10),
        _ev("agent.state_changed", {"to": "waiting_approval"}, offset_s=11),
        _ev("agent.state_changed", {"to": "running"}, offset_s=14),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, offset_s=15),
    ]
    metrics = telemetry.aggregate_agents(events)["totals"]
    assert metrics["completion"]["gate_actions"] == {"continue_work": 1, "allow_final": 1}
    assert metrics["completion"]["bases"] == {"dag_verified": 1}
    assert metrics["completion"]["exit_attempts"] == 1
    assert metrics["compaction"] == {
        "count": 1,
        "refused": 1,
        "refusal_reasons": {"summary_invalid": 1},
        "triggers": {"budget": 1, "overflow": 1},
        "summary_tokens": 900,
        "clamped_sources": 2,
    }
    # 被派发的 session 就是 s1 自己：它的 run 成功 → 父（as_dispatcher）的
    # fan-out 记 1 次派发 + 1 次子成功。
    assert metrics["subagents"] == {"spawned": 1, "succeeded": 1, "failed": 0, "cancelled": 0}
    assert metrics["hub"] == {"posts": 1, "notifications_consumed": 1}
    assert metrics["waits_ms"] == {"input": 2000, "approval": 3000}


def test_aggregate_agents_counts_recovery_after_failure():
    events = [
        _ev("run.started", {}, offset_s=0),
        _ev("run.finished", {"outcome": "failed", "failure_kind": "provider_permanent"}, offset_s=1),
        _ev("run.started", {}, run="r2", offset_s=2),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, run="r2", offset_s=3),
    ]
    agent = telemetry.aggregate_agents(events)["agents"][0]
    assert agent["recovered_after_failure"] == 1


def test_aggregate_agents_never_copies_tool_result_text():
    """聚合结果只带结构化字段：工具原始大结果与提示词绝不进统计。"""
    secret = "RAW_TOOL_OUTPUT_SHOULD_NOT_LEAK" * 20
    events = [
        _ev("run.started", {}, offset_s=0),
        _ev("tool.finished", {"tool_name": "bash", "status": "completed",
                              "result_summary": secret, "raw": secret}, offset_s=1),
        _ev("compaction.finished", {"compacted": True, "trigger": "budget",
                                    "summary": secret}, offset_s=2),
        _ev("llm.completed", {"model": "m1", "kind": "agent", "prompt": secret,
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1}}, offset_s=3),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, offset_s=4),
    ]
    blob = json.dumps(telemetry.aggregate_agents(events))
    assert "RAW_TOOL_OUTPUT_SHOULD_NOT_LEAK" not in blob


def test_aggregate_agents_time_range_filters_events():
    events = [
        _ev("run.started", {}, offset_s=0),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, offset_s=1),
        _ev("run.started", {}, run="r2", offset_s=3600),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None}, run="r2", offset_s=3601),
    ]
    since = (_BASE + timedelta(seconds=1800)).isoformat()
    report = telemetry.aggregate_agents(events, since=since)
    assert report["totals"]["runs"]["total"] == 1
    assert [row["run_id"] for row in report["runs"]] == ["r2"]


# ------------------------------------------------------------------ CLI / API


def _envelope(seq, type_, data, *, session="s1", run="r1", offset_s=0):
    return EventEnvelope(
        stream="agent",
        project_id="p1",
        session_id=session,
        run_id=run,
        seq=seq,
        session_seq=seq,
        type=type_,
        data=data,
        created_at=_BASE + timedelta(seconds=offset_s),
    )


@pytest.fixture
def populated_store(tmp_path):
    """一个真实 runtime-v2.db：两个 run（一成一败）+ 一次工具调用与一次门禁。"""
    store = RuntimeStore(tmp_path / "runtime-v2.db")
    store.append_event(_envelope(1, "run.started", {}))
    store.append_event(_envelope(2, "llm.completed", {
        "model": "m1",
        "kind": "agent",
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100},
    }))
    store.append_event(_envelope(3, "tool.finished", {"tool_name": "bash", "status": "completed"}))
    store.append_event(_envelope(4, "agent.completion_gate", {"action": "allow_final", "basis": "declared"}))
    store.append_event(_envelope(5, "run.finished", {"outcome": "succeeded", "failure_kind": None}))
    store.append_event(_envelope(6, "run.started", {}, run="r2", offset_s=10))
    store.append_event(_envelope(7, "llm.completed", {
        "model": "m1",
        "kind": "summary",
        "usage": {"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220},
    }, run="r2", offset_s=11))
    store.append_event(_envelope(8, "run.finished", {
        "outcome": "failed",
        "error": "provider rejected the request",
        "failure_kind": "provider_permanent",
    }, run="r2", offset_s=12))
    return store


def test_agent_summary_reads_only_and_matches_cli_and_api(populated_store):
    report = telemetry.agent_summary(populated_store.path)

    # CLI 与 API 是同一实现的薄壳：三者结果逐字段一致。
    result = CliRunner().invoke(
        cli, ["stats", "agents", "--db", str(populated_store.path), "--top", "5"]
    )
    assert result.exit_code == 0, result.output
    assert "runs=2" in result.output
    assert "provider_permanent=1" in result.output
    assert "s1" in result.output

    client = TestClient(create_v2_app(store_path=populated_store.path))
    resp = client.get("/api/v2/telemetry/agents")
    assert resp.status_code == 200
    assert resp.json() == json.loads(json.dumps(report))

    assert report["totals"]["runs"] == {
        "total": 2,
        "succeeded": 1,
        "failed": 1,
        "cancelled": 0,
        "failure_kinds": {"provider_permanent": 1},
    }
    assert report["totals"]["llm"]["summary_requests"] == 1
    # 只有第二个 run 烧了 token 却没跑成功任何工具。
    assert [row["run_id"] for row in report["runs"] if row["no_tool_progress"]] == ["r2"]


def test_aggregate_agents_attributes_fanout_to_the_parent_session():
    """fan-out 与子的终态比例记在父行上（子行上记会看成「子又派了子」）。"""
    events = [
        _ev("run.started", {}, session="as_parent", run="rp", offset_s=0),
        _ev("agent.spawned", {"parent_session_id": "as_parent", "role_id": "small_mol"},
            session="as_child", run=None, offset_s=1),
        _ev("run.started", {}, session="as_child", run="rc", offset_s=2),
        _llm(10, 1, session="as_child", run="rc", offset_s=3),
        _ev("run.finished", {"outcome": "failed", "failure_kind": "provider_permanent"},
            session="as_child", run="rc", offset_s=4),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None},
            session="as_parent", run="rp", offset_s=5),
    ]
    rows = {row["session_id"]: row for row in telemetry.aggregate_agents(events)["agents"]}
    assert rows["as_parent"]["metrics"]["subagents"] == {
        "spawned": 1, "succeeded": 0, "failed": 1, "cancelled": 0,
    }
    assert "as_child" in rows


def test_aggregate_agents_counts_cancelled_child_fanout_on_parent():
    """子 agent.cancelled 时父行的 subagents.cancelled 必须 +1（清 open_run_id 之前记账）。"""
    events = [
        _ev("run.started", {}, session="as_parent", run="rp", offset_s=0),
        _ev(
            "agent.spawned",
            {"parent_session_id": "as_parent", "role_id": "small_mol"},
            session="as_child",
            run=None,
            offset_s=1,
        ),
        _ev("run.started", {}, session="as_child", run="rc", offset_s=2),
        _ev("agent.cancelled", {"session_id": "as_child"}, session="as_child", run="rc", offset_s=3),
        _ev("run.finished", {"outcome": "succeeded", "failure_kind": None},
            session="as_parent", run="rp", offset_s=4),
    ]
    rows = {row["session_id"]: row for row in telemetry.aggregate_agents(events)["agents"]}
    assert rows["as_parent"]["metrics"]["subagents"] == {
        "spawned": 1, "succeeded": 0, "failed": 0, "cancelled": 1,
    }
    assert rows["as_child"]["metrics"]["runs"]["cancelled"] == 1
