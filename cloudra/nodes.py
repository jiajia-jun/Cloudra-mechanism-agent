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
from cloudra.config import get_config

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
_CAPABILITY = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+\Z")


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

    def public(self) -> dict:
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "state": self.state,
            "server_version": __version__,
            "protocol_version": 1,
            "scheduler": str(self.scheduler.get("type", "local")),
            "capabilities": list(self.capabilities),
        }


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

        configured = getattr(get_config(), "workspace_dir", None)
        candidate = Path(configured).expanduser() if configured else Path.cwd()
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
            "cpus", "memory", "poll_seconds",
        }
        unknown = set(value) - allowed
        if unknown:
            raise NodeRegistryError(
                f"unknown scheduler fields: {sorted(unknown)}"
            )
        return dict(value, type=scheduler_type)

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
