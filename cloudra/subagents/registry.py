"""Explicit built-in sub-Agent manifest.

Import paths keep registry declaration safe during the ``Agent``/tool import
cycle while remaining independent of source files on disk.
"""

from dataclasses import dataclass

from cloudra.base.role_identity import legacy_agent_id_for_role


@dataclass(frozen=True)
class SubagentRegistration:
    agent_id: str
    module: str
    class_name: str


#: legacy 子 Agent 类清单（class_name 即 role_id）。agent_id 一律由
#: ``cloudra.base.role_identity`` 的**唯一**映射表派生——这里不再手写 a-N 表，
#: 新增/改名角色不需要同步第二处。
_LEGACY_SUBAGENT_ROLES: tuple[str, ...] = (
    "explorer",
    "writer",
    "researcher",
    "small_mol",
    "md",
    "dft",
    "experiment",
    "env",
)

SUBAGENT_REGISTRY: tuple[SubagentRegistration, ...] = tuple(
    SubagentRegistration(
        agent_id=legacy_agent_id_for_role(role_id),
        module=f"cloudra.subagents.{role_id}",
        class_name=role_id,
    )
    for role_id in _LEGACY_SUBAGENT_ROLES
)


