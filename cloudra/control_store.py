"""Durable, idempotent remote-control commands and user interactions."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from cloudra.database import ConversationDB, retry_on_locked

_COMMAND_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,160}$")
_INTERACTION_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,160}$")
_FINAL_COMMAND_STATES = frozenset({"applied", "failed"})


class CommandConflict(ValueError):
    """An idempotency key was reused for different command content."""


class InteractionConflict(ValueError):
    """An interaction was already answered or is no longer pending."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: dict | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: str | None) -> dict | None:
    if value is None:
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {"value": value}
    return decoded if isinstance(decoded, dict) else {"value": decoded}


@dataclass(frozen=True)
class ClientCommand:
    command_id: str
    conversation_id: str
    session_id: str | None
    command_type: str
    payload: dict
    state: str
    result: dict | None
    error: str | None
    created_at: str
    applied_at: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Interaction:
    interaction_id: str
    session_id: str
    agent_id: str
    prompt: str
    state: str
    response: str | None
    created_at: str
    responded_at: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def validate_command_id(command_id: str) -> str:
    if not _COMMAND_ID.fullmatch(command_id):
        raise ValueError("Idempotency-Key 只能包含字母、数字、点、冒号、下划线和连字符")
    return command_id


def new_command_id() -> str:
    return f"cmd_{uuid.uuid4().hex}"


def _command_from_row(row) -> ClientCommand:
    return ClientCommand(
        command_id=row[0],
        conversation_id=row[1],
        session_id=row[2],
        command_type=row[3],
        payload=_decode(row[4]) or {},
        state=row[5],
        result=_decode(row[6]),
        error=row[7],
        created_at=row[8],
        applied_at=row[9],
    )


def get_command(db: ConversationDB, command_id: str) -> ClientCommand | None:
    validate_command_id(command_id)

    def read():
        with db.connect() as con:
            return con.execute(
                """SELECT command_id, conversation_id, session_id, command_type,
                payload, state, result, error, created_at, applied_at
                FROM client_commands WHERE command_id=?""",
                (command_id,),
            ).fetchone()

    row = retry_on_locked(read)
    return _command_from_row(row) if row else None


def receive_command(
    db: ConversationDB,
    *,
    command_id: str,
    conversation_id: str,
    session_id: str | None,
    command_type: str,
    payload: dict,
) -> tuple[ClientCommand, bool]:
    """Persist receipt and return ``(record, newly_created)``.

    Reusing an idempotency key with different semantics is rejected instead of
    silently returning an unrelated previous result.
    """

    validate_command_id(command_id)
    canonical_payload = _json(payload)

    def write() -> tuple[object, bool]:
        with db.connect() as con:
            cursor = con.execute(
                """INSERT OR IGNORE INTO client_commands
                (command_id, conversation_id, session_id, command_type, payload,
                 state, created_at)
                VALUES (?, ?, ?, ?, ?, 'received', ?)""",
                (
                    command_id,
                    conversation_id,
                    session_id,
                    command_type,
                    canonical_payload,
                    _utc_now(),
                ),
            )
            row = con.execute(
                """SELECT command_id, conversation_id, session_id, command_type,
                payload, state, result, error, created_at, applied_at
                FROM client_commands WHERE command_id=?""",
                (command_id,),
            ).fetchone()
            con.commit()
            return row, cursor.rowcount == 1

    row, created = retry_on_locked(write)
    record = _command_from_row(row)
    if (
        record.conversation_id != conversation_id
        or record.session_id != session_id
        or record.command_type != command_type
        or _json(record.payload) != canonical_payload
    ):
        raise CommandConflict("Idempotency-Key 已用于另一条控制命令")
    return record, created


def claim_command(db: ConversationDB, command_id: str) -> bool:
    """Atomically move a newly received command into the applying state."""

    def write() -> bool:
        with db.connect() as con:
            cursor = con.execute(
                """UPDATE client_commands SET state='applying'
                WHERE command_id=? AND state='received'""",
                (command_id,),
            )
            con.commit()
            return cursor.rowcount == 1

    return retry_on_locked(write)


def finish_command(
    db: ConversationDB,
    command_id: str,
    *,
    result: dict | None = None,
    error: str | None = None,
) -> ClientCommand:
    state = "failed" if error is not None else "applied"

    def write() -> None:
        with db.connect() as con:
            con.execute(
                """UPDATE client_commands
                SET state=?, result=?, error=?, applied_at=?
                WHERE command_id=? AND state NOT IN ('applied', 'failed')""",
                (state, _json(result) if result is not None else None, error, _utc_now(), command_id),
            )
            con.commit()

    retry_on_locked(write)
    record = get_command(db, command_id)
    if record is None:  # pragma: no cover - defensive invariant
        raise RuntimeError("控制命令记录意外丢失")
    return record


def create_interaction(
    db: ConversationDB,
    *,
    session_id: str,
    agent_id: str,
    prompt: str,
    interaction_id: str | None = None,
) -> Interaction:
    interaction_id = interaction_id or f"int_{uuid.uuid4().hex}"

    def write() -> None:
        with db.connect() as con:
            con.execute(
                """INSERT INTO interactions
                (interaction_id, session_id, agent_id, prompt, state, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)""",
                (interaction_id, session_id, agent_id, prompt, _utc_now()),
            )
            con.commit()

    retry_on_locked(write)
    record = get_interaction(db, interaction_id)
    if record is None:  # pragma: no cover - defensive invariant
        raise RuntimeError("交互记录意外丢失")
    return record


def _interaction_from_row(row) -> Interaction:
    return Interaction(
        interaction_id=row[0],
        session_id=row[1],
        agent_id=row[2],
        prompt=row[3],
        state=row[4],
        response=row[5],
        created_at=row[6],
        responded_at=row[7],
    )


def get_interaction(db: ConversationDB, interaction_id: str) -> Interaction | None:
    if not _INTERACTION_ID.fullmatch(interaction_id):
        raise ValueError("无效的 interaction_id")

    def read():
        with db.connect() as con:
            return con.execute(
                """SELECT interaction_id, session_id, agent_id, prompt, state,
                response, created_at, responded_at
                FROM interactions WHERE interaction_id=?""",
                (interaction_id,),
            ).fetchone()

    row = retry_on_locked(read)
    return _interaction_from_row(row) if row else None


def list_pending_interactions(
    db: ConversationDB,
    *,
    session_id: str | None = None,
) -> list[Interaction]:
    def read():
        with db.connect() as con:
            if session_id is None:
                return con.execute(
                    """SELECT interaction_id, session_id, agent_id, prompt, state,
                    response, created_at, responded_at FROM interactions
                    WHERE state='pending' ORDER BY created_at"""
                ).fetchall()
            return con.execute(
                """SELECT interaction_id, session_id, agent_id, prompt, state,
                response, created_at, responded_at FROM interactions
                WHERE state='pending' AND session_id=? ORDER BY created_at""",
                (session_id,),
            ).fetchall()

    return [_interaction_from_row(row) for row in retry_on_locked(read)]


def respond_interaction(
    db: ConversationDB,
    interaction_id: str,
    response: str,
) -> tuple[Interaction | None, bool]:
    """Apply a response once; a second decision leaves the original untouched."""

    def write() -> bool:
        with db.connect() as con:
            cursor = con.execute(
                """UPDATE interactions SET state='answered', response=?,
                responded_at=? WHERE interaction_id=? AND state='pending'""",
                (response, _utc_now(), interaction_id),
            )
            con.commit()
            return cursor.rowcount == 1

    changed = retry_on_locked(write)
    return get_interaction(db, interaction_id), changed


def expire_interaction(db: ConversationDB, interaction_id: str) -> bool:
    def write() -> bool:
        with db.connect() as con:
            cursor = con.execute(
                """UPDATE interactions SET state='expired', responded_at=?
                WHERE interaction_id=? AND state='pending'""",
                (_utc_now(), interaction_id),
            )
            con.commit()
            return cursor.rowcount == 1

    return retry_on_locked(write)
