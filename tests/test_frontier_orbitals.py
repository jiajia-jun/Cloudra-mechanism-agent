"""frontier_orbitals 共享原语的纯函数测试（无第三方依赖）。

覆盖审计发现：开壳层前线轨道必须显式报 α/β 两套 HOMO/LUMO（SOMO 语义），
自旋交叉（最低 LUMO 低于最高占据轨道）时 gap 不可判定——置 None 并标注原因，
绝不报负值冒充数值结论。
"""

import pytest

from cloudra.tools.Chemtool.frontier_orbitals import (
    GAP_OK,
    GAP_UNDECIDABLE_MISSING_ORBITALS,
    GAP_UNDECIDABLE_SPIN_CROSSOVER,
    frontier_orbital_summary,
)


def test_closed_shell_reports_single_homo_lumo_gap():
    fo = frontier_orbital_summary([[-10.0, -5.0, -0.5, 1.0, 2.0]], [2])

    assert fo["open_shell"] is False
    assert fo["beta"] is None
    assert fo["alpha"] == {"homo": -5.0, "lumo": -0.5, "n_occupied": 2}
    assert fo["homo"] == pytest.approx(-5.0)
    assert fo["lumo"] == pytest.approx(-0.5)
    assert fo["gap"] == pytest.approx(4.5)
    assert fo["gap_status"] == GAP_OK


def test_open_shell_reports_both_spin_channels():
    fo = frontier_orbital_summary(
        [[-10.0, -4.0, -0.3, 1.0], [-10.5, -4.5, -0.2, 1.2]],
        [2, 2],
    )

    assert fo["open_shell"] is True
    assert fo["alpha"]["homo"] == pytest.approx(-4.0)
    assert fo["alpha"]["lumo"] == pytest.approx(-0.3)
    assert fo["beta"]["homo"] == pytest.approx(-4.5)
    assert fo["beta"]["lumo"] == pytest.approx(-0.2)
    # 整体 HOMO = max(α, β)，LUMO = min(α, β)
    assert fo["homo"] == pytest.approx(-4.0)
    assert fo["lumo"] == pytest.approx(-0.3)
    assert fo["gap"] == pytest.approx(3.7)
    assert fo["gap_status"] == GAP_OK


def test_open_shell_spin_crossover_gap_is_undecidable_not_negative():
    """β-LUMO 低于 α-HOMO（自旋交叉）：旧实现报负 gap，新口径必须 None + 标注。"""
    fo = frontier_orbital_summary(
        [[-11.0, -0.2, 0.5], [-12.0, -0.9, -0.4]],
        [2, 2],
    )

    assert fo["homo"] == pytest.approx(-0.2)  # max(αHOMO, βHOMO)
    assert fo["lumo"] == pytest.approx(-0.4)  # min(αLUMO, βLUMO) < homo
    assert fo["gap"] is None
    assert fo["gap_status"] == GAP_UNDECIDABLE_SPIN_CROSSOVER
    # α/β 两套仍然完整报出（SOMO 语义不丢信息）
    assert fo["alpha"]["homo"] == pytest.approx(-0.2)
    assert fo["beta"]["lumo"] == pytest.approx(-0.4)


def test_missing_virtual_orbital_marks_gap_undecidable():
    """占据数等于轨道数（无虚拟轨道）：lumo 与 gap 都不可判定。"""
    fo = frontier_orbital_summary([[-10.0, -5.0]], [2])

    assert fo["lumo"] is None
    assert fo["gap"] is None
    assert fo["gap_status"] == GAP_UNDECIDABLE_MISSING_ORBITALS


def test_mismatched_spin_channels_fail_loud():
    """mo 能量与占据数通道数不一致是上游解析异常：抛错，绝不猜一个通道。"""
    with pytest.raises(ValueError, match="same length"):
        frontier_orbital_summary([[-1.0, 0.5], [-1.2, 0.3]], [1])

    with pytest.raises(ValueError, match="no spin channels"):
        frontier_orbital_summary([], [])
