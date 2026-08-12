"""DAG 编排查看与用户编辑页面。

每个 conversation 有两张持久图：process（计算流程）与 delivery（化学机理）。
本页面全屏展示双图节点/边、delivery 覆盖报告与近期变更历史，
并提供编辑弹窗，把用户修改经 ``CloudraService.dag_apply_user_mutation``
提交给引擎做原子校验。
"""

from __future__ import annotations

import asyncio
import json

from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select

from cloudra.services.service import CloudraService
from cloudra.tui.new.widgets.safe_static import SafeStatic

# 编辑弹窗支持的操作类型
_EDIT_OPS = (
    "add_node",
    "add_edge",
    "update_node",
    "update_edge",
    "remove_edge",
    "add_link",
    "waive_gate",
)

# 各操作对应的 payload / changes / data JSON 默认值模板（表单预填，便于用户在其上修改）
_JSON_TEMPLATES = {
    "add_node": {"status": "proposed", "priority": 0, "evidence_level": "proposed"},
    "add_edge": {},
    "update_node": {"status": "skipped", "reason": ""},
    "update_edge": {"label": ""},
    "remove_edge": {},
    "add_link": {
        "link_id": "",
        "process_node_id": "",
        "delivery_element_type": "node",
        "delivery_element_id": "",
    },
    "waive_gate": {
        "gate_code": "",
        "target_type": "edge",
        "target_id": "",
        "user_id": "user",
        "session_id": "user",
        "rationale": "",
    },
}

# update_* 操作的 JSON 文本框语义是 changes，add_link/waive_gate 是 op 顶层字段/waiver，
# 其余并入节点/边对象
_CHANGES_OPS = ("update_node", "update_edge")
_DATA_OPS = ("add_link", "waive_gate")

# add_link / waive_gate 的 JSON 必填键（客户端预校验，引擎还会再校验一次）
_DATA_REQUIRED_KEYS = {
    "add_link": ("link_id", "process_node_id", "delivery_element_type", "delivery_element_id"),
    "waive_gate": ("gate_code", "target_type", "target_id", "user_id", "session_id", "rationale"),
}


def json_template(op_name: str) -> str:
    """返回编辑表单中某操作的 JSON 默认值（紧凑单行）。"""
    return json.dumps(_JSON_TEMPLATES.get(op_name, {}), ensure_ascii=False)


def build_operation(
    graph: str,
    op_name: str,
    *,
    node_id: str = "",
    node_type: str = "",
    edge_id: str = "",
    source_node_id: str = "",
    target_node_id: str = "",
    edge_type: str = "",
    label: str = "",
    json_data: dict | None = None,
) -> dict:
    """把编辑表单字段组装成 GraphOperation dict（纯函数，便于单测）。

    op 是以 ``op`` 判别的具名命令：add_* 操作的 ``json_data`` 并入节点/边对象
    （具名字段如 status/evidence_level 直接落在字段上，其余键由模型层归入
    metadata）；update_* 操作的是 changes（可改 status/priority/label/
    annotations/reason/blocked_reason/evidence_level/required 等，不能改
    refs/id/node_type）。add_link / waive_gate 是跨图/契约操作，graph 字段置 None。
    """
    if op_name == "add_node":
        node = {
            "node_id": node_id,
            "node_type": node_type or "planned",
            "label": label,
            **dict(json_data or {}),
        }
        return {"op": op_name, "graph": graph, "node": node}
    if op_name == "add_edge":
        edge = {
            "edge_id": edge_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type or "dependency",
            "label": label,
            **dict(json_data or {}),
        }
        return {"op": op_name, "graph": graph, "edge": edge}
    if op_name == "update_node":
        return {
            "op": op_name,
            "graph": graph,
            "node_id": node_id,
            "changes": dict(json_data or {}),
        }
    if op_name == "update_edge":
        return {
            "op": op_name,
            "graph": graph,
            "edge_id": edge_id,
            "changes": dict(json_data or {}),
        }
    if op_name == "remove_edge":
        return {"op": op_name, "graph": graph, "edge_id": edge_id}
    if op_name == "add_link":
        # 跨图簿记：字段平铺在 op 顶层，graph 置 None
        return {"op": op_name, "graph": None, **dict(json_data or {})}
    if op_name == "waive_gate":
        # 契约豁免：waiver 是一个完整 CoverageWaiver 对象
        return {"op": op_name, "graph": None, "waiver": dict(json_data or {})}
    raise ValueError(f"不支持的操作类型: {op_name}")


def _format_node_extras(payload: dict) -> str:
    """从节点 payload 提取 status/priority/evidence_level 展示后缀。"""
    parts = []
    if payload.get("status"):
        parts.append(f"status={payload['status']}")
    if payload.get("priority"):
        parts.append(f"priority={payload['priority']}")
    if payload.get("evidence_level"):
        parts.append(f"evidence={payload['evidence_level']}")
    return f"  [{' '.join(parts)}]" if parts else ""


def format_graph_section(title: str, graph: dict | None) -> list[str]:
    """把一张图 dict（dag_graph 返回值）渲染成行列表。"""
    lines = [f"== {title} =="]
    if not graph:
        lines.append("  （无数据）")
        return lines
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    lines.append(
        f"revision={graph.get('revision', 0)}  节点 {len(nodes)}  边 {len(edges)}"
    )
    for node in nodes:
        payload = node.get("payload") or {}
        lines.append(
            f"  · {node.get('node_id')} ({node.get('node_type')})"
            f" {node.get('label') or ''}{_format_node_extras(payload)}"
        )
    for edge in edges:
        edge_label = f" {edge['label']}" if edge.get("label") else ""
        lines.append(
            f"  → {edge.get('edge_id')}: {edge.get('source_node_id')}"
            f" → {edge.get('target_node_id')} [{edge.get('edge_type')}]{edge_label}"
        )
    if not nodes and not edges:
        lines.append("  （空图）")
    return lines


def format_delivery_report(report: dict | None) -> list[str]:
    """把 delivery 覆盖报告渲染成行列表。"""
    lines = ["== Delivery 覆盖报告 =="]
    if not report:
        lines.append("  （无数据）")
        return lines
    lines.append(f"  complete: {report.get('complete')}")
    for key, title in (
        ("unresolved", "未解决"),
        ("inconclusive", "不确定"),
        ("waived", "已豁免"),
    ):
        items = report.get(key) or []
        if not items:
            continue
        lines.append(f"  {title} ({len(items)}):")
        for gate in items:
            line = (
                f"    - [{gate.get('code')}] {gate.get('target_type')}"
                f"/{gate.get('target_id')}: {gate.get('detail') or ''}"
            )
            waiver = gate.get("waiver")
            if waiver:
                line += f"（豁免: {waiver.get('rationale') or ''}）"
            lines.append(line)
    return lines


def format_history(rows: list[dict] | None, limit: int = 10) -> list[str]:
    """把近期 mutation journal 渲染成行列表。"""
    lines = ["== 近期变更 =="]
    if not rows:
        lines.append("  （暂无变更）")
        return lines
    for row in rows[:limit]:
        accepted = "√" if row.get("accepted") else "×"
        when = (row.get("created_at") or "")[:19].replace("T", " ")
        line = f"  {accepted} [{row.get('actor')}] {row.get('rationale') or ''}"
        if not row.get("accepted") and row.get("rejection_code"):
            line += f"（拒绝: {row['rejection_code']}）"
        if when:
            line += f"  {when}"
        lines.append(line)
    return lines


def format_dag_content(
    projection: dict | None,
    process_graph: dict | None,
    delivery_graph: dict | None,
    delivery_report: dict | None,
    history: list[dict] | None,
    *,
    conversation_id: str = "",
) -> str:
    """汇总渲染整个 DAG 页面文本；projection 为 None 表示无 DAG。"""
    if projection is None:
        return "当前对话没有 DAG（standard 模式或未启用）。"
    revisions = projection.get("revisions") or {}
    lines = [
        f"对话: {conversation_id}",
        f"模式: {projection.get('mode')}"
        f"  process revision={revisions.get('process', 0)}"
        f"  delivery revision={revisions.get('delivery', 0)}",
        "",
    ]
    lines += format_graph_section("Process DAG（计算流程）", process_graph)
    lines.append("")
    lines += format_graph_section("Delivery DAG（化学机理）", delivery_graph)
    lines.append("")
    lines += format_delivery_report(delivery_report)
    lines.append("")
    lines += format_history(history)
    return "\n".join(lines)


def format_dag_summary(projection: dict | None) -> str:
    """侧栏「DAG」区摘要文本；无 DAG 时显示 standard（无 DAG）。"""
    if projection is None:
        return "standard（无 DAG）"
    revisions = projection.get("revisions") or {}
    lines = [
        f"模式: {projection.get('mode')}",
        f"revision: process={revisions.get('process', 0)}"
        f" delivery={revisions.get('delivery', 0)}",
    ]
    frontier = projection.get("frontier") or []
    for node in frontier[:5]:
        lines.append(f"· {node.get('node_id')} {node.get('label') or ''}")
    lines.append(f"阻塞: {len(projection.get('blockers') or [])}")
    lines.append(f"机理缺口: {len(projection.get('delivery_gaps') or [])}")
    return "\n".join(lines)


class DagEditModal(ModalScreen[dict | None]):
    """DAG 编辑表单弹窗；返回 {"operation": ..., "rationale": ...} 或 None（关闭）。

    JSON 解析失败/必填字段缺失时在表单内提示，不关闭弹窗也不调后端。
    """

    BINDINGS = [
        ("escape", "close", "关闭"),
    ]

    def compose(self) -> ComposeResult:
        with Grid(id="dag-edit-dialog"):
            yield Label("✎ 编辑 DAG", id="dag-edit-title")
            yield Label("图:")
            yield Select(
                ((("process（计算流程）", "process"), ("delivery（化学机理）", "delivery"))),
                value="process",
                id="edit-graph",
                allow_blank=False,
            )
            yield Label("操作:")
            yield Select(
                ((op, op) for op in _EDIT_OPS),
                value="add_node",
                id="edit-op",
                allow_blank=False,
            )
            yield Input(placeholder="node_id（add_node/update_node 必填）", id="edit-node-id")
            yield Input(
                placeholder="node_type（add_node，默认 planned）", id="edit-node-type"
            )
            yield Input(
                placeholder="edge_id（add_edge/update_edge/remove_edge 必填）",
                id="edit-edge-id",
            )
            yield Input(placeholder="source_node_id（add_edge 必填）", id="edit-source")
            yield Input(placeholder="target_node_id（add_edge 必填）", id="edit-target")
            yield Input(
                placeholder="edge_type（add_edge，默认 dependency）", id="edit-edge-type"
            )
            yield Input(placeholder="label", id="edit-label")
            yield Input(
                value=json_template("add_node"),
                placeholder="payload / changes（JSON）",
                id="edit-json",
            )
            yield Input(placeholder="修改理由（rationale）", id="edit-rationale")
            yield SafeStatic("", id="edit-error", markup=False)
            with Grid(id="dag-edit-buttons"):
                yield Button("提交", variant="primary", id="submit")
                yield Button("关闭", variant="default", id="close")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "edit-op":
            # 切换操作类型时预填对应的 JSON 模板
            self.query_one("#edit-json", Input).value = json_template(
                str(event.value)
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self._submit()
        elif event.button.id == "close":
            self.dismiss(None)

    def _error(self, message: str) -> None:
        self.query_one("#edit-error", SafeStatic).update(message)

    def _submit(self) -> None:
        graph = str(self.query_one("#edit-graph", Select).value)
        op_name = str(self.query_one("#edit-op", Select).value)

        json_text = self.query_one("#edit-json", Input).value.strip()
        try:
            json_data = json.loads(json_text) if json_text else {}
            if not isinstance(json_data, dict):
                raise ValueError("JSON 必须是对象")
        except ValueError as exc:
            if op_name in _CHANGES_OPS:
                kind = "changes"
            elif op_name in _DATA_OPS:
                kind = "data"
            else:
                kind = "payload"
            self._error(f"{kind} JSON 解析失败: {exc}")
            return

        fields = {
            "node_id": self.query_one("#edit-node-id", Input).value.strip(),
            "node_type": self.query_one("#edit-node-type", Input).value.strip(),
            "edge_id": self.query_one("#edit-edge-id", Input).value.strip(),
            "source_node_id": self.query_one("#edit-source", Input).value.strip(),
            "target_node_id": self.query_one("#edit-target", Input).value.strip(),
            "edge_type": self.query_one("#edit-edge-type", Input).value.strip(),
            "label": self.query_one("#edit-label", Input).value.strip(),
        }
        required = {
            "add_node": ("node_id",),
            "add_edge": ("edge_id", "source_node_id", "target_node_id"),
            "update_node": ("node_id",),
            "update_edge": ("edge_id",),
            "remove_edge": ("edge_id",),
        }.get(op_name, ())
        missing = [name for name in required if not fields[name]]
        if missing:
            self._error(f"缺少必填字段: {', '.join(missing)}")
            return

        data_required = _DATA_REQUIRED_KEYS.get(op_name, ())
        data_missing = [key for key in data_required if not json_data.get(key)]
        if data_missing:
            self._error(f"data JSON 缺少必填键: {', '.join(data_missing)}")
            return

        rationale = self.query_one("#edit-rationale", Input).value.strip()
        # 引擎强制 remove_edge 批次必须带 rationale，客户端先拦一次
        if op_name == "remove_edge" and not rationale:
            self._error("remove_edge 必须填写修改理由（rationale）")
            return

        operation = build_operation(graph, op_name, json_data=json_data, **fields)
        self.dismiss({"operation": operation, "rationale": rationale})

    def action_close(self) -> None:
        self.dismiss(None)


class DagScreen(Screen):
    """全屏 DAG 视图：双图节点/边、delivery 覆盖报告、近期变更历史。

    r 刷新；e 打开编辑弹窗（修改经引擎原子校验后生效）；
    p 请求 Supervisor 重新规划（仅 dag_guided 会话）。
    """

    BINDINGS = [
        ("escape", "dismiss", "关闭"),
        ("q", "dismiss", "关闭"),
        ("r", "refresh", "刷新"),
        ("e", "edit", "编辑"),
        ("p", "replan", "重新规划"),
    ]

    def __init__(self, service: CloudraService, conversation_id: str) -> None:
        super().__init__()
        self.service = service
        self.conversation_id = conversation_id

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="dag-scroll"):
            yield Label("DAG 编排", id="dag-title")
            yield SafeStatic("加载中…", id="dag-content", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        await self.action_refresh()

    def _load_content(self) -> str:
        """同步拉取并渲染全部 DAG 数据（在 worker 线程中调用）。"""
        cid = self.conversation_id
        projection = self.service.dag_projection(cid)
        if projection is None:
            return format_dag_content(None, None, None, None, None, conversation_id=cid)
        return format_dag_content(
            projection,
            self.service.dag_graph(cid, "process"),
            self.service.dag_graph(cid, "delivery"),
            self.service.dag_delivery_report(cid),
            self.service.dag_history(cid),
            conversation_id=cid,
        )

    async def action_refresh(self) -> None:
        try:
            content = await asyncio.to_thread(self._load_content)
        except Exception as exc:
            content = f"加载 DAG 失败: {exc}"
        self.query_one("#dag-content", SafeStatic).update(content)

    def action_edit(self) -> None:
        try:
            projection = self.service.dag_projection(self.conversation_id)
        except Exception as exc:
            self.notify(f"读取 DAG 失败: {exc}", severity="error")
            return
        if projection is None:
            self.notify("当前对话没有 DAG，无法编辑", severity="warning")
            return

        def on_result(result: dict | None) -> None:
            if result is not None:
                asyncio.create_task(self._apply_mutation(result))

        self.app.push_screen(DagEditModal(), callback=on_result)

    async def _apply_mutation(self, result: dict) -> None:
        """以最新 revisions 为基线提交用户修改，并反馈引擎校验结果。"""
        try:
            # 提交前重新拉一次 projection，避免并发修改导致 stale_revision
            projection = await asyncio.to_thread(
                self.service.dag_projection, self.conversation_id
            )
            if projection is None:
                self.notify("当前对话没有 DAG，无法编辑", severity="warning")
                return
            mutation = await asyncio.to_thread(
                self.service.dag_apply_user_mutation,
                self.conversation_id,
                [result["operation"]],
                projection.get("revisions") or {},
                result.get("rationale") or "",
            )
        except Exception as exc:
            self.notify(f"修改提交失败: {exc}", severity="error")
            return
        if mutation is None:
            self.notify("当前对话没有 DAG，无法编辑", severity="warning")
            return
        if mutation.get("accepted"):
            revisions = mutation.get("revisions") or {}
            self.notify(
                f"修改已生效: process revision={revisions.get('process', 0)}"
                f" delivery revision={revisions.get('delivery', 0)}",
                severity="information",
            )
            await self.action_refresh()
        else:
            self.notify(
                f"修改被拒绝 [{mutation.get('rejection_code')}]:"
                f" {mutation.get('rejection_reason') or ''}",
                severity="error",
            )

    def action_replan(self) -> None:
        asyncio.create_task(self._request_replan())

    async def _request_replan(self) -> None:
        """请求 Supervisor 重新规划（user_replan）；仅 dag_guided 会话可用。"""
        try:
            projection = await asyncio.to_thread(
                self.service.dag_projection, self.conversation_id
            )
        except Exception as exc:
            self.notify(f"读取 DAG 失败: {exc}", severity="error")
            return
        if projection is None:
            self.notify("当前对话没有 DAG，无法重新规划", severity="warning")
            return
        if projection.get("mode") != "dag_guided":
            self.notify(
                f"重新规划仅在 dag_guided 模式可用（当前: {projection.get('mode')}）",
                severity="warning",
            )
            return
        try:
            result = await self.service.dag_request_replan(self.conversation_id)
        except ValueError as exc:
            self.notify(str(exc), severity="warning")
            return
        except Exception as exc:
            self.notify(f"重新规划失败: {exc}", severity="error")
            return
        if result is None:
            self.notify("当前对话没有 DAG，无法重新规划", severity="warning")
            return
        self.notify(
            f"重新规划完成: {result.get('summary') or ''}",
            severity="information",
        )
        await self.action_refresh()

    def action_dismiss(self) -> None:
        self.dismiss()
