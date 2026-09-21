"""端到端压缩烟测：真实 LLM 调用（读当前 config 槽位的 key）。

手工运行，不进 pytest 套件（testpaths=tests，本文件位于 scripts/）：

    python -X utf8 scripts/smoke_compaction.py            # 全流程
    python -X utf8 scripts/smoke_compaction.py --probe    # 只探摘要调用一步

覆盖真实故障面（GH #40/#45 线程）：
1. 摘要调用本身——模型返回什么、结构化校验是否通过、异常的真实类型
   （线上 segment_failed 的 error='' 把异常类型吞了，这里用 repr 还原）；
2. compact_context 全流程——分段/合并/拒替换的真实 reason；
3. kind=summary 的 llm.completed 事件数据必须 JSON 可序列化（#46 的实弹回归）。

退出码：0 = 全过；1 = 有失败项（stdout 有 [FAIL] 明细）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloudra.infra.config import get_config  # noqa: E402
from cloudra.runtime_v2.compaction import (  # noqa: E402
    compact_context,
    parse_compact_summary,
    summarize_with_agent_settings,
)
from cloudra.runtime_v2.events import EventLog  # noqa: E402
from cloudra.runtime_v2.schemas import AgentSession  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def record(ok: bool, label: str) -> None:
    RESULTS.append((ok, label))
    print(("[PASS] " if ok else "[FAIL] ") + label)


def _config_summary() -> dict:
    cfg = get_config()
    slot = cfg.coordinator
    return {
        "model": slot.model,
        "url": slot.url,
        "timeout": slot.timeout,
        "key_set": bool(slot.key),
    }


def _smoke_agent() -> AgentSession:
    return AgentSession(
        id="as_smoke_compaction",
        project_id="prj_smoke_compaction",
        role_id="coordinator",
        display_name="compaction smoke",
    )


def _trajectory() -> list[dict]:
    """小型但真实形态的轨迹：指令区 + 多轮工具往返 + 近期尾部。"""
    messages: list[dict] = [
        {"role": "user", "content": "请计算乙醛羟醛缩合反应的机理与能垒，逐边给出 TS 证据。"},
    ]
    for i in range(6):
        messages.append(
            {
                "role": "assistant",
                "content": f"正在进行第 {i + 1} 步构象搜索与 TS 猜测，"
                f"使用 interpolate 方案生成初始 guesses 并提交 OptTS 作业，"
                f"等待频率与 IRC 验证结果后回填能垒（步骤 {i + 1}/6）。",
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": (
                    f"[ts_guess] step {i + 1}: generated 4 guesses from reactant/product xyz; "
                    f"scan along C-C distance shows maximum at 2.11 A; "
                    f"submitted orca job calc-{100 + i}; awaiting NumFreq."
                )
                * 3,
            }
        )
    messages.append({"role": "user", "content": "继续下一步，并把已完成的边写回 gold。"})
    return messages


async def probe_summary_call(agent: AgentSession) -> str | None:
    """单探摘要调用：返回模型原文；失败时打印异常真实类型（线上 error='' 的还原）。"""
    payload = (
        "Summarize this trajectory into the required JSON with the nine keys "
        "(objective/active_requests/corrections/constraints/pending/completed/"
        "failed_attempts/evidence/next_actions). Each entry cites sources as "
        "trajectory message indexes.\n\n[0] user: 计算乙醛羟醛缩合机理\n"
        "[1] assistant: 构象搜索与 TS 猜测\n[2] tool: ts_guess generated 4 guesses\n"
        "[3] user: 继续并回填 gold\n"
    )
    try:
        raw = await summarize_with_agent_settings(
            agent, [{"role": "user", "content": payload}], event_log=None
        )
    except Exception as exc:  # noqa: BLE001 —— 烟测要把异常原样暴露
        print(f"      summary call raised: {type(exc).__module__}.{type(exc).__name__}: "
              f"str={str(exc)!r} repr={exc!r}")
        record(False, "摘要调用本身成功（异常类型见上）")
        return None
    preview = (raw or "")[:160].replace("\n", "\\n")
    print(f"      raw reply ({len(raw or '')} chars): {preview!r}")
    record(bool(raw), "摘要调用返回非空文本")
    try:
        summary = parse_compact_summary(raw, trajectory_len=4)
        record(True, "结构化校验通过（九键 + 来源下标在界内）")
        print(f"      objective: {summary.objective.text[:80]!r} "
              f"clamped={summary.clamped_sources}")
    except Exception as exc:  # noqa: BLE001
        record(False, f"结构化校验通过（{type(exc).__name__}: {str(exc)[:120]}）")
    return raw


async def run_full_flow(agent: AgentSession, context_window: int, timeout: int) -> None:
    log = EventLog(strict=False)
    messages = _trajectory()
    try:
        new_context, stats = await compact_context(
            messages,
            head=[],
            notices=[],
            summarize=lambda _msgs: summarize_with_agent_settings(
                agent, _msgs, event_log=log, run_id="smoke"
            ),
            context_window=context_window,
            max_output=32768,
            trigger="manual",
            summary_timeout=float(timeout),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"      compact_context raised: {type(exc).__name__}: {exc!r}")
        record(False, "compact_context 全流程完成")
        return
    compacted = bool(stats.get("compacted"))
    print(f"      stats: {json.dumps({k: v for k, v in stats.items() if k != 'segments'}, ensure_ascii=False)[:400]}")
    record(compacted, f"压缩完成并替换（reason={stats.get('reason', 'n/a')}）")
    if compacted:
        shrink = len(messages) - len(new_context)
        record(shrink > 0, f"新上下文更短（{len(messages)} → {len(new_context)} 条）")

    # #46 实弹回归：kind=summary 的 llm.completed 事件必须 JSON 可序列化
    events = [e for e in log.query_session(agent.id) if e.type == "llm.completed"]
    record(bool(events), "落了 kind=summary 的 llm.completed 遥测事件")
    for e in events:
        try:
            json.dumps(e.data)
            record(True, f"事件数据 JSON 可序列化（seq={e.seq}）")
        except TypeError as exc:
            record(False, f"事件数据 JSON 可序列化（seq={e.seq}: {exc}）")

    _ = timeout  # 仅供显示；实际超时由 config 槽位带进 LLMClient


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="只探摘要调用，不跑全流程")
    args = parser.parse_args()

    info = _config_summary()
    print(f"config: model={info['model']} url={info['url']} "
          f"timeout={info['timeout']} key_set={info['key_set']}")
    if not info["key_set"]:
        record(False, "config 槽位有 key（当前为空，无法真实调用）")
        return 1

    agent = _smoke_agent()
    if args.probe:
        await probe_summary_call(agent)
    else:
        raw = await probe_summary_call(agent)
        if raw is not None:
            await run_full_flow(agent, context_window=1_310_720, timeout=info["timeout"] or 300)

    failed = [label for ok, label in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} 项通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
