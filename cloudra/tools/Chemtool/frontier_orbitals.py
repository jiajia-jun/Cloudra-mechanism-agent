"""前线轨道（HOMO/LUMO/SOMO）统一原语：闭壳层与开壳层共用同一套语义。

cclib 侧（log_parser）与 PySCF 侧（electronic_analysis）各自把 mo 能量与
每自旋占据数喂给 ``frontier_orbital_summary``，得到一致口径，避免两处各写
一套互相矛盾的规则：

- 闭壳层：HOMO/LUMO/gap 直接给出；
- 开壳层：α/β 两套 HOMO/LUMO 全部显式报出（SOMO 语义：每自旋最高占据
  轨道）；整体 HOMO = max(αHOMO, βHOMO)，LUMO = min(αLUMO, βLUMO)；
- 自旋交叉（最低 LUMO 低于最高占据轨道）时单 determinant 的 gap 为负，
  物理上不可判定——gap 置 None 且 gap_status 标记原因，绝不报负值冒充
  数值结论。

纯函数、无第三方依赖；能量单位由调用方决定（cclib 传 eV，PySCF 传 Eh）。
"""

from __future__ import annotations

from typing import Optional, Sequence

GAP_OK = "ok"
GAP_UNDECIDABLE_SPIN_CROSSOVER = "undecidable_spin_crossover"
GAP_UNDECIDABLE_MISSING_ORBITALS = "undecidable_missing_orbitals"


def _homo_lumo(energies: Sequence[float], n_occupied: int) -> tuple[Optional[float], Optional[float]]:
    """单自旋通道的 HOMO/LUMO；占据数越界时对应值 None（不可判定）。"""
    homo = float(energies[n_occupied - 1]) if 1 <= n_occupied <= len(energies) else None
    lumo = float(energies[n_occupied]) if 0 <= n_occupied < len(energies) else None
    return homo, lumo


def frontier_orbital_summary(
    mo_energies_by_spin: Sequence[Sequence[float]],
    n_occupied_by_spin: Sequence[int],
) -> dict:
    """统一的前线轨道摘要。

    参数：``mo_energies_by_spin`` 每自旋一条升序轨道能量序列（闭壳层 1 条、
    开壳层 2 条，α 在前）；``n_occupied_by_spin`` 每自旋占据轨道数。
    两条序列长度不一致是上游解析异常——无法判定，抛 ValueError，绝不猜。

    返回键：
    - ``open_shell``: bool；
    - ``alpha`` / ``beta``: ``{"homo", "lumo", "n_occupied"}``（闭壳层 beta=None）；
    - ``homo`` / ``lumo``: 整体值（开壳层取 max/min，均可缺失为 None）；
    - ``gap``: lumo - homo；不可判定时 None；
    - ``gap_status``: "ok" / "undecidable_spin_crossover" /
      "undecidable_missing_orbitals"。
    """
    if len(mo_energies_by_spin) != len(n_occupied_by_spin):
        raise ValueError(
            "mo_energies_by_spin and n_occupied_by_spin must have the same length "
            f"(got {len(mo_energies_by_spin)} vs {len(n_occupied_by_spin)}); "
            "frontier orbitals are undecidable from mismatched spin channels."
        )
    if not mo_energies_by_spin:
        raise ValueError("no spin channels given; frontier orbitals are undecidable.")

    open_shell = len(mo_energies_by_spin) > 1
    channels = [
        _homo_lumo(energies, int(n_occ))
        for energies, n_occ in zip(mo_energies_by_spin, n_occupied_by_spin)
    ]
    alpha = {
        "homo": channels[0][0],
        "lumo": channels[0][1],
        "n_occupied": int(n_occupied_by_spin[0]),
    }
    beta = None
    if open_shell:
        beta = {
            "homo": channels[1][0],
            "lumo": channels[1][1],
            "n_occupied": int(n_occupied_by_spin[1]),
        }

    if not open_shell:
        homo, lumo = alpha["homo"], alpha["lumo"]
    else:
        homos = [c["homo"] for c in (alpha, beta) if c["homo"] is not None]
        lumos = [c["lumo"] for c in (alpha, beta) if c["lumo"] is not None]
        homo = max(homos) if homos else None
        lumo = min(lumos) if lumos else None

    if homo is None or lumo is None:
        gap = None
        gap_status = GAP_UNDECIDABLE_MISSING_ORBITALS
    elif lumo < homo:
        # 自旋交叉：最低空轨道低于最高占据轨道，单 determinant 的 gap 为负，
        # 不是一个可报告的数值结论。
        gap = None
        gap_status = GAP_UNDECIDABLE_SPIN_CROSSOVER
    else:
        gap = lumo - homo
        gap_status = GAP_OK

    return {
        "open_shell": open_shell,
        "alpha": alpha,
        "beta": beta,
        "homo": homo,
        "lumo": lumo,
        "gap": gap,
        "gap_status": gap_status,
    }
