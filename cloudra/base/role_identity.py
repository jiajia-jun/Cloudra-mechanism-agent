"""DAG 存储词表与 v2 role_id 之间的唯一映射。

DAG 变更日志、CallReview sidecar 与 process-node ``assignee`` 用的是历史 a-N
词表（``a-0`` = Coordinator，``a-1``..``a-8`` = 八个科研子 Agent，
``a-supervisor`` = 科学督导）；runtime_v2 的实时身份是语义 role_id
（``coordinator`` / ``small_mol`` …）。运行时身份只在**DAG 存储边界**投影，
映射表只此一张——之前 subagent_bridge 的 ``_AGENT_ID_TO_ROLE``、
``subagents/registry.py`` 的 a-N 列表与 launcher/swarm 提示词里的角色清单各写一份，
新增角色要同步多处。

放置理由：runtime_v2 侧（RoleProfile）与工具侧、DAG 侧都要读它，
所以放在最底层的 ``cloudra.base``，不引入反向依赖。
"""

from __future__ import annotations

#: role_id → DAG 存储词表。新增角色只需在此登记一次 + 在 BUILTIN_ROLES 声明
#: （roles.py 里的 RoleProfile.legacy_agent_id 直接取自本表，不手抄）。
LEGACY_AGENT_ID_BY_ROLE: dict[str, str] = {
    "coordinator": "a-0",
    "explorer": "a-1",
    "writer": "a-2",
    "researcher": "a-3",
    "small_mol": "a-4",
    "md": "a-5",
    "dft": "a-6",
    "experiment": "a-7",
    "env": "a-8",
    "supervisor": "a-supervisor",
}

def legacy_agent_id_for_role(role_id: str) -> str:
    """将角色投影为当前 DAG 的内部编号；自定义角色保留语义 role_id。

    工具入口从实时角色注册表校验身份，此函数只负责 DAG 存储投影。
    """
    return LEGACY_AGENT_ID_BY_ROLE.get(role_id, role_id)
