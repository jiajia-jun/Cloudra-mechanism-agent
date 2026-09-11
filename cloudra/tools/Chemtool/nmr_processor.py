import os
from typing import Any, Dict, List, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_existing_tool_path

try:
    import nmrglue as ng
    _NMRGLUE_AVAILABLE = True
except Exception:
    ng = None
    _NMRGLUE_AVAILABLE = False

description = (
    "NMR raw-data processing via nmrglue: Bruker (fid/1r), Varian/Agilent, JEOL, NMRPipe, JCAMP-DX, "
    "with a full time-to-frequency pipeline (window function, zero-fill, FT, phasing, baseline correction). "
    "Use for: processing experimental NMR raw data and obtaining a chemical-shift spectrum for structure elucidation. "
    "Do not use for: IR processing (use ir_processor) or reading a theoretical chemical-shift log (use log_parser)."
)

class NMRProcessor_input_schema(input_schema):
    data_path: str = Field(description="Path of the raw data file or folder")
    format: str = Field(default="auto", description="Format: 'bruker', 'varian', 'jeol', 'pipe', 'jcamp', 'auto'")

    # 处理参数
    apodization: str = Field(default="em", description="Window function: 'em' (exponential), 'gm' (Gaussian), 'sine', 'none'")
    lb: float = Field(default=0.3, description="Line broadening factor (Hz)")
    zero_fill: int = Field(default=1, description="Zero-fill factor (usually 1 or 2)")
    auto_phase: bool = Field(default=True, description="Whether to auto-phase")
    baseline_corr: bool = Field(default=True, description="Whether to apply baseline correction (polynomial fit)")

    # 分析参数
    extract_peaks: bool = Field(default=True, description="Whether to auto-pick peaks")
    peak_threshold: float = Field(default=0.02, description="Peak-detection threshold (relative intensity)")
    peak_engine: Literal["connected", "downward", "thres", "thres-fast"] = Field(
        default="connected",
        description="Peak-detection algorithm passed to nmrglue ng.peakpick.pick: "
                    "'connected', 'downward', 'thres', or 'thres-fast' "
                    "(exactly the algorithm values ng.peakpick.pick accepts).",
    )

    # 专家选项 (JSON 字典)
    advanced_settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Advanced overrides. Supports: 'p0', 'p1' (manual phase), 'bc_order' (baseline order), 'zf_size' (explicit zero-fill points), etc."
    )

class NMRProcessor_output_schema(output_schema):
    is_success: bool = Field(description="Whether processing succeeded")
    metadata: Dict[str, Any] = Field(default={}, description="Instrument parameters and solvent info")
    spectrum_data: Dict[str, List[float]] = Field(default={}, description="Processed spectrum data (ppm, intensity)")
    peaks: List[Dict[str, Any]] = Field(default=[], description="Peak list")
    message: str = Field(default="", description="Detailed status")

class NMRProcessor(Tool):
    tool_id: str = 't-9'
    tool_name: str = 'nmr_processor'
    tool_description: str = description
    input_schema: Any = NMRProcessor_input_schema
    output_schema: Any = NMRProcessor_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: NMRProcessor_input_schema, session: Session) -> NMRProcessor_output_schema:
        if not _NMRGLUE_AVAILABLE:
            return NMRProcessor_output_schema(
                is_success=False,
                message="nmrglue is not installed. Install it with: pip install 'cloudra[chem]'"
            )

        try:
            path = resolve_existing_tool_path(self, user_input.data_path)
        except FileNotFoundError as exc:
            return NMRProcessor_output_schema(is_success=False, message=str(exc))

        import numpy as np

        try:
            # 1. 动态加载读取器
            dic, data = None, None
            fmt = user_input.format.lower()

            # 强化版格式识别
            if fmt == 'auto':
                if os.path.isdir(path):
                    if any(f in os.listdir(path) for f in ['fid', 'ser', 'pdata']):
                        fmt = 'bruker'
                    elif any(f.endswith('.fid') for f in os.listdir(path)) or 'fid' in os.listdir(path):
                        fmt = 'varian'
                elif path.endswith(('.dx', '.jdx')):
                    fmt = 'jcamp'
                elif path.endswith(('.jdf')):
                    fmt = 'jeol'

            if fmt == 'bruker':
                # 检查是否已有处理好的 pdata
                pdata_path = os.path.join(path, 'pdata', '1')
                if os.path.exists(pdata_path):
                    dic, data = ng.bruker.read_pdata(pdata_path)
                else:
                    dic, data = ng.bruker.read(path)
            elif fmt == 'varian':
                dic, data = ng.varian.read(path)
            elif fmt == 'pipe':
                dic, data = ng.pipe.read(path)
            elif fmt == 'jcamp':
                dic, data = ng.jcampdx.read(path)
            elif fmt == 'jeol':
                dic, data = ng.jeol.read(path)
            else:
                return NMRProcessor_output_schema(is_success=False, message="Unrecognized instrument format.")

            # 2. 深度处理流 (Pipeline)
            if np.iscomplexobj(data):
                adv = user_input.advanced_settings

                # A. 窗函数 (Apodization)
                if user_input.apodization == 'em':
                    data = ng.proc_base.em(data, lb=adv.get('lb', user_input.lb))
                elif user_input.apodization == 'gm':
                    data = ng.proc_base.gm(data, g1=adv.get('g1', 0.01), g2=adv.get('g2', 0.02))

                # B. 补零 (Zero Filling)：zf(data, pad=N) 的 pad 是填充点数；
                # 传 mid=size 只是把填充量当布尔旗标（truthy），零填充根本不发生。
                zf_size = adv.get('zf_size', len(data) * user_input.zero_fill)
                if zf_size > len(data):
                    data = ng.proc_base.zf(data, pad=zf_size - len(data))

                # C. 傅里叶变换
                data = ng.proc_base.fft(data)

                # D. 相位校正
                if 'p0' in adv or 'p1' in adv:
                    # 优先使用手动相位
                    data = ng.proc_base.ps(data, p0=adv.get('p0', 0.0), p1=adv.get('p1', 0.0))
                elif user_input.auto_phase:
                    data = ng.proc_autophase.autops(data, adv.get('autophase_method', 'acme'))

                # E. 丢弃虚部并基线校正
                data = ng.proc_base.di(data)
                if user_input.baseline_corr:
                    data = ng.proc_base.cbf(data, last=adv.get('bc_last', 10), order=adv.get('bc_order', 1))

            # 3. 坐标转换与元数据处理
            # guess_udic 按读取器模块分派（每个 reader 都自带 guess_udic；
            # fileiobase 没有 guess_udic，也早已没有 create_udic——旧降级路径
            # 不存在，且空 udic 会产出无意义的 ppm，属静默错值，不能回退）。
            guess_udic = {
                "bruker": ng.bruker.guess_udic,
                "varian": ng.varian.guess_udic,
                "pipe": ng.pipe.guess_udic,
                "jeol": ng.jeol.guess_udic,
                "jcamp": ng.jcampdx.guess_udic,
            }.get(fmt)
            if guess_udic is None:
                return NMRProcessor_output_schema(
                    is_success=False,
                    message=f"Cannot infer spectral parameters for format '{fmt}'.",
                )
            try:
                udic = guess_udic(dic, data)
            except Exception as exc:
                return NMRProcessor_output_schema(
                    is_success=False,
                    message=(
                        f"Cannot infer spectral parameters (obs/sw/carrier) from the {fmt} "
                        f"header for the ppm axis: {type(exc).__name__}: {exc}. "
                        "Supply a readable {fmt} parameter set or a different input format."
                    ),
                )

            uc = ng.fileiobase.uc_from_udic(udic)
            ppm_axis = uc.ppm_scale()

            # 4. 峰提取：nmrglue 0.12 用 ng.peakpick.pick（ng.analysis.peakpick.
            # pick_1d 已不存在），返回 recarray，1D 时字段为 X_AXIS / X_LW / VOL
            peaks_found = []
            if user_input.extract_peaks:
                if float(np.max(data)) > 0:
                    thres = user_input.peak_threshold * float(np.max(data))
                    p_indices = ng.peakpick.pick(
                        data, pthres=thres, algorithm=user_input.peak_engine,
                    )
                    for p in p_indices:
                        idx = int(round(float(p['X_AXIS'])))
                        idx = max(0, min(idx, len(ppm_axis) - 1))
                        width = float(p['X_LW'])
                        if not np.isfinite(width):
                            width = 0.0
                        peaks_found.append({
                            "ppm": float(ppm_axis[idx]),
                            "intensity": float(data[idx]),
                            "width": width,
                        })
                    # 按 ppm 降序排列 (符合化学习惯)
                    peaks_found.sort(key=lambda x: x['ppm'], reverse=True)

            # 5. 限制返回的谱图点数 (防止上下文爆炸)
            # 采样 1000 个点用于可视化/初步判断，全量数据建议保存为本地文件
            step = max(1, len(data) // 1000)
            reduced_ppm = ppm_axis[::step].tolist()
            reduced_data = data[::step].tolist()

            metadata = {
                "instrument_format": fmt,
                "nucleus": udic.get(0, {}).get('label', 'Unknown'),
                "frequency_mhz": udic.get(0, {}).get('obs', 0.0),
                "solvent": udic.get(0, {}).get('solvent', 'N/A'),
                "points_total": len(data)
            }

            return NMRProcessor_output_schema(
                is_success=True,
                metadata=metadata,
                spectrum_data={"ppm": reduced_ppm, "intensity": reduced_data},
                peaks=peaks_found,
                message="NMR data processed successfully."
            )

        except Exception as e:
            import traceback
            return NMRProcessor_output_schema(is_success=False, message=f"Processing raised an exception: {str(e)}\n{traceback.format_exc()}")

def get_class():
    return NMRProcessor
