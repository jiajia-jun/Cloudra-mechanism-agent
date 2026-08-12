"""AgentHub directory / call helpers. No `query` on the tool wire."""

from __future__ import annotations

from cloudra.persistence.database import ConversationDB, aretry_on_locked
from cloudra.subagents.registry import SUBAGENT_REGISTRY
from cloudra.tools.Managetool._subagent_dispatch import (
    _subagent_orchestration_mode,
    dispatch_subagent,
)

INCOMING_CALL_TEMPLATE = (
    "【来电】{caller_agent_id} 打给你（session={caller_session_id}）。"
    "请第一时间回应这通来电（正文或 agent_hub call/post），"
    "不要先查计算、改提醒或 stop。\n\n"
)


def format_incoming_call(
    *,
    caller_agent_id: str,
    caller_session_id: str,
    message: str,
    post_line: str | None = None,
) -> str:
    # Spoken message is concatenated, not passed through str.format — braces
    # in user speech (e.g. {"freq": -1} or a lone "{") must stay literal.
    text = INCOMING_CALL_TEMPLATE.format(
        caller_agent_id=caller_agent_id,
        caller_session_id=caller_session_id or "unknown",
    ) + message.strip()
    if post_line:
        text = f"{text}\n{post_line}"
    return text


def resolve_agent_id(target: str) -> str | None:
    t = target.strip()
    if not t:
        return None
    if t.lower() in ("coordinator", "a-0"):
        return "a-0"
    if t.startswith("a-") and t[2:].isdigit():
        return t
    for reg in SUBAGENT_REGISTRY:
        if reg.class_name == t:
            return reg.agent_id
    return None


def resolve_call_target(to: str, *, db: ConversationDB) -> tuple[str, dict]:
    raw = (to or "").strip()
    if not raw:
        return "error", {"message": "call 需要非空的 to。"}
    lowered = raw.lower()
    if lowered in ("coordinator", "a-0"):
        row = _latest_coordinator(db)
        if row is None:
            return "error", {"message": "本对话没有 Coordinator session。"}
        return "visit", {"session_id": row[0], "agent_id": "a-0"}
    agent_id = resolve_agent_id(raw)
    if agent_id is not None and agent_id != "a-0":
        return "spawn", {"agent_id": agent_id}
    session_row = _session_row(db, raw)
    if session_row is not None:
        return "visit", {"session_id": session_row[0], "agent_id": session_row[1] or ""}
    return "error", {"message": f"未知的 to: {raw}"}


def _session_row(db: ConversationDB, session_id: str):
    with db.connect() as con:
        return con.execute(
            "SELECT session_id, agent_id, agent_type, state, query FROM session WHERE session_id=?",
            (session_id,),
        ).fetchone()


def _latest_coordinator(db: ConversationDB):
    with db.connect() as con:
        return con.execute(
            "SELECT session_id, agent_id FROM session WHERE agent_id='a-0' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()


async def list_directory(db: ConversationDB) -> list[dict]:
    async def query():
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT session_id, agent_id, agent_type, state, query FROM session "
                "ORDER BY created_at DESC"
            )
            return await cur.fetchall()

    rows = await aretry_on_locked(query)
    return [
        {
            "session_id": r[0],
            "agent_id": r[1],
            "agent_type": r[2],
            "state": r[3],
            "task": r[4] or "",
        }
        for r in rows
    ]


async def lookup_post(db: ConversationDB, post_id: int) -> dict | None:
    async def query():
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT id, topic, kind, author_agent, author_session, to_agent, "
                "parent_id, content, created_at FROM hub_posts WHERE id = ?",
                (post_id,),
            )
            return await cur.fetchone()

    row = await aretry_on_locked(query)
    if row is None:
        return None
    return {
        "id": row[0],
        "topic": row[1],
        "kind": row[2],
        "author_agent": row[3],
        "author_session": row[4],
        "to_agent": row[5],
        "parent_id": row[6],
        "content": row[7],
        "created_at": row[8],
    }


async def spawn_from_call(
    *,
    agent_id: str,
    message: str,
    incoming_text: str,
    conversation_id: str,
    working_directory,
    parent_session_id,
    parent_orchestration_mode,
    caller_agent_id: str,
    caller_session_id: str,
) -> str:
    from cloudra.subagents import Subagent_hash

    agent_cls = Subagent_hash().get(agent_id)
    if agent_cls is None:
        raise ValueError(f"未知 agent_id: {agent_id}")
    result = await dispatch_subagent(
        agent_cls,
        agent_id=agent_id,
        query=message,
        context=[{"role": "user", "content": incoming_text}],
        is_wait=False,
        conversation_id=conversation_id,
        working_directory=working_directory,
        parent_session_id=parent_session_id,
        parent_orchestration_mode=parent_orchestration_mode,
        extra_payload={
            "origin": "hub_call",
            "caller_agent_id": caller_agent_id,
            "caller_session_id": caller_session_id,
        },
    )
    return result.session_id


async def deliver_incoming_call(
    *,
    conversation_id: str,
    callee_agent_id: str,
    callee_session_id: str,
    text: str,
    db_path: str,
) -> None:
    from cloudra.persistence.context_manager import ContextManager

    context_session_id = None if callee_agent_id == "a-0" else callee_session_id
    cm = ContextManager(
        agent_id=callee_agent_id,
        conversation_id=conversation_id,
        prompt=None,
        query="",
        session_id=context_session_id,
        db_path=db_path,
    )
    await cm.append({"role": "user", "content": text})
    await ContextManager.inject_event(
        conversation_id=conversation_id,
        agent_id=callee_agent_id,
        event_type="user_message",
        content=text,
        db_path=db_path,
        session_id=callee_session_id,
    )


async def _session_resume_fields(
    db: ConversationDB, session_id: str
) -> tuple[str | None, str | None]:
    """Target session working_directory / orchestration_mode, if those columns exist."""

    async def query():
        async with db.aconnect() as con:
            cur = await con.execute("PRAGMA table_info(session)")
            cols = {row[1] for row in await cur.fetchall()}
            fields: list[str] = []
            if "working_directory" in cols:
                fields.append("working_directory")
            if "orchestration_mode" in cols:
                fields.append("orchestration_mode")
            if not fields:
                return None
            cur = await con.execute(
                f"SELECT {', '.join(fields)} FROM session WHERE session_id=?",
                (session_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            data = dict(zip(fields, row))
            return data.get("working_directory"), data.get("orchestration_mode")

    try:
        result = await aretry_on_locked(query)
    except Exception:
        return None, None
    if result is None:
        return None, None
    return result


async def resume_follower_if_idle(
    *,
    db: ConversationDB,
    conversation_id: str,
    session_id: str,
    agent_id: str,
    working_directory,
    orchestration_mode,
    parent_session_id,
    caller_agent_id: str = "a-0",
    caller_session_id: str = "",
) -> None:
    """Visit an idle follower by reusing session_id. a-0 is inject-only."""
    if agent_id in ("a-0", "coordinator") or not session_id:
        return

    async def count_live():
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT COUNT(*) FROM subagent_requests "
                "WHERE session_id=? AND state IN ('ready', 'running')",
                (session_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    if await aretry_on_locked(count_live) > 0:
        return

    from cloudra.infra.runtime_profile import subagent_execution_mode
    from cloudra.infra.yolo_guard import is_yolo_enabled
    from cloudra.services import session_store
    from cloudra.tools.Managetool._subagent_dispatch import run_subagent_in_process

    stored_wd, stored_mode = await _session_resume_fields(db, session_id)
    wd = stored_wd if stored_wd else working_directory
    parent_mode = stored_mode if stored_mode else orchestration_mode
    orch = _subagent_orchestration_mode(parent_mode).value
    payload = {
        "agent_id": agent_id,
        "query": "",
        "context": [],
        "conversation_id": conversation_id,
        "parent_session_id": parent_session_id,
        "working_directory": wd,
        "orchestration_mode": orch,
        "yolo": is_yolo_enabled(),
        "origin": "hub_call",
        "caller_agent_id": caller_agent_id,
        "caller_session_id": caller_session_id,
    }
    in_process = subagent_execution_mode() == "inprocess"
    request_state = "running" if in_process else "ready"
    task_id, _, _ = await session_store.acreate_subagent_request(
        db,
        state=request_state,
        payload=payload,
        conversation_id=conversation_id,
        parent_session_id=parent_session_id,
        session_id_fn=lambda _tid: session_id,
    )
    if in_process:
        from cloudra.runtime.mobile_tasks import create_mobile_task

        create_mobile_task(run_subagent_in_process(task_id, db.path, session_id))
    else:
        from cloudra.infra import events

        await events.aemit(
            conversation_id,
            "subagent_request_ready",
            task_id=task_id,
            session_id=session_id,
            agent_id=agent_id,
        )
