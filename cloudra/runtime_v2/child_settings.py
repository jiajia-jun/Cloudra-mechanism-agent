"""子 Agent 的设置继承（评审 5.5）：唯一解析点 + 显式字段分类。

派发（`agent.spawn`）只继承**任务授权与运行边界**——父 agent 代用户授权的
东西（yolo / unattended / schedule / 编排模式 / 干净上下文）。模型、采样参数、
调用协议、视觉模式等属于「由 child 的 role 与项目默认决定」的字段：child 在
`AgentHost.effective_settings` 里按 **project defaults → role defaults → spawn
override** 解析，不随父漂移。秘密字段（`api_key`）永不继承：child 的 key 由
桥接层从 config 槽位补全。

字段清单是代码契约：`tests/test_child_settings.py` 用 `RuntimeSettingsPatch` 的
字段集合做全量覆盖断言——以后新增设置字段必须在此归类，否则测试失败（避免
「新字段悄悄跟着父继承」这类静默行为变化）。

派发回执里的 `receipt` 是非敏感的**有效设置摘要**（含每个字段的来源），用来
回答「child 为什么用这个 model / protocol」；`api_key` 与 `base_url` 永不出现在
回执里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cloudra.runtime_v2.schemas import (
    AgentSession,
    Project,
    RoleProfile,
    RuntimeSettingsPatch,
)

#: 继承父 agent：任务授权与运行边界（父代用户授权的一部分）。
INHERITED_FIELDS: tuple[str, ...] = (
    "orchestration_mode",
    "yolo",
    "unattended",
    "schedule_mode",
    "clean_context",
)

#: 由 child 的 role / 项目默认决定：模型、采样、协议、视觉。
ROLE_DEFAULTED_FIELDS: tuple[str, ...] = (
    "model",
    "base_url",
    "temperature",
    "max_tokens",
    "context_window",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "timeout",
    "reasoning_effort",
    "native_search",
    "native_search_params",
    "invocation_protocol",
    "visual_mode",
)

#: 绝不继承：写only 秘密与端点（child 由桥接层从 config 槽位补全）。
NEVER_INHERITED_FIELDS: tuple[str, ...] = ("api_key",)

SOURCE_INHERITED = "inherited_from_parent"
SOURCE_OVERRIDE = "dispatch_override"
SOURCE_ROLE = "role_default"
SOURCE_PROJECT = "project_default"
SOURCE_SCHEMA = "schema_default"


@dataclass(frozen=True)
class ChildSettingsPlan:
    """一次派发的设置计划：要提交的补丁 + 每个字段的来源。"""

    patch: RuntimeSettingsPatch
    sources: dict[str, str] = field(default_factory=dict)

    def spawn_payload_settings(self) -> dict[str, Any]:
        """`agent.spawn` 的 settings 载荷（JSON 安全：枚举落字符串）。"""
        return self.patch.model_dump(mode="json", exclude_unset=True)

    def receipt(self, child: AgentSession) -> dict[str, Any]:
        """派发回执：child 的**有效**设置摘要 + 来源（非敏感）。"""
        settings = child.settings
        return {
            "session_id": child.id,
            "role_id": child.role_id,
            "model": settings.model,
            "invocation_protocol": settings.invocation_protocol.value,
            "orchestration_mode": settings.orchestration_mode.value,
            "unattended": settings.unattended,
            "visual_mode": settings.visual_mode,
            "yolo": settings.yolo,
            "schedule_mode": settings.schedule_mode,
            "clean_context": settings.clean_context,
            "sources": dict(self.sources),
        }


def resolve_child_settings(
    parent: AgentSession,
    *,
    project: Project,
    role: RoleProfile,
    override: RuntimeSettingsPatch | None = None,
) -> ChildSettingsPlan:
    """child 设置唯一解析点：返回要提交的补丁与逐字段来源。

    ``override`` 是派发方显式给出的设置（目前只有 Supervisor 固定 guided 这类
    系统注入走得到），它同时决定 ROLE_DEFAULTED 字段的来源标注。
    """
    inherited = {name: getattr(parent.settings, name) for name in INHERITED_FIELDS}
    sources = dict.fromkeys(INHERITED_FIELDS, SOURCE_INHERITED)
    for name in ROLE_DEFAULTED_FIELDS + NEVER_INHERITED_FIELDS:
        # 来源按「谁真正给了值」判定：patch 里的 None 是 unset（项目默认补丁
        # 会把全部字段填成 None），不能当成显式设置。
        sources[name] = _value_source(
            name, override=override, role=role, project=project
        )
    return ChildSettingsPlan(patch=RuntimeSettingsPatch(**inherited), sources=sources)


def _value_source(
    name: str,
    *,
    override: RuntimeSettingsPatch | None,
    role: RoleProfile,
    project: Project,
) -> str:
    """字段来源：派发覆盖 > 角色默认 > 项目默认 > schema 默认（None 一律不算设置）。"""
    if override is not None and getattr(override, name, None) is not None:
        return SOURCE_OVERRIDE
    if getattr(role.default_settings, name, None) is not None:
        return SOURCE_ROLE
    if getattr(project.settings.defaults, name, None) is not None:
        return SOURCE_PROJECT
    return SOURCE_SCHEMA
