"""Explicit policy stage registry.

The order here is the policy order.  Harness behaviour is changed by adding or
reordering stages, never by editing the turn pipeline.
"""

from __future__ import annotations

from cloudra.runtime_v2.policies.base import PolicyStage
from cloudra.runtime_v2.policies.dag_stage import DagPolicyStage
from cloudra.runtime_v2.policies.goal_stage import GoalStage
from cloudra.runtime_v2.policies.permission import PermissionStage


def default_stages(core=None) -> list[PolicyStage]:
    return [PermissionStage(), DagPolicyStage(core), GoalStage()]
