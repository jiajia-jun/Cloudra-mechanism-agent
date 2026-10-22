"""nmr_processor 工具测试（cloudra/tools/Chemtool/nmr_processor.py）。

全离线：用 nmrglue 合成指数衰减正弦 FID 并写入真实 NMRPipe 文件，驱动
read → 处理管线（zero-fill/FFT/去虚部/去基线）→ 坐标 → 峰提取的完整链路。
nmrglue 缺失时整体跳过。

覆盖审计发现：
- N1：peakpick 必须用 nmrglue 0.12 真实存在的 ng.peakpick.pick（pick_1d 已删除）；
- N2：zero-fill 必须用 zf(data, pad=…) 语义真正加长数据（mid=size 是 no-op）；
- N3：guess_udic 按读取器模块分派（fileiobase.create_udic 不存在）；peak_engine
      合法值对照 ng.peakpick.pick 支持的 algorithm；
- N4：合成 FID 全管线，断言峰数/峰位与 zero-fill 生效。
"""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("nmrglue")

import nmrglue as ng  # noqa: E402

import cloudra.tools.Chemtool.nmr_processor as nmr_mod  # noqa: E402
from cloudra.tools.Chemtool.nmr_processor import NMRProcessor, NMRProcessor_input_schema  # noqa: E402

# NMRPipe 1D 头部数值槽位（nmrglue pipe.fdata_dic 的字节/槽号）——测试只需写入
# read_1D / pipe.guess_udic 用到的字段。
_SLOTS = {
    "FDDIMCOUNT": 9,
    "FDDIMORDER1": 24,
    "FDF2QUADFLAG": 56,
    "FDSIZE": 99,
    "FDF1QUADFLAG": 55,
    "FDF1SW": 229,
    "FDF1OBS": 218,
    "FDF1CAR": 67,
    "FDF1FTFLAG": 222,
}

# 合成 FID 常量：两条指数衰减正弦（峰 120 Hz 与 320 Hz），观测频率 500 MHz
_N = 1024
_SW_HZ = 2000.0
_OBS_MHZ = 500.0
_F1_HZ, _F2_HZ = 120.0, 320.0


def _synthetic_fid() -> np.ndarray:
    dt = 1.0 / _SW_HZ
    t = np.arange(_N) * dt
    # 加轻微指数衰减抑制截断振铃；衰减远小于峰间距
    decay = np.exp(-t * 8.0)
    data = decay * (
        1.0 * np.exp(2j * np.pi * _F1_HZ * t)
        + 0.8 * np.exp(2j * np.pi * _F2_HZ * t)
    )
    return data.astype("complex64")


def _write_pipe_fid(tmp_path: Path, data: np.ndarray) -> Path:
    """把复数 FID 写成真实 NMRPipe 1D 文件（2048B 头部 + [real…, imag…] float32）。"""
    path = tmp_path / "synthetic.fid"
    n = len(data)
    fdata = np.zeros(512, dtype="float32")
    values = {
        "FDDIMCOUNT": 1.0,
        "FDDIMORDER1": 1.0,
        "FDF2QUADFLAG": 0.0,  # ≠1 → 复数数据（real 与 imag 前后相接存储）
        "FDF1QUADFLAG": 0.0,
        "FDF1FTFLAG": 0.0,  # 时域
        "FDSIZE": float(n),
        "FDF1SW": float(_SW_HZ),
        "FDF1OBS": float(_OBS_MHZ),
        "FDF1CAR": 0.0,
    }
    for key, value in values.items():
        fdata[_SLOTS[key]] = value
    header = bytearray(fdata.tobytes())
    header[72:80] = b"1H".ljust(8, b"\x00")  # FDF1LABEL（8 字符槽）
    raw = np.concatenate([data.real, data.imag]).astype("float32")
    path.write_bytes(bytes(header) + raw.tobytes())
    return path


def _run_nmr(path: Path, **overrides) -> nmr_mod.NMRProcessor_output_schema:
    params = {
        "data_path": str(path),
        "format": "pipe",
        "apodization": "none",
        "auto_phase": False,
        "baseline_corr": False,
        "extract_peaks": True,
        "peak_threshold": 0.15,
        "zero_fill": 2,
    }
    params.update(overrides)
    return NMRProcessor().tool_call(NMRProcessor_input_schema(**params), session=None)


# ---------------------------------------------------------------------------
# N4 / N1：合成 FID 全管线 + 峰提取走真实 ng.peakpick.pick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_zero_filled_spectrum_picks_two_lines(tmp_path):
    """N4/N1 端到端：合成 FID 经 zf→FFT→去虚部→检峰。

    - zero_fill=2 使时域点数 1024 → 2048（metadata.points_total 必须翻倍）；
    - 峰提取必须成功（ng.peakpick.pick）并找到 2 条谱线；
    - 两条线按观测频率换算的化学位移间隔 = Δf/obs = 200 Hz / 500 MHz = 0.4 ppm。
    """
    path = _write_pipe_fid(tmp_path, _synthetic_fid())
    result = await _run_nmr(path)
    assert result.is_success, result.message
    assert result.metadata["points_total"] == 2048
    assert result.metadata["instrument_format"] == "pipe"

    assert len(result.spectrum_data["ppm"]) == len(result.spectrum_data["intensity"])

    # 峰数与峰位
    assert len(result.peaks) == 2, result.peaks
    ppms = sorted(float(p["ppm"]) for p in result.peaks)
    # 峰间化学位移间隔（ppm）= 频率差 / 观测频率
    assert abs(ppms[1] - ppms[0] - (_F2_HZ - _F1_HZ) / _OBS_MHZ) < 0.02
    assert all(float(p["intensity"]) > 0 for p in result.peaks)
    # 按 ppm 降序排列（化学习惯：低场到高场）
    assert result.peaks[0]["ppm"] >= result.peaks[1]["ppm"]


@pytest.mark.asyncio
async def test_zero_fill_actually_pads_when_requested(tmp_path):
    """N2：zf(data, pad=…) 必须真正加长数据——zero_fill=1 时 1024 点，
    zero_fill=2 时 2048 点（旧实现把填充量当 mid 布尔旗标，永远 no-op）。"""
    path = _write_pipe_fid(tmp_path, _synthetic_fid())

    no_fill = await _run_nmr(path, zero_fill=1)
    assert no_fill.is_success, no_fill.message
    assert no_fill.metadata["points_total"] == _N

    doubled = await _run_nmr(path, zero_fill=2)
    assert doubled.is_success, doubled.message
    assert doubled.metadata["points_total"] == 2 * _N


@pytest.mark.asyncio
async def test_extract_peaks_disabled_skips_picking(tmp_path):
    """extract_peaks=False：整条峰提取链路不应执行（或失败），仅返回谱。"""
    path = _write_pipe_fid(tmp_path, _synthetic_fid())
    result = await _run_nmr(path, extract_peaks=False)
    assert result.is_success, result.message
    assert result.peaks == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bc_last,tail_points", [(None, 103), (20, 205)])
async def test_constant_baseline_correction_uses_selected_tail(tmp_path, bc_last, tail_points):
    path = _write_pipe_fid(tmp_path, _synthetic_fid())
    settings = {} if bc_last is None else {"bc_last": bc_last}

    result = await _run_nmr(
        path, zero_fill=1, baseline_corr=True, advanced_settings=settings,
    )

    assert result.is_success, result.message
    assert result.metadata["points_total"] == _N
    assert len(result.peaks) == 2
    # Constant correction centers the selected trailing region at zero.
    assert np.mean(result.spectrum_data["intensity"][-tail_points:]) == pytest.approx(0, abs=1e-5)


# ---------------------------------------------------------------------------
# N3：schema 的 peak_engine 合法值对照真实 algorithm
# ---------------------------------------------------------------------------


def test_peak_engine_schema_accepts_only_real_ng_peakpick_algorithms():
    valid = {"connected", "downward", "thres", "thres-fast"}
    # 旧 schema 的 'greedy'/'clound' 均不是 nmrglue 0.12 支持的 algorithm
    from pydantic import ValidationError

    for engine in valid:
        NMRProcessor_input_schema(data_path="dummy", peak_engine=engine)  # 不应抛错
    for bogus in ("clound", "greedy", "gaussian"):
        with pytest.raises(ValidationError):
            NMRProcessor_input_schema(data_path="dummy", peak_engine=bogus)
    # 默认值必须是真实存在的 algorithm（'connected' 为 nmrglue pick 默认）
    assert NMRProcessor_input_schema.model_fields["peak_engine"].default == "connected"


def test_ng_peakpick_pick_is_the_supported_api():
    """N1 回归护栏：nmrglue 0.12 的 pick_1d 不存在，工具必须指向 pick。"""
    assert hasattr(ng.peakpick, "pick")
    assert not hasattr(ng.analysis.peakpick, "pick_1d")


def test_guess_udic_dispatches_to_reader_module(tmp_path):
    """N3：guess_udic 必须从各读取器模块调用（fileiobase 无 guess_udic/create_udic）。"""
    assert not hasattr(ng.fileiobase, "guess_udic")
    assert not hasattr(ng.fileiobase, "create_udic")

    path = _write_pipe_fid(tmp_path, _synthetic_fid())
    dic, data = ng.pipe.read(str(path))
    udic = ng.pipe.guess_udic(dic, data)
    assert udic[0]["obs"] == _OBS_MHZ
    assert udic[0]["sw"] == _SW_HZ
    assert udic[0]["time"] is True


def test_tool_metadata():
    tool = NMRProcessor()
    assert tool.tool_name == "nmr_processor"
    assert tool.is_read() is True


@pytest.mark.asyncio
async def test_nmrglue_missing_returns_clean_failure(monkeypatch, tmp_path):
    """nmrglue 缺失时工具给安装提示而非裸异常。"""
    monkeypatch.setattr(nmr_mod, "_NMRGLUE_AVAILABLE", False)
    result = await NMRProcessor().tool_call(
        NMRProcessor_input_schema(data_path=str(tmp_path / "x")), session=None,
    )
    assert result.is_success is False
    assert "nmrglue" in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["jeol", "auto"])
async def test_unsupported_jeol_reader_returns_clean_failure(tmp_path, format):
    path = tmp_path / "spectrum.jdf"
    path.touch()

    result = await NMRProcessor().tool_call(
        NMRProcessor_input_schema(data_path=str(path), format=format), session=None,
    )

    assert not result.is_success
    assert "JEOL" in result.message and "not supported" in result.message
    assert "nmrglue" in result.message
    assert "Traceback" not in result.message
    assert not result.spectrum_data and not result.peaks


# ---------------------------------------------------------------------------
# N5：auto 格式探测——Varian 的 procpar 共存必须先判 Varian
# ---------------------------------------------------------------------------


def test_detect_format_varian_procpar_wins_over_bruker_fid(tmp_path):
    """Varian 数据目录 xxx.fid/ 内含 fid + procpar：旧检测先命中 Bruker 的
    fid 判据误走 bruker 读取；procpar 共存必须先判 Varian。"""
    varian = tmp_path / "sample.fid"
    varian.mkdir()
    (varian / "fid").touch()
    (varian / "procpar").touch()
    assert nmr_mod._detect_data_format(str(varian)) == "varian"


def test_detect_format_bruker_without_procpar(tmp_path):
    for marker in ("fid", "ser", "pdata"):
        bruker = tmp_path / f"bruker_{marker}"
        bruker.mkdir()
        (bruker / marker).touch()
        assert nmr_mod._detect_data_format(str(bruker)) == "bruker", marker


def test_detect_format_varian_fid_suffixed_entry(tmp_path):
    holder = tmp_path / "holder"
    holder.mkdir()
    (holder / "exp1.fid").mkdir()
    assert nmr_mod._detect_data_format(str(holder)) == "varian"


def test_detect_format_file_suffixes_and_undecidable(tmp_path):
    assert nmr_mod._detect_data_format(str(tmp_path / "spec.dx")) == "jcamp"
    assert nmr_mod._detect_data_format(str(tmp_path / "spec.jdx")) == "jcamp"
    assert nmr_mod._detect_data_format(str(tmp_path / "spec.jdf")) == "jeol"
    # 判不出返回 None（不猜），由调用方报 Unrecognized instrument format
    assert nmr_mod._detect_data_format(str(tmp_path / "spec.bin")) is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert nmr_mod._detect_data_format(str(empty)) is None
