"""IRC 路径判定件（ts_guess strict verify 与 benchmark 评分共用唯一实现）。

严格档路径方向证明：不要求 IRC 收敛到极小值，但要求双侧带坐标端点各自
**几何上位于 TS 与对应端点参考几何之间**——端点的监测对距离须落在
[TS, 参考几何] 区间内（带容差）且比 TS 更靠近参考几何；两端允许
direct/swapped 无序配对，任一指派成立即方向一致。

监测原子对不是纯距离抓的，而是分层的化学分类器：

- A 层（硬证据）：TS 与中间体的键图 diff——
  键状态翻转（formed/broken）+ 两侧成键但距离剧变的伸缩对。
  键感知主通道 RDKit rdDetermineBonds（与 reaction_mapping 同一事实源，
  需总电荷）；仅当两侧感知都来自该通道时 A 层才算硬证据。
  A 层判定：中间体端仍是共价键的对出区间 = 硬失败；中间体端已超出
  共价半径判据的对（氢键/弱接触——IRC 不需要保真这类键）出区间
  无论过冲欠程都降级为 warning 放行（用户决策）。
- 回退层（distance_top5）：A 层不可用/为空（构象、翻转步）时退回旧规则
  |Δd| top-5，仍作判定对，但标记来源以示区分。
- B 层（软证据，只记录不进闸门）：ΔEN（电负性差，质子转移/氢键/极性）+
  重原子因子（反应中心多为重原子，非键减半压 I···I 型假阳性）+ |Δd|
  归一，median + 2.5·MAD 过滤离群低值。

原子对应：原子数/元素多重集不等直接判负（进不了这一层）；相等时用
距离指纹（每原子到他原子的距离排序向量，旋转平移不变）+ Hungarian
最优指派把任意原子序的几何重排到同一坐标序，原子序重排的输入不再
构成障碍。已知边界：TS↔中间体构象差大时指派可能错配——区间证明是
最后一道判官；对齐距离矩阵 rmsd 超过保守闸门（1.0 Å）的组合不可信，
直接按 undecidable 跳过（返回 None），不带着可疑对应进区间证明。
"""

from __future__ import annotations

from typing import Optional, Sequence


def same_geometry(reference, mobile) -> bool:
    """Same coordinates up to atom order and proper rigid rotation.

    Reuse the existing six-decimal XYZ rounding bound; this is identity of a
    calculation geometry, not a conformer or chemical similarity criterion.
    """
    import numpy as np

    if reference is None or mobile is None:
        return False
    ref_symbols, mob_symbols = reference[0], mobile[0]
    if len(ref_symbols) == 0 or sorted(ref_symbols) != sorted(mob_symbols):
        return False
    ref = np.asarray(reference[1], dtype=float)
    mob = np.asarray(mobile[1], dtype=float)
    ref = ref - ref.mean(axis=0)
    mob = mob - mob.mean(axis=0)
    tolerance = np.sqrt(3) * 10 ** -6

    def proper_rotation(left, right):
        u, _, vt = np.linalg.svd(left.T @ right)
        if np.linalg.det(u @ vt) < 0:
            u[:, -1] *= -1
        return u @ vt

    def matches(perm):
        ordered = mob[perm]
        residual = np.linalg.norm(ordered @ proper_rotation(ordered, ref) - ref, axis=1)
        return bool(np.max(residual) <= tolerance)

    alignment = align_atom_order(*reference, *mobile)
    if alignment is not None and matches(alignment[0]):
        return True

    # Distance-fingerprint ties can choose an improper symmetry, or mix several
    # symmetries. Keep the lineage-aware interval alignment above unchanged, but
    # search alternative strict-identity correspondences here. Two independent
    # centered vectors determine a proper rotation: at most n * (n - 1) anchor
    # pairs, rather than factorial permutations of equivalent atoms.
    d_ref, d_mob = dist_matrix(ref), dist_matrix(mob)
    fp_ref, fp_mob = np.sort(d_ref, axis=1), np.sort(d_mob, axis=1)
    compatible = np.array(mob_symbols)[:, None] == np.array(ref_symbols)[None, :]
    for i in range(len(ref_symbols)):
        # If each atom moves by at most tolerance, a pair distance changes by
        # at most twice that bound. This only prunes correspondence candidates;
        # the original proper-rotation residual remains the acceptance test.
        compatible[:, i] &= np.max(np.abs(fp_mob - fp_ref[i]), axis=1) <= 2 * tolerance
    if not np.all(np.any(compatible, axis=0)):
        return False

    first = int(np.argmax(np.linalg.norm(ref, axis=1)))
    cross = np.linalg.norm(np.cross(ref[first], ref), axis=1)
    second = int(np.argmax(cross))
    for mob_first in np.flatnonzero(compatible[:, first]):
        # Collinear geometries need only one axis; rotation about it is free.
        seconds = np.flatnonzero(compatible[:, second]) if cross[second] > 0 else [None]
        for mob_second in seconds:
            ref_anchors, mob_anchors = [first], [mob_first]
            if mob_second is not None:
                if mob_first == mob_second or abs(
                    d_ref[first, second] - d_mob[mob_first, mob_second]
                ) > 2 * tolerance:
                    continue
                ref_anchors.append(second)
                mob_anchors.append(mob_second)
            rotated = mob @ proper_rotation(mob[mob_anchors], ref[ref_anchors])
            cost = np.linalg.norm(rotated[:, None, :] - ref[None, :, :], axis=2)
            cost[~compatible] = 1e9
            perm = np.argmin(cost, axis=0).tolist()
            if len(set(perm)) != len(perm):
                perm = _hungarian(cost)
            if perm is not None and matches(perm):
                return True
    return False

_STRICT_PAIR_DELTA_MIN_ANG = 0.15
_STRICT_INTERVAL_TOL_ANG = 0.10
_STRICT_MAX_AUTO_PAIRS = 5
_STRICT_PAIR_EPS_ANG = 1e-8

# 同序偏好界：reference 与 mobile 元素序列完全一致时，只有 Hungarian 指派的
# 总代价 decisively 低于恒等指派（×此系数）才允许换序——同谱系材料的"恒等
# 对应"不该被几何噪声驱动的换序覆盖（CA/TS 误指派教训）；真正重排的输入
# （元素位置不同）恒等代价是禁配级，必然被 Hungarian 击败。
_IDENTICAL_ORDER_COST_MARGIN = 0.5

# 共价半径（Å，Cordero 系；internal_coordinates 从本模块引用，唯一事实源）
COVALENT_RADII = {
    'H': 0.31, 'He': 0.28,
    'Li': 1.28, 'Be': 0.96, 'B': 0.84, 'C': 0.76, 'N': 0.71, 'O': 0.66, 'F': 0.57, 'Ne': 0.58,
    'Na': 1.66, 'Mg': 1.41, 'Al': 1.21, 'Si': 1.11, 'P': 1.07, 'S': 1.05, 'Cl': 1.02, 'Ar': 1.06,
    'K': 2.03, 'Ca': 1.76, 'Sc': 1.70, 'Ti': 1.60, 'V': 1.53, 'Cr': 1.39, 'Mn': 1.39,
    'Fe': 1.32, 'Co': 1.26, 'Ni': 1.24, 'Cu': 1.32, 'Zn': 1.22, 'Ga': 1.22, 'Ge': 1.20,
    'As': 1.19, 'Se': 1.20, 'Br': 1.20, 'Kr': 1.16,
    'Rb': 2.20, 'Sr': 1.95, 'Y': 1.90, 'Zr': 1.75, 'Nb': 1.64, 'Mo': 1.54, 'Tc': 1.47,
    'Ru': 1.46, 'Rh': 1.42, 'Pd': 1.39, 'Ag': 1.45, 'Cd': 1.44, 'In': 1.42, 'Sn': 1.39,
    'Sb': 1.39, 'Te': 1.38, 'I': 1.39, 'Xe': 1.40,
}

#: 距离连通判据的容差系数（唯一来源）：r ≤ factor × 共价半径和 判为成键。
#: internal_coordinates / electronic_analysis / topology_change 的距离判据与
#: ts_guess 的弱接触分级全部引用此常量，避免同一分子在不同模块得到不同成键结论。
DISTANCE_CONNECTIVITY_FACTOR = 1.25

_ATOMIC_NUMBER = {
    'H': 1, 'He': 2, 'Li': 3, 'Be': 4, 'B': 5, 'C': 6, 'N': 7, 'O': 8, 'F': 9, 'Ne': 10,
    'Na': 11, 'Mg': 12, 'Al': 13, 'Si': 14, 'P': 15, 'S': 16, 'Cl': 17, 'Ar': 18,
    'K': 19, 'Ca': 20, 'Sc': 21, 'Ti': 22, 'V': 23, 'Cr': 24, 'Mn': 25, 'Fe': 26,
    'Co': 27, 'Ni': 28, 'Cu': 29, 'Zn': 30, 'Ga': 31, 'Ge': 32, 'As': 33, 'Se': 34,
    'Br': 35, 'Kr': 36, 'Rb': 37, 'Sr': 38, 'Y': 39, 'Zr': 40, 'Nb': 41, 'Mo': 42,
    'Tc': 43, 'Ru': 44, 'Rh': 45, 'Pd': 46, 'Ag': 47, 'Cd': 48, 'In': 49, 'Sn': 50,
    'Sb': 51, 'Te': 52, 'I': 53, 'Xe': 54,
}

# Pauling 电负性（B 层启发项；表外元素按 0 处理——该项失效而不是猜）
_PAULING_EN = {
    'H': 2.20, 'B': 2.04, 'C': 2.55, 'N': 3.04, 'O': 3.44, 'F': 3.98,
    'Si': 1.90, 'P': 2.19, 'S': 2.58, 'Cl': 3.16, 'As': 2.18, 'Se': 2.55,
    'Br': 2.96, 'I': 2.66,
}

# B 层提名权重与 MAD 过滤强度（用户决策：量级结合实践调整）
_HEURISTIC_W_EN = 1.0
_HEURISTIC_W_HEAVY = 0.5
_HEURISTIC_W_DIST = 1.0
_HEURISTIC_MAD_K = 2.5


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


def xyz_block(symbols, positions) -> str:
    """(symbols, positions) → 标准 XYZ 块（喂 RDKit MolFromXYZBlock）。"""
    lines = [str(len(symbols)), ""]
    for s, (x, y, z) in zip(symbols, positions):
        lines.append(f"{s} {x:.6f} {y:.6f} {z:.6f}")
    return "\n".join(lines) + "\n"


def pair_label(symbols, pair: tuple[int, int], base: int = 1) -> str:
    return f"{symbols[pair[0]]}{pair[0] + base}-{symbols[pair[1]]}{pair[1] + base}"


def dist_matrix(coords):
    import numpy as np

    pos = np.asarray(coords, dtype=float)
    diff = pos[:, None, :] - pos[None, :, :]
    return np.linalg.norm(diff, axis=-1)


#: 指派对齐的保守闸门：重排后距离矩阵 rmsd 超过该值（Å）说明指派很可能错配，
#: 该组合按 undecidable 处理（align_atom_order 返回 None）
_ALIGN_MAX_RMSD_ANG = 1.0


def bond_pairs_from_dist(symbols, d, scale: float = DISTANCE_CONNECTIVITY_FACTOR) -> set[tuple[int, int]]:
    """距离矩阵版共价半径成键判据（0-based，i<j；与 bond_pairs 同一阈值）。"""
    n = len(symbols)
    pairs: set[tuple[int, int]] = set()
    for i in range(n):
        ri = COVALENT_RADII.get(symbols[i], 1.2)
        for j in range(i + 1, n):
            rj = COVALENT_RADII.get(symbols[j], 1.2)
            if float(d[i][j]) <= scale * (ri + rj):
                pairs.add((i, j))
    return pairs


def bond_pairs(symbols, positions, scale: float = DISTANCE_CONNECTIVITY_FACTOR) -> set[tuple[int, int]]:
    """共价半径距离判据成键对集合（0-based，i<j）。"""
    return bond_pairs_from_dist(symbols, dist_matrix(positions), scale)


def _rdkit_bonds(symbols, positions, charge: int) -> Optional[dict]:
    """rdDetermineBonds 主通道；RDKit 缺失或感知失败返回 None。"""
    try:
        from rdkit import Chem
        from rdkit.Chem import rdDetermineBonds
    except ImportError:
        return None
    try:
        mol = Chem.MolFromXYZBlock(xyz_block(symbols, positions))
        if mol is None:
            return None
        rdDetermineBonds.DetermineBonds(mol, charge=charge)
    except Exception:
        return None
    out: dict[tuple[int, int], float] = {}
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        out[(min(i, j), max(i, j))] = float(bond.GetBondTypeAsDouble())
    return out


def perceive_bonds(symbols, positions, charge: int = 0) -> tuple[dict, str]:
    """键感知 → (bonds {(i,j): order}, source)。

    主通道 RDKit rdDetermineBonds（与 reaction_mapping 同一事实源，需总
    电荷）；失败/无 RDKit 回退共价半径距离判据——source="distance" 的键图
    不得充当 A 层硬证据，只喂 B 层启发项。"""
    bonds = _rdkit_bonds(symbols, positions, charge)
    if bonds is not None:
        return bonds, "rdDetermineBonds"
    return {p: 1.0 for p in bond_pairs(symbols, positions)}, "distance"


def _hungarian(cost) -> Optional[list[int]]:
    """Kuhn-Munkres 最小权指派（纯 numpy O(n³)，确定性 tie-break）。

    返回 perm：perm[j] = 分配给列 j 的行下标。大数（1e9）表示禁配。
    返回前校验：每列的指派代价 < 1e9（禁配被选中 = 无合法完美匹配）且
    每行恰好被指派一次；违反即返回 None（调用方按 undecidable 处理）。"""
    import numpy as np

    a = np.asarray(cost, dtype=float)
    n = a.shape[0]
    u = np.zeros(n + 1)
    v = np.zeros(n + 1)
    p = np.zeros(n + 1, dtype=int)
    way = np.zeros(n + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n + 1, np.inf)
        used = np.zeros(n + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = np.inf
            j1 = 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = a[i0 - 1, j - 1] - u[i0] - v[j]
                if cur < minv[j] - 1e-12:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta - 1e-12:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    perm = [int(p[j]) - 1 for j in range(1, n + 1)]
    if sorted(perm) != list(range(n)):
        return None
    if any(a[perm[j], j] >= 1e9 for j in range(n)):
        return None
    return perm


def align_atom_order(ref_symbols, ref_pos, mob_symbols, mob_pos, *, atom_order=None):
    """把 mobile 几何重排到 reference 的原子序（任意原子序输入的对应件）。

    原子数/元素多重集不等 → None（进不了这一层，调用方按 undecidable 处理）。
    对应准则：每原子的距离指纹（到他原子的距离排序向量，旋转平移不变），
    同元素掩码 + Hungarian 最优指派。返回 (perm, rmsd)：perm[ref_idx] =
    mob_idx；rmsd 是重排后距离矩阵均方根差。rmsd 超过保守闸门
    （_ALIGN_MAX_RMSD_ANG）或不存在合法的元素一致指派时也返回 None——
    对齐太差的组合按 undecidable 跳过，不带着可疑对应进区间证明。"""
    import numpy as np

    n = len(ref_symbols)
    if n != len(mob_symbols) or sorted(ref_symbols) != sorted(mob_symbols):
        return None
    d_ref = dist_matrix(ref_pos)
    d_mob = dist_matrix(mob_pos)
    if atom_order is not None:
        if (len(atom_order) != n or any(type(index) is not int for index in atom_order)
                or sorted(atom_order) != list(range(n))
                or any(ref_symbols[i] != mob_symbols[index] for i, index in enumerate(atom_order))):
            return None
        rmsd = float(np.sqrt(((d_ref - d_mob[np.ix_(atom_order, atom_order)]) ** 2).mean()))
        return (list(atom_order), rmsd) if rmsd <= _ALIGN_MAX_RMSD_ANG else None
    fp_ref = np.sort(d_ref, axis=1)
    fp_mob = np.sort(d_mob, axis=1)
    cost = np.full((n, n), 1e9)
    for i in range(n):
        for j in range(n):
            if mob_symbols[j] == ref_symbols[i]:
                cost[i, j] = float(np.linalg.norm(fp_ref[i] - fp_mob[j]))
    col_to_row = _hungarian(cost)
    if col_to_row is None:
        return None
    perm = [0] * n
    for j, i in enumerate(col_to_row):
        perm[i] = j
    if list(mob_symbols) == list(ref_symbols):
        # 元素序列一致：恒等对应（同谱系）天然合法；只有 Hungarian decisively
        # 更好（代价 < margin × 恒等代价）才换序，避免几何噪声造成假换序。
        identity_cost = float(sum(cost[i, i] for i in range(n)))
        hungarian_cost = float(sum(cost[i, perm[i]] for i in range(n)))
        if hungarian_cost >= identity_cost * _IDENTICAL_ORDER_COST_MARGIN:
            perm = list(range(n))
    rmsd = float(np.sqrt(((d_ref - d_mob[np.ix_(perm, perm)]) ** 2).mean()))
    if rmsd > _ALIGN_MAX_RMSD_ANG:
        return None
    return perm, rmsd


def classify_watch_pairs(symbols, d_ts, d_int, ts_bonds, int_bonds) -> dict:
    """反应原子对分类：bond_diff（A 层候选）/ distance_top5（回退）/ b（软提名）。

    输入是同一坐标序下的 (符号, TS 距离矩阵, 中间体距离矩阵, 两张键图)。
    - bond_diff：键状态翻转 ∪ 两侧成键且 |Δd|≥阈值的伸缩对；
    - distance_top5：|Δd| 最大的至多 5 对（≥阈值），bond_diff 不可用时的回退；
    - b：其余对按 ΔEN + 重原子 + |Δd|_norm 打分，median + k·MAD 过滤离群低值。
    """
    import statistics

    import numpy as np

    d_ts = np.asarray(d_ts, dtype=float)
    d_int = np.asarray(d_int, dtype=float)
    n = len(symbols)
    all_pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    deltas = {p: abs(float(d_ts[p]) - float(d_int[p])) for p in all_pairs}

    flips = set(ts_bonds) ^ set(int_bonds)
    stretches = {
        p for p in set(ts_bonds) & set(int_bonds)
        if deltas[p] >= _STRICT_PAIR_DELTA_MIN_ANG
    }
    bond_diff = sorted(flips | stretches)

    top5 = sorted(
        (p for p in sorted(all_pairs, key=lambda p: (-deltas[p], p))
         if deltas[p] >= _STRICT_PAIR_DELTA_MIN_ANG),
    )[:_STRICT_MAX_AUTO_PAIRS]

    gated = set(bond_diff) | set(top5)
    max_delta = max(deltas.values()) or 1.0
    bonded_any = set(ts_bonds) | set(int_bonds)
    scores: dict[tuple[int, int], float] = {}
    for p in all_pairs:
        if p in gated:
            continue
        i, j = p
        en = abs(
            _PAULING_EN.get(symbols[i], 0.0) - _PAULING_EN.get(symbols[j], 0.0)
        ) / 3.0
        heavy = min(
            _ATOMIC_NUMBER.get(symbols[i], 0), _ATOMIC_NUMBER.get(symbols[j], 0)
        ) / 6.0
        heavy = min(heavy, 1.0) * (1.0 if p in bonded_any else 0.5)
        scores[p] = (
            _HEURISTIC_W_EN * en
            + _HEURISTIC_W_HEAVY * heavy
            + _HEURISTIC_W_DIST * (deltas[p] / max_delta)
        )
    b_pairs: list[tuple[int, int]] = []
    if scores:
        values = list(scores.values())
        median = statistics.median(values)
        mad = statistics.median([abs(v - median) for v in values])
        if mad > 0:
            cutoff = median + _HEURISTIC_MAD_K * mad
        elif len(values) > 1:
            # MAD=0 退化（对称分子大量并列分）：median + k·MAD 退成 median，
            # 等于不过滤——回退固定上四分位（不随并列退化）。
            cutoff = statistics.quantiles(values, n=4)[2]
        else:
            # 单对无法构成统计过滤：不提名
            cutoff = values[0]
        b_pairs = sorted(p for p, s in scores.items() if s > cutoff)
    return {"bond_diff": bond_diff, "distance_top5": top5, "b": b_pairs}


def evaluate_endpoint_between(symbols: Sequence[str], ts_pos, end_pos,
                              intermediate_pos, watch_pairs: Sequence[Sequence[int]],
                              charge: int = 0, *, index_base: int = 1) -> dict:
    """判断一个部分 IRC 端点是否位于 TS 与某个端点参考几何之间。

    判定对来源（硬闸门）：显式 watch_pairs > 键图 diff（A 层，两侧感知均为
    rdDetermineBonds 时）> distance_top5 回退。B 层提名对只进 details。"""
    import numpy as np

    n = len(symbols)
    arrays = [np.asarray(pos, dtype=float) for pos in (ts_pos, end_pos, intermediate_pos)]
    if any(pos.shape != (n, 3) for pos in arrays):
        return {
            "is_decidable": False, "is_between": False, "score": float("inf"),
            "pairs": [], "pairs_a": [], "pairs_b": [],
            "pair_layer": "", "perception": "", "warnings": [],
            "details": ["Coordinate dimensions of TS, IRC endpoint, and intermediate do not match."],
        }

    d_ts, d_end, d_int = (dist_matrix(pos) for pos in arrays)
    b_pairs: list[tuple[int, int]] = []
    perception = "explicit_watch_pairs"
    if watch_pairs:
        layer = "explicit"
        pairs = []
        for raw_pair in watch_pairs:
            if len(raw_pair) != 2:
                return {
                    "is_decidable": False, "is_between": False, "score": float("inf"),
                    "pairs": [], "pairs_a": [], "pairs_b": [],
                    "pair_layer": "", "perception": "", "warnings": [],
                    "details": [f"watch_pairs entries must contain two atom indices: {raw_pair}"],
                }
            i, j = int(raw_pair[0]) - index_base, int(raw_pair[1]) - index_base
            if not (0 <= i < n and 0 <= j < n) or i == j:
                return {
                    "is_decidable": False, "is_between": False, "score": float("inf"),
                    "pairs": [], "pairs_a": [], "pairs_b": [],
                    "pair_layer": "", "perception": "", "warnings": [],
                    "details": [f"watch_pairs atom indices invalid: {raw_pair}"],
                }
            pair = (min(i, j), max(i, j))
            if pair not in pairs:
                pairs.append(pair)
        pairs = [pair for pair in pairs if abs(d_int[pair] - d_ts[pair]) > _STRICT_PAIR_EPS_ANG]
    else:
        ts_bonds, src_ts = perceive_bonds(symbols, ts_pos, charge)
        int_bonds, src_int = perceive_bonds(symbols, intermediate_pos, charge)
        perception = f"ts={src_ts},intermediate={src_int}"
        cls = classify_watch_pairs(symbols, d_ts, d_int, ts_bonds, int_bonds)
        b_pairs = cls["b"]
        authoritative = src_ts == src_int == "rdDetermineBonds"
        if authoritative and cls["bond_diff"]:
            pairs, layer = cls["bond_diff"], "bond_diff"
        else:
            pairs, layer = cls["distance_top5"], "distance_top5"

    if not pairs:
        return {
            "is_decidable": False, "is_between": False, "score": float("inf"),
            "pairs": [], "pairs_a": [], "pairs_b": b_pairs,
            "pair_layer": layer, "perception": perception, "warnings": [],
            "details": ["No atom-pair distance change between TS and intermediate is large enough to judge direction."],
        }

    q_ts = np.asarray([d_ts[pair] for pair in pairs])
    q_end = np.asarray([d_end[pair] for pair in pairs])
    q_int = np.asarray([d_int[pair] for pair in pairs])
    lower = np.minimum(q_ts, q_int) - _STRICT_INTERVAL_TOL_ANG
    upper = np.maximum(q_ts, q_int) + _STRICT_INTERVAL_TOL_ANG
    inside = (q_end >= lower) & (q_end <= upper)

    # 失败分级：中间体端仍是共价键的对，任何出区间都是硬失败；
    # 中间体端已超出共价半径判据的对（氢键/弱接触——IRC 不需要保真这类键，
    # 用户决策）无论过冲还是欠程都降级为 warning——弱接触在两个方向上
    # 都是 floppy 的，未完全收敛的端点在上面偏一点是常态。
    warnings: list[tuple[int, int]] = []
    hard_outside: list[tuple[int, int]] = []
    for k, pair in enumerate(pairs):
        if inside[k]:
            continue
        weak_at_intermediate = float(q_int[k]) > DISTANCE_CONNECTIVITY_FACTOR * (
            COVALENT_RADII.get(symbols[pair[0]], 1.2)
            + COVALENT_RADII.get(symbols[pair[1]], 1.2)
        )
        if weak_at_intermediate:
            warnings.append(pair)
        else:
            hard_outside.append(pair)

    dist_ts_to_int = float(np.linalg.norm(q_ts - q_int))
    dist_end_to_int = float(np.linalg.norm(q_end - q_int))
    closer = dist_end_to_int < dist_ts_to_int
    is_between = bool(not hard_outside and closer)
    score = dist_end_to_int / dist_ts_to_int if dist_ts_to_int > 0 else float("inf")

    details = [
        f"{pair_label(symbols, pair, index_base)}: TS={d_ts[pair]:.3f} Å, "
        f"IRC_endpoint={d_end[pair]:.3f} Å, intermediate={d_int[pair]:.3f} Å, "
        f"{'inside interval' if inside[k] else 'outside interval'}"
        for k, pair in enumerate(pairs)
    ]
    for pair in warnings:
        details.append(
            f"[warning] {pair_label(symbols, pair, index_base)}: endpoint deviates from the "
            f"interval on a weak contact (H-bond/non-covalent at the minimum, "
            f"d={d_int[pair]:.3f} Å); IRC need not preserve such pairs."
        )
    details.append(f"Distance-vector ratio endpoint-to-intermediate={score:.3f} (<1 means closer than TS).")
    details.append(f"Gate pairs layer: {layer} (perception: {perception}).")
    for pair in b_pairs:
        details.append(
            f"[advisory-B] {pair_label(symbols, pair, index_base)}: TS={d_ts[pair]:.3f} Å, "
            f"IRC_endpoint={d_end[pair]:.3f} Å, intermediate={d_int[pair]:.3f} Å"
        )
    return {
        "is_decidable": True,
        "is_between": is_between,
        "score": score,
        "pairs": pairs,
        "pairs_a": pairs,
        "pairs_b": b_pairs,
        "pair_layer": layer,
        "perception": perception,
        "warnings": warnings,
        "details": details,
    }


def assign_irc_endpoints(symbols: Sequence[str], ts_pos, end_a_pos, end_b_pos,
                         intermediate_a_pos, intermediate_b_pos,
                         watch_pairs: Sequence[Sequence[int]],
                         charge: int = 0, *, index_base: int = 1) -> dict:
    """尝试 IRC 两端与两个端点参考几何的 direct/swapped 无序配对。"""
    assignments = []
    for name, target_a, target_b in (
        ("direct", intermediate_a_pos, intermediate_b_pos),
        ("swapped", intermediate_b_pos, intermediate_a_pos),
    ):
        result_a = evaluate_endpoint_between(
            symbols, ts_pos, end_a_pos, target_a, watch_pairs, charge, index_base=index_base
        )
        result_b = evaluate_endpoint_between(
            symbols, ts_pos, end_b_pos, target_b, watch_pairs, charge, index_base=index_base
        )
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
        "warnings": chosen["a"].get("warnings", []) + chosen["b"].get("warnings", []),
        "details": chosen["a"]["details"] + chosen["b"]["details"],
    }


def prove_irc_endpoint_direction(
    ts_symbols: Sequence[str],
    ts_pos,
    endpoint_a: tuple[Sequence[str], object],
    endpoint_b: tuple[Sequence[str], object],
    intermediate_a: tuple[Sequence[str], object],
    intermediate_b: tuple[Sequence[str], object],
    watch_pairs: Sequence[Sequence[int]],
    charge: int = 0,
    *, index_base: int = 1, atom_orders=None,
) -> dict:
    """Align four geometries to the TS and apply the shared IRC direction test.

    This is the single deterministic path-direction predicate used by ``ts_guess``
    and benchmark self-consistency.  It deliberately proves only geometric
    direction; optimization convergence and file provenance remain separate facts.
    """
    aligned = []
    for slot, (label, (symbols, positions)) in enumerate((
        ("IRC endpoint A", endpoint_a),
        ("IRC endpoint B", endpoint_b),
        ("intermediate A", intermediate_a),
        ("intermediate B", intermediate_b),
    )):
        result = align_atom_order(ts_symbols, ts_pos, symbols, positions,
                                  atom_order=atom_orders[slot] if atom_orders else None)
        if result is None:
            return {
                "is_decidable": False,
                "is_match": False,
                "assignment": "",
                "details": [
                    f"{label} differs from the TS in elements or atom counts, or geometry alignment failed."
                ],
            }
        perm, rmsd = result
        aligned.append([positions[k] for k in perm])

    result = assign_irc_endpoints(
        ts_symbols,
        ts_pos,
        aligned[0], aligned[1], aligned[2], aligned[3],
        watch_pairs,
        charge, index_base=index_base,
    )
    result["aligned_positions"] = aligned
    return result
