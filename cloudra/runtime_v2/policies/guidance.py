"""Guidance stage: behavioral steering via pinned context notices.

通道纪律：操作级修正进工具结果（跟随单次调用），行为级引导进 pin 的
常驻上下文通知（跨轮/跨 run/跨重启可见；NoticeManager 按键幂等去重，
重复 pin 不产生新消息、免费去抖）。本 stage 只提示、永不阻拦——它不是
闸门，是「工作方式该调整」的提醒通道。

引导项：
- submit_compute_job 提交 TS/IRC 类作业 → ts_prepare SOP 提示（含 QST
  禁令复述）；输入文件嗅探是 fail-soft 的纯 token 扫描（调度核心链路的
  零输入解析铁律不碰：这里读的是 agent 自己提交的文件，读不出就不提示）；
- Coordinator 亲自提交正式计算 → 派单提醒（原 delegation_guard 从工具
  结果前置文案迁入）；
- bash 写文件/手写坐标 → 结构化工具提醒（原 bash_habit_guard/coord_guard
  的结果前置警告迁入）。
"""

from __future__ import annotations

import os

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall
from cloudra.tools.core.bash_habit_guard import bash_file_write_warning
from cloudra.tools.core.coord_guard import handwritten_coord_warning

_PIN_TS_SOP = "guidance-ts-sop"
_PIN_DELEGATE = "guidance-delegate-compute"
_PIN_BASH_WRITE = "guidance-bash-file-write"
_PIN_BASH_COORDS = "guidance-handwritten-coords"

_TS_NOTICE = (
    "[Guidance] This looks like a TS/IRC job. TS searches default to the "
    "ts_prepare process (build → map → assemble → guess → validate → submit → "
    "refine, autonomously; if it stops blocked, fix the named declaration and "
    "ts_resume). QST2/QST3 are banned; the ceiling is mapped interpolation/NEB, "
    "with relaxed scans as the agent-side workhorse. If you are deliberately "
    "running a manual chain, state the reason in one line in your next message."
)
_DELEGATE_NOTICE = (
    "[Guidance] You are the Coordinator submitting compute yourself. Quick "
    "checks are fine; formal or long QM jobs belong to the small_mol / dft / md "
    "sub-agents — dispatch with file paths, goals, and acceptance criteria."
)
_BASH_WRITE_NOTICE = (
    "[Guidance] bash is not for creating or editing files — use write/edit; "
    "coordinates come from smiles_to_mol / format_converter / "
    "internal_coordinates / qm_input_writer outputs, never hand-written."
)
_BASH_COORDS_NOTICE = (
    "[Guidance] Hand-written coordinate blocks in shell commands are not a "
    "structure source — use smiles_to_mol / format_converter / "
    "internal_coordinates (or ts_guess/qm_input_writer) instead."
)

# TS/IRC 路由嗅探：括号形式走子串（大小写不敏感），裸词走 token 精确比对。
_TS_ROUTE_SUBSTRINGS = ("optts", "scants", "qst2", "qst3", "opt=(ts", "opt = (ts")
_TS_ROUTE_TOKENS = frozenset({"irc"})
_SNIFF_HEAD_BYTES = 65536


def sniff_ts_or_irc_input(text: str) -> bool:
    """输入文件是否声明 TS/IRC 类作业（纯 token 扫描，非解析）。

    松弛扫描（modredundant 等）不触发——扫描是 agent 侧的正当手段，本引导
    针对的是直接 TS/IRC 提交。读不出/不含声明时返回 False（fail-soft）。
    """
    folded = text.casefold()
    if any(marker in folded for marker in _TS_ROUTE_SUBSTRINGS):
        return True
    for line in folded.splitlines():
        for raw in line.replace("=", " ").split():
            if raw.strip("!%(),;:#") in _TS_ROUTE_TOKENS:
                return True
    return False


class GuidanceStage:
    name = "guidance"

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        notices = ctx.notices
        if notices is None:
            return PolicyResult.allow()
        if call.name == "submit_compute_job":
            self._guide_submit(ctx, call, notices)
        elif call.name == "bash":
            self._guide_bash(ctx, call, notices)
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None:
        return None

    # ------------------------------------------------------------- 内部

    def _guide_submit(self, ctx: PipelineContext, call: ToolCall, notices) -> None:
        if getattr(ctx.agent, "role_id", "") == "coordinator":
            notices.pin(ctx.agent.id, key=_PIN_DELEGATE, content=_DELEGATE_NOTICE)
        input_file = str(call.arguments.get("input_file") or "")
        text = self._read_input_head(ctx, input_file)
        if text is not None and sniff_ts_or_irc_input(text):
            notices.pin(ctx.agent.id, key=_PIN_TS_SOP, content=_TS_NOTICE)

    def _guide_bash(self, ctx: PipelineContext, call: ToolCall, notices) -> None:
        command = str(call.arguments.get("command") or "")
        if not command:
            return
        if handwritten_coord_warning(command, path=None) is not None:
            notices.pin(ctx.agent.id, key=_PIN_BASH_COORDS, content=_BASH_COORDS_NOTICE)
        elif bash_file_write_warning(command) is not None:
            notices.pin(ctx.agent.id, key=_PIN_BASH_WRITE, content=_BASH_WRITE_NOTICE)

    @staticmethod
    def _read_input_head(ctx: PipelineContext, input_file: str) -> str | None:
        """读输入文件头部；相对路径同时试 workspace_dir 与进程 cwd。"""
        if not input_file:
            return None
        candidates = [input_file]
        if not os.path.isabs(input_file) and ctx.workspace_dir:
            candidates.insert(0, os.path.join(ctx.workspace_dir, input_file))
        for candidate in candidates:
            try:
                with open(candidate, encoding="utf-8", errors="replace") as fh:
                    return fh.read(_SNIFF_HEAD_BYTES)
            except OSError:
                continue
        return None
