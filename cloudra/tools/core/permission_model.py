"""
Permission Model for Cloudra Tools.

Replaces the fragile list[bool] permission system with a robust IntFlag-based model.
"""

from enum import IntFlag

from pydantic import BaseModel, ConfigDict


class PermissionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read: bool = True
    write: bool = False
    manage: bool = False
    script: bool = False
    destructive: bool = False


class Permission(IntFlag):
    """Bit-flag permissions for tools and agents."""
    NONE = 0
    READ = 1
    WRITE = 2
    MANAGE = 4
    SCRIPT = 8
    DESTRUCTIVE = 16

    # Common composites
    ALL = READ | WRITE | MANAGE | SCRIPT | DESTRUCTIVE


def check_permission(agent_perms: Permission, tool_perms: Permission) -> bool:
    """
    Check if an agent has sufficient permissions for a tool.

    Logic: tool_perms must be a subset of agent_perms.
    i.e. every bit set in tool_perms must also be set in agent_perms.
    """
    if tool_perms == Permission.NONE:
        return True
    return (tool_perms & agent_perms) == tool_perms


def permission_to_dict(perms: Permission) -> dict[str, bool]:
    """Convert Permission flags to a human-readable dict."""
    return {
        'is_read': bool(perms & Permission.READ),
        'is_write': bool(perms & Permission.WRITE),
        'is_manage': bool(perms & Permission.MANAGE),
        'is_script': bool(perms & Permission.SCRIPT),
        'is_destructive': bool(perms & Permission.DESTRUCTIVE),
    }
