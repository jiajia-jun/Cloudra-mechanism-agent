"""Session-scoped durable waiting for non-approval user interaction."""

from __future__ import annotations

import asyncio
import os
import time

from cloudra.infra import events
from cloudra.persistence.database import ConversationDB, aretry_on_locked
from cloudra.services import control_store, session_store


async def _asession_state(db: ConversationDB, session_id: str) -> str | None:
    async with db.aconnect() as con:
        cursor = await con.execute(
            "SELECT state FROM session WHERE session_id=?",
            (session_id,),
        )
        row = await cursor.fetchone()
    return row[0] if row else None


async def _aset_session_state(
    db: ConversationDB,
    session_id: str,
    state: str,
    *,
    event_data: dict | None = None,
) -> None:
    # 等价于 update_session_fields({"state": state}) + insert_session_event；
    # async 上下文禁止同步写库，这里走 aconnect 不阻塞事件循环。
    async def write() -> None:
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE session SET state = ? WHERE session_id = ?",
                (state, session_id),
            )
            await con.commit()

    await aretry_on_locked(write)
    await session_store._aemit_session_state(db, session_id, state)
    await session_store.ainsert_session_event(
        db,
        session_id,
        state,
        event_data or {},
    )


async def wait_for_user_response(
    *,
    conversation_id: str,
    session_id: str,
    agent_id: str,
    prompt: str,
    db_path: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Persist a question and wait until one response is durably applied."""

    db = (
        ConversationDB.from_path(db_path)
        if db_path is not None
        else ConversationDB(conversation_id)
    )
    queue = await events.subscribe_async(conversation_id, "interaction_answered")
    interaction = await control_store.acreate_interaction(
        db,
        session_id=session_id,
        agent_id=agent_id,
        prompt=prompt,
    )
    await _aset_session_state(
        db,
        session_id,
        "waiting_for_user",
        event_data={"interaction_id": interaction.interaction_id},
    )
    # 与审批同款的双通道：实时事件走 kind="interaction_requested"（TUI 弹窗
    # 订阅的是这个 kind），历史回放靠下面的 session_event。只发 session_event
    # 时订阅 kind 的前端（Textual TUI）永远收不到，弹窗不会打开。
    try:
        events.emit(
            conversation_id,
            "interaction_requested",
            **interaction.to_dict(),
        )
    except Exception:
        pass
    await session_store.ainsert_session_event(
        db,
        session_id,
        "interaction_requested",
        interaction.to_dict(),
    )

    if timeout_seconds is None:
        try:
            timeout_seconds = float(
                os.getenv("CLOUDRA_INTERACTION_TIMEOUT_SECONDS", "86400")
            )
        except ValueError:
            timeout_seconds = 86400.0
    deadline = time.monotonic() + max(0.01, timeout_seconds)

    try:
        while True:
            current = await control_store.aget_interaction(
                db,
                interaction.interaction_id,
            )
            if current is not None and current.state == "answered":
                if await _asession_state(db, session_id) == "waiting_for_user":
                    await _aset_session_state(db, session_id, "running")
                return current.response or ""

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await control_store.aexpire_interaction(
                    db,
                    interaction.interaction_id,
                )
                await session_store.ainsert_session_event(
                    db,
                    session_id,
                    "interaction_expired",
                    {"interaction_id": interaction.interaction_id},
                )
                if await _asession_state(db, session_id) == "waiting_for_user":
                    await _aset_session_state(db, session_id, "running")
                raise TimeoutError("等待用户回答超时")

            try:
                message = await asyncio.wait_for(
                    queue.get(),
                    timeout=min(30.0, remaining),
                )
            except asyncio.TimeoutError:
                continue
            if message.get("interaction_id") != interaction.interaction_id:
                continue
    except asyncio.CancelledError:
        await control_store.aexpire_interaction(db, interaction.interaction_id)
        await session_store.ainsert_session_event(
            db,
            session_id,
            "interaction_cancelled",
            {"interaction_id": interaction.interaction_id},
        )
        raise
