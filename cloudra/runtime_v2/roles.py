"""Role profiles: the only place role permissions and defaults live.

Coordinator is one role among peers; nothing in the runtime may special-case
its role_id.  Agent-to-agent privileges are derived from ``can_spawn`` and
``spawn_roles``, never from a hard-coded coordinator id.
"""

from __future__ import annotations

from cloudra.runtime_v2.schemas import PermissionSet, RoleProfile

BUILTIN_ROLES: tuple[RoleProfile, ...] = (
    RoleProfile(
        role_id="coordinator",
        display_name="Coordinator",
        description="Decomposes objectives and dispatches peer agents.",
        permissions=PermissionSet(read=True, write=True, manage=True, script=True, destructive=True),
        can_spawn=True,
        spawn_roles=None,
    ),
    RoleProfile(
        role_id="explorer",
        display_name="Explorer",
        description="Read-only project structure and evidence review.",
        permissions=PermissionSet(read=True),
        can_spawn=False,
    ),
    RoleProfile(
        role_id="writer",
        display_name="Writer",
        description="Writes documents and reports; no script execution.",
        permissions=PermissionSet(read=True, write=True),
        can_spawn=False,
    ),
    RoleProfile(
        role_id="researcher",
        display_name="Researcher",
        description="Literature search and method comparison.",
        permissions=PermissionSet(read=True, write=True, script=True, destructive=True),
        can_spawn=False,
    ),
    RoleProfile(
        role_id="small_mol",
        display_name="Small-molecule compute",
        description="Gaussian/ORCA molecular and cluster QM.",
        permissions=PermissionSet(read=True, write=True, script=True, destructive=True),
        can_spawn=False,
    ),
    RoleProfile(
        role_id="md",
        display_name="Molecular dynamics",
        description="Classical and enhanced-sampling MD.",
        permissions=PermissionSet(read=True, write=True, script=True, destructive=True),
        can_spawn=False,
    ),
    RoleProfile(
        role_id="dft",
        display_name="First-principles",
        description="VASP/CP2K periodic systems.",
        permissions=PermissionSet(read=True, write=True, script=True, destructive=True),
        can_spawn=False,
    ),
    RoleProfile(
        role_id="experiment",
        display_name="Experiment design",
        description="Experimental design and data analysis.",
        permissions=PermissionSet(read=True, write=True, script=True, destructive=True),
        can_spawn=False,
    ),
    RoleProfile(
        role_id="env",
        display_name="Environment",
        description="Scientific software environment setup and debugging.",
        permissions=PermissionSet(read=True, write=True, script=True, destructive=True),
        can_spawn=False,
    ),
    RoleProfile(
        role_id="supervisor",
        display_name="Supervisor",
        description="DAG 督导运行的壳会话：只在 dag_guided 下由 dag stage 投影，不经 LLM 管线。",
        permissions=PermissionSet(read=True),
        can_spawn=False,
    ),
)


class RoleRegistry:
    def __init__(self, roles: tuple[RoleProfile, ...] = BUILTIN_ROLES) -> None:
        self._roles = {role.role_id: role for role in roles}

    def list(self) -> list[RoleProfile]:
        return list(self._roles.values())

    def get(self, role_id: str) -> RoleProfile | None:
        return self._roles.get(role_id)

    def require(self, role_id: str) -> RoleProfile:
        role = self._roles.get(role_id)
        if role is None:
            from cloudra.runtime_v2.schemas import CommandRejected

            raise CommandRejected("not_found", f"unknown role {role_id!r}")
        return role

    def update(self, role_id: str, patch: dict) -> RoleProfile:
        role = self.require(role_id)
        # 整模型重校验：patch 里的嵌套 dict（default_settings/permissions/
        # tool_policy）必须落成对应模型实例。裸 model_copy 不校验，会让活
        # core 持 dict 而快照恢复持模型——同一份 role.updated 事件在两条
        # 路径上推出不同形态（等价性门禁实测漂移点）。
        updated = RoleProfile.model_validate({**role.model_dump(mode="json"), **patch})
        self._roles[role_id] = updated
        return updated
