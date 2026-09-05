"""Explicit built-in sub-Agent manifest.

Import paths keep registry declaration safe during the ``Agent``/tool import
cycle while remaining independent of source files on disk.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SubagentRegistration:
    agent_id: str
    module: str
    class_name: str


SUBAGENT_REGISTRY: tuple[SubagentRegistration, ...] = (
    SubagentRegistration("a-1", "cloudra.subagents.explorer", "explorer"),
    SubagentRegistration("a-2", "cloudra.subagents.writer", "writer"),
    SubagentRegistration("a-3", "cloudra.subagents.researcher", "researcher"),
    SubagentRegistration("a-4", "cloudra.subagents.small_mol", "small_mol"),
    SubagentRegistration("a-5", "cloudra.subagents.md", "md"),
    SubagentRegistration("a-6", "cloudra.subagents.dft", "dft"),
    SubagentRegistration("a-7", "cloudra.subagents.experiment", "experiment"),
    SubagentRegistration("a-8", "cloudra.subagents.env", "env"),
)


def legacy_agent_id_for_role(role_id: str) -> str:
    """Map a v2 role_id (or Coordinator) onto the DAG assignee vocabulary.

    Process-node ``assignee`` and tool ``actor_id`` use legacy a-N ids
    (``a-0`` = Coordinator).  The scientific Supervisor has the dedicated
    ``a-supervisor`` id — it is not a research assignee slot, and an explicit
    branch keeps it distinct from the unknown-role passthrough below.
    Unknown roles pass through unchanged.
    """
    if role_id == "coordinator":
        return "a-0"
    if role_id == "supervisor":
        return "a-supervisor"
    for reg in SUBAGENT_REGISTRY:
        if reg.class_name == role_id or reg.agent_id == role_id:
            return reg.agent_id
    return role_id

