"""irc_path 反应对分类器与原子对应的锚点测试。

覆盖：Hungarian/align_atom_order 对应、perceive_bonds 分层、
classify_watch_pairs 的 A/B 分层、evaluate_endpoint_between 的闸门层级。
无 LLM、无网络；RDKit 相关用例按环境探测 skip。
"""

from __future__ import annotations

import importlib.util

import pytest

from cloudra.tools.core import irc_path
from cloudra.tools.core.irc_path import (
    align_atom_order,
    assign_irc_endpoints,
    bond_pairs,
    classify_watch_pairs,
    evaluate_endpoint_between,
    perceive_bonds,
)

_RDKIT = importlib.util.find_spec("rdkit") is not None

_WATER_S = ["O", "H", "H"]
_WATER_P = [[0.0, 0.0, 0.1173], [0.0, 0.7572, -0.4692], [0.0, -0.7572, -0.4692]]


# ---------------------------------------------------------------------------
# 原子对应
# ---------------------------------------------------------------------------


def test_align_atom_order_recovers_permutation():
    perm = [2, 0, 1]
    mob_s = [_WATER_S[k] for k in perm]
    mob_p = [_WATER_P[k] for k in perm]
    result = align_atom_order(_WATER_S, _WATER_P, mob_s, mob_p)
    assert result is not None
    got_perm, rmsd = result
    # perm[ref_idx] = mob_idx：ref 的 O(0) 应对应 mob 的 1
    assert got_perm[0] == 1
    assert sorted(got_perm) == [0, 1, 2]
    assert rmsd < 1e-6


def test_align_atom_order_rejects_composition_mismatch():
    assert align_atom_order(_WATER_S, _WATER_P, ["O", "O"], [[0, 0, 0], [0, 0, 1.2]]) is None
    assert align_atom_order(_WATER_S, _WATER_P, ["O", "H", "F"], _WATER_P) is None


def test_align_atom_order_rotation_invariant():
    # 同一几何绕 z 轴转 90°：距离指纹不变，指派应与未旋转一致
    rotated = [[-p[1], p[0], p[2]] for p in _WATER_P]
    result = align_atom_order(_WATER_S, _WATER_P, _WATER_S, rotated)
    assert result is not None
    assert result[0] == [0, 1, 2]


def test_align_prefers_identity_for_same_order_lineage():
    # 同序同谱系（TS↔极小值情形）：几何有差异也只是扰动，恒等对应不被
    # 几何噪声驱动的换序覆盖
    symbols = ["C", "O", "N", "H", "H"]
    ref = [[0, 0, 0], [0, 0, 1.3], [0, 0, -1.5], [1.0, 0, 1.2], [1.0, 0, -1.4]]
    mob = [[0, 0, 0.1], [0, 0, 1.35], [0, 0, -1.45], [1.1, 0, 1.1], [0.6, 0, -1.9]]
    result = align_atom_order(symbols, ref, symbols, mob)
    assert result is not None
    assert result[0] == [0, 1, 2, 3, 4]


def test_align_overrides_identity_for_decisively_better_assignment():
    # 元素序列相同但两个环境迥异的 H 真被交换：Hungarian decisively 更好
    # （代价 < margin × 恒等代价）时必须换序
    symbols = ["C", "O", "N", "H", "H"]
    ref = [[0, 0, 0], [0, 0, 1.3], [0, 0, -1.5], [1.0, 0, 1.2], [1.0, 0, -1.4]]
    mob = [[0, 0, 0], [0, 0, 1.3], [0, 0, -1.5], [1.0, 0, -1.4], [1.0, 0, 1.2]]
    result = align_atom_order(symbols, ref, symbols, mob)
    assert result is not None
    assert result[0] == [0, 1, 2, 4, 3]


# ---------------------------------------------------------------------------
# 键感知分层
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _RDKIT, reason="rdkit not installed")
def test_perceive_bonds_water_via_rdkit():
    bonds, source = perceive_bonds(_WATER_S, _WATER_P, charge=0)
    assert source == "rdDetermineBonds"
    assert set(bonds) == {(0, 1), (0, 2)}


def test_perceive_bonds_distance_fallback(monkeypatch):
    monkeypatch.setattr(irc_path, "_rdkit_bonds", lambda *a: None)
    bonds, source = perceive_bonds(_WATER_S, _WATER_P, charge=0)
    assert source == "distance"
    assert set(bonds) == {(0, 1), (0, 2)}
    assert bonds[(0, 1)] == 1.0


def test_bond_pairs_excludes_far_contacts():
    far = [[0.0, 0.0, 0.0], [0.0, 0.0, 5.0]]
    assert bond_pairs(["H", "H"], far) == set()
    assert bond_pairs(["H", "H"], [[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]]) == {(0, 1)}


# ---------------------------------------------------------------------------
# 反应对分类器（质子转移玩具：O···H 从 O 迁移到 N）
# ---------------------------------------------------------------------------


def _ptoy(d_ts, d_int):
    """三原子 O/N/H 线性玩具的距离矩阵与键图。
    几何：O 在 0、N 在 4.0、H 位置可变。键图显式给定（不依赖感知）。"""
    o, n, h = 0, 1, 2
    ts = [[0.0, 4.0, d_ts[0]], [4.0, 0.0, d_ts[1]], [d_ts[0], d_ts[1], 0.0]]
    it = [[0.0, 4.0, d_int[0]], [4.0, 0.0, d_int[1]], [d_int[0], d_int[1], 0.0]]
    return (o, n, h), ts, it


def test_classify_watch_pairs_catches_bond_flip():
    # TS：O-H 成键；中间体：N-H 成键（质子从 O 转移到 N）
    (o, n, h), d_ts, d_int = _ptoy((1.5, 2.5), (3.0, 1.0))
    ts_bonds = {(o, h): 1.0}
    int_bonds = {(n, h): 1.0}
    cls = classify_watch_pairs(["O", "N", "H"], d_ts, d_int, ts_bonds, int_bonds)
    assert set(cls["bond_diff"]) == {(o, h), (n, h)}


def test_classify_watch_pairs_floppy_contact_not_in_bond_diff():
    # 两侧都不成键的 H···H 型接触：Δd 再大也只能进 distance_top5，进不了 bond_diff
    symbols = ["C", "C", "H", "H"]
    n = len(symbols)
    base = [[0.0] * n for _ in range(n)]
    d_ts = [row[:] for row in base]
    d_int = [row[:] for row in base]
    # C-C 恒为 1.54（成键无变化）；H3-H4 从 3.0 → 4.5（floppy 接触）
    d_ts[0][1] = d_ts[1][0] = d_int[0][1] = d_int[1][0] = 1.54
    d_ts[2][3] = d_ts[3][2] = 3.0
    d_int[2][3] = d_int[3][2] = 4.5
    bonds = {(0, 1): 1.0}
    cls = classify_watch_pairs(symbols, d_ts, d_int, bonds, bonds)
    assert cls["bond_diff"] == []
    assert (2, 3) not in cls["bond_diff"]


def test_classify_watch_pairs_mad_filters_noise_floor():
    # 大量近零分对 + 一个高 ΔEN 且大 Δd 的对：MAD 过滤后只有显著对进 B
    symbols = ["C", "O", "H", "H", "H", "H"]
    n = len(symbols)
    d_ts = [[0.0] * n for _ in range(n)]
    d_int = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d_ts[i][j] = d_ts[j][i] = 2.0 + 0.01 * (i + j)
            d_int[i][j] = d_int[j][i] = d_ts[i][j] + 0.01
    # 高显著对：O-H 电负性差大 + Δd 大（但不成键，不进 A）
    d_ts[1][2] = d_ts[2][1] = 1.5
    d_int[1][2] = d_int[2][1] = 3.5
    cls = classify_watch_pairs(symbols, d_ts, d_int, {}, {})
    # 大 Δd 对进 distance_top5 回退层（gate 候选），不进 B
    assert (1, 2) in cls["distance_top5"]
    # B 层：噪声底（H-H 接触，ΔEN=0、轻原子、Δd≈0）被 MAD 滤掉
    assert not any(symbols[p[0]] == "H" and symbols[p[1]] == "H" for p in cls["b"])
    # C-O 这类重原子+电极性对保留作佐证
    assert (0, 1) in cls["b"]


# ---------------------------------------------------------------------------
# evaluate_endpoint_between 闸门层级
# ---------------------------------------------------------------------------


def _linear_ptoy():
    """O(0) ··· N(4.0) 线性骨架上的质子转移几何族。"""
    symbols = ["O", "N", "H"]

    def geo(h_x):
        return [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [h_x, 0.0, 0.0]]

    ts = geo(1.5)          # TS：H 距 O 1.5、距 N 2.5
    intermediate = geo(3.0)  # 中间体：H 到 N 上（O-H 3.0、N-H 1.0）
    good_end = geo(2.2)    # 端点在路上（O-H 2.2、N-H 1.8，均在区间内）
    bad_end = geo(1.0)     # 端点根本没走（N-H 3.0 出区间）
    return symbols, ts, intermediate, good_end, bad_end


def test_evaluate_bond_diff_layer_gates(monkeypatch):
    symbols, ts, intermediate, good_end, bad_end = _linear_ptoy()
    monkeypatch.setattr(
        irc_path, "perceive_bonds",
        lambda s, p, c=0: ({(0, 2): 1.0} if p is ts else {(1, 2): 1.0}, "rdDetermineBonds"),
    )
    good = evaluate_endpoint_between(symbols, ts, good_end, intermediate, [])
    assert good["is_decidable"] and good["is_between"]
    assert good["pair_layer"] == "bond_diff"
    assert set(good["pairs_a"]) == {(0, 2), (1, 2)}
    bad = evaluate_endpoint_between(symbols, ts, bad_end, intermediate, [])
    assert bad["is_decidable"] and not bad["is_between"]


def test_evaluate_falls_back_to_distance_top5_when_not_authoritative(monkeypatch):
    symbols, ts, intermediate, good_end, _ = _linear_ptoy()
    monkeypatch.setattr(
        irc_path, "perceive_bonds", lambda s, p, c=0: ({(0, 2): 1.0}, "distance")
    )
    result = evaluate_endpoint_between(symbols, ts, good_end, intermediate, [])
    assert result["pair_layer"] == "distance_top5"
    assert result["is_decidable"] and result["is_between"]


def test_evaluate_explicit_watch_pairs_keep_legacy_layer():
    symbols, ts, intermediate, good_end, _ = _linear_ptoy()
    result = evaluate_endpoint_between(symbols, ts, good_end, intermediate, [[1, 3]])
    assert result["pair_layer"] == "explicit"
    assert result["pairs"] == [(0, 2)]


def test_evaluate_weak_contact_deviation_is_warning_not_fail():
    """氢键/弱接触（中间体端超出共价半径判据）上的出区间——无论过冲欠程——
    降级为 warning：这类键 IRC 不需要保真（用户决策）。"""
    symbols = ["N", "O", "H"]
    ts = [[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [1.273, 0.0, 0.0]]      # TS: N-H 1.273
    inter = [[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [1.977, 0.0, 0.0]]    # 极小值: N···H 1.977（氢键）
    # 过冲（端点比极小值更散）：warning 放行
    over = [[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [2.231, 0.0, 0.0]]
    result = evaluate_endpoint_between(symbols, ts, over, inter, [[1, 3]])
    assert result["is_decidable"] and result["is_between"], result["details"]
    assert result["warnings"] == [(0, 2)], result["details"]
    # 欠程方向同样只记 warning、不进硬闸门（本例因单对矢量不再 closer 而不过，
    # 但失败来自 closer 检查，不来自区间硬失败）
    under = [[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [1.000, 0.0, 0.0]]
    result_u = evaluate_endpoint_between(symbols, ts, under, inter, [[1, 3]])
    assert result_u["warnings"] == [(0, 2)], result_u["details"]
    assert not result_u["is_between"]  # 只有 closer 失败；区间硬失败为空


def test_evaluate_covalent_deviation_is_hard_fail():
    """中间体端仍是共价键的对出区间（无论过冲欠程）→ 硬失败，不是 warning。"""
    symbols = ["C", "O", "H"]
    ts = [[0.0, 0.0, 0.0], [0.0, 0.0, 1.30], [0.0, 0.0, 2.60]]       # TS: O-H 1.30
    inter = [[0.0, 0.0, 0.0], [0.0, 0.0, 1.30], [0.0, 0.0, 2.28]]    # 极小值: O-H 0.98（共价）
    over = [[0.0, 0.0, 0.0], [0.0, 0.0, 1.30], [0.0, 0.0, 2.10]]     # 过冲方向但共价端
    result = evaluate_endpoint_between(symbols, ts, over, inter, [[2, 3]])
    assert result["is_decidable"]
    assert not result["is_between"]
    assert result["warnings"] == []


def test_assign_irc_endpoints_chained_with_alignment():
    # 端点/中间体原子序任意重排：调用方对齐后 assign 仍判 pass
    symbols, ts, intermediate, good_end, _ = _linear_ptoy()
    # 交换 O/H 位置的"重排中间体"
    perm = [2, 1, 0]
    int_s = [symbols[k] for k in perm]
    int_p = [intermediate[k] for k in perm]
    res = align_atom_order(symbols, ts, int_s, int_p)
    assert res is not None
    aligned_int = [int_p[k] for k in res[0]]
    verdict = assign_irc_endpoints(
        symbols, ts, good_end, good_end, intermediate, aligned_int, []
    )
    assert verdict["is_decidable"]
    assert verdict["is_match"]
