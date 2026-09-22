"""dag_* 工具测试的共享身份构造与调用助手（Task 6 迁移 + 评审 5.4）。

旧的 ``SupervisorAgent``（cloudra/core/supervisor.py）与 ``Coordinator`` /
``Follower``（cloudra/core/agent.py）都只是 legacy 执行栈里的身份壳，已随
评审 5.4 删除。在线路径的身份是 ``AgentSession`` 经 ``_LegacyAgentBridge``
映射出的 ``type``——dag_* 工具 ``_actor()`` 判 GraphActor 的唯一入口。

权限取自 ``BUILTIN_ROLES`` 的 ``RoleProfile``；Supervisor 的工具面与
``AgentHost.build`` 一样取 ``supervisor_tool_names()`` 的动态投影，其余角色
取 role 的静态 tool_policy。可见性断言走 ``tool_catalog.wire_tool_schemas``
（线缆投影唯一实现），不再有 legacy ``Agent.get_available_tools()``。
"""

from __future__ import annotations

from cloudra.dag.models import OrchestrationMode
from cloudra.runtime_v2.adapters import _LegacyAgentBridge
from cloudra.runtime_v2.roles import BUILTIN_ROLES
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    InvocationProtocol,
    RuntimeSettings,
)
from cloudra.tools.capabilities import supervisor_tool_names


def make_session(
    conversation_id: str,
    role_id: str,
    *,
    orchestration_mode: str = "dag_guided",
    protocol: str = "javascript",
    session_id: str | None = None,
) -> AgentSession:
    """按 RoleProfile 构造在线 AgentSession（权限/工具面同 AgentHost 派发口径）。

    ``protocol`` 默认取运行默认（javascript，评审 5.1）：该协议下线缆只投影
    ``js_exec`` + 直接控制类，**业务工具要走 JS 程序**（``guest_tool_names``）。
    断言「业务工具在不在工具面里」时必须显式 ``protocol="traditional"``。
    """
    role = next(r for r in BUILTIN_ROLES if r.role_id == role_id)
    return AgentSession(
        id=session_id or f"as_{role_id}_test",
        project_id=conversation_id,
        role_id=role_id,
        display_name=role.display_name,
        settings=RuntimeSettings(
            invocation_protocol=InvocationProtocol(protocol),
            orchestration_mode=OrchestrationMode(orchestration_mode)
        ),
        capabilities=AgentCapabilities(
            permissions=role.permissions,
            can_spawn=role.can_spawn,
            spawn_roles=list(role.spawn_roles) if role.spawn_roles is not None else None,
            tools=(
                supervisor_tool_names()
                if role.role_id == "supervisor"
                else list(role.tool_policy.allow)
            ),
        ),
    )


def make_actor(
    conversation_id: str,
    role_id: str,
    *,
    orchestration_mode: str = "dag_guided",
    workspace_dir: str | None = None,
    session_id: str | None = None,
) -> _LegacyAgentBridge:
    """按 RoleProfile 构造在线身份并经桥暴露 legacy 工具面。

    ``type`` 由角色推出（coordinator / supervisor / follower），与
    ``_LegacyAgentBridge`` 对在线 agent 的映射逐字一致。
    """
    return _LegacyAgentBridge(
        make_session(
            conversation_id,
            role_id,
            orchestration_mode=orchestration_mode,
            session_id=session_id,
        ),
        workspace_dir,
    )


def make_coordinator(
    conversation_id: str,
    *,
    orchestration_mode: str = "dag_guided",
    workspace_dir: str | None = None,
    session_id: str | None = None,
) -> _LegacyAgentBridge:
    """Coordinator 身份（actor=AGENT）：设计 delivery/机理图的唯一角色。"""
    return make_actor(
        conversation_id,
        "coordinator",
        orchestration_mode=orchestration_mode,
        workspace_dir=workspace_dir,
        session_id=session_id,
    )


def make_subagent(
    conversation_id: str,
    role_id: str = "small_mol",
    *,
    orchestration_mode: str = "dag_guided",
    workspace_dir: str | None = None,
    session_id: str | None = None,
) -> _LegacyAgentBridge:
    """科研子 Agent 身份（actor=SUBAGENT）。"""
    return make_actor(
        conversation_id,
        role_id,
        orchestration_mode=orchestration_mode,
        workspace_dir=workspace_dir,
        session_id=session_id,
    )


def make_supervisor(
    conversation_id: str,
    *,
    orchestration_mode: str = "dag_guided",
    workspace_dir: str | None = None,
) -> _LegacyAgentBridge:
    """以在线路径同款桥构造督导身份（type="supervisor" → actor=SUPERVISOR）。"""
    return make_actor(
        conversation_id,
        "supervisor",
        orchestration_mode=orchestration_mode,
        workspace_dir=workspace_dir,
        session_id="as_sv_test",
    )


def projected_tool_names(session: AgentSession) -> set[str]:
    """该 agent 在线缆投影下能看到的工具名（与 runner 发给模型的同一函数）。

    取代 legacy ``Agent.get_available_tools()``：可见性口径只有 tool_catalog 一处。
    """
    from cloudra.runtime_v2.tool_catalog import wire_tool_schemas

    return {
        (schema.get("function") or {}).get("name")
        for schema in wire_tool_schemas(session, list(session.capabilities.tools))
    }


async def call_dag_tool(cls, agent, session, **kwargs):
    """与 LegacyToolExecutor 相同的构造路径：先空构造，再越过 pydantic 校验
    挂上身份（部分 dag_* 工具把 subagent 收窄声明为 legacy Agent 类型，
    duck-typed 桥过不去校验）。"""
    tool = cls()
    object.__setattr__(tool, "subagent", agent)
    schema = cls.model_fields["input_schema"].default
    return await tool.tool_call(schema(**kwargs), session)
