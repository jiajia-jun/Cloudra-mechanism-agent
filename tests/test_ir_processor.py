"""ir_processor 工具测试（cloudra/tools/Chemtool/ir_processor.py）。

全离线：用合成的 JCAMP-DX 透过率光谱驱动真实 spectrochempy 读取 + 工具管线，
不依赖任何外部 IR 数据文件。spectrochempy 缺失时整体跳过。

覆盖审计发现：
- I1：%T → 吸光度换算方向（吸收带必须是峰，基线 A=0，不允许 log10(%T) 倒置）；
      JCAMP `TRANSMITTANCE`（scp 能正确给单位）与 `PERCENT TRANSMITTANCE`
      （scp 0.12.6 丢单位，走文件级 %T 提示）两条路径。
- I2：normalize='area' 承诺的归一化必须真的发生（谱下面积 → 1）。
"""

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("spectrochempy")

import numpy as np  # noqa: E402

import cloudra.tools.Chemtool.ir_processor as ir_mod  # noqa: E402
from cloudra.tools.Chemtool.ir_processor import IRProcessor, IRProcessor_input_schema  # noqa: E402

# matplotlib（spectrochempy 传递依赖）需要可写配置目录；测试进程常有只读 HOME。
os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "cloudra_mpl"))


# ---------------------------------------------------------------------------
# 合成 %T JCAMP-DX（1800→1600 cm⁻¹，-1 cm⁻¹ 步长；1700 cm⁻¹ 处 10%T 吸收带）
# ---------------------------------------------------------------------------


def _percent_spectrum_values() -> tuple[np.ndarray, np.ndarray]:
    xs = np.arange(1800.0, 1599.5, -1.0)
    ys = np.full(len(xs), 100.0)
    i1700 = int(np.argmin(np.abs(xs - 1700.0)))
    ys[i1700] = 10.0
    for dx in (-1, 1):  # 加宽吸收带，避免单点 dip 难以平滑/检峰
        if 0 <= i1700 + dx < len(xs):
            ys[i1700 + dx] = 40.0
    return xs, ys


def _write_jcamp_percent_transmittance(tmp_path: Path, yunit: str = "TRANSMITTANCE") -> Path:
    """写一张 %T 光谱 JCAMP-DX（YUNITS 可选 TRANSMITTANCE / PERCENT TRANSMITTANCE）。"""
    xs, ys = _percent_spectrum_values()
    row = " ".join(f"{v:.4f}" for v in ys)
    text = (
        "##TITLE=test ir\n"
        "##JCAMP-DX=5.00\n"
        "##DATA TYPE=INFRARED SPECTRUM\n"
        "##ORIGIN=cloudra\n"
        "##XUNITS=1/CM\n"
        f"##YUNITS={yunit}\n"
        "##FIRSTX=1800.0\n"
        "##LASTX=1600.0\n"
        f"##NPOINTS={len(xs)}\n"
        "##DELTAX=-1.0\n"
        "##XFACTOR=1.0\n"
        "##YFACTOR=1.0\n"
        "##XYDATA=(X++(Y..Y))\n"
        f"1800.0 {row}\n"
        "##END\n"
    )
    path = tmp_path / "ir_trans.jdx"
    path.write_text(text, encoding="utf-8")
    return path


def _run_ir(path: Path, **overrides) -> ir_mod.IRProcessor_output_schema:
    params = {
        "data_path": str(path),
        "smooth": False,
        "baseline": False,
        "normalize": "none",
        "detect_peaks": True,
        "peak_threshold": 0.5,
        "identify_groups": False,
    }
    params.update(overrides)
    return IRProcessor().tool_call(IRProcessor_input_schema(**params), session=None)


def _spectrum_arrays(result: ir_mod.IRProcessor_output_schema):
    wn = [float(v) for v in result.spectrum["wavenumber"]]
    it = [float(v) for v in result.spectrum["intensity"]]
    return np.asarray(wn), np.asarray(it)


# ---------------------------------------------------------------------------
# I1：%T → 吸光度
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_percent_transmittance_converted_to_absorbance_bands_are_peaks(tmp_path):
    """I1（JCAMP TRANSMITTANCE 路径）：%T 吸收带必须换算成向上的吸光度峰。

    1700 cm⁻¹ 处 T=10% → A=1.0（峰），T=100% 基线 → A=0。若沿用 log10(%T)
    谱被倒置：基线 2.0、带 1.0，find_peaks 会去检基线噪声而非吸收带。
    """
    path = _write_jcamp_percent_transmittance(tmp_path, yunit="TRANSMITTANCE")
    result = await _run_ir(path)
    assert result.is_success, result.message
    assert result.y_unit in ("a.u.", "Absorbance", "absorbance")

    wn, intensity = _spectrum_arrays(result)
    assert len(wn) == len(intensity) == 201  # 抽稀步长 1，未丢数据

    i_band = int(np.argmin(np.abs(wn - 1700.0)))
    i_base = int(np.argmin(np.abs(wn - 1800.0)))
    # 吸收带向上：1700 处是全场最大（≈A=1.0），基线≈0
    assert intensity[i_band] == pytest.approx(1.0, abs=0.05)
    assert intensity[i_base] == pytest.approx(0.0, abs=0.05)
    assert intensity[i_band] > intensity[i_base] + 0.5

    # 检峰必须在 1700 cm⁻¹ 找到吸收带（而不是基线噪声）
    assert len(result.peaks) == 1
    peak = result.peaks[0]
    assert abs(float(peak["wavenumber"]) - 1700.0) < 2.0
    assert float(peak["intensity"]) == pytest.approx(1.0, abs=0.1)


@pytest.mark.asyncio
async def test_percent_transmittance_jcamp_with_lost_units_still_converts(tmp_path):
    """I1（JCAMP PERCENT TRANSMITTANCE 路径）：spectrochempy 0.12.6 对该 YUNITS
    不落地 dataset.units，工具必须从文件语义兜底换算，不允许把 0..100 的 %T
    原样当吸光度交给下游（吸收带仍必须是峰、基线 A=0）。"""
    path = _write_jcamp_percent_transmittance(tmp_path, yunit="PERCENT TRANSMITTANCE")
    result = await _run_ir(path)
    assert result.is_success, result.message

    wn, intensity = _spectrum_arrays(result)
    i_band = int(np.argmin(np.abs(wn - 1700.0)))
    i_base = int(np.argmin(np.abs(wn - 1800.0)))
    assert intensity[i_band] == pytest.approx(1.0, abs=0.05)
    assert intensity[i_base] == pytest.approx(0.0, abs=0.05)
    assert len(result.peaks) == 1
    assert abs(float(result.peaks[0]["wavenumber"]) - 1700.0) < 2.0


# ---------------------------------------------------------------------------
# I2：normalize='area'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_area_integrates_to_unity(tmp_path):
    """I2：normalize='area' 承诺的"归一化到单位谱面积"必须真的发生。"""
    path = _write_jcamp_percent_transmittance(tmp_path, yunit="TRANSMITTANCE")
    # detect_peaks 关闭：本测试只验证归一化本身（归一化后峰值尺度随面积缩放，
    # 绝对值阈值检峰与归一化语义无关）
    result = await _run_ir(path, normalize="area", detect_peaks=False)
    assert result.is_success, result.message

    wn, intensity = _spectrum_arrays(result)
    # 归一化后 |A| 在谱域上的梯形面积 = 1（x 升序积分，避免负 Δx 方向性）
    area = float(np.trapezoid(np.abs(intensity[::-1]), wn[::-1]))
    assert area == pytest.approx(1.0, abs=1e-3)

    # 形状保留：1700 cm⁻¹ 吸收带仍是显著特征（归一化只是缩放，不改变相对形状）
    assert float(np.max(intensity)) > 0
    i_band = int(np.argmin(np.abs(wn - 1700.0)))
    assert float(np.argmax(np.abs(intensity))) == i_band


# ---------------------------------------------------------------------------
# 其他：非法输入 / 元数据 / 环境缺失
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_file_returns_clean_failure(tmp_path):
    result = await _run_ir(tmp_path / "does_not_exist.jdx")
    assert result.is_success is False
    assert "File not found" in result.message


def test_tool_metadata():
    tool = IRProcessor()
    assert tool.tool_name == "ir_processor"
    assert tool.is_read() is True
    # schema 承诺的 normalize 合法值（area 必须被实现而非静默忽略）
    assert IRProcessor_input_schema.model_fields["normalize"].default == "snv"


@pytest.mark.asyncio
async def test_ir_imports_spectrochempy_lazily(monkeypatch, tmp_path):
    """spectrochempy 缺失时工具给安装提示而非裸 ImportError。"""
    import cloudra.tools.Chemtool.ir_processor as mod

    monkeypatch.setattr(mod, "_import_spectrochempy", lambda: None)
    result = await IRProcessor().tool_call(
        IRProcessor_input_schema(data_path=str(tmp_path / "x.jdx")), session=None,
    )
    assert result.is_success is False
    assert "spectrochempy" in result.message


# ---------------------------------------------------------------------------
# I5：单位丢失的透过率换算——歧义区 fail-loud，绝不按数值静默猜量纲
# ---------------------------------------------------------------------------


class _FakeProc:
    """_to_absorbance 的最小替身：data/units/log10()/to()（签名带 **_kwargs）。"""

    def __init__(self, data, units=None):
        self.data = np.asarray(data, dtype=float)
        self.units = units

    def log10(self, **_kwargs):
        return np.log10(self.data)

    def to(self, *_args, **_kwargs):
        raise RuntimeError("scp conversion unavailable in this stub")


def test_to_absorbance_declared_percent_ignores_magnitude():
    """显式声明的 %T（scp percent 单位 / JCAMP 头）按定义 A=2−log10(T%)：
    强吸收样品全谱 <1.5 %T 也是 %T——旧实现按 peak_scale≤1.5 误判为小数 T。"""
    proc = _FakeProc([1.4, 0.5, 1.2], units="percent")
    out = ir_mod._to_absorbance(proc, percent_declared=True)
    assert np.asarray(out)[0] == pytest.approx(2.0 - np.log10(1.4))
    assert np.asarray(out)[1] == pytest.approx(2.0 - np.log10(0.5))


def test_to_absorbance_unitless_above_physical_limit_infers_percent():
    """单位丢失但数值超出小数 T 物理上限（>1.5）：安全推断为 %T。"""
    proc = _FakeProc([50.0, 10.0])
    out = ir_mod._to_absorbance(proc)
    assert np.asarray(out)[0] == pytest.approx(2.0 - np.log10(50.0))
    assert np.asarray(out)[1] == pytest.approx(1.0)  # T=10% → A=1.0


def test_to_absorbance_unitless_ambiguous_range_fails_loud():
    """单位丢失且数值全落 (0, 1.5] 歧义区：小数 T 与 %T 不可区分——
    fail-loud 抛 ValueError（is_success=False），绝不静默猜值。"""
    proc = _FakeProc([1.4, 0.5, 1.0])
    with pytest.raises(ValueError, match="undecidable"):
        ir_mod._to_absorbance(proc)


@pytest.mark.asyncio
async def test_strong_absorption_percent_jcamp_converts_by_declaration(tmp_path):
    """端到端：PERCENT TRANSMITTANCE 声明的强吸收谱（全谱 ≤1.5 %T）必须按
    %T 定义换算——吸收带 A=2−log10(0.5)≈2.30 高于基线 2−log10(1.4)≈1.85，
    旧实现误判为小数 T 会给出 A≈0.3 的荒谬值且 is_success=True。"""
    xs = np.arange(1800.0, 1599.5, -1.0)
    ys = np.full(len(xs), 1.4)
    i1700 = int(np.argmin(np.abs(xs - 1700.0)))
    ys[i1700] = 0.5
    row = " ".join(f"{v:.4f}" for v in ys)
    path = tmp_path / "strong_absorption.jdx"
    path.write_text(
        "##TITLE=strong absorption\n"
        "##JCAMP-DX=5.00\n"
        "##DATA TYPE=INFRARED SPECTRUM\n"
        "##XUNITS=1/CM\n"
        "##YUNITS=PERCENT TRANSMITTANCE\n"
        "##FIRSTX=1800.0\n"
        "##LASTX=1600.0\n"
        f"##NPOINTS={len(xs)}\n"
        "##DELTAX=-1.0\n"
        "##XFACTOR=1.0\n"
        "##YFACTOR=1.0\n"
        "##XYDATA=(X++(Y..Y))\n"
        f"1800.0 {row}\n"
        "##END\n",
        encoding="utf-8",
    )

    result = await _run_ir(path, detect_peaks=False)

    assert result.is_success, result.message
    wn, intensity = _spectrum_arrays(result)
    i_band = int(np.argmin(np.abs(wn - 1700.0)))
    i_base = int(np.argmin(np.abs(wn - 1800.0)))
    assert intensity[i_band] == pytest.approx(2.0 - np.log10(0.5), abs=0.02)
    assert intensity[i_base] == pytest.approx(2.0 - np.log10(1.4), abs=0.02)
    assert intensity[i_band] > intensity[i_base]
