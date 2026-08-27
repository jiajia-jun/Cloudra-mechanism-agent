"""JSONL-backed LLM message history (Supervisor + Agent.llm_call diagnostics path)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from cloudra.persistence import paths
from cloudra.persistence.fs_utils import atomic_write_jsonl

SUPERVISOR_ADVICE_MARKER = "[Supervisor]"


def parse_context_text(text: str) -> tuple[list, bool]:
    """Parse JSONL blocks or a legacy single JSON array."""
    stripped = text.lstrip()
    if not stripped:
        return [], False
    if stripped.startswith("["):
        return json.loads(text), True
    blocks: list = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            blocks.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return blocks, False


def read_context_file(path: str) -> list:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as stream:
        blocks, _legacy = parse_context_text(stream.read())
    return blocks


def repair_tool_pairing(messages: list[dict]) -> list[dict]:
    declared: set[str] = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            call_id = call.get("id") if isinstance(call, dict) else None
            if call_id:
                declared.add(call_id)

    answered = {
        msg.get("tool_call_id")
        for msg in messages
        if msg.get("role") == "tool" and msg.get("tool_call_id")
    }

    repaired: list[dict] = []
    pending: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            call_id = msg.get("tool_call_id")
            if call_id and call_id not in declared:
                continue
            repaired.append(msg)
            continue
        repaired.extend(pending)
        pending.clear()
        repaired.append(msg)
        if role != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            call_id = call.get("id") if isinstance(call, dict) else None
            if call_id and call_id not in answered:
                pending.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": "[Missing tool result: may have been lost during context compact]",
                    }
                )
                answered.add(call_id)
    repaired.extend(pending)
    return repaired


def build_llm_messages(
    *,
    history: list[dict],
    identity_messages: list[dict],
) -> list[dict]:
    messages = [dict(message) for message in identity_messages] + list(history)
    cleaned: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "assistant" and not content and not msg.get("tool_calls"):
            continue
        if role == "user" and isinstance(content, str) and not content.strip():
            continue
        cleaned.append(msg)
    return repair_tool_pairing(cleaned)


class JsonlMessageHistory:
    """Append-only conversation history stored as JSONL on disk."""

    def __init__(
        self,
        *,
        conversation_id: str,
        agent_id: str,
        session_id: str | None = None,
        initial_query: str = "",
        context_file: str | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.agent_id = agent_id
        self.session_id = session_id
        self.initial_query = initial_query
        self.context_file = context_file or str(
            paths.context_path(conversation_id, agent_id, session_id)
        )
        os.makedirs(os.path.dirname(self.context_file), exist_ok=True)
        self._cache: list[dict] | None = None
        self._legacy = False

    @classmethod
    def for_supervisor(cls, conversation_id: str) -> JsonlMessageHistory:
        return cls(
            conversation_id=conversation_id,
            agent_id="supervisor",
            session_id=None,
            initial_query="",
        )

    @staticmethod
    def _is_legacy_identity(context: list) -> bool:
        if len(context) < 2:
            return False
        first, second = context[0], context[1]
        if first.get("role") != "system" or second.get("role") != "user":
            return False
        content = first.get("content", "")
        if not isinstance(content, str):
            return False
        return not content.startswith(
            (SUPERVISOR_ADVICE_MARKER, "[Context compact]", "[Skill material]")
        )

    async def load(self) -> list[dict]:
        if self._cache is not None:
            return list(self._cache)
        if os.path.isfile(self.context_file):
            blocks, legacy = await asyncio.to_thread(self._read_file)
            self._legacy = legacy
            if self._is_legacy_identity(blocks):
                blocks = blocks[1:]
                await self.replace(blocks)
            self._cache = blocks
            return list(blocks)
        initial = (
            [{"role": "user", "content": self.initial_query}]
            if self.initial_query
            else []
        )
        self._cache = initial
        if initial:
            await self.replace(initial)
        return list(initial)

    def _read_file(self) -> tuple[list, bool]:
        with open(self.context_file, encoding="utf-8") as stream:
            return parse_context_text(stream.read())

    async def replace(self, context: list[dict]) -> None:
        self._cache = list(context)
        self._legacy = False
        await asyncio.to_thread(atomic_write_jsonl, self.context_file, context)

    async def append(self, block: dict) -> None:
        item = dict(block)
        item.setdefault("role", "user")
        if "content" not in item:
            item["content"] = str(item)
        context = await self.load()
        context.append(item)
        if self._legacy or not os.path.isfile(self.context_file):
            await self.replace(context)
            return

        def append_line() -> None:
            line = json.dumps(item, ensure_ascii=False) + "\n"
            with open(self.context_file, "r+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() > 0:
                    handle.seek(-1, os.SEEK_END)
                    if handle.read(1) != b"\n":
                        handle.write(b"\n")
                handle.write(line.encode("utf-8"))

        await asyncio.to_thread(append_line)
        self._cache = context

    async def clear(self) -> None:
        await self.replace([])

    async def build_messages(
        self,
        *,
        identity_messages: list[dict],
        supports_vision: bool = False,
        max_context_tokens: Optional[int] = None,
    ) -> list[dict]:
        del supports_vision, max_context_tokens
        history = await self.load()
        return build_llm_messages(history=history, identity_messages=identity_messages)
