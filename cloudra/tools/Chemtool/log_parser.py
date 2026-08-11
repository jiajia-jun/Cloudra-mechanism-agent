import os
import re
from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

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
        "zero_point_correction_hartree",
        "thermal_energy_correction_hartree",
        "thermal_enthalpy_correction_hartree",
        "thermal_gibbs_correction_hartree",
        "total_zero_point_energy_hartree",
        "total_thermal_energy_hartree",
        "total_enthalpy_hartree",
        "total_gibbs_free_energy_hartree",
        "zero_point_energy_hartree",
        "thermal_energy_hartree",
        "enthalpy_hartree",
        "gibbs_free_energy_hartree",
    ],
    "mulliken_charges": ["mulliken_charges"],
    "convergence": ["normal_termination"],
    "job_type": ["job_types"],
    "scan": ["scan_parameter", "scan_energies_ev"],
    "irc": [
        "irc_num_points_forward",
        "irc_num_points_backward",
        "irc_rx_coord_range",
        "irc_endpoint_energies_hartree",
        "irc_both_directions_converged",
    ],
}


_GAUSSIAN_FLOAT = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][+-]?\d+)?)"
_THERMO_PATTERNS = {
    "zero_point_correction_hartree": rf"Zero-point correction=\s*{_GAUSSIAN_FLOAT}",
    "thermal_energy_correction_hartree": rf"Thermal correction to Energy=\s*{_GAUSSIAN_FLOAT}",
    "thermal_enthalpy_correction_hartree": rf"Thermal correction to Enthalpy=\s*{_GAUSSIAN_FLOAT}",
    "thermal_gibbs_correction_hartree": rf"Thermal correction to Gibbs Free Energy=\s*{_GAUSSIAN_FLOAT}",
    "total_zero_point_energy_hartree": rf"Sum of electronic and zero-point Energies=\s*{_GAUSSIAN_FLOAT}",
    "total_thermal_energy_hartree": rf"Sum of electronic and thermal Energies=\s*{_GAUSSIAN_FLOAT}",
    "total_enthalpy_hartree": rf"Sum of electronic and thermal Enthalpies=\s*{_GAUSSIAN_FLOAT}",
    "total_gibbs_free_energy_hartree": rf"Sum of electronic and thermal Free Energies=\s*{_GAUSSIAN_FLOAT}",
}


def _extract_gaussian_thermochemistry(log_path: str) -> dict[str, float]:
    """Extract the last complete Gaussian thermochemistry block without changing units."""
    with open(log_path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()

    starts = [match.start() for match in re.finditer(r"Zero-point correction=", text)]
    chunks = (
        [text[start:(starts[index + 1] if index + 1 < len(starts) else len(text))]
         for index, start in enumerate(starts)]
        if starts else [text]
    )
    parsed_blocks: list[dict[str, float]] = []
    for chunk in chunks:
        values: dict[str, float] = {}
        for field, pattern in _THERMO_PATTERNS.items():
            match = re.search(pattern, chunk)
            if match:
                values[field] = float(match.group(1).replace("D", "E").replace("d", "e"))
        if values:
            parsed_blocks.append(values)
    if not parsed_blocks:
        return {}
    complete = [block for block in parsed_blocks if len(block) == len(_THERMO_PATTERNS)]
    return complete[-1] if complete else parsed_blocks[-1]


class LogParser_input_schema(input_schema):
    log_path: str = Field(
        description="Gaussian 输出日志文件（.log 或 .out）的绝对路径。"
    )
    properties: Optional[list[str]] = Field(
        default=None,
        description="需要提取的物理量列表。可选值: "
                    "'energy', 'homo_lumo', 'dipole', 'frequencies', "
                    "'thermochemistry', 'mulliken_charges', 'convergence', "
                    "'job_type'（任务类型识别）, 'scan'（扫描参数与能量序列）, "
                    "'irc'（IRC 路径摘要）。"
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
    zero_point_correction_hartree: Optional[float] = Field(default=None, description="零点能校正 (Hartree)")
    thermal_energy_correction_hartree: Optional[float] = Field(default=None, description="热能校正 (Hartree)")
    thermal_enthalpy_correction_hartree: Optional[float] = Field(default=None, description="热焓校正 (Hartree)")
    thermal_gibbs_correction_hartree: Optional[float] = Field(default=None, description="热 Gibbs 自由能校正 (Hartree)")
    total_zero_point_energy_hartree: Optional[float] = Field(default=None, description="电子能与零点能之和 (Hartree)")
    total_thermal_energy_hartree: Optional[float] = Field(default=None, description="电子能与热能之和 (Hartree)")
    total_enthalpy_hartree: Optional[float] = Field(default=None, description="电子能与热焓之和 (Hartree)")
    total_gibbs_free_energy_hartree: Optional[float] = Field(default=None, description="电子能与热 Gibbs 自由能之和 (Hartree)")
    zero_point_energy_hartree: Optional[float] = Field(
        default=None,
        description="兼容字段：zero_point_correction_hartree 的别名 (Hartree)",
    )
    thermal_energy_hartree: Optional[float] = Field(
        default=None,
        description="兼容字段：thermal_energy_correction_hartree 的别名 (Hartree)",
    )
    enthalpy_hartree: Optional[float] = Field(
        default=None,
        description="兼容字段：total_enthalpy_hartree 的别名；这是总焓，不是焓校正 (Hartree)",
    )
    gibbs_free_energy_hartree: Optional[float] = Field(
        default=None,
        description="兼容字段：total_gibbs_free_energy_hartree 的别名；这是总自由能，不是校正项 (Hartree)",
    )
    mulliken_charges: Optional[dict] = Field(default=None, description="Mulliken 电荷分布 {原子序号: 电荷}")
    normal_termination: Optional[bool] = Field(default=None, description="Gaussian 是否正常终止")
    job_types: Optional[list[str]] = Field(default=None, description="识别到的任务类型（opt/ts/freq/scan/irc/sp 的子集，升序）")
    scan_parameter: Optional[list[float]] = Field(default=None, description="扫描参数值序列（relaxed PES scan）")
    scan_energies_ev: Optional[list[float]] = Field(default=None, description="各扫描点能量 (eV)")
    irc_num_points_forward: Optional[int] = Field(default=None, description="IRC 正向路径点数（不含 TS）")
    irc_num_points_backward: Optional[int] = Field(default=None, description="IRC 反向路径点数（不含 TS）")
    irc_rx_coord_range: Optional[list[float]] = Field(default=None, description="IRC 反应坐标范围 [min, max]")
    irc_endpoint_energies_hartree: Optional[list[float]] = Field(default=None, description="IRC 两端点能量 (Hartree)，按反应坐标从小到大")
    irc_both_directions_converged: Optional[bool] = Field(default=None, description="IRC 两个方向是否都收敛到极小点")
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

            thermo_fields = set(_AVAILABLE_PROPERTIES["thermochemistry"])
            if thermo_fields & requested:
                thermo = _extract_gaussian_thermochemistry(log_path)

                # cclib correctly exposes these as total quantities. Prefer the
                # literal Gaussian summary when present and use cclib as fallback.
                if "total_enthalpy_hartree" not in thermo:
                    value = getattr(data, "enthalpy", None)
                    if value is not None:
                        thermo["total_enthalpy_hartree"] = float(value)
                if "total_gibbs_free_energy_hartree" not in thermo:
                    value = getattr(data, "freeenergy", None)
                    if value is not None:
                        thermo["total_gibbs_free_energy_hartree"] = float(value)
                if "zero_point_correction_hartree" not in thermo:
                    value = getattr(data, "zpve", None)
                    if value is not None:
                        thermo["zero_point_correction_hartree"] = float(value)

                aliases = {
                    "zero_point_energy_hartree": "zero_point_correction_hartree",
                    "thermal_energy_hartree": "thermal_energy_correction_hartree",
                    "enthalpy_hartree": "total_enthalpy_hartree",
                    "gibbs_free_energy_hartree": "total_gibbs_free_energy_hartree",
                }
                for field in thermo_fields:
                    if field in requested and field in thermo:
                        result[field] = thermo[field]
                for alias, canonical in aliases.items():
                    if alias in requested and canonical in thermo:
                        result[alias] = thermo[canonical]

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

            # job_type / scan / irc 摘要（IRC 逐点解析在 core.gaussian_frames 中自写实现）
            want_gaussian_frames = "job_types" in requested or any(
                f.startswith("irc_") for f in requested
            )
            if want_gaussian_frames:
                from cloudra.tools.core import gaussian_frames

            if "job_types" in requested:
                result["job_types"] = sorted(gaussian_frames.detect_job_types(log_path))

            if {"scan_parameter", "scan_energies_ev"} & requested:
                scanparm = getattr(data, "scanparm", None)
                scanenergies = getattr(data, "scanenergies", None)
                if scanparm is not None and len(scanparm) > 0:
                    result["scan_parameter"] = [float(v) for v in np.asarray(scanparm[0], dtype=float)]
                if scanenergies is not None and len(scanenergies) > 0:
                    result["scan_energies_ev"] = [float(v) for v in np.asarray(list(scanenergies), dtype=float)]

            if any(f.startswith("irc_") for f in requested):
                if "irc" in gaussian_frames.detect_job_types(log_path):
                    try:
                        _irc_frames, irc_meta = gaussian_frames.extract_irc(log_path)
                        result["irc_num_points_forward"] = irc_meta["num_points_forward"]
                        result["irc_num_points_backward"] = irc_meta["num_points_backward"]
                        if irc_meta["rx_coord_range"] is not None:
                            result["irc_rx_coord_range"] = [float(v) for v in irc_meta["rx_coord_range"]]
                        if irc_meta["endpoint_energies_hartree"] is not None:
                            result["irc_endpoint_energies_hartree"] = [
                                float(v) for v in irc_meta["endpoint_energies_hartree"]
                            ]
                        result["irc_both_directions_converged"] = bool(
                            irc_meta["forward_converged"] and irc_meta["backward_converged"]
                        )
                    except ValueError as e:
                        result["message"] = f"日志解析成功；IRC 摘要提取失败: {e}"

            return LogParser_output_schema(**result)

        except Exception as e:
            return LogParser_output_schema(
                is_success=False,
                message=f"日志解析失败: {str(e)}"
            )


def get_class():
    return LogParser
