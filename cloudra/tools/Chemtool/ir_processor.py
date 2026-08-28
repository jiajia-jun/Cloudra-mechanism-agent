# spectrochempy 在 Python 3.10 中会引用 datetime.UTC（3.11 新增），
# 在导入前为 3.10 环境补上兼容性补丁。
import datetime
import os
from typing import Any, Dict, List

from pydantic import Field

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema


def _import_spectrochempy():
    """惰性导入 spectrochempy（重依赖），未安装时返回 None。"""
    try:
        import spectrochempy as scp
        return scp
    except Exception:
        return None

description = (
    "Infrared (IR) spectrum processing and assignment: SpectroChemPy, supporting JCAMP-DX, Thermo Nicolet (SPA/SPG), CSV, etc., "
    "with baseline correction, smoothing, normalization, second-derivative analysis, and automatic functional-group ID. "
    "Use for: processing experimental IR raw spectra, assigning functional groups, comparing with computed spectra. "
    "Do not use for: NMR processing (use nmr_processor) or reading a Gaussian frequency log (use log_parser)."
)

class IRProcessor_input_schema(input_schema):
    data_path: str = Field(
        description="Path of the raw IR data file. Absolute path, or relative to the agent process's current working directory; absolute paths are recommended."
    )

    # 预处理选项
    baseline: bool = Field(default=True, description="Whether to apply baseline correction (Rubberband/Modified Poly)")
    smooth: bool = Field(default=True, description="Whether to smooth (Savitzky-Golay)")
    normalize: str = Field(default="snv", description="Normalization: 'snv' (standard normal variate), 'minmax', 'area', 'none'")

    # 分析参数
    detect_peaks: bool = Field(default=True, description="Whether to auto-extract absorption peaks")
    peak_threshold: float = Field(default=0.05, description="Peak-picking sensitivity")
    identify_groups: bool = Field(default=True, description="Whether to auto-identify functional groups from a characteristic-frequency library")

    # 专家选项 (JSON 字典)
    advanced_settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Advanced overrides. Supports: 'smooth_size', 'smooth_order', 'baseline_method', 'baseline_params' (dict), etc."
    )

class IRProcessor_output_schema(output_schema):
    is_success: bool = Field(description="Whether processing succeeded")
    units: str = Field(default="cm^-1", description="X-axis unit")
    y_unit: str = Field(default="Absorbance", description="Y-axis unit (Abs/Trans)")
    spectrum: Dict[str, List[float]] = Field(default={}, description="Processed spectrum data")
    peaks: List[Dict[str, Any]] = Field(default=[], description="Detected peaks and possible matching functional groups")
    message: str = Field(default="", description="Status message")

class IRProcessor(Tool):
    tool_id: str = 't-8'
    tool_name: str = 'ir_processor'
    tool_description: str = description
    input_schema: Any = IRProcessor_input_schema
    output_schema: Any = IRProcessor_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: IRProcessor_input_schema, session: Session) -> IRProcessor_output_schema:
        scp = _import_spectrochempy()
        if scp is None:
            return IRProcessor_output_schema(
                is_success=False,
                message="spectrochempy is not installed. Install it with: pip install 'cloudra[chem]'"
            )

        import numpy as np

        path = user_input.data_path
        if not os.path.exists(path):
            return IRProcessor_output_schema(is_success=False, message=f"File does not exist: {path}")

        try:
            # 1. 读取数据
            # SpectroChemPy 具有强大的文件读取引擎
            dataset = scp.read(path)
            if isinstance(dataset, list):
                dataset = dataset[0]

            # 2. 预处理流水线
            proc = dataset.copy()
            adv = user_input.advanced_settings

            # 转换为吸光度 (如果是透过率)
            try:
                if str(proc.units) == "percent":
                    proc = proc.log10()
            except Exception:
                pass

            # 平滑 (使用高级方法 smooth)
            if user_input.smooth:
                if proc.shape[-1] > 11:
                    size = adv.get('smooth_size', 11)
                    order = adv.get('smooth_order', 2)
                    proc = proc.smooth(size=size, order=order)

            # 基线校正 (使用 basc)
            if user_input.baseline:
                method = adv.get('baseline_method', 'rubberband')
                params = adv.get('baseline_params', {})
                proc = proc.basc(method=method, **params)

            # 归一化 (使用高级数学运算)
            if user_input.normalize == 'snv':
                # 高级运算会自动处理单位，归一化后变为无单位 (dimensionless)
                proc = (proc - proc.mean()) / proc.std()
            elif user_input.normalize == 'minmax':
                proc = (proc - proc.min()) / (proc.max() - proc.min())

            # 3. 峰提取
            peaks_list = []
            if user_input.detect_peaks:
                res = proc.find_peaks(threshold=user_input.peak_threshold)
                pk_dataset = res[0]

                # 提取峰位置和强度
                y_peaks = np.atleast_1d(pk_dataset.data.squeeze())
                x_peaks = np.atleast_1d(pk_dataset.x.values)

                for i in range(len(y_peaks)):
                    # 统一使用 .magnitude 安全提取数值用于 JSON 序列化
                    pos_val = x_peaks[i]
                    pos = float(pos_val.magnitude) if hasattr(pos_val, 'magnitude') else float(pos_val)

                    inten_val = y_peaks[i]
                    val = float(inten_val.magnitude) if hasattr(inten_val, 'magnitude') else float(inten_val)

                    group_matches = []
                    if user_input.identify_groups:
                        group_matches = self._match_group(pos)

                    peaks_list.append({
                        "wavenumber": round(pos, 2),
                        "intensity": round(val, 4),
                        "possible_groups": group_matches
                    })

            # 4. 数据抽稀与格式化
            # 确保返回的是纯数值列表，避免带单位的对象进入 JSON
            x_raw = proc.x.values
            y_raw = proc.data.squeeze()

            x_list = [float(v.magnitude) if hasattr(v, 'magnitude') else float(v) for v in x_raw]
            y_list = [float(v.magnitude) if hasattr(v, 'magnitude') else float(v) for v in y_raw]

            step = max(1, len(x_list) // 800)

            return IRProcessor_output_schema(
                is_success=True,
                units=str(proc.x.units),
                y_unit=str(proc.units),
                spectrum={
                    "wavenumber": x_list[::step],
                    "intensity": y_list[::step]
                },
                peaks=peaks_list,
                message="IR spectrum processing complete."
            )

        except Exception as e:
            return IRProcessor_output_schema(is_success=False, message=f"IR processing raised an exception: {str(e)}")

    def _match_group(self, wn: float) -> List[str]:
        """特征频率匹配逻辑"""
        TABLE = [
            (3200, 3600, "O-H / N-H stretching"),
            (3000, 3100, "C-H stretching (sp2)"),
            (2850, 2980, "C-H stretching (sp3)"),
            (2210, 2260, "C≡N stretching"),
            (2100, 2260, "C≡C stretching"),
            (1680, 1820, "C=O stretching"),
            (1600, 1680, "C=C stretching"),
            (1450, 1600, "Aromatic C=C"),
            (1000, 1300, "C-O stretching"),
        ]
        results = []
        for low, high, name in TABLE:
            if low <= wn <= high:
                results.append(name)
        return results

def get_class():
    return IRProcessor
