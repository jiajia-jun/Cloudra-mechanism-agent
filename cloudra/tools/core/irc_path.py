"""IRC 路径的纯几何判定件（ts_guess strict verify 与 benchmark 评分共用唯一实现）。

严格档路径方向证明：不要求 IRC 收敛到极小值，但要求双侧带坐标端点各自
**几何上位于 TS 与对应优化中间体之间**——对 TS↔中间体距离变化最大的原子对，
端点的对距离须落在 [TS, 中间体] 区间内（带容差）且比 TS 更靠近中间体；
两端允许 direct/swapped 无序配对，任一指派成立即方向一致。
"""

from __future__ import annotations

from typing import Optional, Sequence

_STRICT_PAIR_DELTA_MIN_ANG = 0.15
_STRICT_INTERVAL_TOL_ANG = 0.10
_STRICT_MAX_AUTO_PAIRS = 5
_STRICT_PAIR_EPS_ANG = 1e-8


def parse_xyz(text: str) -> Optional[tuple[list[str], list[list[float]]]]:
    """标准 XYZ 块 → (symbols, positions)。首行原子数、次行注释、随后 N 行
    "元素 x y z"；任何一行不合格即返回 None（纯 split，不用正则）。"""
    lines = text.strip().splitlines()
    if not lines:
        return None
    try:
        n = int(lines[0].strip())
    except ValueError:
        return None
    if n <= 0 or len(lines) < n + 2:
        return None
    symbols: list[str] = []
    positions: list[list[float]] = []
    for line in lines[2:2 + n]:
        parts = line.split()
        if len(parts) < 4:
            return None
        try:
            positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
        except ValueError:
            return None
        symbols.append(parts[0])
    return symbols, positions


def pair_label(symbols, pair: tuple[int, int]) -> str:
    return f"{symbols[pair[0]]}{pair[0] + 1}-{symbols[pair[1]]}{pair[1] + 1}"


def dist_matrix(coords):
    import numpy as np

    pos = np.asarray(coords, dtype=float)
    diff = pos[:, None, :] - pos[None, :, :]
    return np.linalg.norm(diff, axis=-1)


def evaluate_endpoint_between(symbols: Sequence[str], ts_pos, end_pos,
                              intermediate_pos, watch_pairs: Sequence[Sequence[int]]) -> dict:
    """判断一个部分 IRC 端点是否位于 TS 与某个优化中间体之间。"""
    import numpy as np

    n = len(symbols)
    arrays = [np.asarray(pos, dtype=float) for pos in (ts_pos, end_pos, intermediate_pos)]
    if any(pos.shape != (n, 3) for pos in arrays):
        return {
            "is_decidable": False, "is_between": False, "score": float("inf"),
            "pairs": [], "details": ["Coordinate dimensions of TS, IRC endpoint, and intermediate do not match."],
        }

    d_ts, d_end, d_int = (dist_matrix(pos) for pos in arrays)
    pairs: list[tuple[int, int]] = []
    if watch_pairs:
        for raw_pair in watch_pairs:
            if len(raw_pair) != 2:
                return {
                    "is_decidable": False, "is_between": False, "score": float("inf"),
                    "pairs": [], "details": [f"watch_pairs entries must contain two atom indices: {raw_pair}"],
                }
            i, j = int(raw_pair[0]) - 1, int(raw_pair[1]) - 1
            if not (0 <= i < n and 0 <= j < n) or i == j:
                return {
                    "is_decidable": False, "is_between": False, "score": float("inf"),
                    "pairs": [], "details": [f"watch_pairs atom indices invalid: {raw_pair}"],
                }
            pair = (min(i, j), max(i, j))
            if pair not in pairs:
                pairs.append(pair)
        pairs = [pair for pair in pairs if abs(d_int[pair] - d_ts[pair]) > _STRICT_PAIR_EPS_ANG]
    else:
        ranked = []
        for i in range(n):
            for j in range(i + 1, n):
                delta = abs(d_int[i, j] - d_ts[i, j])
                if delta >= _STRICT_PAIR_DELTA_MIN_ANG:
                    ranked.append((delta, (i, j)))
        ranked.sort(reverse=True)
        pairs = [pair for _, pair in ranked[:_STRICT_MAX_AUTO_PAIRS]]

    if not pairs:
        return {
            "is_decidable": False, "is_between": False, "score": float("inf"),
            "pairs": [], "details": ["No atom-pair distance change between TS and intermediate is large enough to judge direction."],
        }

    q_ts = np.asarray([d_ts[pair] for pair in pairs])
    q_end = np.asarray([d_end[pair] for pair in pairs])
    q_int = np.asarray([d_int[pair] for pair in pairs])
    lower = np.minimum(q_ts, q_int) - _STRICT_INTERVAL_TOL_ANG
    upper = np.maximum(q_ts, q_int) + _STRICT_INTERVAL_TOL_ANG
    inside = (q_end >= lower) & (q_end <= upper)
    dist_ts_to_int = float(np.linalg.norm(q_ts - q_int))
    dist_end_to_int = float(np.linalg.norm(q_end - q_int))
    closer = dist_end_to_int < dist_ts_to_int
    is_between = bool(np.all(inside) and closer)
    score = dist_end_to_int / dist_ts_to_int if dist_ts_to_int > 0 else float("inf")

    details = [
        f"{pair_label(symbols, pair)}: TS={d_ts[pair]:.3f} Å, "
        f"IRC_endpoint={d_end[pair]:.3f} Å, intermediate={d_int[pair]:.3f} Å, "
        f"{'inside interval' if inside[k] else 'outside interval'}"
        for k, pair in enumerate(pairs)
    ]
    details.append(f"Distance-vector ratio endpoint-to-intermediate={score:.3f} (<1 means closer than TS).")
    return {
        "is_decidable": True,
        "is_between": is_between,
        "score": score,
        "pairs": pairs,
        "details": details,
    }


def assign_irc_endpoints(symbols: Sequence[str], ts_pos, end_a_pos, end_b_pos,
                         intermediate_a_pos, intermediate_b_pos,
                         watch_pairs: Sequence[Sequence[int]]) -> dict:
    """尝试 IRC 两端与两个优化中间体的 direct/swapped 无序配对。"""
    assignments = []
    for name, target_a, target_b in (
        ("direct", intermediate_a_pos, intermediate_b_pos),
        ("swapped", intermediate_b_pos, intermediate_a_pos),
    ):
        result_a = evaluate_endpoint_between(symbols, ts_pos, end_a_pos, target_a, watch_pairs)
        result_b = evaluate_endpoint_between(symbols, ts_pos, end_b_pos, target_b, watch_pairs)
        assignments.append({
            "name": name,
            "a": result_a,
            "b": result_b,
            "is_decidable": result_a["is_decidable"] and result_b["is_decidable"],
            "is_match": result_a["is_between"] and result_b["is_between"],
            "score": result_a["score"] + result_b["score"],
        })

    decidable = [item for item in assignments if item["is_decidable"]]
    if not decidable:
        details = assignments[0]["a"]["details"] + assignments[0]["b"]["details"]
        return {
            "is_decidable": False, "is_match": False, "assignment": "",
            "details": details,
        }

    matches = [item for item in decidable if item["is_match"]]
    chosen = min(matches or decidable, key=lambda item: item["score"])
    return {
        "is_decidable": True,
        "is_match": bool(matches),
        "assignment": chosen["name"] if matches else "",
        "details": chosen["a"]["details"] + chosen["b"]["details"],
    }
