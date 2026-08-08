import os
from typing import Any, Optional

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "深度解析 Gaussian 输出日志（.log / .out），提取能量、偶极矩、HOMO/LUMO 能级、"
    "频率、热力学修正等物理化学性质。"
    "适用：Gaussian 计算完成后对结果做全面分析，或检查任务是否正常收敛。"
    "不适用：提交计算任务（用 submit_compute_job）、实验光谱数据处理（用 ir_processor / nmr_processor）。"
)


# 用户可请求的属性名 -> 对应输出字段
_AVAILABLE_PROPERTIES = {
    "energy": ["scf_energy_hartree", "scf_energy_ev"],
    "homo_lumo": ["homo_ev", "lumo_ev", "homo_lumo_gap_ev"],
    "dipole": ["dipole_moment_debye"],
    "frequencies": ["frequencies_cm", "imaginary_frequencies"],
    "thermochemistry": [
        "zero_point_energy_hartree",
        "thermal_energy_hartree",
        "enthalpy_hartree",
        "gibbs_free_energy_hartree",
    ],
    "mulliken_charges": ["mulliken_charges"],
    "convergence": ["normal_termination"],
}


class LogParser_input_schema(input_schema):
    log_path: str = Field(
        description="Gaussian 输出日志文件（.log 或 .out）的绝对路径。"
    )
    properties: Optional[list[str]] = Field(
        default=None,
        description="需要提取的物理量列表。可选值: "
                    "'energy', 'homo_lumo', 'dipole', 'frequencies', "
                    "'thermochemistry', 'mulliken_charges', 'convergence'。"
                    "为 None 时提取所有可用物理量。"
    )


class LogParser_output_schema(output_schema):
    is_success: bool = Field(description="解析是否成功")
    scf_energy_hartree: Optional[float] = Field(default=None, description="最终 SCF 能量 (Hartree)")
    scf_energy_ev: Optional[float] = Field(default=None, description="最终 SCF 能量 (eV)")
    homo_ev: Optional[float] = Field(default=None, description="HOMO 能级 (eV)")
    lumo_ev: Optional[float] = Field(default=None, description="LUMO 能级 (eV)")
    homo_lumo_gap_ev: Optional[float] = Field(default=None, description="HOMO-LUMO 能隙 (eV)")
    dipole_moment_debye: Optional[float] = Field(default=None, description="偶极矩 (Debye)")
    frequencies_cm: Optional[list[float]] = Field(default=None, description="振动频率列表 (cm⁻¹)")
    imaginary_frequencies: Optional[list[float]] = Field(default=None, description="虚频列表 (cm⁻¹)，用于判断过渡态")
    zero_point_energy_hartree: Optional[float] = Field(default=None, description="零点能校正 (Hartree)")
    thermal_energy_hartree: Optional[float] = Field(default=None, description="热力学能校正 (Hartree)")
    enthalpy_hartree: Optional[float] = Field(default=None, description="焓校正 (Hartree)")
    gibbs_free_energy_hartree: Optional[float] = Field(default=None, description="吉布斯自由能校正 (Hartree)")
    mulliken_charges: Optional[dict] = Field(default=None, description="Mulliken 电荷分布 {原子序号: 电荷}")
    normal_termination: Optional[bool] = Field(default=None, description="Gaussian 是否正常终止")
    message: str = Field(default="", description="状态或错误信息")


class LogParser(Tool):
    tool_id: str = 't-23'
    tool_name: str = 'gaussian_log_parser'
    tool_description: str = description
    input_schema: Any = LogParser_input_schema
    output_schema: Any = LogParser_output_schema

    def is_read(self) -> bool:
        return True

    @staticmethod
    def _resolve_requested_fields(properties: Optional[list[str]]) -> set[str]:
        """根据用户请求的属性列表，返回需要填充的输出字段集合。"""
        if not properties:
            # 默认提取全部
            fields = set()
            for flds in _AVAILABLE_PROPERTIES.values():
                fields.update(flds)
            return fields

        fields = set()
        for prop in properties:
            prop = prop.lower().strip()
            if prop in _AVAILABLE_PROPERTIES:
                fields.update(_AVAILABLE_PROPERTIES[prop])
        return fields

    async def tool_call(self, user_input: LogParser_input_schema, session: Session) -> LogParser_output_schema:
        log_path = user_input.log_path

        # 1. 校验日志文件是否存在
        if not os.path.isfile(log_path):
            return LogParser_output_schema(
                is_success=False,
                message=f"日志文件不存在: {log_path}"
            )

        try:
            # 2. 使用 cclib 解析日志（重依赖惰性导入，避免拖慢工具模块加载）
            import cclib
            import numpy as np

            data = cclib.io.ccread(log_path)
            if data is None:
                return LogParser_output_schema(
                    is_success=False,
                    message="cclib 未能从日志中解析出任何数据。"
                )

            requested = self._resolve_requested_fields(user_input.properties)
            result: dict[str, Any] = {"is_success": True, "message": "日志解析成功。"}

            # 3. 根据请求填充字段
            if "scf_energy_hartree" in requested or "scf_energy_ev" in requested:
                if hasattr(data, "scfenergies") and data.scfenergies is not None and len(data.scfenergies) > 0:
                    # cclib 的 scfenergies 单位为 eV
                    ev = float(data.scfenergies[-1])
                    result["scf_energy_ev"] = ev
                    result["scf_energy_hartree"] = ev / 27.211386245988

            if {"homo_ev", "lumo_ev", "homo_lumo_gap_ev"} & requested:
                if (
                    hasattr(data, "moenergies")
                    and hasattr(data, "homos")
                    and data.moenergies is not None
                    and data.homos is not None
                    and len(data.moenergies) > 0
                ):
                    mo = data.moenergies[0]
                    homo_idx = int(data.homos[0]) if hasattr(data.homos, "__iter__") else int(data.homos)

                    if 0 <= homo_idx < len(mo):
                        result["homo_ev"] = float(mo[homo_idx])
                    if homo_idx + 1 < len(mo):
                        result["lumo_ev"] = float(mo[homo_idx + 1])

                    if result.get("homo_ev") is not None and result.get("lumo_ev") is not None:
                        result["homo_lumo_gap_ev"] = result["lumo_ev"] - result["homo_ev"]

            if "dipole_moment_debye" in requested:
                if hasattr(data, "moments") and data.moments is not None and len(data.moments) >= 2:
                    # moments[1] 为偶极矩向量 (Debye)
                    dipole_vec = np.asarray(data.moments[1], dtype=float)
                    result["dipole_moment_debye"] = float(np.linalg.norm(dipole_vec))

            if {"frequencies_cm", "imaginary_frequencies"} & requested:
                if hasattr(data, "vibfreqs") and data.vibfreqs is not None and len(data.vibfreqs) > 0:
                    freqs = np.asarray(data.vibfreqs, dtype=float)
                    result["frequencies_cm"] = [float(f) for f in freqs if f >= 0]
                    result["imaginary_frequencies"] = [float(abs(f)) for f in freqs if f < 0]

            thermo_map = {
                "zero_point_energy_hartree": "zpve",
                "thermal_energy_hartree": "enthalpy",
                "enthalpy_hartree": "enthalpy",
                "gibbs_free_energy_hartree": "freeenergy",
            }
            for out_key, ccib_attr in thermo_map.items():
                if out_key in requested and hasattr(data, ccib_attr):
                    value = getattr(data, ccib_attr)
                    if value is not None:
                        result[out_key] = float(value)

            if "mulliken_charges" in requested:
                if hasattr(data, "atomcharges") and data.atomcharges is not None:
                    mulliken = data.atomcharges.get("mulliken")
                    if mulliken is not None:
                        result["mulliken_charges"] = {
                            str(i + 1): float(charge)
                            for i, charge in enumerate(mulliken)
                        }

            if "normal_termination" in requested:
                if hasattr(data, "metadata") and data.metadata is not None:
                    result["normal_termination"] = bool(data.metadata.get("success", False))
                elif hasattr(data, "optdone"):
                    result["normal_termination"] = bool(data.optdone)

            return LogParser_output_schema(**result)

        except Exception as e:
            return LogParser_output_schema(
                is_success=False,
                message=f"日志解析失败: {str(e)}"
            )


def get_class():
    return LogParser
