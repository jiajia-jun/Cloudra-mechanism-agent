import asyncio
import os
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.Chemtool.frontier_orbitals import (
    GAP_UNDECIDABLE_SPIN_CROSSOVER,
    frontier_orbital_summary,
)

description = (
    "Deep-parse a quantum-chemistry output log (Gaussian .log/.out, ORCA .out, or xtb .out; engine auto-detected) "
    "and extract energies, dipole, HOMO/LUMO, frequencies, thermochemical corrections, and other "
    "physicochemical properties. "
    "For Gaussian/ORCA logs with imaginary frequencies, each imaginary mode also gets a composition summary "
    "(top displaced atom pairs, heavy-atom displacement fraction, and — when watch_pairs are supplied — each "
    "watch pair's share of the total pair-projected displacement). "
    "Use for: a full analysis after a Gaussian/ORCA/xtb job, or checking whether the job converged normally. "
    "Recognized Gaussian/ORCA scan paths report internal local-peak candidates and their exact existing XYZ references, "
    "even when only convergence was requested; use that seed with ts_prepare rather than comparing energies by hand. "
    "Do not use for: submitting a job (use submit_compute_job) or processing experimental spectra (use ir_processor / nmr_processor)."
)


# 用户可请求的属性名 -> 对应输出字段
_AVAILABLE_PROPERTIES = {
    "energy": ["scf_energy_hartree", "scf_energy_ev"],
    "homo_lumo": [
        "homo_ev", "lumo_ev", "homo_lumo_gap_ev",
        "alpha_homo_ev", "alpha_lumo_ev", "beta_homo_ev", "beta_lumo_ev",
        "spin_crossover",
    ],
    "dipole": ["dipole_moment_debye"],
    "frequencies": ["frequencies_cm", "imaginary_frequencies", "imaginary_modes"],
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
    "convergence": ["normal_termination", "opt_converged"],
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


def _extract_gaussian_thermochemistry(text: str) -> dict[str, float]:
    """Extract the last complete Gaussian thermochemistry block without changing units.

    吃日志文本而不是路径：调用方（LogParser._parse_log）已把日志单读一次，
    不在此处重复 IO。
    """
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
        description="Path of the output log (Gaussian .log/.out, ORCA .out, or xtb .out): "
                    "absolute as-is, or relative to the Agent working directory."
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
    watch_pairs: Optional[list[list[int]]] = Field(
        default=None,
        description="1-based atom pairs to score each imaginary mode against, "
                    "e.g. the step's declared forming/breaking pairs. When given, each entry of "
                    "imaginary_modes carries watch_pair_fraction (the pairs' share of the total "
                    "pair-projected displacement); ignored when there are no imaginary modes.",
    )


class ScanPeak(BaseModel):
    point_number: int = Field(description="Peak scan point, 1-based; not an atom index.")
    energy_hartree: float = Field(description="Native electronic energy at this scan point (Hartree).")
    relative_to_first_point_kcal: float = Field(
        description="Peak minus the first scan point (kcal/mol), not a verified reaction barrier."
    )
    geometry_ref: str | None = Field(
        default=None, description="Existing peak XYZ from this scan, when available; no file is written."
    )


class LogParser_output_schema(output_schema):
    is_success: bool = Field(description="Whether parsing succeeded")
    scf_energy_hartree: Optional[float] = Field(default=None, description="Final SCF energy (Hartree)")
    scf_energy_ev: Optional[float] = Field(default=None, description="Final SCF energy (eV)")
    homo_ev: Optional[float] = Field(default=None, description="HOMO energy (eV); open-shell: max of α/β HOMO (highest SOMO)")
    lumo_ev: Optional[float] = Field(default=None, description="LUMO energy (eV); open-shell: min of α/β LUMO")
    homo_lumo_gap_ev: Optional[float] = Field(default=None, description="HOMO-LUMO gap (eV); None when undecidable (open-shell spin crossover)")
    alpha_homo_ev: Optional[float] = Field(default=None, description="Open-shell only: α-channel HOMO (SOMO) energy (eV)")
    alpha_lumo_ev: Optional[float] = Field(default=None, description="Open-shell only: α-channel LUMO energy (eV)")
    beta_homo_ev: Optional[float] = Field(default=None, description="Open-shell only: β-channel HOMO (SOMO) energy (eV)")
    beta_lumo_ev: Optional[float] = Field(default=None, description="Open-shell only: β-channel LUMO energy (eV)")
    spin_crossover: Optional[bool] = Field(
        default=None,
        description="Open-shell only: True when the lowest virtual orbital lies below the highest "
                    "occupied one — the single-determinant HOMO-LUMO gap is then undecidable (not reported).",
    )
    dipole_moment_debye: Optional[float] = Field(default=None, description="Dipole moment (Debye)")
    frequencies_cm: Optional[list[float]] = Field(default=None, description="Vibrational frequencies (cm⁻¹)")
    imaginary_frequencies: Optional[list[float]] = Field(default=None, description="Imaginary frequencies (cm⁻¹, negative values), used to judge a TS")
    imaginary_modes: Optional[list[dict]] = Field(
        default=None,
        description="Composition summary per imaginary mode (Gaussian/ORCA only): frequency_cm, "
                    "top_displaced_atoms (atom, element, fraction), top_displaced_pairs "
                    "([i, j, projected score], 1-based), heavy_atom_fraction, watch_atom_fraction, and "
                    "watch_pair_fraction when watch_pairs were supplied. Atom fractions use unweighted "
                    "squared displacements, not mass weighting or a scientific pass/fail cutoff. None when normal-mode "
                    "displacements or the final geometry could not be parsed (xtb always None).",
    )
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
    normal_termination: Optional[bool] = Field(default=None, description="Whether the job terminated normally")
    opt_converged: Optional[bool] = Field(
        default=None,
        description="Geometry/TS optimization convergence: True=converged, False=reached max cycles unconverged, "
                    "None=not an optimization or undeterminable. Independent of normal_termination: "
                    "ORCA still terminates normally when an optimization hits the max-cycle limit.",
    )
    engine: Optional[str] = Field(default=None, description="Detected QM program: gaussian / orca / xtb")
    job_types: Optional[list[str]] = Field(default=None, description="Detected job types (subset of opt/ts/freq/scan/irc/sp, sorted)")
    scan_parameter: Optional[list[float]] = Field(default=None, description="Scan parameter series (relaxed PES scan)")
    scan_energies_ev: Optional[list[float]] = Field(default=None, description="Energy at each scan point (eV)")
    scan_has_internal_peak: bool | None = Field(
        default=None, description="Automatically reported for recognized scans: an internal maximum exists; null if not established."
    )
    scan_peak: ScanPeak | None = Field(
        default=None, description="Internal scan maximum and existing geometry: a seed for refinement, not an accepted TS."
    )
    irc_num_points_forward: Optional[int] = Field(default=None, description="IRC forward-path point count (excluding TS)")
    irc_num_points_backward: Optional[int] = Field(default=None, description="IRC reverse-path point count (excluding TS)")
    irc_rx_coord_range: Optional[list[float]] = Field(default=None, description="IRC reaction-coordinate range [min, max]")
    irc_endpoint_energies_hartree: Optional[list[float]] = Field(default=None, description="IRC endpoint energies (Hartree), ordered by reaction coordinate")
    irc_both_directions_converged: Optional[bool] = Field(default=None, description="Whether both IRC directions converged to a minimum")
    message: str = Field(default="", description="Status or error message")


class LogParser(Tool):
    tool_id: str = 't-23'
    tool_name: str = 'log_parser'
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
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱）。
        user_input.log_path = resolve_tool_path(self, user_input.log_path)
        log_path = user_input.log_path

        # 1. 校验日志文件是否存在
        if not os.path.isfile(log_path):
            return LogParser_output_schema(
                is_success=False,
                message=f"Log file not found: {log_path}. "
                        "Check the path, or locate the log with query_compute_job, then retry."
            )

        requested = self._resolve_requested_fields(user_input.properties)
        # 大日志的 cclib 解析与文本回退是分钟级同步 CPU 工作，整条流水线
        # 卸载出事件循环，避免冻结整个 API。
        return await asyncio.to_thread(self._parse_log, log_path, requested, user_input.watch_pairs)

    def _parse_log(self, log_path: str, requested: set[str], watch_pairs: Optional[list[list[int]]] = None) -> LogParser_output_schema:
        """同步解析流水线主体（cclib + ORCA/xtb 文本回退）；只经 to_thread 调用。"""
        try:
            # 2. 引擎嗅探先于 cclib：外部 MLIP（ExtOpt/ProgExt）日志无 SCF 块，
            # cclib 常整体解析失败或 metadata.success 失真——ORCA 路径把 cclib
            # 降级为可选数据源，能量/终止判定退回文本权威提取（GH #17）。
            # xtb 则整体跳过 cclib（与 runtime/monitor.py 一致）：cclib 1.8.1
            # 已有 xtb parser 但结果错误——opt 日志的 scfenergies[-1] 是最后
            # 一个 opt cycle 的能量而非 boxed TOTAL ENERGY，hess 日志的热化学
            # 属性是荒谬值——能量/频率/热化学全走 xtb_frames 文本原语（GH #26）。
            from cloudra.tools.core import gaussian_frames, orca_frames, xtb_frames
            from cloudra.tools.core.qm_engine import detect_qm_engine

            engine = detect_qm_engine(log_path)

            import cclib
            import numpy as np

            data = None
            cclib_error: Exception | None = None
            if engine != "xtb":
                try:
                    data = cclib.io.ccread(log_path)
                except Exception as e:
                    cclib_error = e

            if data is None and engine not in ("orca", "xtb"):
                if cclib_error is not None:
                    raise cclib_error
                return LogParser_output_schema(
                    is_success=False,
                    message=f"cclib could not parse any data from: {log_path}. "
                            "Check that it is a complete computational-chemistry log; "
                            "if the job failed, inspect the log tail to find the cause."
                )

            # 日志文本只读一次：终止判定、能量/频率/偶极回退、热化学、任务
            # 类型识别与 IRC 提取全部共用这份文本（此前同一日志被整读 5-6 遍）。
            with open(log_path, encoding="utf-8", errors="replace") as handle:
                log_text = handle.read()

            # 任务类型全引擎只识别一次（同一份文本）：job_types 字段、
            # opt_converged 的 cclib 回退门控与 IRC 分支判定共用。
            if engine == "xtb":
                # xtb stdout 不回显 CLI 标志，从输出节判定（opt/freq/sp）
                detected_jobs = xtb_frames.detect_job_types_from_text(log_text)
            elif engine == "orca":
                detected_jobs = orca_frames.detect_job_types_from_text(log_text)
            else:
                # gaussian 与未知引擎沿用 Gaussian 路由卡/结构标记判据
                detected_jobs = gaussian_frames.detect_job_types_from_text(log_text)

            result: dict[str, Any] = {"is_success": True, "message": "Log parsed successfully.", "engine": engine}
            if data is None:
                if engine == "xtb":
                    result["message"] = (
                        "xtb logs are parsed by text extraction (tools.core.xtb_frames); "
                        "cclib is not consulted for this engine."
                    )
                else:
                    result["message"] = (
                        "cclib could not parse the log (external-MLIP/ExtOpt logs have no SCF blocks); "
                        "fell back to text extraction for energy/termination/job-type/IRC fields."
                    )

            # 3. 根据请求填充字段
            if "scf_energy_hartree" in requested or "scf_energy_ev" in requested:
                # cclib 的 eV/Hartree 常数与本工具不同，回算会有偏差；
                # ORCA 最终电子能以原始 Hartree 输出为准。
                orca_energy = orca_frames.final_energy_hartree(log_text) if engine == "orca" else None
                if orca_energy is not None:
                    result["scf_energy_hartree"] = orca_energy
                    result["scf_energy_ev"] = orca_energy * 27.211386245988
                elif data is not None and hasattr(data, "scfenergies") and data.scfenergies is not None and len(data.scfenergies) > 0:
                    # cclib 的 scfenergies 单位为 eV
                    from cloudra.tools.core.cclib_units import energy_ev_to_hartree

                    ev = float(data.scfenergies[-1])
                    result["scf_energy_ev"] = ev
                    result["scf_energy_hartree"] = energy_ev_to_hartree(ev)
                elif engine == "xtb":
                    # xtb：最终 TOTAL ENERGY 块 / :: total energy / opt 周期能量行
                    e_hartree = xtb_frames.final_energy_hartree(log_text)
                    if e_hartree is not None:
                        result["scf_energy_hartree"] = e_hartree
                        result["scf_energy_ev"] = e_hartree * 27.211386245988

            if {
                "homo_ev", "lumo_ev", "homo_lumo_gap_ev",
                "alpha_homo_ev", "alpha_lumo_ev", "beta_homo_ev", "beta_lumo_ev",
                "spin_crossover",
            } & requested:
                if (
                    data is not None
                    and getattr(data, "moenergies", None) is not None
                    and getattr(data, "homos", None) is not None
                    and len(data.moenergies) > 0
                ):
                    # 与 electronic_analysis 共用同一套前线轨道原语：开壳层报
                    # α/β 两套 HOMO/LUMO（SOMO 语义），自旋交叉时 gap 不可判定。
                    homos = [int(h) for h in np.asarray(data.homos).ravel()]
                    if len(data.moenergies) == len(homos):
                        frontier = frontier_orbital_summary(
                            [list(mo) for mo in data.moenergies],
                            [h + 1 for h in homos],  # cclib homos 是 0-based 索引
                        )
                        if frontier["homo"] is not None:
                            result["homo_ev"] = frontier["homo"]
                        if frontier["lumo"] is not None:
                            result["lumo_ev"] = frontier["lumo"]
                        if frontier["gap"] is not None:
                            result["homo_lumo_gap_ev"] = frontier["gap"]
                        if frontier["open_shell"]:
                            result["alpha_homo_ev"] = frontier["alpha"]["homo"]
                            result["alpha_lumo_ev"] = frontier["alpha"]["lumo"]
                            result["beta_homo_ev"] = frontier["beta"]["homo"]
                            result["beta_lumo_ev"] = frontier["beta"]["lumo"]
                            result["spin_crossover"] = (
                                frontier["gap_status"] == GAP_UNDECIDABLE_SPIN_CROSSOVER
                            )
                            if result["spin_crossover"]:
                                result["message"] += (
                                    " Open-shell spin crossover: the lowest virtual orbital lies "
                                    "below the highest occupied one (max α/β HOMO above min α/β LUMO), "
                                    "so the HOMO-LUMO gap is undecidable for this single determinant "
                                    "and is not reported."
                                )
                    # moenergies/homos 通道数不一致是上游解析异常：不发任何前线
                    # 轨道字段（不可判定），绝不猜一个通道的值。
                elif engine == "xtb":
                    # xtb：cclib 对其日志解析不可靠，gap 从 SUMMARY 块文本回退
                    gap = xtb_frames.homo_lumo_gap_ev(log_text)
                    if gap is not None:
                        result["homo_lumo_gap_ev"] = gap

            if "dipole_moment_debye" in requested:
                if hasattr(data, "moments") and data.moments is not None and len(data.moments) >= 2:
                    # moments[1] 为偶极矩向量 (Debye)
                    dipole_vec = np.asarray(data.moments[1], dtype=float)
                    result["dipole_moment_debye"] = float(np.linalg.norm(dipole_vec))
                elif engine == "xtb":
                    # xtb：Property Printout 的 "full:" 行第四列（Debye）
                    dipole = xtb_frames.dipole_debye(log_text)
                    if dipole is not None:
                        result["dipole_moment_debye"] = dipole

            if {"frequencies_cm", "imaginary_frequencies"} & requested:
                vibfreqs: list[float] | None = None
                if hasattr(data, "vibfreqs") and data.vibfreqs is not None and len(data.vibfreqs) > 0:
                    vibfreqs = [float(f) for f in np.asarray(data.vibfreqs, dtype=float)]
                elif engine == "orca":
                    # 外部 MLIP（ExtOpt NumFreq）日志无 SCF 块，cclib 常整体
                    # 失败——频率从 VIBRATIONAL FREQUENCIES 块文本回退（GH #16）
                    vibfreqs = orca_frames.vibfreqs_from_text(log_text) or None
                elif engine == "xtb":
                    # xtb：projected vibrational frequencies 块的 eigval 行
                    vibfreqs = xtb_frames.vibfreqs_from_text(log_text) or None
                if vibfreqs is not None:
                    # 虚频保留负号（负值=虚频是 frames 原语与下游 DAG/benchmark
                    # 的原生语义）；frequencies_cm 只存非负实频。
                    result["frequencies_cm"] = [f for f in vibfreqs if f >= 0]
                    result["imaginary_frequencies"] = [f for f in vibfreqs if f < 0]
                    if (
                        "imaginary_modes" in requested
                        and result["imaginary_frequencies"]
                        and engine in ("orca", "gaussian")
                    ):
                        # 位移与末帧几何一律走文本权威通道（ORCA 6.1 日志 cclib
                        # 整体崩溃）；拿不到位移或几何时 imaginary_modes 保持 None。
                        from cloudra.tools.core.mode_analysis import imaginary_mode_summaries_from_text
                        modes = imaginary_mode_summaries_from_text(engine, log_text, vibfreqs, watch_pairs)
                        if modes:
                            result["imaginary_modes"] = modes

            thermo_fields = set(_AVAILABLE_PROPERTIES["thermochemistry"])
            if thermo_fields & requested:
                if engine == "orca":
                    thermo = orca_frames.extract_thermochemistry_from_text(log_text)
                elif engine == "gaussian":
                    thermo = _extract_gaussian_thermochemistry(log_text)
                elif engine == "xtb":
                    # xtb：THERMODYNAMIC 块/最终块文本（cclib 热化学对 xtb 是
                    # 荒谬值，永不作为数据源）
                    thermo = xtb_frames.thermochemistry(log_text)
                else:
                    # 未知引擎：无热化学提取路径，留空
                    thermo = {}

                # cclib correctly exposes these as total quantities. Prefer the
                # literal Gaussian/ORCA/xtb summary when present and use cclib as
                # fallback — gated per engine: xtb never touches cclib (data is
                # always None for xtb by construction).
                if data is not None:
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
                if engine == "orca":
                    # 文本标记权威：cclib metadata 对无 SCF 块的外部 MLIP 日志
                    # 不可靠（GH #17 job17：正常终止却报 success=False）
                    result["normal_termination"] = orca_frames.normal_termination(log_text)
                elif engine == "xtb":
                    # 同款文本权威：normal termination of xtb（GH #26）
                    result["normal_termination"] = xtb_frames.normal_termination(log_text)
                elif engine == "gaussian":
                    result["normal_termination"] = gaussian_frames.normal_termination(log_text)
                elif hasattr(data, "metadata") and data.metadata is not None:
                    result["normal_termination"] = bool(data.metadata.get("success", False))
                elif hasattr(data, "optdone"):
                    result["normal_termination"] = bool(data.optdone)

            if "opt_converged" in requested:
                # 优化收敛与正常终止语义分开（GH #21）：ORCA 优化跑满最大步数
                # 未收敛时仍正常终止。ORCA 走文本标记为主、cclib optdone 为辅
                # （外部 MLIP 日志 cclib 可能解析失败，不能依赖它）。
                if engine == "orca":
                    converged = orca_frames.opt_converged(log_text)
                    if converged is None and data is not None:
                        optdone = getattr(data, "optdone", None)
                        if optdone is not None and ({"opt", "ts"} & detected_jobs):
                            converged = bool(optdone)
                    result["opt_converged"] = converged
                elif engine == "xtb":
                    # xtb 同款语义（GH #26）：FAILED TO CONVERGE 即 False
                    result["opt_converged"] = xtb_frames.opt_converged(log_text)
                elif engine == "gaussian":
                    converged = gaussian_frames.opt_converged(log_text)
                    if converged is None and {"opt", "ts"} & detected_jobs:
                        # Gaussian cclib optdone also contains IRC corrector
                        # steps, which are not independent optimizations.
                        optdone = getattr(data, "optdone", None)
                        if optdone is not None:
                            converged = bool(optdone)
                    result["opt_converged"] = converged
                elif data is not None:
                    optdone = getattr(data, "optdone", None)
                    if optdone is not None:
                        result["opt_converged"] = bool(optdone)

            # job_type / scan / irc 摘要（Gaussian IRC 逐点解析在 core.gaussian_frames 自写；
            # ORCA 侧由 core.orca_frames.extract_irc 从主输出的 FORWARD/BACKWARD
            # IRC 迭代块与 PATH SUMMARY 提取点数/收敛/端点能量）
            if "job_types" in requested:
                result["job_types"] = sorted(detected_jobs)

            if {"scan_parameter", "scan_energies_ev"} & requested:
                scanparm = getattr(data, "scanparm", None)
                scanenergies = getattr(data, "scanenergies", None)
                if scanparm is not None and len(scanparm) > 0:
                    result["scan_parameter"] = [float(v) for v in np.asarray(scanparm[0], dtype=float)]
                if scanenergies is not None and len(scanenergies) > 0:
                    result["scan_energies_ev"] = [float(v) for v in np.asarray(list(scanenergies), dtype=float)]

            if "scan" in detected_jobs and engine in {"orca", "gaussian"}:
                from cloudra.tools.Chemtool.ts_guess import _ScanStepsUngroupable, _SidecarIncomplete

                try:
                    scan = self._scan_summary(log_path, engine, log_text)
                    result["message"] += " " + scan.pop("message")
                    result.update(scan)
                except (ValueError, _ScanStepsUngroupable, _SidecarIncomplete) as exc:
                    result["message"] += f" Scan peak could not be established: {exc}"

            if any(f.startswith("irc_") for f in requested):
                if engine == "orca":
                    if "irc" in detected_jobs:
                        try:
                            irc_meta = orca_frames.extract_irc_from_text(log_text)
                            result["irc_num_points_forward"] = irc_meta["num_points_forward"]
                            result["irc_num_points_backward"] = irc_meta["num_points_backward"]
                            if irc_meta["endpoint_energies_hartree"] is not None:
                                result["irc_endpoint_energies_hartree"] = [
                                    float(v) for v in irc_meta["endpoint_energies_hartree"]
                                ]
                            result["irc_both_directions_converged"] = bool(
                                irc_meta["forward_converged"] and irc_meta["backward_converged"]
                            )
                        except ValueError as e:
                            result["message"] = f"Log parsed; ORCA IRC extraction failed: {e}"
                elif engine == "gaussian" and "irc" in detected_jobs:
                    try:
                        _irc_frames, irc_meta = gaussian_frames.extract_irc_from_text(log_text)
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

    @staticmethod
    def _scan_summary(log_path: str, engine: str, text: str) -> dict[str, Any]:
        """Reuse the scan tool's native parsing and peak math without writing a guess."""
        from cloudra.tools.Chemtool.ts_guess import (
            KCAL_PER_HARTREE,
            _gaussian_scan_is_grid,
            _orca_scan_is_grid,
            _parse_gaussian_scan_summary,
            _parse_orca_relaxed_scan_sidecar,
            _parse_orca_scan,
            _SidecarIncomplete,
            analyze_scan_profile,
        )
        from cloudra.tools.core import orca_frames

        geometry_available = True
        notes = []
        if engine == "orca":
            if _orca_scan_is_grid(log_path, text):
                return {'scan_has_internal_peak': None, 'scan_peak': None,
                        'message': 'Independent multidimensional scan grid is not a one-dimensional path; no candidate was derived.'}
            try:
                sidecar = _parse_orca_relaxed_scan_sidecar(log_path)
                energies = sidecar["energies"] if sidecar else [
                    step["energy_hartree"] for step in _parse_orca_scan(text)
                ]
            except _SidecarIncomplete as exc:
                if not exc.energies:
                    return {'scan_has_internal_peak': None, 'scan_peak': None, 'message': str(exc)}
                energies = exc.energies
                geometry_available = False
                notes.append(str(exc))
        else:
            import cclib
            try:
                data = cclib.io.ccread(log_path)
            except Exception:
                data = None
            if _gaussian_scan_is_grid(text, data):
                return {'scan_has_internal_peak': None, 'scan_peak': None,
                        'message': 'Independent Gaussian multidimensional grid is not a one-dimensional path; no candidate was derived.'}
            energies = _parse_gaussian_scan_summary(text)
        profile = analyze_scan_profile([(e - energies[0]) * KCAL_PER_HARTREE for e in energies])
        indices = profile['peak_indices']
        internal = bool(indices)
        peak = None
        if len(indices) == 1:
            index = indices[0]
            geometry_ref = None
            if engine == "orca" and geometry_available:
                for directory, stem in orca_frames._orca_sidecar_roots(log_path, text):
                    path = os.path.join(directory, f"{stem}.{index + 1:03d}.xyz")
                    if os.path.isfile(path):
                        geometry_ref = path
                        break
            peak = ScanPeak(
                point_number=index + 1, energy_hartree=energies[index],
                relative_to_first_point_kcal=(energies[index] - energies[0]) * KCAL_PER_HARTREE, geometry_ref=geometry_ref,
            )
            message = (
                f"Scan has {len(energies)} points; internal maximum at point {index + 1} (1-based), "
                f"{energies[index]:.12f} Hartree, {peak.relative_to_first_point_kcal:.4f} kcal/mol relative to its first point. "
                f"Existing peak XYZ: {geometry_ref or 'unavailable; extract it with ts_guess mode=scan_parse'}. "
                "Use the peak as a ts_prepare seed; it is not a verified TS or reaction barrier."
            )
        elif indices:
            candidates = []
            for index in indices:
                geometry_ref = None
                if engine == 'orca' and geometry_available:
                    for directory, stem in orca_frames._orca_sidecar_roots(log_path, text):
                        path = os.path.join(directory, f'{stem}.{index + 1:03d}.xyz')
                        if os.path.isfile(path):
                            geometry_ref = path
                            break
                candidates.append(f'Candidate point {index + 1}: energy={energies[index]:.12f} Hartree; XYZ={geometry_ref or "unavailable"}')
            message = '; '.join(candidates) + '. Inspect these local peaks and choose one with guess.kind=provided; none is a verified TS.'
        else:
            message = "No internal local scan maximum; an endpoint maximum is not a TS seed."
        return {
            "scan_has_internal_peak": internal, "scan_peak": peak,
            "message": " ".join([message, *profile["verdicts"], *notes]),
        }




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
    that try to set derived evidence fields themselves.  IRC 解析字段
    （点数/收敛/端点能量）只是信息字段：short_irc 阶段绑定不走本 deriver，
    由 harness 按几何方向区间证明重解析日志判定（irc_evidence）。
    """
    del current, arguments  # 本工具派生不需要 current/arguments
    imaginary = _imaginary_frequency_list(result)
    # 终止状态必须是显式 True 才计证据：None（undecidable，未判定终止）与
    # False 一样不发证据——未知终止的日志不能派生 structure/saddle 支撑。
    normal = result.get("normal_termination") is True
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
