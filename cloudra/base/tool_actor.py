"""工具看到的调用者身份（ToolActorContext）。

工具（bash/read/write/dag_*/goal/todo/…）只需要「谁在调我」的少量信息：工作
目录、会话与项目键、权限位、编排模式。此前它们直接 import
``cloudra.core.agent`` 的 ``Agent``——那个类带 LLM 调用能力，工具因此与已下线
的执行栈耦合；字段被收窄成具体类还逼得执行器用 ``object.__setattr__`` 绕过
pydantic 校验（见 ``runtime_v2/adapters.py``）。该执行栈（``Agent``/
``Coordinator``/``Follower`` 与 ``core/message_history.py``）已随评审 5.4
删除，这里只剩工具真正需要的表面。

这里只声明**工具真正用到**的表面。生产实现是 ``runtime_v2.adapters`` 里包
``AgentSession`` 的那个对象；测试可用任意鸭子类型对象。

刻意不声明的字段：``agent_id`` 等 DAG 库里的历史 id（工具用
``getattr(..., default)`` 兜底读取，属于迁移边界，不是新工具参数的首选身份）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cloudra.tools.core.permission_model import Permission


@runtime_checkable
class ToolActorContext(Protocol):
    """调用方 Agent 暴露给工具的只读身份（不含任何执行能力）。"""

    #: 会话 id（v2 为 ``as_*``；历史数据可能是旧的 a-N 组合 id）。
    id: str
    #: 调用者显示名；v2 下即 role_id（``coordinator`` / ``small_mol`` / …）。
    name: str
    #: 调用者类型：``coordinator`` / ``supervisor`` / ``follower``（DAG actor 判据）。
    type: str
    #: 会话键（v2 = project_id）：todos/goal 等 per-agent 存储的分区键。
    conversation_id: str
    #: 工具解析相对路径的根目录（绝不回落进程 cwd）。
    working_directory: str
    #: 编排模式字符串（standard / dag_record / dag_guided）。
    orchestration_mode: str
    #: 会话 id 别名；同角色并行实例（swarm）据此隔离各自的 todos/goal。
    session_id: str

    def permission_all(self) -> "Permission":
        """调用者的权限位（IntFlag 投影，供 bash 等工具判定命令类别）。"""
        ...
