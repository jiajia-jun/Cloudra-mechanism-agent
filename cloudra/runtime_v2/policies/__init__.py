"""Explicit policy stage registry.

The order here is the policy order.  Harness behaviour is changed by adding or
reordering stages, never by editing the turn pipeline.
"""

from __future__ import annotations

from cloudra.runtime_v2.policies.base import PolicyStage
from cloudra.runtime_v2.policies.dag_stage import DagPolicyStage
from cloudra.runtime_v2.policies.goal_stage import GoalStage
from cloudra.runtime_v2.policies.knowledge_stage import KnowledgeStage
from cloudra.runtime_v2.policies.method_policy import MethodPolicyStage
from cloudra.runtime_v2.policies.permission import PermissionStage
from cloudra.runtime_v2.policies.schedule_stage import ScheduleStage


def default_stages(core=None) -> list[PolicyStage]:
    return [
        PermissionStage(),
        # per-project 方法白名单（GH #25）：core=None 或项目未设置
        # method_policy 时完全放行。
        MethodPolicyStage(core=core),
        DagPolicyStage(core),
        GoalStage(),
        ScheduleStage(core),
        KnowledgeStage(),
    ]
