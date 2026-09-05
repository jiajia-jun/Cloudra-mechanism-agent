"""Knowledge injection stage: auto-retrieve the chem-kb library after compute tools.

Every time a compute tool (a tool that launches computation or parses
computational results, per the ``dag_compute_entry`` /
``dag_evidence_producer`` semantics in the tool registry) finishes, this
stage queries the registered
knowledge providers and pushes the hits back as a one-shot notice
(``notices.push``), so the next LLM turn carries relevant troubleshooting /
interpretation guidance without the agent having to remember ``agent_hub``
search.

This is a pure pull-into-context trigger, not a gate: retrieval failures or an
empty library (no plugin installed, no hits) are silent no-ops that never
affect the turn.  The stage is stateless and restart-safe — every injection is
derived from the turn inputs plus the knowledge provider registry.
"""

from __future__ import annotations

import logging
from typing import Any

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall, ToolResult

logger = logging.getLogger(__name__)

_QUERY_MAX_CHARS = 800
_HIT_LIMIT = 3


def is_compute_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    """Whether a tool launches computation or parses computational results.

    Reuses the registry's existing semantics (no per-tool name set kept here):
    ``dag_compute_entry`` marks "starts compute / writes compute inputs",
    ``dag_evidence_producer`` marks "finished call yields computational
    evidence".
    """
    from cloudra.tools.capabilities import is_dag_compute_entry, is_dag_evidence_producer

    return is_dag_compute_entry(tool_name, arguments) or is_dag_evidence_producer(tool_name)


def build_knowledge_query(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    summary: str = "",
) -> str:
    """Pure decision: tool turn → library query string.

    The tool name seeds the query; string argument values (SMILES, method
    names, paths) and the result summary (which carries failure markers on
    error) extend it.  Capped so an oversized summary/payload can't balloon
    the FTS/vector query.
    """
    parts = [tool_name]
    for value in (arguments or {}).values():
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    if summary and summary.strip():
        parts.append(summary.strip())
    return " ".join(parts)[:_QUERY_MAX_CHARS]


class KnowledgeStage:
    """Auto-retrieve the chem-kb library after a compute tool finishes."""

    name = "knowledge"

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None:
        if not is_compute_tool(call.name, call.arguments):
            return
        notices = getattr(ctx, "notices", None)
        if notices is None:
            return
        try:
            from cloudra.runtime_v2.knowledge import render_library_hits, search_library

            query = build_knowledge_query(call.name, call.arguments, result.summary)
            hits = await search_library(query, limit=_HIT_LIMIT)
        except Exception:
            logger.exception("knowledge stage retrieval failed for tool %s", call.name)
            return
        if not hits:
            return
        notices.push(
            ctx.agent.id,
            f"[Knowledge] Suggestions from the chem-kb library for `{call.name}`:\n"
            f"{render_library_hits(hits)}",
        )

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None:
        return None
