from pathlib import Path

import pytest

from cloudra.tools.Chemtool.log_parser import (
    LogParser,
    LogParser_input_schema,
    _extract_gaussian_thermochemistry,
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

    values = _extract_gaussian_thermochemistry(str(log))

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
    assert result.imaginary_frequencies == pytest.approx([294.67])


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
