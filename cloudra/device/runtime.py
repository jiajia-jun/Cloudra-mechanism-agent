"""Foreground Android executor for durable server-side device tool calls."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from cloudra import __version__
from cloudra.device.registry import (
    DEVICE_TOOLS,
    DeviceToolContext,
    capability_manifest,
    capability_revision,
)


class DeviceStateStore:
    """Atomic non-secret local state; device credentials are never persisted."""

    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def identity(self) -> dict:
        raw = self._load().get("identity", {})
        return raw if isinstance(raw, dict) else {}

    def save_identity(self, device_id: str, display_name: str) -> None:
        data = self._load()
        data["identity"] = {
            "device_id": device_id,
            "display_name": display_name,
        }
        self._save(data)

    def runtime_enabled(self) -> bool:
        return bool(self._load().get("runtime_enabled", False))

    def set_runtime_enabled(self, enabled: bool) -> None:
        data = self._load()
        data["runtime_enabled"] = bool(enabled)
        self._save(data)

    def revisions(self) -> tuple[int, int]:
        raw = self._load().get("revisions", {})
        if not isinstance(raw, dict):
            raw = {}
        try:
            workspace_revision = max(1, int(raw.get("workspace", 1)))
            config_revision = max(1, int(raw.get("config", 1)))
        except (TypeError, ValueError):
            return 1, 1
        return workspace_revision, config_revision

    def authorize_workspace(self, workspace: Path) -> tuple[int, int]:
        data = self._load()
        revisions = data.setdefault(
            "revisions",
            {"workspace": 1, "config": 1},
        )
        previous = data.get("workspace")
        current = str(workspace.expanduser().resolve())
        if previous != current:
            revisions["workspace"] = int(revisions.get("workspace", 1)) + 1
            data["workspace"] = current
            data.pop("workspace_snapshot", None)
        self._save(data)
        return self.revisions()

    @staticmethod
    def _workspace_snapshot(
        workspace: Path,
        *,
        max_entries: int = 2_000,
        max_depth: int = 8,
    ) -> tuple[dict[str, str], bool]:
        root = workspace.expanduser().resolve()
        snapshot: dict[str, str] = {}
        truncated = False
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack and len(snapshot) < max_entries:
            directory, depth = stack.pop()
            try:
                children = sorted(
                    os.scandir(directory),
                    key=lambda item: item.name,
                    reverse=True,
                )
            except OSError:
                continue
            for child in children:
                if len(snapshot) >= max_entries:
                    truncated = True
                    break
                try:
                    relative = Path(child.path).relative_to(root).as_posix()
                    stat = child.stat(follow_symlinks=False)
                    if child.is_symlink():
                        kind = "symlink"
                    elif child.is_dir(follow_symlinks=False):
                        kind = "directory"
                    elif child.is_file(follow_symlinks=False):
                        kind = "file"
                    else:
                        kind = "other"
                    snapshot[relative] = (
                        f"{kind}:{stat.st_size}:{stat.st_mtime_ns}"
                    )
                    if kind == "directory" and depth < max_depth:
                        stack.append((Path(child.path), depth + 1))
                except (OSError, ValueError):
                    continue
        if stack:
            truncated = True
        return snapshot, truncated

    @staticmethod
    def _snapshot_changes(
        previous: dict[str, str],
        current: dict[str, str],
    ) -> tuple[list[dict[str, str]], bool]:
        changes = []
        truncated = False
        for path in sorted(set(previous) | set(current)):
            if path not in previous:
                action = "added"
            elif path not in current:
                action = "deleted"
            elif previous[path] != current[path]:
                action = "modified"
            else:
                continue
            if len(changes) >= 100:
                truncated = True
                break
            changes.append({"path": path, "change": action})
        return changes, truncated

    @staticmethod
    def _queue_observation(
        data: dict,
        event_type: str,
        revision: int,
        payload: dict,
    ) -> None:
        pending = data.setdefault("pending_observations", {})
        if not isinstance(pending, dict):
            pending = {}
            data["pending_observations"] = pending
        observation_id = f"obs_{uuid.uuid4().hex}"
        pending[observation_id] = {
            "observation_id": observation_id,
            "event_type": event_type,
            "revision": int(revision),
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        while len(pending) > 256:
            pending.pop(next(iter(pending)))

    def observe_workspace(self, workspace: Path) -> int:
        """Detect external workspace changes and queue a durable observation."""

        data = self._load()
        revisions = data.setdefault(
            "revisions",
            {"workspace": 1, "config": 1},
        )
        current, scan_truncated = self._workspace_snapshot(workspace)
        previous = data.get("workspace_snapshot")
        if not isinstance(previous, dict):
            data["workspace_snapshot"] = current
            self._save(data)
            return int(revisions.get("workspace", 1))
        changes, change_truncated = self._snapshot_changes(
            previous,
            current,
        )
        if changes:
            revision = int(revisions.get("workspace", 1)) + 1
            revisions["workspace"] = revision
            data["workspace_snapshot"] = current
            self._queue_observation(
                data,
                "workspace.changed",
                revision,
                {
                    "changes": changes,
                    "truncated": scan_truncated or change_truncated,
                },
            )
            self._save(data)
            return revision
        return int(revisions.get("workspace", 1))

    def public_config(self, default_display_name: str) -> dict:
        raw = self._load().get("config", {})
        if not isinstance(raw, dict):
            raw = {}
        try:
            max_read_bytes = int(raw.get("max_read_bytes", 262_144))
        except (TypeError, ValueError):
            max_read_bytes = 262_144
        return {
            "display_name": (
                str(raw.get("display_name", default_display_name)).strip()
                or default_display_name
            )[:100],
            "max_read_bytes": min(
                max(max_read_bytes, 1_024),
                1_048_576,
            ),
        }

    def bump_workspace_revision(self, changed_path: str = "") -> int:
        data = self._load()
        revisions = data.setdefault(
            "revisions",
            {"workspace": 1, "config": 1},
        )
        revisions["workspace"] = int(revisions.get("workspace", 1)) + 1
        workspace = data.get("workspace")
        previous = data.get("workspace_snapshot")
        changes: list[dict[str, str]] = []
        truncated = False
        if isinstance(workspace, str):
            current, scan_truncated = self._workspace_snapshot(
                Path(workspace)
            )
            if isinstance(previous, dict):
                changes, truncated = self._snapshot_changes(
                    previous,
                    current,
                )
            data["workspace_snapshot"] = current
            truncated = truncated or scan_truncated
        if not changes and changed_path:
            changes = [{"path": changed_path, "change": "modified"}]
        self._queue_observation(
            data,
            "workspace.changed",
            int(revisions["workspace"]),
            {"changes": changes, "truncated": truncated},
        )
        self._save(data)
        return int(revisions["workspace"])

    def apply_config_patch(
        self,
        expected_revision: int,
        patch: dict,
        old_values: dict | None = None,
    ) -> dict:
        data = self._load()
        revisions = data.setdefault(
            "revisions",
            {"workspace": 1, "config": 1},
        )
        current_revision = int(revisions.get("config", 1))
        if current_revision != int(expected_revision):
            raise ValueError(
                "配置在审批期间已变化，请重新读取后再修改"
            )
        config = data.setdefault("config", {})
        if not isinstance(config, dict):
            config = {}
            data["config"] = config
        recorded_old_values = (
            dict(old_values)
            if old_values is not None
            else {key: config.get(key) for key in patch}
        )
        config.update(patch)
        new_revision = current_revision + 1
        revisions["config"] = new_revision
        audit = data.setdefault("config_audit", [])
        if not isinstance(audit, list):
            audit = []
            data["config_audit"] = audit
        audit.append(
            {
                "old_values": recorded_old_values,
                "new_values": dict(patch),
                "before_revision": current_revision,
                "after_revision": new_revision,
                "applied_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        del audit[:-50]
        self._queue_observation(
            data,
            "config.changed",
            new_revision,
            {"changed_keys": sorted(patch)},
        )
        self._save(data)
        return {
            "status": "applied",
            "old_values": recorded_old_values,
            "new_values": dict(patch),
            "config_revision": new_revision,
        }

    def completed(self, tool_call_id: str) -> dict | None:
        data = self._load()
        outbox = data.get("outbox", {})
        if isinstance(outbox, dict):
            pending = outbox.get(tool_call_id)
            if isinstance(pending, dict):
                return pending
        completed = data.get("completed", {})
        if not isinstance(completed, dict):
            return None
        value = completed.get(tool_call_id)
        if not isinstance(value, dict):
            return None
        if value.get("_cloudra_completed") is True:
            return {
                "status": "failed",
                "result": {
                    "native_status": "duplicate_after_ack",
                    "result_sha256": value.get("payload_sha256", ""),
                },
                "error": (
                    "设备已执行并由服务器确认过该调用；"
                    "为避免重复副作用，拒绝再次执行"
                ),
            }
        # Migration path for Phase 5/6 development state. The full payload is
        # returned once if it still needs replay; mark_sent() replaces it with
        # a compact tombstone after the server acknowledges it.
        return value

    @staticmethod
    def _completion_tombstone(payload: dict, *, acknowledged: bool) -> dict:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return {
            "_cloudra_completed": True,
            "status": str(payload.get("status", "failed")),
            "payload_sha256": hashlib.sha256(encoded).hexdigest(),
            "acknowledged": bool(acknowledged),
        }

    def record_completed(self, tool_call_id: str, payload: dict) -> None:
        data = self._load()
        completed = data.setdefault("completed", {})
        if not isinstance(completed, dict):
            completed = {}
            data["completed"] = completed
        completed[tool_call_id] = self._completion_tombstone(
            payload,
            acknowledged=False,
        )
        while len(completed) > 256:
            completed.pop(next(iter(completed)))
        outbox = data.setdefault("outbox", {})
        if not isinstance(outbox, dict):
            outbox = {}
            data["outbox"] = outbox
        outbox[tool_call_id] = payload
        self._save(data)

    def outbox(self) -> dict[str, dict]:
        raw = self._load().get("outbox", {})
        if not isinstance(raw, dict):
            return {}
        return {
            key: value
            for key, value in raw.items()
            if isinstance(key, str) and isinstance(value, dict)
        }

    def mark_sent(self, tool_call_id: str) -> None:
        data = self._load()
        outbox = data.get("outbox", {})
        payload = None
        if isinstance(outbox, dict):
            payload = outbox.pop(tool_call_id, None)
        completed = data.get("completed", {})
        if isinstance(completed, dict):
            existing = completed.get(tool_call_id)
            if isinstance(payload, dict):
                completed[tool_call_id] = self._completion_tombstone(
                    payload,
                    acknowledged=True,
                )
            elif (
                isinstance(existing, dict)
                and existing.get("_cloudra_completed") is True
            ):
                existing["acknowledged"] = True
            elif isinstance(existing, dict):
                completed[tool_call_id] = self._completion_tombstone(
                    existing,
                    acknowledged=True,
                )
        self._save(data)

    def pending_observations(self) -> list[dict]:
        raw = self._load().get("pending_observations", {})
        if not isinstance(raw, dict):
            return []
        return [
            value
            for value in raw.values()
            if isinstance(value, dict)
        ][:64]

    def mark_observations_sent(self, observation_ids: list[str]) -> None:
        if not observation_ids:
            return
        data = self._load()
        pending = data.get("pending_observations", {})
        if isinstance(pending, dict):
            for observation_id in observation_ids:
                pending.pop(str(observation_id), None)
        self._save(data)


class DeviceRuntime:
    """Poll/lease executor designed for the Android app's foreground lifetime."""

    def __init__(
        self,
        backend,
        state_store: DeviceStateStore,
        workspace: Path,
        *,
        display_name: str = "Cloudra Android",
        status_callback: Callable[[str], None] | None = None,
        approval_handler: (
            Callable[[dict, dict], Awaitable[tuple[bool, str]]] | None
        ) = None,
        native_bridge=None,
        credential_handler: (
            Callable[[str, str], Awaitable[None]] | None
        ) = None,
    ):
        self.backend = backend
        self.state_store = state_store
        self.workspace = workspace.expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.display_name = self.state_store.public_config(
            display_name
        )["display_name"]
        self.status_callback = status_callback
        self.approval_handler = approval_handler
        self.native_bridge = native_bridge
        self.credential_handler = credential_handler
        self.device_id = ""
        self._device_token = ""
        self._announced = False
        self._announced_capability_revision: int | None = None
        self._stop = asyncio.Event()
        self._finished = asyncio.Event()
        self._running = False
        self.workspace_revision, self.config_revision = (
            self.state_store.authorize_workspace(self.workspace)
        )

    @property
    def paired(self) -> bool:
        return bool(self.device_id and self._device_token)

    def _status(self, value: str) -> None:
        if self.status_callback is not None:
            self.status_callback(value)

    def manifest(self) -> dict:
        return {
            "display_name": self.display_name,
            "client_version": __version__,
            "capabilities": capability_manifest(),
            "capability_revision": capability_revision(),
            "workspace_revision": self.workspace_revision,
            "config_revision": self.config_revision,
        }

    async def pair(self) -> dict:
        credential = await self.backend.pair_device(self.manifest())
        self.device_id = credential["device_id"]
        self._device_token = credential["device_token"]
        self.display_name = credential.get("display_name", self.display_name)
        if self.credential_handler is not None:
            await self.credential_handler(
                self.device_id,
                self._device_token,
            )
        self.state_store.save_identity(self.device_id, self.display_name)
        self._announced = False
        self._announced_capability_revision = None
        self._status("设备已配对")
        return {
            key: value
            for key, value in credential.items()
            if key != "device_token"
        }

    def restore_pairing(
        self,
        device_id: str,
        device_token: str,
        *,
        display_name: str | None = None,
    ) -> None:
        """Restore a Keystore-backed credential without persisting its token."""

        device_id = str(device_id).strip()
        device_token = str(device_token).strip()
        if not device_id or not device_token:
            raise ValueError("设备身份或凭据为空")
        self.device_id = device_id
        self._device_token = device_token
        if display_name:
            self.display_name = str(display_name).strip()[:100]
        self._announced = False
        self._announced_capability_revision = None

    async def announce(self) -> dict:
        if not self.paired:
            raise RuntimeError("设备尚未配对")
        result = await self.backend.device_hello(
            self.device_id,
            self._device_token,
            self.manifest(),
        )
        self._announced = True
        self._announced_capability_revision = capability_revision()
        self._status("设备在线")
        return result

    def _context(self) -> DeviceToolContext:
        return DeviceToolContext(
            workspace=self.workspace,
            workspace_revision=self.workspace_revision,
            config_revision=self.config_revision,
            device_id=self.device_id,
            display_name=self.display_name,
            state_store=self.state_store,
        )

    async def _submit_payload(self, tool_call_id: str, payload: dict) -> None:
        await self.backend.device_tool_result(
            self.device_id,
            self._device_token,
            tool_call_id,
            payload,
        )
        self.state_store.mark_sent(tool_call_id)

    async def flush_outbox(self) -> None:
        for tool_call_id, payload in self.state_store.outbox().items():
            await self._submit_payload(tool_call_id, payload)

    @staticmethod
    def _expired(call: dict) -> bool:
        try:
            expiry = datetime.fromisoformat(str(call["expires_at"]))
        except (KeyError, TypeError, ValueError):
            return True
        return expiry <= datetime.now(timezone.utc)

    async def _execute(self, call: dict) -> None:
        tool_call_id = str(call["tool_call_id"])
        existing = self.state_store.completed(tool_call_id)
        if existing is not None:
            await self._submit_payload(tool_call_id, existing)
            return
        lease_id = str(call["lease_id"])
        await self.backend.device_tool_action(
            self.device_id,
            self._device_token,
            tool_call_id,
            "ack",
            lease_id,
        )
        if self._expired(call):
            payload = {
                "status": "failed",
                "result": {},
                "error": "设备调用已过期",
            }
        elif (
            call.get("expected_workspace_revision") is not None
            and int(call["expected_workspace_revision"])
            != self.workspace_revision
        ):
            payload = {
                "status": "failed",
                "result": {
                    "workspace_revision": self.workspace_revision,
                },
                "error": "设备工作区 revision 不匹配",
            }
        else:
            spec = DEVICE_TOOLS.get(str(call.get("tool", "")))
            if spec is None:
                payload = {
                    "status": "failed",
                    "result": {},
                    "error": "设备未注册该工具",
                }
            else:
                try:
                    if spec.requires_approval:
                        if spec.prepare is None:
                            raise RuntimeError("设备审批工具缺少 prepare")
                        preview, prepared = await asyncio.to_thread(
                            spec.prepare,
                            call.get("arguments") or {},
                            self._context(),
                        )
                        await self.backend.device_tool_action(
                            self.device_id,
                            self._device_token,
                            tool_call_id,
                            "waiting-for-approval",
                            lease_id,
                        )
                        if self.approval_handler is None:
                            approved, reason = (
                                False,
                                "Android 本地审批界面不可用",
                            )
                        else:
                            approved, reason = await self.approval_handler(
                                call,
                                preview,
                            )
                        if not approved:
                            payload = {
                                "status": "declined",
                                "result": {
                                    "preview": preview,
                                },
                                "error": reason or "用户拒绝了设备写操作",
                            }
                        else:
                            await self.backend.device_tool_action(
                                self.device_id,
                                self._device_token,
                                tool_call_id,
                                "running",
                                lease_id,
                            )
                            if spec.native_action is not None:
                                if self.native_bridge is None:
                                    raise RuntimeError(
                                        "Android 原生桥不可用"
                                    )
                                result = await self.native_bridge.execute(
                                    spec.native_action,
                                    prepared,
                                )
                            else:
                                if spec.apply is None:
                                    raise RuntimeError(
                                        "设备写工具缺少 apply"
                                    )
                                result = await asyncio.to_thread(
                                    spec.apply,
                                    prepared,
                                    self._context(),
                                )
                            if result.get("status") == "cancelled":
                                payload = {
                                    "status": "declined",
                                    "result": result,
                                    "error": "用户取消了 Android 系统交互",
                                }
                            else:
                                payload = {
                                    "status": "succeeded",
                                    "result": result,
                                    "error": "",
                                }
                    else:
                        await self.backend.device_tool_action(
                            self.device_id,
                            self._device_token,
                            tool_call_id,
                            "running",
                            lease_id,
                        )
                        if spec.native_action is not None:
                            if self.native_bridge is None:
                                raise RuntimeError("Android 原生桥不可用")
                            result = await self.native_bridge.execute(
                                spec.native_action,
                                call.get("arguments") or {},
                            )
                        else:
                            if spec.handler is None:
                                raise RuntimeError(
                                    "设备只读工具缺少 handler"
                                )
                            result = await asyncio.to_thread(
                                spec.handler,
                                call.get("arguments") or {},
                                self._context(),
                            )
                        payload = {
                            "status": "succeeded",
                            "result": result,
                            "error": "",
                        }
                except asyncio.CancelledError:
                    payload = {
                        "status": "declined",
                        "result": {
                            "native_status": "runtime_stopped",
                        },
                        "error": (
                            "Android Device Runtime 在本地操作完成前停止"
                        ),
                    }
                except Exception as exc:
                    native_status = str(
                        getattr(exc, "status", "")
                    ).strip()
                    native_payload = getattr(exc, "payload", {})
                    if not isinstance(native_payload, dict):
                        native_payload = {}
                    if native_status:
                        native_payload = {
                            **native_payload,
                            "native_status": native_status,
                        }
                    payload = {
                        "status": (
                            "declined"
                            if native_status == "cancelled"
                            else "failed"
                        ),
                        "result": native_payload,
                        "error": str(exc)[:2_000],
                    }
        result = payload.get("result") or {}
        if payload["status"] == "succeeded":
            if "workspace_revision" in result:
                self.workspace_revision = int(
                    result["workspace_revision"]
                )
            if "config_revision" in result:
                self.config_revision = int(result["config_revision"])
                config = self.state_store.public_config(self.display_name)
                self.display_name = config["display_name"]
                self.state_store.save_identity(
                    self.device_id,
                    self.display_name,
                )
                self._announced = False
        self.state_store.record_completed(tool_call_id, payload)
        await self._submit_payload(tool_call_id, payload)

    async def run_once(self) -> int:
        if (
            self._announced_capability_revision is not None
            and self._announced_capability_revision
            != capability_revision()
        ):
            self._announced = False
        if not self._announced:
            await self.announce()
        self.workspace_revision = self.state_store.observe_workspace(
            self.workspace
        )
        observations = self.state_store.pending_observations()
        heartbeat = await self.backend.device_heartbeat(
            self.device_id,
            self._device_token,
            self.workspace_revision,
            self.config_revision,
            observations,
        )
        self.state_store.mark_observations_sent(
            list(heartbeat.get("accepted_observation_ids", []))
        )
        await self.flush_outbox()
        calls = await self.backend.lease_device_tool_calls(
            self.device_id,
            self._device_token,
        )
        for call in calls:
            if self._stop.is_set():
                break
            await self._execute(call)
        return len(calls)

    async def run(self, *, poll_seconds: float = 2.0) -> None:
        self._stop.clear()
        self._finished.clear()
        self._running = True
        try:
            while not self._stop.is_set():
                try:
                    await self.run_once()
                    self._status("设备在线")
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    self._announced = False
                    self._status(f"设备连接中断：{exc}")
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=max(0.5, poll_seconds),
                    )
                except TimeoutError:
                    pass
        finally:
            self._running = False
            self._finished.set()

    def stop(self) -> None:
        self._stop.set()

    async def wait_stopped(self) -> None:
        if self._running:
            await self._finished.wait()
