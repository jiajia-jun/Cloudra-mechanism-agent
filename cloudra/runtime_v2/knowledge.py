"""Knowledge provider plugin interface — the AgentHub library layer.

GraphRAG-style knowledge is embedded in AgentHub (the forum's "library"),
not exposed as a separate tool: registered providers are queried whenever an
agent runs ``agent_hub`` search, and their entries ride back in the same
tool result, marked with evidence levels (L0 literature / L1 verified
computation / L2 model hypothesis; falsified entries are demoted, never
deleted).

Plugin contract (deliberately minimal):

- Own your store.  The core never writes to the knowledge base — there is
  **no self-evolution**: no automatic sedimentation from DAG verdicts, hub
  posts, or run summaries.  Maintenance interfaces belong to the plugin.
- Implement ``search(query, *, limit)`` (sync or async) returning
  ``KnowledgeEntry`` objects or plain dicts with the same fields.
- Register via the general plugin mechanism in ``plugins.py``: a plugin
  object with a ``search`` hook is automatically picked up as a library
  provider (in-process ``register_plugin`` or the ``plugins`` config list).

To push findings at the agent beyond query results (passive injection at
key nodes), plugins use ``on_event`` for triggers and the CommandBus they
receive in ``setup(core)`` (``context.inject``) — or, out of process, the
``POST /api/v2/agents/{id}/context/inject`` HTTP endpoint.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

EVIDENCE_LEVELS = ("L0", "L1", "L2")
# Retrieval ranking per the validation plan: verified computation first,
# literature next, model hypotheses last; falsified sinks within its level.
_LEVEL_RANK = {"L1": 0, "L0": 1, "L2": 2}


@dataclass
class KnowledgeEntry:
    """One library hit.  ``source`` is a provenance pointer (paper, project,
    run id, artifact…) so claims stay traceable; ``falsified`` marks
    refuted entries — kept for audit but demoted."""

    title: str
    content: str
    evidence_level: str = "L0"
    source: str = ""
    falsified: bool = False
    score: float = 0.0


@runtime_checkable
class KnowledgeProvider(Protocol):
    name: str

    def search(self, query: str, *, limit: int = 5) -> list[Any]:
        """Return matching entries (KnowledgeEntry or dict).  May be async."""
        ...


_providers: list[KnowledgeProvider] = []


def register_knowledge_provider(provider: KnowledgeProvider) -> None:
    if not hasattr(provider, "search"):
        raise TypeError(f"knowledge provider {provider!r} has no search()")
    _providers.append(provider)


def clear_knowledge_providers() -> None:
    """Drop all registrations (test isolation)."""
    _providers.clear()


def registered_providers() -> tuple[KnowledgeProvider, ...]:
    return tuple(_providers)


def _normalize(raw: Any, provider_name: str) -> dict[str, Any] | None:
    if isinstance(raw, KnowledgeEntry):
        entry = {
            "title": raw.title,
            "content": raw.content,
            "evidence_level": raw.evidence_level,
            "source": raw.source,
            "falsified": raw.falsified,
            "score": raw.score,
        }
    elif isinstance(raw, dict):
        entry = {
            "title": str(raw.get("title") or ""),
            "content": str(raw.get("content") or ""),
            "evidence_level": str(raw.get("evidence_level") or "L0"),
            "source": str(raw.get("source") or ""),
            "falsified": bool(raw.get("falsified")),
            "score": float(raw.get("score") or 0.0),
        }
    else:
        return None
    if not entry["title"] and not entry["content"]:
        return None
    if entry["evidence_level"] not in EVIDENCE_LEVELS:
        entry["evidence_level"] = "L0"
    entry["provider"] = provider_name
    return entry


async def search_library(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Query every registered provider; merge, rank, and cap the hits.

    A broken provider is logged and skipped — it must never break a hub
    search.  Sync providers run in a worker thread (never block the loop).
    """
    hits: list[dict[str, Any]] = []
    for provider in list(_providers):
        name = str(getattr(provider, "name", type(provider).__name__))
        try:
            if asyncio.iscoroutinefunction(getattr(provider, "search", None)):
                raw = await provider.search(query, limit=limit)
            else:
                raw = await asyncio.to_thread(provider.search, query, limit=limit)
            if inspect.isawaitable(raw):
                raw = await raw
        except Exception:
            logger.exception("knowledge provider %s search failed", name)
            continue
        for item in raw or []:
            entry = _normalize(item, name)
            if entry is not None:
                hits.append(entry)
    hits.sort(
        key=lambda e: (
            _LEVEL_RANK.get(e["evidence_level"], 3),
            e["falsified"],
            -e["score"],
        )
    )
    return hits[:limit]


def render_library_hits(hits: list[dict[str, Any]]) -> str:
    """Render merged library hits into a compact bullet list (no header).

    Shared by the hub search result, the compute-notify broker and the
    knowledge policy stage, so one hit renders identically in every channel.
    Callers prepend their own header ("Library hits", "Knowledge base
    suggestions", …).
    """
    if not hits:
        return ""
    lines: list[str] = []
    for entry in hits:
        flag = " [FALSIFIED — refuted, kept for audit]" if entry.get("falsified") else ""
        source = f" — source: {entry['source']}" if entry.get("source") else ""
        snippet = " ".join(str(entry.get("content") or "").split())[:200]
        lines.append(
            f"- [{entry.get('evidence_level', 'L0')}]{flag} {entry.get('title') or ''}: "
            f"{snippet} (provider: {entry.get('provider', '?')}){source}"
        )
    return "\n".join(lines)
