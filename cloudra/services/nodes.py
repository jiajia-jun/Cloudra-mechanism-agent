"""Validated server-side node and workspace registry.

The first Phase 8 implementation keeps execution in one Cloudra server process
but makes routing explicit. A later gateway can replace the loader without
changing the Android/API contract.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from cloudra import __version__

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
_CAPABILITY = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+\Z")
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class NodeRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class WorkspaceRoute:
    workspace_id: str
    node_id: str
    display_name: str
    path: Path
    access: str = "read_write"

    def public(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "node_id": self.node_id,
            "display_name": self.display_name,
            "path": str(self.path),
            "access": self.access,
        }


@dataclass(frozen=True)
class NodeRoute:
    node_id: str
    display_name: str
    state: str
    workspaces: tuple[WorkspaceRoute, ...]
    scheduler: dict
    capabilities: tuple[str, ...]
    resources: dict

    def public(self) -> dict:
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "state": self.state,
            "server_version": __version__,
            "protocol_version": 1,
            "scheduler": str(self.scheduler.get("type", "local")),
            "capabilities": list(self.capabilities),
            "resources": dict(self.resources),
        }


_DEFAULT_SLOTS = 10
_MEMORY_RESERVE_MB = 8192


def default_resources() -> dict:
    """本地节点的兜底资源量：全核 + 内存记账额度 + ``_DEFAULT_SLOTS`` 槽位。

    守护进程只按 agent 声明的 req_* 记账，这里的上限是**记账额度**不是硬预留：
    agent 的声明普遍偏保守（ORCA ``%maxcore`` 是每核上限），实际占用远低于声明。
    内存额度 = 物理内存扣掉留给系统其他进程的 ``_MEMORY_RESERVE_MB``，且不低于
    物理内存的一半（小机器不因新公式变宽松）。
    """
    cpus = os.cpu_count() or 1
    memory_mb = 4096
    try:
        physical_mb = (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) // (1024 * 1024)
        memory_mb = max(physical_mb // 2, physical_mb - _MEMORY_RESERVE_MB)
    except (ValueError, OSError, AttributeError):
        pass
    return {"max_concurrent": _DEFAULT_SLOTS, "cpus": cpus, "memory_mb": memory_mb}


class NodeRegistry:
    def __init__(self, nodes: tuple[NodeRoute, ...], default_node_id: str):
        self.nodes = nodes
        self.default_node_id = default_node_id
        self._nodes = {node.node_id: node for node in nodes}
        if default_node_id not in self._nodes:
            raise NodeRegistryError("default_node_id does not exist")

    @staticmethod
    def _identifier(value: object, field: str) -> str:
        text = str(value or "").strip()
        if not _IDENTIFIER.fullmatch(text):
            raise NodeRegistryError(f"invalid {field}: {text!r}")
        return text

    @staticmethod
    def _workspace_path(value: object) -> Path:
        path = Path(str(value or "")).expanduser()
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise NodeRegistryError(f"workspace path is unavailable: {path}") from exc
        if not resolved.is_dir():
            raise NodeRegistryError(f"workspace path is not a directory: {resolved}")
        return resolved

    @classmethod
    def from_dict(cls, payload: object) -> "NodeRegistry":
        if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
            raise NodeRegistryError("node registry must contain a nodes list")
        routes: list[NodeRoute] = []
        seen_nodes: set[str] = set()
        seen_routes: set[tuple[str, str]] = set()
        for raw_node in payload["nodes"]:
            if not isinstance(raw_node, dict):
                raise NodeRegistryError("node entry must be an object")
            node_id = cls._identifier(raw_node.get("node_id"), "node_id")
            if node_id in seen_nodes:
                raise NodeRegistryError(f"duplicate node_id: {node_id}")
            seen_nodes.add(node_id)
            raw_workspaces = raw_node.get("workspaces", [])
            if not isinstance(raw_workspaces, list) or not raw_workspaces:
                raise NodeRegistryError(f"node {node_id} has no workspaces")
            workspaces: list[WorkspaceRoute] = []
            for raw_workspace in raw_workspaces:
                if not isinstance(raw_workspace, dict):
                    raise NodeRegistryError("workspace entry must be an object")
                workspace_id = cls._identifier(
                    raw_workspace.get("workspace_id"), "workspace_id"
                )
                route_key = (node_id, workspace_id)
                if route_key in seen_routes:
                    raise NodeRegistryError(
                        f"duplicate workspace route: {node_id}/{workspace_id}"
                    )
                seen_routes.add(route_key)
                access = str(raw_workspace.get("access", "read_write"))
                if access not in {"read_only", "read_write"}:
                    raise NodeRegistryError(f"invalid workspace access: {access}")
                path = cls._workspace_path(raw_workspace.get("path"))
                workspaces.append(
                    WorkspaceRoute(
                        workspace_id=workspace_id,
                        node_id=node_id,
                        display_name=str(
                            raw_workspace.get("display_name") or path.name or path
                        )[:100],
                        path=path,
                        access=access,
                    )
                )
            scheduler = cls._scheduler(raw_node.get("scheduler"))
            routes.append(
                NodeRoute(
                    node_id=node_id,
                    display_name=str(raw_node.get("display_name") or node_id)[:100],
                    state=str(raw_node.get("state", "online")),
                    workspaces=tuple(workspaces),
                    scheduler=scheduler,
                    capabilities=cls._capabilities(
                        raw_node.get("capabilities"),
                        scheduler_type=str(scheduler.get("type")),
                    ),
                    resources=cls._resources(raw_node.get("resources")),
                )
            )
        default_node_id = cls._identifier(
            payload.get("default_node_id") or (routes[0].node_id if routes else ""),
            "default_node_id",
        )
        return cls(tuple(routes), default_node_id)

    @classmethod
    def from_environment(cls) -> "NodeRegistry":
        registry_file = os.getenv("CLOUDRA_NODE_REGISTRY_FILE", "").strip()
        if registry_file:
            path = Path(registry_file).expanduser().resolve(strict=True)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise NodeRegistryError(f"cannot load node registry: {path}") from exc
            return cls.from_dict(payload)

        candidate = Path.cwd()
        try:
            workspace = candidate.resolve(strict=True)
        except OSError:
            workspace = Path.cwd().resolve()
        if not workspace.is_dir():
            workspace = Path.cwd().resolve()
        node_id = cls._identifier(
            os.getenv("CLOUDRA_NODE_ID", "node-local"), "node_id"
        )
        return cls(
            (
                NodeRoute(
                    node_id=node_id,
                    display_name=os.getenv("CLOUDRA_SERVER_NAME", "Cloudra Server")[:100],
                    state="online",
                    workspaces=(
                        WorkspaceRoute(
                            workspace_id="default",
                            node_id=node_id,
                            display_name=workspace.name or str(workspace),
                            path=workspace,
                        ),
                    ),
                    scheduler={"type": "local"},
                    capabilities=(
                        "agent.session",
                        "artifact.download",
                        "compute.local",
                    ),
                    resources=default_resources(),
                ),
            ),
            node_id,
        )

    def node(self, node_id: str | None) -> NodeRoute:
        selected = node_id or self.default_node_id
        try:
            return self._nodes[selected]
        except KeyError as exc:
            raise NodeRegistryError(f"unknown node: {selected}") from exc

    def workspace(self, node_id: str | None, workspace_id: str) -> WorkspaceRoute:
        node = self.node(node_id)
        for workspace in node.workspaces:
            if workspace.workspace_id == workspace_id:
                return workspace
        raise NodeRegistryError(
            f"unknown workspace route: {node.node_id}/{workspace_id}"
        )

    def public_nodes(self) -> list[dict]:
        return [node.public() for node in self.nodes]

    def public_workspaces(self) -> list[dict]:
        return [
            workspace.public()
            for node in self.nodes
            for workspace in node.workspaces
        ]

    @staticmethod
    def _scheduler(value: object) -> dict:
        if value is None:
            return {"type": "local"}
        if not isinstance(value, dict):
            raise NodeRegistryError("scheduler must be an object")
        scheduler_type = str(value.get("type", "local"))
        if scheduler_type not in {"local", "slurm"}:
            raise NodeRegistryError(f"unsupported scheduler: {scheduler_type}")
        allowed = {
            "type", "partition", "account", "qos", "time_limit",
            "cpus", "memory", "poll_seconds", "modules", "environment",
        }
        unknown = set(value) - allowed
        if unknown:
            raise NodeRegistryError(
                f"unknown scheduler fields: {sorted(unknown)}"
            )
        scheduler = dict(value, type=scheduler_type)
        if "modules" in scheduler:
            modules = scheduler["modules"]
            if (
                not isinstance(modules, list)
                or not modules
                or any(not isinstance(module, str) or not module.strip() for module in modules)
            ):
                raise NodeRegistryError("scheduler modules must be a non-empty list of names")
            scheduler["modules"] = [module.strip() for module in modules]
        if "environment" in scheduler:
            environment = scheduler["environment"]
            if not isinstance(environment, dict):
                raise NodeRegistryError("scheduler environment must be an object")
            normalized_environment: dict[str, str] = {}
            for name, raw_value in environment.items():
                if not isinstance(name, str) or not _ENVIRONMENT_NAME.fullmatch(name):
                    raise NodeRegistryError(
                        f"invalid scheduler environment variable name: {name!r}"
                    )
                if (
                    not isinstance(raw_value, str)
                    or "\n" in raw_value
                    or "\r" in raw_value
                    or "\0" in raw_value
                ):
                    raise NodeRegistryError(
                        f"scheduler environment value for {name!r} must be a single-line string"
                    )
                normalized_environment[name] = raw_value
            scheduler["environment"] = normalized_environment
        return scheduler

    @staticmethod
    def _resources(value: object) -> dict:
        """节点资源量（调度器容量记账依据）；缺省用本地兜底值。"""
        if value is None:
            return default_resources()
        if not isinstance(value, dict):
            raise NodeRegistryError("resources must be an object")
        allowed = {"max_concurrent", "cpus", "memory_mb"}
        unknown = set(value) - allowed
        if unknown:
            raise NodeRegistryError(f"unknown resources fields: {sorted(unknown)}")
        merged = default_resources()
        for key in allowed:
            if key not in value:
                continue
            try:
                num = int(value[key])
            except (TypeError, ValueError) as exc:
                raise NodeRegistryError(f"resources.{key} must be a positive integer") from exc
            if num < 1:
                raise NodeRegistryError(f"resources.{key} must be a positive integer")
            merged[key] = num
        return merged

    @staticmethod
    def _capabilities(value: object, *, scheduler_type: str) -> tuple[str, ...]:
        if value is None:
            value = ["agent.session", "artifact.download", f"compute.{scheduler_type}"]
        if not isinstance(value, list):
            raise NodeRegistryError("capabilities must be a list")
        normalized: list[str] = []
        for raw in value:
            name = str(raw).strip()
            if not _CAPABILITY.fullmatch(name):
                raise NodeRegistryError(f"invalid node capability: {name!r}")
            if name in normalized:
                raise NodeRegistryError(f"duplicate node capability: {name}")
            normalized.append(name)
        required = f"compute.{scheduler_type}"
        if required not in normalized:
            raise NodeRegistryError(f"node scheduler requires capability: {required}")
        return tuple(normalized)

    def route_for_path(self, path: Path) -> tuple[NodeRoute, WorkspaceRoute]:
        resolved = path.expanduser().resolve(strict=True)
        matches: list[tuple[int, NodeRoute, WorkspaceRoute]] = []
        for node in self.nodes:
            for workspace in node.workspaces:
                if resolved == workspace.path or workspace.path in resolved.parents:
                    matches.append((len(workspace.path.parts), node, workspace))
        if not matches:
            raise NodeRegistryError(f"path is outside registered workspaces: {resolved}")
        _depth, node, workspace = max(matches, key=lambda item: item[0])
        return node, workspace
