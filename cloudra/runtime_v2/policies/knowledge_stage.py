"""Knowledge injection stage: auto-retrieve the chem-kb library after compute tools.

Every time a compute tool (a tool that launches computation or parses
computational results, per the ``dag_compute_entry`` /
``dag_evidence_producer`` semantics in the tool registry) finishes, this
stage queries the registered knowledge providers and pushes the hits back as a one-shot notice
(``notices.push``), so the next LLM turn carries relevant troubleshooting /
interpretation guidance without the agent having to remember ``agent_hub``
search.

v13 查询与注入策略：

- 查询不再是"工具名+全部参数+summary 全文"的 800 字符 blob——blob 进 FTS
  全 token AND 与模糊层子串 AND 命中率≈0（图谱/模糊通道实际死亡），还稀释
  向量编码。改为工具名 + 短参数 + summary 的报错窗口（≤200 字符）。
- 注入分级：``is_success=False`` 必注入（排障价值最高）；成功仅当 top 命中
  分 ≥ ``_SUCCESS_SCORE_THRESHOLD`` 才注入——压掉"每次计算都注入"的上下文
  噪声（验证计划"被动提示仅在关键节点触发"原则）。

This is a pure pull-into-context trigger, not a gate: retrieval failures or an
empty library (no plugin installed, no hits) are silent no-ops that never
affect the turn.  The stage is stateless and restart-safe — every injection is
derived from the turn inputs plus the knowledge provider registry.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall, ToolResult

logger = logging.getLogger(__name__)

_QUERY_MAX_CHARS = 200
_HIT_LIMIT = 3
# 成功路径的注入门槛：跨通道分数只是近似（bm25 归一/余弦/子串不同量纲），
# 该值是"宁缺勿滥"的经验折中——低于它的成功注入几乎必然是噪声。
_SUCCESS_SCORE_THRESHOLD = 0.55
_ERROR_WINDOW = 160  # 报错命中点附近截取的上下文窗口

# 报错/诊断信号：中英文失败词 + Gaussian Link 错误码（L####）
_ERROR_MARKERS = re.compile(
    r"(error|fail(?:ed|ure)?|converg\w*|erroneous|exception|segfault|L\d{4}"
    r"|不收敛|失败|报错|错误|虚频|异常)",
    re.IGNORECASE,
)


def is_compute_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    """Whether a tool launches computation or parses computational results.

    Reuses the registry's existing semantics (no per-tool name set kept here):
    ``dag_compute_entry`` marks "starts compute / writes compute inputs",
    ``dag_evidence_producer`` marks "finished call yields computational
    evidence".
    """
    from cloudra.tools.capabilities import is_dag_compute_entry, is_dag_evidence_producer

    return is_dag_compute_entry(tool_name, arguments) or is_dag_evidence_producer(tool_name)


def _informative_arg(value: str) -> bool:
    """短且非纯数字的参数才算信号：SMILES/方法名/短路径保留，长串与数字丢弃。"""
    v = value.strip()
    if not v or len(v) > 120:
        return False
    if re.fullmatch(r"-?\d+(\.\d+)?", v):
        return False
    return True


def _error_window(summary: str) -> str:
    """summary 里的报错命中点 ± 上下文窗口；无报错信号返回空串。"""
    m = _ERROR_MARKERS.search(summary)
    if not m:
        return ""
    start = max(0, m.start() - _ERROR_WINDOW // 4)
    return summary[start : m.end() + _ERROR_WINDOW * 3 // 4].strip()


def build_knowledge_query(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    summary: str = "",
) -> str:
    """Pure decision: tool turn → library query string (v13 短查询).

    旧版拼"工具名+全部参数+summary 全文"成 ≤800 字符 blob——FTS 全 token
    AND 与模糊层子串 AND 对 blob 的命中率≈0（图谱/模糊通道实际死亡），向量
    编码也被 JSON 噪声稀释。现改为：工具名 + 短参数（SMILES/方法名/短路径，
    >120 字符与纯数字丢弃）+ summary 的报错窗口；总体仍截 200 字符。
    """
    parts = [tool_name]
    for value in (arguments or {}).values():
        if isinstance(value, str) and _informative_arg(value):
            parts.append(value.strip())
    if summary:
        window = _error_window(summary)
        if window:
            parts.append(window)
    return " ".join(parts)[:_QUERY_MAX_CHARS].strip()


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
        # v13 注入分级：失败必注入（排障价值最高，且 fail_reason 类查询本身
        # 短而准）；成功仅当 top 分过阈值——压掉"每次计算都注入"的噪声。
        if result.is_success:
            top = max(float(h.get("score") or 0.0) for h in hits)
            if top < _SUCCESS_SCORE_THRESHOLD:
                return
        notices.push(
            ctx.agent.id,
            f"[Knowledge] Suggestions from the chem-kb library for `{call.name}`:\n"
            f"{render_library_hits(hits)}",
        )

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None:
        return None
