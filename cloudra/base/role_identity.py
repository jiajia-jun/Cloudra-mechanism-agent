"""DAG 存储词表与 v2 role_id 之间的唯一映射。

DAG 变更日志、CallReview sidecar 与 process-node ``assignee`` 用的是历史 a-N
词表（``a-0`` = Coordinator，``a-1``..``a-8`` = 八个科研子 Agent，
``a-supervisor`` = 科学督导）；runtime_v2 的实时身份是语义 role_id
（``coordinator`` / ``small_mol`` …）。两套词表只在**存储/读取边界**互换，
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

#: 反向索引（一次构建）。
_ROLE_BY_LEGACY_AGENT_ID: dict[str, str] = {
    legacy: role for role, legacy in LEGACY_AGENT_ID_BY_ROLE.items()
}


def legacy_agent_id_for_role(role_id: str) -> str:
    """v2 role_id → DAG 词表 id。未知 role（或传入的已是 legacy id）原样透传。

    透传是刻意的：历史库里存着 a-N，读取边界不能再把未知值改成别的身份。
    """
    return LEGACY_AGENT_ID_BY_ROLE.get(role_id, role_id)


def role_id_for_legacy_agent_id(legacy_agent_id: str) -> str:
    """DAG 词表 id → v2 role_id。未知值（或已是 role_id）原样透传。

    仅用于把历史输入（旧提示词/旧工具参数里的 ``a-3``）归一到语义身份；新事件与
    新工具参数一律以 role_id 为准。
    """
    return _ROLE_BY_LEGACY_AGENT_ID.get(legacy_agent_id, legacy_agent_id)
