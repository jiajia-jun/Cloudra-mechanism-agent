"""Gaussian 日志关键帧提取测试（cloudra/tools/core/gaussian_frames.py）。

fixtures 为真实 Gaussian 输出日志，来源见 tests/fixtures/gaussian/README.md：
- hcn_ts_irc_g16.log：G16 IRC，正/反向各 10 点 + TS，含 Summary of reaction path following 汇总表
- h2_scan_g09.log：G09 relaxed PES scan（opt=ModRedundant），100 步 H-H 键长扫描
- water_opt_freq_g16.out：G16 opt+freq，5 个优化步，3 个频率
"""

import csv
from pathlib import Path

import pytest

from cloudra.tools.core.gaussian_frames import (
    EV_PER_HARTREE,
    detect_job_types,
    extract_frames,
    extract_irc,
    frames_to_csv,
)

FIXTURES = Path(__file__).parent / "fixtures" / "gaussian"
IRC_LOG = FIXTURES / "hcn_ts_irc_g16.log"
SCAN_LOG = FIXTURES / "h2_scan_g09.log"
OPT_FREQ_LOG = FIXTURES / "water_opt_freq_g16.out"

TS_ENERGY = -93.114020  # IRC 日志中 "Energies reported relative to the TS energy of"


def test_final_frame_energy_matches_gaussian_hartree_line():
    # cclib stores energies in eV using its own conversion constant.
    frames = extract_frames(str(OPT_FREQ_LOG))
    assert frames[-1].electronic_energy_hartree == pytest.approx(
        -74.9659011806, rel=0, abs=1e-7,
    )


# ---------------------------------------------------------------------------
# detect_job_types
# ---------------------------------------------------------------------------

def _write_route(tmp_path, route: str) -> Path:
    """写一个只含路由回显行的最小日志。"""
    p = tmp_path / "job.log"
    p.write_text(f" {route}\n")
    return p


@pytest.mark.parametrize(("route", "expected"), [
    ("# opt freq rb3lyp/6-311++g(3df,3pd) geom=connectivity", {"opt", "freq"}),
    ("# opt=(ts,noeigen,calcfc) freq b3lyp/6-31g(d)", {"opt", "ts", "freq"}),
    ("# opt=ts b3lyp/6-31g(d)", {"opt", "ts"}),
    ("# hf/sto-3g", {"sp"}),
    ("# hf/sto-3g freq", {"sp", "freq"}),
    ("#p irc=(lqa,calcfc,maxpoint=80) b3lyp/6-31g(d)", {"irc"}),
    ("# opt=scan b3lyp/6-31g(d)", {"opt", "scan"}),
])
def test_detect_job_types_from_route(tmp_path, route, expected):
    assert detect_job_types(str(_write_route(tmp_path, route))) == expected


def test_detect_job_types_wrapped_route(tmp_path):
    """路由跨行缠绕（token 中间断行）时仍能识别。"""
    p = tmp_path / "job.log"
    p.write_text(" #p external=\"x\" irc=(calcall,stepsize=10,m\n axpoint=100,lqa) geom=allcheck\n")
    assert detect_job_types(str(p)) == {"irc"}


def test_detect_job_types_real_fixtures():
    assert detect_job_types(str(IRC_LOG)) == {"irc"}
    # ModRedundant 扫描路由里没有 scan 关键词，靠结构标记兜底；opt 同时命中
    assert detect_job_types(str(SCAN_LOG)) == {"opt", "scan"}
    assert detect_job_types(str(OPT_FREQ_LOG)) == {"opt", "freq"}


# ---------------------------------------------------------------------------
# IRC 解析
# ---------------------------------------------------------------------------

def test_irc_frame_count_and_paths():
    frames, meta = extract_irc(str(IRC_LOG))
    assert len(frames) == 21  # 正向 10 + 反向 10 + TS
    assert meta["num_points_forward"] == 10
    assert meta["num_points_backward"] == 10

    # 反应坐标全局单调递增（反向端点 → TS → 正向端点）
    rx = [f.reaction_coordinate for f in frames]
    assert all(rx[i] < rx[i + 1] for i in range(len(rx) - 1))
    assert meta["rx_coord_range"] == (pytest.approx(-0.80848), pytest.approx(0.80848))


def test_irc_energies_match_summary_table():
    frames, meta = extract_irc(str(IRC_LOG))
    # 汇总表首行 (rx=-0.80848) 相对能量 -0.01110，末行 (rx=0.80848) 相对 -0.01565
    assert frames[0].electronic_energy_hartree == pytest.approx(TS_ENERGY - 0.01110, abs=1e-6)
    assert frames[-1].electronic_energy_hartree == pytest.approx(TS_ENERGY - 0.01565, abs=1e-6)
    # TS 帧：rx=0，能量即 TS 能量
    ts_frame = next(f for f in frames if f.reaction_coordinate == 0.0)
    assert ts_frame.electronic_energy_hartree == pytest.approx(TS_ENERGY, abs=1e-6)
    assert meta["endpoint_energies_hartree"] == (
        pytest.approx(frames[0].electronic_energy_hartree),
        pytest.approx(frames[-1].electronic_energy_hartree),
    )


def test_irc_path_assignment():
    frames, _meta = extract_irc(str(IRC_LOG))
    # 该日志 FORWARD=Path 1 对应正反应坐标，REVERSE=Path 2 对应负反应坐标
    for f in frames:
        if f.reaction_coordinate > 0:
            assert f.path_number == 1
        elif f.reaction_coordinate < 0:
            assert f.path_number == 2


def test_irc_endpoint_convergence():
    """该日志两个方向都因 maxsteps 耗尽终止，端点不收敛。"""
    frames, meta = extract_irc(str(IRC_LOG))
    assert frames[0].converged is False
    assert frames[-1].converged is False
    assert meta["forward_converged"] is False
    assert meta["backward_converged"] is False
    # 中间帧不标收敛
    assert all(f.converged is None for f in frames[1:-1])


def test_irc_xyz_blocks():
    frames, _meta = extract_irc(str(IRC_LOG))
    non_ts = [f for f in frames if f.reaction_coordinate != 0.0]
    assert non_ts
    for f in non_ts:
        lines = f.xyz.splitlines()
        assert int(lines[0]) == 3  # HCN 三原子
        symbols = [line.split()[0] for line in lines[2:]]
        assert sorted(symbols) == ["C", "H", "N"]


# ---------------------------------------------------------------------------
# scan / opt+freq 解析
# ---------------------------------------------------------------------------

def test_scan_frames():
    frames = extract_frames(str(SCAN_LOG))
    assert len(frames) == 101  # 初值 + 100 个扫描步
    # 扫描参数 0.6 → 1.6，等步长 0.01
    rx = [f.reaction_coordinate for f in frames]
    assert rx[0] == pytest.approx(0.6)
    assert rx[-1] == pytest.approx(1.6)
    assert rx[1] - rx[0] == pytest.approx(0.01)
    # 每帧能量齐全且 xyz 为 H2 双原子
    for f in frames:
        assert f.electronic_energy_hartree is not None
        assert int(f.xyz.splitlines()[0]) == 2


def test_opt_freq_frames():
    frames = extract_frames(str(OPT_FREQ_LOG))
    assert len(frames) == 5
    # 仅末帧标收敛并挂频率
    assert frames[-1].converged is True
    assert len(frames[-1].frequencies_cm) == 3
    for f in frames[:-1]:
        assert f.converged is None
        assert f.frequencies_cm == []
    # 频率有符号（该体系无虚频，均为正）
    assert all(v > 0 for v in frames[-1].frequencies_cm)


# ---------------------------------------------------------------------------
# frames_to_csv
# ---------------------------------------------------------------------------

def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_frames_to_csv_roundtrip(tmp_path):
    frames, _meta = extract_irc(str(IRC_LOG))
    out = tmp_path / "irc.csv"
    frames_to_csv(frames, str(out))

    rows = _read_csv(out)
    assert len(rows) == len(frames)
    assert list(rows[0].keys()) == [
        "frame", "path_number", "reaction_coordinate",
        "electronic_energy_hartree", "electronic_energy_ev", "frequencies_cm", "xyz",
    ]
    # 数值可回读
    assert float(rows[0]["reaction_coordinate"]) == pytest.approx(-0.80848)
    assert float(rows[0]["electronic_energy_hartree"]) == pytest.approx(TS_ENERGY - 0.01110, abs=1e-6)
    assert float(rows[0]["electronic_energy_ev"]) == pytest.approx(
        (TS_ENERGY - 0.01110) * EV_PER_HARTREE, abs=1e-4
    )
    assert int(rows[0]["path_number"]) == 2
    # 多行 xyz 字段靠 csv 引号机制正确回读
    assert int(rows[0]["xyz"].splitlines()[0]) == 3
    # IRC 帧无频率 → 空字段
    assert rows[0]["frequencies_cm"] == ""


def test_frames_to_csv_frequencies_format(tmp_path):
    frames = extract_frames(str(OPT_FREQ_LOG))
    out = tmp_path / "opt_freq.csv"
    frames_to_csv(frames, str(out))

    rows = _read_csv(out)
    freq_str = rows[-1]["frequencies_cm"]
    parts = freq_str.split(";")
    assert len(parts) == 3
    assert all(float(p) > 0 for p in parts)


# ---------------------------------------------------------------------------
# format_converter log→csv 端到端
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_format_converter_log_to_csv(tmp_path):
    from cloudra.tools.Chemtool.format_converter import (
        FormatConverter,
        FormatConverter_input_schema,
    )

    out = tmp_path / "frames.csv"
    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(OPT_FREQ_LOG),
            input_format="log",
            output_format="csv",
            output_path=str(out),
        ),
        session=None,
    )
    assert result.is_success is True
    assert "opt+freq" in result.message
    assert "5 frames" in result.message
    rows = _read_csv(out)
    assert len(rows) == 5
    assert int(rows[-1]["xyz"].splitlines()[0]) == 3


@pytest.mark.asyncio
async def test_format_converter_log_to_csv_irc(tmp_path):
    from cloudra.tools.Chemtool.format_converter import (
        FormatConverter,
        FormatConverter_input_schema,
    )

    out = tmp_path / "irc.csv"
    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(IRC_LOG),
            input_format="log",
            output_format="csv",
            output_path=str(out),
        ),
        session=None,
    )
    assert result.is_success is True
    assert "irc" in result.message
    assert "21 frames" in result.message


@pytest.mark.asyncio
async def test_format_converter_log_to_xyz(tmp_path):
    from cloudra.tools.Chemtool.format_converter import (
        FormatConverter,
        FormatConverter_input_schema,
    )

    out_xyz = tmp_path / "water_final.xyz"
    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(OPT_FREQ_LOG),
            input_format="log",
            output_format="xyz",
            output_path=str(out_xyz),
        ),
        session=None,
    )
    assert result.is_success is True
    assert "extracted final frame" in result.message
    assert out_xyz.is_file()
    content = out_xyz.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert lines[0] == "3"
    assert any("O" in line for line in lines[2:])
    assert any("H" in line for line in lines[2:])


@pytest.mark.asyncio
async def test_format_converter_log_wrong_output_format(tmp_path):
    from cloudra.tools.Chemtool.format_converter import (
        FormatConverter,
        FormatConverter_input_schema,
    )

    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(OPT_FREQ_LOG),
            input_format="log",
            output_format="pdb",
            output_path=str(tmp_path / "x.pdb"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "csv" in result.message and "xyz" in result.message


@pytest.mark.asyncio
async def test_format_converter_csv_requires_log_input(tmp_path):
    from cloudra.tools.Chemtool.format_converter import (
        FormatConverter,
        FormatConverter_input_schema,
    )

    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(OPT_FREQ_LOG),
            input_format="xyz",
            output_format="csv",
            output_path=str(tmp_path / "x.csv"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "log" in result.message


@pytest.mark.asyncio
async def test_format_converter_log_missing_file(tmp_path):
    from cloudra.tools.Chemtool.format_converter import (
        FormatConverter,
        FormatConverter_input_schema,
    )

    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(tmp_path / "nonexistent.log"),
            input_format="log",
            output_format="csv",
            output_path=str(tmp_path / "x.csv"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "does not exist" in result.message


# ---------------------------------------------------------------------------
# log_parser 新字段冒烟
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_parser_job_type_and_irc():
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(IRC_LOG), properties=["job_type", "irc"]),
        session=None,
    )
    assert result.is_success is True
    assert result.job_types == ["irc"]
    assert result.irc_num_points_forward == 10
    assert result.irc_num_points_backward == 10
    assert result.irc_rx_coord_range == pytest.approx([-0.80848, 0.80848])
    assert result.irc_endpoint_energies_hartree == pytest.approx(
        [TS_ENERGY - 0.01110, TS_ENERGY - 0.01565], abs=1e-6
    )
    assert result.irc_both_directions_converged is False


@pytest.mark.asyncio
async def test_log_parser_scan():
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(SCAN_LOG), properties=["scan"]),
        session=None,
    )
    assert result.is_success is True
    assert len(result.scan_parameter) == 101
    assert len(result.scan_energies_ev) == 101
    assert result.scan_parameter[0] == pytest.approx(0.6)
    assert result.scan_parameter[-1] == pytest.approx(1.6)


@pytest.mark.asyncio
async def test_log_parser_job_type_opt_freq():
    from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema

    result = await LogParser().tool_call(
        LogParser_input_schema(log_path=str(OPT_FREQ_LOG), properties=["job_type"]),
        session=None,
    )
    assert result.is_success is True
    assert result.job_types == ["freq", "opt"]


def test_ccread_translates_cclib_internal_index_error(tmp_path, monkeypatch):
    """cclib 对截断/畸形日志内部裸抛 IndexError 时，_ccread 必须翻译成带语义的
    ValueError（疑似截断/损坏），调用方据此给出可读指引而非裸 errno 文案。"""
    import cclib

    from cloudra.tools.core.gaussian_frames import _ccread

    def _boom(path):
        raise IndexError("list index out of range")

    monkeypatch.setattr(cclib.io, "ccread", _boom)
    log = tmp_path / "truncated.log"
    log.write_text("garbage\n", encoding="utf-8")
    with pytest.raises(ValueError, match="截断"):
        _ccread(str(log))


def test_ccread_translates_cclib_assertion_with_source_and_cause(monkeypatch):
    """A third-party format assertion must enter the existing parse-error path."""
    import cclib

    from cloudra.tools.core.gaussian_frames import _ccread_from_text

    failure = AssertionError()

    def parse(_source):
        raise failure

    monkeypatch.setattr(cclib.io, "ccread", parse)
    with pytest.raises(ValueError, match="orca-xtb.log") as error:
        _ccread_from_text("native ORCA output", source_desc="orca-xtb.log")
    assert error.value.__cause__ is failure
