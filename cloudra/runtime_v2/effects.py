"""decide/effect 分离的契约类型（FP 内核化 3b）。

命令处理拆成两半：

- **decide**（纯）：``decide(core, command) -> Decision``。只做守卫校验与
  载荷构造——零 IO、零 mutate、零 await 副作用。产出三样东西：
  ``events``（待落日志的事件草稿）、``effects``（待执行的副作用描述）、
  ``result``（命令结果取自哪里）。
- **shell**（``CommandBus.execute`` 固定四拍）：追加并发布/持久化事件 →
  ``apply_event`` 投影状态 → 统一执行 effects → 解析 result。

本模块只放数据类型，不依赖 runtime_v2 其它模块（schemas 反向引用
``EventDraft`` 于 ``CommandRejected.events``，不许在这里 import 回去）。

效果清单（按 commands.py 现状枚举；新增类型必须有 decide 侧产出方）：
- ``EnsureDir``：工作区目录创建（原 ``_normalize_workspace`` 内联 mkdir）。
- ``ScheduleAgent`` / ``CancelRunner``：runner 调度/取消（无 runner 时 shell
  侧跳过，decide 只表达意图）。
- ``DeliverMessage``：inbox 入队。对应的 ``agent.message_injected`` 事件由
  decide 以草稿产出、shell 在第二拍落日志——事件先于投递落地，message_id
  两处一致。
- ``PatchApiKey``：api_key 是 write-only 秘密，永不进事件/快照；活对象的
  内存覆盖补挂也是副作用，显式建模而不是藏在 decide 里 mutate。
- ``ReconcileSupervision``：编排模式迁移沿（project.update 或
  agent.settings_update 切回/切入 dag_guided）补一次督导待办通知（产出方
  ``_decide_update_project`` / ``_decide_patch_agent_settings``）。
- ``CancelLaunchGroups``：取消 agent 时级联停掉它持有的 launch group
  （产出方 ``_decide_cancel_agent``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class EventDraft:
    """一条待落日志的事件（seq/session_seq/event_id/created_at 由 EventLog 分配）。"""

    type: str
    stream: Literal["agent", "project"]
    project_id: str
    session_id: str | None = None
    run_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnsureDir:
    path: str


@dataclass(frozen=True)
class ScheduleAgent:
    session_id: str


@dataclass(frozen=True)
class CancelRunner:
    session_id: str


@dataclass(frozen=True)
class DeliverMessage:
    """inbox 入队载荷；message 形状见 ``Mailbox.message_payload``。"""

    session_id: str
    message: dict[str, Any]


@dataclass(frozen=True)
class PatchApiKey:
    """给活 agent 补挂/清除 api_key 内存覆盖（空字符串 = 清除回落全局 key）。"""

    session_id: str
    api_key: str


@dataclass(frozen=True)
class ReconcileSupervision:
    """编排模式切回 dag_guided 后的督导待办补通知（事件驱动督导 Task 4）。

    decide 只表达"该项目可能需要补一次督导通知"的意图；shell 在第四拍执行
    ``reconcile_supervision``（扫持久化待办并按状态表补通知——failed/
    cancelled 不复活、待办不清空）。effects 只在在线命令路径执行，重放/
    恢复不经过，天然满足"恢复扫描零执行副作用"。
    """

    project_id: str


@dataclass(frozen=True)
class CancelLaunchGroups:
    """取消某 agent 持有的全部 launch group（停止继续 spawn，逐项落 cancelled）。

    与 runner 任务取消同级表达：worker 任务登记在 runner 的
    ``track_background`` 里，本效果负责组级状态收敛（state=cancelled、
    queued 项不再 spawn）；已 spawn 的子 agent 由 decide 的后代级联
    （``_decide_cancel_agent``）落 cancelled 终态。
    """

    session_id: str


Effect = (
    EnsureDir
    | ScheduleAgent
    | CancelRunner
    | DeliverMessage
    | PatchApiKey
    | ReconcileSupervision
    | CancelLaunchGroups
)


@dataclass(frozen=True)
class ResultRef:
    """命令结果的引用：shell 在 apply+effects 之后从活 core 解析。

    result 必须是 apply 后的对象（含 apply_event 写入的 updated_at /
    current_run.started_at），decide 里重建一份会漂移成影子 applier；
    所以 decide 只声明"去哪里取"，状态推导依然只有 apply_event 一处。
    非 ResultRef 的 ``Decision.result`` 原样作为字面量结果。
    """

    kind: Literal["project", "agent", "role"]
    key: str


@dataclass(frozen=True)
class Decision:
    events: tuple[EventDraft, ...] = ()
    effects: tuple[Effect, ...] = ()
    result: Any = None
