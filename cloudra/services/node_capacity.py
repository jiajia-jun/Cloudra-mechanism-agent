"""多节点容量视图：注册节点 → 生效容量 + 在用量 + 余量。

容量池按节点解耦后，这一份口径被三个消费方共用：调度守护的认领额度
（``scheduler/daemon.py``）、agent 的容量查询工具（``query_compute_queue``）、
控制面 API（``GET /api/v2/compute/nodes``）。三处各写一遍必然漂移。

口径与边界：

- 生效容量 = ``min(注册声明, OS 实时余量)``，但**只有跑在本机的 local 节点**
  受 OS 余量约束（``host_capacity.effective_node_resources``）；远端/集群节点
  不在这台机器上，OS 读数对它没有意义，原样用注册声明。
- 在用量 = 中央 ``compute.db`` 里租约有效的 ``running`` 行，**按节点分组**；
  未声明内存的作业按该节点公平份额（``memory_mb // max_concurrent``）记账。
- 这里只做读数与展示：放行判定由认领在同一事务内现算（避免读写之间的额度
  漂移），进程存活/终态一律不在这里判。
"""

from __future__ import annotations

import os
from typing import Any, Optional

from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import compute_inflight_usage_by_node
from cloudra.services.host_capacity import (
    capacity_report,
    effective_node_resources,
    effective_resources,
)
from cloudra.services.nodes import NodeRegistry, default_resources

_ZERO = {"slots": 0, "cpus": 0, "memory_mb": 0}


def fair_share_mb(capacity: dict) -> int:
    """节点公平份额：未声明内存的作业按 ``memory_mb // max_concurrent`` 记账。"""
    slots = max(1, int(capacity.get("max_concurrent", 1)))
    return max(1, int(capacity.get("memory_mb", 1024)) // slots)


def _fallback_node_id() -> str:
    return os.getenv("CLOUDRA_NODE_ID", "node-local").strip() or "node-local"


def _registry_or_none() -> Optional[NodeRegistry]:
    try:
        return NodeRegistry.from_environment()
    except Exception:  # noqa: BLE001 - 注册表缺失/损坏 → 单节点兜底
        return None


def node_capacities() -> tuple[dict[str, dict], str]:
    """``({node_id: {max_concurrent, cpus, memory_mb}}, default_node_id)``。

    注册表缺失/损坏时退化为单节点（与 ``nodes.py`` 的单节点路由同一语义）。
    """
    registry = _registry_or_none()
    if registry is None:
        node_id = _fallback_node_id()
        return {node_id: effective_resources(default_resources())}, node_id
    from cloudra.services.host_capacity import node_capacities as _capacities

    return _capacities(registry), registry.default_node_id


def node_capacity_views(db: ComputeDB | None = None) -> tuple[list[dict[str, Any]], str]:
    """每节点容量视图 + 默认节点 id。

    视图字段：``node_id`` / ``display_name`` / ``scheduler`` / ``state`` /
    ``capacity{registered, os_available, effective}`` / ``in_flight`` / ``free``。
    传 ``db`` 时填在用量与余量（缺库/空库即在用量为 0）。
    """
    registry = _registry_or_none()
    if registry is None:
        node_id = _fallback_node_id()
        report = capacity_report(default_resources())
        view = {
            "node_id": node_id,
            "display_name": node_id,
            "scheduler": "local",
            "connection": "local",
            "remote": None,
            "state": "online",
            "capacity": {
                "registered": report["declared"],
                "os_available": report["os_available"],
                "effective": report["effective"],
            },
            "in_flight": dict(_ZERO),
            "free": dict(_ZERO),
        }
        _fill_free(view)
        return [view], node_id

    views: list[dict[str, Any]] = []
    for node in registry.nodes:
        effective = effective_node_resources(node)
        connection = dict(node.connection or {})
        if str(node.scheduler.get("type", "local")) == "local":
            report = capacity_report(dict(node.resources))
            capacity = {
                "registered": report["declared"],
                "os_available": report["os_available"],
                "effective": report["effective"],
            }
        else:
            capacity = {
                "registered": dict(node.resources),
                "os_available": {},
                "effective": effective,
            }
        view = {
            "node_id": node.node_id,
            "display_name": node.display_name,
            "scheduler": str(node.scheduler.get("type", "local")),
            "connection": str(connection.get("type", "local")),
            "remote": (
                f"{connection['user']}@{connection['host']}"
                if connection.get("type") == "ssh"
                else None
            ),
            "state": node.state,
            "capacity": capacity,
            "in_flight": dict(_ZERO),
            "free": dict(_ZERO),
        }
        _fill_free(view)
        views.append(view)

    default_node_id = registry.default_node_id
    if db is not None:
        try:
            usage = compute_inflight_usage_by_node(
                db,
                default_node_id=default_node_id,
                fair_share_mb={
                    view["node_id"]: fair_share_mb(view["capacity"]["effective"])
                    for view in views
                },
            )
        except Exception:  # noqa: BLE001 - 展示路径的读失败不退化为错误视图
            usage = {}
        for view in views:
            view["in_flight"] = dict(usage.get(view["node_id"], _ZERO))
            _fill_free(view)
    return views, default_node_id


def _fill_free(view: dict[str, Any]) -> None:
    """把 ``free`` 重算成 生效容量 − 在用量（不小于 0）。"""
    capacity = view["capacity"]["effective"]
    used = view["in_flight"]
    view["free"] = {
        "slots": max(0, int(capacity.get("max_concurrent", 1)) - int(used["slots"])),
        "cpus": max(0, int(capacity.get("cpus", 1)) - int(used["cpus"])),
        "memory_mb": max(0, int(capacity.get("memory_mb", 1024)) - int(used["memory_mb"])),
    }
