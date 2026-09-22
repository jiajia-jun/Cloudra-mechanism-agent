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
import uuid
from typing import Any

from cloudra.base.role_identity import role_id_for_legacy_agent_id
from cloudra.runtime_v2.child_manifest import build_child_manifest, render_child_report
from cloudra.runtime_v2.child_settings import resolve_child_settings
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentSession, AgentState, Command, CommandRejected

_TERMINAL_STATES = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}
_LAUNCHER = "subagent_launcher"
_SWARM = "subagent_swarm"
_REPORT = "get_subagent_report"
NATIVE_TOOL_NAMES = {_LAUNCHER, _SWARM, _REPORT}


def _combined_query(query: str, context: list[Any]) -> str:
    messages = [m for m in context if isinstance(m, dict) and m.get("content")]
    if not messages:
        return query
    lines = ["[Context from coordinator]"]
    lines.extend(f"{m.get('role', 'user')}: {m['content']}" for m in messages)
    return "\n".join(lines) + f"\n\n[Task]\n{query}"


def _render_settings_receipt(receipt: dict[str, Any]) -> str:
    """把有效设置摘要渲染成一行文本（确定性；api_key/base_url 不出现）。"""
    return (
        f"settings: role={receipt['role_id']} model={receipt['model'] or '(unset)'} "
        f"protocol={receipt['invocation_protocol']} "
        f"orchestration={receipt['orchestration_mode']} "
        f"unattended={receipt['unattended']} visual={receipt['visual_mode']}"
    )


async def _spawn_child(
    bus: CommandBus, parent: AgentSession, *, role_id: str, query: str, context: list[Any]
) -> tuple[AgentSession, dict[str, Any]]:
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
    # 继承规则只有一个解析点（child_settings）：这里只提交补丁，不回显规则。
    plan = resolve_child_settings(
        parent,
        project=bus.core.require_project(parent.project_id),
        role=bus.core.roles.require(role_id),
    )
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": parent.project_id},
            payload={
                "role_id": role_id,
                "parent_session_id": parent.id,
                "query": query,
                "settings": plan.spawn_payload_settings(),
            },
        )
    )
    child = result.data
    return child, plan.receipt(child)


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


def _manifest_payload(core, child: AgentSession) -> dict[str, Any]:
    """子 Agent 完成回报的结构化 manifest（唯一来源，文本由它渲染）。"""
    return build_child_manifest(core, child)


def child_completion_message(
    core, child: AgentSession
) -> tuple[str, str, dict[str, Any]] | None:
    """父信箱的完成回报：``(parent_session_id, content, manifest)``。

    纯组装（不投递、不入队）：live 路径经 ``MessageDispatcher`` 投递，恢复路径
    经 ``persistence`` 先落库再入队——两处共用同一份载荷构造，避免第二套报文。
    None = 没有父或父已不在内存。
    """
    parent_id = child.parent_session_id
    if not parent_id:
        return None
    if core.agents.get(parent_id) is None:
        return None
    manifest = build_child_manifest(core, child)
    return parent_id, render_child_report(manifest), manifest


async def deliver_child_completion_to_parent(
    core, child: AgentSession, *, wake: bool = True
) -> None:
    """Push a finished child's report into the parent's mailbox and wake it.

    Async (``is_wait=False``) dispatch otherwise leaves the parent with no
    signal; the mailbox is the same channel hub mentions already use.

    统一不复活纪律（park-don't-wake）：父处于 failed/cancelled 终态时报告
    照常投递信箱驻留（durable ``agent.message_injected`` + 内存队列），但
    绝不唤醒——用户随后用显式消息复活该 agent 时首轮即可读到。succeeded
    父在*在线*完成回传时照常 wake 开新 run（异步派发回传模式）。

    ``wake=False`` 给进程恢复：只投递信箱，不把休眠父打进新的 LLM run
    （issue #35）。显式 message / restart 才开跑，届时首轮 drain 可读到。
    """
    message = child_completion_message(core, child)
    if message is None:
        return
    parent_id, content, manifest = message
    await core.dispatcher.commit_and_deliver(
        to_session_id=parent_id,
        project_id=child.project_id,
        # 父上下文只注入简洁文本；结构化 manifest 随事件留存（评审 5.5：
        # 「人类可读文本从 manifest 确定性渲染；事件/API 保留结构化数据」）。
        content=content,
        sender=child.role_id,
        manifest=manifest,
        wake=WakePolicy.PARK_TERMINAL if wake else WakePolicy.NEVER,
    )


async def _cancel_child(core, session_id: str) -> None:
    """取消一个子 agent；已终态则直接返回，不去取命令锁。

    快路径不是省事：本函数常在「刚被取消的父 agent 的收尾」里被调用，而父的
    ``agent.cancel`` 命令此刻正持有 CommandBus 的串行化锁、并把持锁任务挂在
    这批收尾上。为**已终态**的子 agent 再去抢同一把锁会直接自死锁（
    ``_TaskReentrantLock`` 只认同一个 task 重入，而这里是新任务）——实测三个
    子 agent 全已 cancelled、两个本函数仍卡在等锁，把整批取消悬停。
    已终态时 ``plan_cancel`` 本来就返回空计划，跳过与执行它严格等价。
    """
    agent = core.agents.get(session_id)
    if agent is None or agent.state in _TERMINAL_STATES:
        return
    try:
        await CommandBus(core).execute(
            Command(type="agent.cancel", target={"session_id": session_id}, payload={})
        )
    except CommandRejected:
        pass  # already terminal (raced with another cancel)


async def _handle_launcher(core, parent: AgentSession, args: dict[str, Any]) -> ToolResult:
    bus = CommandBus(core)
    role_id = role_id_for_legacy_agent_id(str(args.get("agent_id") or ""))
    child, settings_receipt = await _spawn_child(
        bus, parent, role_id=role_id, query=str(args.get("query") or ""), context=args.get("context") or []
    )
    data = {"session_id": child.id, "act_agent": child.role_id, "settings": settings_receipt}
    if not args.get("is_wait"):
        data["result"] = (
            f"Task submitted asynchronously: session_id={child.id} "
            f"({_render_settings_receipt(settings_receipt)}). "
            f"The sub-agent will notify progress via agent_hub and deliver a completion report upon finish. "
            f'You may proceed with other work, stop/suspend, or check get_subagent_report(session_id="{child.id}").'
        )
        return ToolResult(is_success=True, summary=data["result"], data=data)
    try:
        child = await _await_terminal(core, child.id)
    except asyncio.CancelledError:
        await _cancel_child(core, child.id)
        raise
    manifest = build_child_manifest(core, child)
    data["result"] = (
        f"[{_render_settings_receipt(settings_receipt)}]\n\n{render_child_report(manifest)}"
    )
    data["settings"] = settings_receipt
    data["manifest"] = manifest
    return ToolResult(
        is_success=child.state is AgentState.SUCCEEDED,
        summary=data["result"],
        data=data,
    )


def _launch_group_manager(core):
    """组的投影随 core 装配（事件应用点需要它）；这里只接线进程内能力。"""
    def _track(parent_session_id: str, task: asyncio.Task, label: str) -> None:
        # 组 worker 任务登记进 runner 的 session 作用域后台注册表：用户
        # 取消父 agent / 服务 shutdown 才能取消并 await 它（停止语义契约
        # 1/3）；runner 后挂时经闭包现读，绝不留裸 create_task。
        runner = getattr(core, "runner", None)
        if runner is not None:
            runner.track_background(parent_session_id, task, label=label)

    return core.launch_groups.configure(track=_track)


async def _handle_swarm(core, parent: AgentSession, args: dict[str, Any]) -> ToolResult:
    bus = CommandBus(core)
    role_id = role_id_for_legacy_agent_id(str(args.get("agent_id") or ""))
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
            child, _receipt = await _spawn_child(bus, parent, role_id=role_id, query=query, context=context)
            return child
        group_id = "grp_" + uuid.uuid4().hex
        # 组清单先落 durable 事件再启动 worker（评审 5.2：重启可重建组清单）。
        await manager.create(
            group_id=group_id,
            parent_session_id=parent.id,
            project_id=parent.project_id,
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
            child, _receipt = await _spawn_child(bus, parent, role_id=role_id, query=query, context=context)
            spawned.append(child.id)
            if is_wait:
                child = await _await_terminal(core, child.id)
            return item, child
        async with semaphore:
            child, _receipt = await _spawn_child(bus, parent, role_id=role_id, query=query, context=context)
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
    manifests: list[dict[str, Any]] = []
    ok = True
    for item, child in results:
        manifest = build_child_manifest(core, child)
        manifests.append(manifest)
        ok = ok and child.state is AgentState.SUCCEEDED
        sections.append(f"## {item[:40]}\n{render_child_report(manifest)}")
    summary = "\n\n".join(sections)
    return ToolResult(
        is_success=ok,
        summary=summary,
        # 部分失败也有稳定结构：每个 child 一条 manifest，父不必解析文本。
        data={"session_ids": session_ids, "result": summary, "children": manifests},
    )


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
    manifest = build_child_manifest(core, agent)
    text = render_child_report(manifest)
    return ToolResult(
        is_success=agent.state is AgentState.SUCCEEDED,
        summary=text,
        data={
            "session_id": session_id,
            "state": agent.state.value,
            "result": text,
            "manifest": manifest,
        },
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
