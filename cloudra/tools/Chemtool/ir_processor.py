# spectrochempy 在 Python 3.10 中会引用 datetime.UTC（3.11 新增），
# 在导入前为 3.10 环境补上兼容性补丁。
import asyncio
import datetime
import os
from typing import Any, Dict, List

from pydantic import Field

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_existing_tool_path


def _import_spectrochempy():
    """惰性导入 spectrochempy（重依赖），未安装时返回 None。"""
    try:
        import spectrochempy as scp
        return scp
    except Exception:
        return None


def _unit_token(proc) -> str:
    """单位的小写规范化标签：优先 spectrochempy 的 pretty 表示（percent/
    transmittance/absorbance），退化为 str()。"""
    unit = getattr(proc, "units", None)
    if unit is None:
        return ""
    try:
        return f"{unit:P}".lower()
    except Exception:
        return str(unit).lower()


def _jcamp_yunit(path: str) -> str | None:
    """解析 JCAMP-DX 的 YUNITS 记录，拒绝缺失、冲突或不支持的声明。

    spectrochempy 0.12.6 的 JCAMP reader 只把 'ABSORBANCE'/'TRANSMITTANCE'/
    'ARBITRARY UNITS' 落地为 dataset.units——最常见的 'PERCENT TRANSMITTANCE'
    不落地（units=None）。这类文件数值是 0..100 的 %T，不是吸光度/任意单位；
    从文件头补足该语义，避免把 %T 原样当吸光度交给下游（GH I1）。
    """
    # SpectroChemPy 的 JCAMP reader 支持 .jdx / .dx；SPA 等二进制格式
    # 的字节不属于 JCAMP 元数据，不能通过文本匹配触发单位换算。
    if os.path.splitext(path)[1].lower() not in {".jdx", ".dx"}:
        return None
    supported_units = {"ABSORBANCE", "TRANSMITTANCE", "ARBITRARY UNITS", "PERCENT TRANSMITTANCE"}
    declared_unit = None
    previous_label = ""
    with open(path, "r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            # $$ 引入 JCAMP 注释；注释或其他记录的值不是单位声明。
            line = raw_line.partition("$$")[0].strip()
            if not line:
                continue
            if not line.startswith("##"):
                if previous_label == "YUNITS":
                    raise ValueError(f"Unsupported JCAMP YUNITS continuation at line {line_number}")
                continue
            label, separator, value = line[2:].partition("=")
            label = label.strip().upper()
            if not label or (not separator and label != "END"):
                raise ValueError(f"Malformed JCAMP record at line {line_number}: expected LABEL=VALUE")
            previous_label = label
            if label != "YUNITS":
                continue
            unit = " ".join(value.split()).upper()
            if unit not in supported_units:
                raise ValueError(f"Unsupported or empty JCAMP YUNITS at line {line_number}: {value!r}")
            if declared_unit is not None and unit != declared_unit:
                raise ValueError(f"Conflicting JCAMP YUNITS declarations: {declared_unit!r} and {unit!r}")
            declared_unit = unit
    if declared_unit is None:
        raise ValueError("JCAMP YUNITS declaration is missing")
    return declared_unit


def _to_absorbance(proc, *, percent_declared: bool = False):
    """把透过率光谱换算成吸光度（A = -log10(T)），返回 scp 数据集。

    - 单位声明为 'transmittance'：spectrochempy 0.12.6 在该单位下对 0..100 的
      %T 数值的 .to('absorbance') 数学正确（100→0、10→1），直接复用；
    - 显式声明的 %T（scp 单位含 'percent'，或 JCAMP 头声明 PERCENT
      TRANSMITTANCE，经 percent_declared 传入）：按定义 A = 2 − log10(T%)，
      与数值大小无关——强吸收样品全谱 <1.5 %T 也是 %T，不做数值猜测；
    - 以上都不成立（声明的 transmittance 换算失败后的数值兜底）：只有数值
      超出小数 T 物理上限（peak > 1.5）才安全推断为 %T；全落 (0, 1.5] 的
      歧义区无法区分小数 T 与 %T——fail-loud 抛 ValueError，绝不静默猜值。
    """
    token = _unit_token(proc)
    if token == "transmittance" and not percent_declared:
        try:
            return proc.to('absorbance')
        except Exception:
            pass  # 落到数值推断路径
    if percent_declared:
        return 2.0 - proc.log10()  # %T 0..100：A = log10(100) − log10(T) = 2 − log10(T)
    import numpy as np

    arr = np.asarray(proc.data, dtype=float).ravel()
    peak_scale = float(np.nanmax(np.abs(arr))) if arr.size else 0.0
    if peak_scale > 1.5:
        # 超出小数 T 的物理上限（T ≤ 1），必为 0..100 的 %T
        return 2.0 - proc.log10()
    raise ValueError(
        "Transmittance-like spectrum without a declared y-unit: all values lie in the "
        "(0, 1.5] ambiguous range, so fractional transmittance (0..1) and percent "
        "transmittance (0..100) cannot be distinguished — the conversion is undecidable. "
        "Re-export the file with an explicit YUNITS declaration (TRANSMITTANCE or "
        "PERCENT TRANSMITTANCE), then retry."
    )

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
        try:
            path = resolve_existing_tool_path(self, user_input.data_path)
        except FileNotFoundError as exc:
            return IRProcessor_output_schema(is_success=False, message=str(exc))

        # spectrochempy 冷 import 与整条处理流水线都是同步重活，
        # 卸载出事件循环，避免冻结整个 API。
        return await asyncio.to_thread(self._process, path, user_input)

    def _process(self, path: str, user_input: IRProcessor_input_schema) -> IRProcessor_output_schema:
        """同步处理流水线主体；只经 to_thread 调用。"""
        scp = _import_spectrochempy()
        if scp is None:
            return IRProcessor_output_schema(
                is_success=False,
                message="spectrochempy is not installed. Install it with: pip install 'cloudra[chem]'"
            )

        import numpy as np

        try:
            # 1. 读取数据
            jcamp_yunit = _jcamp_yunit(path)
            # SpectroChemPy 具有强大的文件读取引擎
            dataset = scp.read(path)
            if isinstance(dataset, list):
                dataset = dataset[0]

            # 2. 预处理流水线
            proc = dataset.copy()
            adv = user_input.advanced_settings

            # 已校验的 JCAMP 声明是单位事实源；reader 会丢失带注释或
            # 大小写变化的单位。沿用它已有的单位定义，避免按数值猜量纲。
            if jcamp_yunit is not None:
                proc.units = {
                    "ABSORBANCE": "absorbance",
                    "TRANSMITTANCE": "transmittance",
                    "ARBITRARY UNITS": None,
                    "PERCENT TRANSMITTANCE": None,
                }[jcamp_yunit]

            # 转换为吸光度 (如果是透过率)。%T 换算必须得到向上吸收峰
            # （T=10% → A=1.0，T=100% → A=0）；log10(%T) 会把谱倒置
            # （基线 2.0 / 带 1.0），find_peaks 于是去检基线噪声（GH I1）。
            # 显式声明的 %T（scp percent 单位 / JCAMP 头）按定义换算；
            # 单位丢失且数值落歧义区时 _to_absorbance fail-loud（GH I5）。
            unit_token = _unit_token(proc)
            jcamp_percent_hint = jcamp_yunit == "PERCENT TRANSMITTANCE"
            transmittance_like = (
                any(tok in unit_token for tok in ("transmittance", "percent"))
                or jcamp_percent_hint
            )
            converted_to_absorbance = False
            if transmittance_like:
                proc = _to_absorbance(
                    proc,
                    percent_declared=("percent" in unit_token or jcamp_percent_hint),
                )
                converted_to_absorbance = True

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

            # 归一化
            if user_input.normalize == 'snv':
                # 高级运算会自动处理单位，归一化后变为无单位 (dimensionless)
                proc = (proc - proc.mean()) / proc.std()
            elif user_input.normalize == 'minmax':
                proc = (proc - proc.min()) / (proc.max() - proc.min())
            elif user_input.normalize == 'area':
                # 面积归一化（schema 承诺的语义）：∫|y| dx → 1，保留相对形状
                import numpy as np

                x = np.asarray(proc.x.values, dtype=float).ravel()
                y = np.asarray(proc.data, dtype=float).ravel()
                area = float(np.trapezoid(np.abs(y), x))
                if not np.isfinite(area) or abs(area) <= 1e-300:
                    raise ValueError(
                        "area normalization failed: the spectral integral is zero or non-finite"
                    )
                proc = proc / abs(area)

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
                y_unit="Absorbance" if converted_to_absorbance else str(proc.units),
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
