"""dag_guided 反馈环：被驳回草稿的 reject_reason 随 DAG 投影回 Coordinator。

事件驱动督导的报告唯一投递口是普通子 agent 完成回传（Supervisor spawn 时
parent=Coordinator，agent_runner 终态回传），由
tests/test_runtime_v2_supervision.py 的生命周期用例与反馈矩阵承接。
本文件保留 DAG 投影侧的驳回理由回环（与督导执行方式无关）。
"""

import asyncio

import pytest

from cloudra.dag.controller import DagController
from cloudra.dag.models import CallReview
from cloudra.persistence.database import ConversationDB


def _db(tmp_path, conversation_id):
    return ConversationDB(conversation_id, data_dir=tmp_path).init()


_OPS = [
    {
        "op": "add_node",
        "graph": "delivery",
        "node": {"node_id": "r", "node_type": "occurrence", "label": "R", "role": "reactant"},
    },
    {
        "op": "add_node",
        "graph": "delivery",
        "node": {"node_id": "p", "node_type": "occurrence", "label": "P", "role": "product"},
    },
    {
        "op": "add_edge",
        "graph": "delivery",
        "edge": {
            "edge_id": "step1",
            "edge_type": "elementary_step",
            "source_node_id": "r",
            "target_node_id": "p",
        },
    },
]


@pytest.mark.asyncio
async def test_prompt_projection_includes_rejected_draft_reason(tmp_path):
    """to_prompt_text 带最近被驳回草稿的 reject_reason：Coordinator 下一轮
    从投影直接读到督导的驳回理由。"""
    db = _db(tmp_path, "supervisor-feedback-projection")
    controller = DagController(db, "s1", "dag_guided")
    await controller.initialize()
    proposed = await controller.propose_mechanism(
        operations=_OPS,
        stage_contracts={"step1": ["ts_guess", "ts_opt", "frequency"]},
        rationale="Claisen chair hypothesis",
        actor_id="a-0",
    )
    await controller.accept_mechanism(
        verdict="reject",
        rationale="step1 lacks an IRC stage; add short_irc before frequency",
        draft_id=proposed["draft_id"],
    )

    text = await controller.prompt_projection()

    assert "rejected_draft" in text
    assert proposed["draft_id"] in text
    assert "add short_irc before frequency" in text


@pytest.mark.asyncio
async def test_prompt_projection_omits_reject_reason_after_new_open_draft(tmp_path):
    """有新的 open 草稿在审时，旧驳回不再投影（最新草稿优先，驳回已被响应）。"""
    db = _db(tmp_path, "supervisor-feedback-superseded")
    controller = DagController(db, "s1", "dag_guided")
    await controller.initialize()
    proposed = await controller.propose_mechanism(
        operations=_OPS,
        stage_contracts={"step1": ["ts_guess", "ts_opt", "frequency"]},
        rationale="first hypothesis",
        actor_id="a-0",
    )
    await controller.accept_mechanism(
        verdict="reject",
        rationale="stale rejection reason",
        draft_id=proposed["draft_id"],
    )
    await controller.propose_mechanism(
        operations=_OPS,
        stage_contracts={"step1": ["ts_guess", "ts_opt", "frequency"]},
        rationale="revised hypothesis",
        actor_id="a-0",
    )

    text = await controller.prompt_projection()

    assert "stale rejection reason" not in text


@pytest.mark.asyncio
async def test_prompt_projection_pending_reviews_are_explicit_only(tmp_path):
    """投影 pin 的 pending_reviews 与 dag_view 同一口径：只列 source="explicit"
    的可消费送审行；legacy_auto/auto 历史行保留审计但绝不出现在 pin 里
    （否则 Coordinator/Supervisor 会对着永远不可消费的"待办"空转）。"""
    db = _db(tmp_path, "projection-explicit-only")
    controller = DagController(db, "s1", "dag_guided")
    await controller.initialize()
    for source in ("explicit", "legacy_auto"):
        await asyncio.to_thread(
            controller.store.enqueue_call_review,
            CallReview(
                review_id=source,
                tool_call_id=source,
                tool_name="log_parser",
                is_success=True,
                source=source,
                claim=f"claim from {source}",
            ),
        )

    text = await controller.prompt_projection()

    assert "explicit" in text
    assert "legacy_auto" not in text
