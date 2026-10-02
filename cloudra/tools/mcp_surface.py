"""MCP 工具面投影：把注册表声明的语义翻译成 MCP 客户端能看到的工具表。

MCP 只桥接 Tools（support resources / prompts 不在本模块范围）。本模块是 MCP
可见性的**唯一判定点**，它复用 ``cloudra.tools.capabilities`` 的同一批投影，因此
「MCP 看得到」与「进程内允许调用」不可能分歧：一个工具不可能对 MCP 可见、却在
wire 层被角色门禁拒绝。

为什么要排除一部分工具：见 ``EXCLUDED_FROM_MCP``。把宿主自带的通用工具经 MCP
再暴露一遍，会得到两套互相竞争的工具表——每次请求的 token 翻倍，而且模型无从
判断该用哪一套。

工具类按 registry 的 import path 惰性加载（registry 刻意不在 import 期导入实现，
以免可选化学依赖缺失时整张表不可用），所以**单个工具加载失败不得拖垮工具表**：
失败被收集进 ``McpSurface.unavailable`` 交给调用方报告，而不是静默吞掉。
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

from cloudra.base.tools_class import Tool, input_schema
from cloudra.tools.capabilities import (
    dag_tools,
    role_hidden_tools,
    supervisor_tool_names,
    visual_tools,
)
from cloudra.tools.registry import TOOL_REGISTRY, ToolRegistration

logger = logging.getLogger(__name__)

# 不进入 MCP 面的工具及理由。分两类：
#   1. 通用 Agent harness 几乎都自带的工具（shell / 文件读写 / 待办 / 人机提问 /
#      子代理调度 / 同伴消息）。集合刻意保守——只排除「宿主一定有」的，领域能力
#      一律保留，宁可多给模型一个工具，也不要替宿主猜它有什么。
#   2. 领域内但决定不暴露的：文献检索交给宿主的通用 web 检索。
EXCLUDED_FROM_MCP: dict[str, str] = {
    "bash": "host harness provides shell execution",
    "read": "host harness provides file reading",
    "write": "host harness provides file writing",
    "edit": "host harness provides file editing",
    "todo": "host harness provides a todo tool",
    "ask_user": "host harness provides a human-question tool",
    "stop": "host harness owns turn lifecycle",
    "get_skill": "host harness provides a skill loader",
    "goal": "host harness provides goal state",
    "schedule": "host harness provides scheduled follow-ups",
    "agent_hub": "host harness provides peer messaging and a task board",
    "subagent_launcher": "host harness provides subagent delegation",
    "subagent_swarm": "host harness provides workflow fan-out",
    "get_subagent_report": "host harness provides child status",
    "update_memory": "host harness provides persistent instructions",
    "search": "host harness provides general web search; Cloudra literature retrieval stays in-process",
    "browser": "host harness provides web retrieval; headless browsing stays in-process",
}


@dataclass(frozen=True)
class McpTool:
    """一个 MCP 工具描述符（``tools/list`` 的单条记录）。"""

    name: str
    description: str
    input_schema: dict[str, Any]

    def as_mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass(frozen=True)
class McpSurface:
    """一次 MCP 工具面快照。

    ``unavailable`` 是加载失败的工具名 -> 错误摘要。调用方必须把它报出去（日志或
    启动诊断），不能当成「工具本来就不存在」。
    """

    tools: tuple[McpTool, ...]
    unavailable: dict[str, str] = field(default_factory=dict)


def visible_tool_names(
    *,
    role_id: str | None,
    orchestration_mode: str = "standard",
    visual_mode: bool = False,
    disabled_by_config: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """角色 / 编排模式 / 视觉模式 / 配置门禁之后，MCP 客户端应当看到的工具名。

    判定顺序与 wire 层一致：先排除宿主自带，再按角色收窄，再逐项应用声明式门禁。
    ``disabled_by_config`` 由调用方传入（``capabilities.config_disabled_tools()``），
    以免本函数隐含读取全局配置、失去可测性。
    """
    named = {reg.tool_name for reg in TOOL_REGISTRY if reg.tool_name}
    visible = named - set(EXCLUDED_FROM_MCP)

    if role_id == "supervisor":
        # 督导的能力面由 supervisor_access 投影独占；role_allowlist 对它只减不增，
        # 因此两条约束取交集，而不是二选一。
        visible &= set(supervisor_tool_names())
    else:
        visible -= role_hidden_tools(role_id)

    if not visual_mode:
        visible -= visual_tools()
    if orchestration_mode == "standard":
        visible -= dag_tools()
    visible -= disabled_by_config
    return frozenset(visible)


def mcp_tools(names: frozenset[str]) -> McpSurface:
    """把工具名解析成 MCP 描述符；加载失败的工具进入 ``unavailable``。"""
    tools: list[McpTool] = []
    unavailable: dict[str, str] = {}
    for reg in TOOL_REGISTRY:
        if not reg.tool_name or reg.tool_name not in names:
            continue
        try:
            tools.append(_describe(reg))
        except Exception as error:  # noqa: BLE001 — 单工具失败不得拖垮整张工具表
            unavailable[reg.tool_name] = f"{type(error).__name__}: {error}"
            logger.warning("MCP surface: tool %s unavailable: %s", reg.tool_name, error)
    tools.sort(key=lambda tool: tool.name)
    return McpSurface(tools=tuple(tools), unavailable=unavailable)


def _describe(reg: ToolRegistration) -> McpTool:
    """加载一个工具类并产出它的 MCP 描述符。"""
    module = importlib.import_module(reg.module)
    cls = getattr(module, reg.class_name)
    if not (isinstance(cls, type) and issubclass(cls, Tool)):
        raise TypeError(f"{reg.module}.{reg.class_name} is not a Tool subclass")
    return McpTool(
        name=reg.tool_name,
        description=_description_of(cls),
        input_schema=_input_schema_of(cls),
    )


def _description_of(cls: type[Tool]) -> str:
    """工具描述。

    ``tool_schema_json()`` 是实例方法，因为部分描述在 ``__init__`` 后才能确定
    （见 ``Tool.tool_schema_json`` 的说明）。这些动态描述的工具（Bash / GetSkill）
    都不在 MCP 面内，但仍优先取实例值以保持忠实；实例化失败时退回类级默认值。
    """
    try:
        return str(cls().tool_schema_json()["function"]["description"])
    except Exception:  # noqa: BLE001 — 退化路径，失败不改变可见性
        return str(cls._get_field_default("tool_description") or "")


def _input_schema_of(cls: type[Tool]) -> dict[str, Any]:
    # Pydantic v2 的类字段默认值只能经 _get_field_default 读取（与 tools_class 同源）。
    schema_cls = cls._get_field_default("input_schema") or input_schema
    return schema_cls.to_parameters_schema()
