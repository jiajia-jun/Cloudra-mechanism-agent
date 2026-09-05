"""事件驱动督导的生产端触发纪律。

本文件锁定：``DagController.on_tool_finished`` 之后哪些工具完成会经
``_trigger_supervisor_after_tool`` → ``notify_supervisor`` 触达项目唯一
Supervisor agent（spawn + 信箱变更消息），哪些必须保持安静。

督导语义的其它测试面：
- 督导生命周期/状态表/取消不复活：tests/test_runtime_v2_supervision.py；
- 督导工具面与权限：tests/test_runtime_v2_supervisor_tools.py；
- 裁决语义（dag_review_call/dag_review_evidence）：tests/test_dag_review_call.py、
  tests/test_dag_review_requests.py；
- 科学审查约束：prompts/supervisor.md（唯一事实源）。
"""

from __future__ import annotations

import pytest

from cloudra.dag.controller import DagController
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    CoverageContract,
    GraphActor,
    MutationBatch,
    SetCoverageContract,
)
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.supervision import find_project_supervisor


async def _core_project(name: str):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(Command(type="project.create", payload={"name": name}))
    ).data
    return core, project


def _guided_controller(project_id: str, core, mode: str = "dag_guided") -> DagController:
    db = ConversationDB(project_id).init()
    return DagController(db, "s1", mode, conversation_id=project_id, core=core)


def _supervisor_messages(core, session_id):
    return [
        e
        for e in core.event_log.query_session(session_id)
        if e.type == "agent.message_injected"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["standard", "dag_record"])
async def test_non_guided_modes_never_notify(mode):
    """standard / dag_record：提案落库也不通知（督导信箱只在 guided 消费）。"""
    core, project = await _core_project(f"supervision-quiet-{mode}")
    controller = _guided_controller(project.id, core, mode=mode)

    await controller.on_tool_finished(
        "tc-propose",
        "dag_propose_mechanism",
        {"rationale": "hypothesis"},
        {
            "is_success": True,
            "accepted": True,
            "result": {"draft_id": "draft_1", "state": "accepted"},
        },
    )

    assert find_project_supervisor(core, project.id) is None


@pytest.mark.asyncio
async def test_guided_propose_draft_notifies_supervisor():
    """dag_propose_mechanism 草稿落库（guided 返回 accepted=False + draft_id）
    → 项目唯一 Supervisor 被 spawn 并收到信箱变更消息；裁决不在此等待。"""
    core, project = await _core_project("supervision-propose")
    controller = _guided_controller(project.id, core)

    await controller.on_tool_finished(
        "tc-propose",
        "dag_propose_mechanism",
        {"rationale": "Claisen chair hypothesis"},
        {
            "is_success": True,
            "accepted": False,
            "result": {"draft_id": "draft_1", "state": "open", "accepted": False},
        },
    )

    supervisor = find_project_supervisor(core, project.id)
    assert supervisor is not None
    assert supervisor.role_id == "supervisor"
    messages = _supervisor_messages(core, supervisor.id)
    assert len(messages) == 1
    assert "mailbox changed" in str(messages[0].data.get("content", ""))


@pytest.mark.asyncio
async def test_failed_or_rejected_proposal_does_not_notify():
    """校验失败/被拒的提案不落草稿，不通知 Supervisor。"""
    core, project = await _core_project("supervision-no-propose")
    controller = _guided_controller(project.id, core)

    await controller.on_tool_finished(
        "tc-propose-bad",
        "dag_propose_mechanism",
        {"rationale": "invalid"},
        {
            "is_success": False,
            "accepted": False,
            "error": "a mechanism proposal requires a non-empty rationale",
        },
    )

    assert find_project_supervisor(core, project.id) is None


@pytest.mark.asyncio
async def test_delivery_updates_are_not_a_supervision_trigger():
    """§1/§5：delivery_updated 触发口已删除——dag_add_species/dag_add_step/
    dag_update_delivery_element 的图变更持久化在 store 变更日志里，不
    单独通知（督导信箱只有显式送审/草稿/结构化请求三类）。"""
    core, project = await _core_project("supervision-delivery-quiet")
    controller = _guided_controller(project.id, core)

    for tool_name in (
        "dag_add_species",
        "dag_add_step",
        "dag_update_delivery_element",
    ):
        await controller.on_tool_finished(
            f"tc-{tool_name}",
            tool_name,
            {"node_id": "r", "rationale": "graph edit"},
            {"is_success": True, "accepted": True},
        )

    assert find_project_supervisor(core, project.id) is None


@pytest.mark.asyncio
async def test_read_only_and_non_delivery_tools_do_not_notify():
    """dag_view / process 残留调用 / 模板初始化 / 删边拒绝都不是通知口。"""
    core, project = await _core_project("supervision-readonly-quiet")
    controller = _guided_controller(project.id, core)

    await controller.on_tool_finished(
        "tc-view", "dag_view", {"graph_kind": "both"}, {"is_success": True}
    )
    await controller.on_tool_finished(
        "tc-process",
        "dag_update_process_node",
        {"node_id": "x", "priority": 1},
        {"is_success": True, "accepted": True},
    )
    await controller.on_tool_finished(
        "tc-init",
        "dag_init_from_template",
        {"rationale": "start"},
        {"is_success": True, "accepted": True},
    )
    await controller.on_tool_finished(
        "tc-rm",
        "dag_remove_edge",
        {"graph": "delivery", "edge_id": "e1", "rationale": "no longer needed"},
        {"is_success": False, "accepted": False, "rejection_code": "x"},
    )

    assert find_project_supervisor(core, project.id) is None


@pytest.mark.asyncio
async def test_research_tool_completions_register_evidence_without_notify():
    """§5：bash 不登记；log_parser 完成（成功或失败）只登记证据与派生事实，
    不入 review 信箱、不通知 Supervisor——送审是显式动作。"""
    core, project = await _core_project("supervision-evidence-quiet")
    controller = _guided_controller(project.id, core)

    await controller.on_tool_finished(
        "tc-bash",
        "bash",
        {"command": "cat ts1.log"},
        {"is_success": True, "output": "normal termination"},
    )
    await controller.on_tool_finished(
        "tc-parse",
        "log_parser",
        {"log_path": "ts1.log"},
        {"is_success": True, "normal_termination": True, "scf_energy": -303.65},
    )
    await controller.on_tool_finished(
        "tc-parse-bad",
        "log_parser",
        {"log_path": "bad.log"},
        {"is_success": False, "error": "parse error"},
    )

    assert find_project_supervisor(core, project.id) is None
    store = DagStore(ConversationDB(project.id))
    assert store.list_call_reviews() == []
    assert store.resolve_evidence_for_call("tc-parse") is not None
    assert store.resolve_evidence_for_call("tc-parse-bad") is not None


@pytest.mark.asyncio
async def test_dag_verdict_tool_completions_do_not_notify():
    """dag_bind_evidence / dag_review_evidence 的工具完成事件不是通知口：
    送审通知发生在 submit_evidence_for_review 内部（持久化之后），督导自己
    的裁决工具绝不唤醒督导（无自我复核循环）。"""
    core, project = await _core_project("supervision-verdict-quiet")
    controller = _guided_controller(project.id, core)

    await controller.on_tool_finished(
        "tc-bind",
        "dag_bind_evidence",
        {"tool_call_id": "tc-x", "bind_target": "step1", "stage_kind": "ts_opt"},
        {"is_success": True, "accepted": True},
    )
    await controller.on_tool_finished(
        "tc-review",
        "dag_review_evidence",
        {"request_id": "req_x", "verdict": "accept"},
        {"is_success": True, "accepted": True},
    )

    assert find_project_supervisor(core, project.id) is None


@pytest.mark.asyncio
async def test_message_supervisor_notifies_after_persisted_request():
    """dag_message_supervisor 成功（纯文本或结构化，均已落
    dag_review_requests）→ 通知；空消息/失败不通知。"""
    core, project = await _core_project("supervision-message")
    controller = _guided_controller(project.id, core)

    await controller.on_tool_finished(
        "tc-msg-empty", "dag_message_supervisor", {"message": ""}, {"is_success": True}
    )
    await controller.on_tool_finished(
        "tc-msg-fail",
        "dag_message_supervisor",
        {"message": "hello"},
        {"is_success": False, "error": "oops"},
    )
    assert find_project_supervisor(core, project.id) is None

    await controller.on_tool_finished(
        "tc-msg",
        "dag_message_supervisor",
        {"message": "frontier 空，请复核 TS 证据"},
        {
            "is_success": True,
            "accepted": True,
            "result": {"request_id": "req_1", "kind": "exception", "enqueued": True},
        },
    )
    supervisor = find_project_supervisor(core, project.id)
    assert supervisor is not None
    assert len(_supervisor_messages(core, supervisor.id)) == 1


@pytest.mark.asyncio
async def test_notify_without_core_handle_is_a_no_op(tmp_path):
    """无 core 句柄的调用方（直连 DagController 的诊断/测试形态）：持久化
    照常，通知静默降级到 reconcile 补投，绝不炸工具路径。"""
    db = ConversationDB("supervision-no-core", data_dir=tmp_path).init()
    controller = DagController(db, "s1", "dag_guided", conversation_id="supervision-no-core")

    await controller.on_tool_finished(
        "tc-propose",
        "dag_propose_mechanism",
        {"rationale": "hypothesis"},
        {"is_success": True, "result": {"draft_id": "draft_1", "state": "open"}},
    )
    # 无异常即契约（通知降级为 debug 日志）。


def test_supervisor_may_strengthen_but_not_lower_coverage(tmp_path):
    db = ConversationDB("supervisor-coverage", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    stronger = CoverageContract.mechanism_default(require_thermochemistry=True)
    accepted = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.SUPERVISOR,
            actor_id="supervisor",
            base_revisions=store.load_bundle().revisions,
            operations=[
                SetCoverageContract(op="set_coverage_contract", contract=stronger)
            ],
        )
    )
    lowered = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.SUPERVISOR,
            actor_id="supervisor",
            base_revisions=store.load_bundle().revisions,
            operations=[
                SetCoverageContract(
                    op="set_coverage_contract",
                    contract=CoverageContract.mechanism_default(),
                ),
            ],
        )
    )

    assert accepted.accepted
    assert not lowered.accepted
    assert lowered.rejection_code == "actor_forbidden"
