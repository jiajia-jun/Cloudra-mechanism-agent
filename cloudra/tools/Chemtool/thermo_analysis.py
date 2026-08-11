import json
import math
import os
import shutil
import subprocess
import tempfile
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.tools.Chemtool.log_parser import _extract_gaussian_thermochemistry

_EH_TO_KCAL = 627.5094740631
_R_J_MOL_K = 8.31446261815324
_HARTREE_J_MOL = 2_625_499.6394799
_R_L_ATM_MOL_K = 0.082057366080960


description = (
    "汇总多个量化输出的反应热化学：按带符号的化学计量系数组合 ΔE、ΔH 与 ΔG，"
    "可把频率计算得到的 RRHO 校正叠加到更高水平单点能上。"
    "raw_rrho 后端忠实使用日志中的 RRHO 热校正；goodvibes 后端显式调用 GoodVibes 做准谐振校正。"
    "所有结果都记录温度、标准态、能量来源与后端，不把缺数据或缺 GoodVibes 静默当作完整结果。"
)


class ThermoSpecies(BaseModel):
    name: str = Field(description="物种唯一名称，用于表格和可选参考物。")
    log_path: str = Field(description="包含频率与热化学摘要的 Gaussian 输出路径。")
    coefficient: float = Field(
        description="带符号化学计量系数：反应物为负、产物为正；中间态比较也可直接给相对系数。"
    )
    single_point_energy_hartree: Optional[float] = Field(
        default=None,
        description="可选的更高水平电子单点能 (Hartree)。提供后，日志只贡献 H/G 的热校正。",
    )


class ThermoAnalysis_input_schema(input_schema):
    species: list[ThermoSpecies] = Field(min_length=1, description="参与汇总的物种及带符号系数。")
    backend: Literal["raw_rrho", "goodvibes"] = Field(
        default="raw_rrho",
        description="raw_rrho：使用日志原始 RRHO；goodvibes：调用外部 GoodVibes 做 quasi-harmonic 校正。",
    )
    temperature: float = Field(default=298.15, gt=0, description="热化学温度 (K)。")
    standard_state: Literal["gas_1atm", "solution_1m", "solution_custom"] = Field(
        default="gas_1atm",
        description="标准态。raw_rrho 的溶液标准态由日志压力做理想气体 1 atm→浓度修正；GoodVibes 用 --conc 重算。",
    )
    concentration_molar: Optional[float] = Field(
        default=None,
        gt=0,
        description="solution_custom 的浓度 (mol/L)；solution_1m 固定为 1.0 mol/L。",
    )
    reference_species: Optional[str] = Field(
        default=None,
        description="可选参考物种名称；提供后，每个物种额外返回相对该物种的 E/H/G。",
    )
    frequency_cutoff_cm: float = Field(
        default=100.0,
        ge=0,
        description="GoodVibes quasi-harmonic 熵/焓共用的低频截止值 (cm⁻¹)。raw_rrho 不使用。",
    )
    frequency_scale_factor: Optional[float] = Field(
        default=None,
        gt=0,
        description="GoodVibes 振动频率缩放因子；缺省时由 GoodVibes 自动判断或使用 1.0。",
    )
    timeout: int = Field(default=600, gt=0, description="GoodVibes 子进程超时（秒）。")


class ThermoAnalysis_output_schema(output_schema):
    is_success: bool = Field(description="工具是否正常执行；科学材料不完整时仍可为 true。")
    status: Literal["complete", "inconclusive"] = Field(description="热化学结果是否完整。")
    species: list[dict] = Field(default_factory=list, description="各物种绝对 E/H/G、校正项与能量来源。")
    reaction: dict = Field(default_factory=dict, description="按系数组合的 ΔE、ΔH、ΔG（Hartree 与 kcal/mol）。")
    assumptions: list[str] = Field(default_factory=list, description="温度、标准态与校正模型假设。")
    provenance: dict = Field(default_factory=dict, description="后端、命令、版本与是否发生 fallback。")
    table: str = Field(default="", description="不含坐标的热化学数值表。")
    message: str = Field(default="", description="状态或不完整原因。")


def _combine_species_records(records: list[dict]) -> dict[str, float]:
    """Combine complete species records with signed stoichiometric coefficients."""
    totals = {
        "delta_e_hartree": sum(r["coefficient"] * r["electronic_energy_hartree"] for r in records),
        "delta_h_hartree": sum(r["coefficient"] * r["enthalpy_hartree"] for r in records),
        "delta_g_hartree": sum(r["coefficient"] * r["gibbs_free_energy_hartree"] for r in records),
    }
    for quantity in ("e", "h", "g"):
        totals[f"delta_{quantity}_kcal_mol"] = (
            totals[f"delta_{quantity}_hartree"] * _EH_TO_KCAL
        )
    return totals


def _concentration(user_input: ThermoAnalysis_input_schema) -> Optional[float]:
    if user_input.standard_state == "gas_1atm":
        return None
    if user_input.standard_state == "solution_1m":
        return 1.0
    return user_input.concentration_molar


def _standard_state_correction_hartree(
    temperature: float,
    concentration_molar: float,
    source_pressure_atm: float,
) -> float:
    """Return RT ln(C°RT/p°) for one ideal-gas molecule, in Hartree."""
    ratio = concentration_molar * _R_L_ATM_MOL_K * temperature / source_pressure_atm
    return (_R_J_MOL_K * temperature * math.log(ratio)) / _HARTREE_J_MOL


def _reaction_expression(records: list[dict]) -> str:
    reactants = []
    products = []
    for record in records:
        coefficient = float(record["coefficient"])
        if coefficient == 0:
            continue
        magnitude = abs(coefficient)
        label = record["name"] if magnitude == 1 else f"{magnitude:g} {record['name']}"
        (products if coefficient > 0 else reactants).append(label)
    return " + ".join(reactants) + " -> " + " + ".join(products)


def _add_relative_values(records: list[dict], reference_species: Optional[str]) -> None:
    if reference_species is None:
        return
    reference = next((record for record in records if record["name"] == reference_species), None)
    if reference is None:
        raise ValueError(f"reference_species 不在 species 中: {reference_species}")
    for record in records:
        record["relative_to"] = reference_species
        record["relative_e_kcal_mol"] = (
            record["electronic_energy_hartree"] - reference["electronic_energy_hartree"]
        ) * _EH_TO_KCAL
        record["relative_h_kcal_mol"] = (
            record["enthalpy_hartree"] - reference["enthalpy_hartree"]
        ) * _EH_TO_KCAL
        record["relative_g_kcal_mol"] = (
            record["gibbs_free_energy_hartree"] - reference["gibbs_free_energy_hartree"]
        ) * _EH_TO_KCAL


def _render_table(
    records: list[dict],
    reaction: dict,
    temperature: float,
    standard_state: str,
    backend: str,
) -> str:
    lines = [
        f"conditions: temperature={temperature:g} K; standard_state={standard_state}; backend={backend}",
        f"{'species':<18} {'coef':>7} {'E / Eh':>16} {'H / Eh':>16} {'G / Eh':>16} {'source':>22}",
        "-" * 101,
    ]
    for row in records:
        lines.append(
            f"{row['name']:<18} {row['coefficient']:>7g} "
            f"{row['electronic_energy_hartree']:>16.8f} {row['enthalpy_hartree']:>16.8f} "
            f"{row['gibbs_free_energy_hartree']:>16.8f} {row['energy_source']:>22}"
        )
    lines.extend([
        "",
        f"reaction: {_reaction_expression(records)}",
        f"delta E/H/G (kcal/mol): {reaction['delta_e_kcal_mol']:.3f} / "
        f"{reaction['delta_h_kcal_mol']:.3f} / {reaction['delta_g_kcal_mol']:.3f}",
    ])
    return "\n".join(lines)


def _load_raw_rrho_record(
    species: ThermoSpecies,
    temperature: float,
    standard_state: str,
    concentration_molar: Optional[float],
) -> tuple[Optional[dict], Optional[str]]:
    import cclib

    data = cclib.io.ccread(species.log_path)
    if data is None:
        return None, f"{species.name}: cclib 未解析到数据"
    log_temperature = getattr(data, "temperature", None)
    if log_temperature is None:
        return None, f"{species.name}: 日志未提供 RRHO 温度，不能确认 thermochemistry 条件"
    if abs(float(log_temperature) - temperature) > 0.05:
        return None, (
            f"{species.name}: 日志 RRHO 温度为 {float(log_temperature):g} K，"
            f"不能直接当作 {temperature:g} K；请重跑频率热化学或使用 GoodVibes"
        )

    thermo = _extract_gaussian_thermochemistry(species.log_path)
    total_h = thermo.get("total_enthalpy_hartree")
    total_g = thermo.get("total_gibbs_free_energy_hartree")
    h_correction = thermo.get("thermal_enthalpy_correction_hartree")
    g_correction = thermo.get("thermal_gibbs_correction_hartree")
    if None in (total_h, total_g, h_correction, g_correction):
        return None, (
            f"{species.name}: 缺少 Gaussian thermochemistry 的总量或 literal H/G correction"
        )
    freq_e_from_h = float(total_h) - float(h_correction)
    freq_e_from_g = float(total_g) - float(g_correction)
    if abs(freq_e_from_h - freq_e_from_g) > 5e-6:
        return None, (
            f"{species.name}: thermochemistry 总量与 H/G correction 对应的电子能不一致"
        )
    freq_e = 0.5 * (freq_e_from_h + freq_e_from_g)
    electronic = (
        species.single_point_energy_hartree
        if species.single_point_energy_hartree is not None
        else freq_e
    )
    state_correction = 0.0
    log_pressure = getattr(data, "pressure", None)
    if log_pressure is None:
        return None, f"{species.name}: 日志未提供 RRHO 压力，不能确认标准态"
    pressure = float(log_pressure)
    if pressure <= 0:
        return None, f"{species.name}: 日志 RRHO 压力必须大于 0 atm"
    if concentration_molar is not None:
        state_correction = _standard_state_correction_hartree(
            temperature, concentration_molar, pressure,
        )
    elif standard_state == "gas_1atm":
        state_correction = (
            _R_J_MOL_K * temperature * math.log(1.0 / pressure)
        ) / _HARTREE_J_MOL

    return {
        "name": species.name,
        "log_path": os.path.abspath(species.log_path),
        "coefficient": float(species.coefficient),
        "frequency_electronic_energy_hartree": freq_e,
        "electronic_energy_hartree": float(electronic),
        "enthalpy_correction_hartree": float(h_correction),
        "gibbs_correction_hartree": float(g_correction),
        "standard_state_g_correction_hartree": state_correction,
        "enthalpy_hartree": float(electronic) + float(h_correction),
        "gibbs_free_energy_hartree": float(electronic) + float(g_correction) + state_correction,
        "energy_source": (
            "supplied_single_point"
            if species.single_point_energy_hartree is not None
            else "frequency_log_scf"
        ),
        "rrho_temperature_k": float(log_temperature) if log_temperature is not None else None,
        "rrho_pressure_atm": pressure,
    }, None


def _goodvibes_command(
    executable: str,
    user_input: ThermoAnalysis_input_schema,
    json_path: str,
) -> list[str]:
    command = [
        executable,
        *[os.path.abspath(species.log_path) for species in user_input.species],
        "-q",
        "-f",
        f"{user_input.frequency_cutoff_cm:g}",
        "--temp",
        f"{user_input.temperature:g}",
    ]
    concentration = _concentration(user_input)
    if concentration is not None:
        command.extend(["--conc", f"{concentration:g}"])
    if user_input.frequency_scale_factor is not None:
        command.extend(["-v", f"{user_input.frequency_scale_factor:g}"])
    command.extend(["--json", json_path])
    return command


def _match_goodvibes_entry(entries: list[dict], species: ThermoSpecies) -> Optional[dict]:
    wanted = os.path.realpath(species.log_path)
    exact = [entry for entry in entries if os.path.realpath(entry.get("file", "")) == wanted]
    if len(exact) == 1:
        return exact[0]
    stem = os.path.splitext(os.path.basename(species.log_path))[0]
    by_name = [entry for entry in entries if entry.get("name") == stem]
    return by_name[0] if len(by_name) == 1 else None


def _load_goodvibes_records(
    user_input: ThermoAnalysis_input_schema,
    executable: str,
) -> tuple[list[dict], dict, Optional[str]]:
    with tempfile.TemporaryDirectory(prefix="cloudra_goodvibes_") as workdir:
        json_path = os.path.join(workdir, "results.json")
        command = _goodvibes_command(executable, user_input, json_path)
        try:
            proc = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=user_input.timeout,
            )
        except subprocess.TimeoutExpired:
            return [], {"command": command}, f"GoodVibes 运行超时（>{user_input.timeout}s）"
        provenance = {
            "backend": "goodvibes",
            "command": command,
            "returncode": proc.returncode,
            "fallback_used": False,
        }
        if proc.returncode != 0 or not os.path.isfile(json_path):
            tail = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-2000:]
            return [], provenance, f"GoodVibes 未生成结构化结果（returncode={proc.returncode}）：{tail}"
        try:
            with open(json_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            return [], provenance, f"GoodVibes JSON 无法解析: {exc}"

    if not isinstance(payload, dict):
        return [], provenance, "GoodVibes JSON top-level must be an object"
    goodvibes_version = payload.get("goodvibes_version")
    if not isinstance(goodvibes_version, str) or not goodvibes_version.strip():
        return [], provenance, "GoodVibes JSON 缺少非空的 goodvibes_version"
    provenance.update({
        "goodvibes_version": goodvibes_version,
        "schema_version": payload.get("schema_version"),
        "options": payload.get("options", {}),
    })
    schema_version = payload.get("schema_version")
    try:
        schema_major = int(str(schema_version).split(".", 1)[0])
    except (TypeError, ValueError):
        return [], provenance, "GoodVibes JSON 缺少可识别的 schema_version"
    if schema_major != 1:
        return [], provenance, (
            f"GoodVibes schema_version={schema_version!r} 不受支持；当前只接受 1.x"
        )
    entries = payload.get("results", [])
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        return [], provenance, "GoodVibes JSON 的 results 必须是对象列表"
    records = []
    for species in user_input.species:
        entry = _match_goodvibes_entry(entries, species)
        if entry is None:
            return [], provenance, f"GoodVibes 结果中无法唯一匹配物种 {species.name}"
        thermo = entry.get("thermo", {})
        if not isinstance(thermo, dict):
            return [], provenance, f"{species.name}: GoodVibes thermo 必须是对象"
        base_energy = thermo.get("sp_energy")
        if base_energy is None:
            base_energy = thermo.get("scf_energy")
        qh_h = thermo.get("qh_enthalpy")
        qh_g = thermo.get("qh_gibbs_free_energy")
        if base_energy is None or qh_h is None or qh_g is None:
            return [], provenance, f"{species.name}: GoodVibes 缺少 qh_enthalpy 或 qh_gibbs_free_energy"
        numeric_values = {}
        for field_name, value in (
            ("base_energy", base_energy),
            ("qh_enthalpy", qh_h),
            ("qh_gibbs_free_energy", qh_g),
        ):
            try:
                if isinstance(value, bool):
                    raise TypeError
                number = float(value)
            except (TypeError, ValueError):
                return [], provenance, (
                    f"{species.name}: GoodVibes 字段 {field_name} must be numeric"
                )
            if not math.isfinite(number):
                return [], provenance, (
                    f"{species.name}: GoodVibes 字段 {field_name} must be finite numeric"
                )
            numeric_values[field_name] = number
        base_energy_value = numeric_values["base_energy"]
        qh_h_value = numeric_values["qh_enthalpy"]
        qh_g_value = numeric_values["qh_gibbs_free_energy"]
        electronic = (
            species.single_point_energy_hartree
            if species.single_point_energy_hartree is not None
            else base_energy_value
        )
        records.append({
            "name": species.name,
            "log_path": os.path.abspath(species.log_path),
            "coefficient": float(species.coefficient),
            "frequency_electronic_energy_hartree": base_energy_value,
            "electronic_energy_hartree": float(electronic),
            "enthalpy_correction_hartree": qh_h_value - base_energy_value,
            "gibbs_correction_hartree": qh_g_value - base_energy_value,
            "standard_state_g_correction_hartree": None,
            "enthalpy_hartree": float(electronic) + qh_h_value - base_energy_value,
            "gibbs_free_energy_hartree": float(electronic) + qh_g_value - base_energy_value,
            "energy_source": (
                "supplied_single_point"
                if species.single_point_energy_hartree is not None
                else ("goodvibes_spc" if thermo.get("sp_energy") is not None else "frequency_log_scf")
            ),
        })
    return records, provenance, None


class ThermoAnalysis(Tool):
    tool_id: str = "t-48"
    tool_name: str = "thermo_analysis"
    tool_description: str = description
    input_schema: Any = ThermoAnalysis_input_schema
    output_schema: Any = ThermoAnalysis_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: ThermoAnalysis_input_schema,
        session: Session,
    ) -> ThermoAnalysis_output_schema:
        names = [species.name for species in user_input.species]
        if len(names) != len(set(names)):
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message="species 名称必须唯一。",
            )
        if not any(species.coefficient != 0 for species in user_input.species):
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message="至少一个化学计量系数必须非零。",
            )
        sp_coverage = [
            species.single_point_energy_hartree is not None
            for species in user_input.species
        ]
        if any(sp_coverage) and not all(sp_coverage):
            return ThermoAnalysis_output_schema(
                is_success=True,
                status="inconclusive",
                provenance={"backend": user_input.backend, "fallback_used": False},
                message=(
                    "single-point 能量只覆盖了部分物种，不能把不同电子结构水平静默混成"
                    "一个反应能；请为全部物种提供同水平单点能，或全部使用频率日志电子能。"
                ),
            )
        if user_input.reference_species is not None and user_input.reference_species not in names:
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message=f"reference_species 不在 species 中: {user_input.reference_species}",
            )
        concentration = _concentration(user_input)
        if user_input.standard_state == "solution_custom" and concentration is None:
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message="solution_custom 必须提供 concentration_molar。",
            )
        missing_paths = [species.log_path for species in user_input.species if not os.path.isfile(species.log_path)]
        if missing_paths:
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message=f"热化学日志不存在: {missing_paths}",
            )

        assumptions = [
            f"temperature={user_input.temperature:g} K",
            f"standard_state={user_input.standard_state}",
        ]
        if concentration is not None:
            assumptions.append(f"concentration={concentration:g} mol/L")

        if user_input.backend == "goodvibes":
            executable = shutil.which("goodvibes")
            provenance = {
                "backend": "goodvibes",
                "fallback_used": False,
            }
            assumptions.append(
                f"GoodVibes quasi-harmonic: -q, cutoff={user_input.frequency_cutoff_cm:g} cm^-1"
            )
            if executable is None:
                return ThermoAnalysis_output_schema(
                    is_success=True,
                    status="inconclusive",
                    assumptions=assumptions,
                    provenance=provenance,
                    message=(
                        "未找到 GoodVibes 可执行程序；goodvibes 后端结果为 inconclusive，"
                        "没有静默回退到 raw_rrho。可安装 goodvibes 后重试。"
                    ),
                )
            records, provenance, error = _load_goodvibes_records(user_input, executable)
            if error:
                return ThermoAnalysis_output_schema(
                    is_success=True,
                    status="inconclusive",
                    assumptions=assumptions,
                    provenance=provenance,
                    message=error,
                )
        else:
            provenance = {
                "backend": "raw_rrho",
                "fallback_used": False,
            }
            assumptions.append(
                "raw Gaussian RRHO corrections; requested temperature must match the frequency log"
            )
            if concentration is not None:
                assumptions.append("ideal-gas RT ln(C°RT/p°) standard-state correction applied per species")
            records = []
            errors = []
            for species in user_input.species:
                record, error = _load_raw_rrho_record(
                    species,
                    user_input.temperature,
                    user_input.standard_state,
                    concentration,
                )
                if error:
                    errors.append(error)
                elif record is not None:
                    records.append(record)
            if errors:
                return ThermoAnalysis_output_schema(
                    is_success=True,
                    status="inconclusive",
                    species=records,
                    assumptions=assumptions,
                    provenance=provenance,
                    message="Thermochemistry 材料不完整：" + "; ".join(errors),
                )

        try:
            _add_relative_values(records, user_input.reference_species)
            reaction = _combine_species_records(records)
        except (KeyError, TypeError, ValueError) as exc:
            return ThermoAnalysis_output_schema(
                is_success=True,
                status="inconclusive",
                species=records,
                assumptions=assumptions,
                provenance=provenance,
                message=f"热化学汇总失败: {exc}",
            )

        return ThermoAnalysis_output_schema(
            is_success=True,
            status="complete",
            species=records,
            reaction=reaction,
            assumptions=assumptions,
            provenance=provenance,
            table=_render_table(
                records,
                reaction,
                user_input.temperature,
                user_input.standard_state,
                user_input.backend,
            ),
            message=(
                f"热化学汇总完成（{user_input.backend}）：{_reaction_expression(records)}。"
                "ΔE/ΔH/ΔG 均由给定的带符号系数组合；请结合所选标准态和能量水平解释。"
            ),
        )


def get_class():
    return ThermoAnalysis
