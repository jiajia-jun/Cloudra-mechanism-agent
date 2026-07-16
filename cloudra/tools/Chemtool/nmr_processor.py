import os
from typing import Any, Dict, List

import numpy as np
from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "科研级 NMR 原始数据处理工具：集成 nmrglue 深度处理流水线。"
    "支持 Bruker (fid/1r), Varian/Agilent, JEOL, NMRPipe, JCAMP-DX 格式。"
    "提供从时域到频域的完整变换流程，包含窗函数、补零、傅里叶变换、相位校正及基线校正。"
)

class NMRProcessor_input_schema(input_schema):
    data_path: str = Field(description="原始数据文件或文件夹路径")
    format: str = Field(default="auto", description="格式: 'bruker', 'varian', 'jeol', 'pipe', 'jcamp', 'auto'")

    # 处理参数
    apodization: str = Field(default="em", description="窗函数类型: 'em' (指数), 'gm' (高斯), 'sine', 'none'")
    lb: float = Field(default=0.3, description="线宽因子 (Line Broadening, Hz)")
    zero_fill: int = Field(default=1, description="补零倍数 (通常为 1 或 2)")
    auto_phase: bool = Field(default=True, description="是否自动相位校正")
    baseline_corr: bool = Field(default=True, description="是否进行基线校正 (多项式拟合)")

    # 分析参数
    extract_peaks: bool = Field(default=True, description="是否自动识别峰")
    peak_threshold: float = Field(default=0.02, description="峰检测阈值 (相对强度)")
    peak_engine: str = Field(default="greedy", description="峰检测算法: 'greedy' 或 'clound'")

    # 专家选项 (JSON 字典)
    advanced_settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="高级参数覆盖。支持: 'p0', 'p1' (手动相位), 'bc_order' (基线阶数), 'zf_size' (指定补零点数) 等"
    )

class NMRProcessor_output_schema(output_schema):
    is_success: bool = Field(description="是否处理成功")
    metadata: Dict[str, Any] = Field(default={}, description="仪器参数及溶剂信息")
    spectrum_data: Dict[str, List[float]] = Field(default={}, description="处理后的谱图数据 (ppm, intensity)")
    peaks: List[Dict[str, Any]] = Field(default=[], description="特征峰列表")
    message: str = Field(default="", description="详细状态说明")

class NMRProcessor(Tool):
    tool_id: str = 't-9'
    tool_name: str = 'nmr_processor'
    tool_description: str = description
    input_schema: Any = NMRProcessor_input_schema
    output_schema: Any = NMRProcessor_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: NMRProcessor_input_schema, session: Session) -> NMRProcessor_output_schema:
        try:
            import nmrglue as ng
        except ImportError:
            return NMRProcessor_output_schema(is_success=False, message="缺少 nmrglue 库。")

        path = user_input.data_path
        if not os.path.exists(path):
            return NMRProcessor_output_schema(is_success=False, message="输入路径不存在。")

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
            elif fmt == 'jcamp':
                dic, data = ng.jcampdx.read(path)
            elif fmt == 'jeol':
                dic, data = ng.jeol.read(path)
            else:
                return NMRProcessor_output_schema(is_success=False, message="未识别的仪器格式。")

            # 2. 深度处理流 (Pipeline)
            if np.iscomplexobj(data):
                adv = user_input.advanced_settings

                # A. 窗函数 (Apodization)
                if user_input.apodization == 'em':
                    data = ng.proc_base.em(data, lb=adv.get('lb', user_input.lb))
                elif user_input.apodization == 'gm':
                    data = ng.proc_base.gm(data, g1=adv.get('g1', 0.01), g2=adv.get('g2', 0.02))

                # B. 补零 (Zero Filling)
                zf_size = adv.get('zf_size', len(data) * user_input.zero_fill)
                if zf_size > len(data):
                    data = ng.proc_base.zf(data, mid=zf_size)

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
            # 尝试各种猜测 udic 的方法
            udic = None
            try:
                if fmt == 'bruker':
                    udic = ng.bruker.guess_udic(dic, data)
                elif fmt == 'varian':
                    udic = ng.varian.guess_udic(dic, data)
                else:
                    udic = ng.fileiobase.guess_udic(dic, data)
            except Exception:
                udic = ng.fileiobase.create_udic(len(data), 1.0)  # 降级方案

            uc = ng.fileiobase.uc_from_udic(udic)
            ppm_axis = uc.ppm_scale()

            # 4. 峰提取
            peaks_found = []
            if user_input.extract_peaks:
                thres = user_input.peak_threshold * data.max()
                # 使用 nmrglue 的 peakpick
                p_indices = ng.analysis.peakpick.pick_1d(data, threshold=thres, method=user_input.peak_engine)
                for p in p_indices:
                    idx = int(p['location'])
                    peaks_found.append({
                        "ppm": float(ppm_axis[idx]),
                        "intensity": float(data[idx]),
                        "width": float(p.get('width', 0.0))
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
                message="NMR 数据处理成功。"
            )

        except Exception as e:
            import traceback
            return NMRProcessor_output_schema(is_success=False, message=f"处理异常: {str(e)}\n{traceback.format_exc()}")

def get_class():
    return NMRProcessor
