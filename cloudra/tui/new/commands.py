"""TUI 斜杠命令解析。

纯函数解析，便于单测。命令的执行逻辑在 MainScreen._run_command。
"""

from __future__ import annotations

# 支持的命令（用于 /help 展示与未知命令提示）
KNOWN_COMMANDS = (
    "help",
    "new",
    "list",
    "conv",
    "agents",
    "yolo",
    "mode",
    "goal",
    "compact",
    "compress",
    "context",
    "tokens",
    "dag",
    "cancel",
    "quit",
    "exit",
)

# 命令描述：输入补全与 /help 共用
COMMAND_DESCRIPTIONS = (
    ("help", "显示帮助"),
    ("new", "新建对话"),
    ("list", "列出历史对话"),
    ("conv", "切换对话（无参打开侧栏）"),
    ("agents", "打开/收起侧栏（Agent 与对话列表）"),
    ("yolo", "查看/切换自动审批模式"),
    ("mode", "查看/切换编排模式（off/record/guided）"),
    ("goal", "设置目标（/goal <目标>）；/goal pause 暂停当前任务"),
    ("compact", "压缩当前对话上下文"),
    ("context", "上下文统计"),
    ("dag", "查看/编辑 DAG 编排图"),
    ("cancel", "取消当前任务"),
    ("quit", "退出"),
)

# 别名归一化
_ALIASES = {
    "compress": "compact",
    "exit": "quit",
}


def parse_command(text: str) -> tuple[str, str] | None:
    """解析斜杠命令。

    Returns:
        (cmd, arg)；非斜杠输入返回 None。cmd 已归一化别名。
    """
    text = text.strip()
    if not text.startswith("/"):
        return None
    body = text[1:].strip()
    if not body:
        return None
    if " " in body:
        cmd, arg = body.split(" ", 1)
        arg = arg.strip()
    else:
        cmd, arg = body, ""
    cmd = cmd.lower()
    cmd = _ALIASES.get(cmd, cmd)
    return cmd, arg
