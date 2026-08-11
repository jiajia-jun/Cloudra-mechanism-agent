"""DAG TUI 的纯渲染/辅助函数测试（不启动 Textual App）。"""

import json

import pytest

from cloudra.tui.new.screens.dag_screen import (
    build_operation,
    format_dag_content,
    format_dag_summary,
    format_delivery_report,
    format_graph_section,
    format_history,
    json_template,
)


def test_json_template_defaults():
    """编辑表单的 JSON 默认值模板：update_node 预填 skipped，add_node 预填 proposed。"""
    update = json.loads(json_template("update_node"))
    assert update == {"status": "skipped", "reason": ""}
    add = json.loads(json_template("add_node"))
    assert add["evidence_level"] == "proposed"
    assert json.loads(json_template("add_edge")) == {}


def test_build_operation_add_node():
    op = build_operation(
        "process",
        "add_node",
        node_id="opt-ts",
        label="TS 优化",
        json_data={"status": "proposed", "priority": 3},
    )
    assert op == {
        "op": "add_node",
        "graph": "process",
        "data": {
            "node_id": "opt-ts",
            "node_type": "work",
            "label": "TS 优化",
            "payload": {"status": "proposed", "priority": 3},
        },
    }


def test_build_operation_add_edge():
    op = build_operation(
        "delivery",
        "add_edge",
        edge_id="chair",
        source_node_id="r",
        target_node_id="p",
        edge_type="elementary_step",
        label="chair [3,3]",
    )
    assert op["data"]["edge_type"] == "elementary_step"
    assert op["data"]["payload"] == {}
    # 未给 edge_type 时回退 depends_on
    default = build_operation(
        "process", "add_edge", edge_id="e", source_node_id="a", target_node_id="b"
    )
    assert default["data"]["edge_type"] == "depends_on"


def test_build_operation_update_ops_wrap_changes():
    op = build_operation(
        "process", "update_node", node_id="opt-ts", json_data={"status": "skipped"}
    )
    assert op["data"] == {"node_id": "opt-ts", "changes": {"status": "skipped"}}
    edge_op = build_operation(
        "delivery", "update_edge", edge_id="chair", json_data={"label": "boat"}
    )
    assert edge_op["data"] == {"edge_id": "chair", "changes": {"label": "boat"}}
    with pytest.raises(ValueError):
        build_operation("process", "attach_ref", node_id="x")


def test_edit_ops_include_new_user_ops():
    """编辑弹窗词表：删边、挂 link、豁免 gate 都对用户开放。"""
    from cloudra.tui.new.screens.dag_screen import _EDIT_OPS

    assert {"remove_edge", "add_link", "waive_gate"} <= set(_EDIT_OPS)


def test_build_operation_remove_edge():
    op = build_operation("delivery", "remove_edge", edge_id="chair")
    assert op == {"op": "remove_edge", "graph": "delivery", "data": {"edge_id": "chair"}}


def test_build_operation_add_link_and_waive_gate_carry_full_data():
    """add_link / waive_gate 的 JSON 即完整 data，graph 置 None（跨图/契约操作）。"""
    link = build_operation(
        "process",
        "add_link",
        json_data={
            "link_id": "l1",
            "process_node_id": "opt-ts",
            "delivery_element_type": "edge",
            "delivery_element_id": "chair",
        },
    )
    assert link["graph"] is None
    assert link["data"]["link_id"] == "l1"
    assert link["data"]["delivery_element_id"] == "chair"

    waiver = build_operation(
        "delivery",
        "waive_gate",
        json_data={
            "gate_code": "missing_thermochemistry",
            "target_type": "edge",
            "target_id": "chair",
            "user_id": "user",
            "session_id": "user",
            "rationale": "能量非关键路径",
        },
    )
    assert waiver["graph"] is None
    assert waiver["data"]["gate_code"] == "missing_thermochemistry"
    assert waiver["data"]["rationale"] == "能量非关键路径"


def test_json_template_new_ops_prefill_required_keys():
    """新操作的 JSON 模板预填引擎要求的必填键。"""
    link = json.loads(json_template("add_link"))
    assert {
        "link_id",
        "process_node_id",
        "delivery_element_type",
        "delivery_element_id",
    } <= set(link)
    waiver = json.loads(json_template("waive_gate"))
    assert {"gate_code", "target_type", "target_id", "rationale"} <= set(waiver)


def test_format_dag_summary_without_dag():
    assert format_dag_summary(None) == "standard（无 DAG）"


def test_format_dag_summary_with_projection():
    projection = {
        "mode": "dag_record",
        "revisions": {"process": 3, "delivery": 1},
        "frontier": [{"node_id": "opt-ts", "label": "TS 优化", "status": "ready", "priority": 1}],
        "blockers": [{"node_id": "freq", "status": "failed"}],
        "delivery_gaps": [{"code": "missing_endpoint_evidence"}],
    }
    text = format_dag_summary(projection)
    assert "process=3" in text
    assert "delivery=1" in text
    assert "opt-ts" in text
    assert "阻塞: 1" in text
    assert "机理缺口: 1" in text


def test_format_dag_content_without_dag():
    text = format_dag_content(None, None, None, None, None, conversation_id="c1")
    assert "没有 DAG" in text


def test_format_graph_section_renders_nodes_and_edges():
    graph = {
        "revision": 2,
        "nodes": [
            {
                "node_id": "map",
                "node_type": "work",
                "label": "mapping",
                "payload": {"status": "ready", "priority": 2},
            }
        ],
        "edges": [
            {
                "edge_id": "map-before-ts",
                "source_node_id": "map",
                "target_node_id": "ts",
                "edge_type": "depends_on",
            }
        ],
    }
    text = "\n".join(format_graph_section("Process", graph))
    assert "revision=2" in text
    assert "map (work) mapping" in text
    assert "status=ready" in text
    assert "map → ts [depends_on]" in text


def test_format_delivery_report_lists_gaps_and_waivers():
    report = {
        "complete": False,
        "unresolved": [
            {
                "code": "missing_endpoint_evidence",
                "target_type": "edge",
                "target_id": "chair",
                "detail": "requires endpoint_supported",
            }
        ],
        "inconclusive": [],
        "waived": [
            {
                "code": "missing_thermochemistry",
                "target_type": "edge",
                "target_id": "chair",
                "detail": "",
                "waiver": {"rationale": "能量非关键路径"},
            }
        ],
    }
    text = "\n".join(format_delivery_report(report))
    assert "complete: False" in text
    assert "missing_endpoint_evidence" in text
    assert "豁免" in text


def test_format_history_renders_actor_and_acceptance():
    rows = [
        {
            "actor": "user",
            "rationale": "跳过频率计算",
            "accepted": True,
            "created_at": "2026-08-10T10:00:00",
        },
        {
            "actor": "harness",
            "rationale": "",
            "accepted": False,
            "rejection_code": "cycle",
            "created_at": "2026-08-10T09:00:00",
        },
    ]
    text = "\n".join(format_history(rows))
    assert "[user] 跳过频率计算" in text
    assert "√" in text
    assert "拒绝: cycle" in text


def test_format_dag_content_with_real_service_graph(tmp_path, monkeypatch):
    """用临时目录 + 真实 CloudraService/DagStore 造小图，校验渲染输出含关键 id。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, GraphOperation, MutationBatch
    from cloudra.dag.store import DagStore
    from cloudra.infra.config import get_config, reload_config
    from cloudra.persistence.database import ConversationDB
    from cloudra.services.service import CloudraService

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path / "data"))
    reload_config()
    get_config()._ensure_dirs()

    cid = "dag-tui"
    db = ConversationDB(cid, data_dir=tmp_path / "data").init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="tui-test",
            base_revisions=store.load_bundle().revisions,
            rationale="seed tui test graph",
            operations=[
                GraphOperation(
                    op="add_node",
                    graph="process",
                    data={
                        "node_id": "map",
                        "node_type": "work",
                        "label": "mapping",
                        "payload": {"status": "ready", "priority": 1},
                    },
                ),
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "r",
                        "node_type": "intermediate_occurrence",
                        "label": "C=COCC=C",
                        "payload": {"evidence_level": "proposed"},
                    },
                ),
            ],
        )
    )
    assert seeded.accepted

    service = CloudraService()
    projection = service.dag_projection(cid)
    assert projection is not None
    text = format_dag_content(
        projection,
        service.dag_graph(cid, "process"),
        service.dag_graph(cid, "delivery"),
        service.dag_delivery_report(cid),
        service.dag_history(cid),
        conversation_id=cid,
    )
    assert "map (work) mapping" in text
    assert "status=ready" in text
    assert "C=COCC=C" in text
    assert "evidence=proposed" in text
    assert "Delivery 覆盖报告" in text
    assert "近期变更" in text
    assert "seed tui test graph" in text

    summary = format_dag_summary(service.dag_projection(cid))
    assert "map" in summary
    assert "阻塞:" in summary


# ------------------------------------------------------------------
# /mode 编排模式切换（消融开关：off / record / guided）
# ------------------------------------------------------------------


def test_mode_command_registered_and_parsed():
    from cloudra.tui.new.commands import (
        COMMAND_DESCRIPTIONS,
        KNOWN_COMMANDS,
        parse_command,
    )

    assert "mode" in KNOWN_COMMANDS
    assert any(name == "mode" for name, _ in COMMAND_DESCRIPTIONS)
    assert parse_command("/mode guided") == ("mode", "guided")
    assert parse_command("/mode") == ("mode", "")


def _make_app(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config, reload_config
    from cloudra.tui.new.app import CloudraTextualApp

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path / "data"))
    reload_config()
    get_config()._ensure_dirs()
    return CloudraTextualApp()


@pytest.mark.asyncio
async def test_cmd_mode_switches_and_updates_status_bar(tmp_path, monkeypatch):
    from cloudra.tui.new.widgets.status_bar import StatusBar

    app = _make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        bar = screen.query_one("#status-bar", StatusBar)
        # 默认 standard，状态栏不显示 DAG 标记
        assert screen.orchestration_mode == "standard"
        assert "DAG" not in str(bar.render())

        await screen._cmd_mode("guided")
        await pilot.pause()
        assert screen.orchestration_mode == "dag_guided"
        assert bar.orch_mode == "dag_guided"
        assert "DAG·引导" in str(bar.render())

        # 未知值不改变模式
        await screen._cmd_mode("bogus")
        assert screen.orchestration_mode == "dag_guided"

        # status 只查询不修改
        await screen._cmd_mode("status")
        assert screen.orchestration_mode == "dag_guided"

        # 运行中有任务时拒绝切换（保证模式在 session 创建时固定）
        async def _active():
            return True

        monkeypatch.setattr(screen, "_has_active_session", _active)
        await screen._cmd_mode("off")
        assert screen.orchestration_mode == "dag_guided"


@pytest.mark.asyncio
async def test_submit_threads_orchestration_mode(tmp_path, monkeypatch):
    """提交新任务时把当前编排模式传给 service（消融三模式都能从 UI 发起）。"""
    from types import SimpleNamespace

    app = _make_app(tmp_path, monkeypatch)
    captured = {}

    async def fake_submit(query, **kwargs):
        captured.update(kwargs)
        return "conv", SimpleNamespace(session_id="s-mode-test", state="queued")

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        monkeypatch.setattr(screen.service, "submit_session_async", fake_submit)
        screen.orchestration_mode = "dag_record"
        await screen._start_coordinator_task("研究 Claisen 重排机理")
        await pilot.pause()
        assert captured["orchestration_mode"] == "dag_record"
        assert captured["yolo"] is False
