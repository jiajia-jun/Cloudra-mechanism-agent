"""Agent 的线缆字典：模型字段 + 运行期投影（完成依据）。

完成依据来自事件流（``runtime_v2.completion``），不是 agent 的持久状态，所以
它不能长在 ``AgentSession`` 上；所有返回 agent 的端点（GET 与命令响应）都经
这里序列化，保证同一 agent 的 ``completion`` 字段处处一致，UI 无需自己推断。

``completion`` 为 null 的含义：这个 agent 没有已结束的 run（含正在跑/挂起——
那一次尚未有结论），或事件流里没有收尾依据。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from cloudra.runtime_v2.completion import (
    COMPLETION_EVENT_TYPES,
    COMPLETION_TAIL,
    completion_summary,
)

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import AgentSession


def agent_dict(
    core: "RuntimeCore", agent: "AgentSession", *, before_session_seq: int | None = None,
) -> dict[str, Any]:
    """单个 agent 的线缆字典（GET /api/v2/agents/{id}、命令响应用）。"""
    data = agent.model_dump(mode="json")
    if agent.current_run is not None:
        # 正在跑/挂起：这一次 run 还没有结论。
        data["completion"] = None
        return data
    data["completion"] = completion_summary(
        core.event_log.query_session(
            agent.id, types=COMPLETION_EVENT_TYPES, limit=COMPLETION_TAIL,
            before_session_seq=before_session_seq,
        )
    )
    return data


def agent_dicts(core: "RuntimeCore", agents: Iterable["AgentSession"]) -> list[dict[str, Any]]:
    """列表与单 Agent 共用有界的完成依据读取。"""
    return [agent_dict(core, agent) for agent in agents]
