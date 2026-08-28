"""v2-native AgentHub: the forum lives in the event log, calls in the Mailbox.

The legacy ``agent_hub`` tool stores posts in the conversation SQLite
(``hub_posts``) and notifies through legacy context injection.  In runtime_v2 neither
exists, so this bridge re-implements the six actions on kernel primitives:

- ``post`` appends a ``hub.posted`` event (project stream); the event log is
  the forum store, so posts survive replay like everything else.
- ``browse`` / ``read`` / ``search`` are pure projections over those events.
- Notifications (to_agent / reply) and ``call`` to a live session go through
  ``Mailbox.deliver`` — the runner picks the message up at the next turn
  boundary, which is the v2 equivalent of legacy inject_event.  A
  sleeping/idle addressee is woken (``AgentHost.wake``) so the mention or call
  takes effect immediately instead of sitting in the inbox.
- ``call`` to a role/id spawns a fresh child via the same CommandBus path as
  the launcher bridge.

The legacy tool module is untouched — CLI/Flet keep using it.  Only the fuzzy
scoring helpers (pure functions) and the incoming-call template are imported
from there.
"""

from __future__ import annotations

from typing import Any

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentSession, CommandRejected
from cloudra.runtime_v2.subagent_bridge import _role_id_for, _spawn_child
from cloudra.tools.Managetool._hub_call import format_incoming_call
from cloudra.tools.Managetool.agent_hub import _FUZZY_FLOOR, _SEARCH_SCAN_LIMIT, _fuzzy_score

_POST_KINDS = ("finding", "question", "answer", "broadcast", "message")
_COORDINATOR_ALIASES = ("coordinator", "a-0")


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


def _resolve_live_target(core, project_id: str, target: str) -> AgentSession | None:
    """Map a to_agent/to spec onto a live session: coordinator alias, exact
    session id, or the most recently spawned live agent of a role."""
    t = target.strip()
    if not t:
        return None
    sessions = _live_sessions(core, project_id)
    if t.lower() in _COORDINATOR_ALIASES:
        return next((a for a in sessions if a.role_id == "coordinator"), None)
    by_id = core.agents.get(t)
    if by_id is not None and by_id.project_id == project_id:
        return by_id
    role_id = _role_id_for(t)
    matches = [a for a in sessions if a.role_id == role_id]
    return matches[-1] if matches else None


def _notify(core, project_id: str, target: AgentSession, *, sender: str, content: str) -> None:
    core.mailbox.deliver(
        to_session_id=target.id,
        project_id=project_id,
        content=content,
        sender=sender,
    )
    # A sleeping or idle addressee would otherwise leave the message sitting
    # in the inbox until some unrelated event; wake it so the mention/call
    # takes effect immediately.
    core.agent_host.wake(target, runner=core.runner)


def _err(message: str) -> ToolResult:
    return ToolResult(is_success=False, summary=message, data={"is_success": False, "message": message})


def _ok(summary: str, **data: Any) -> ToolResult:
    return ToolResult(is_success=True, summary=summary, data={"is_success": True, "message": summary, **data})


def _post(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    topic = str(args.get("topic") or "").strip()
    content = str(args.get("content") or "").strip()
    if not topic or not content:
        return _err("post requires non-empty topic and content.")
    kind = str(args.get("kind") or "finding").strip().lower()
    if kind not in _POST_KINDS:
        return _err(f"Unknown kind: {kind}")
    to_agent = str(args.get("to_agent") or "").strip()
    parent_id = args.get("parent_id") or None
    if kind == "message" and not to_agent:
        return _err("message posts need to_agent to name the addressee (the post is still public).")
    # A valid name may have no live session in this project; the post is still
    # public, so an unresolved addressee just means no notification.
    addressee = _resolve_live_target(core, author.project_id, to_agent) if to_agent else None

    envelope = core.event_log.append(
        "hub.posted",
        stream="project",
        project_id=author.project_id,
        session_id=author.id,
        data={
            "topic": topic,
            "kind": kind,
            "author_agent": author.role_id,
            "author_session": author.id,
            "to_agent": to_agent or None,
            "parent_id": parent_id,
            "content": content,
        },
    )
    notices = []
    if addressee is not None and addressee.id != author.id:
        _notify(
            core,
            author.project_id,
            addressee,
            sender=author.role_id,
            content=(
                f"{author.role_id} mentioned you in AgentHub topic '{topic}' "
                f"(post {envelope.event_id}): {content}"
            ),
        )
        notices.append(f"Notified {to_agent}.")
    if parent_id:
        parent = next((p for p in _posts(core, author.project_id) if p["id"] == parent_id), None)
        if parent is not None and parent["author_session"] != author.id:
            original = core.agents.get(parent["author_session"])
            if original is not None and (addressee is None or original.id != addressee.id):
                _notify(
                    core,
                    author.project_id,
                    original,
                    sender=author.role_id,
                    content=(
                        f"{author.role_id} replied to your AgentHub post in topic "
                        f"'{parent['topic']}' {parent_id} (reply {envelope.event_id}): {content}"
                    ),
                )
                notices.append(f"Notified original author {parent['author_agent']}.")
    message = f"Posted to topic '{topic}' (id={envelope.event_id})."
    if notices:
        message += " " + " ".join(notices)
    return _ok(message, post_id=envelope.event_id)


def _browse(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    limit = int(args.get("limit") or 20)
    topics: dict[str, dict[str, Any]] = {}
    for post in _posts(core, author.project_id):
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
    rows = sorted(topics.values(), key=lambda r: r["latest_seq"], reverse=True)[:limit]
    for row in rows:
        row.pop("latest_seq", None)
    if not rows:
        return _ok("The forum has no posts yet.", posts=[])
    summary = (
        f"{len(rows)} topic(s). Browse shows only each topic's latest post preview; "
        "call read with a topic name (or search with a keyword) to see the full posts."
    )
    return _ok(summary, posts=rows)


def _read(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    topic = str(args.get("topic") or "").strip()
    if not topic:
        return _err("read requires a topic.")
    limit = int(args.get("limit") or 20)
    posts = [p for p in _posts(core, author.project_id) if p["topic"] == topic][:limit]
    return _ok(
        f"Topic '{topic}' has {len(posts)} post(s)." if posts else f"Topic '{topic}' has no posts yet.",
        posts=posts,
    )


def _render_library(entries: list[dict[str, Any]]) -> str:
    """Model-facing rendering of library hits (full dicts ride in data)."""
    lines = []
    for entry in entries:
        flag = " [FALSIFIED — refuted, kept for audit]" if entry["falsified"] else ""
        source = f" — source: {entry['source']}" if entry["source"] else ""
        snippet = " ".join(str(entry["content"]).split())[:200]
        lines.append(
            f"- [{entry['evidence_level']}]{flag} {entry['title']}: {snippet}"
            f" (provider: {entry['provider']}){source}"
        )
    return "\n".join(lines)


async def _search(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    keyword = str(args.get("keyword") or "").strip()
    if not keyword:
        return _err("search requires a keyword.")
    limit = int(args.get("limit") or 20)
    scanned = _posts(core, author.project_id, limit=_SEARCH_SCAN_LIMIT)
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
    from cloudra.runtime_v2.knowledge import search_library

    library = await search_library(keyword, limit=5)
    forum_line = (
        f"Keyword '{keyword}' fuzzy-matched {len(posts)} post(s) (scanned the latest {len(scanned)})."
        if posts
        else f"Keyword '{keyword}' had no forum hits."
    )
    if not library:
        return _ok(forum_line, posts=posts, library=[])
    summary = f"{forum_line}\nLibrary hits ({len(library)}):\n{_render_library(library)}"
    return _ok(summary, posts=posts, library=library)


def _directory(core, author: AgentSession) -> ToolResult:
    rows = [
        {
            "session_id": a.id,
            "agent_id": a.role_id,
            "agent_type": "coordinator" if a.role_id == "coordinator" else "follower",
            "state": a.state.value,
            "display_name": a.display_name,
        }
        for a in sorted(_live_sessions(core, author.project_id), key=lambda a: a.created_at, reverse=True)
    ]
    return _ok(f"{len(rows)} session(s)." if rows else "No sessions right now.", sessions=rows)


async def _call(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    spoken = str(args.get("message") or "").strip()
    if not spoken:
        return _err("call requires a non-empty message.")
    raw_to = str(args.get("to") or "").strip()
    if not raw_to:
        return _err("call requires a non-empty to.")

    post_line = None
    if args.get("post_id"):
        post = next((p for p in _posts(core, author.project_id) if p["id"] == args["post_id"]), None)
        if post is not None:
            post_line = f"Related post {post['id']} (topic {post['topic']})."
    text = format_incoming_call(
        caller_agent_id=author.role_id,
        caller_session_id=author.id,
        message=spoken,
        post_line=post_line,
    )

    target = _resolve_live_target(core, author.project_id, raw_to)
    if target is not None:
        _notify(core, author.project_id, target, sender=author.role_id, content=text)
        return _ok(f"Called {target.id} (non-blocking).", session_id=target.id)

    # No live session: role names / a-N ids spawn a fresh child, mirroring the
    # legacy spawn-from-call path.
    role_id = _role_id_for(raw_to)
    core.roles.require(role_id)  # raises CommandRejected for unknown roles
    child = await _spawn_child(
        CommandBus(core),
        author,
        role_id=role_id,
        query=spoken,
        context=[{"role": "user", "content": text}],
    )
    return _ok(f"Called {child.id} (non-blocking).", session_id=child.id)


async def handle_hub_tool(core, author: AgentSession, call: ToolCall) -> ToolResult:
    args = call.arguments or {}
    action = str(args.get("action") or "").strip().lower()
    if action == "post":
        return _post(core, author, args)
    if action == "browse":
        return _browse(core, author, args)
    if action == "read":
        return _read(core, author, args)
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
