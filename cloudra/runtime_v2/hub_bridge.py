"""v2-native AgentHub: the forum lives in the event log, calls in the Mailbox.

The legacy ``agent_hub`` tool stores posts in the conversation SQLite
(``hub_posts``) and notifies through legacy context injection.  In runtime_v2 neither
exists, so this bridge re-implements the six actions on kernel primitives:

- ``post`` appends a ``hub.posted`` event (project stream); the event log is
  the forum store, so posts survive replay like everything else.
- ``browse`` / ``read`` / ``search`` are pure projections over those events.
- Notifications (to_agent / reply) and ``call`` to a live session go through
  ``MessageDispatcher.commit_and_deliver`` — the runner picks the message up
  at the next turn boundary, which is the v2 equivalent of legacy inject_event.
  A sleeping/idle addressee is woken (``WakePolicy``) so the mention or call
  takes effect immediately instead of sitting in the inbox; a failed/cancelled
  addressee is never auto-revived — the message is parked in its mailbox.
- ``call`` to an absent role creates an independent project peer through
  CommandBus. It does not inherit the caller's settings or lifecycle.

The tool module supplies its wire schema and shared fuzzy-scoring helpers;
runtime_v2 handles persistence and dispatch here.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from pydantic import ValidationError

from cloudra.infra.tool_errors import validation_feedback
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.dispatcher import WakePolicy, should_wake
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentSession, AgentState, Command, CommandRejected, EventEnvelope
from cloudra.tools.Managetool._hub_call import format_incoming_call
from cloudra.tools.Managetool.agent_hub import (
    _FUZZY_FLOOR,
    _SEARCH_SCAN_LIMIT,
    AgentHub_input_schema,
    AgentHub_output_schema,
    _fuzzy_score,
)

_POST_KINDS = ("finding", "question", "answer", "broadcast", "message")


def _posts(core, project_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    envelopes = core.event_log.query_project(project_id, types={"hub.posted"}, limit=limit)
    return [
        {
            "id": env.event_id,
            "seq": env.seq,
            "created_at": env.created_at.isoformat(),
            **env.data,
        }
        for env in envelopes
    ]


def _live_sessions(core, project_id: str) -> list[AgentSession]:
    return [a for a in core.agents.values() if a.project_id == project_id]


def _resolve_live_target(
    core, project_id: str, target: str, *, wakeable_role_only: bool = False, author: AgentSession | None = None
) -> AgentSession | None:
    """Resolve ids/roles first, then fall back to a display name."""
    t = target.strip()
    if not t:
        return None
    sessions = _live_sessions(core, project_id)
    clean = t.lstrip("@").lower()
    if author is not None and clean == "parent" and author.parent_session_id:
        parent = core.agents.get(author.parent_session_id)
        if parent is not None and parent.project_id == project_id:
            return parent
    by_id = core.agents.get(t)
    if by_id is not None and by_id.project_id == project_id:
        return by_id
    if author is not None and clean == "coordinator" and author.parent_session_id:
        parent = core.agents.get(author.parent_session_id)
        if parent is not None and parent.project_id == project_id and parent.role_id == "coordinator":
            if not wakeable_role_only or parent.state not in {AgentState.FAILED, AgentState.CANCELLED}:
                return parent
    matches = [a for a in sessions if a.role_id == clean]
    if clean == "supervisor":
        # The role alias belongs to the ongoing research discussion. A final
        # reviewer stays addressable through its explicit session id above.
        matches = [a for a in matches if a.final_review_request_id is None]
    if matches or clean == "supervisor":
        if wakeable_role_only:
            matches = [
                a for a in matches if a.state not in {AgentState.FAILED, AgentState.CANCELLED}
            ]
        return matches[-1] if matches else None
    name_matches = [a for a in sessions if a.display_name.strip().lower() == clean]
    if wakeable_role_only:
        wakeable = [
            a for a in name_matches if a.state not in {AgentState.FAILED, AgentState.CANCELLED}
        ]
        if wakeable:
            return wakeable[-1]
    return name_matches[-1] if name_matches else None


def _repeat_call_without_progress(core, target: AgentSession, *, sender: str, content: str) -> bool:
    """Recognize an already consumed call whose only response was another wait."""
    from cloudra.runtime_v2.agent_host import is_background_parked

    if not is_background_parked(core, target):
        return False
    gate = core.event_log.query_session(target.id, types={"agent.completion_gate"}, limit=1)[0]
    previous = core.event_log.query_session(
        target.id, types={"agent.message_injected"}, before_session_seq=gate.session_seq, limit=1,
    )

    def same_call(event):
        return (
            event.data.get("sender") == sender
            and event.data.get("content") == content
            and event.data.get("post_id") is None
        )

    if not previous or not same_call(previous[0]):
        return False
    events = core.event_log.query_session(
        target.id, run_id=gate.run_id,
        types={"tool.requested", "tool.finished", "program.submitted", "context.appended"}, limit=None,
    )
    # JS programs have their own receipts. Conservatively keep their wake
    # semantics instead of mistaking an outer program for a stop-only turn.
    if any(event.type == "program.submitted" for event in events):
        return False
    requested = [event for event in events if event.type == "tool.requested"]
    finished = [event for event in events if event.type == "tool.finished"]
    if not requested or any(event.data.get("tool_name") != "stop" for event in requested):
        return False
    if ({event.data.get("tool_call_id") for event in requested}
            != {event.data.get("tool_call_id") for event in finished}
            or any(event.data.get("is_success") is not True for event in finished)):
        return False
    consumed = {message.get("message_id") for event in events if event.type == "context.appended"
                for message in event.data.get("messages", []) if message.get("role") == "user"}
    if previous[0].data.get("message_id") not in consumed:
        return False
    for event in core.event_log.iter_project(
        target.project_id, after_seq=gate.seq,
        types={"agent.message_injected", "run.finished", "launch_group.finished", "hub.posted",
               "tool.result_recorded", "tool.finished"},
    ):
        if event.type == "run.finished" and event.session_id == target.id:
            continue
        if event.type in {"tool.result_recorded", "tool.finished"}:
            # Hub content changes already have hub.posted/message events.
            # Its call/read receipts and stop alone are not new work; every
            # other tool result conservatively keeps the normal wake.
            if event.data.get("tool_name") not in {"agent_hub", "stop"}:
                return False
            continue
        if event.type == "agent.message_injected":
            if event.session_id == target.id:
                if not same_call(event):
                    return False
            elif (event.data.get("manifest") or {}).get("kind") in {
                "compute_completion", "child_completion", "peer_completion",
            }:
                return False
        else:
            return False
    return True


async def _notify(
    core,
    project_id: str,
    target: AgentSession,
    *,
    sender: str,
    content: str,
    post_id: str | None = None,
    author: AgentSession | None = None,
) -> dict[str, str]:
    # 统一不复活纪律（park-don't-wake）：failed/cancelled 终态 agent 不被
    # mention/call 自动 reopen——消息驻留 durable 信箱，用户显式复活后首轮
    # 即可读到。其余状态照常唤醒（策略由 dispatcher 唯一解析）。
    wake = WakePolicy.PARK_TERMINAL
    # Only program calls share this identity. Posts have their own durable
    # evidence identity; user messages remain explicit instructions to wake.
    if post_id is None and author is not None and await asyncio.to_thread(
        _repeat_call_without_progress, core, target, sender=sender, content=content,
    ):
        wake = WakePolicy.NEVER
    # This snapshot describes wake intent. Persisting the message may yield,
    # so requested is not evidence that the recipient actually started a run.
    target_state = target.state.value
    wake_allowed = await asyncio.to_thread(should_wake, core, target, wake)
    envelope = await core.dispatcher.commit_and_deliver(
        to_session_id=target.id,
        project_id=project_id,
        content=content,
        sender=sender,
        post_id=post_id,
        manifest=(
            {"kind": "task_assignment", "session_id": target.id, "parent_session_id": author.id}
            if post_id is None and author is not None
            and author.project_id == project_id == target.project_id
            and target.parent_session_id == author.id else None
        ),
        wake=wake,
    )
    return {
        "session_id": target.id,
        "message_event_id": envelope.event_id,
        "delivery": "delivered" if wake_allowed else "parked",
        "wake_status": (
            "parked" if not wake_allowed else
            "already_running" if target_state == AgentState.RUNNING.value else "requested"
        ),
        "wake_policy": wake.value,
        "target_state": target_state,
    }


def post_notification_text(core, post: EventEnvelope, target_id: str) -> str:
    """Render the same frozen post notification for live delivery and restore."""
    data = post.data
    author = str(data.get("author_agent") or "")
    topic = str(data.get("topic") or "")
    content = str(data.get("content") or "")
    parent_id = data.get("parent_id")
    is_reply = target_id == data.get("reply_session_id") and (
        target_id != data.get("addressed_session_id")
    )
    if is_reply:
        parent = core.event_log.get(parent_id) if parent_id else None
        return (
            f"{author} replied to your AgentHub post in topic "
            f"'{parent.data['topic'] if parent else topic}' {parent_id} "
            f"(reply {post.event_id}): {content}"
        )
    return (
        f"{author} {'broadcast' if data.get('kind') == 'broadcast' else 'mentioned you'} "
        f"in AgentHub topic '{topic}' (post {post.event_id}): {content}"
    )


def _err(message: str, **data: Any) -> ToolResult:
    return ToolResult(
        is_success=False,
        summary=message,
        data={"is_success": False, "message": message, **data},
    )


def _ok(summary: str, **data: Any) -> ToolResult:
    return ToolResult(is_success=True, summary=summary, data={"is_success": True, "message": summary, **data})


async def _post(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    topic = str(args.get("topic") or "").strip()
    content = str(args.get("content") or "").strip()
    kind = args["kind"]
    to_agent = str(args.get("to_agent") or "").strip()
    if (
        to_agent and _resolve_live_target(core, author.project_id, to_agent, author=author) is None
        and core.roles.get(to_agent.lstrip("@").lower()) is None
    ):
        return _err(f"Addressee {to_agent!r} is neither a project session, display_name, nor a known role_id.")
    parent_id = args.get("parent_id") or None
    retry_post_id = str(args.get("post_id") or "").strip()
    if retry_post_id:
        envelope = await asyncio.to_thread(core.event_log.get, retry_post_id)
        expected = {
            "topic": topic, "kind": kind, "to_agent": to_agent or None,
            "parent_id": parent_id, "content": content,
        }
        if (
            envelope is None or envelope.type != "hub.posted"
            or envelope.project_id != author.project_id or envelope.session_id != author.id
            or any(envelope.data.get(key) != value for key, value in expected.items())
        ):
            return _err("post_id does not identify your matching post in this project.")
    else:
        # Freeze the recipient set with the post. A retry must only finish its
        # original deliveries; a session created later cannot receive an old
        # broadcast just because one recipient temporarily failed.
        addressee = _resolve_live_target(core, author.project_id, to_agent, author=author) if to_agent else None
        parent = await asyncio.to_thread(core.event_log.get, parent_id) if parent_id else None
        original = (
            core.agents.get(parent.session_id)
            if parent is not None and parent.type == "hub.posted"
            and parent.project_id == author.project_id and parent.session_id != author.id
            else None
        )
        targets = (
            [
                agent for agent in _live_sessions(core, author.project_id)
                if agent.id != author.id
                and agent.state not in {AgentState.FAILED, AgentState.CANCELLED}
            ] + ([original] if original is not None and original.id != author.id else [])
            if kind == "broadcast" else
            [agent for agent in (addressee, original) if agent is not None and agent.id != author.id]
        )
        target_ids = list(dict.fromkeys(agent.id for agent in targets))
        envelope = await core.event_writer.commit(
            EventDraft(
                "hub.posted", stream="project", project_id=author.project_id,
                session_id=author.id,
                data={
                    "topic": topic, "kind": kind, "author_agent": author.role_id,
                    "author_session": author.id, "to_agent": to_agent or None,
                    "parent_id": parent_id, "content": content,
                    "notification_target_ids": target_ids,
                    "addressed_session_id": addressee.id if addressee else None,
                    "reply_session_id": original.id if original else None,
                },
            )
        )

    delivered_ids = (
        {
            event.session_id
            for event in await asyncio.to_thread(
                core.event_log.query_project, author.project_id, after_seq=envelope.seq,
                types={"agent.message_injected"}, limit=None, tail=False,
            )
            if event.data.get("post_id") == envelope.event_id
        }
        if retry_post_id else set()
    )
    notices: list[str] = []
    notifications: list[dict[str, str]] = []
    failed_ids: list[str] = []
    for target_id in envelope.data.get("notification_target_ids", []):
        if target_id in delivered_ids:
            continue
        target = core.agents.get(target_id)
        if target is None or target.project_id != author.project_id:
            failed_ids.append(target_id)
            continue
        is_reply = target_id == envelope.data.get("reply_session_id") and (
            target_id != envelope.data.get("addressed_session_id")
        )
        notification = await asyncio.to_thread(post_notification_text, core, envelope, target_id)
        if is_reply:
            parent = await asyncio.to_thread(core.event_log.get, parent_id)
            receipt = f"Notified original author {parent.data['author_agent'] if parent else target.role_id}."
        else:
            receipt = f"Notified {to_agent or target.role_id}."
        try:
            delivery = await _notify(
                core, author.project_id, target, sender=author.role_id,
                content=notification, post_id=envelope.event_id, author=author,
            )
        except EventPersistenceError:
            failed_ids.append(target_id)
            continue
        delivered_ids.add(target_id)
        notifications.append(delivery)
        if delivery["delivery"] == "parked":
            receipt += " Delivery parked in the mailbox; recipient was not woken."
        if kind != "broadcast":
            notices.append(receipt)
    message = f"Posted to topic '{topic}' (id={envelope.event_id})."
    if kind == "broadcast":
        message += f" Notified {len(delivered_ids)} project sessions."
    elif notices:
        message += " " + " ".join(notices)
    if kind == "broadcast":
        parked_count = sum(item["delivery"] == "parked" for item in notifications)
        if parked_count:
            message += f" {parked_count} delivery/deliveries parked without waking the recipient."
    if failed_ids:
        return _err(
            message + " Some notifications failed; retry post with this post_id and the same fields.",
            post_id=envelope.event_id, notified_count=len(delivered_ids),
            failed_session_ids=failed_ids, notifications=notifications,
        )
    return _ok(message, post_id=envelope.event_id, notified_count=len(delivered_ids), notifications=notifications)


async def post_user_post(
    core,
    project_id: str,
    *,
    topic: str,
    content: str,
    kind: str = "finding",
    to_agent: str = "",
    parent_id: str | None = None,
) -> dict[str, Any]:
    """User-authored forum post (the API path): same ``hub.posted`` event and
    mailbox-notification semantics as an agent's tool post, but authored by
    ``user`` with no session.  Validation failures raise ``CommandRejected``
    (the API layer maps it to HTTP)."""
    topic = topic.strip()
    content = content.strip()
    if not topic or not content:
        raise CommandRejected("rejected", "post requires non-empty topic and content.")
    kind = kind.strip().lower()
    if kind not in _POST_KINDS:
        raise CommandRejected("rejected", f"Unknown kind: {kind}")
    to_agent = to_agent.strip()
    if kind == "message" and not to_agent:
        raise CommandRejected(
            "rejected", "message posts need to_agent to name the addressee (the post is still public)."
        )
    core.require_project(project_id)
    addressee = _resolve_live_target(core, project_id, to_agent) if to_agent else None
    parent = await asyncio.to_thread(core.event_log.get, parent_id) if parent_id else None
    if parent_id and (
        parent is None or parent.type != "hub.posted" or parent.project_id != project_id
    ):
        raise CommandRejected("not_found", f"parent post not found in this project: {parent_id}")
    original = (
        core.agents.get(parent.session_id)
        if parent is not None and parent.session_id
        else None
    )
    targets = (
        [
            agent for agent in _live_sessions(core, project_id)
            if agent.state not in {AgentState.FAILED, AgentState.CANCELLED}
        ]
        if kind == "broadcast" else
        [agent for agent in (addressee, original) if agent is not None]
    )
    target_ids = list(dict.fromkeys(agent.id for agent in targets))
    envelope = await core.event_writer.commit(
        EventDraft(
            "hub.posted", stream="project", project_id=project_id, session_id=None,
            data={
                "topic": topic, "kind": kind, "author_agent": "user",
                "author_session": None, "to_agent": to_agent or None,
                "parent_id": parent_id, "content": content,
                "notification_target_ids": target_ids,
                "addressed_session_id": addressee.id if addressee else None,
                "reply_session_id": original.id if original else None,
            },
        )
    )
    delivered = 0
    failed_ids: list[str] = []
    for target_id in target_ids:
        target = core.agents.get(target_id)
        if target is None or target.project_id != project_id:
            failed_ids.append(target_id)
            continue
        try:
            await _notify(
                core, project_id, target, sender="user",
                content=await asyncio.to_thread(post_notification_text, core, envelope, target_id),
                post_id=envelope.event_id,
            )
        except EventPersistenceError:
            failed_ids.append(target_id)
            continue
        delivered += 1
    return {
        "post": {
            "id": envelope.event_id,
            "seq": envelope.seq,
            "created_at": envelope.created_at.isoformat(),
            **envelope.data,
        },
        "notified_count": delivered,
        "failed_session_ids": failed_ids,
    }


def _browse(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    limit = max(1, min(int(args.get("limit") or 20), 100))
    cursor = (args.get("cursor") or "").strip()
    posts = _posts(core, author.project_id)
    if cursor:
        cursor_post = next((p for p in posts if p["id"] == cursor), None)
        if cursor_post is None:
            return _err(f"cursor not found: {cursor!r}")
        # Browse is newest-first; a cursor advances to older activity.
        posts = [p for p in posts if p["seq"] < cursor_post["seq"]]
    topics: dict[str, dict[str, Any]] = {}
    for post in posts:
        entry = topics.setdefault(
            post["topic"],
            {
                "topic": post["topic"],
                "post_count": 0,
                "latest_at": "",
                "latest_seq": -1,
                "latest_author": "",
                "preview": "",
                "latest_post_id": None,
            },
        )
        entry["post_count"] += 1
        if post["seq"] > entry["latest_seq"]:
            entry["latest_seq"] = post["seq"]
            entry["latest_at"] = post["created_at"]
            entry["latest_author"] = post.get("author_agent") or ""
            entry["preview"] = str(post.get("content") or "").strip()[:120]
            entry["latest_post_id"] = post["id"]
    rows = sorted(topics.values(), key=lambda r: r["latest_seq"], reverse=True)
    has_more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        row.pop("latest_seq", None)
    next_cursor = rows[-1]["latest_post_id"] if has_more and rows else None
    if not rows:
        return _ok("The forum has no posts yet.", posts=[], next_cursor=None)
    summary = (
        f"{len(rows)} topic(s). Browse shows only each topic's latest post preview; "
        "call read with a topic name (or search with a keyword) to see the full posts."
    )
    return _ok(summary, posts=rows, next_cursor=next_cursor)


def _read(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    topic = str(args.get("topic") or "").strip()
    limit = int(args.get("limit") or 20)
    posts = [p for p in _posts(core, author.project_id) if p["topic"] == topic][:limit]
    return _ok(
        f"Topic '{topic}' has {len(posts)} post(s)." if posts else f"Topic '{topic}' has no posts yet.",
        posts=posts,
    )


async def _search(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    keyword = str(args.get("keyword") or "").strip()
    limit = int(args.get("limit") or 20)
    scanned = await asyncio.to_thread(_posts, core, author.project_id, limit=_SEARCH_SCAN_LIMIT)
    scored = []
    for post in scanned:
        score = max(
            _fuzzy_score(keyword, post["topic"]),
            _fuzzy_score(keyword, post["content"]) * 0.9,
        )
        if score >= _FUZZY_FLOOR:
            post["score"] = round(score, 3)
            scored.append((score, post["seq"], post))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    posts = [post for _, _, post in scored[:limit]]
    # The library layer: registered knowledge providers (GraphRAG plugins)
    # are queried on every hub search — same tool, no extra interface.
    from cloudra.runtime_v2.knowledge import registered_providers, render_library_hits, search_library

    library, library_errors = await search_library(keyword, limit=5)

    # The skills layer: match domain skills on demand
    matched_skills = []
    try:
        from cloudra.base.skill_class import skill_loader
        loader = skill_loader()
        all_skills = loader.list_skills()
        k_lower = keyword.lower()
        is_skill_query = "skill" in k_lower or "sop" in k_lower or "guide" in k_lower
        for sk in all_skills:
            name_score = _fuzzy_score(keyword, sk["name"])
            desc_score = _fuzzy_score(keyword, sk["description"])
            combined = max(name_score, desc_score * 0.8)
            if is_skill_query:
                clean_k = k_lower.replace("skill", "").replace("sop", "").replace("guide", "").strip()
                if not clean_k or clean_k in sk["name"].lower() or clean_k in sk["description"].lower():
                    combined = max(combined, 0.85)
            if combined >= _FUZZY_FLOOR:
                matched_skills.append((combined, sk))
        matched_skills.sort(key=lambda x: -x[0])
        matched_skills = [sk for _, sk in matched_skills[:4]]
    except Exception:
        matched_skills = []

    forum_line = (
        f"Keyword '{keyword}' fuzzy-matched {len(posts)} post(s) (scanned the latest {len(scanned)})."
        if posts
        else f"Keyword '{keyword}' had no forum hits."
    )
    sources_status = {
        "project_posts": "available",
        "library": ('partial' if len(library_errors) < len(registered_providers()) else 'unavailable')
        if library_errors else ('available' if registered_providers() else 'no_hits'),
        "skills": "available" if matched_skills else "no_hits",
    }

    summary_parts = [forum_line]
    if matched_skills:
        skill_lines = []
        for sk in matched_skills:
            skill_lines.append(
                f"- **{sk['name']}**: {sk['description']}\n"
                f"  -> Load via: `get_skill(skill_name=\"{sk['name']}\")`"
            )
        summary_parts.append("Matched Domain Skills:\n" + "\n".join(skill_lines))

    if library:
        summary_parts.append(f"Library hits ({len(library)}):\n{render_library_hits(library)}")
    if library_errors:
        summary_parts.append('Library source errors:\n' + '\n'.join(
            f'- {name}: {error}' for name, error in library_errors.items()))

    summary = "\n\n".join(summary_parts)
    return _ok(summary, posts=posts, library=library, library_errors=library_errors,
               skills=matched_skills, sources_status=sources_status)


def _directory(core, author: AgentSession) -> ToolResult:
    rows = [
        {
            "session_id": a.id,
            "agent_id": a.role_id,
            "agent_type": (
                "system" if a.role_id == "supervisor" else
                "subagent" if a.parent_session_id else "peer"
            ),
            "parent_session_id": a.parent_session_id,
            "role_id": a.role_id,
            "state": a.state.value,
            "display_name": a.display_name,
        }
        for a in sorted(_live_sessions(core, author.project_id), key=lambda a: a.created_at, reverse=True)
    ]
    return _ok(f"{len(rows)} session(s)." if rows else "No sessions right now.", sessions=rows)


async def _call(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    spoken = str(args.get("message") or "").strip()
    raw_to = str(args.get("to") or "").strip()

    post_line = None
    raw_post_id = args.get("post_id")
    if raw_post_id is not None:
        post = await asyncio.to_thread(lambda: next((p for p in _posts(core, author.project_id) if p["id"] == raw_post_id), None))
        if post is not None:
            post_line = f"Related post {post['id']} (topic {post['topic']})."
    target = _resolve_live_target(core, author.project_id, raw_to, wakeable_role_only=True, author=author)
    text = format_incoming_call(
        caller_agent_id=author.role_id,
        caller_session_id=author.id,
        message=spoken,
        post_line=post_line,
        auto_report=target is None,
    )

    if target is not None:
        notification = await _notify(core, author.project_id, target, sender=author.role_id, content=text, author=author)
        return _ok(f"Called {target.id} (non-blocking).", session_id=target.id, notifications=[notification])

    # A missing role is a request for a new peer, independent of the caller's
    # role, settings, and cancellation tree. Process and final Supervisors are
    # system-managed; callers cannot create them through a missing role alias.
    role_id = raw_to.lstrip("@").lower()
    try:
        core.roles.require(role_id)
    except CommandRejected:
        import difflib
        valid_roles = sorted(r.role_id for r in core.roles.list())
        matches = difflib.get_close_matches(role_id, valid_roles, n=2, cutoff=0.35)
        suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
        return _err(
            f"Target {raw_to!r} is neither a project session, display_name, nor a known role.{suggestion} "
            f"Available roles: {valid_roles}."
        )
    if role_id == "supervisor":
        return _err("The Supervisor is system-managed; call its existing session or submit a review request.")
    result = await CommandBus(core).execute(
        Command(
            type="agent.spawn",
            target={"project_id": author.project_id},
            payload={
                "role_id": role_id,
                "requested_by_session_id": author.id,
            },
            actor="agent",
        )
    )
    if not result.accepted:
        error = result.data.get("error", {})
        raise CommandRejected(error.get("code", "rejected"), error.get("message", "peer creation rejected"))
    peer = result.data
    # Create the peer queued, then use the one durable Agent-to-Agent message
    # path to deliver the call and wake it. A failed message write cannot run
    # an empty peer; the returned id lets the caller retry the existing one.
    for attempt in range(2):
        try:
            notification = await _notify(core, author.project_id, peer, sender=author.role_id, content=text, author=author)
            break
        except EventPersistenceError:
            if attempt:
                return _err(
                    f"Peer {peer.id} was created, but the call message was not delivered. "
                    "Retry the call using this session_id.",
                    session_id=peer.id,
                )
    settings = peer.settings
    project = core.require_project(peer.project_id)
    project_defaults = {
        name for name, value in project.settings.defaults.model_dump(exclude_unset=True).items()
        if value is not None
    }
    role_defaults = {
        name for name, value in core.roles.require(peer.role_id).default_settings.model_dump(exclude_unset=True).items()
        if value is not None
    }
    receipt = {
        "session_id": peer.id,
        "role_id": peer.role_id,
        "model": settings.model,
        "invocation_protocol": settings.invocation_protocol.value,
        "orchestration_mode": settings.orchestration_mode.value,
        "unattended": settings.unattended,
        "visual_mode": settings.visual_mode,
        "yolo": settings.yolo,
        "schedule_mode": settings.schedule_mode,
        "clean_context": settings.clean_context,
        "sources": {
            name: (
                "role_default" if name in role_defaults else
                "project_default" if name == "orchestration_mode" or name in project_defaults else
                "schema_default"
            )
            for name in (
                "model", "invocation_protocol", "orchestration_mode", "unattended",
                "visual_mode", "yolo", "schedule_mode", "clean_context",
            )
        },
    }
    return _ok(
        f"Called {peer.id} (non-blocking). role={receipt['role_id']} "
        f"model={receipt['model'] or '(unset)'} protocol={receipt['invocation_protocol']}",
        session_id=peer.id,
        settings=receipt,
        notifications=[notification],
    )


async def handle_hub_tool(core, author: AgentSession, call: ToolCall) -> ToolResult:
    result = await _dispatch_hub_tool(core, author, call)
    receipt = AgentHub_output_schema.model_validate(result.data)
    return replace(result, data=receipt.model_dump(exclude_unset=True))


async def _dispatch_hub_tool(core, author: AgentSession, call: ToolCall) -> ToolResult:
    try:
        args = AgentHub_input_schema.model_validate(call.arguments).model_dump()
    except ValidationError as exc:
        return _err(validation_feedback(exc, schema=AgentHub_input_schema))
    action = args["action"]
    if action == "post":
        return await _post(core, author, args)
    if action == "browse":
        return await asyncio.to_thread(_browse, core, author, args)
    if action == "read":
        return await asyncio.to_thread(_read, core, author, args)
    if action == "search":
        return await _search(core, author, args)
    if action == "directory":
        return _directory(core, author)
    if action == "call":
        try:
            return await _call(core, author, args)
        except CommandRejected as exc:
            return _err(f"[dispatch rejected] {exc.message}")
    return _err(
        f"Unknown action: {action!r}. The 'action' argument is required — "
        "one of: post / browse / read / search / directory / call"
    )
