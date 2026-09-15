from pathlib import Path

import pytest

from cloudra.tools.Chemtool.log_parser import (
    LogParser,
    LogParser_input_schema,
    _extract_gaussian_thermochemistry,
    derive_delivery_changes,
)

FIXTURE = Path(__file__).parent / "fixtures" / "gaussian" / "water_opt_freq_g16.out"


@pytest.mark.asyncio
async def test_gaussian_thermochemistry_distinguishes_corrections_from_totals():
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(FIXTURE), properties=["thermochemistry"]),
        session=None,
    )

    assert result.is_success is True
    assert result.zero_point_correction_hartree == pytest.approx(0.024385)
    assert result.thermal_energy_correction_hartree == pytest.approx(0.027218)
    assert result.thermal_enthalpy_correction_hartree == pytest.approx(0.028162)
    assert result.thermal_gibbs_correction_hartree == pytest.approx(0.006648)
    assert result.total_enthalpy_hartree == pytest.approx(-74.937739)
    assert result.total_gibbs_free_energy_hartree == pytest.approx(-74.959254)

    # 兼容字段保留原有调用方式，但不能再把 cclib 的总焓冒充热能校正。
    assert result.zero_point_energy_hartree == pytest.approx(0.024385)
    assert result.thermal_energy_hartree == pytest.approx(0.027218)
    assert result.enthalpy_hartree == pytest.approx(-74.937739)
    assert result.gibbs_free_energy_hartree == pytest.approx(-74.959254)


def test_thermochemistry_parser_never_mixes_separate_summary_blocks(tmp_path):
    log = tmp_path / "two_freq_jobs.log"
    log.write_text(
        """Zero-point correction= 0.010000
Thermal correction to Energy= 0.020000
Thermal correction to Enthalpy= 0.030000
Thermal correction to Gibbs Free Energy= 0.040000
Sum of electronic and zero-point Energies= -9.990000
Sum of electronic and thermal Energies= -9.980000
Sum of electronic and thermal Enthalpies= -9.970000
Sum of electronic and thermal Free Energies= -9.960000
Zero-point correction= 0.110000
Thermal correction to Energy= 0.120000
""",
        encoding="utf-8",
    )

    values = _extract_gaussian_thermochemistry(log.read_text(encoding="utf-8"))

    assert values["zero_point_correction_hartree"] == pytest.approx(0.010000)
    assert values["thermal_energy_correction_hartree"] == pytest.approx(0.020000)
    assert values["total_gibbs_free_energy_hartree"] == pytest.approx(-9.960000)


ORCA_FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "co2_freq_orca42.out"


@pytest.mark.asyncio
async def test_orca_log_full_parse_matches_gaussian_field_semantics():
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(ORCA_FIXTURE)), session=None,
    )

    assert result.is_success is True
    assert result.engine == "orca"
    assert result.job_types == ["freq", "opt"]
    assert result.normal_termination is True
    assert result.scf_energy_hartree == pytest.approx(-184.75776616)
    assert result.dipole_moment_debye == pytest.approx(0.0)
    assert result.zero_point_correction_hartree == pytest.approx(0.00684398)
    assert result.thermal_energy_correction_hartree == pytest.approx(0.00993959)
    assert result.total_enthalpy_hartree == pytest.approx(-184.74688237)
    assert result.total_gibbs_free_energy_hartree == pytest.approx(-184.77272599)
    assert result.imaginary_frequencies == []
    assert result.mulliken_charges is not None
    # cclib 可用时频率仍走 cclib（文本回退不得改变既有行为，GH #16 回归）
    assert result.frequencies_cm == pytest.approx([289.50, 458.10, 1114.50, 1142.05])


@pytest.mark.asyncio
async def test_orca_opt_without_freq_does_not_fake_zero_imaginary():
    fixture = Path(__file__).parent / "fixtures" / "orca" / "dvb_opt_orca42.out"
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(fixture)), session=None,
    )

    assert result.is_success is True
    assert result.job_types == ["opt"]
    # 无频率数据时必须保持 None（不得被 DAG 侧当成零虚频极小点）
    assert result.frequencies_cm is None
    assert result.imaginary_frequencies is None


ORCA_EXTOPT_FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "cope_irc_extopt_mace_orca611.out"
ORCA_IRC_FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "hcn_irc_orca60.out"


@pytest.mark.asyncio
async def test_orca_extopt_energy_and_termination_from_text_when_cclib_fails(monkeypatch):
    """GH #17：外部 MLIP（ExtOpt）日志无 SCF 块，cclib 解析抛错——能量回退取
    FINAL SINGLE POINT ENERGY (From external program)，终止判定认
    ORCA TERMINATED NORMALLY 文本标记，整体解析仍成功。"""
    import cclib

    def _boom(*_args, **_kwargs):
        raise ValueError("Unexpectedly encountered end of logfile")

    monkeypatch.setattr(cclib.io, "ccread", _boom)

    result = await LogParser().tool_call(
        LogParser_input_schema(
            log_path=str(ORCA_EXTOPT_FIXTURE), properties=["energy", "convergence"]
        ),
        session=None,
    )
    assert result.is_success is True
    assert result.engine == "orca"
    assert result.normal_termination is True
    assert result.scf_energy_hartree == pytest.approx(-234.506295105500)


@pytest.mark.asyncio
async def test_orca_normal_termination_marker_overrides_cclib_metadata(monkeypatch):
    """GH #17 job17：cclib 可解析但 metadata.success=False（MLIP 日志无 SCF
    完成标记）——ORCA 的终止判定以文本标记为权威，不采信 cclib metadata。"""
    import types

    import cclib

    stub = types.SimpleNamespace(metadata={"success": False})
    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: stub)

    result = await LogParser().tool_call(
        LogParser_input_schema(
            log_path=str(ORCA_EXTOPT_FIXTURE), properties=["convergence", "energy"]
        ),
        session=None,
    )
    assert result.is_success is True
    assert result.normal_termination is True
    assert result.scf_energy_hartree == pytest.approx(-234.506295105500)


@pytest.mark.asyncio
async def test_orca_extopt_abnormal_termination_reported_false(tmp_path, monkeypatch):
    """终止标记缺失（error termination / 被 kill）→ normal_termination=False；
    日志里有能量行也不反推成功。"""
    import cclib

    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: None)
    log = tmp_path / "job.out"
    log.write_text(
        "                         * O   R   C   A *\n"
        "FINAL SINGLE POINT ENERGY (From external program)     -234.500000000000\n"
        "ORCA finished by error termination in ORCA_GSTEP\n",
        encoding="utf-8",
    )
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=["convergence", "energy"]),
        session=None,
    )
    assert result.is_success is True
    assert result.normal_termination is False
    assert result.scf_energy_hartree == pytest.approx(-234.5)


# GH #21：未收敛的 MACE ExtOpt Opt 日志片段（GH #21/#22 真实样本，原日志已随工作区清理删除）
_ORCA_EXTOPT_OPT_NOT_CONVERGED = (
    "                         * O   R   C   A *\n"
    "! ExtOpt Opt\n"
    "FINAL SINGLE POINT ENERGY (From external program)      -383.418935837100\n"
    "                        GEOMETRY OPTIMIZATION CYCLE   1\n"
    "Current Energy                          ....  -383.544742265 Eh\n"
    "                                  WARNING !!!\n"
    "       The optimization did not converge but reached the maximum number of\n"
    "       optimization cycles.\n"
    "       Please check your results very carefully.\n"
    "                             ****ORCA TERMINATED NORMALLY****\n"
)


# GH #16：合成的最小 ExtOpt NumFreq 日志（频率块格式取自真实 ORCA NumFreq
# 输出；外部 MLIP 日志无 SCF 块，cclib 整体失败时频率须从文本回退）。
_ORCA_EXTOPT_NUMFREQ = (
    "                         * O   R   C   A *\n"
    "! ExtOpt NumFreq\n"
    "FINAL SINGLE POINT ENERGY (From external program)      -234.506295105500\n"
    "VIBRATIONAL FREQUENCIES\n"
    "-----------------------\n"
    "\n"
    "   0:      -294.67 cm**-1 ***imaginary mode***\n"
    "   1:       289.50 cm**-1\n"
    "   2:       458.10 cm**-1\n"
    "\n"
    "                             ****ORCA TERMINATED NORMALLY****\n"
)


@pytest.mark.asyncio
async def test_orca_extopt_numfreq_frequencies_from_text_when_cclib_fails(tmp_path, monkeypatch):
    """GH #16：cclib 对 ExtOpt NumFreq 日志解析失败时，频率从
    VIBRATIONAL FREQUENCIES 块文本回退，负值导出虚频（n_imag 正确）。"""
    import cclib

    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: None)
    log = tmp_path / "job.out"
    log.write_text(_ORCA_EXTOPT_NUMFREQ, encoding="utf-8")
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=["frequencies", "convergence"]),
        session=None,
    )
    assert result.is_success is True
    assert result.engine == "orca"
    assert result.normal_termination is True
    assert result.frequencies_cm == pytest.approx([289.50, 458.10])
    assert result.imaginary_frequencies == pytest.approx([-294.67])


@pytest.mark.asyncio
async def test_orca_extopt_opt_without_freq_keeps_none(tmp_path, monkeypatch):
    """GH #16：无频率块的 ExtOpt 日志回退后仍保持 None（不得当成零虚频）。"""
    import cclib

    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: None)
    log = tmp_path / "job.out"
    log.write_text(_ORCA_EXTOPT_OPT_NOT_CONVERGED, encoding="utf-8")
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=["frequencies"]),
        session=None,
    )
    assert result.is_success is True
    assert result.frequencies_cm is None
    assert result.imaginary_frequencies is None


@pytest.mark.asyncio
async def test_orca_opt_converged_exposed_separately_from_normal_termination(tmp_path, monkeypatch):
    """GH #21：未收敛的 Opt 仍 normal_termination=True（进程正常结束）但
    opt_converged=False——两者语义分开；能量取最后的 Current Energy（GH #22）。"""
    import cclib

    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: None)
    log = tmp_path / "job.out"
    log.write_text(_ORCA_EXTOPT_OPT_NOT_CONVERGED, encoding="utf-8")
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=["convergence", "energy"]),
        session=None,
    )
    assert result.is_success is True
    assert result.normal_termination is True
    assert result.opt_converged is False
    assert result.scf_energy_hartree == pytest.approx(-383.544742265)


@pytest.mark.asyncio
async def test_orca_opt_converged_true_for_converged_opt():
    """收敛的 DFT Opt（dvb fixture）：opt_converged=True。"""
    fixture = Path(__file__).parent / "fixtures" / "orca" / "dvb_opt_orca42.out"
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(fixture), properties=["convergence"]),
        session=None,
    )
    assert result.is_success is True
    assert result.normal_termination is True
    assert result.opt_converged is True


@pytest.mark.asyncio
async def test_orca_opt_converged_none_for_non_opt_log():
    """非优化日志（freq-only / sp）：opt_converged 为 None，不误报收敛状态。"""
    fixture = Path(__file__).parent / "fixtures" / "orca" / "dvb_scan_unrelaxed_orca42.out"
    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(fixture), properties=["convergence"]),
        session=None,
    )
    assert result.is_success is True
    assert result.opt_converged is None


# ---------------------------------------------------------------------------
# 前线轨道（开壳层 α/β 双通道，与 electronic_analysis 共用原语）
# ---------------------------------------------------------------------------


def _stub_cclib(monkeypatch, namespace):
    import cclib

    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: namespace)


_ORCA_MINIMAL_LOG = (
    "                         * O   R   C   A *\n"
    "FINAL SINGLE POINT ENERGY      -100.000000000000\n"
    "                             ****ORCA TERMINATED NORMALLY****\n"
)


@pytest.mark.asyncio
async def test_open_shell_frontier_orbitals_report_alpha_beta_channels(tmp_path, monkeypatch):
    """开壳层：显式报 α/β 两套 HOMO/LUMO（SOMO 语义）；自旋交叉时 gap 不可判定
    （None + message 标注），旧实现只取 α 通道报 "α-only gap" 且可能为负。"""
    import types

    # α: HOMO(idx1)=-0.2 LUMO=0.1；β: HOMO(idx1)=-0.3 LUMO=-0.25（< αHOMO → 自旋交叉）
    stub = types.SimpleNamespace(
        moenergies=[[-10.0, -0.2, 0.1], [-10.5, -0.3, -0.25]],
        homos=[1, 1],
    )
    _stub_cclib(monkeypatch, stub)
    log = tmp_path / "open_shell.out"
    log.write_text(_ORCA_MINIMAL_LOG, encoding="utf-8")

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=["homo_lumo"]),
        session=None,
    )

    assert result.is_success is True
    assert result.alpha_homo_ev == pytest.approx(-0.2)
    assert result.alpha_lumo_ev == pytest.approx(0.1)
    assert result.beta_homo_ev == pytest.approx(-0.3)
    assert result.beta_lumo_ev == pytest.approx(-0.25)
    assert result.homo_ev == pytest.approx(-0.2)  # max(αHOMO, βHOMO)
    assert result.lumo_ev == pytest.approx(-0.25)  # min(αLUMO, βLUMO)
    assert result.spin_crossover is True
    assert result.homo_lumo_gap_ev is None  # 不可判定，绝不报负值
    assert "spin crossover" in result.message


@pytest.mark.asyncio
async def test_closed_shell_frontier_orbitals_unchanged(tmp_path, monkeypatch):
    """闭壳层回归：单一 HOMO/LUMO/gap 照常给出，不出现自旋通道字段。"""
    import types

    stub = types.SimpleNamespace(
        moenergies=[[-10.0, -5.0, -0.5, 1.0]],
        homos=[1],
    )
    _stub_cclib(monkeypatch, stub)
    log = tmp_path / "closed_shell.out"
    log.write_text(_ORCA_MINIMAL_LOG, encoding="utf-8")

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(log), properties=["homo_lumo"]),
        session=None,
    )

    assert result.is_success is True
    assert result.homo_ev == pytest.approx(-5.0)
    assert result.lumo_ev == pytest.approx(-0.5)
    assert result.homo_lumo_gap_ev == pytest.approx(4.5)
    assert result.alpha_homo_ev is None
    assert result.spin_crossover is None


# ---------------------------------------------------------------------------
# 终止判定证据门控（None = undecidable，不发证据）
# ---------------------------------------------------------------------------


def test_delivery_evidence_requires_explicit_true_normal_termination():
    """normal_termination=None（终止未判定）不得派生 structure_supported：
    旧实现 `is not False` 把未知当正常放行。"""
    base = {"frequencies_cm": [100.0, 200.0], "imaginary_frequencies": []}

    undecidable = derive_delivery_changes(
        current={}, role="intermediate_optimization", arguments={},
        result={**base, "normal_termination": None},
    )
    assert undecidable == {}

    confirmed = derive_delivery_changes(
        current={}, role="intermediate_optimization", arguments={},
        result={**base, "normal_termination": True},
    )
    assert confirmed == {"evidence_level": "structure_supported"}

    ts_undecidable = derive_delivery_changes(
        current={}, role="ts_optimization_frequency", arguments={},
        result={"frequencies_cm": [100.0], "imaginary_frequencies": [-50.0],
                "normal_termination": None},
    )
    assert ts_undecidable == {}


# ---------------------------------------------------------------------------
# 单读一次：解析全程不得再走 frames 模块的 log_path 变体
# ---------------------------------------------------------------------------


def _raise_on_reread(*_args, **_kwargs):
    raise AssertionError("log text was re-read through a log_path variant")


@pytest.mark.asyncio
async def test_orca_parse_never_rereads_log_via_path_variants(monkeypatch):
    """单读一次（ORCA 含 IRC 的日志）：detect_job_types / extract_thermochemistry /
    extract_irc 的 log_path 变体全程不得被调用——一切走 *_from_text。"""
    import cclib

    import cloudra.tools.core.orca_frames as orca_frames

    monkeypatch.setattr(cclib.io, "ccread", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(orca_frames, "detect_job_types", _raise_on_reread)
    monkeypatch.setattr(orca_frames, "extract_thermochemistry", _raise_on_reread)
    monkeypatch.setattr(orca_frames, "extract_irc", _raise_on_reread)

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(ORCA_IRC_FIXTURE)),
        session=None,
    )

    assert result.is_success is True
    assert "irc" in result.job_types
    assert result.irc_num_points_forward == 5
    assert result.irc_num_points_backward == 7
    assert result.irc_both_directions_converged is True


@pytest.mark.asyncio
async def test_gaussian_parse_never_rereads_log_via_path_variants(monkeypatch):
    """单读一次（Gaussian）：detect_job_types / extract_irc 的 log_path 变体
    全程不得被调用；热化学吃同一份已读文本。"""
    import cloudra.tools.core.gaussian_frames as gaussian_frames

    monkeypatch.setattr(gaussian_frames, "detect_job_types", _raise_on_reread)
    monkeypatch.setattr(gaussian_frames, "extract_irc", _raise_on_reread)

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(FIXTURE)),
        session=None,
    )

    assert result.is_success is True
    assert result.job_types == ["freq", "opt"]
    assert result.zero_point_correction_hartree == pytest.approx(0.024385)
