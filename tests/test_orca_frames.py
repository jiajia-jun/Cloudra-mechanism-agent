"""ORCA frames: engine/job-type detection, thermochemistry, frame extraction."""

from pathlib import Path

import pytest

pytest.importorskip("cclib", reason="orca_frames requires cclib (chem extra)")

from cloudra.tools.core import orca_frames
from cloudra.tools.core.qm_engine import detect_qm_engine

ORCA_FIXTURES = Path(__file__).parent / "fixtures" / "orca"
GAUSSIAN_FIXTURES = Path(__file__).parent / "fixtures" / "gaussian"


def test_engine_detection_distinguishes_orca_from_gaussian():
    assert detect_qm_engine(str(ORCA_FIXTURES / "co2_freq_orca42.out")) == "orca"
    assert detect_qm_engine(str(ORCA_FIXTURES / "dvb_opt_orca42.out")) == "orca"
    assert detect_qm_engine(str(GAUSSIAN_FIXTURES / "water_opt_freq_g16.out")) == "gaussian"
    assert detect_qm_engine(str(GAUSSIAN_FIXTURES / "hcn_ts_irc_g16.log")) == "gaussian"


def test_orca_job_type_detection():
    assert orca_frames.detect_job_types(str(ORCA_FIXTURES / "co2_freq_orca42.out")) == {"opt", "freq"}
    assert orca_frames.detect_job_types(str(ORCA_FIXTURES / "dvb_opt_orca42.out")) == {"opt"}
    assert orca_frames.detect_job_types(str(ORCA_FIXTURES / "dvb_scan_unrelaxed_orca42.out")) == {"scan"}
    assert orca_frames.detect_job_types(str(ORCA_FIXTURES / "hcn_irc_orca60.out")) == {"irc"}


def test_orca_irc_extraction_from_main_output():
    """ORCA IRC 的点数/收敛/端点能量从主输出的 FORWARD/BACKWARD 迭代块与
    IRC PATH SUMMARY 提取（无需追 trj 边文件），供 short_irc 阶段绑定。"""
    meta = orca_frames.extract_irc(str(ORCA_FIXTURES / "hcn_irc_orca60.out"))
    assert meta["num_points_forward"] == 5
    assert meta["num_points_backward"] == 7
    assert meta["forward_converged"] is True
    assert meta["backward_converged"] is True
    # PATH SUMMARY 首行=反应物端、末行=产物端；"<= TS" 行为 TS 能量（最高）
    assert meta["endpoint_energies_hartree"] == pytest.approx((-1404.7228, -1404.7223))
    assert meta["ts_energy_hartree"] == pytest.approx(-1404.7175)
    assert meta["ts_energy_hartree"] > max(meta["endpoint_energies_hartree"])


def test_orca_thermochemistry_matches_gaussian_field_semantics():
    thermo = orca_frames.extract_thermochemistry(str(ORCA_FIXTURES / "co2_freq_orca42.out"))

    # 修正量
    assert thermo["zero_point_correction_hartree"] == pytest.approx(0.00684398)
    # 含 ZPE 口径（Total thermal correction 0.00309561 + ZPE 0.00684398）
    assert thermo["thermal_energy_correction_hartree"] == pytest.approx(0.00993959)
    assert thermo["thermal_enthalpy_correction_hartree"] == pytest.approx(0.00094421)
    assert thermo["thermal_gibbs_correction_hartree"] == pytest.approx(-0.01495982)
    # 总量
    assert thermo["total_thermal_energy_hartree"] == pytest.approx(-184.74782658)
    assert thermo["total_enthalpy_hartree"] == pytest.approx(-184.74688237)
    assert thermo["total_gibbs_free_energy_hartree"] == pytest.approx(-184.77272599)
    # 派生：E(el) + ZPE = -184.75776616 + 0.00684398
    assert thermo["total_zero_point_energy_hartree"] == pytest.approx(-184.75092218)


def test_orca_opt_frames_carry_convergence_and_xyz():
    frames = orca_frames.extract_frames(str(ORCA_FIXTURES / "dvb_opt_orca42.out"))
    assert len(frames) == 4
    assert all(f.xyz for f in frames)
    assert all(f.scf_energy_hartree is not None for f in frames)
    assert frames[-1].converged is True


def test_orca_unrelaxed_scan_frames_have_parameter_series():
    frames = orca_frames.extract_frames(str(ORCA_FIXTURES / "dvb_scan_unrelaxed_orca42.out"))
    assert len(frames) == 12
    rx = [f.reaction_coordinate for f in frames]
    assert rx[0] == pytest.approx(0.0)
    assert rx[1] == pytest.approx(32.72727273)
    assert all(v is not None for v in rx)
    # 单调递增的二面角扫描
    assert rx == sorted(rx)


@pytest.mark.asyncio
async def test_log_parser_orca_irc_end_to_end():
    """log_parser 走 ORCA 引擎时透出 short_irc deriver 消费的字段，
    使 ORCA 路线的 short_irc 阶段绑定可达（不再结构性断供）。"""
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(
            log_path=str(ORCA_FIXTURES / "hcn_irc_orca60.out"),
            properties=["job_type", "irc"],
        ),
        session=None,
    )
    assert result.is_success is True
    assert result.job_types == ["irc"]
    assert result.irc_num_points_forward == 5
    assert result.irc_num_points_backward == 7
    assert result.irc_both_directions_converged is True
    assert result.irc_endpoint_energies_hartree == pytest.approx(
        [-1404.7228, -1404.7223]
    )


# ---------------------------------------------------------------------------
# GH #21：几何优化未收敛（max-cycles）判定；GH #22：未收敛 ExtOpt Opt 的能量
# ---------------------------------------------------------------------------

# 未收敛的 MACE ExtOpt Opt 日志片段（GH #21/#22 真实样本，原日志已随工作区清理删除）：
# FINAL SP 只在起始几何打印一次，逐周期能量以 Current Energy 行给出。
_EXTOPT_OPT_NOT_CONVERGED_SNIPPET = (
    "FINAL SINGLE POINT ENERGY (From external program)      -383.418935837100\n"
    "Current Energy                          ....  -383.543545238 Eh\n"
    "Current Energy                          ....  -383.544742265 Eh\n"
    "                                  WARNING !!!\n"
    "       The optimization did not converge but reached the maximum number of\n"
    "       optimization cycles.\n"
    "       Please check your results very carefully.\n"
    "                             ****ORCA TERMINATED NORMALLY****\n"
)

# 取自 calc-25.out.log（收敛的 ExtOpt Opt）：收敛后在末几何再打印一次 FINAL SP。
_EXTOPT_OPT_CONVERGED_SNIPPET = (
    "Current Energy                          ....  -153.827552874 Eh\n"
    "                    ***        THE OPTIMIZATION HAS CONVERGED     ***\n"
    "FINAL SINGLE POINT ENERGY (From external program)      -153.827552913800\n"
    "                             ****ORCA TERMINATED NORMALLY****\n"
)


def test_final_energy_returns_later_current_energy_for_unconverged_extopt():
    """GH #22：未收敛（max-cycles）只打印一次 FINAL SP（起始几何），最后的
    Current Energy 才是最佳几何能量——按文本位置取更靠后者。"""
    energy = orca_frames.final_energy_hartree(_EXTOPT_OPT_NOT_CONVERGED_SNIPPET)
    assert energy == pytest.approx(-383.544742265)


def test_final_energy_keeps_final_sp_when_printed_last():
    """收敛的 Opt（DFT/ExtOpt）在收敛几何后再打印 FINAL SP，位置在最后，
    位置规则天然返回它——收敛作业行为不变。"""
    energy = orca_frames.final_energy_hartree(_EXTOPT_OPT_CONVERGED_SNIPPET)
    assert energy == pytest.approx(-153.827552913800)


def test_final_energy_single_point_log_unchanged():
    """单点/无 Current Energy 的日志行为不变：仍取最后的 FINAL SP。"""
    text = (
        "FINAL SINGLE POINT ENERGY     -76.000000000001\n"
        "FINAL SINGLE POINT ENERGY     -76.000000000002\n"
    )
    assert orca_frames.final_energy_hartree(text) == pytest.approx(-76.000000000002)
    assert orca_frames.final_energy_hartree("no energy here") is None


def test_final_energy_dft_opt_fixture_uses_last_final_sp():
    """DFT 收敛 Opt（dvb fixture）回归守卫：最后的 FINAL SP 在 Current Energy
    之后打印，位置规则不得改变既有行为。"""
    text = (ORCA_FIXTURES / "dvb_opt_orca42.out").read_text(encoding="utf-8")
    assert orca_frames.final_energy_hartree(text) == pytest.approx(-382.050786152426)


def test_opt_converged_text_markers():
    """GH #21：优化收敛状态文本判定（不依赖 cclib）；非优化日志返回 None。"""
    assert orca_frames.opt_converged(_EXTOPT_OPT_NOT_CONVERGED_SNIPPET) is False
    assert orca_frames.opt_converged(_EXTOPT_OPT_CONVERGED_SNIPPET) is True
    assert orca_frames.opt_converged("FINAL SINGLE POINT ENERGY     -76.0\n") is None


# ---------------------------------------------------------------------------
# GH #16：频率文本回退（外部 MLIP ExtOpt NumFreq 日志无 SCF 块，cclib 常整体失败）
# ---------------------------------------------------------------------------

# VIBRATIONAL FREQUENCIES 块格式取自真实 ORCA NumFreq 输出（模式行
# `N: <freq> cm**-1`；虚频为负值，尾部带 ***imaginary mode*** 标记）。
_NUMFREQ_BLOCK_WITH_IMAGINARY = (
    "VIBRATIONAL FREQUENCIES\n"
    "-----------------------\n"
    "\n"
    "Scaling factor for frequencies =  1.0000\n"
    "\n"
    "   0:      -294.67 cm**-1 ***imaginary mode***\n"
    "   1:         0.00 cm**-1\n"
    "   2:       289.50 cm**-1\n"
    "   3:       458.10 cm**-1\n"
    "\n"
    "\n"
    "-------------\n"
    "NORMAL MODES\n"
    "-------------\n"
)


def test_vibfreqs_from_text_parses_imaginary_as_negative():
    """GH #16：虚频以负值解析（***imaginary mode*** 标记行照常取数）。"""
    freqs = orca_frames.vibfreqs_from_text(_NUMFREQ_BLOCK_WITH_IMAGINARY)
    assert freqs == pytest.approx([-294.67, 0.00, 289.50, 458.10])


def test_vibfreqs_from_text_takes_only_last_block():
    """多次打印频率块（如 Opt+NumFreq 逐周期）时只取最后一个块。"""
    first_block = (
        "VIBRATIONAL FREQUENCIES\n"
        "-----------------------\n"
        "\n"
        "   0:       111.11 cm**-1\n"
    )
    freqs = orca_frames.vibfreqs_from_text(first_block + "\n" + _NUMFREQ_BLOCK_WITH_IMAGINARY)
    assert freqs == pytest.approx([-294.67, 0.00, 289.50, 458.10])


def test_vibfreqs_from_text_no_block_returns_empty():
    """无频率块的日志返回空列表（调用方保持 None 语义，不得当成零虚频）。"""
    assert orca_frames.vibfreqs_from_text("FINAL SINGLE POINT ENERGY     -76.0\n") == []


def test_vibfreqs_from_text_co2_fixture_matches_block():
    """co2 fixture 回归：文本解析结果与块内数值一致（前 5 个零为平动/转动模式）。"""
    text = (ORCA_FIXTURES / "co2_freq_orca42.out").read_text(encoding="utf-8")
    freqs = orca_frames.vibfreqs_from_text(text)
    assert freqs == pytest.approx([0.0] * 5 + [289.50, 458.10, 1114.50, 1142.05])


# ---------------------------------------------------------------------------
# IRC 端点几何（extract_irc_endpoints / read_endpoint_geometry）
# ---------------------------------------------------------------------------

_IRC_ENDPOINT_XYZ = "3\nendpoint frame\nC 0.0 0.0 0.0\nN 0.0 0.0 1.2\nH 0.0 0.0 2.2\n"


def _write_synthetic_irc_log(tmp_path, name="ircjob"):
    """最小 ORCA IRC 日志：输入回显带 NAME，F 收敛、B 未收敛。"""
    log = tmp_path / "harness_calc_log.txt"  # 日志名与 ORCA 作业名刻意不同
    log.write_text(
        f"NAME = {tmp_path / name}.inp\n"
        "* FORWARD IRC *\n"
        " 0 -100.123694 -0.987880 0.009347 0.001949\n"
        " 1 -100.223694 -0.887880 0.009347 0.001949\n"
        "THE IRC HAS CONVERGED\n"
        "* BACKWARD IRC *\n"
        " 0 -100.123694 -0.987880 0.009347 0.001949\n"
        " 1 -100.023694 -0.787880 0.009347 0.001949\n",
        encoding="utf-8",
    )
    return log


def test_extract_irc_endpoints_fixture_without_sidecars_is_unavailable():
    """真实 IRC fixture 无边文件：收敛标记可读，端点几何必须标 unavailable，
    不得用同一侧或末帧顶替。"""
    result = orca_frames.extract_irc_endpoints(str(ORCA_FIXTURES / "hcn_irc_orca60.out"))
    for direction in ("forward", "backward"):
        assert result[direction]["converged"] is True
        assert result[direction]["availability"] == "unavailable"
        assert result[direction]["geometry_ref"] is None
        assert orca_frames.read_endpoint_geometry(result[direction]) is None


def test_extract_irc_endpoints_uses_input_echo_name_and_prefers_final_files(tmp_path):
    """harness 日志名与作业名不同时按输入回显的 NAME 定位边文件；
    final endpoint 文件优先于 trajectory。"""
    log = _write_synthetic_irc_log(tmp_path)
    (tmp_path / "ircjob_IRC_F.xyz").write_text(_IRC_ENDPOINT_XYZ, encoding="utf-8")
    (tmp_path / "ircjob_IRC_B.xyz").write_text(_IRC_ENDPOINT_XYZ, encoding="utf-8")
    # 同时放置 trajectory：final endpoint 文件必须赢
    (tmp_path / "ircjob_IRC_F_trj.xyz").write_text(
        _IRC_ENDPOINT_XYZ.replace("endpoint frame", "trj frame"), encoding="utf-8"
    )

    result = orca_frames.extract_irc_endpoints(str(log))
    assert result["forward"]["origin"] == "final_endpoint_file"
    assert result["forward"]["availability"] == "available"
    assert result["forward"]["converged"] is True
    assert result["backward"]["converged"] is False
    xyz = orca_frames.read_endpoint_geometry(result["forward"])
    assert xyz is not None and "endpoint frame" in xyz


def test_read_endpoint_geometry_trajectory_returns_last_frame(tmp_path):
    """只有 F/B trajectory 时取末帧，origin 标记为 trajectory_last_frame。"""
    log = _write_synthetic_irc_log(tmp_path)
    frames = [
        _IRC_ENDPOINT_XYZ.replace("endpoint frame", f"trj frame {i}") for i in range(3)
    ]
    (tmp_path / "ircjob_IRC_F_trj.xyz").write_text("".join(frames), encoding="utf-8")

    result = orca_frames.extract_irc_endpoints(str(log))
    forward = result["forward"]
    assert forward["origin"] == "trajectory_last_frame"
    xyz = orca_frames.read_endpoint_geometry(forward)
    assert xyz is not None
    assert "trj frame 2" in xyz
    assert "trj frame 0" not in xyz
