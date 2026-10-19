"""ORCA frames: engine/job-type detection, thermochemistry, frame extraction."""

from pathlib import Path

import pytest

pytest.importorskip("cclib", reason="orca_frames requires cclib (chem extra)")

from cloudra.tools.core import orca_frames
from cloudra.tools.core.qm_engine import detect_qm_engine

ORCA_FIXTURES = Path(__file__).parent / "fixtures" / "orca"
GAUSSIAN_FIXTURES = Path(__file__).parent / "fixtures" / "gaussian"


def test_frequency_without_cartesian_table_uses_native_input_echo():
    """Actual IA8 NumFreq output has inline input coordinates but no Cartesian table."""
    from cloudra.tools.core.irc_evidence import probe_log
    from cloudra.tools.core.irc_path import parse_xyz

    path = ORCA_FIXTURES / 'ch2oo_numfreq_input_echo.out'
    n_imag, geometry = probe_log(path)
    assert n_imag == 1
    assert geometry is not None
    assert geometry[0] == ['C', 'O', 'O', 'H', 'H']
    assert geometry[1][0] == pytest.approx([-.423508, -.004670, .002086])
    assert parse_xyz(orca_frames.final_xyz_from_text(path.read_text())) == geometry


def test_optimization_input_echo_is_never_a_final_geometry():
    text = (ORCA_FIXTURES / 'ch2oo_numfreq_input_echo.out').read_text()
    text = text.replace('! NumFreq GFN2-xTB TightSCF', '! Opt GFN2-xTB TightSCF')
    assert orca_frames.final_xyz_from_text(text) == ''


def test_irc_anchor_can_use_its_native_input_echo(tmp_path):
    from cloudra.tools.core.irc_evidence import irc_start_geometry

    text = (ORCA_FIXTURES / 'ch2oo_numfreq_input_echo.out').read_text()
    text = text.replace('! NumFreq GFN2-xTB TightSCF', '! IRC GFN2-xTB TightSCF')
    text += 'Intrinsic Reaction Coordinate Calculation\n* FORWARD IRC *\n* BACKWARD IRC *\n'
    path = tmp_path / 'irc.out'
    path.write_text(text)
    geometry = irc_start_geometry(path)
    assert geometry is not None
    assert geometry[0] == ['C', 'O', 'O', 'H', 'H']
    assert geometry[1][0] == pytest.approx([-.423508, -.004670, .002086])


def test_orca_xtb_optts_short_dipole_block_retains_final_geometry():
    """IA8 job 739: cclib assumes dipole contribution rows absent in GFN2-xTB."""
    frames = orca_frames.extract_frames(str(ORCA_FIXTURES / "ch2oo_optts_gfn2_orca611.out"))
    assert len(frames) == 10
    assert frames[-1].converged is True
    assert frames[-1].frequencies_cm == []  # Optimization alone cannot verify a TS.
    assert frames[-1].electronic_energy_hartree == pytest.approx(-11.083861872140)
    rows = [line.split() for line in frames[-1].xyz.splitlines()[2:]]
    assert [row[0] for row in rows] == ["C", "O", "O", "H", "H"]
    for row, expected in zip(rows, [
        [-0.423530, -0.004703, 0.002036],
        [0.591597, -0.682213, -0.372134],
        [1.476819, 0.188463, 0.229121],
        [-1.261767, -0.509001, 0.485509],
        [-0.434262, 1.076129, -0.083405],
    ], strict=True):
        assert [float(value) for value in row[1:]] == pytest.approx(expected)


def test_final_frame_energy_matches_orca_hartree_line():
    log = ORCA_FIXTURES / "dvb_opt_orca42.out"
    frames = orca_frames.extract_frames(str(log))
    assert frames[-1].electronic_energy_hartree == pytest.approx(
        orca_frames.final_energy_hartree(log.read_text()), rel=0, abs=1e-7,
    )


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
    assert thermo["thermal_enthalpy_correction_hartree"] == pytest.approx(0.01088379)
    assert thermo["thermal_gibbs_correction_hartree"] == pytest.approx(-0.01495983)
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
    assert all(f.electronic_energy_hartree is not None for f in frames)
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
    """log_parser 走 ORCA 引擎时透出 IRC 信息字段（点数/收敛/端点能量）。

    这些字段只是信息性记录：short_irc 阶段绑定已改为几何方向区间证明
    （dag 闸门经 irc_evidence.verify_short_irc_direction 重解析日志本身），
    不再消费这里的收敛/点数标志。"""
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


def test_sidecar_roots_find_parent_dir_of_cloudra_capture(tmp_path):
    """harness 布局：stdout 捕获在 <作业目录>/.cloudra/calc-<id>.out.log，
    边文件留在父目录；NAME 只带文件名（相对路径）时也必须解析到。"""
    jobdir = tmp_path / "ts"
    (jobdir / ".cloudra").mkdir(parents=True)
    log = jobdir / ".cloudra" / "calc-320.out.log"
    log.write_text(
        "NAME = ircjob.inp\n* FORWARD IRC *\n 0 -100.0 -1.0 0.01 0.001\n",
        encoding="utf-8",
    )
    (jobdir / "ircjob_IRC_F_trj.xyz").write_text(_IRC_ENDPOINT_XYZ, encoding="utf-8")

    result = orca_frames.extract_irc_endpoints(str(log))
    assert result["forward"]["origin"] == "trajectory_last_frame"
    xyz = orca_frames.read_endpoint_geometry(result["forward"])
    assert xyz is not None and "endpoint frame" in xyz


@pytest.mark.parametrize('neighbor_in_parent', [False, True])
def test_irc_reader_never_uses_another_jobs_only_backward_endpoint(tmp_path, neighbor_in_parent):
    jobdir = tmp_path / 'current'
    jobdir.mkdir()
    log = _write_synthetic_irc_log(jobdir, 'current')
    forward = jobdir / 'current_IRC_F.xyz'
    forward.write_text(_IRC_ENDPOINT_XYZ)
    neighbor_dir = tmp_path if neighbor_in_parent else jobdir
    (neighbor_dir / 'another_IRC_B.xyz').write_text(_IRC_ENDPOINT_XYZ.replace('endpoint frame', 'foreign job'))

    result = orca_frames.extract_irc_endpoints(str(log))

    assert result['forward']['geometry_ref'] == str(forward)
    assert result['backward']['geometry_ref'] is None
    assert result['backward']['availability'] == 'unavailable'


def test_irc_log_without_native_name_never_adopts_unique_neighbor_pair(tmp_path):
    log = _write_synthetic_irc_log(tmp_path)
    log.write_text('\n'.join(log.read_text().splitlines()[1:]) + '\n')
    for direction in ('F', 'B'):
        (tmp_path / f'another_IRC_{direction}.xyz').write_text(_IRC_ENDPOINT_XYZ)

    result = orca_frames.extract_irc_endpoints(str(log))

    assert all(endpoint['geometry_ref'] is None for endpoint in result.values())


# ---------------------------------------------------------------------------
# 末帧几何文本回退（cclib 对 ORCA 6.1 日志整体崩溃时的权威通道）
# ---------------------------------------------------------------------------

_CARTESIAN_BLOCK = (
    "--------------------------------\n"
    "CARTESIAN COORDINATES (ANGSTROEM)\n"
    "--------------------------------\n"
    "  C      0.000000    0.000000    0.000000\n"
    "  N      0.000000    0.000000    1.200000\n"
    "  H      0.000000    0.000000    2.200000\n"
    "\n"
)


def test_final_xyz_from_text_takes_last_block():
    earlier = _CARTESIAN_BLOCK.replace("1.200000", "9.999999")
    text = earlier + "some log noise\n" + _CARTESIAN_BLOCK + "ORCA TERMINATED NORMALLY\n"
    xyz = orca_frames.final_xyz_from_text(text)
    assert xyz.startswith("3\n")
    assert "1.200000" in xyz and "9.999999" not in xyz


def test_final_xyz_from_text_no_block_returns_empty():
    assert orca_frames.final_xyz_from_text("FINAL SINGLE POINT ENERGY -76.0\n") == ""


def test_final_xyz_with_text_fallback_on_cclib_hostile_log(tmp_path, monkeypatch):
    """cclib 整体崩溃（帧为空，ORCA 6.1 实况）时回退文本权威
    CARTESIAN COORDINATES 块。"""
    monkeypatch.setattr(orca_frames, "extract_frames", lambda path: [])
    log = tmp_path / "calc-1.out.log"
    log.write_text(
        "ORCA 6.1 log that crashes cclib\n" + _CARTESIAN_BLOCK,
        encoding="utf-8",
    )
    xyz = orca_frames.final_xyz_with_text_fallback(str(log))
    assert "1.200000" in xyz


# ---------------------------------------------------------------------------
# NEB：必须被识别，但只跑路径搜索的 NEB 不得退化成单点
# ---------------------------------------------------------------------------


def test_neb_is_recognised_from_the_keyword_echo():
    """ORCA 在输出开头回显输入文件的 `!` 行；NEB 由该关键字识别。

    测试用的是关键字回显片段（ORCA 的既有格式，本目录其它 fixture 已覆盖），
    **不是伪造的引擎输出**：这里只验证关键字扫描这一纯函数。
    """
    assert orca_frames.detect_job_types_from_text("|  1> ! NEB\n") == {"neb"}
    # NEB-TS 后面还会做 TS 优化：两个类型都要给出来
    assert orca_frames.detect_job_types_from_text("|  1> ! NEB-TS\n|  2> ! OPT\n") == {"neb", "opt"}
    # 普通单点不受影响
    assert orca_frames.detect_job_types_from_text("|  1> ! wB97X-D def2-SVP\n") == {"sp"}


def test_neb_only_log_yields_no_frames_instead_of_a_fake_single_point(tmp_path):
    """只跑路径搜索的 NEB：逐图像几何尚未解析 → 返回空，绝不退化成"一个结构"。

    把一条路径报成一个单点比什么都不报更糟：下游会把路径当成一个几何来用。
    """
    log = tmp_path / "neb_only.out"
    log.write_text("|  1> ! NEB\n", encoding="utf-8")
    assert orca_frames.extract_frames(str(log)) == []


def test_neb_ts_log_still_extracts_the_ts_optimisation_frames(tmp_path):
    """NEB-TS：带优化段，逐帧几何应照常由优化段解析（不因识别出 neb 而丢帧）。

    这里**不能**用"只有关键字、没有任何 ORCA 内容"的桩日志：cclib 对桩的行为取决于可选的
    Open Babel 兜底装没装（装了 → 返回空 ccData，于是得到 []；没装 → 返回 None，本模块按
    fail-loud 抛 `cclib 未能解析日志`）。CI 没装 Open Babel，桩日志上的断言只在开发机成立。
    改成在**真实**优化日志上注入 `! NEB-TS` 关键字：内容真实，帧提取与 cclib 兜底无关。
    """
    source = ORCA_FIXTURES / "dvb_opt_orca42.out"
    log = tmp_path / "neb_ts.out"
    log.write_text("|  1> ! NEB-TS\n" + source.read_text(encoding="utf-8"), encoding="utf-8")
    assert orca_frames.detect_job_types(str(log)) == {"neb", "opt"}
    # neb 不接管：有优化段时几何仍走优化段，帧数与非 NEB 的同一份日志一致
    assert len(orca_frames.extract_frames(str(log))) == len(
        orca_frames.extract_frames(str(source))
    ) != 0


# ---------------------------------------------------------------------------
# NEB：逐图像几何在边文件里，读不到必须给出**具体原因**（不许静默返回空）
# ---------------------------------------------------------------------------

NEB_FIXTURE = ORCA_FIXTURES / "neb_hcn" / "neb.out"


def test_neb_frames_come_from_the_per_image_side_files():
    """真实 ORCA NEB-TS 运行：逐图像几何从 <作业名>_im<N>.xyz 边文件读出来。

    主输出里只有迭代表，几何在边文件里——"日志里读不到几何"不等于"作业没有几何"。
    """
    frames = orca_frames.extract_frames(str(NEB_FIXTURE))
    assert [f.frame for f in frames] == [0, 4, 8]
    # 真实能量（Eh），来自边文件注释行 `Coordinates from ORCA-job neb_im8 E -93.03...`
    assert frames[0].electronic_energy_hartree == pytest.approx(-93.300300911883, abs=1e-9)
    assert frames[-1].electronic_energy_hartree == pytest.approx(-93.031209778059, abs=1e-9)
    for frame in frames:
        assert frame.xyz.splitlines()[0].strip() == "3"


def test_neb_reason_is_none_when_frames_are_actually_available():
    assert orca_frames.frames_unavailable_reason(str(NEB_FIXTURE)) is None


def test_neb_missing_side_files_yields_an_explicit_reason(tmp_path):
    """边文件缺失时：返回空 + **说明是 NEB、几何在边文件里**，而不是一句"没有关键帧"。"""
    log = tmp_path / "neb.out"
    log.write_text(NEB_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    assert orca_frames.extract_frames(str(log)) == []
    reason = orca_frames.frames_unavailable_reason(str(log))
    assert reason is not None
    assert "ORCA NEB job" in reason
    assert "_im<N>.xyz" in reason


def test_irc_reason_explains_where_the_path_points_live():
    """IRC 同理：主输出没有逐点坐标，原因里要指明边文件与可用的替代入口。"""
    reason = orca_frames.frames_unavailable_reason(str(ORCA_FIXTURES / "hcn_irc_orca60.out"))
    assert reason is not None
    assert "IRC" in reason
    assert "extract_irc_endpoints" in reason


def test_frequencies_with_text_fallback_survives_cclib_failure(tmp_path):
    """cclib 对 ORCA 6.1 日志裸抛 IndexError 时，评分链路的频率判定走
    文本权威 VIBRATIONAL FREQUENCIES 块——虚频个数必须仍然可判定。"""
    log = tmp_path / "calc-296.out.log"
    log.write_text(
        "not a parseable ORCA log for cclib\n"
        "VIBRATIONAL FREQUENCIES\n"
        "-----------------------\n"
        "   0:         0.00 cm**-1\n"
        "   1:         0.00 cm**-1\n"
        "   2:      -164.95 cm**-1  ***imaginary mode***\n"
        "   3:       150.30 cm**-1\n"
        "   4:       264.86 cm**-1\n",
        encoding="utf-8",
    )
    freqs = orca_frames.frequencies_with_text_fallback(str(log))
    assert sum(1 for f in freqs if f < 0) == 1
    assert freqs[2] == -164.95

    no_block = tmp_path / "sp.out.log"
    no_block.write_text("no frequency block here\n", encoding="utf-8")
    assert orca_frames.frequencies_with_text_fallback(str(no_block)) == []


# ---------------------------------------------------------------------------
# GH #44：cclib 对 ORCA 6.1 日志在 SCF 收敛段裸抛 IndexError（scfvalues 为空
# 时 [-1] 越界）——opt/ts 与 sp 帧提取回退文本权威通道
# ---------------------------------------------------------------------------

# 最小 ORCA 6.1 风格 OptTS+Freq 日志骨架：两个优化周期 + 收敛后的最终几何
# 尾块（与周期 2 几何逐字符相同 → 去重）+ 频率块（一个虚频）。
_ORCA61_OPTTS_LOG = (
    "                                 *****  ORCA VERSION: 6.1.1  *****\n"
    "|  1> ! B3LYP D3BJ def2-SVP OptTS Freq\n"
    "GEOMETRY OPTIMIZATION CYCLE   1\n"
    "--------------------------------\n"
    "CARTESIAN COORDINATES (ANGSTROEM)\n"
    "--------------------------------\n"
    "  C      0.000000    0.000000    0.000000\n"
    "  N      0.000000    0.000000    1.100000\n"
    "  H      0.000000    0.000000    2.200000\n"
    "\n"
    "Current Energy                          ....  -100.000001000 Eh\n"
    "GEOMETRY OPTIMIZATION CYCLE   2\n"
    "--------------------------------\n"
    "CARTESIAN COORDINATES (ANGSTROEM)\n"
    "--------------------------------\n"
    "  C      0.000000    0.000000    0.000000\n"
    "  N      0.000000    0.000000    1.200000\n"
    "  H      0.000000    0.000000    2.200000\n"
    "\n"
    "Current Energy                          ....  -100.000002000 Eh\n"
    "                    ***        THE OPTIMIZATION HAS CONVERGED     ***\n"
    "--------------------------------\n"
    "CARTESIAN COORDINATES (ANGSTROEM)\n"
    "--------------------------------\n"
    "  C      0.000000    0.000000    0.000000\n"
    "  N      0.000000    0.000000    1.200000\n"
    "  H      0.000000    0.000000    2.200000\n"
    "\n"
    "FINAL SINGLE POINT ENERGY     -100.000002500000\n"
    "VIBRATIONAL FREQUENCIES\n"
    "-----------------------\n"
    "   0:         0.00 cm**-1\n"
    "   1:      -164.95 cm**-1  ***imaginary mode***\n"
    "   2:       150.30 cm**-1\n"
    "****ORCA TERMINATED NORMALLY****\n"
)


def _crash_ccread(text, source_desc=""):
    raise ValueError(f"日志解析器内部索引越界（疑似截断或损坏的计算日志）: {source_desc}")


def test_opt_frames_text_fallback_survives_cclib61_crash(monkeypatch):
    """cclib 崩溃时 opt/ts 帧走文本权威通道：逐周期几何+Current Energy 配对，
    收敛尾块与末周期去重，末帧挂收敛标记与频率。"""
    monkeypatch.setattr(orca_frames, "_ccread_from_text", _crash_ccread)
    frames = orca_frames.extract_frames_from_text(_ORCA61_OPTTS_LOG)
    assert [f.frame for f in frames] == [0, 1]  # 尾块去重，不重复计帧
    assert frames[0].electronic_energy_hartree == pytest.approx(-100.000001)
    assert frames[1].electronic_energy_hartree == pytest.approx(-100.000002)
    assert "1.100000" in frames[0].xyz and "1.200000" in frames[1].xyz
    assert frames[1].converged is True
    assert frames[1].frequencies_cm[1] == -164.95


def test_opt_frames_fallback_appends_differing_final_block(monkeypatch):
    """收敛尾块与末周期几何不同（如 freq 段重打印了微调几何）时追加为末帧。"""
    monkeypatch.setattr(orca_frames, "_ccread_from_text", _crash_ccread)
    log = _ORCA61_OPTTS_LOG.replace(
        "  N      0.000000    0.000000    1.200000\n"
        "  H      0.000000    0.000000    2.200000\n"
        "\n"
        "FINAL SINGLE POINT ENERGY",
        "  N      0.000000    0.000000    1.200500\n"
        "  H      0.000000    0.000000    2.200000\n"
        "\n"
        "FINAL SINGLE POINT ENERGY",
    )
    frames = orca_frames.extract_frames_from_text(log)
    assert [f.frame for f in frames] == [0, 1, 2]
    assert frames[2].electronic_energy_hartree == pytest.approx(-100.0000025)
    assert "1.200500" in frames[2].xyz
    assert frames[2].converged is True


def test_sp_frames_text_fallback_survives_cclib61_crash(monkeypatch):
    """单点日志 cclib 崩溃时回退：末帧几何 + FINAL SP + 频率块。"""
    monkeypatch.setattr(orca_frames, "_ccread_from_text", _crash_ccread)
    frames = orca_frames.extract_frames_from_text(
        "|  1> ! B3LYP def2-SVP\n"
        + _CARTESIAN_BLOCK
        + "FINAL SINGLE POINT ENERGY     -76.400000000001\n"
    )
    assert len(frames) == 1
    assert frames[0].electronic_energy_hartree == pytest.approx(-76.400000000001)
    assert "1.200000" in frames[0].xyz


@pytest.mark.asyncio
async def test_format_converter_log_to_xyz_end_to_end_on_cclib61_crash(tmp_path, monkeypatch):
    """GH #44 的 agent 面回归：format_converter log→xyz 在 cclib 崩溃的
    ORCA 6.1 OptTS 日志上必须给出最终几何而不是越界报错。"""
    from types import SimpleNamespace

    from cloudra.tools.Chemtool.format_converter import (
        FormatConverter,
        FormatConverter_input_schema,
    )

    monkeypatch.setattr(orca_frames, "_ccread_from_text", _crash_ccread)
    log = tmp_path / "calc-528.out.log"
    log.write_text(_ORCA61_OPTTS_LOG, encoding="utf-8")
    out = tmp_path / "final.xyz"
    result = await FormatConverter(
        subagent=SimpleNamespace(working_directory=str(tmp_path))
    ).tool_call(
        FormatConverter_input_schema(
            input_path=str(log), output_path=str(out),
            input_format="log", output_format="xyz",
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    assert "1.200000" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize('base_exists', [True, False])
def test_irc_explicit_echo_base_uses_only_exact_sidecars(tmp_path, base_exists):
    log = _write_synthetic_irc_log(tmp_path, 'input')
    log.write_text('O   R   C   A\nINPUT FILE\nNAME = input.inp\n|  1> ! IRC\n'
                   '|  2> %base "native"\n|  3> * xyz 0 1\n'
                   + log.read_text())
    for direction in ('F', 'B'):
        for stem in ('foreign', 'input', log.stem):
            (tmp_path / f'{stem}_IRC_{direction}.xyz').write_text(_IRC_ENDPOINT_XYZ)
        if base_exists:
            (tmp_path / f'native_IRC_{direction}.xyz').write_text(_IRC_ENDPOINT_XYZ)
    result = orca_frames.extract_irc_endpoints(str(log))
    for name, direction in [('forward', 'F'), ('backward', 'B')]:
        expected = str(tmp_path / f'native_IRC_{direction}.xyz') if base_exists else None
        assert result[name]['geometry_ref'] == expected


@pytest.mark.parametrize('capture', [False, True])
def test_explicit_base_endpoints_survive_dag_snapshot(tmp_path, capture):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    log = _write_synthetic_irc_log(tmp_path, 'input')
    log.write_text('O   R   C   A\n|  1> %base "native"\n' + log.read_text())
    if capture:
        capture_dir = tmp_path / '.cloudra'
        capture_dir.mkdir()
        log = log.rename(capture_dir / 'calc-123.out.log')
    for direction in ('F', 'B'):
        (tmp_path / f'native_IRC_{direction}.xyz').write_text(_IRC_ENDPOINT_XYZ)
    snapshot = snapshot_evidence_file(log, tmp_path)
    for direction in ('F', 'B'):
        (tmp_path / f'native_IRC_{direction}.xyz').unlink()
    endpoints = orca_frames.extract_irc_endpoints(snapshot.snapshot_path)
    assert all(orca_frames.read_endpoint_geometry(endpoint) == _IRC_ENDPOINT_XYZ
               for endpoint in endpoints.values())


@pytest.mark.parametrize('directive', ['%base "foreign"', '|  2> # %base "foreign"'])
def test_base_outside_native_directive_does_not_authorize_foreign_endpoints(tmp_path, directive):
    log = _write_synthetic_irc_log(tmp_path)
    log.write_text(directive + '\n' + log.read_text())
    for direction in ('F', 'B'):
        (tmp_path / f'foreign_IRC_{direction}.xyz').write_text(_IRC_ENDPOINT_XYZ)
    assert all(endpoint['geometry_ref'] is None
               for endpoint in orca_frames.extract_irc_endpoints(str(log)).values())
