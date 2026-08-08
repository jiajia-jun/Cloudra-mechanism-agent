"""Durable server-side broker for paired Android tool nodes."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from cloudra.config import get_config

_DEVICE_ID = re.compile(r"^dev_[A-Za-z0-9_-]{12,120}$")
_TOOL_CALL_ID = re.compile(r"^dtc_[A-Za-z0-9_-]{12,150}$")
_OBSERVATION_ID = re.compile(r"^obs_[A-Za-z0-9_-]{12,150}$")
_FINAL_INVOCATION_STATES = frozenset(
    {"succeeded", "failed", "declined", "expired", "cancelled"}
)


class PairingError(ValueError):
    pass


class DeviceAuthenticationError(ValueError):
    pass


class DeviceInvocationError(ValueError):
    pass


class DeviceInvocationConflict(DeviceInvocationError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _json(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode(value: str | None, fallback):
    if value is None:
        return fallback
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return fallback
    return decoded


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_capabilities(capabilities: list[dict]) -> list[dict]:
    normalized = []
    seen = set()
    for raw in capabilities:
        if not isinstance(raw, dict):
            raise PairingError("设备能力清单格式无效")
        name = str(raw.get("name", "")).strip()
        if (
            not name.startswith("device.")
            or len(name) > 120
            or name in seen
        ):
            raise PairingError("设备能力名称无效或重复")
        seen.add(name)
        normalized.append(
            {
                "name": name,
                "schema_version": int(raw.get("schema_version", 1)),
                "execution_target": "device",
                "risk": str(raw.get("risk", "read")),
                "requires_approval": bool(
                    raw.get("requires_approval", False)
                ),
                "available": bool(raw.get("available", True)),
            }
        )
    return sorted(normalized, key=lambda item: item["name"])


def _normalize_observations(observations: list[dict]) -> list[dict]:
    if len(observations) > 64:
        raise ValueError("一次 heartbeat 最多携带 64 个 observation")
    normalized = []
    for raw in observations:
        if not isinstance(raw, dict):
            raise ValueError("设备 observation 格式无效")
        observation_id = str(raw.get("observation_id", ""))
        if not _OBSERVATION_ID.fullmatch(observation_id):
            raise ValueError("设备 observation_id 无效")
        event_type = str(raw.get("event_type", ""))
        if event_type not in {"workspace.changed", "config.changed"}:
            raise ValueError("设备 observation 类型无效")
        revision = max(0, int(raw.get("revision", 0)))
        payload = raw.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("设备 observation payload 无效")
        if event_type == "workspace.changed":
            clean_changes = []
            changes = payload.get("changes", [])
            if not isinstance(changes, list) or len(changes) > 100:
                raise ValueError("workspace observation changes 无效")
            for change in changes:
                if not isinstance(change, dict):
                    raise ValueError("workspace observation change 无效")
                path = str(change.get("path", ""))
                kind = str(change.get("change", ""))
                if (
                    not path
                    or len(path) > 300
                    or path.startswith("/")
                    or ".." in Path(path).parts
                    or any(ord(character) < 32 for character in path)
                    or kind not in {"added", "modified", "deleted"}
                ):
                    raise ValueError("workspace observation 路径或动作无效")
                clean_changes.append({"path": path, "change": kind})
            clean_payload = {
                "changes": clean_changes,
                "truncated": bool(payload.get("truncated", False)),
            }
        else:
            changed_keys = payload.get("changed_keys", [])
            if (
                not isinstance(changed_keys, list)
                or len(changed_keys) > 20
                or not all(
                    isinstance(key, str)
                    and key in {"display_name", "max_read_bytes"}
                    for key in changed_keys
                )
            ):
                raise ValueError("config observation changed_keys 无效")
            clean_payload = {"changed_keys": sorted(set(changed_keys))}
        created_at = str(raw.get("created_at", ""))[:64]
        normalized.append(
            {
                "observation_id": observation_id,
                "event_type": event_type,
                "revision": revision,
                "payload": clean_payload,
                "created_at": created_at,
            }
        )
    return normalized


class DeviceBroker:
    """SQLite-backed pairing, heartbeat, leasing, and result authority."""

    def __init__(self, data_dir: Path | None = None):
        configured = data_dir or Path(get_config().data_dir)
        root = Path(configured).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "device-broker.db"
        self._init()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=60)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA busy_timeout=60000")
            with con:
                yield con
        finally:
            con.close()

    def _init(self) -> None:
        with contextlib.closing(
            sqlite3.connect(self.path, timeout=60)
        ) as bootstrap:
            bootstrap.execute("PRAGMA busy_timeout=60000")
            bootstrap.execute("PRAGMA journal_mode=WAL")
            bootstrap.commit()
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS pairing_sessions(
                    pairing_id TEXT PRIMARY KEY,
                    secret_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS devices(
                    device_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    client_version TEXT NOT NULL,
                    protocol_version INTEGER NOT NULL,
                    capability_revision INTEGER NOT NULL,
                    workspace_revision INTEGER NOT NULL,
                    config_revision INTEGER NOT NULL,
                    capabilities TEXT NOT NULL,
                    paired_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS device_tool_invocations(
                    tool_call_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    expected_workspace_revision INTEGER,
                    state TEXT NOT NULL,
                    lease_id TEXT,
                    lease_expires_at TEXT,
                    expires_at TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    started_at TEXT,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_device_calls_delivery
                ON device_tool_invocations(device_id, state, created_at);
                CREATE INDEX IF NOT EXISTS idx_device_calls_session
                ON device_tool_invocations(conversation_id, session_id);
                CREATE TABLE IF NOT EXISTS device_observations(
                    observation_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    received_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_device_observations_device
                ON device_observations(device_id, received_at DESC);
                """
            )
            con.commit()

    def start_pairing(self, *, ttl_seconds: int = 300) -> dict:
        ttl_seconds = min(max(int(ttl_seconds), 30), 600)
        created_at = _now()
        expires_at = created_at + timedelta(seconds=ttl_seconds)
        pairing_id = f"pair_{uuid.uuid4().hex}"
        secret = secrets.token_urlsafe(24)
        with self._connect() as con:
            con.execute(
                "DELETE FROM pairing_sessions WHERE expires_at<=?",
                (_iso(created_at),),
            )
            con.execute(
                """INSERT INTO pairing_sessions
                (pairing_id, secret_hash, created_at, expires_at)
                VALUES (?, ?, ?, ?)""",
                (
                    pairing_id,
                    _hash_secret(secret),
                    _iso(created_at),
                    _iso(expires_at),
                ),
            )
            con.commit()
        return {
            "pairing_id": pairing_id,
            "pairing_secret": secret,
            "expires_at": _iso(expires_at),
        }

    def complete_pairing(
        self,
        *,
        pairing_id: str,
        pairing_secret: str,
        display_name: str,
        client_version: str,
        capabilities: list[dict],
        capability_revision: int,
        workspace_revision: int,
        config_revision: int,
    ) -> dict:
        normalized = _normalize_capabilities(capabilities)
        now = _iso(_now())
        token = f"devtok_{secrets.token_urlsafe(32)}"
        device_id = f"dev_{uuid.uuid4().hex}"
        safe_name = display_name.strip()[:100] or "Android Device"
        with self._connect() as con:
            row = con.execute(
                """SELECT secret_hash, expires_at, used_at
                FROM pairing_sessions WHERE pairing_id=?""",
                (pairing_id,),
            ).fetchone()
            if (
                row is None
                or row["used_at"] is not None
                or row["expires_at"] <= now
                or not hmac.compare_digest(
                    row["secret_hash"],
                    _hash_secret(pairing_secret),
                )
            ):
                raise PairingError("配对信息无效、已使用或已过期")
            claimed = con.execute(
                """UPDATE pairing_sessions SET used_at=?
                WHERE pairing_id=? AND used_at IS NULL AND expires_at>?""",
                (now, pairing_id, now),
            )
            if claimed.rowcount != 1:
                raise PairingError("配对信息已被使用")
            con.execute(
                """INSERT INTO devices
                (device_id, display_name, token_hash, state, client_version,
                 protocol_version, capability_revision, workspace_revision,
                 config_revision, capabilities, paired_at, last_seen_at)
                VALUES (?, ?, ?, 'online', ?, 1, ?, ?, ?, ?, ?, ?)""",
                (
                    device_id,
                    safe_name,
                    _hash_secret(token),
                    client_version[:100],
                    int(capability_revision),
                    int(workspace_revision),
                    int(config_revision),
                    _json(normalized),
                    now,
                    now,
                ),
            )
            con.commit()
        return {
            "device_id": device_id,
            "device_token": token,
            "display_name": safe_name,
            "paired_at": now,
        }

    def authenticate(self, token: str) -> dict:
        if not token:
            raise DeviceAuthenticationError("缺少设备凭据")
        with self._connect() as con:
            row = con.execute(
                """SELECT * FROM devices
                WHERE token_hash=? AND revoked_at IS NULL""",
                (_hash_secret(token),),
            ).fetchone()
        if row is None:
            raise DeviceAuthenticationError("设备凭据无效或已撤销")
        return self._device_dict(row)

    @staticmethod
    def _device_dict(row: sqlite3.Row, *, now: datetime | None = None) -> dict:
        current = now or _now()
        try:
            last_seen = datetime.fromisoformat(row["last_seen_at"])
        except (TypeError, ValueError):
            last_seen = datetime.min.replace(tzinfo=timezone.utc)
        if row["revoked_at"] is not None:
            connection_state = "revoked"
        elif current - last_seen <= timedelta(seconds=45):
            connection_state = "online"
        else:
            connection_state = "offline"
        capabilities = _decode(row["capabilities"], [])
        return {
            "device_id": row["device_id"],
            "display_name": row["display_name"],
            "state": connection_state,
            "client_version": row["client_version"],
            "protocol_version": row["protocol_version"],
            "capability_revision": row["capability_revision"],
            "workspace_revision": row["workspace_revision"],
            "config_revision": row["config_revision"],
            "capabilities": (
                capabilities if isinstance(capabilities, list) else []
            ),
            "paired_at": row["paired_at"],
            "last_seen_at": row["last_seen_at"],
            "revoked_at": row["revoked_at"],
        }

    def list_devices(self, *, include_revoked: bool = False) -> list[dict]:
        with self._connect() as con:
            query = "SELECT * FROM devices"
            if not include_revoked:
                query += " WHERE revoked_at IS NULL"
            query += " ORDER BY paired_at DESC"
            rows = con.execute(query).fetchall()
        current = _now()
        return [self._device_dict(row, now=current) for row in rows]

    def revoke(self, device_id: str) -> bool:
        if not _DEVICE_ID.fullmatch(device_id):
            raise ValueError("无效的 device_id")
        now = _iso(_now())
        with self._connect() as con:
            cursor = con.execute(
                """UPDATE devices SET state='revoked', revoked_at=?
                WHERE device_id=? AND revoked_at IS NULL""",
                (now, device_id),
            )
            con.execute(
                """UPDATE device_tool_invocations
                SET state='cancelled', error='设备已撤销', completed_at=?
                WHERE device_id=? AND state NOT IN
                ('succeeded','failed','declined','expired','cancelled')""",
                (now, device_id),
            )
            con.commit()
            return cursor.rowcount == 1

    def hello(
        self,
        device_id: str,
        *,
        display_name: str,
        client_version: str,
        capabilities: list[dict],
        capability_revision: int,
        workspace_revision: int,
        config_revision: int,
    ) -> dict:
        normalized = _normalize_capabilities(capabilities)
        now = _iso(_now())
        with self._connect() as con:
            cursor = con.execute(
                """UPDATE devices SET display_name=?, state='online',
                client_version=?, protocol_version=1,
                capability_revision=?, workspace_revision=?,
                config_revision=?, capabilities=?, last_seen_at=?
                WHERE device_id=? AND revoked_at IS NULL""",
                (
                    display_name.strip()[:100] or "Android Device",
                    client_version[:100],
                    int(capability_revision),
                    int(workspace_revision),
                    int(config_revision),
                    _json(normalized),
                    now,
                    device_id,
                ),
            )
            con.commit()
        if cursor.rowcount != 1:
            raise DeviceAuthenticationError("设备不存在或已撤销")
        return self.get_device(device_id)

    def heartbeat(
        self,
        device_id: str,
        *,
        workspace_revision: int,
        config_revision: int,
        observations: list[dict] | None = None,
    ) -> dict:
        now = _iso(_now())
        normalized_observations = _normalize_observations(
            observations or []
        )
        with self._connect() as con:
            cursor = con.execute(
                """UPDATE devices SET state='online', workspace_revision=?,
                config_revision=?, last_seen_at=?
                WHERE device_id=? AND revoked_at IS NULL""",
                (
                    int(workspace_revision),
                    int(config_revision),
                    now,
                    device_id,
                ),
            )
            for observation in normalized_observations:
                con.execute(
                    """INSERT OR IGNORE INTO device_observations
                    (observation_id, device_id, event_type, revision,
                     payload, created_at, received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        observation["observation_id"],
                        device_id,
                        observation["event_type"],
                        observation["revision"],
                        _json(observation["payload"]),
                        observation["created_at"] or now,
                        now,
                    ),
                )
            con.execute(
                """DELETE FROM device_observations
                WHERE device_id=? AND observation_id NOT IN (
                    SELECT observation_id FROM device_observations
                    WHERE device_id=? ORDER BY received_at DESC LIMIT 500
                )""",
                (device_id, device_id),
            )
            con.commit()
        if cursor.rowcount != 1:
            raise DeviceAuthenticationError("设备不存在或已撤销")
        return {
            "device_id": device_id,
            "state": "online",
            "last_seen_at": now,
            "accepted_observation_ids": [
                item["observation_id"]
                for item in normalized_observations
            ],
        }

    def recent_observations(
        self,
        *,
        device_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 500)
        with self._connect() as con:
            if device_id is None:
                rows = con.execute(
                    """SELECT * FROM device_observations
                    ORDER BY received_at DESC LIMIT ?""",
                    (safe_limit,),
                ).fetchall()
            else:
                rows = con.execute(
                    """SELECT * FROM device_observations
                    WHERE device_id=? ORDER BY received_at DESC LIMIT ?""",
                    (device_id, safe_limit),
                ).fetchall()
        return [
            {
                "observation_id": row["observation_id"],
                "device_id": row["device_id"],
                "event_type": row["event_type"],
                "revision": row["revision"],
                "payload": _decode(row["payload"], {}),
                "created_at": row["created_at"],
                "received_at": row["received_at"],
            }
            for row in rows
        ]

    def get_device(self, device_id: str) -> dict:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM devices WHERE device_id=?",
                (device_id,),
            ).fetchone()
        if row is None:
            raise DeviceAuthenticationError("设备不存在")
        return self._device_dict(row)

    @staticmethod
    def _supports(device: dict, tool_name: str) -> bool:
        return any(
            capability.get("name") == tool_name
            and capability.get("available", True)
            for capability in device.get("capabilities", [])
            if isinstance(capability, dict)
        )

    def available_tool_names(self) -> set[str]:
        names = set()
        for device in self.list_devices():
            if device["state"] != "online":
                continue
            for capability in device["capabilities"]:
                if capability.get("available", True):
                    names.add(str(capability.get("name", "")))
        return names

    def select_device(
        self,
        tool_name: str,
        device_id: str | None = None,
    ) -> dict:
        if device_id:
            device = self.get_device(device_id)
            if device["state"] != "online" or not self._supports(
                device,
                tool_name,
            ):
                raise DeviceInvocationError("指定设备离线或不提供该能力")
            return device
        candidates = [
            device
            for device in self.list_devices()
            if device["state"] == "online"
            and self._supports(device, tool_name)
        ]
        if not candidates:
            raise DeviceInvocationError("没有在线设备提供该能力")
        return candidates[0]

    def create_invocation(
        self,
        *,
        conversation_id: str,
        session_id: str,
        tool_name: str,
        arguments: dict,
        device_id: str | None = None,
        expected_workspace_revision: int | None = None,
        ttl_seconds: int = 120,
    ) -> dict:
        device = self.select_device(tool_name, device_id)
        if (
            expected_workspace_revision is None
            and tool_name.startswith("device.workspace.")
        ):
            expected_workspace_revision = int(device["workspace_revision"])
        created_at = _now()
        expires_at = created_at + timedelta(
            seconds=min(max(int(ttl_seconds), 10), 600)
        )
        tool_call_id = f"dtc_{uuid.uuid4().hex}"
        with self._connect() as con:
            con.execute(
                """INSERT INTO device_tool_invocations
                (tool_call_id, device_id, conversation_id, session_id,
                 tool_name, arguments, expected_workspace_revision, state,
                 expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)""",
                (
                    tool_call_id,
                    device["device_id"],
                    conversation_id,
                    session_id,
                    tool_name,
                    _json(arguments),
                    expected_workspace_revision,
                    _iso(expires_at),
                    _iso(created_at),
                ),
            )
            con.commit()
        record = self.get_invocation(tool_call_id)
        self._record_invocation_event(record)
        return record

    @staticmethod
    def _record_invocation_event(record: dict) -> None:
        """Best-effort durable Session event for UI and reconnect replay."""

        try:
            from cloudra import session_store
            from cloudra.database import ConversationDB

            db = ConversationDB(record["conversation_id"])
            if not Path(db.path).is_file():
                return
            session_store.insert_session_event(
                db,
                record["session_id"],
                "device_tool_state",
                {
                    "tool_call_id": record["tool_call_id"],
                    "device_id": record["device_id"],
                    "tool": record["tool"],
                    "state": record["state"],
                    "error": record.get("error") or "",
                },
            )
        except (OSError, ValueError, sqlite3.Error):
            pass

    def _expire_and_requeue(self, con: sqlite3.Connection) -> None:
        now = _iso(_now())
        con.execute(
            """UPDATE device_tool_invocations
            SET state='expired', error='设备调用已过期', completed_at=?
            WHERE expires_at<=? AND state NOT IN
            ('succeeded','failed','declined','expired','cancelled')""",
            (now, now),
        )
        con.execute(
            """UPDATE device_tool_invocations
            SET state='queued', lease_id=NULL, lease_expires_at=NULL
            WHERE lease_expires_at IS NOT NULL AND lease_expires_at<=?
            AND expires_at>? AND state IN
            ('leased','acknowledged','waiting_for_local_approval','running')""",
            (now, now),
        )

    def lease(
        self,
        device_id: str,
        *,
        max_count: int = 4,
        lease_seconds: int = 30,
    ) -> list[dict]:
        max_count = min(max(int(max_count), 1), 16)
        lease_seconds = min(max(int(lease_seconds), 10), 60)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._expire_and_requeue(con)
            rows = con.execute(
                """SELECT tool_call_id FROM device_tool_invocations
                WHERE device_id=? AND state='queued'
                ORDER BY created_at LIMIT ?""",
                (device_id, max_count),
            ).fetchall()
            leased = []
            for row in rows:
                lease_id = f"lease_{uuid.uuid4().hex}"
                lease_expires_at = _iso(
                    _now() + timedelta(seconds=lease_seconds)
                )
                cursor = con.execute(
                    """UPDATE device_tool_invocations
                    SET state='leased', lease_id=?, lease_expires_at=?
                    WHERE tool_call_id=? AND state='queued'""",
                    (lease_id, lease_expires_at, row["tool_call_id"]),
                )
                if cursor.rowcount == 1:
                    leased.append((row["tool_call_id"], lease_id))
            con.commit()
        results = []
        for tool_call_id, lease_id in leased:
            record = self.get_invocation(tool_call_id)
            record["lease_id"] = lease_id
            results.append(record)
        return results

    def acknowledge(
        self,
        device_id: str,
        tool_call_id: str,
        lease_id: str,
    ) -> dict:
        with self._connect() as con:
            self._expire_and_requeue(con)
            cursor = con.execute(
                """UPDATE device_tool_invocations
                SET state='acknowledged', acknowledged_at=?
                WHERE tool_call_id=? AND device_id=? AND lease_id=?
                AND state='leased'""",
                (_iso(_now()), tool_call_id, device_id, lease_id),
            )
            con.commit()
        if cursor.rowcount != 1:
            record = self.get_invocation(tool_call_id)
            if record["state"] in {
                "acknowledged",
                "running",
                *_FINAL_INVOCATION_STATES,
            }:
                return record
            raise DeviceInvocationConflict("设备调用租约无效或已过期")
        record = self.get_invocation(tool_call_id)
        self._record_invocation_event(record)
        return record

    def mark_waiting_for_local_approval(
        self,
        device_id: str,
        tool_call_id: str,
        lease_id: str,
    ) -> dict:
        with self._connect() as con:
            self._expire_and_requeue(con)
            cursor = con.execute(
                """UPDATE device_tool_invocations
                SET state='waiting_for_local_approval',
                lease_expires_at=expires_at
                WHERE tool_call_id=? AND device_id=? AND lease_id=?
                AND state='acknowledged'""",
                (tool_call_id, device_id, lease_id),
            )
            con.commit()
        if cursor.rowcount != 1:
            record = self.get_invocation(tool_call_id)
            if record["state"] in {
                "waiting_for_local_approval",
                "running",
                *_FINAL_INVOCATION_STATES,
            }:
                return record
            raise DeviceInvocationConflict(
                "设备调用尚未确认或本地审批状态无效"
            )
        record = self.get_invocation(tool_call_id)
        self._record_invocation_event(record)
        return record

    def mark_running(
        self,
        device_id: str,
        tool_call_id: str,
        lease_id: str,
    ) -> dict:
        with self._connect() as con:
            self._expire_and_requeue(con)
            cursor = con.execute(
                """UPDATE device_tool_invocations
                SET state='running', started_at=?
                WHERE tool_call_id=? AND device_id=? AND lease_id=?
                AND state IN
                ('acknowledged','waiting_for_local_approval')""",
                (_iso(_now()), tool_call_id, device_id, lease_id),
            )
            con.commit()
        if cursor.rowcount != 1:
            record = self.get_invocation(tool_call_id)
            if record["state"] in {"running", *_FINAL_INVOCATION_STATES}:
                return record
            raise DeviceInvocationConflict("设备调用尚未确认或租约已过期")
        record = self.get_invocation(tool_call_id)
        self._record_invocation_event(record)
        return record

    def finish(
        self,
        device_id: str,
        tool_call_id: str,
        *,
        status: str,
        result: dict | None = None,
        error: str = "",
    ) -> dict:
        if status not in {"succeeded", "failed", "declined", "cancelled"}:
            raise DeviceInvocationError("无效的设备调用结果状态")
        result = result or {}
        encoded_result = _json(result)
        if len(encoded_result.encode("utf-8")) > 2_500_000:
            raise DeviceInvocationError("设备调用结果超过 2.5 MB 上限")
        replay = False
        with self._connect() as con:
            self._expire_and_requeue(con)
            existing = con.execute(
                """SELECT state, result, error FROM device_tool_invocations
                WHERE tool_call_id=? AND device_id=?""",
                (tool_call_id, device_id),
            ).fetchone()
            if existing is None:
                raise DeviceInvocationError("设备调用不存在")
            if existing["state"] in _FINAL_INVOCATION_STATES:
                authoritative_terminal = existing["state"] in {
                    "cancelled",
                    "expired",
                }
                same = (
                    existing["state"] == status
                    and (existing["result"] or "{}") == encoded_result
                    and (existing["error"] or "") == error
                )
                if not same and not authoritative_terminal:
                    raise DeviceInvocationConflict(
                        "设备调用已有不同的终态结果"
                    )
                replay = True
                cursor = None
            else:
                cursor = con.execute(
                    """UPDATE device_tool_invocations
                    SET state=?, result=?, error=?, completed_at=?,
                    lease_id=NULL, lease_expires_at=NULL
                    WHERE tool_call_id=? AND device_id=? AND state NOT IN
                    ('succeeded','failed','declined','expired','cancelled')""",
                    (
                        status,
                        encoded_result,
                        error[:2_000],
                        _iso(_now()),
                        tool_call_id,
                        device_id,
                    ),
                )
            con.commit()
        if not replay and (cursor is None or cursor.rowcount != 1):
            raise DeviceInvocationConflict("设备调用结果未能生效")
        record = self.get_invocation(tool_call_id)
        if not replay:
            self._record_invocation_event(record)
        return record

    def get_invocation(self, tool_call_id: str) -> dict:
        if not _TOOL_CALL_ID.fullmatch(tool_call_id):
            raise DeviceInvocationError("无效的 tool_call_id")
        with self._connect() as con:
            self._expire_and_requeue(con)
            row = con.execute(
                """SELECT * FROM device_tool_invocations
                WHERE tool_call_id=?""",
                (tool_call_id,),
            ).fetchone()
            con.commit()
        if row is None:
            raise DeviceInvocationError("设备调用不存在")
        return {
            "tool_call_id": row["tool_call_id"],
            "device_id": row["device_id"],
            "conversation_id": row["conversation_id"],
            "session_id": row["session_id"],
            "tool": row["tool_name"],
            "arguments": _decode(row["arguments"], {}),
            "expected_workspace_revision": row[
                "expected_workspace_revision"
            ],
            "state": row["state"],
            "lease_id": row["lease_id"],
            "lease_expires_at": row["lease_expires_at"],
            "expires_at": row["expires_at"],
            "result": _decode(row["result"], None),
            "error": row["error"],
            "created_at": row["created_at"],
            "acknowledged_at": row["acknowledged_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }


# 进程级缓存：每个数据目录（即每个 device-broker.db 文件）一个实例。
# DeviceBroker.__init__ 每次都会 mkdir + 切 WAL + 全量 DDL 写事务；推理热路径
# （get_available_tools）每轮多次构造会让并发 Agent 在同一数据库文件上互等
# 写锁。DDL 全部是 CREATE TABLE/INDEX IF NOT EXISTS（幂等），每个库文件初始化
# 一次即可，后续调用复用同一实例，查询语义（实时 list_devices）不变。
_BROKER_CACHE: dict[str, DeviceBroker] = {}
_BROKER_CACHE_LOCK = threading.Lock()


def get_device_broker(data_dir: Path | None = None) -> DeviceBroker:
    """返回按数据目录缓存的 DeviceBroker 实例（线程安全，一次性初始化）。"""
    configured = data_dir or Path(get_config().data_dir)
    key = str(Path(configured).expanduser().resolve())
    broker = _BROKER_CACHE.get(key)
    if broker is None:
        with _BROKER_CACHE_LOCK:
            # 双重检查：构造（含 _init DDL）只发生一次，即使在多线程下
            broker = _BROKER_CACHE.get(key)
            if broker is None:
                broker = DeviceBroker(Path(key))
                _BROKER_CACHE[key] = broker
    return broker
