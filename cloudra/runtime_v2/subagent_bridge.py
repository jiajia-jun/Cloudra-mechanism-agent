"""v2-native execution for the legacy Managetool dispatch tools.

``subagent_launcher`` / ``subagent_swarm`` / ``get_subagent_report``
(legacy classes ``SubAgentLauncher`` / ``SubAgentSwarm``) are
intercepted by LegacyToolExecutor and reimplemented on the v2 kernel:
children become first-class v2 agents (streaming, cancel, message injection,
DAG policy stage) instead of legacy executor sessions in the conversation DB.
The legacy dispatch module is untouched — CLI/Flet keep using it.

Role mapping mirrors the launcher prompt (a-1..a-8 → role names); passing a
role name directly is also accepted.
"""

from __future__ import annotations

import asyncio
from typing import Any

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentSession, AgentState, Command, CommandRejected

# Stable ids from the subagent_launcher prompt; values are v2 role ids.
_AGENT_ID_TO_ROLE = {
    "a-1": "explorer",
    "a-2": "writer",
    "a-3": "researcher",
    "a-4": "small_mol",
    "a-5": "md",
    "a-6": "dft",
    "a-7": "experiment",
    "a-8": "env",
}

_TERMINAL_STATES = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}
_LAUNCHER = "subagent_launcher"
_SWARM = "subagent_swarm"
_REPORT = "get_subagent_report"
NATIVE_TOOL_NAMES = {_LAUNCHER, _SWARM, _REPORT}


def _role_id_for(agent_id: str) -> str:
    return _AGENT_ID_TO_ROLE.get(agent_id, agent_id)


def _child_mode(parent: AgentSession) -> str:
    """Children inherit the parent's orchestration mode (standard / dag_record / dag_guided)."""
    return parent.settings.orchestration_mode.value


def _combined_query(query: str, context: list[Any]) -> str:
    messages = [m for m in context if isinstance(m, dict) and m.get("content")]
    if not messages:
        return query
    lines = ["[Context from coordinator]"]
    lines.extend(f"{m.get('role', 'user')}: {m['content']}" for m in messages)
    return "\n".join(lines) + f"\n\n[Task]\n{query}"


async def _spawn_child(
    bus: CommandBus, parent: AgentSession, *, role_id: str, query: str, context: list[Any]
) -> AgentSession:
    parent_role = bus.core.roles.require(parent.role_id)
    if not parent_role.can_spawn:
        raise CommandRejected("forbidden", f"role {parent.role_id!r} cannot spawn sub-agents")
    if parent_role.spawn_roles is not None and role_id not in parent_role.spawn_roles:
        raise CommandRejected("forbidden", f"role {parent.role_id!r} cannot spawn {role_id!r}")
    # 空任务字段绝不发送：空 query 的 spawn 只会产出永不调度的僵尸子 agent
    # （只落 agent.spawned，无 run、无 prompt 注入），上层轮询无果即挂死。
    # 响亮拒绝并留反馈给模型重试，而不是静默造一个空壳。
    query = _combined_query(query, context)
    if not query.strip():
        raise CommandRejected(
            "invalid_request",
            "refusing to spawn a sub-agent: task query is empty (expected the 'query' argument); nothing was dispatched",
        )
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": parent.project_id},
            payload={
                "role_id": role_id,
                "parent_session_id": parent.id,
                "query": query,
                # yolo 是用户对整个任务的信任授权，子 agent 代父行事，spawn 时
                # 继承父的取值——否则父开了 yolo、子 agent 仍逐项弹审批。
                "settings": {
                    "orchestration_mode": _child_mode(parent),
                    "yolo": parent.settings.yolo,
                    "schedule_mode": parent.settings.schedule_mode,
                    "clean_context": parent.settings.clean_context,
                },
            },
        )
    )
    return result.data


async def _await_terminal(core, session_id: str) -> AgentSession:
    agent = core.require_agent(session_id)
    if agent.state in _TERMINAL_STATES:
        return agent
    done = asyncio.Event()

    async def on_event(envelope) -> None:
        if (
            envelope.type == "agent.state_changed"
            and envelope.session_id == session_id
            and envelope.data.get("to") in {s.value for s in _TERMINAL_STATES}
        ):
            done.set()

    core.event_hub.subscribe(on_event)
    try:
        await done.wait()
    finally:
        core.event_hub.unsubscribe(on_event)
    return core.require_agent(session_id)


def _final_text(core, agent: AgentSession) -> str:
    emitted = core.event_log.query_session(
        agent.id, types={"agent.message_emitted"}, limit=1
    )
    if emitted:
        return str(emitted[-1].data.get("content") or "")
    if agent.state is AgentState.FAILED:
        return f"Sub-agent failed: {agent.current_run or 'see events'}"
    return f"Sub-agent ended with state {agent.state.value} and no final message."


def _parent_report_text(core, child: AgentSession) -> str:
    return (
        f"[Sub-agent finished] role={child.role_id} session_id={child.id} "
        f"state={child.state.value}\n\n{_final_text(core, child)}"
    )


def deliver_child_completion_to_parent(core, child: AgentSession) -> None:
    """Push a finished child's report into the parent's mailbox and wake it.

    Async (``is_wait=False``) dispatch otherwise leaves the parent with no
    signal; the mailbox is the same channel hub mentions already use.  A
    cancelled parent is left alone so cascade-cancel does not reopen it.
    """
    parent_id = child.parent_session_id
    if not parent_id:
        return
    parent = core.agents.get(parent_id)
    if parent is None or parent.state is AgentState.CANCELLED:
        return
    core.mailbox.deliver(
        to_session_id=parent.id,
        project_id=child.project_id,
        content=_parent_report_text(core, child),
        sender=child.role_id,
    )
    core.agent_host.wake(parent, runner=core.runner)


async def _cancel_child(core, session_id: str) -> None:
    try:
        await CommandBus(core).execute(
            Command(type="agent.cancel", target={"session_id": session_id}, payload={})
        )
    except CommandRejected:
        pass  # already terminal


async def _handle_launcher(core, parent: AgentSession, args: dict[str, Any]) -> ToolResult:
    bus = CommandBus(core)
    role_id = _role_id_for(str(args.get("agent_id") or ""))
    child = await _spawn_child(
        bus, parent, role_id=role_id, query=str(args.get("query") or ""), context=args.get("context") or []
    )
    data = {"session_id": child.id, "act_agent": child.role_id}
    if not args.get("is_wait"):
        data["result"] = (
            f"Task submitted asynchronously: session_id={child.id}. "
            f'Retrieve the result later with get_subagent_report(session_id="{child.id}").'
        )
        return ToolResult(is_success=True, summary=data["result"], data=data)
    try:
        child = await _await_terminal(core, child.id)
    except asyncio.CancelledError:
        await _cancel_child(core, child.id)
        raise
    data["result"] = _final_text(core, child)
    return ToolResult(
        is_success=child.state is AgentState.SUCCEEDED,
        summary=data["result"],
        data=data,
    )


def _launch_group_manager(core):
    if getattr(core, "launch_groups", None) is None:
        from cloudra.runtime_v2.launch_groups import LaunchGroupManager
        core.launch_groups = LaunchGroupManager(spawner=lambda _query: None)
    return core.launch_groups


async def _handle_swarm(core, parent: AgentSession, args: dict[str, Any]) -> ToolResult:
    bus = CommandBus(core)
    role_id = _role_id_for(str(args.get("agent_id") or ""))
    template = str(args.get("prompt_template") or "")
    items = [str(item) for item in args.get("items") or []]
    context = args.get("context") or []
    is_wait = bool(args.get("is_wait", True))
    max_concurrency = int(args.get("max_concurrency") or 0)
    if "{{item}}" not in template:
        return ToolResult(is_success=False, summary="prompt_template must contain the {{item}} placeholder")
    if not items:
        return ToolResult(is_success=False, summary="items must be a non-empty list")

    # New non-blocking + capped path uses LaunchGroupManager.  The semaphore
    # covers child lifetime (not just spawn), unlike the legacy is_wait=false
    # path which returns immediately and cannot enforce active children.
    if not is_wait and max_concurrency > 0:
        manager = _launch_group_manager(core)
        async def spawner(query):
            return await _spawn_child(bus, parent, role_id=role_id, query=query, context=context)
        group_id = "grp_" + asyncio.get_running_loop().time().__str__().replace(".", "_")
        manager.create(
            group_id=group_id,
            parent_session_id=parent.id,
            items=[(f"{item[:20]}-{idx}", template.replace("{{item}}", item)) for idx, item in enumerate(items)],
            max_concurrency=max_concurrency,
            spawner=spawner,
        )
        summary = f"Dispatched launch group {group_id} with {len(items)} items; pending_count={len(items)}"
        return ToolResult(
            is_success=True,
            summary=summary,
            data={"group_id": group_id, "session_ids": [], "pending_count": len(items), "result": summary},
        )

    semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency > 0 else None

    spawned: list[str] = []

    async def run_one(item: str) -> tuple[str, AgentSession]:
        query = template.replace("{{item}}", item)
        if semaphore is None:
            child = await _spawn_child(bus, parent, role_id=role_id, query=query, context=context)
            spawned.append(child.id)
            if is_wait:
                child = await _await_terminal(core, child.id)
            return item, child
        async with semaphore:
            child = await _spawn_child(bus, parent, role_id=role_id, query=query, context=context)
            spawned.append(child.id)
            if is_wait:
                child = await _await_terminal(core, child.id)
        return item, child

    try:
        results = await asyncio.gather(*(run_one(item) for item in items))
    except asyncio.CancelledError:
        # Parent run cancelled mid-swarm: cascade to the children.
        await asyncio.gather(
            *(_cancel_child(core, sid) for sid in spawned), return_exceptions=True
        )
        raise
    except CommandRejected as exc:
        return ToolResult(is_success=False, summary=f"swarm dispatch rejected: {exc.message}")
    session_ids = [child.id for _, child in results]
    if not is_wait:
        summary = f"Dispatched {len(session_ids)} sub-agents: " + ", ".join(session_ids)
        return ToolResult(is_success=True, summary=summary, data={"session_ids": session_ids, "result": summary})

    sections = []
    ok = True
    for item, child in results:
        text = _final_text(core, child)
        ok = ok and child.state is AgentState.SUCCEEDED
        sections.append(f"## {item[:40]}\nstate: {child.state.value}\n{text}")
    summary = "\n\n".join(sections)
    return ToolResult(is_success=ok, summary=summary, data={"session_ids": session_ids, "result": summary})


async def _handle_report(core, args: dict[str, Any]) -> ToolResult:
    group_id = str(args.get("group_id") or "")
    if group_id:
        manager = _launch_group_manager(core)
        group = manager.get(group_id)
        if group is None:
            return ToolResult(is_success=False, summary=f"Unknown launch group {group_id!r}")
        summary_obj = group.summary()
        summary = (
            f"Launch group {group_id}: state={summary_obj['state']} "
            f"pending={summary_obj['pending_count']} running={summary_obj['running_count']}"
        )
        return ToolResult(is_success=True, summary=summary, data=summary_obj)
    session_id = str(args.get("session_id") or "")
    agent = core.agents.get(session_id)
    if agent is None:
        return ToolResult(
            is_success=False,
            summary=f"Unknown v2 session {session_id!r}. Sessions dispatched before this migration live in the legacy store and are not queryable here.",
        )
    if agent.state not in _TERMINAL_STATES:
        return ToolResult(
            is_success=True,
            summary=f"Sub-agent {session_id} is still {agent.state.value}; ask again later.",
            data={"session_id": session_id, "state": agent.state.value},
        )
    text = _final_text(core, agent)
    return ToolResult(
        is_success=agent.state is AgentState.SUCCEEDED,
        summary=text,
        data={"session_id": session_id, "state": agent.state.value, "result": text},
    )


async def handle_native_tool(core, parent: AgentSession, call: ToolCall) -> ToolResult:
    try:
        if call.name == _LAUNCHER:
            return await _handle_launcher(core, parent, call.arguments)
        if call.name == _SWARM:
            return await _handle_swarm(core, parent, call.arguments)
        return await _handle_report(core, call.arguments)
    except CommandRejected as exc:
        return ToolResult(is_success=False, summary=f"[dispatch rejected] {exc.message}")
