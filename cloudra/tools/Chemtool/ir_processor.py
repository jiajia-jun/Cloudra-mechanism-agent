import os
from pydantic import Field
from typing import Any, Optional, List, Dict
import numpy as np
from cloudra.tools_class import Tool, input_schema, output_schema
from cloudra.session_class import Session

description = (
    "专业级红外光谱 (IR) 处理与解析工具：基于 SpectroChemPy 库。"
    "支持 JCAMP-DX, Thermo Nicolet (SPA/SPG), CSV 等格式。"
    "提供基线校正、平滑、归一化、二阶导数分析及官能团自动识别。"
)

class IRProcessor_input_schema(input_schema):
    data_path: str = Field(description="原始 IR 数据文件路径")
    
    # 预处理选项
    baseline: bool = Field(default=True, description="是否进行基线校正 (Rubberband/Modified Poly)")
    smooth: bool = Field(default=True, description="是否进行平滑 (Savitzky-Golay)")
    normalize: str = Field(default="snv", description="归一化方法: 'snv' (标准正态变换), 'minmax', 'area', 'none'")
    
    # 分析参数
    detect_peaks: bool = Field(default=True, description="是否自动提取吸收峰")
    peak_threshold: float = Field(default=0.05, description="峰提取灵敏度")
    identify_groups: bool = Field(default=True, description="是否基于特征频率库自动识别官能团")

    # 专家选项 (JSON 字典)
    advanced_settings: Dict[str, Any] = Field(
        default_factory=dict, 
        description="高级参数覆盖。支持: 'smooth_size', 'smooth_order', 'baseline_method', 'baseline_params' (dict) 等"
    )

class IRProcessor_output_schema(output_schema):
    is_success: bool = Field(description="是否成功处理")
    units: str = Field(default="cm^-1", description="X轴单位")
    y_unit: str = Field(default="Absorbance", description="Y轴单位 (Abs/Trans)")
    spectrum: Dict[str, List[float]] = Field(default={}, description="处理后的谱图数据")
    peaks: List[Dict[str, Any]] = Field(default=[], description="检测到的峰及其对应的可能官能团")
    message: str = Field(default="", description="执行信息")

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
            import spectrochempy as scp
        except ImportError:
            return IRProcessor_output_schema(is_success=False, message="环境未安装 spectrochempy 库。")

        path = user_input.data_path
        if not os.path.exists(path):
            return IRProcessor_output_schema(is_success=False, message=f"文件不存在: {path}")

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
            except:
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
                for i in range(pk_dataset.shape[-1]):
                    # 统一使用 .magnitude 安全提取数值用于 JSON 序列化
                    pos_val = pk_dataset.x.values[i]
                    pos = float(pos_val.magnitude) if hasattr(pos_val, 'magnitude') else float(pos_val)
                    
                    inten_val = pk_dataset.data.squeeze()[i]
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
                message="红外光谱处理完成。"
            )

        except Exception as e:
            return IRProcessor_output_schema(is_success=False, message=f"IR 处理异常: {str(e)}")

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
