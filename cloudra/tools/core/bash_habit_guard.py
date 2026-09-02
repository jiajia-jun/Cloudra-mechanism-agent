"""Bash 习惯守卫：检测 agent 用 bash 完成本该走结构化工具的工作（软警告）。

背景：长上下文后期模型判断力下降，习惯性退回 bash——用 cat/echo/tee/heredoc
键入文件内容、sed -i 原地改文件、直接命令行调用量化程序，绕开 write /
edit / submit_compute_job 等结构化工具。这些行为绕过文件变更审批、产物
记录与 DAG 证据链；prompt 层已明令禁止（bash 描述"严禁用 Bash、sed、
重定向、tee 或临时脚本改文件"），但长上下文下仍然复发，这里在 harness 层
检测并**在工具结果里附警告**（照常执行，不硬拦）——让模型读到"这是绕开
结构化工具/DAG 系统"的明确信号后自行纠正，而不是逼它换更隐蔽的路径。

与 coord_guard 的关系：coord_guard 专管"坐标块嵌入写入内容"（命中面窄、
误伤风险低、直接点破 supervisor 审查），本模块管更宽泛的"bash 习惯"。
"""

from __future__ import annotations

import re
import shlex

from .command_analyzer import BashCommandClassifier

# 写操作重定向符（可带数字 fd：2>、3>>；`2>&1` 这类 fd 重定向不匹配，见
# _is_real_file_target 的 fd 判定）。
_REDIRECT_RE = re.compile(r"^\d*(?:>>|>|&>|&>>|<>)$")
# heredoc 起始符：`<<`、`<<-`、`<<EOF`、`<<'EOF'`（shlex 可能拆成独立 token
# 也可能粘连成单个 token）。
_HEREDOC_RE = re.compile(r"^<<-?")
# 向文件"键入内容"的命令：echo / printf 本身以打印内容为目的。
_CONTENT_WRITE_CMDS = frozenset({"echo", "printf", "print"})

# 直接调用、且存在结构化替代的量化程序（submit_compute_job / conformer_search /
# electronic_analysis 等）。is_substantive_bash_command（DAG compute-entry 判定）
# 据此识别绕过结构化工具的直调。
_COMPUTE_PROGRAMS = frozenset({
    "g03", "g09", "g16", "gaussian",
    "orca", "cp2k", "vasp", "vasp_std", "vasp_gam", "nwchem",
    "xtb", "crest", "mopac", "gamess", "psi4", "qchem", "molpro",
})

_FILE_WRITE_GUIDANCE = (
    "You are using bash to write/edit workspace files (redirect / heredoc / tee / in-place edit), which bypasses "
    "write / edit file-change approval, artifact recording, and the DAG evidence chain. Use "
    "read + edit for existing files and write for new files; do not use bash to bypass these "
    "structured tools, and do not try to bypass the DAG system."
)


def _tokenize(command: str) -> list[str]:
    """尽力把命令拆成 token；shlex 失败时退化为空白分词。"""
    try:
        return shlex.split(command, comments=False, posix=True)
    except ValueError:
        return command.split()


def _redirect_targets(tokens: list[str]) -> list[str]:
    """返回重定向符后面的目标 token 列表（`> file` 取 `file`）。"""
    targets = []
    for i, tok in enumerate(tokens):
        if _REDIRECT_RE.fullmatch(tok) and i + 1 < len(tokens):
            targets.append(tokens[i + 1])
    return targets


def _is_real_file_target(target: str) -> bool:
    """过滤 fd / 系统设备目标：/dev/null、2>&1 后的 fd、/proc 等不算文件写入。"""
    if not target:
        return False
    if target.startswith(("/dev/", "/proc/", "/sys/")):
        return False
    if target.isdigit():
        return False
    return True


def _primary_word(tokens: list[str]) -> str:
    """返回命令中的主命令（跳过开头的变量赋值与重定向符）。"""
    for tok in tokens:
        if _REDIRECT_RE.fullmatch(tok):
            continue
        if "=" in tok and tok.index("=") > 0 and tok[: tok.index("=")].isidentifier():
            continue
        return tok
    return ""


def _is_inplace_edit(tokens: list[str]) -> bool:
    """sed -i / awk -i inplace / perl -pi 这类原地编辑。"""
    for i, tok in enumerate(tokens):
        if tok in {"sed", "awk", "perl"}:
            flags = tokens[i + 1 :]
            if tok == "sed" and any(re.fullmatch(r"-[a-zA-Z]*i[a-zA-Z]*", f) for f in flags):
                return True
            if tok == "awk":
                for j, f in enumerate(flags):
                    if f == "-i" and j + 1 < len(flags) and flags[j + 1] == "inplace":
                        return True
            if tok == "perl" and any(f.startswith("-") and "i" in f[1:] for f in flags):
                return True
    return False


def _is_content_write(tokens: list[str]) -> bool:
    """向文件"键入内容"：heredoc 写文件、echo/printf 重定向、tee 写文件、
    裸重定向建/清空文件。刻意不拦 `python x.py > out.log` 这类输出捕获。"""
    if not tokens:
        return False
    has_heredoc = any(_HEREDOC_RE.match(tok) for tok in tokens)
    targets = [t for t in _redirect_targets(tokens) if _is_real_file_target(t)]
    primary = _primary_word(tokens)

    if has_heredoc and targets:
        return True
    if primary in _CONTENT_WRITE_CMDS and targets:
        return True
    # tee 出现在管道任意位置、且带真实文件操作数（单独 `tee` 只写 stdout）。
    for i, tok in enumerate(tokens):
        if tok != "tee":
            continue
        for nxt in tokens[i + 1 :]:
            if _REDIRECT_RE.fullmatch(nxt) or nxt in ("|", "|&", "||", "&&", ";"):
                break
            if nxt.startswith("-"):
                continue
            if _is_real_file_target(nxt):
                return True
    if _REDIRECT_RE.fullmatch(tokens[0]) and _is_real_file_target(
        tokens[1] if len(tokens) > 1 else ""
    ):
        return True
    return False


def bash_file_write_warning(command: str) -> str | None:
    """检测 bash 命令是否在向工作区文件键入内容或原地编辑。

    命中返回警告消息（调用方照常执行命令，把警告附在结果里），无命中返回 None。
    """
    tokens = _tokenize(command)
    if not tokens:
        return None
    if _is_inplace_edit(tokens) or _is_content_write(tokens):
        return f"[Warning: suspected bash habit] {_FILE_WRITE_GUIDANCE}"
    return None


def _direct_compute_program(command: str) -> str | None:
    """返回命令主流程中直接调用的量化程序名（无则 None）。"""
    try:
        analysis = BashCommandClassifier.classify(command)
    except Exception:
        return None
    for cmd in analysis.pipe_commands:
        lowered = cmd.lower()
        if lowered in _COMPUTE_PROGRAMS:
            return lowered
    return None


def is_substantive_bash_command(arguments: dict) -> bool:
    """DAG-gate predicate for the bash registration.

    True when a bash call writes/edits workspace files or directly invokes a
    compute program, i.e. the same signals the habit guard watches for.
    """
    command = str((arguments or {}).get("command") or "").strip()
    if not command:
        return False
    return bool(bash_file_write_warning(command)) or bool(_direct_compute_program(command))
