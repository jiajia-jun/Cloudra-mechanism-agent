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

# GoodVibes 4.x JSON 的 thermo 恒写 sp_energy 键——未做单点修正（SPC）时它与
# scf_energy 逐位相同。sp_energy 与 scf_energy 的差异超过该容差才算真做了 SPC
# （sp_energy 是独立高能级单点），否则不得标 goodvibes_spc。
_SPC_ENERGY_DIFF_EH = 1e-8

# GoodVibes CLI flags verified against GoodVibes 4.2 / 3.x public help:
#   -q              Grimme mRRHO entropy + Head-Gordon qh enthalpy
#   --qs {grimme,truhlar}   quasi-harmonic entropy scheme (default grimme)
#   -f / --tau      shared frequency cutoff for S and H (cm^-1; default 100)
#   --fs / --fh     entropy-only / enthalpy-only overrides of -f
#   --temp TEMP     temperature (K); no short -t in 4.2
#   -c / --conc     solution concentration (mol/L); omit for gas 1 atm
# This module maps frequency_cutoff_cm -> -f (shared cutoff under -q).


description = (
    "Aggregate reaction thermochemistry from multiple QM outputs: combine ΔE, ΔH, and ΔG with signed stoichiometric coefficients; "
    "RRHO corrections from a frequency job can be stacked on a higher-level single-point energy. "
    "The raw_rrho backend uses the log's RRHO thermal corrections as-is; the goodvibes backend calls GoodVibes for quasi-harmonic corrections. "
    "Every result records temperature, standard state, energy source, and backend; missing data or missing GoodVibes is never silently treated as a complete result."
)


class ThermoSpecies(BaseModel):
    name: str = Field(description="Unique species name, used in the table and as an optional reference.")
    log_path: str = Field(
        description="Path of a Gaussian output that contains frequencies and a thermochemistry summary. "
                    "Absolute path, or relative to the agent process's current working directory; absolute paths are recommended."
    )
    coefficient: float = Field(
        description="Signed stoichiometric coefficient: negative for reactants, positive for products; relative coefficients are also fine for intermediate comparisons."
    )
    single_point_energy_hartree: Optional[float] = Field(
        default=None,
        description="Optional higher-level electronic single-point energy (Hartree). When set, the log only contributes H/G thermal corrections.",
    )


class ThermoAnalysis_input_schema(input_schema):
    species: list[ThermoSpecies] = Field(min_length=1, description="Species in the aggregation, with signed coefficients.")
    backend: Literal["raw_rrho", "goodvibes"] = Field(
        default="raw_rrho",
        description="raw_rrho: use the log's original RRHO; goodvibes: call external GoodVibes for quasi-harmonic corrections.",
    )
    temperature: float = Field(default=298.15, gt=0, description="Thermochemistry temperature (K).")
    standard_state: Literal["gas_1atm", "solution_1m", "solution_custom"] = Field(
        default="gas_1atm",
        description=(
            "Standard state. For raw_rrho, solution states apply an ideal-gas 1 atm→concentration correction from the log pressure; "
            "GoodVibes recomputes with --conc/-c (same semantics as raw_rrho: gas omits concentration, solution_1m→1.0 M)."
        ),
    )
    concentration_molar: Optional[float] = Field(
        default=None,
        gt=0,
        description="Concentration (mol/L) for solution_custom; solution_1m is fixed at 1.0 mol/L.",
    )
    reference_species: Optional[str] = Field(
        default=None,
        description="Optional reference species name; when set, each species also returns E/H/G relative to it.",
    )
    qh_scheme: Literal["grimme", "truhlar"] = Field(
        default="grimme",
        description=(
            "GoodVibes quasi-harmonic entropy scheme, mapped to CLI `--qs`: grimme=mRRHO interpolation (default); "
            "truhlar=raise low frequencies. Unused by raw_rrho. Assumes GoodVibes 3.x/4.x."
        ),
    )
    frequency_cutoff_cm: float = Field(
        default=100.0,
        ge=0,
        description=(
            "GoodVibes quasi-harmonic frequency cutoff (cm⁻¹), mapped to CLI `-f/--tau` (applies to both entropy and enthalpy; "
            "default 100. `--fs` is entropy-only; this tool always uses -f under -q). Unused by raw_rrho."
        ),
    )
    frequency_scale_factor: Optional[float] = Field(
        default=None,
        gt=0,
        description="GoodVibes vibrational frequency scale factor; if omitted, GoodVibes auto-detects or uses 1.0.",
    )
    timeout: int = Field(default=600, gt=0, description="GoodVibes subprocess timeout (seconds).")


class ThermoAnalysis_output_schema(output_schema):
    is_success: bool = Field(description="Whether the tool ran normally; may still be true when scientific material is incomplete.")
    status: Literal["complete", "inconclusive"] = Field(description="Whether the thermochemistry result is complete.")
    species: list[dict] = Field(default_factory=list, description="Absolute E/H/G, corrections, and energy source per species.")
    reaction: dict = Field(default_factory=dict, description="ΔE, ΔH, ΔG combined by coefficients (Hartree and kcal/mol).")
    assumptions: list[str] = Field(default_factory=list, description="Temperature, standard-state, and correction-model assumptions.")
    provenance: dict = Field(default_factory=dict, description="Backend, command, version, and whether a fallback occurred.")
    table: str = Field(default="", description="Thermochemistry numeric table without coordinates.")
    message: str = Field(default="", description="Status or reason for incompleteness.")


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

    try:
        data = cclib.io.ccread(species.log_path)
    except Exception as exc:
        # cclib 对版本不兼容的日志会抛裸异常（如 cclib 1.8.1 读 ORCA 6.1.1 全抛
        # IndexError）；解析失败属于"材料不完整"，归入 inconclusive 通道而非逃逸。
        return None, f"{species.name}: cclib 解析日志失败（{type(exc).__name__}: {exc}）"
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

    try:
        with open(species.log_path, encoding="utf-8", errors="replace") as handle:
            log_text = handle.read()
    except OSError as exc:
        return None, f"{species.name}: 日志读取失败（{exc}）"
    thermo = _extract_gaussian_thermochemistry(log_text)
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
        "--qs",
        user_input.qh_scheme,
        "-f",
        f"{user_input.frequency_cutoff_cm:g}",
        "--temp",
        f"{user_input.temperature:g}",
    ]
    concentration = _concentration(user_input)
    if concentration is not None:
        # Prefer long form; GoodVibes also accepts -c (same semantics as raw_rrho solution SS).
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


def _parse_float_token(token: str) -> Optional[float]:
    try:
        value = float(token)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _parse_goodvibes_text_table(stdout: str) -> tuple[list[dict], Optional[str]]:
    """Parse classic GoodVibes stdout tables (3.2 README style and SPC variants).

    Looks for a header containing Structure plus qh-G(T) (or qh-G(T)_SPC) and
    optional qh-H / H_SPC columns. Returns per-structure dicts with keys
    name, scf_energy, qh_enthalpy, qh_gibbs_free_energy (Hartree).
    Never raises: failures return ([], reason).
    """
    if not stdout or not stdout.strip():
        return [], "GoodVibes stdout 为空，无法解析文本表"

    lines = stdout.splitlines()
    header_idx = None
    header_cols: list[str] = []
    for idx, line in enumerate(lines):
        if "Structure" not in line:
            continue
        # Normalize spaced column names like "qh-G(T)" / "T.qh-S"
        tokens = line.split()
        if "Structure" not in tokens:
            continue
        lowered = [t.lower() for t in tokens]
        if not any(t.startswith("qh-g") for t in lowered):
            continue
        header_idx = idx
        header_cols = tokens
        break

    if header_idx is None:
        return [], "GoodVibes stdout 未找到含 qh-G(T) 的 Structure 表头"

    col_index = {name.lower(): i for i, name in enumerate(header_cols)}
    # Structure is always first logical column after optional leading markers.
    structure_i = col_index.get("structure")
    if structure_i is None:
        return [], "GoodVibes 文本表缺少 Structure 列"

    def _find_col(*candidates: str) -> Optional[int]:
        for candidate in candidates:
            key = candidate.lower()
            if key in col_index:
                return col_index[key]
        return None

    e_i = _find_col("E_SPC", "E")
    h_i = _find_col("qh-H", "H_SPC", "H")
    g_i = _find_col("qh-G(T)_SPC", "qh-G(T)")
    if g_i is None:
        return [], "GoodVibes 文本表缺少 qh-G(T) / qh-G(T)_SPC 列"
    if e_i is None or h_i is None:
        return [], "GoodVibes 文本表缺少 E 或焓（H / qh-H / H_SPC）列"

    entries: list[dict] = []
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if set(stripped) <= {"*", "─", "-", "=", " "}:
            if entries:
                break
            continue
        if stripped.startswith("RXN:"):
            break
        # Data rows often start with "o  name ..."
        tokens = stripped.split()
        if not tokens:
            continue
        if tokens[0] in {"o", "*", "x", "!"} and len(tokens) > 1:
            tokens = tokens[1:]
        # Skip Temp/K interval rows that insert an extra temperature column.
        if "temp/k" in {c.lower() for c in header_cols}:
            # Interval tables are not used by this tool; reject explicitly.
            return [], "GoodVibes 温度扫描表（含 Temp/K）不受支持；请使用单温度 --temp"
        # Expect: name + numeric columns matching header after Structure
        numeric_expected = len(header_cols) - structure_i - 1
        if len(tokens) < 1 + numeric_expected:
            continue
        name = tokens[0]
        numbers = tokens[1:]
        if len(numbers) < numeric_expected:
            continue
        # Map relative to columns after Structure
        values_by_header = {}
        for offset, col_name in enumerate(header_cols[structure_i + 1 :]):
            parsed = _parse_float_token(numbers[offset])
            if parsed is None:
                values_by_header = {}
                break
            values_by_header[col_name.lower()] = parsed
        if not values_by_header:
            continue

        def _val(*candidates: str) -> Optional[float]:
            for candidate in candidates:
                key = candidate.lower()
                if key in values_by_header:
                    return values_by_header[key]
            return None

        energy = _val("E_SPC", "E")
        qh_h = _val("qh-H", "H_SPC", "H")
        qh_g = _val("qh-G(T)_SPC", "qh-G(T)")
        if energy is None or qh_h is None or qh_g is None:
            continue
        entries.append({
            "name": name,
            "scf_energy": energy,
            "qh_enthalpy": qh_h,
            "qh_gibbs_free_energy": qh_g,
        })

    if not entries:
        return [], "GoodVibes 文本表未解析到任何物种数据行"
    return entries, None


def _records_from_thermo_maps(
    user_input: ThermoAnalysis_input_schema,
    thermo_by_stem: dict[str, dict],
) -> tuple[list[dict], Optional[str]]:
    records = []
    for species in user_input.species:
        stem = os.path.splitext(os.path.basename(species.log_path))[0]
        thermo = thermo_by_stem.get(stem)
        if thermo is None and len(thermo_by_stem) == 1 and len(user_input.species) == 1:
            thermo = next(iter(thermo_by_stem.values()))
        if thermo is None:
            return [], f"GoodVibes 结果中无法唯一匹配物种 {species.name}（stem={stem}）"
        base_energy = thermo.get("sp_energy")
        if base_energy is None:
            base_energy = thermo.get("scf_energy")
        qh_h = thermo.get("qh_enthalpy")
        qh_g = thermo.get("qh_gibbs_free_energy")
        if base_energy is None or qh_h is None or qh_g is None:
            return [], f"{species.name}: GoodVibes 缺少 qh_enthalpy 或 qh_gibbs_free_energy"
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
                return [], f"{species.name}: GoodVibes 字段 {field_name} must be numeric"
            if not math.isfinite(number):
                return [], f"{species.name}: GoodVibes 字段 {field_name} must be finite numeric"
            numeric_values[field_name] = number
        base_energy_value = numeric_values["base_energy"]
        qh_h_value = numeric_values["qh_enthalpy"]
        qh_g_value = numeric_values["qh_gibbs_free_energy"]
        electronic = (
            species.single_point_energy_hartree
            if species.single_point_energy_hartree is not None
            else base_energy_value
        )
        # SPC 判据：仅当 sp_energy 与 scf_energy 显著不同（> _SPC_ENERGY_DIFF_EH）时
        # 才认为该物种真做了独立单点修正；GoodVibes 4.x 未做 SPC 时也恒写 sp_energy
        #（与 scf_energy 相同），不能凭"sp_energy 键存在"就标 goodvibes_spc。
        spc_detected = False
        sp_energy_value = thermo.get("sp_energy")
        scf_energy_value = thermo.get("scf_energy")
        if (
            sp_energy_value is not None
            and not isinstance(sp_energy_value, bool)
            and scf_energy_value is not None
            and not isinstance(scf_energy_value, bool)
        ):
            try:
                spc_detected = (
                    math.isfinite(float(sp_energy_value))
                    and math.isfinite(float(scf_energy_value))
                    and abs(float(sp_energy_value) - float(scf_energy_value)) > _SPC_ENERGY_DIFF_EH
                )
            except (TypeError, ValueError):
                spc_detected = False
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
                else ("goodvibes_spc" if spc_detected else "frequency_log_scf")
            ),
        })
    return records, None


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
            "qh_scheme": user_input.qh_scheme,
            "frequency_cutoff_cm": user_input.frequency_cutoff_cm,
        }
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined_tail = (stdout + "\n" + stderr)[-2000:]

        json_error: Optional[str] = None
        payload: Optional[dict] = None
        if proc.returncode != 0:
            json_error = f"GoodVibes 退出码非零（returncode={proc.returncode}）：{combined_tail}"
        elif not os.path.isfile(json_path):
            json_error = "GoodVibes 未生成 JSON 文件"
        else:
            try:
                with open(json_path, encoding="utf-8") as handle:
                    loaded = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                json_error = f"GoodVibes JSON 无法解析: {exc}"
            else:
                if not isinstance(loaded, dict):
                    json_error = "GoodVibes JSON top-level must be an object"
                else:
                    payload = loaded

        if payload is not None:
            goodvibes_version = payload.get("goodvibes_version")
            if not isinstance(goodvibes_version, str) or not goodvibes_version.strip():
                json_error = "GoodVibes JSON 缺少非空的 goodvibes_version"
            else:
                provenance.update({
                    "goodvibes_version": goodvibes_version,
                    "schema_version": payload.get("schema_version"),
                    "options": payload.get("options", {}),
                    "parse_source": "json",
                })
                schema_version = payload.get("schema_version")
                try:
                    schema_major = int(str(schema_version).split(".", 1)[0])
                except (TypeError, ValueError):
                    json_error = "GoodVibes JSON 缺少可识别的 schema_version"
                else:
                    if schema_major != 1:
                        json_error = (
                            f"GoodVibes schema_version={schema_version!r} 不受支持；"
                            "当前只接受 1.x"
                        )
                    else:
                        entries = payload.get("results", [])
                        if not isinstance(entries, list) or not all(
                            isinstance(entry, dict) for entry in entries
                        ):
                            json_error = "GoodVibes JSON 的 results 必须是对象列表"
                        else:
                            thermo_by_stem: dict[str, dict] = {}
                            for species in user_input.species:
                                entry = _match_goodvibes_entry(entries, species)
                                if entry is None:
                                    json_error = (
                                        f"GoodVibes 结果中无法唯一匹配物种 {species.name}"
                                    )
                                    break
                                thermo = entry.get("thermo", {})
                                if not isinstance(thermo, dict):
                                    json_error = f"{species.name}: GoodVibes thermo 必须是对象"
                                    break
                                stem = os.path.splitext(os.path.basename(species.log_path))[0]
                                thermo_by_stem[stem] = thermo
                            else:
                                records, record_error = _records_from_thermo_maps(
                                    user_input, thermo_by_stem,
                                )
                                if record_error:
                                    json_error = record_error
                                else:
                                    return records, provenance, None

        # JSON path failed: try classic stdout table (GoodVibes 3.2 README style).
        text_entries, text_error = _parse_goodvibes_text_table(stdout)
        if text_error:
            reason = json_error or "GoodVibes JSON 不可用"
            return [], provenance, (
                f"{reason}；文本表回退亦失败：{text_error}"
            )
        provenance["parse_source"] = "stdout_table"
        if json_error:
            provenance["json_parse_error"] = json_error
        thermo_by_stem = {
            entry["name"]: {
                "scf_energy": entry["scf_energy"],
                "qh_enthalpy": entry["qh_enthalpy"],
                "qh_gibbs_free_energy": entry["qh_gibbs_free_energy"],
            }
            for entry in text_entries
        }
        # Also index by basename stem aliases if name differs slightly.
        for entry in text_entries:
            thermo_by_stem.setdefault(entry["name"], {
                "scf_energy": entry["scf_energy"],
                "qh_enthalpy": entry["qh_enthalpy"],
                "qh_gibbs_free_energy": entry["qh_gibbs_free_energy"],
            })
        records, record_error = _records_from_thermo_maps(user_input, thermo_by_stem)
        if record_error:
            return [], provenance, record_error
        return records, provenance, None


class ThermoAnalysis(Tool):
    tool_id: str = "t-50"
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
                message="Species names must be unique. Rename the duplicates and retry.",
            )
        if not any(species.coefficient != 0 for species in user_input.species):
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message="At least one stoichiometric coefficient must be non-zero.",
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
                    "single-point energies cover only part of the species, so energies from different "
                    "electronic-structure levels cannot be silently mixed into one reaction energy; "
                    "provide same-level single-point energies for all species, or use the frequency-log "
                    "electronic energies for all of them."
                ),
            )
        if user_input.reference_species is not None and user_input.reference_species not in names:
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message=f"reference_species is not in species: {user_input.reference_species}",
            )
        concentration = _concentration(user_input)
        if user_input.standard_state == "solution_custom" and concentration is None:
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message="solution_custom requires concentration_molar to be set.",
            )
        missing_paths = [
            species.log_path for species in user_input.species if not os.path.isfile(species.log_path)
        ]
        if missing_paths:
            return ThermoAnalysis_output_schema(
                is_success=False,
                status="inconclusive",
                message=f"Thermochemistry log files do not exist: {missing_paths}. "
                        "Check the paths, then retry.",
            )

        assumptions = [
            f"temperature={user_input.temperature:g} K",
            f"standard_state={user_input.standard_state}",
        ]
        if concentration is not None:
            assumptions.append(f"concentration={concentration:g} mol/L")

        # GoodVibes / 日志解析为同步 IO+子进程；移出事件循环，避免 TUI 假死。
        import asyncio

        return await asyncio.to_thread(
            self._compute_thermochemistry,
            user_input,
            concentration,
            assumptions,
        )

    @staticmethod
    def _compute_thermochemistry(
        user_input: ThermoAnalysis_input_schema,
        concentration: float | None,
        assumptions: list[str],
    ) -> ThermoAnalysis_output_schema:
        if user_input.backend == "goodvibes":
            executable = shutil.which("goodvibes")
            provenance = {
                "backend": "goodvibes",
                "fallback_used": False,
                "qh_scheme": user_input.qh_scheme,
                "frequency_cutoff_cm": user_input.frequency_cutoff_cm,
            }
            assumptions = [
                *assumptions,
                f"GoodVibes quasi-harmonic: -q --qs {user_input.qh_scheme}, "
                f"cutoff(-f)={user_input.frequency_cutoff_cm:g} cm^-1",
            ]
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
            assumptions = [
                *assumptions,
                "raw Gaussian RRHO corrections; requested temperature must match the frequency log",
            ]
            if concentration is not None:
                assumptions.append(
                    "ideal-gas RT ln(C°RT/p°) standard-state correction applied per species"
                )
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


def derive_delivery_changes(
    *,
    current: dict[str, Any],
    role: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """DAG evidence derivation owned by this tool; kept out of DagController."""
    del current, arguments, result  # 本工具派生只需要 role
    if role == "thermochemistry":
        return {"thermochemistry_supported": True}
    return {}
