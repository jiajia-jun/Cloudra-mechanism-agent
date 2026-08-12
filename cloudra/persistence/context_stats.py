"""对话级上下文统计（只读）。

供 TUI 状态栏与 /context 使用：按 agent/session 分列，用 tiktoken 精确计数
持久化消息。不会创建或改写上下文文件（避免 ContextManager.load 在缺文件时
初始化空上下文的副作用）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from cloudra.infra.token_estimator import TokenEstimator
from cloudra.persistence import paths
from cloudra.persistence.context_manager import (
    COMPACT_SUMMARY_MARKER,
    SKILL_PIN_MARKER,
    read_context_file,
)


@dataclass(frozen=True, slots=True)
class RoleStats:
    messages: int = 0
    tokens: int = 0


@dataclass(frozen=True, slots=True)
class AgentContextStats:
    """单个上下文文件的统计。"""

    agent_id: str
    session_id: Optional[str]
    path: str
    scope: str  # conversation | session
    label: str
    messages: int
    tokens: int
    by_role: dict[str, RoleStats] = field(default_factory=dict)
    skill_pin_tokens: int = 0
    compact_summary_tokens: int = 0
    file_bytes: int = 0
    exists: bool = True

    @property
    def key(self) -> str:
        if self.session_id:
            return f"{self.agent_id}/{self.session_id}"
        return self.agent_id


@dataclass(frozen=True, slots=True)
class ConversationContextStats:
    conversation_id: str
    agents: tuple[AgentContextStats, ...]
    total_messages: int
    total_tokens: int


def _label_for(agent_id: str, session_id: Optional[str], agent_type: Optional[str] = None) -> str:
    if agent_id == "a-0":
        return "Coordinator"
    if agent_id == "supervisor":
        return "Supervisor"
    if agent_type:
        return f"{agent_type} ({agent_id})"
    if session_id:
        return f"Follower ({agent_id})"
    return agent_id


def _role_messages(messages: Iterable[dict]) -> list[dict]:
    return [m for m in messages if isinstance(m, dict) and m.get("role")]


def summarize_messages(messages: list[dict]) -> tuple[int, int, dict[str, RoleStats], int, int]:
    """返回 (msg_count, tokens, by_role, skill_pin_tokens, compact_summary_tokens)。

    ``tokens`` 与 ``TokenEstimator.count_messages`` 对齐（含 reply priming）。
    ``by_role`` 为各 role 的 ``count_message`` 之和（不含 priming）。
    """
    ordered = _role_messages(messages)
    by_role: dict[str, RoleStats] = {}
    skill_pin_tokens = 0
    compact_tokens = 0
    for msg in ordered:
        role = str(msg.get("role") or "?")
        msg_tokens = TokenEstimator.count_message(msg)
        prev = by_role.get(role) or RoleStats()
        by_role[role] = RoleStats(messages=prev.messages + 1, tokens=prev.tokens + msg_tokens)
        content = str(msg.get("content") or "")
        if content.startswith(SKILL_PIN_MARKER):
            skill_pin_tokens += msg_tokens
        if content.startswith(COMPACT_SUMMARY_MARKER):
            compact_tokens += msg_tokens
    total_tokens = TokenEstimator.count_messages(ordered) if ordered else 0
    return len(ordered), total_tokens, by_role, skill_pin_tokens, compact_tokens


def _stats_for_file(
    *,
    agent_id: str,
    session_id: Optional[str],
    path: Path,
    agent_type: Optional[str] = None,
) -> AgentContextStats:
    scope = "session" if session_id else "conversation"
    label = _label_for(agent_id, session_id, agent_type)
    if not path.is_file():
        return AgentContextStats(
            agent_id=agent_id,
            session_id=session_id,
            path=str(path),
            scope=scope,
            label=label,
            messages=0,
            tokens=0,
            exists=False,
        )
    try:
        messages = read_context_file(str(path))
    except Exception:
        return AgentContextStats(
            agent_id=agent_id,
            session_id=session_id,
            path=str(path),
            scope=scope,
            label=label,
            messages=0,
            tokens=0,
            file_bytes=path.stat().st_size,
            exists=True,
        )
    n_msg, tokens, by_role, skill_tok, compact_tok = summarize_messages(messages)
    return AgentContextStats(
        agent_id=agent_id,
        session_id=session_id,
        path=str(path),
        scope=scope,
        label=label,
        messages=n_msg,
        tokens=tokens,
        by_role=by_role,
        skill_pin_tokens=skill_tok,
        compact_summary_tokens=compact_tok,
        file_bytes=path.stat().st_size,
        exists=True,
    )


def _parse_session_filename(stem: str, known: dict[str, tuple[str, Optional[str]]]) -> tuple[str, Optional[str]]:
    """把 sessions/{agent_id}_{session_id}.json 的 stem 解析回 (agent_id, session_id)。"""
    if stem in known:
        return known[stem]
    # session_id 常以 agent_id 开头（如 a-4 + a-4_task1 → a-4_a-4_task1）
    for agent_id, session_id in known.values():
        if session_id and stem == f"{agent_id}_{session_id}":
            return agent_id, session_id
    # 回退：按第一个 '_' 切开（agent_id 一般为 a-N / supervisor）
    if "_" in stem:
        agent_id, session_id = stem.split("_", 1)
        return agent_id, session_id
    return stem, None


def collect_conversation_context_stats(
    conversation_id: str,
    *,
    session_records: Optional[Iterable[Any]] = None,
    data_dir: Optional[Path | str] = None,
) -> ConversationContextStats:
    """扫描对话下全部上下文文件并统计。

    ``session_records`` 可选（SessionRecord 或 duck-type），用于正确拆分
    ``{agent_id}_{session_id}.json`` 与补全 agent_type 标签。
    """
    base = paths.contexts_dir(conversation_id, data_dir)
    known_files: dict[str, tuple[str, Optional[str]]] = {}
    type_by_agent: dict[str, str] = {}
    expected: list[tuple[str, Optional[str], Optional[str]]] = []

    if session_records is not None:
        for rec in session_records:
            agent_id = getattr(rec, "agent_id", None) or "a-0"
            session_id = getattr(rec, "session_id", None)
            agent_type = getattr(rec, "agent_type", None)
            if agent_type:
                type_by_agent[agent_id] = str(agent_type)
            # Coordinator / Supervisor：对话级文件，不按 session 隔离
            if agent_id in ("a-0", "supervisor"):
                expected.append((agent_id, None, agent_type))
            elif session_id:
                known_files[f"{agent_id}_{session_id}"] = (agent_id, session_id)
                expected.append((agent_id, session_id, agent_type))

    # 始终纳入对话级 a-0 / supervisor（即使尚无 session 记录）
    for agent_id in ("a-0", "supervisor"):
        if not any(a == agent_id and s is None for a, s, _ in expected):
            expected.append((agent_id, None, type_by_agent.get(agent_id)))

    seen: set[str] = set()
    agents: list[AgentContextStats] = []

    def _add(agent_id: str, session_id: Optional[str], agent_type: Optional[str] = None) -> None:
        key = f"{agent_id}\0{session_id or ''}"
        if key in seen:
            return
        seen.add(key)
        path = paths.context_path(conversation_id, agent_id, session_id, data_dir)
        # 对话级文件不存在则跳过（避免空 supervisor 占一行）；a-0 始终显示
        if session_id is None and agent_id != "a-0" and not path.is_file():
            return
        if session_id is not None and not path.is_file():
            return
        agents.append(
            _stats_for_file(
                agent_id=agent_id,
                session_id=session_id,
                path=path,
                agent_type=agent_type or type_by_agent.get(agent_id),
            )
        )

    for agent_id, session_id, agent_type in expected:
        _add(agent_id, session_id, agent_type)

    # 扫盘补漏（孤儿上下文 / 无 DB 记录）
    if base.is_dir():
        for path in sorted(base.glob("*.json")):
            _add(path.stem, None, type_by_agent.get(path.stem))
        sessions_dir = base / "sessions"
        if sessions_dir.is_dir():
            for path in sorted(sessions_dir.glob("*.json")):
                agent_id, session_id = _parse_session_filename(path.stem, known_files)
                _add(agent_id, session_id, type_by_agent.get(agent_id))

    # 排序：Coordinator → Supervisor → 其余按 key
    def _sort_key(item: AgentContextStats) -> tuple:
        if item.agent_id == "a-0" and item.session_id is None:
            return (0, "", "")
        if item.agent_id == "supervisor" and item.session_id is None:
            return (1, "", "")
        return (2, item.agent_id, item.session_id or "")

    agents_sorted = tuple(sorted(agents, key=_sort_key))
    return ConversationContextStats(
        conversation_id=conversation_id,
        agents=agents_sorted,
        total_messages=sum(a.messages for a in agents_sorted),
        total_tokens=sum(a.tokens for a in agents_sorted),
    )


def format_token_count(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def format_status_bar_context_info(stats: ConversationContextStats) -> str:
    """状态栏短摘要：主上下文 + 路数合计。"""
    if not stats.agents:
        return "空"
    primary = next((a for a in stats.agents if a.agent_id == "a-0" and a.session_id is None), stats.agents[0])
    n_agents = len(stats.agents)
    if n_agents == 1:
        return (
            f"{primary.label} {primary.messages}条/{format_token_count(primary.tokens)}"
        )
    return (
        f"{primary.label} {primary.messages}条/{format_token_count(primary.tokens)}"
        f" · {n_agents}路Σ{format_token_count(stats.total_tokens)}"
    )


def format_context_report(
    stats: ConversationContextStats,
    *,
    focus_key: Optional[str] = None,
    include_previews: bool = True,
    preview_limit: int = 40,
) -> str:
    """/context 页面正文。"""
    lines = [
        f"对话: {stats.conversation_id}",
        f"合计: {len(stats.agents)} 路上下文 · {stats.total_messages} 条消息 · "
        f"{format_token_count(stats.total_tokens)} tokens（tiktoken，持久化消息）",
        "说明: 不含请求时附带的 tools schema / 动态拼装的 system 段；"
        "Skill 钉住资料计入对应 agent 的 system。",
        "",
        f"{'Agent':<14} {'范围':<12} {'消息':>6} {'Tokens':>8} {'Skill钉':>8} 角色细分",
        "-" * 78,
    ]
    for agent in stats.agents:
        role_bits = ", ".join(
            f"{role}:{rs.messages}/{format_token_count(rs.tokens)}"
            for role, rs in sorted(agent.by_role.items())
        ) or "—"
        scope = "对话级" if agent.scope == "conversation" else "任务级"
        marker = "▶" if focus_key and agent.key == focus_key else " "
        name = agent.agent_id if agent.session_id is None else f"{agent.agent_id}@{agent.session_id[-16:]}"
        lines.append(
            f"{marker}{name:<13} {scope:<12} {agent.messages:>6} "
            f"{format_token_count(agent.tokens):>8} "
            f"{format_token_count(agent.skill_pin_tokens):>8} {role_bits}"
        )

    focus = None
    if focus_key:
        focus = next((a for a in stats.agents if a.key == focus_key), None)
    if focus is None and stats.agents:
        focus = stats.agents[0]

    if focus is not None and include_previews:
        lines.extend(["", f"--- {focus.label} · {focus.key} 消息预览 ---"])
        try:
            messages = read_context_file(focus.path) if focus.exists else []
        except Exception as exc:
            lines.append(f"（无法读取: {exc}）")
            messages = []
        shown = 0
        for i, msg in enumerate(messages, 1):
            if not isinstance(msg, dict) or not msg.get("role"):
                continue
            shown += 1
            if shown > preview_limit:
                lines.append(f"… 仅显示前 {preview_limit} 条 role 消息")
                break
            tok = TokenEstimator.count_message(msg)
            preview = _preview(msg.get("content"))
            lines.append(f"{i}. [{msg.get('role')}] ({format_token_count(tok)}) {preview}")

    return "\n".join(lines)


def _preview(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
                elif part.get("type") == "image_url":
                    parts.append("[图片]")
            else:
                parts.append(str(part))
        text = " ".join(parts)
    else:
        text = str(content)
    text = text.replace("\n", " ")
    return text[:120] + ("…" if len(text) > 120 else "")
