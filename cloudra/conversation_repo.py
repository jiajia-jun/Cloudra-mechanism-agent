"""会话（Conversation）查询的唯一入口。

只读模块：扫描 conversations 目录、解析 meta.json、读取会话消息，
供 service / CLI / email_listener 等调用方共用，避免多处手写目录扫描。
所有路径均通过 cloudra.paths 推导。
"""

from __future__ import annotations

import json
from typing import Optional

from cloudra import paths
from cloudra.paths import PathLike

# email_listener 的唤醒语义：只有这些状态的会话可以被选中继续任务
ACTIVE_STATES = ("running", "sleeping", "active")


def list_conversations(data_dir: Optional[PathLike] = None) -> list[dict]:
    """扫描 conversations 目录，返回按 last_active 倒序排列的 meta 列表。

    跳过缺少 meta.json 或 meta 损坏的目录；meta 缺 id 时以目录名补齐。
    """
    root = paths.conversations_dir(data_dir)
    result = []
    for entry in root.iterdir() if root.exists() else []:
        meta_path = entry / "meta.json"
        if not entry.is_dir() or not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta, dict):
            continue
        meta.setdefault("id", entry.name)
        result.append(meta)
    return sorted(result, key=lambda item: item.get("last_active", ""), reverse=True)


def latest_active_conversation(data_dir: Optional[PathLike] = None) -> Optional[str]:
    """返回最近一次活跃且非归档的会话 id，优先使用配置中的 last_conversation_id。"""
    from cloudra.config import get_config

    cfg = get_config()
    if cfg.last_conversation_id:
        return cfg.last_conversation_id
    candidates = [
        (meta.get("last_active", ""), meta["id"])
        for meta in list_conversations(data_dir)
        if meta.get("state") in ACTIVE_STATES
    ]
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    return None


def conversation_messages(
    conv_id: str,
    data_dir: Optional[PathLike] = None,
    agent_id: str = "a-0",
) -> list[dict]:
    """读取会话主上下文（默认 Coordinator a-0）的消息列表；文件不存在时返回空列表。"""
    path = paths.conversation_dir(conv_id, data_dir) / "contexts" / f"{agent_id}.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("会话消息文件格式错误")
    return data
