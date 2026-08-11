"""data_dir 下所有目录/文件路径的唯一事实来源。

所有函数都是纯路径推导，不做任何 IO（不建目录、不读写文件）。
未显式传入 ``data_dir`` 参数时，在调用时（而非模块导入时）从
``get_config()`` 惰性解析数据根目录。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]


def _resolve_data_dir() -> Path:
    """从全局配置惰性解析数据根目录。"""
    from cloudra.infra.config import get_config

    return Path(get_config().data_dir)


def _root(override: Optional[PathLike]) -> Path:
    return Path(override) if override is not None else _resolve_data_dir()


def data_dir(override: Optional[PathLike] = None) -> Path:
    """返回数据根目录；未传 override 时从全局配置惰性解析。"""
    return _root(override)


def conversations_dir(data_dir: Optional[PathLike] = None) -> Path:
    return _root(data_dir) / "conversations"


def conversation_dir(conv_id: str, data_dir: Optional[PathLike] = None) -> Path:
    return conversations_dir(data_dir) / conv_id


def conversation_db_path(conv_id: str, data_dir: Optional[PathLike] = None) -> Path:
    """指定 conversation 的任务状态数据库路径。"""
    return conversation_dir(conv_id, data_dir) / "tasks" / "database.db"


def contexts_dir(conv_id: Optional[str] = None, data_dir: Optional[PathLike] = None) -> Path:
    """会话级 contexts 目录；conv_id 为空或 'default' 时回退到全局 contexts。"""
    if conv_id and conv_id != "default":
        return conversation_dir(conv_id, data_dir) / "contexts"
    return _root(data_dir) / "contexts"


def context_path(
    conv_id: Optional[str],
    agent_id: str,
    session_id: Optional[str] = None,
    data_dir: Optional[PathLike] = None,
) -> Path:
    """指定 agent 的上下文文件路径；带 session_id 时放到 contexts/sessions/ 下。"""
    base = contexts_dir(conv_id, data_dir)
    if session_id:
        return base / "sessions" / f"{agent_id}_{session_id}.json"
    return base / f"{agent_id}.json"


def session_dir(conv_id: str, data_dir: Optional[PathLike] = None) -> Path:
    """指定 conversation 的 session 执行记录目录。"""
    return conversation_dir(conv_id, data_dir) / "sessions"


def logs_dir(conv_id: Optional[str] = None, data_dir: Optional[PathLike] = None) -> Path:
    """会话级 logs 目录；conv_id 为空时返回全局 logs 目录。"""
    if conv_id:
        return conversation_dir(conv_id, data_dir) / "logs"
    return _root(data_dir) / "logs"


def memory_path(data_dir: Optional[PathLike] = None) -> Path:
    """全局长期记忆文件（MEMORY.md）路径。"""
    return _root(data_dir) / "memory" / "MEMORY.md"


def case_bank_path(data_dir: Optional[PathLike] = None) -> Path:
    """全局经验案例库（case_bank.db）路径。"""
    return _root(data_dir) / "case_bank.db"
