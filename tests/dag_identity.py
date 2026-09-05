"""dag_* 工具测试的共享身份构造与调用助手（Task 6 迁移）。

旧的 ``SupervisorAgent``（cloudra/core/supervisor.py）只是测试身份壳，已随
事件驱动督导迁移删除。在线路径的督导身份是
``AgentSession(role_id="supervisor")`` 经 ``_LegacyAgentBridge`` 映射出
``type="supervisor"``——dag_* 工具 ``_actor()`` 判 GraphActor.SUPERVISOR 的
唯一入口。测试直接经同一座桥构造身份，不保留"仅测试在用"的生产类。
"""

from __future__ import annotations

from cloudra.dag.models import OrchestrationMode
from cloudra.runtime_v2.adapters import _LegacyAgentBridge
from cloudra.runtime_v2.schemas import AgentSession, RuntimeSettings


def make_supervisor(
    conversation_id: str,
    *,
    orchestration_mode: str = "dag_guided",
    workspace_dir: str | None = None,
) -> _LegacyAgentBridge:
    """以在线路径同款桥构造督导身份（type="supervisor" → actor=SUPERVISOR）。"""
    agent = AgentSession(
        id="as_sv_test",
        project_id=conversation_id,
        role_id="supervisor",
        display_name="Supervisor",
        settings=RuntimeSettings(
            orchestration_mode=OrchestrationMode(orchestration_mode)
        ),
    )
    return _LegacyAgentBridge(agent, workspace_dir)


async def call_dag_tool(cls, agent, session, **kwargs):
    """与 LegacyToolExecutor 相同的构造路径：先空构造，再越过 pydantic 校验
    挂上身份（部分 dag_* 工具把 subagent 收窄声明为 legacy Agent 类型，
    duck-typed 桥过不去校验）。"""
    tool = cls()
    object.__setattr__(tool, "subagent", agent)
    schema = cls.model_fields["input_schema"].default
    return await tool.tool_call(schema(**kwargs), session)
