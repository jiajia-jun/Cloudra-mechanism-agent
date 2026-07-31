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

