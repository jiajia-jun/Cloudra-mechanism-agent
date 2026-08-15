import os
import re
from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Deep-parse a Gaussian output log (.log / .out) and extract energies, dipole, HOMO/LUMO, "
    "frequencies, thermochemical corrections, and other physicochemical properties. "
    "Use for: a full analysis after a Gaussian job, or checking whether the job converged normally. "
    "Do not use for: submitting a job (use submit_compute_job) or processing experimental spectra (use ir_processor / nmr_processor)."
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
        description="Absolute path of the Gaussian output log (.log or .out)."
    )
    properties: Optional[list[str]] = Field(
        default=None,
        description="Properties to extract. Allowed: "
                    "'energy', 'homo_lumo', 'dipole', 'frequencies', "
                    "'thermochemistry', 'mulliken_charges', 'convergence', "
                    "'job_type' (job-type detection), 'scan' (scan parameters and energy series), "
                    "'irc' (IRC path summary). "
                    "None extracts every available property."
    )


class LogParser_output_schema(output_schema):
    is_success: bool = Field(description="Whether parsing succeeded")
    scf_energy_hartree: Optional[float] = Field(default=None, description="Final SCF energy (Hartree)")
    scf_energy_ev: Optional[float] = Field(default=None, description="Final SCF energy (eV)")
    homo_ev: Optional[float] = Field(default=None, description="HOMO energy (eV)")
    lumo_ev: Optional[float] = Field(default=None, description="LUMO energy (eV)")
    homo_lumo_gap_ev: Optional[float] = Field(default=None, description="HOMO-LUMO gap (eV)")
    dipole_moment_debye: Optional[float] = Field(default=None, description="Dipole moment (Debye)")
    frequencies_cm: Optional[list[float]] = Field(default=None, description="Vibrational frequencies (cm⁻¹)")
    imaginary_frequencies: Optional[list[float]] = Field(default=None, description="Imaginary frequencies (cm⁻¹), used to judge a TS")
    zero_point_correction_hartree: Optional[float] = Field(default=None, description="Zero-point correction (Hartree)")
    thermal_energy_correction_hartree: Optional[float] = Field(default=None, description="Thermal energy correction (Hartree)")
    thermal_enthalpy_correction_hartree: Optional[float] = Field(default=None, description="Thermal enthalpy correction (Hartree)")
    thermal_gibbs_correction_hartree: Optional[float] = Field(default=None, description="Thermal Gibbs free-energy correction (Hartree)")
    total_zero_point_energy_hartree: Optional[float] = Field(default=None, description="Electronic energy plus ZPE (Hartree)")
    total_thermal_energy_hartree: Optional[float] = Field(default=None, description="Electronic energy plus thermal energy (Hartree)")
    total_enthalpy_hartree: Optional[float] = Field(default=None, description="Electronic energy plus thermal enthalpy (Hartree)")
    total_gibbs_free_energy_hartree: Optional[float] = Field(default=None, description="Electronic energy plus thermal Gibbs free energy (Hartree)")
    zero_point_energy_hartree: Optional[float] = Field(
        default=None,
        description="Compatibility alias of zero_point_correction_hartree (Hartree)",
    )
    thermal_energy_hartree: Optional[float] = Field(
        default=None,
        description="Compatibility alias of thermal_energy_correction_hartree (Hartree)",
    )
    enthalpy_hartree: Optional[float] = Field(
        default=None,
        description="Compatibility alias of total_enthalpy_hartree; this is total enthalpy, not the enthalpy correction (Hartree)",
    )
    gibbs_free_energy_hartree: Optional[float] = Field(
        default=None,
        description="Compatibility alias of total_gibbs_free_energy_hartree; this is total free energy, not the correction (Hartree)",
    )
    mulliken_charges: Optional[dict] = Field(default=None, description="Mulliken charges {atom index: charge}")
    normal_termination: Optional[bool] = Field(default=None, description="Whether Gaussian terminated normally")
    job_types: Optional[list[str]] = Field(default=None, description="Detected job types (subset of opt/ts/freq/scan/irc/sp, sorted)")
    scan_parameter: Optional[list[float]] = Field(default=None, description="Scan parameter series (relaxed PES scan)")
    scan_energies_ev: Optional[list[float]] = Field(default=None, description="Energy at each scan point (eV)")
    irc_num_points_forward: Optional[int] = Field(default=None, description="IRC forward-path point count (excluding TS)")
    irc_num_points_backward: Optional[int] = Field(default=None, description="IRC reverse-path point count (excluding TS)")
    irc_rx_coord_range: Optional[list[float]] = Field(default=None, description="IRC reaction-coordinate range [min, max]")
    irc_endpoint_energies_hartree: Optional[list[float]] = Field(default=None, description="IRC endpoint energies (Hartree), ordered by reaction coordinate")
    irc_both_directions_converged: Optional[bool] = Field(default=None, description="Whether both IRC directions converged to a minimum")
    message: str = Field(default="", description="Status or error message")


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
                message=f"Log file not found: {log_path}. "
                        "Check the path, or locate the log with query_compute_job, then retry."
            )

        try:
            # 2. 使用 cclib 解析日志（重依赖惰性导入，避免拖慢工具模块加载）
            import cclib
            import numpy as np

            data = cclib.io.ccread(log_path)
            if data is None:
                return LogParser_output_schema(
                    is_success=False,
                    message=f"cclib could not parse any data from: {log_path}. "
                            "Check that it is a complete computational-chemistry log; "
                            "if the job failed, inspect the log tail to find the cause."
                )

            requested = self._resolve_requested_fields(user_input.properties)
            result: dict[str, Any] = {"is_success": True, "message": "Log parsed successfully."}

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
                        result["message"] = f"Log parsed; IRC summary extraction failed: {e}"

            return LogParser_output_schema(**result)

        except FileNotFoundError:
            return LogParser_output_schema(
                is_success=False,
                message=f"Log file not found: {log_path}. "
                        "Check the path, or locate the log with query_compute_job, then retry."
            )
        except ImportError as e:
            return LogParser_output_schema(
                is_success=False,
                message=f"Required parser library is not installed: {str(e)}. "
                        "Install it with: pip install 'cloudra[chem]', then retry."
            )
        except Exception as e:
            return LogParser_output_schema(
                is_success=False,
                message=f"Failed to parse the log: {str(e)}. "
                        f"Check that {log_path} is a valid, complete log file; "
                        "if the job crashed, inspect the log tail for the cause."
            )


def get_class():
    return LogParser


def _has_frequency_data(result: dict[str, Any]) -> bool:
    """频率列表确实存在才可计数（不能只凭 job_types / 热化学块）。"""
    return (
        result.get("frequencies_cm") is not None
        or result.get("imaginary_frequencies") is not None
    )


def _imaginary_frequency_list(result: dict[str, Any]) -> list[Any] | None:
    """返回虚频列表；无法确认频率数据时返回 None（不得当成零虚频）。"""
    if not _has_frequency_data(result):
        return None
    imaginary = result.get("imaginary_frequencies")
    if imaginary is None:
        # 仅有 frequencies_cm（实频）时视为零虚频。
        return []
    return list(imaginary)


def derive_delivery_changes(
    *,
    current: dict[str, Any],
    role: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """DAG evidence derivation owned by this tool; kept out of DagController.

    Only the deterministic harness calls this, and engine still rejects models
    that try to set derived evidence fields themselves.
    """
    del current, arguments  # 本工具派生不需要 current/arguments
    imaginary = _imaginary_frequency_list(result)
    normal = result.get("normal_termination") is not False
    # short_irc 门槛：双向均收敛，或每个方向至少这么多 IRC 点（不含 TS）。
    min_irc_points = 50
    if (
        role == "intermediate_optimization"
        and normal
        and imaginary is not None
        and len(imaginary) == 0
    ):
        return {"evidence_level": "structure_supported"}
    if (
        role == "ts_optimization_frequency"
        and normal
        and imaginary is not None
        and len(imaginary) == 1
    ):
        return {
            "saddle_supported": True,
            "evidence_level": "saddle_supported",
        }
    if role == "short_irc" and (
        result.get("irc_both_directions_converged") is True
        or (
            int(result.get("irc_num_points_forward") or 0) >= min_irc_points
            and int(result.get("irc_num_points_backward") or 0) >= min_irc_points
        )
    ):
        return {"short_irc_supported": True}
    if (
        role == "endpoint_a_optimization"
        and normal
        and imaginary is not None
        and len(imaginary) == 0
    ):
        return {"endpoint_a_minimum_supported": True}
    if (
        role == "endpoint_b_optimization"
        and normal
        and imaginary is not None
        and len(imaginary) == 0
    ):
        return {"endpoint_b_minimum_supported": True}
    return {}
