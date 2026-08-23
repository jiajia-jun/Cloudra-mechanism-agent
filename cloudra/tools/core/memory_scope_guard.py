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

import re

# POSIX 绝对路径（至少两段：/home/user/x、/data/proj/job.gjf）。
_POSIX_PATH_RE = re.compile(r"/(?:[^\s/]+/)+[^\s/]+")
# Windows 盘符路径（C:\...、D:\...）。
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s]+")
# 作业号特征：job/slurm/pid/task 等词后紧跟 5 位以上数字（job 12345678）。
_JOB_ID_RE = re.compile(r"(?:job(?:\s*id)?|slurm|pid|task)\s*#?\s*:?\s*\d{5,}", re.IGNORECASE)


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
    for pattern in (_POSIX_PATH_RE, _WINDOWS_PATH_RE, _JOB_ID_RE):
        for match in pattern.finditer(text):
            fragment = match.group(0)
            if fragment not in fragments:
                fragments.append(fragment)
    return fragments
