"""虚频模式组成摘要：把简正模式位移投影到原子对方向上（纯函数，不发起计算）。

供 log_parser 与 TS 管线在频率数值之外给出「这条虚频主要是哪些原子在动」的组成
信息；位移与几何由调用方从引擎日志文本解析（gaussian_frames / orca_frames
的文本权威通道），本模块只做投影与占比汇总。numpy 在函数内惰性导入。
"""

from __future__ import annotations

from typing import Optional, Sequence

_TOP_PAIRS = 5
# 重原子判定：H/D 以外一律算重原子（质量加权不在此做，口径与 irc_path 一致只看元素）
_LIGHT_SYMBOLS = {"H", "D"}


def imaginary_mode_summary(
    frequencies_cm: Sequence[float],
    vibdisps,
    positions,
    symbols: Optional[Sequence[str]],
    watch_pairs: Optional[Sequence[Sequence[int]]] = None,
) -> Optional[list[dict]]:
    """对每条负频模式给出组成摘要；位移或几何缺失/形状不符时返回 None。

    - frequencies_cm：有符号频率（负值=虚频），顺序与 vibdisps 的模式轴一致；
    - vibdisps：(n_modes, n_atoms, 3) 简正模式位移；
    - positions：(n_atoms, 3) 当前几何（Å）；
    - symbols：元素符号（判重原子：H/D 以外）；
    - watch_pairs：1-based 原子对；给定时每条模式附带 watch_pair_fraction
      （各监视对投影占总对投影和的比例 + 逐对投影），未给时该字段为 None。

    每条模式产出：
    - frequency_cm：负值原样；
    - top_displaced_pairs：前 5 个原子对 [i, j, score]（1-based），
      score = 位移差在该对键方向上的投影 |(u_i−u_j)·r̂_ij|（r̂ 为当前几何
      i→j 单位矢量）；
    - top_displaced_atoms：前 5 个原子的编号、元素与 Σ|u|² 占比；
    - heavy_atom_fraction：重原子的 Σ|u|² 占比；
    - watch_atom_fraction：监视对包含的去重原子的 Σ|u|² 占比。
    以上均不加质量权重，仅描述原始模式的运动组成，不自行判定反应模式合格。
    """
    import numpy as np

    if vibdisps is None or positions is None or symbols is None:
        return None
    disps = np.asarray(vibdisps, dtype=float)
    pos = np.asarray(positions, dtype=float)
    freqs = [float(f) for f in frequencies_cm]
    if disps.ndim != 3 or disps.shape[2] != 3 or pos.ndim != 2 or pos.shape[1] != 3:
        return None
    n_modes, n_atoms = disps.shape[0], disps.shape[1]
    if n_atoms == 0 or pos.shape[0] != n_atoms or len(symbols) != n_atoms or len(freqs) > n_modes:
        return None
    imag_idxs = [i for i, f in enumerate(freqs) if f < 0]
    if not imag_idxs:
        return []

    heavy = np.array([str(s).strip().capitalize() not in _LIGHT_SYMBOLS for s in symbols])

    # watch_pairs → 0-based (i<j)；越界/自对的条目丢弃，不拖垮整体摘要
    watch: list[tuple[int, int]] = []
    if watch_pairs:
        for raw in watch_pairs:
            if len(raw) != 2:
                continue
            i, j = int(raw[0]) - 1, int(raw[1]) - 1
            if 0 <= i < n_atoms and 0 <= j < n_atoms and i != j:
                pair = (min(i, j), max(i, j))
                if pair not in watch:
                    watch.append(pair)

    summaries: list[dict] = []
    for mode_idx in imag_idxs:
        u = disps[mode_idx]
        pair_scores: dict[tuple[int, int], float] = {}
        for i in range(n_atoms):
            for j in range(i + 1, n_atoms):
                vec = pos[j] - pos[i]
                norm = float(np.linalg.norm(vec))
                if norm <= 0.0:
                    continue  # 重合原子无键方向，投影无定义
                pair_scores[(i, j)] = abs(float(np.dot(u[i] - u[j], vec / norm)))

        ranked = sorted(pair_scores.items(), key=lambda kv: (-kv[1], kv[0]))
        top = [[i + 1, j + 1, score] for (i, j), score in ranked[:_TOP_PAIRS]]

        per_atom = np.sum(u * u, axis=1)  # 每原子 |u|²
        total_e = float(per_atom.sum())
        heavy_fraction = float(per_atom[heavy].sum()) / total_e if total_e > 0 else None

        # 原子组成和键向投影分别报告，避免把不沿键方向的运动漏掉。
        atom_ranking = sorted(range(n_atoms), key=lambda i: (-float(per_atom[i]), i))
        top_atoms = [dict(atom=i + 1, element=str(symbols[i]),
                          fraction=float(per_atom[i]) / total_e if total_e > 0 else None)
                     for i in atom_ranking[:_TOP_PAIRS]]
        watch_atoms = {atom for pair in watch for atom in pair}
        watch_atom_fraction = (float(per_atom[list(watch_atoms)].sum()) / total_e
                               if watch_atoms and total_e > 0 else None)
        watch_fraction = None
        if watch_pairs:
            per_pair = {f"{i + 1}-{j + 1}": pair_scores.get((i, j), 0.0) for i, j in watch}
            total_proj = sum(pair_scores.values())
            watch_fraction = {
                "fraction": (sum(per_pair.values()) / total_proj) if total_proj > 0 else None,
                "pair_projections": per_pair,
            }

        summaries.append({
            "frequency_cm": freqs[mode_idx],
            "top_displaced_atoms": top_atoms,
            "watch_atom_fraction": watch_atom_fraction,
            "top_displaced_pairs": top,
            "heavy_atom_fraction": heavy_fraction,
            "watch_pair_fraction": watch_fraction,
        })
    return summaries


def imaginary_mode_summaries_from_text(
    engine: str,
    log_text: str,
    vibfreqs: list[float],
    watch_pairs: Optional[list[list[int]]],
) -> Optional[list[dict]]:
    """虚频组成摘要（纯解析）：文本权威通道取简正模式位移与末帧几何。

    位移或几何拿不到时返回 None（调用方保持 None 语义，不填 0/空列表冒充）。
    """
    if engine == "orca":
        from cloudra.tools.core import orca_frames
        from cloudra.tools.core.irc_path import parse_xyz

        # 与 NORMAL MODES 位移块对齐必须用全模式频率轴（含平动/转动零频；
        # cclib 会裁掉打头模式），故摘要的频率一律取文本权威块。
        freqs = orca_frames.vibfreqs_from_text(log_text)
        n_atoms = len(freqs) // 3 if freqs and len(freqs) % 3 == 0 else 0
        disps = orca_frames.vibdisps_from_text(log_text, len(freqs), n_atoms) if n_atoms else None
        xyz = orca_frames.final_xyz_from_text(log_text)
        parsed = parse_xyz(xyz) if xyz.strip() else None
        if parsed is None:
            return None
        symbols, positions = parsed
    else:  # gaussian
        from cloudra.tools.core import gaussian_frames

        freqs = vibfreqs
        disps = gaussian_frames.vibdisps_from_text(log_text, len(freqs))
        blocks = gaussian_frames.std_orientation_frames(log_text)
        if not blocks:
            return None
        from cclib.parser.utils import PeriodicTable

        rows = blocks[-1]
        pt = PeriodicTable()
        symbols = [pt.element[int(z)] for z, *_ in rows]
        positions = [[x, y, z] for _, x, y, z in rows]
    return imaginary_mode_summary(freqs, disps, positions, symbols, watch_pairs)
