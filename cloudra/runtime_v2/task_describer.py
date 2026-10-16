"""Dynamic agent running task description generator.

Triggers an out-of-band LLM call whenever:
1. A user sends a message to an agent (sender == "user").
2. A parent agent spawns or sends a message/query to a subagent (agent.parent_session_id is not None).

Generates a crisp, concise, active running description (under 15 Chinese chars or 8 English words)
matching the current language environment and updates `current_task` via `agent.task_updated`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional

from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.schemas import AgentSession, EventEnvelope

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

logger = logging.getLogger(__name__)

# Non-task system notifications that should NOT trigger a new task description.
_SYSTEM_NOTICE_SENDERS = {
    "completion_gate",
    "background_quiescence",
    "reminder",
    "compute_notify",
    "email_listener",
}


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _extractive_fallback(instruction: str, language: str) -> str:
    cleaned = " ".join(instruction.strip().split())
    if not cleaned:
        return "执行任务" if language == "zh" else "Executing task"
    if language == "zh":
        if len(cleaned) > 10:
            cleaned = cleaned[:9] + "…"
        return f"正在执行: {cleaned}" if not cleaned.startswith("正在") else cleaned
    else:
        words = cleaned.split()
        if len(words) > 6:
            cleaned = " ".join(words[:6]) + "…"
        return f"Working on: {cleaned}"


async def generate_task_description(
    agent: AgentSession,
    instruction: str,
    language: Optional[str] = None,
) -> str:
    """Generate a crisp active description using the agent's LLM configuration."""
    target_lang = "zh" if (language == "zh" or (not language and _has_chinese(instruction))) else "en"

    from cloudra.infra.codex_auth import is_codex_url
    from cloudra.infra.llm_client import LLMClient
    from cloudra.runtime_v2.adapters import legacy_default_settings

    settings = legacy_default_settings(agent)
    if not settings.model or (not settings.api_key and not is_codex_url(settings.base_url)):
        return _extractive_fallback(instruction, target_lang)

    if target_lang == "zh":
        system_prompt = (
            "你是一个计算化学科研 Agent 系统的任务描述生成器。\n"
            "请根据输入的新任务或消息，用一句话生成该 Agent 正在进行的清晰、简短的运行描述。\n"
            "要求：\n"
            "1. 严格使用简体中文输出。\n"
            "2. 动词或进行时开头，描述正在做什么（例如：正在优化反应物构型、检索过渡态结构、计算虚频与振动方向、分析反应路径能垒等）。\n"
            "3. 极其简练，严禁超过 15 个汉字。\n"
            "4. 严禁包含标点符号、引号、括号、前缀或多余解释，只输出描述短语本身。"
        )
    else:
        system_prompt = (
            "You are a concise task summarizer for a computational chemistry AI agent.\n"
            "Based on the incoming message or task, generate a single short active phrase describing what this agent is currently working on.\n"
            "Requirements:\n"
            "1. Strictly output in English.\n"
            "2. Start with an active verb or participle (e.g., Optimizing reactant conformers, Searching TS structures, Calculating harmonic frequencies, Analyzing reaction barriers).\n"
            "3. Keep it extremely brief (under 8 words).\n"
            "4. Do NOT output quotes, punctuation, prefixes or extra text. Output ONLY the phrase."
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction[:500]},
    ]

    client = LLMClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=min(settings.timeout or 15, 15),
    )
    try:
        kwargs: dict[str, Any] = {
            "model": settings.model,
            "messages": messages,
            "temperature": 0.3,
            "stream": False,
        }
        if settings.reasoning_effort:
            kwargs["reasoning_effort"] = settings.reasoning_effort

        response = await client.create_with_retry(**kwargs)
        raw_text = (response.choices[0].message.content or "").strip()
        cleaned = raw_text.strip("\"'`").split("\n")[0].strip()
        if cleaned:
            return cleaned
    except Exception as exc:
        logger.warning("task description generation failed, using fallback: %s", exc)
    finally:
        await client.aclose()

    return _extractive_fallback(instruction, target_lang)


class TaskDescriber:
    """Observer listening to event hub to generate dynamic task descriptions."""

    def __init__(self, core: "RuntimeCore") -> None:
        self.core = core
        self._active_tasks: dict[asyncio.Task, str] = {}
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._started = True
            self.core.event_hub.subscribe(self._on_event)

    def close(self) -> None:
        if self._started:
            self._started = False
            self.core.event_hub.unsubscribe(self._on_event)
        for t in list(self._active_tasks):
            t.cancel()
        self._active_tasks.clear()

    def prune_sessions(self, session_ids: set[str]) -> None:
        """Stop descriptions that can no longer update an existing session."""
        for task, session_id in list(self._active_tasks.items()):
            if session_id not in session_ids:
                task.cancel()
                self._active_tasks.pop(task)

    async def _on_event(self, envelope: EventEnvelope) -> None:
        if envelope.type != "agent.message_injected":
            return

        session_id = envelope.session_id
        if not session_id:
            return

        agent = self.core.agents.get(session_id)
        if agent is None:
            return

        data = envelope.data or {}
        sender = str(data.get("sender") or "")
        content = str(data.get("content") or "").strip()
        if not content:
            return

        # Ignore non-task system notices and child completion reports
        if sender in _SYSTEM_NOTICE_SENDERS:
            return
        manifest = data.get("manifest") or {}
        if manifest.get("kind") in {"child_report", "background_quiescence"}:
            return

        # Check triggers:
        # 1. User message (sender == 'user' or actor == 'user')
        # 2. Parent-to-subagent message / spawn query (agent.parent_session_id is not None)
        # 3. Initial instruction to a root agent
        is_user_msg = sender == "user" or data.get("actor") == "user"
        is_subagent_msg = agent.parent_session_id is not None
        is_initial_root = (not agent.parent_session_id) and (agent.current_task is None)

        if not (is_user_msg or is_subagent_msg or is_initial_root):
            return

        language = data.get("language")
        task = asyncio.create_task(self._process_task_update(agent, content, language))
        self._active_tasks[task] = session_id
        task.add_done_callback(lambda done: self._active_tasks.pop(done, None))

    async def _process_task_update(
        self, agent: AgentSession, instruction: str, language: Optional[str]
    ) -> None:
        try:
            desc = await generate_task_description(agent, instruction, language)
            if not desc:
                return

            draft = EventDraft(
                type="agent.task_updated",
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=agent.current_run.run_id if agent.current_run else None,
                data={"current_task": desc, "instruction": instruction[:200]},
            )
            await self.core.event_writer.commit_and_apply(
                [draft], lambda envelope: apply_event(self.core, envelope),
            )

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("failed to apply task description for %s: %s", agent.id, exc)
