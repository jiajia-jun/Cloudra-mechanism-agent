"""Memory 范围守卫：拦截写进全局 MEMORY.md 的项目特定内容。

MEMORY.md 是全局长期记忆，会注入**所有项目**的 Coordinator system prompt；
项目特定内容（本项目的绝对路径、工作区位置、Slurm job ID 等）写进去会
污染其他项目的上下文。与 bash_habit_guard 的软警告不同，这里由
update_memory 工具在写入前调用并**硬拦**：命中时返回 is_success=False，
要求模型用项目无关的通用措辞重写——改写后可逆，污染不可逆。

只认硬信号（误伤代价是模型重写一次，可接受；漏检代价是跨项目污染，
不可接受），有意不做语义级"项目相关"判定。
"""

from __future__ import annotations

_PATH_BOUNDARIES = frozenset("([{<\"'`=:,;，。；：！？")
_PATH_ENDINGS = frozenset(")]}>\"'`,;，。；：！？")
_JOB_LABELS = frozenset({"job", "jobid", "job_id", "slurm", "pid", "task"})


def _path_fragments(text: str) -> list[str]:
    """Recognize absolute path tokens, rather than slashes inside URLs or relative paths."""
    fragments: list[str] = []
    index = 0
    while index < len(text):
        previous = text[index - 1] if index else ""
        boundary = (index == 0 or previous.isspace() or previous in _PATH_BOUNDARIES
                    or "\u3400" <= previous <= "\u9fff" or text[max(0, index - 7):index] == "file://")
        posix = text[index] == "/" and not text.startswith("//", index)
        drive = (text[index].isascii() and text[index].isalpha() and text[index + 1:index + 3] == ":\\")
        if not boundary or not (posix or drive):
            index += 1
            continue
        end = index + 1
        while end < len(text) and not text[end].isspace() and text[end] not in _PATH_ENDINGS:
            end += 1
        fragment = text[index:end].rstrip(".!?:")
        if drive or len([part for part in fragment.split("/") if part]) >= 2:
            fragments.append(fragment)
        index = end
    return fragments


def _job_fragments(text: str) -> list[str]:
    """Match explicit job labels followed by numeric identifier tokens (at least five digits)."""
    tokens: list[tuple[str, int, int]] = []
    index = 0
    while index < len(text):
        if not (text[index].isascii() and (text[index].isalnum() or text[index] == "_")):
            index += 1
            continue
        start = index
        while index < len(text) and text[index].isascii() and (text[index].isalnum() or text[index] == "_"):
            index += 1
        tokens.append((text[start:index].casefold(), start, index))
    fragments: list[str] = []
    for index, (word, start, end) in enumerate(tokens):
        attached_number = next((word[len(label):] for label in _JOB_LABELS
                                if word.startswith(label) and word[len(label):].isdigit()), "")
        if len(attached_number) >= 5:
            fragments.append(text[start:end])
            continue
        if word not in _JOB_LABELS:
            continue
        next_index = index + 1
        if word == "job" and next_index < len(tokens) and tokens[next_index][0] == "id":
            if not text[end:tokens[next_index][1]].isspace():
                continue
            end = tokens[next_index][2]
            next_index += 1
        if next_index >= len(tokens):
            continue
        number, number_start, number_end = tokens[next_index]
        separator = text[end:number_start]
        if len(number) >= 5 and number.isascii() and number.isdigit() and all(
            char.isspace() or char in "#:=_"
            for char in separator
        ):
            fragments.append(text[start:number_end])
    return fragments


def _data_dir() -> str:
    """配置的数据目录绝对路径；未配置/异常时返回空串（不参与匹配）。"""
    try:
        from cloudra.infra.config import get_config

        return str(get_config().data_dir or "")
    except Exception:
        return ""


def find_project_specific_fragments(text: str) -> list[str]:
    """返回 text 中命中的项目特定片段；空列表表示可以安全写入全局记忆。"""
    if not text:
        return []
    fragments: list[str] = []
    data_dir = _data_dir()
    if data_dir and data_dir in text:
        fragments.append(data_dir)
    for fragment in _path_fragments(text) + _job_fragments(text):
        if fragment not in fragments:
            fragments.append(fragment)
    return fragments
