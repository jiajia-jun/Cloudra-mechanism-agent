"""回放计量汇总（计划 2026-09-13-harness-cache-continuity Task 6）。

读 scripts/replay_cache_probe.py 产出的逐请求 JSON，按计划的固定公式计算：

    token_weighted_hit_rate = sum(cached_input_tokens) / sum(input_tokens)
    uncached_input_tokens = sum(input_tokens - cached_input_tokens)
    prefix_mutations = count(non_boundary_request_with_changed_old_prefix)

边界（冷启动，不计入 prefix_mutations，单列）：首请求、真实 compact 后的
首个主请求、模型/工具协议变化的请求。usage 缺缓存字段的请求记
missing_usage，不进入任何分母（验收 8：不记 0）。主流程（stream=True）与
摘要/汇总请求（stream=False）分开统计。

用法：
    uv run python scripts/analyze_cache_probe.py /tmp/probe_g1_old.json ...
输出：机器可读 JSON 汇总（打印到 stdout）。
"""

from __future__ import annotations

import json
import statistics
import sys


def _usage_fields(usage: dict | None) -> tuple[int | None, int | None]:
    """(input_tokens, cached_input_tokens)；缺字段返回 None（不记 0）。"""
    if not usage:
        return None, None
    input_tokens = usage.get("prompt_tokens")
    if input_tokens is None:
        input_tokens = usage.get("input_tokens")
    cached = usage.get("prompt_cache_hit_tokens")
    if cached is None:
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    if cached is None:
        cached = (usage.get("input_tokens_details") or {}).get("cached_tokens")
    return input_tokens, cached


def _analyze_capture(capture: dict) -> dict:
    requests = capture["requests"]
    # 展开：marker 行只承担边界/步序信息；compact 边界标记作用于其后首个
    # **主请求**（中间隔着 compact 的 SYNC 摘要调用，不能吃掉边界标记）。
    entries = []
    pending_compact = False
    for entry in requests:
        if "marker" in entry:
            if entry["marker"] == "compact":
                pending_compact = True
            continue
        if entry["stream"]:
            entries.append((entry, pending_compact))
            pending_compact = False
        else:
            entries.append((entry, False))

    mains = [(e, post_compact) for e, post_compact in entries if e["stream"]]
    summaries = [e for e, _ in entries if not e["stream"]]

    # 前缀连续性：相邻主请求对；边界 = 全局首请求 / compact 后首请求 /
    # 模型或工具协议变化。
    mutations = []
    boundaries = []
    for index in range(1, len(mains)):
        prev, _ = mains[index - 1]
        cur, post_compact = mains[index]
        reason = None
        if post_compact:
            reason = "post_compact"
        elif cur["tools_hash"] != prev["tools_hash"]:
            reason = "tools_changed"
        elif cur.get("model") != prev.get("model"):
            reason = "model_changed"
        if reason is not None:
            boundaries.append({"pair": [index - 1, index], "reason": reason})
            continue
        prev_hashes = prev["message_hashes"]
        cur_hashes = cur["message_hashes"]
        common = min(len(prev_hashes), len(cur_hashes))
        divergence = None
        for i in range(common):
            if prev_hashes[i] != cur_hashes[i]:
                divergence = i
                break
        if divergence is None and len(prev_hashes) > len(cur_hashes):
            divergence = common
        if divergence is not None:
            mutations.append(
                {
                    "pair": [index - 1, index],
                    "first_divergence": divergence,
                    "prev_role": prev["message_roles"][divergence]
                    if divergence < len(prev["message_roles"])
                    else "<end>",
                }
            )

    def totals(rows):
        input_sum = cached_sum = missing = 0
        for entry, _post in rows:
            input_tokens, cached = _usage_fields(entry.get("usage"))
            if input_tokens is None or cached is None:
                missing += 1
                continue
            input_sum += input_tokens
            cached_sum += cached
        return {
            "requests": len(rows),
            "input_tokens": input_sum,
            "cached_input_tokens": cached_sum,
            "uncached_input_tokens": input_sum - cached_sum,
            "missing_usage": missing,
            "hit_rate": (cached_sum / input_sum) if input_sum else None,
        }

    boundary_indexes = {b["pair"][1] for b in boundaries}
    boundary_indexes.add(0)
    stable = [row for i, row in enumerate(mains) if i not in boundary_indexes]

    ttfts = [e["ttft_s"] for e, _ in mains if e.get("ttft_s") is not None]
    summary_input = summary_output = summary_missing = 0
    for entry in summaries:
        usage = entry.get("usage")
        if not usage:
            summary_missing += 1
            continue
        input_tokens, _ = _usage_fields(usage)
        summary_input += input_tokens or 0
        summary_output += usage.get("completion_tokens") or usage.get("output_tokens") or 0

    return {
        "version": capture["version"],
        "module": capture.get("cloudra_module"),
        "overall": totals(mains),
        "stable_interval": totals(stable),
        "boundary_count": len(boundary_indexes),
        "prefix_mutations": len(mutations),
        "mutation_details": mutations,
        "summary_calls": len(summaries),
        "summary_input_tokens": summary_input,
        "summary_output_tokens": summary_output,
        "summary_missing_usage": summary_missing,
        "ttft_s": {
            "n": len(ttfts),
            "mean": round(statistics.mean(ttfts), 3) if ttfts else None,
            "min": min(ttfts) if ttfts else None,
            "max": max(ttfts) if ttfts else None,
        },
    }


def main() -> None:
    per_capture = []
    for path in sys.argv[1:]:
        per_capture.append(_analyze_capture(json.load(open(path))))

    # 分组：每 version 的多次独立重复 → 均值/波动
    by_version: dict[str, list[dict]] = {}
    for result in per_capture:
        by_version.setdefault(result["version"], []).append(result)

    groups = {}
    for version, rows in by_version.items():
        hit_rates = [r["overall"]["hit_rate"] for r in rows if r["overall"]["hit_rate"] is not None]
        stable_rates = [
            r["stable_interval"]["hit_rate"]
            for r in rows
            if r["stable_interval"]["hit_rate"] is not None
        ]
        groups[version] = {
            "groups": len(rows),
            "overall_hit_rates": [round(r, 4) for r in hit_rates],
            "overall_hit_rate_mean": round(statistics.mean(hit_rates), 4) if hit_rates else None,
            "overall_hit_rate_stdev": (
                round(statistics.stdev(hit_rates), 4) if len(hit_rates) > 1 else 0.0
            ),
            "stable_hit_rate_mean": (
                round(statistics.mean(stable_rates), 4) if stable_rates else None
            ),
            "input_tokens": sum(r["overall"]["input_tokens"] for r in rows),
            "cached_input_tokens": sum(r["overall"]["cached_input_tokens"] for r in rows),
            "uncached_input_tokens": sum(r["overall"]["uncached_input_tokens"] for r in rows),
            "missing_usage": sum(r["overall"]["missing_usage"] for r in rows),
            "prefix_mutations": sum(r["prefix_mutations"] for r in rows),
            "summary_calls": sum(r["summary_calls"] for r in rows),
            "summary_input_tokens": sum(r["summary_input_tokens"] for r in rows),
            "summary_output_tokens": sum(r["summary_output_tokens"] for r in rows),
            "summary_missing_usage": sum(r["summary_missing_usage"] for r in rows),
            "ttft_mean_s": round(
                statistics.mean(
                    r["ttft_s"]["mean"] for r in rows if r["ttft_s"]["mean"] is not None
                ),
                3,
            ),
            "ttft_max_s": max(
                (r["ttft_s"]["max"] for r in rows if r["ttft_s"]["max"] is not None),
                default=None,
            ),
        }

    print(json.dumps({"groups": groups, "per_capture": per_capture}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
