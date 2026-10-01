"""完成依据投影（评审 5.3）：区分「运行结束」与「目标已验证完成」。

覆盖两层：

- 纯投影：``agent.completion_gate`` 的结构化 ``basis`` + ``run.finished`` /
  ``agent.cancelled`` 终态 → (run_outcome, completion_basis, verification_label)；
  未声明依据、被拦的判定、失败与取消一律 ``unverified``。
- 线缆投影：``GET /api/v2/agents/{id}``、项目 agent 列表与命令响应三个出口
  同口径；正在跑的 run 没有结论（``completion`` 为 null）。

不改变 DAG 完成算法与科学阈值，也不解析 reason 文本。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.completion import (
    COMPLETION_EVENT_TYPES,
    completion_state,
    completion_summary,
)
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.events import EventLog
from cloudra.services.api_v2 import create_v2_app

_PROJECT = "prj_test"
_SESSION = "agt_test"


def _log() -> EventLog:
    return EventLog(strict=True)


def _gate(log: EventLog, *, run_id: str, basis: str | None, session_id: str = _SESSION) -> None:
    log.append(
        "agent.completion_gate",
        stream="agent",
        project_id=_PROJECT,
        session_id=session_id,
        run_id=run_id,
        data={
            "action": "allow_final" if basis else "continue_work",
            "source": "dag" if basis else "dag",
            "explicit_stop": True,
            "reason": "irrelevant free text that must never be parsed",
            "request_id": None,
            "basis": basis,
        },
    )


def _finished(log: EventLog, *, run_id: str, outcome: str, session_id: str = _SESSION) -> None:
    log.append(
        "run.finished",
        stream="agent",
        project_id=_PROJECT,
        session_id=session_id,
        run_id=run_id,
        data={"outcome": outcome, "error": None if outcome == "succeeded" else "boom"},
    )


# basis → 期望的验证等级。只有证据门禁确认过的结题才是 verified。
_BASIS_LABELS = {
    "dag_verified": "verified",
    "supervisor_supported": "supervisor_reviewed",
    "supervisor_approved": "partial",
    "partial_recorded": "partial",
    "declared": "unverified",
    "background_wait": "unverified",
    "user_terminated": "unverified",
}


@pytest.mark.parametrize("basis,label", sorted(_BASIS_LABELS.items()))
def test_every_basis_maps_to_its_documented_label(basis, label):
    log = _log()
    _gate(log, run_id="run_1", basis=basis)
    _finished(log, run_id="run_1", outcome="succeeded")
    summary = completion_summary(list(log))
    assert summary == {
        "run_id": "run_1",
        "run_outcome": "succeeded",
        "completion_basis": basis,
        "verification_label": label,
    }


def test_succeeded_without_any_gate_is_unverified_and_claims_no_basis():
    """没有门禁事件（或 basis 未声明）时绝不冒充已验证完成。"""
    log = _log()
    _finished(log, run_id="run_1", outcome="succeeded")
    assert completion_summary(list(log)) == {
        "run_id": "run_1",
        "run_outcome": "succeeded",
        "completion_basis": None,
        "verification_label": "unverified",
    }

    log = _log()
    _gate(log, run_id="run_1", basis=None)  # 被拦的判定：没有依据可言
    _finished(log, run_id="run_1", outcome="succeeded")
    summary = completion_summary(list(log))
    assert summary["completion_basis"] is None
    assert summary["verification_label"] == "unverified"


def test_failed_and_cancelled_runs_are_never_verified():
    log = _log()
    _gate(log, run_id="run_1", basis="dag_verified")
    _finished(log, run_id="run_1", outcome="failed")
    assert completion_summary(list(log))["verification_label"] == "unverified"

    log = _log()
    log.append(
        "agent.cancelled",
        stream="project",
        project_id=_PROJECT,
        session_id=_SESSION,
        data={"session_id": _SESSION},
    )
    assert completion_summary(list(log)) == {
        "run_id": None,
        "run_outcome": "cancelled",
        "completion_basis": None,
        "verification_label": "unverified",
    }


def test_gate_of_an_earlier_run_does_not_leak_into_the_latest_run():
    """依据必须与终态同属一个 run：上一轮 dag_verified 不能给下一轮背书。"""
    log = _log()
    _gate(log, run_id="run_1", basis="dag_verified")
    _finished(log, run_id="run_1", outcome="succeeded")
    _gate(log, run_id="run_2", basis="declared")
    _finished(log, run_id="run_2", outcome="succeeded")
    summary = completion_summary(list(log))
    assert summary["run_id"] == "run_2"
    assert summary["completion_basis"] == "declared"
    assert summary["verification_label"] == "unverified"


def test_completion_state_groups_sessions_in_one_pass():
    log = _log()
    _gate(log, run_id="run_a", basis="dag_verified", session_id="agt_a")
    _finished(log, run_id="run_a", outcome="succeeded", session_id="agt_a")
    _gate(log, run_id="run_b", basis="declared", session_id="agt_b")
    _finished(log, run_id="run_b", outcome="succeeded", session_id="agt_b")
    # 没有终态事件的 session 不进结果。
    log.append(
        "agent.completion_gate",
        stream="agent",
        project_id=_PROJECT,
        session_id="agt_c",
        run_id="run_c",
        data={"action": "wait_review", "source": "dag", "basis": None},
    )
    state = completion_state(list(log))
    assert set(state) == {"agt_a", "agt_b"}
    assert state["agt_a"]["verification_label"] == "verified"
    assert state["agt_b"]["verification_label"] == "unverified"


def test_completion_event_types_are_the_only_inputs():
    assert COMPLETION_EVENT_TYPES == {"agent.completion_gate", "run.finished", "agent.cancelled"}


# ---------------------------------------------------------------- 线缆投影


async def _api_client(core: RuntimeCore):
    app = create_v2_app(core)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.asyncio
async def test_api_never_reports_a_declared_run_as_verified_complete():
    core = RuntimeCore(strict_events=True)
    async with await _api_client(core) as client:
        project = (await client.post("/api/v2/projects", json={"name": "completion"})).json()["data"]
        spawn = await client.post(
            f"/api/v2/projects/{project['id']}/agents", json={"role_id": "coordinator"}
        )
        agent = spawn.json()["data"]

        # 没跑过 / 正在跑：都没有结论。
        assert spawn.json()["data"]["completion"] is None
        live = core.require_agent(agent["id"])
        run_id = await core.agent_host.start_run(live)
        detail = (await client.get(f"/api/v2/agents/{agent['id']}")).json()
        assert detail["completion"] is None

        # 门禁按模型自述放行，run 正常结束（standard 模式）：
        core.event_log.append(
            "agent.completion_gate",
            stream="agent",
            project_id=project["id"],
            session_id=agent["id"],
            run_id=run_id,
            data={
                "action": "allow_final",
                "source": "declared",
                "explicit_stop": False,
                "reason": "no completion gate applies to this agent",
                "request_id": None,
                "basis": "declared",
            },
        )
        await core.agent_host.finish_run(live, outcome="succeeded")

        expected = {
            "run_id": run_id,
            "run_outcome": "succeeded",
            "completion_basis": "declared",
            "verification_label": "unverified",
        }
        detail = (await client.get(f"/api/v2/agents/{agent['id']}")).json()
        assert detail["completion"] == expected

        # 列表端点与命令响应同口径（前端用响应整体替换 agent，不能丢字段）。
        listing = (await client.get(f"/api/v2/projects/{project['id']}/agents")).json()
        assert [a["completion"] for a in listing if a["id"] == agent["id"]] == [expected]
        patched = await client.patch(
            f"/api/v2/agents/{agent['id']}/settings", json={"yolo": True}
        )
        assert patched.json()["data"]["completion"] == expected
