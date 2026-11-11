"""过渡态初猜工作流工具：插值路径生成 / 约束扫描输入生成 / 扫描日志解析 / TS 候选检查。

xtb_path 执行 xTB 路径搜索；其他模式生成输入、插值或解析证据。
坐标与输入文件一律落盘，上下文只回数值表、判定与路径。
引擎输出解析的正则封装在本模块与 cloudra/tools/core/*_frames 共享层
（gaussian_frames 的 FREQ_LINE_RE / vibdisps_from_text / std_orientation_frames），
agent 无需啃日志格式。

默认 verify 只给 agent 提供方向建议；strict verify 要求同一 TS 的双向 IRC 外侧帧
实际优化到身份正确且零虚频的极小点。证据核对复用 core/irc_evidence，
几何区间检查只提供辅助提示，不决定是否通过。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter
from io import StringIO
from typing import Any, Literal, Optional, Sequence

from pydantic import ConfigDict, Field, StrictInt, model_validator

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core import gaussian_frames, orca_frames
from cloudra.tools.core.geometry_inputs import (
    FrozenCoordinateInput,
    ScanCoordinateInput,
    atom_index_base,
    atom_indices,
    native_coordinate_settings,
)
from cloudra.tools.core.irc_path import (
    COVALENT_RADII as _COVALENT_RADII,
)
from cloudra.tools.core.irc_path import (
    DISTANCE_CONNECTIVITY_FACTOR as _DISTANCE_CONNECTIVITY_FACTOR,
)
from cloudra.tools.core.irc_path import (
    bond_pairs_from_dist as _bond_pairs_from_dist,
)
from cloudra.tools.core.irc_path import (
    classify_watch_pairs as _classify_watch_pairs,
)
from cloudra.tools.core.irc_path import (
    dist_matrix as _dist_matrix,
)
from cloudra.tools.core.irc_path import (
    pair_label as _pair_label,
)
from cloudra.tools.core.irc_path import (
    perceive_bonds as _perceive_bonds,
)
from cloudra.tools.core.molecule import read_molecule, to_ase, to_xyz, total_charge, with_positions
from cloudra.tools.core.qm_calculation import QmCalculation, QmInputSettings
from cloudra.tools.core.qm_engine import detect_qm_engine
from cloudra.tools.core.topology_change import default_connectivity
from cloudra.tools.core.ts_inputs import PathSolvation, ScanGuess
from cloudra.tools.core.xtb_path_runner import DEFAULT_REFINEMENT_RUNS, PathTermination

KCAL_PER_HARTREE = 627.5095
# 虚频模式与反应坐标：watch_pairs 中至少一对的相对位移须达全局最大相对位移的该比例。
_IMAG_MODE_WATCH_RATIO = 0.5

# 可操作补救提示（仅文本）：strict verify 因「材料不足 / 未通过」而不 pass 时追加到
# checks 与 verdict 文案，指导 agent 去补做端点优化，而不是放宽阈值。不改变 verdict 取值。
_IRC_TRUNCATION_REMEDY = (
    "Optimize each actual IRC outer frame to its endpoint minimum and confirm zero imaginary "
    "frequencies. Submit the native Opt/Freq logs as reactant_logs / product_logs "
    "(combined or separate logs), with reactant_path / product_path identifying the expected species."
)

description = (
    "Transition-state (TS) guess workflow: choose an explicit mode. "
    "Use run_id to revise the guess intent of an existing TS run through its durable queue. "
    "The run owns endpoint structures, atom correspondence, charge, multiplicity, electronic character and compute resources. "
    "Independent geometry analysis accepts complete endpoint MOL/SDF graphs and proves their mapping internally; "
    "xtb_path: execute an independent xTB metadynamics path search between confirmed all-atom endpoints; "
    "interpolate: linear or IDPP interpolation from reactant/product xyz to generate NEB candidate-path images "
    "(confirmed automatic atom correspondence, alignment, distance monitoring and a candidate frame); "
    "scan_prepare: write a Gaussian/ORCA constrained-scan input or a typed native xTB scan manifest "
    "(bond/angle/dihedral; xTB requires an explicit method and force_constant); for MLIP/external potentials pass "
    "method='ExtOpt' (ORCA, plus orca_blocks with the %method ProgExt block) or method='external' "
    "(Gaussian, plus keywords='external=\"mace\"'); "
    "scan_parse: inspect a one-dimensional or explicitly concerted native scan path and report internal local-peak candidates. "
    "A unique peak yields a TS-guess xyz; multiple peaks list point numbers, energies and exact XYZ paths in verdicts for a provided-guess choice. "
    "ORCA uses relaxscanact.dat plus matching ts_scan.NNN.xyz frames; independent multidimensional grids are not flattened into paths. "
    "without the sidecar the log text is grouped per 'RELAXED SURFACE SCAN STEP' and each point's converged "
    "(last) energy/geometry is used, so per-cycle energies are never misread as scan points; "
    "verify: by default, frequency plus rough IRC-endpoint connectivity yields candidate/unlikely/inconclusive; "
    "with strict=True, requires exactly one imaginary frequency, bidirectional IRC from that same TS, "
    "expected endpoint structures, and native reactant_logs/product_logs proving that the actual IRC outer frames "
    "were optimized to the correct zero-imaginary minima, yielding pass/fail/inconclusive. "
    "Opt and Freq may be in combined or separate logs; imaginary-mode alignment and geometric interval checks are advisory only. "
    "For an exploratory scan: scan_prepare (after internal_coordinates) → submit → scan_parse. "
    "For formal TS refinement and validation, provide the candidate to ts_prepare rather than submitting manual TS/IRC jobs; "
    "xtb_path/interpolate are fallbacks and never a saddle. Independent xtb_path executes a calculation directly; "
    "run-based operations always use the existing TS revision and queue; "
    "scan_prepare writes an input to submit with submit_compute_job, while interpolate/scan_parse/verify generate or inspect artifacts. "
    "Coordinates never enter context; only numeric tables, verdicts, and file paths are returned."
)


_MODE_FIELDS = {
    'interpolate': {'engine', 'reactant_path', 'reactant_text', 'product_path', 'product_text',
                    'n_images', 'interp_method', 'idpp_mode', 'watch_pairs', 'output_dir', 'selected_candidate',
                    'charge', 'multiplicity', 'electronic_character'},
    'xtb_path': {'engine', 'reactant_path', 'reactant_text', 'product_path', 'product_text',
                 'n_images', 'interp_method', 'idpp_mode', 'watch_pairs', 'output_dir', 'timeout',
                 'refinement_runs', 'charge', 'multiplicity', 'electronic_character', 'selected_candidate'},
    'scan_prepare': {*QmCalculation.model_fields, 'input_path', 'input_text', 'scans', 'freeze',
                     *QmInputSettings.model_fields, 'output_path', 'force_constant', 'scan_mode', 'solvation'},
    'scan_parse': {'engine', 'log_path', 'ts_candidate_path', 'watch_pairs'},
    'verify': {'engine', 'freq_log', 'irc_log', 'reactant_path', 'reactant_text',
               'product_path', 'product_text', 'reactant_logs', 'product_logs', 'watch_pairs',
               'charge', 'strict', 'output_dir'},
}

_RUN_MODE_FIELDS = {
    'xtb_path': {'method', 'refinement_runs', 'solvation'},
    'interpolate': {'n_images', 'interp_method', 'idpp_mode', 'watch_pairs'},
    'scan_prepare': {*QmCalculation.model_fields, 'scans', 'freeze', 'force_constant', 'scan_mode', 'solvation'},
    'scan': {*QmCalculation.model_fields, 'scans', 'freeze', 'force_constant', 'scan_mode', 'solvation'},
    'provided': {'ts_candidate_path', 'evidence_refs'},
}


def _mode_json_schema(schema: dict[str, Any]) -> None:
    """Expose mode requirements alongside the shared field definitions."""
    def path_or_text(prefix: str) -> dict:
        return {"anyOf": [
            {"properties": {field: {"type": "string", "minLength": 1}}, "required": [field]}
            for field in (prefix + "_path", prefix + "_text")
        ]}

    branches = [
        {
            "properties": {"mode": {"const": mode}}, "required": ["mode"],
            "allOf": [path_or_text("reactant"), path_or_text("product")],
        }
        for mode in ("xtb_path", "interpolate")
    ]
    scan_array = next(item for item in schema["properties"]["scans"]["anyOf"]
                      if item.get("type") == "array")
    for mode in ("scan_prepare", "scan"):
        properties = {
            "mode": {"const": mode},
            "engine": {"enum": ['gaussian', 'orca', 'xtb']},
            "method": {"type": "string", "minLength": 1},
            "basis_set": {"type": "string"},
            "scans": dict(scan_array, minItems=1),
            "output_path": {"type": "string", "minLength": 1},
        }
        if mode == "scan":
            properties["log_path"] = {"enum": ["", None]}
        branches.append({
            "properties": properties, "required": ["mode", "engine", "method", "basis_set", "scans", "output_path"],
            **path_or_text("input"),
        })
    for mode, field in (("scan_parse", "log_path"), ("verify", "freq_log"), ("scan", "log_path")):
        branches.append({
            "properties": {"mode": {"const": mode}, field: {"type": "string", "minLength": 1}},
            "required": ["mode", field],
        })
    for branch in branches:
        mode = branch['properties']['mode']['const']
        selected = ('scan_parse' if 'log_path' in branch.get('required', []) else 'scan_prepare') if mode == 'scan' else mode
        allowed = _MODE_FIELDS[selected] | {'mode'}
        if mode == 'scan' and selected == 'scan_prepare':
            allowed.add('log_path')
        branch['properties'].update({field: {'not': {}} for field in schema['properties'] if field not in allowed})
    for mode, fields in _RUN_MODE_FIELDS.items():
        allowed = fields | {'mode', 'run_id'}
        branches.append({
            'properties': {'mode': {'const': mode}, 'run_id': {'type': 'string', 'minLength': 1},
                **{field: {'not': {}} for field in schema['properties'] if field not in allowed}},
            'required': ['mode', 'run_id'],
        })
    schema["oneOf"] = branches


class TsGuess_input_schema(QmInputSettings, input_schema):
    model_config = ConfigDict(json_schema_extra=_mode_json_schema)

    @classmethod
    def to_parameters_schema(cls) -> dict:
        parameters = super().to_parameters_schema()
        parameters["oneOf"] = cls.model_json_schema()["oneOf"]
        return parameters

    mode: Literal[
        "xtb_path", "interpolate", "scan_prepare", "scan_parse", "verify", "scan", "provided",
    ] = Field(
        description="Required sub-function; no calculation path is selected when mode is omitted. "
                    "DEFAULT SEED PATH when one forming/breaking bond/angle is known: "
                    "scan_prepare → submit → scan_parse (relaxed scan), then provide the peak to ts_prepare for formal TS refinement. "
                    "Do NOT default to xtb_path/interpolate just because they are cheap. "
                    "xtb_path: xTB metadynamics path search between endpoints (needs `xtb`); falls back to "
                    "interpolate with path_kind='idpp_fallback' when xtb is absent (never silently). "
                    "interpolate: IDPP/linear images — only when both endpoints and the all-atom map are already "
                    "trustworthy; it is not the default TS-seed start. "
                    "scan_prepare (write a scan input; atom indices should come from internal_coordinates first), "
                    "scan_parse (parse a scan log and judge), verify (frequency+IRC verification). "
                    "Alias: 'scan' maps to 'scan_prepare' (or 'scan_parse' if log_path is given). "
                    "NOTE: xtb_path/interpolate return a PATH AND A GUESS, never a saddle point — "
                    "unconstrained OptTS + frequency + IRC are still required. The former 'xtb_neb' alias is gone: xTB has no NEB."
    )

    run_id: str | None = Field(default=None, min_length=1,
        description='Existing TS run in the current project and workspace. Mutually exclusive with endpoint files/text, charge/multiplicity/electronic_character and output/resource overrides. Guess changes use the existing revision transaction and automatic queue.')
    selected_candidate: StrictInt | None = Field(default=None, ge=0,
        description='Independent endpoint analysis: optional 0-based override of a complete concrete atom-correspondence candidate. Omitted/null uses the existing mapping ranking automatically.')
    evidence_refs: list[str] = Field(default_factory=list,
        description='provided with run_id: source evidence for the supplied TS candidate.')

    # ---------- interpolate ----------
    reactant_path: Optional[str] = Field(
        default=None,
        description="Independent path/interpolation: complete reactant MOL/SDF graph; verify also accepts XYZ reference geometry. Declared graphs are retained. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    reactant_text: Optional[str] = Field(
        default=None,
        description="Reactant XYZ/MOL/SDF text; strict verify uses it to identify the expected reactant. Path takes precedence.",
    )
    product_path: Optional[str] = Field(
        default=None,
        description="Independent path/interpolation: complete product MOL/SDF graph; verify also accepts XYZ reference geometry. Declared graphs are retained. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    product_text: Optional[str] = Field(
        default=None,
        description="Product XYZ/MOL/SDF text; strict verify uses it to identify the expected product. Path takes precedence.",
    )
    n_images: int = Field(default=10, description="interpolate: total image count (including endpoints), ≥2.")
    interp_method: Literal["idpp", "linear"] = Field(
        default="idpp", description="interpolate: interpolation method. idpp uses the selected idpp_mode; linear is Cartesian interpolation without relaxation."
    )
    idpp_mode: Literal["standard", "light"] = Field(
        default="standard",
        description="interpolate (also independent xtb_path fallback): standard uses ASE's current-distance^-4 "
                    "IDPP potential with coupled NEB and MDMin; light preserves the original fixed-target-weight, "
                    "independent-image Adam approximation. Only used when interp_method=idpp. "
                    "Unrelated to agent experiment arms. Neither method verifies a TS.",
    )
    watch_pairs: list[list[int]] = Field(
        default_factory=list,
        description="xtb_path/interpolate/scan_parse: pairs for distance monitoring; verify: pairs for advisory imaginary-mode alignment. "
                    "Indices refer to the concrete reactant XYZ for path/interpolation, each scan frame for scan_parse, "
                    "and the TS frequency geometry for verify, including explicit H. Gaussian/xTB are 1-based; ORCA is 0-based. "
                    "Use internal_coordinates on that file or reaction_mapping's concrete_watch_pairs with complete, current structure binding; "
                    "SMILES graph indices and indices from another atom order are not interchangeable. "
                    "If omitted, distance checks nominate bond-change and largest-distance-change pairs; imaginary-mode alignment is skipped.",
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="interpolate: image output directory (default ./ts_interp/); verify: directory to write IRC endpoints (default <freq_log_stem>_verify/). "
                    "Relative paths resolve against the Agent working directory.",
    )
    timeout: int = Field(
        default=900,
        description="xtb_path: subprocess timeout in seconds. On expiry only this run's own "
                    "process group is terminated; its logs and intermediate files are kept.",
    )
    refinement_runs: int = Field(
        default=DEFAULT_REFINEMENT_RUNS, ge=1,
        description="xtb_path: ceiling on the number of path-refinement cycles handed to xTB "
                    "($path nrun). This is a COMPUTE ceiling, not a convergence criterion: the "
                    "engine stops by itself when its own criterion is met. Do NOT lower it: the "
                    "engine's built-in default is 3 cycles, which measurably truncates the path "
                    "(the highest frame then sits in the reactant's own basin, 21 deg from the "
                    "start, and an OptTS started from it never converges). If a run reports "
                    "termination='path_not_converged', raise this and rerun.",
    )

    # ---------- scan_prepare ----------
    input_path: Optional[str] = Field(default=None, description="scan_prepare: input structure file path (XYZ/MOL/SDF). Absolute as-is, or relative to the Agent working directory.")
    input_text: Optional[str] = Field(default=None, description="scan_prepare: input structure XYZ/MOL/SDF text.")
    engine: Literal["gaussian", "orca", "xtb"] | None = Field(default=None, description="Required explicit engine for scan_prepare. For scan_parse/verify, omit to detect Gaussian/ORCA from the native log; an explicit engine must match the log. For geometry modes this selects atom numbering, not a calculation method.")
    scans: Optional[list[ScanCoordinateInput]] = Field(
        default=None,
        description=(
            "scan_prepare: scan-coordinate list, one entry per scanned coordinate. "
            "Each entry: {\"coord_type\": \"bond\"|\"angle\"|\"dihedral\", \"atoms\": [2|3|4 atom indices], "
            "Atoms refer to the exact input_path/input_text XYZ order, including explicit H. "
            "Gaussian and xTB use 1-based indices; ORCA uses 0-based indices. internal_coordinates on that same structure is 1-based: subtract 1 only for ORCA. "
            "\"scan_start\": optional start value (default the current geometry value), \"scan_end\": end value, "
            "\"scan_steps\": step count}. A single entry drives a 1D scan. Two ORCA coordinates require scan_mode='concerted' "
            "for a simultaneous path or 'grid' for an independent potential-energy surface. Gaussian uses an independent grid; "
            "xTB requires concerted or sequential. scan_parse does not derive a TS candidate from a grid. "
            "Scanning only one geometric coordinate is often not enough: TS search frequently needs a second, "
            "coupled coordinate (e.g. both the forming and the breaking bond) to see a barrier."
        )
    )
    freeze: list[FrozenCoordinateInput] = Field(
        default_factory=list,
        description="scan_prepare: coordinates held at the input geometry value; atoms belong to the exact input XYZ order including explicit H. "
                    "Gaussian/xTB atoms start at 1; ORCA at 0. Do not freeze a scanned coordinate.",
    )
    method: str | None = Field(default=None, description="scan_prepare requires one native method token. Put the basis only in basis_set and additional native settings only in keywords. Use the same calculation fields as qm_input_writer and ts_prepare. Current task requirements govern the method; MethodPolicy applies only to Benchmark tasks.")
    basis_set: str | None = Field(default=None, description="scan_prepare requires an explicit basis token, or an explicit empty string for a method with no basis. Declare the method and basis in their separate fields.")
    keywords: str = Field(default='', description="scan_prepare: explicitly requested native electronic keywords, e.g. D3BJ RIJCOSX def2/J TightSCF CPCM(DCM) for ORCA, or scrf=(solvent=water) for Gaussian.")
    frequency_mode: Literal['auto', 'analytic', 'numeric'] = Field(default='auto', description="Native frequency-mode declaration. Setting this without a frequency task produces a warning and does not add a frequency task.")
    output_path: Optional[str] = Field(default=None, description="scan_prepare: path to write the Gaussian/ORCA input or xTB typed manifest (required). Absolute as-is, or relative to the Agent working directory.")
    orca_blocks: Optional[str] = Field(
        default=None,
        description="scan_prepare: explicit native % blocks preserved beside generated scan coordinates. Additional %geom blocks produce advice; shared resource admission checks %pal/%maxcore declarations. For example, the external-potential block '%method\\n  ProgExt \"/abs/path/to/mace\"\\n  Ext_Params \"--model /abs/model --device cpu --dtype float64\"\\nend' when method='ExtOpt'. For Gaussian the text is preserved in the trailing section with a warning.",
    )

    end_setting: str = Field(default='', description='scan_prepare: explicit trailing native settings, after Gaussian ModRedundant coordinates. With ORCA the text is preserved with a native-syntax warning.')
    force_constant: float | None = Field(default=None, gt=0, allow_inf_nan=False, description='Native xTB scan restraint force constant in atomic units; required for engine=xtb.')
    scan_mode: Literal['concerted', 'sequential', 'grid'] | None = Field(default=None, description='Two-coordinate scan intent: ORCA requires concerted (simultaneous path, equal steps) or grid (independent surface, no automatic TS candidate); xTB supports concerted or sequential. Omit for one coordinate or Gaussian grids.')
    solvation: PathSolvation | None = Field(default=None, description='Native xTB solvation declaration, when used.')

    # ---------- scan_parse ----------
    log_path: Optional[str] = Field(default=None, description="scan_parse: Gaussian/ORCA scan log path, or xTB typed manifest path after completion. Absolute as-is, or relative to the Agent working directory.")
    ts_candidate_path: Optional[str] = Field(
        default=None, description="scan_parse: path to write the TS-guess xyz (default <log_stem>_ts_guess.xyz). Absolute as-is, or relative to the Agent working directory."
    )

    # ---------- verify ----------
    freq_log: Optional[str] = Field(default=None, description="verify: frequency-calculation log path. Absolute as-is, or relative to the Agent working directory.")
    irc_log: Optional[str] = Field(
        default=None,
        description="verify: IRC log path; optional in default mode, required in strict mode with valid frames on both rx<0 and rx>0 sides. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    reactant_logs: list[str] = Field(default_factory=list,
        description="verify strict: native Opt and Freq logs proving an actual IRC outer frame was optimized to the expected reactant zero-imaginary minimum. Combined Opt/Freq or separate logs are accepted. Paths are absolute or relative to the Agent working directory.")
    product_logs: list[str] = Field(default_factory=list,
        description="verify strict: native Opt and Freq logs proving the opposite IRC outer frame was optimized to the expected product zero-imaginary minimum. Combined Opt/Freq or separate logs are accepted. Paths are absolute or relative to the Agent working directory.")
    strict: bool = Field(
        default=False,
        description="verify only: prove direction using the same TS and bidirectional IRC plus actual outer-frame Opt/Freq logs and expected endpoint structures. "
                    "IRC itself need not reach minima; the optimized endpoints must have zero imaginary frequencies. Imaginary-mode alignment and geometric intervals are advisory.",
    )

    @model_validator(mode="after")
    def require_mode_inputs(self):
        if self.run_id is not None:
            if self.mode not in _RUN_MODE_FIELDS:
                raise ValueError(f'{self.mode} is independent evidence analysis; omit run_id')
            unused = self.model_fields_set - (_RUN_MODE_FIELDS[self.mode] | {'mode', 'run_id'})
            if unused:
                raise ValueError(f'run {self.mode} does not use fields: {", ".join(sorted(unused))}; endpoint and resource state belongs to the run')
            return self
        if self.mode == 'provided':
            raise ValueError('provided requires run_id')
        mode = "scan_parse" if self.mode == "scan" and self.log_path else (
            "scan_prepare" if self.mode == "scan" else self.mode
        )
        if mode in {"xtb_path", "interpolate"}:
            if not (self.reactant_path or self.reactant_text):
                raise ValueError(f"{mode} requires reactant_path or reactant_text")
            if not (self.product_path or self.product_text):
                raise ValueError(f"{mode} requires product_path or product_text")
        elif mode == "scan_prepare":
            if not (self.input_path or self.input_text):
                raise ValueError("scan_prepare requires input_path or input_text")
            if not self.method or not self.method.strip():
                raise ValueError("scan_prepare requires an explicit method")
            if self.engine is None:
                raise ValueError('scan_prepare requires an explicit engine')
            if self.basis_set is None:
                raise ValueError("scan_prepare requires an explicit basis_set; use '' for no basis")
            QmCalculation.model_validate({field: getattr(self, field) for field in QmCalculation.model_fields})
            if self.engine == 'xtb' and 'mem' in self.model_fields_set:
                raise ValueError('native xTB scan does not use mem; this field is for Gaussian/ORCA inputs')
            if not self.scans:
                raise ValueError("scan_prepare requires scans: at least one scanned coordinate")
            if not self.output_path:
                raise ValueError("scan_prepare requires output_path")
        elif mode == "scan_parse" and not self.log_path:
            raise ValueError("scan_parse requires log_path")
        elif mode == "verify" and not self.freq_log:
            raise ValueError("verify requires freq_log")
        allowed = _MODE_FIELDS[mode] | {'mode'}
        if self.mode == 'scan' and mode == 'scan_prepare':
            allowed.add('log_path')
        unused = self.model_fields_set - allowed
        if unused:
            raise ValueError(f'{mode} does not use fields: {", ".join(sorted(unused))}; remove them or select the corresponding operation')
        return self


class TsGuess_output_schema(output_schema):
    is_success: bool = Field(description="Whether the operation succeeded")
    message: str = Field(default="", description="Status or error message")
    warnings: list[dict] = Field(default_factory=list, description="Native calculation advice; declared settings are preserved.")
    process: dict | None = Field(default=None,
        description='For run_id operations: authoritative TS process view after the accepted guess revision. A successful call is not scientific verification.')
    diagnostics: list[str] = Field(default_factory=list,
        description='Original independent path-runner diagnostics; retained on failure and explicit interpolation fallback.')
    mapping_candidates: list[dict] = Field(default_factory=list,
        description='Independent geometry analysis: available endpoint correspondence alternatives when binding cannot be completed. These are mapping alternatives, not verified TS results; selected_candidate can specify an override.')
    calculation: QmCalculation | None = Field(default=None,
        description="scan_prepare: complete settings of the written input/manifest. Preparation is not a calculation result or TS validation.")

    # interpolate
    interpolation: dict | None = Field(default=None,
        description="Interpolation method and numerical termination record, also saved to interpolation.json. "
                    "is_success means artifacts generated, not IDPP convergence or TS verification. "
                    "Null for non-interpolation operations and older saved results.")
    images_dir: str = Field(default="", description="interpolate/xtb_path: image directory, or the retained run directory on an unsuccessful xTB path search")
    distance_table: str = Field(default="", description="interpolate/scan_parse: per-frame observed distance text table; scan_parse marks missing or unaligned geometries explicitly")
    ts_candidate_index: Optional[int] = Field(default=None, description="TS candidate frame index (0-based)")
    # scan_parse 也复用 ts_candidate_path
    ts_candidate_path: str = Field(default="", description="TS-guess xyz path")
    refinement_termination: Literal["", "converged", "cycles_exhausted"] = Field(
        default="",
        description="xtb_path: what the engine's own path-refinement loop reported. 'converged' = "
                    "xTB declared its convergence criterion met (the only state in which the TS "
                    "candidate is handed over); 'cycles_exhausted' = the refinement hit the "
                    "`refinement_runs` ceiling and the path is TRUNCATED, so is_success is False.",
    )
    path_termination_reason: Optional[PathTermination] = Field(
        default=None,
        description="xtb_path: overall runner outcome, separate from the engine's refinement marker.",
    )
    path_kind: Literal["", "xtb_path", "idpp_fallback"] = Field(
        default="",
        description="How the path guess was produced. 'xtb_path' = xTB metadynamics path search; "
                    "'idpp_fallback' = xtb was unavailable so IDPP interpolation was used instead "
                    "(a degraded route, reported explicitly); '' = this mode does not produce a path. "
                    "Never treat a guess as a verified saddle point.",
    )

    # scan_prepare
    input_file_path: str = Field(default="", description="scan_prepare: generated input file path")
    run_hint: str = Field(default="", description="scan_prepare: submit/run hint")

    # scan_parse
    profile_table: str = Field(default="", description="scan_parse: per-point relative-energy text table (kcal/mol)")
    scan_has_internal_peak: Optional[bool] = Field(
        default=None,
        description="scan_parse: whether an analyzed energy profile has an internal maximum; null when no reliable energy profile was parsed, independent of geometry availability.",
    )
    verdicts: list[str] = Field(default_factory=list, description="scan_parse: profile verdicts")
    barrier_kcal: Optional[float] = Field(default=None, description="scan_parse: constrained-scan diagnostic only (highest point − first point, kcal/mol) — NOT a verified ΔE‡/ΔG‡; unconstrained OptTS + freq + IRC still required before any barrier claim")
    candidate: Optional[dict] = Field(
        default=None,
        description="scan_parse: unique constrained-scan local-peak candidate as {scan_index, energy, geometry_ref, source}; "
                    "not a validated TS. Multiple candidates are listed in verdicts with point/energy/XYZ for an existing provided-guess choice; "
                    "null when no unique candidate was selected or its geometry is unavailable.",
    )
    candidate_unavailable: bool = Field(
        default=False,
        description="scan_parse: an internal peak exists but its geometry could not be "
                    "recovered from this run's artifacts (a missing sidecar frame is NEVER "
                    "substituted with the last frame).",
    )

    # verify
    verdict: str = Field(
        default="",
        description="verify: default candidate/unlikely/inconclusive; strict is pass/fail/inconclusive.",
    )
    verification_status: Literal["", "candidate", "pass", "fail", "inconclusive"] = Field(
        default="",
        description="verify: structured status from the verification branch; empty outside verify or when verification could not run.",
    )
    n_imag: Optional[int] = Field(default=None, description="verify: number of imaginary frequencies")
    imag_freqs: list[float] = Field(default_factory=list, description="verify: imaginary frequencies (cm⁻¹, negative)")
    checks: list[str] = Field(default_factory=list, description="verify: per-check details")
    irc_end_a_path: str = Field(default="", description="verify: IRC endpoint A xyz path")
    irc_end_b_path: str = Field(default="", description="verify: IRC endpoint B xyz path")
    imag_mode_aligned: Optional[bool] = Field(
        default=None,
        description="verify: advisory heuristic of whether the imaginary normal mode matches the watch_pairs reaction coordinate; "
                    "None if skipped or undecidable. Does not decide strict verification.",
    )
    imag_mode_alignment: str = Field(
        default="",
        description="verify: explanation of the imaginary-mode vs reaction-coordinate alignment check.",
    )


# ---------------------------------------------------------------------------
# 通用 xyz 读取 / 几何
# ---------------------------------------------------------------------------

def _source_molecule(user_input, role: str):
    """工具入口转换一次；内部继续传递完整分子，不丢弃声明图。"""
    declared = user_input.charge if "charge" in getattr(user_input, "model_fields_set", {"charge"}) else None
    return read_molecule(
        input_path=getattr(user_input, role + "_path"),
        input_text=getattr(user_input, role + "_text"), charge=declared,
    )


def _reference_molecules(user_input):
    return {role: _source_molecule(user_input, role) for role in ("reactant", "product")
            if getattr(user_input, role + "_path") or getattr(user_input, role + "_text")}


class _UnconfirmedEndpointMapping(ValueError):
    def __init__(self, message, candidates):
        super().__init__(message)
        self.candidates = candidates


def _independent_path_endpoints(user_input):
    """Import once, then use the same confirmed endpoint state as TS runs."""
    from rdkit import Chem

    from cloudra.tools.Chemtool.reaction_mapping import bind_reaction_structures
    from cloudra.tools.core.reaction_state import ReactionStructures, path_endpoints
    from cloudra.tools.core.ts_inputs import TsInput

    molecules = _reference_molecules(user_input)
    for role, mol in molecules.items():
        if mol.HasProp('cloudra_graph_status') and mol.GetProp('cloudra_graph_status') == 'unresolved':
            raise ValueError(f'{role} XYZ has unresolved molecular identity; supply a complete MOL/SDF graph before endpoint mapping')
    reaction = dict(
        reactant_smiles=Chem.MolToSmiles(Chem.RemoveHs(molecules['reactant']), canonical=False),
        product_smiles=Chem.MolToSmiles(Chem.RemoveHs(molecules['product']), canonical=False),
        charge=total_charge(molecules['reactant']), multiplicity=user_input.multiplicity,
        electronic_character=user_input.electronic_character,
    )
    if user_input.selected_candidate is not None:
        reaction['selected_candidate'] = user_input.selected_candidate
    binding = bind_reaction_structures(TsInput(reaction=reaction), molecules['reactant'], molecules['product'])
    if binding.get('binding_status') != 'complete':
        diagnostics = ' '.join(binding.get('binding_diagnostics', []))
        raise _UnconfirmedEndpointMapping('Concrete endpoint correspondence is unconfirmed. ' + diagnostics +
            ' Choose a reported complete mapping candidate with selected_candidate when correspondence is genuinely ambiguous.',
            binding.get('candidates', []))
    state = ReactionStructures(**molecules,
        product_to_reactant=tuple(index - 1 for index in binding['atom_map']))
    return path_endpoints(state)


def _atoms_to_xyz_block(symbols, positions, comment: str = "") -> str:
    lines = [str(len(symbols)), comment]
    for s, p in zip(symbols, positions):
        lines.append(f"{s:<4} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# interpolate：对齐 + 插值 + IDPP
# ---------------------------------------------------------------------------

def _kabsch_rotate(mobile, ref):
    """把 mobile（已去质心）旋转到 ref（已去质心）上，返回旋转后坐标。纯 numpy Kabsch。"""
    import numpy as np

    h = np.asarray(mobile).T @ np.asarray(ref)
    u, _s, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rot = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    return np.asarray(mobile) @ rot.T


def _select_watch_pairs(symbols, d_start, d_end, watch_pairs, *, index_base=1) -> list[tuple[int, int]]:
    """选监测原子对：给了 watch_pairs 就用它（1-based 输入，越界即报错）；否则用
    irc_path.classify_watch_pairs 的闸门对（键图 diff ∪ |Δd| top-5，唯一实现，
    键图由距离矩阵按共价半径判据派生）。两端无任何显著变化（闸门为空，如刚性
    平移玩具）时退回 |Δd| 最大的 5 对——只用于距离表展示，不作任何判定。
    interpolate 与 xtb_path 共用这一份实现。"""
    import numpy as np

    n = len(symbols)
    if watch_pairs:
        pairs: list[tuple[int, int]] = []
        for pair in watch_pairs:
            if len(pair) != 2:
                raise ValueError(f"Each watch_pairs entry must contain 2 atom indices: {pair}")
            i, j = pair[0] - index_base, pair[1] - index_base
            if not (0 <= i < n and 0 <= j < n) or i == j:
                raise ValueError(
                    f"watch_pairs atom indices out of range: {pair} (system has {n} atoms)"
                )
            pairs.append((min(i, j), max(i, j)))
        return pairs
    start_bonds = _bond_pairs_from_dist(symbols, d_start)
    end_bonds = _bond_pairs_from_dist(symbols, d_end)
    cls = _classify_watch_pairs(symbols, d_start, d_end, start_bonds, end_bonds)
    gate = sorted(set(cls["bond_diff"]) | set(cls["distance_top5"]))
    if gate:
        return gate
    iu = np.triu_indices(n, k=1)
    deltas = np.abs(d_end[iu] - d_start[iu])
    order = np.argsort(-deltas)[:5]
    return sorted({(int(iu[0][o]), int(iu[1][o])) for o in order})


def _scan_geometry_report(energies, frames, watch_pairs, *, index_base=1):
    """Observed distances and adjacent-frame connectivity; neither proves a reaction."""
    import numpy as np

    n = len(energies)
    if not frames or len(frames) != n:
        return (
            "frame  geometry\n" + "\n".join(f"{i:>5}  unavailable/unmatched" for i in range(n)),
            ["Scan geometries are unavailable or cannot be aligned one-to-one with energy points; "
             "per-frame distances and connectivity changes were not inferred."],
            None,
        )
    normalized = []
    for frame in frames:
        try:
            normalized.append(None if frame is None else
                              (frame[0], np.asarray(frame[1], dtype=float)))
        except (TypeError, ValueError):
            normalized.append(None)
    frames = normalized
    for i, frame in enumerate(frames):
        if frame is not None:
            syms, pos = frame
            if pos.shape != (len(syms), 3) or not np.isfinite(pos).all():
                frames[i] = None
    valid = [(i, syms, pos) for i, frame in enumerate(frames)
             if frame is not None for syms, pos in [frame]]
    if not valid:
        return (
            "frame  geometry\n" + "\n".join(f"{i:>5}  unavailable" for i in range(n)),
            ["No aligned scan geometry is available; per-frame distances and connectivity changes "
             "were not inferred."],
            None,
        )
    sequences = Counter(tuple(syms) for _, syms, _ in valid).most_common()
    if len(sequences) > 1 and sequences[0][1] == sequences[1][1]:
        return (
            "frame  geometry\n" + "\n".join(f"{i:>5}  unavailable/unaligned" for i in range(n)),
            ["Scan frames have conflicting atom sequences with no unique most frequent sequence; "
             "distances and connectivity changes were not inferred."],
            None,
        )
    ref_syms = list(sequences[0][0])
    atom_count = len(ref_syms)
    for i, syms, pos in valid:
        if syms != ref_syms or pos.shape != (atom_count, 3):
            frames[i] = None
    valid = [(i, syms, pos) for i, frame in enumerate(frames)
             if frame is not None for syms, pos in [frame]]
    if watch_pairs:
        pairs = _select_watch_pairs(ref_syms, None, None, watch_pairs, index_base=index_base)
    elif len(valid) >= 2:
        pairs = _select_watch_pairs(ref_syms, _dist_matrix(valid[0][2]),
                                    _dist_matrix(valid[-1][2]), [])
    else:
        pairs = []
    labels = [_pair_label(ref_syms, (i, j), index_base) for i, j in pairs]
    lines = ["frame  geometry" + ("  " + "  ".join(f"{label} (A)" for label in labels) if labels else "")]
    for i, frame in enumerate(frames):
        if frame is None:
            lines.append(f"{i:>5}  unavailable/invalid")
            continue
        _, pos = frame
        distances = [float(np.linalg.norm(pos[a] - pos[b])) for a, b in pairs]
        lines.append(f"{i:>5}  observed" + "".join(f"  {d:.4f}" for d in distances))
    connectivity = default_connectivity()
    changes = []
    for i in range(1, n):
        before, after = frames[i - 1], frames[i]
        if before is None or after is None:
            changes.append(f"Frames {i - 1}->{i}: connectivity comparison unavailable (missing geometry).")
            continue
        previous = set(connectivity(before[0], before[1]))
        current = set(connectivity(after[0], after[1]))
        formed = sorted(current - previous)
        broken = sorted(previous - current)
        if formed or broken:
            changes.append(
                f"Frames {i - 1}->{i}: perceived connectivity formed "
                f"{[_pair_label(ref_syms, pair, index_base) for pair in formed]}, "
                f"broken {[_pair_label(ref_syms, pair, index_base) for pair in broken]}."
            )
    return "\n".join(lines), [
        "Per-frame distances are observed geometry values. Adjacent-frame perceived connectivity "
        "changes use the existing distance heuristic (including H); they do not prove bond "
        "formation, a product identity, or chemical success.",
        *changes,
    ], ref_syms


def _idpp_relax(images, mode: str = "standard", max_iter: int | None = None,
                lr: float = 0.02, tol: float | None = None):
    """Return coordinates and honest termination metadata, without a QM calculator.

    standard delegates the current-distance-weighted potential and NEB optimization
    to ASE. Its MDMin/fmax/step defaults are ASE idpp_interpolate defaults. Pin the
    improved tangent method explicitly so ASE version changes cannot switch it.
    light retains the original coordinate updates and stopping criterion.
    """
    import numpy as np

    if mode not in {"standard", "light"}:
        raise ValueError(f"Unknown IDPP mode: {mode}")
    images = np.asarray(images, dtype=float).copy()
    if images.ndim != 3 or images.shape[0] < 2 or images.shape[1] < 2 or images.shape[2] != 3:
        raise ValueError("IDPP requires at least two images and two atoms, shape (images, atoms, 3)")
    if not np.isfinite(images).all():
        raise ValueError("IDPP coordinates must be finite")
    steps = (4000 if mode == "light" else 100) if max_iter is None else max_iter
    threshold = (1e-7 if mode == "light" else 0.1) if tol is None else tol
    if steps < 0 or not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("IDPP requires non-negative max_iter and positive finite tol")
    report = {"method": "idpp", "idpp_mode": mode, "max_steps": steps,
              "tolerance": threshold}
    if mode == "light":
        coordinates, status = _idpp_relax_light(images, max_iter=steps, lr=lr, tol=threshold)
        report.update(optimizer="Adam", objective="fixed_target_distance^-4",
                      criterion="max_abs_gradient_component", learning_rate=lr, **status)
        return coordinates, report

    from ase import Atoms

    from cloudra.tools.core.neb_idpp import relax_standard_idpp

    atoms = [Atoms(numbers=[1] * len(frame), positions=frame) for frame in images]
    report = relax_standard_idpp(atoms, steps=steps, threshold=threshold)
    return np.asarray([image.positions for image in atoms]), report


def _idpp_relax_light(images, max_iter: int = 4000, lr: float = 0.02, tol: float = 1e-7):
    """Original fixed-target-weight Adam approximation; keep coordinate updates unchanged."""
    import numpy as np

    images = np.asarray(images, dtype=float).copy()
    n_img = len(images)
    if n_img <= 2:
        return images, {"converged": None, "termination": "not_required", "steps": 0, "residual": None}

    d_r = _dist_matrix(images[0])
    d_p = _dist_matrix(images[-1])
    n = images.shape[1]
    iu = np.triu_indices(n, k=1)

    targets = []
    weights = []
    for k in range(1, n_img - 1):
        t = k / (n_img - 1)
        d_t = (1.0 - t) * d_r + t * d_p
        targets.append(d_t[iu])
        weights.append(1.0 / np.clip(d_t[iu], 0.1, None) ** 4)

    m = np.zeros_like(images)
    v = np.zeros_like(images)
    beta1, beta2, eps = 0.9, 0.999, 1e-8

    def gradient():
        grad = np.zeros_like(images)
        for k in range(1, n_img - 1):
            pos = images[k]
            d = _dist_matrix(pos)[iu]
            diff = pos[iu[0]] - pos[iu[1]]  # (npair, 3)
            err = d - targets[k - 1]
            # dS/d(diff) = 2 w err * diff / d；先把 (npair,) 扩成 (npair,1) 再乘 (npair,3)
            scale = (2.0 * weights[k - 1] * err / np.clip(d, 1e-8, None))[:, None]
            g_pair = scale * diff
            np.add.at(grad[k], iu[0], g_pair)
            np.add.at(grad[k], iu[1], -g_pair)

        return grad

    steps = 0
    for it in range(1, max_iter + 1):
        grad = gradient()
        max_step = float(np.abs(grad[1:-1]).max()) if n_img > 2 else 0.0
        if max_step < tol:
            break
        m = beta1 * m + (1 - beta1) * grad
        v = beta2 * v + (1 - beta2) * grad ** 2
        m_hat = m / (1 - beta1 ** it)
        v_hat = v / (1 - beta2 ** it)
        step = lr * m_hat / (np.sqrt(v_hat) + eps)
        images[1:-1] -= step[1:-1]
        steps = it
    residual = float(np.abs(gradient()[1:-1]).max())
    if not np.isfinite(images).all() or not np.isfinite(residual):
        raise ValueError("light IDPP produced non-finite coordinates or gradient")
    legacy_stopping_criterion_met = residual < tol
    # Below the legacy denominator floor, the clipped gradient can vanish even
    # when the distance objective is not stationary. Preserve every old update,
    # but do not interpret that stopping test as valid convergence.
    degenerate = any(np.any(_dist_matrix(frame)[iu] < 1e-8) for frame in images[1:-1])
    converged = None if degenerate else legacy_stopping_criterion_met
    return images, {"converged": converged,
                    "termination": ("degenerate_geometry" if degenerate else
                                    "converged" if converged else "max_steps"),
                    "legacy_stopping_criterion_met": legacy_stopping_criterion_met,
                    "steps": steps, "residual": residual}


# ---------------------------------------------------------------------------
# scan_parse：能量剖面判定（纯函数，便于单测）
# ---------------------------------------------------------------------------

def analyze_scan_profile(rel_energies_kcal: Sequence[float]) -> dict:
    """对相对能量剖面（kcal/mol）做判定。返回 barrier_kcal/ts_index/verdicts。

    判定项：全程单调、相邻能量突跳（滑谷/不连续）、极值在扫描边界、多峰。
    """
    import numpy as np

    e = np.asarray(rel_energies_kcal, dtype=float)
    if e.ndim != 1 or len(e) < 2:
        raise ValueError("The energy profile needs at least 2 points")
    n = len(e)
    ts_index = int(np.argmax(e))
    barrier = float(e[ts_index] - e[0])
    verdicts: list[str] = []

    diffs = np.diff(e)
    if np.all(diffs >= 0) or np.all(diffs <= 0):
        verdicts.append("Scan energy is monotonic throughout: possibly no barrier or a wrongly chosen scan coordinate; check the reaction coordinate choice.")

    abs_diffs = np.abs(diffs)
    med = float(np.median(abs_diffs))
    jump_idx = int(np.argmax(abs_diffs))
    jump = float(abs_diffs[jump_idx])
    if jump > 3.0 * med and jump > 2.0:
        verdicts.append(
            f"Energy jump of {jump:.2f} kcal/mol between frames {jump_idx}→{jump_idx + 1} "
            f"(median {med:.2f}): possible valley sliding/discontinuity; inspect the structures near this point."
        )

    if ts_index == 0 or ts_index == n - 1:
        verdicts.append(
            f"Global energy maximum lies on the scan boundary (frame {ts_index}); internal local peaks, if present, remain unverified candidates."
        )

    peaks = [i for i in range(1, n - 1) if e[i] > e[i - 1] and e[i] > e[i + 1]]
    if len(peaks) > 1:
        verdicts.append(f"Multiple energy peaks detected (frames {', '.join(str(i) for i in peaks)}); inspect each one.")

    return {"barrier_kcal": barrier, "ts_index": ts_index, "peak_indices": peaks, "verdicts": verdicts}


# ---------------------------------------------------------------------------
# scan_parse：Gaussian / ORCA 日志解析
# ---------------------------------------------------------------------------

_SCAN_SUMMARY_RE = re.compile(r"Summary of .*Potential Surface Scan", re.IGNORECASE)
_EIGEN_LINE_RE = re.compile(r"Eigenvalues --\s+((?:-?\d+\.\d+\s*)+)")


def _parse_gaussian_scan_summary(text: str) -> list[float]:
    """解析 Gaussian 扫描日志的 "Summary of ... Potential Surface Scan" 表，返回各点能量（Eh）。"""
    m = _SCAN_SUMMARY_RE.search(text)
    if not m:
        raise ValueError("No 'Summary of ... Potential Surface Scan' table found in the log.")
    energies: list[float] = []
    for line in text[m.end():].splitlines():
        em = _EIGEN_LINE_RE.search(line)
        if em:
            energies.extend(float(v) for v in em.group(1).split())
    if not energies:
        raise ValueError("No Eigenvalues energy lines parsed from the scan summary table.")
    return energies


# 复用 orca_frames 的同一正则（容忍 "(From external program)" 后缀与 D 指数），
# 避免两处对同一日志行的解析规则漂移（GH #23）。
_ORCA_SPE_RE = orca_frames.FINAL_ENERGY_RE

# ORCA relaxed surface scan 的扫描点边界标记（每个扫描点一次）。
_SCAN_STEP_MARKER_RE = re.compile(r"RELAXED SURFACE SCAN STEP\s+\d+")


class _ScanStepsUngroupable(Exception):
    """ORCA relaxed-scan 日志文本无法按扫描步可靠分组（标记缺失/步内能量或几何
    缺位）：此时严禁按块均分等启发式把几何拼给某个能量帧（GH G1）。"""


def _parse_orca_scan(text: str) -> list[dict]:
    """按扫描步分组解析 ORCA relaxed-scan 文本回退，返回每步一帧（与扫描点一一对应）：

        [{"index": i, "energy_hartree": Eh, "geom": [(symbol, x, y, z), ...]}, ...]

    relaxed scan 的每个扫描点是一段约束优化，期间每轮优化周期都会打印一条
    'FINAL SINGLE POINT ENERGY'（实测 ORCA 6.1.1 的 10 点扫描共 55 条）——只有
    opt 块收敛后的最后一条才是该扫描点的能量。因此按 'RELAXED SURFACE SCAN
    STEP N' 标记切段，每段取最后一条能量与最后一块直角坐标（即收敛结构的
    能量与几何），而不是把每个优化周期的能量当扫描点、再按块均分猜几何。

    日志没有扫描步标记、或任一步段缺能量/几何时抛 _ScanStepsUngroupable；
    调用方走 candidate_unavailable 通道（参照 _SidecarIncomplete 语义），
    绝不按块均分等启发式发几何（GH #16/#G1）。
    """
    energies_all = [float(v.replace("D", "E").replace("d", "e")) for v in _ORCA_SPE_RE.findall(text)]
    if not energies_all:
        tail = text[-1500:]
        raise ValueError(f"Failed to parse scan energies from ORCA output ('FINAL SINGLE POINT ENERGY' not found).\nOutput tail:\n{tail}")
    markers = list(_SCAN_STEP_MARKER_RE.finditer(text))
    if not markers:
        raise _ScanStepsUngroupable(
            "the log text has no 'RELAXED SURFACE SCAN STEP' markers, so the "
            f"{len(energies_all)} 'FINAL SINGLE POINT ENERGY' lines (one per optimization "
            "cycle) cannot be mapped to scan points."
        )
    bounds = [m.start() for m in markers] + [len(text)]
    steps: list[dict] = []
    for i in range(len(markers)):
        seg = text[bounds[i]:bounds[i + 1]]
        seg_energies = [float(v.replace("D", "E").replace("d", "e")) for v in _ORCA_SPE_RE.findall(seg)]
        geoms: list[list[tuple[str, float, float, float]]] = []
        for m in re.finditer(r"CARTESIAN COORDINATES \(ANGSTROEM\)", seg):
            geom: list[tuple[str, float, float, float]] = []
            for line in seg[m.end():].splitlines()[2:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0].isalpha():
                    try:
                        geom.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
                        continue
                    except ValueError:
                        pass
                break
            if geom:
                geoms.append(geom)
        if not seg_energies or not geoms:
            raise _ScanStepsUngroupable(
                f"scan step {i + 1} contains no FINAL SINGLE POINT ENERGY or no Cartesian "
                "geometry block; the per-step energies and geometries cannot be aligned."
            )
        steps.append({"index": i, "energy_hartree": seg_energies[-1], "geom": geoms[-1]})
    return steps


_ORCA_NAME_RE = re.compile(r"^\s*NAME\s*=\s*(?P<path>\S+)\s*$", re.M)


class _SidecarIncomplete(Exception):
    """relaxscanact.dat 存在但逐帧几何缺失/不匹配：峰值帧严禁用末帧替代。"""

    def __init__(self, message: str, energies: Optional[list] = None, frames: Optional[list] = None):
        super().__init__(message)
        self.energies = energies
        self.frames = frames


def _find_orca_sidecar_dat(log_path: str, workdir: str) -> Optional[str]:
    """stem 不匹配时定位 relaxscanact.dat，找不到或无法唯一确定返回 None。

    优先从日志的输入回显（``NAME = <作业>.inp``）推导真实作业名——harness 的
    日志名（如 .cloudra/calc-28.out.log）与 ORCA 作业名无关；其次在日志目录
    与其父目录（计算工作目录）找唯一的 sidecar，多于一个时拒绝猜测（GH #23）。
    """
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            head = f.read(200_000)  # NAME 在日志开头的输入回显段
    except OSError:
        head = ""
    m = _ORCA_NAME_RE.search(head)
    if m:
        candidate = os.path.splitext(m.group("path"))[0] + ".relaxscanact.dat"
        if os.path.isfile(candidate):
            return candidate
    import glob

    found = set(glob.glob(os.path.join(workdir, "*.relaxscanact.dat")))
    found.update(glob.glob(os.path.join(os.path.dirname(workdir), "*.relaxscanact.dat")))
    if len(found) == 1:
        return found.pop()
    return None


def _gaussian_scan_is_grid(text: str, data=None) -> bool:
    parameters = getattr(data, 'scanparm', None) if data is not None else None
    if parameters is not None and len(parameters) > 1:
        return True
    coordinates = set()
    for line in text.splitlines():
        tokens = line.upper().split()
        count = {'B': 2, 'A': 3, 'D': 4}.get(tokens[0]) if tokens else None
        if count and len(tokens) > count + 1 and tokens[count + 1] == 'S':
            atoms = tuple(tokens[1:count + 1])
            if all(atom.isdigit() for atom in atoms):
                coordinates.add((tokens[0], min(atoms, tuple(reversed(atoms)))))
    return len(coordinates) > 1


def _orca_scan_controls(log_path: str, text: str = "") -> list[str]:
    """Read native scan controls so independent grids keep their topology."""
    from pathlib import Path

    from cloudra.tools.core.calculation_intent import orca_directives
    for directory, stem in orca_frames._orca_sidecar_roots(log_path, text):
        path = Path(directory) / (stem + '.inp')
        if path.is_file():
            return orca_directives(path.read_text())[1].get('geom', [])
    echoed = []
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) > 2 and tokens[0] == '|' and tokens[1].endswith('>'):
            line = ' '.join(tokens[2:])
        echoed.append(line)
    return orca_directives('\n'.join(echoed))[1].get('geom', [])


def _orca_scan_is_grid(log_path: str, text: str = "") -> bool:
    controls = _orca_scan_controls(log_path, text)
    simultaneous = any(token == 'simul_scan' and controls[i + 1:i + 2] == ['true']
                       for i, token in enumerate(controls))
    scanning = False
    coordinates = 0
    for token in controls:
        if token == 'scan':
            scanning = True
        elif token == 'end':
            scanning = False
        elif scanning and token in {'b', 'a', 'd'}:
            coordinates += 1
    return coordinates > 1 and not simultaneous


def _parse_orca_relaxed_scan_sidecar(log_path: str) -> Optional[dict]:
    """解析 ORCA relaxed scan 的 sidecar 产物（优先于 .out 文本）。

    ORCA 沿作业名写 ``<job>.relaxscanact.dat``（每帧一行：扫描坐标值 + 总能量 Eh）
    与逐帧几何 ``<job>.NNN.xyz``（NNN=帧号，1-based，与 dat 行号一一对应）。
    返回 {"energies": [...], "frames": [(symbols, positions), ...]}，帧数必须与
    dat 行数一致；缺帧/错位抛 _SidecarIncomplete，保留可对齐帧供诊断，
    但不回退到 .out 文本猜测候选几何。

    能量最高帧（TS 候选）通常不是末帧；sidecar 让 scan_parse 能按能量最高帧
    而不是 ``rfind`` 出来的末帧取几何。

    sidecar 定位：先按日志名 stem 在日志同目录找；不匹配时经
    ``_find_orca_sidecar_dat`` 从日志 NAME 记录/唯一 glob 推导（GH #23）。
    """
    import glob
    from pathlib import Path

    import numpy as np

    stem = os.path.splitext(os.path.basename(log_path))[0]
    workdir = os.path.dirname(os.path.abspath(log_path))
    dat_path = os.path.join(workdir, f"{stem}.relaxscanact.dat")
    if not os.path.isfile(dat_path):
        dat_path = _find_orca_sidecar_dat(log_path, workdir)
        if dat_path is None:
            return None
        workdir = os.path.dirname(dat_path)
        stem = os.path.basename(dat_path)[: -len(".relaxscanact.dat")]
    log_text = Path(log_path).read_text(errors='replace') if Path(log_path).is_file() else ''
    controls = _orca_scan_controls(log_path, log_text)
    simultaneous = any(token == 'simul_scan' and controls[i + 1:i + 2] == ['true']
                       for i, token in enumerate(controls))
    if _orca_scan_is_grid(log_path, log_text):
        raise _SidecarIncomplete('Independent multidimensional scan grid is not a one-dimensional path; no candidate was derived.')
    try:
        with open(dat_path, encoding="utf-8", errors="replace") as f:
            energies = []
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    values = [float(value) for value in parts]
                except ValueError:
                    continue
                if len(values) > 2 and (len(values) != 3 or not simultaneous):
                    raise _SidecarIncomplete('Multidimensional scan grid or unproven simultaneous path; no candidate was derived.')
                energies.append(values[-1])
    except OSError as exc:
        raise _SidecarIncomplete(f"{dat_path} exists but cannot be read: {exc}") from exc
    if not energies:
        raise _SidecarIncomplete(f"{dat_path} contains no parseable energy rows.")

    frame_paths = sorted(
        glob.glob(os.path.join(workdir, f"{stem}.[0-9][0-9][0-9].xyz")),
    )
    import ase.io

    frames = [None] * len(energies)
    unreadable = []
    for p in frame_paths:
        number = os.path.splitext(os.path.basename(p))[0].rsplit(".", 1)[-1]
        index = int(number) - 1
        if not 0 <= index < len(energies):
            raise _SidecarIncomplete(
                f"frame numbering next to {dat_path} is outside 1..{len(energies)} "
                f"(offending file: {os.path.basename(p)}).", energies=energies, frames=frames,
            )
        try:
            atoms = ase.io.read(p, format="xyz")
            frames[index] = (atoms.get_chemical_symbols(), np.asarray(atoms.get_positions(), dtype=float))
        except Exception as exc:
            unreadable.append(f"{os.path.basename(p)}: {exc}")
    if any(frame is None for frame in frames):
        raise _SidecarIncomplete(
            f"{dat_path} lists {len(energies)} scan points but only "
            f"{sum(frame is not None for frame in frames)} readable, aligned "
            f"{stem}.NNN.xyz frame files exist next to it. "
            + (f"Unreadable: {'; '.join(unreadable)}." if unreadable else ""),
            energies=energies, frames=frames,
        )
    return {"energies": energies, "frames": frames, "frame_paths": frame_paths}


# ---------------------------------------------------------------------------
# verify：频率解析（cclib 优先，正则回退）+ IRC 端点
#
# Gaussian 频率/位移块正则与 Standard orientation 解析归位共享层
# cloudra.tools.core.gaussian_frames（FREQ_LINE_RE / vibdisps_from_text /
# std_orientation_frames），本模块不再保留重复实现。
# ---------------------------------------------------------------------------


def _assess_imag_mode_alignment(
    vibfreqs: Sequence[float],
    vibdisps,
    watch_pairs: Sequence[Sequence[int]],
    symbols: Optional[Sequence[str]] = None,
    positions=None,
    charge: int = 0,
    index_base: int = 1,
    **_kwargs,
) -> dict[str, Any]:
    """检查最低虚频模式是否主要落在 watch_pairs 反应中心上。

    对每个原子对取 |d_i - d_j|；要求 watch_pairs 中至少一对达到全局最大相对位移的
    `_IMAG_MODE_WATCH_RATIO` 倍。缺位移数据时 status=missing。

    扭转/角主导的 TS（阻转、环翻转、锥形反转）：全局最大相对位移对**两端不成键**
    （用 TS 几何的 perceive_bonds 键图判）时，键对距离本就几乎不动，pair-distance
    对齐材料不足以判方向——status=undecidable。主导对是键对、或 TS 几何缺失
    无法判成键性时，维持原规则。该启发式仅作诊断，不决定 strict 验收。
    """
    import numpy as np

    if vibdisps is None:
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }
    imag_idxs = [i for i, f in enumerate(vibfreqs) if f < 0]
    if not imag_idxs:
        return {
            "status": "missing",
            "aligned": None,
            "message": "No imaginary frequency; skipping the imaginary-mode alignment check.",
            "details": [],
        }
    mode_idx = min(imag_idxs, key=lambda i: vibfreqs[i])
    try:
        disps = np.asarray(vibdisps[mode_idx], dtype=float)
    except (IndexError, TypeError, ValueError):
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }
    if disps.ndim != 2 or disps.shape[1] != 3 or disps.shape[0] < 2:
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }

    n = disps.shape[0]
    pair_mags: list[tuple[tuple[int, int], float]] = []
    max_rel = 0.0
    max_pair = (0, 1)
    for i in range(n):
        for j in range(i + 1, n):
            rel = float(np.linalg.norm(disps[i] - disps[j]))
            pair_mags.append(((i, j), rel))
            if rel > max_rel:
                max_rel = rel
                max_pair = (i, j)

    if max_rel <= 0.0:
        return {
            "status": "missing",
            "aligned": None,
            "message": "All imaginary-mode displacements are zero; cannot check direction.",
            "details": [],
        }

    if not watch_pairs:
        return {
            "status": "skipped",
            "aligned": None,
            "message": "No watch_pairs provided; skipping the imaginary-mode vs reaction-coordinate alignment check.",
            "details": [f"Global max relative-displacement pair=({max_pair[0] + index_base},{max_pair[1] + index_base})"],
        }

    threshold = _IMAG_MODE_WATCH_RATIO * max_rel
    watch_set: set[frozenset[int]] = set()
    watch_details: list[str] = []
    best_watch = 0.0
    for raw in watch_pairs:
        if len(raw) != 2:
            continue
        i, j = int(raw[0]) - index_base, int(raw[1]) - index_base
        if not (0 <= i < n and 0 <= j < n) or i == j:
            watch_details.append(f"watch_pairs atom indices invalid: {raw}")
            continue
        lo, hi = (i, j) if i < j else (j, i)
        watch_set.add(frozenset((lo, hi)))
        rel = float(np.linalg.norm(disps[lo] - disps[hi]))
        best_watch = max(best_watch, rel)
        watch_details.append(
            f"Atom pair ({lo + index_base},{hi + index_base}) relative displacement={rel:.3f}"
            f" (threshold {_IMAG_MODE_WATCH_RATIO:.2f}×{max_rel:.3f}={threshold:.3f})"
        )

    max_fs = frozenset(max_pair)
    # 最大相对位移对本身在 watch_pairs 中 → 对齐；否则须严格超过比例阈值，
    # 避免「两端反向伸缩、监视原子静止」时 |d_i-d_j| 恰好 = 0.5×max 的假阳性。
    if max_fs in watch_set:
        aligned = best_watch >= threshold
    else:
        aligned = best_watch > threshold
    if aligned:
        message = (
            f"Imaginary mode is consistent with the declared reaction coordinate: watch_pairs max relative displacement {best_watch:.3f} "
            f"≥ {_IMAG_MODE_WATCH_RATIO:.2f}×global max {max_rel:.3f} "
            f"(max pair=({max_pair[0] + index_base},{max_pair[1] + index_base}))."
        )
        status = "aligned"
    else:
        # 扭转/角主导模式：全局最大相对位移对两端不成键时，键对距离几乎不动是
        # 这类模式的固有性质，pair-distance 对齐无法判方向——undecidable。
        dominant_bonded: Optional[bool] = None
        if symbols is not None and positions is not None and len(symbols) == n:
            bond_graph, _src = _perceive_bonds(list(symbols), positions, charge)
            dominant_bonded = (min(max_pair), max(max_pair)) in bond_graph
        if dominant_bonded is False:
            return {
                "status": "undecidable",
                "aligned": None,
                "message": (
                    f"The imaginary mode's dominant motion is on the NON-BONDED atom pair "
                    f"({max_pair[0] + index_base},{max_pair[1] + index_base}): a torsion/angle-dominated mode "
                    "(hindered rotation, ring flip, pyramidal inversion) barely moves bonded-pair "
                    "distances, so pair-distance alignment against watch_pairs cannot judge its "
                    "direction. The material is insufficient for a pass/fail verdict."
                ),
                "details": watch_details,
            }
        message = (
            f"Imaginary mode is inconsistent with the declared reaction coordinate: watch_pairs max relative displacement {best_watch:.3f} "
            f"< {_IMAG_MODE_WATCH_RATIO:.2f}×global max {max_rel:.3f} "
            f"(dominant motion on atom pair ({max_pair[0] + index_base},{max_pair[1] + index_base}))."
        )
        status = "misaligned"
    return {
        "status": status,
        "aligned": aligned,
        "message": message,
        "details": watch_details,
    }


def _parse_freq_log(log_path: str, engine: str) -> dict:
    """Read separate native termination, optimization and frequency facts."""
    from cloudra.tools.core.qm_log_facts import read_qm_log

    facts = read_qm_log(log_path)
    if facts.engine != engine:
        raise ValueError(f"Expected {engine} frequency output, detected {facts.engine}: {log_path}")
    text = facts.text
    vibfreqs = facts.frequencies_cm
    vibdisps = None
    if vibfreqs is None:
        raise ValueError(f"Failed to parse vibrational frequencies from the frequency log: {log_path}")
    # Keep vectors paired with the frequencies and geometry from the same log.
    data = facts.parser_data
    if data is not None:
        vd = getattr(data, 'vibdisps', None)
        vf = getattr(data, 'vibfreqs', None)
        if vd is not None and vf is not None and len(vd) == len(vibfreqs) and len(vf) == len(vibfreqs):
            import numpy as np

            if np.array_equal(np.asarray(vf, dtype=float), np.asarray(vibfreqs, dtype=float)):
                vibdisps = np.asarray(vd, dtype=float)
    if vibdisps is None and engine == "gaussian":
        vibdisps = gaussian_frames.vibdisps_from_text(text, len(vibfreqs))
    elif vibdisps is None and engine == "orca":
        # cclib 也可能只解析出裁掉零频的频率。原生位移按完整 3N 轴编号，
        # 必须连同原生频率一起取，不能拿裁剪后的轴推算原子数或匹配位移。
        native_freqs = orca_frames.vibfreqs_from_text(text)
        n_atoms = len(native_freqs) // 3 if native_freqs and len(native_freqs) % 3 == 0 else 0
        if n_atoms > 0:
            native_disps = orca_frames.vibdisps_from_text(text, len(native_freqs), n_atoms)
            if native_disps is not None:
                vibfreqs, vibdisps = native_freqs, native_disps
    symbols, positions = (None, None)
    if facts.geometry is not None:
        import numpy as np

        symbols = list(facts.geometry[0])
        positions = np.asarray(facts.geometry[1], dtype=float)
    return {
        "vibfreqs": vibfreqs,
        "vibdisps": vibdisps,
        "normal_termination": facts.normal_termination,
        "opt_converged": facts.opt_converged,
        "symbols": symbols,
        "positions": positions,
    }


# ---------------------------------------------------------------------------
# Tool 主类
# ---------------------------------------------------------------------------

class TsGuess(Tool):
    tool_id: str = 't-45'
    tool_name: str = 'ts_guess'
    tool_description: str = description
    input_schema: Any = TsGuess_input_schema
    output_schema: Any = TsGuess_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: TsGuess_input_schema, session: Session) -> TsGuess_output_schema:
        if user_input.run_id is not None:
            try:
                return await self._run_guess(user_input, session)
            except (ValueError, OSError) as exc:
                return TsGuess_output_schema(is_success=False, message=f'ts_guess: {exc}')
        # 路径语义收口：所有文件路径字段的相对路径统一解析到 agent 工作
        # 目录（沙箱）；绝对路径保持既有权限语义。
        user_input = user_input.model_copy(
            update={
                **{
                    field: resolve_tool_path(self, value)
                    for field, value in {
                        "reactant_path": user_input.reactant_path,
                        "product_path": user_input.product_path,
                        "input_path": user_input.input_path,
                        "output_path": user_input.output_path,
                        "log_path": user_input.log_path,
                        "ts_candidate_path": user_input.ts_candidate_path,
                        "freq_log": user_input.freq_log,
                        "irc_log": user_input.irc_log,
                        "output_dir": user_input.output_dir,
                    }.items()
                    if value
                },
                **{field: [resolve_tool_path(self, path) for path in getattr(user_input, field)]
                   for field in ("reactant_logs", "product_logs")},
            }
        )
        mode = user_input.mode
        if mode == "scan":
            mode = "scan_parse" if user_input.log_path else "scan_prepare"

        handlers = {
            "xtb_path": self._xtb_path,
            "interpolate": self._interpolate,
            "scan_prepare": self._scan_prepare,
            "scan_parse": self._scan_parse,
            "verify": self._verify,
        }
        if mode not in handlers:
            import difflib
            matches = difflib.get_close_matches(mode, list(handlers.keys()), n=1, cutoff=0.35)
            suggestion = f" Did you mean {matches[0]!r}?" if matches else ""
            return TsGuess_output_schema(
                is_success=False,
                message=f"Unknown mode {mode!r}.{suggestion} Allowed modes: {sorted(handlers.keys())}",
            )
        try:
            # handler 是同步重活（xtb_path 会 proc.communicate 等 xTB 子进程、
            # scan_parse 逐帧啃大日志）：卸载出事件循环，避免冻结整个 API。
            return await asyncio.to_thread(handlers[mode], user_input)
        except _UnconfirmedEndpointMapping as exc:
            return TsGuess_output_schema(is_success=False, message=str(exc), mapping_candidates=exc.candidates)
        except Exception as e:
            return TsGuess_output_schema(is_success=False, message=f"{user_input.mode} failed: {e}")

    async def _run_guess(self, user_input, session):
        from cloudra.runtime_v2.invocation_context import current_invocation_scope
        from cloudra.services.ts_pipeline_context import pipeline_database
        from cloudra.services.ts_pipeline_store import get_revision_receipt
        from cloudra.tools.Chemtool.ts_search_process import (
            _read_resume_record,
            _request_key,
            _resolve_workspace,
            revise_run,
        )
        from cloudra.tools.core.permission_model import Permission

        if not self.subagent or not self.subagent.permission_all() & Permission.WRITE:
            raise ValueError('TS mutation requires producer write permission')
        record = await asyncio.to_thread(_read_resume_record, pipeline_database(),
            _resolve_workspace(self), user_input.run_id, self.subagent.conversation_id)
        # Replays assemble the identical intent from the declaration that the
        # original call read, rather than copying its already accepted result.
        inputs, structures = record.input, record.structures
        scope = current_invocation_scope()
        if scope is not None and scope.tool_name == self.tool_name:
            accepted = await asyncio.to_thread(get_revision_receipt, pipeline_database(),
                process_id=record.pipeline_id, request_key=_request_key(self.tool_name))
            if accepted:
                previous = next((attempt for attempt in record.attempt_history
                    if attempt.declaration_revision == accepted.previous_input_revision), None)
                if previous is None or previous.input is None or previous.structures is None:
                    raise ValueError('Accepted TS guess has no original declaration and structure snapshot')
                inputs, structures = previous.input, previous.structures
        interpolation_result = None
        current = inputs.guess
        supplied = user_input.model_fields_set
        mode = user_input.mode
        if mode == 'xtb_path':
            guess = current.model_dump(mode='json') if current and current.kind == 'xtb_path' else {'kind': 'xtb_path'}
            for field in ('method', 'refinement_runs', 'solvation'):
                if field in supplied:
                    value = getattr(user_input, field)
                    guess[field] = value.model_dump(mode='json') if hasattr(value, 'model_dump') else value
            if not guess.get('method'):
                raise ValueError('xtb_path requires an explicit method or an existing xtb_path method in this run')
        elif mode in {'scan', 'scan_prepare'}:
            guess = {'kind': 'scan'}
            for field in ('scans', 'freeze', 'force_constant', 'solvation'):
                if field in supplied:
                    value = getattr(user_input, field)
                    guess[field] = ([item.model_dump(mode='json') for item in value] if isinstance(value, list)
                                    else value.model_dump(mode='json') if hasattr(value, 'model_dump') else value)
            if 'scan_mode' in supplied:
                guess['mode'] = user_input.scan_mode
            fields = supplied & set(QmCalculation.model_fields)
            if fields or not current or current.kind != 'scan':
                from cloudra.tools.core.ts_inputs import resolve_calculation
                calculation = (resolve_calculation(current.calculation, inputs.calculations).model_dump(mode='json')
                    if current and current.kind == 'scan' else {})
                calculation.update({field: getattr(user_input, field) for field in fields})
                complete = QmCalculation.model_validate(calculation)
                guess['calculation'] = {'replace': complete.model_dump(mode='json')}
            if 'scans' not in guess and (not current or current.kind != 'scan'):
                raise ValueError('scan requires explicit scanned coordinates or an existing scan intent in this run')
        elif mode == 'provided':
            guess = current.model_dump(mode='json') if current and current.kind == 'provided' else {'kind': 'provided'}
            if 'ts_candidate_path' in supplied:
                guess['xyz_path'] = resolve_tool_path(self, user_input.ts_candidate_path)
            if 'evidence_refs' in supplied:
                guess['evidence_refs'] = [resolve_tool_path(self, value) for value in user_input.evidence_refs]
            if not guess.get('xyz_path') or not guess.get('evidence_refs'):
                raise ValueError('provided requires ts_candidate_path and source evidence_refs')
        else:
            import hashlib
            from pathlib import Path

            from cloudra.tools.core.reaction_state import export_structure, path_endpoints
            reactant, product = path_endpoints(structures)
            identity = hashlib.sha256(_request_key(self.tool_name).encode()).hexdigest()[:20]
            request = user_input.model_copy(update={
                'output_dir': str(Path(record.run_dir) / 'interpolation' / identity),
            })
            result = await asyncio.to_thread(self._interpolate_molecules, request, reactant, product)
            interpolation_result = result
            references = [result.ts_candidate_path, str(Path(result.images_dir) / 'interpolation.json')]
            source_record = record.model_copy(update={'structures': structures})
            for role in ('reactant', 'product'):
                paths = await asyncio.to_thread(export_structure, source_record, role)
                references.extend(paths)
            guess = dict(kind='provided', xyz_path=result.ts_candidate_path, evidence_refs=references)
        output = await revise_run(self, user_input.run_id, {'guess': guess},
            f'Use the explicitly requested {mode} TS guess', session, expected_revision=record.revision)
        return TsGuess_output_schema(is_success=output.is_success, message=output.message,
                                     process=output.model_dump(mode='json'),
                                     interpolation=interpolation_result.interpolation if interpolation_result else None)

    # ---------- mode=interpolate ----------

    def _interpolate(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        reactant, product = _independent_path_endpoints(user_input)
        return self._interpolate_molecules(user_input, reactant, product)

    def _interpolate_molecules(self, user_input, reactant, product):
        import numpy as np

        if user_input.n_images < 2:
            raise ValueError("n_images must be ≥ 2")

        r_syms = [atom.GetSymbol() for atom in reactant.GetAtoms()]
        r_pos = np.asarray(reactant.GetConformer().GetPositions(), dtype=float)
        p_pos = np.asarray(product.GetConformer().GetPositions(), dtype=float)
        n = len(r_syms)

        # Kabsch 对齐（各自去质心后旋转产物到反应物取向）
        r_centered = r_pos - r_pos.mean(axis=0)
        p_centered = p_pos - p_pos.mean(axis=0)
        p_aligned = _kabsch_rotate(p_centered, r_centered)

        # 生成 N 帧线性插值
        n_img = user_input.n_images
        images = np.zeros((n_img, n, 3))
        for k in range(n_img):
            t = k / (n_img - 1)
            images[k] = (1.0 - t) * r_centered + t * p_aligned

        interpolation = {"method": "linear", "idpp_mode": None, "converged": None,
                         "termination": "not_required", "steps": 0, "residual": None}
        if user_input.interp_method == "idpp":
            images, interpolation = _idpp_relax(images, mode=user_input.idpp_mode)

        # 落盘
        out_dir = user_input.output_dir or resolve_tool_path(self, "./ts_interp")
        os.makedirs(out_dir, exist_ok=True)
        atomic_write_text(os.path.join(out_dir, "interpolation.json"),
                          json.dumps(interpolation, indent=2, allow_nan=False) + "\n")
        for k in range(n_img):
            atomic_write_text(
                os.path.join(out_dir, f"img_{k:02d}.xyz"),
                to_xyz(with_positions(reactant, images[k]), comment=f"ts_guess {user_input.interp_method} image {k}; idpp_mode={interpolation['idpp_mode']}; termination={interpolation['termination']}"),
            )

        # 监测原子对
        d_r = _dist_matrix(images[0])
        d_p = _dist_matrix(images[-1])
        pairs = _select_watch_pairs(r_syms, d_r, d_p, user_input.watch_pairs, index_base=atom_index_base(user_input.engine))

        # 距离表
        header = f"{'frame':>4}" + "".join(f"  {_pair_label(r_syms, pr, atom_index_base(user_input.engine)):>12}" for pr in pairs)
        lines = [header]
        for k in range(n_img):
            d_k = _dist_matrix(images[k])
            row = f"{k:>4}" + "".join(f"  {d_k[i, j]:>12.4f}" for i, j in pairs)
            lines.append(row)
        distance_table = "\n".join(lines)

        # TS 候选帧：变化最大原子对的距离跨过两端中点的帧
        deltas = {pr: abs(d_p[pr] - d_r[pr]) for pr in pairs}
        key_pair = max(deltas, key=deltas.get)
        mid = 0.5 * (d_r[key_pair] + d_p[key_pair])
        ts_index = 0
        for k in range(n_img):
            d_k = _dist_matrix(images[k])[key_pair]
            if (d_k - mid) * (d_r[key_pair] - mid) <= 0:
                ts_index = k
                break
        else:
            ts_index = int(np.argmin([abs(_dist_matrix(images[k])[key_pair] - mid) for k in range(n_img)]))
        ts_path = os.path.join(out_dir, f"img_{ts_index:02d}.xyz")

        return TsGuess_output_schema(
            is_success=True,
            images_dir=out_dir,
            interpolation=interpolation,
            distance_table=distance_table,
            ts_candidate_index=ts_index,
            ts_candidate_path=ts_path,
            message=(
                f"Generated {n_img} images ({user_input.interp_method}, idpp_mode={interpolation['idpp_mode']}) in {out_dir}. "
                f"Numerical termination: {interpolation['termination']}; convergence={interpolation['converged']}. "
                "Generation success is not convergence or TS verification. "
                f"TS candidate frame: img_{ts_index:02d}.xyz (watched pair {_pair_label(r_syms, key_pair, atom_index_base(user_input.engine))} crosses the endpoint midpoint). "
                "These images can serve directly as a NEB initial path, or be optimized frame by frame with constraints to find a TS guess; "
                "you can also use scan_prepare to generate a constrained-scan input to further locate the barrier top."
            ),
        )

    # ---------- mode=xtb_path ----------

    def _xtb_path(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        """xTB 元动力学路径搜索出 TS 初猜（SOP `guess` 阶段的便宜端）。

        **这个模式返回的是路径与初猜，不是鞍点**：``xtbpath_ts.xyz`` 是 MTD 采到的最高点附近
        结构，验证仍归 ``verify``（频率 + IRC）。两条纪律：

        - xTB **不存在**时退回 IDPP 插值，并把 ``path_kind`` 标成 ``idpp_fallback``、
          在 message 里写明走了降级路线——绝不静默降级。
        - xTB **存在但跑失败**时**不**换兜底充数：报出分层分类与持久运行目录，让调用方决定。
        """
        import numpy as np

        from cloudra.tools.core.xtb_path_runner import XtbPathRequest, run_xtb_path

        reactant, product = _independent_path_endpoints(user_input)
        r_syms = [atom.GetSymbol() for atom in reactant.GetAtoms()]

        out_dir = user_input.output_dir or resolve_tool_path(self, "./ts_path")

        run = run_xtb_path(XtbPathRequest(
            reactant_xyz=to_xyz(reactant, "ts_guess reactant"),
            product_xyz=to_xyz(product, "ts_guess product"),
            output_dir=out_dir,
            charge=total_charge(reactant),
            multiplicity=user_input.multiplicity,
            electronic_character=user_input.electronic_character,
            timeout=user_input.timeout,
            refinement_runs=user_input.refinement_runs,
            run_label="guess",
        ))

        if run.termination_reason == "executable_missing":
            fallback = self._interpolate_molecules(user_input, reactant, product)
            fallback.path_kind = "idpp_fallback"
            fallback.path_termination_reason = run.termination_reason
            fallback.diagnostics = list(run.diagnostics)
            fallback.message += (
                "\nNOTE: the `xtb` executable was not found on PATH, so this path guess fell back "
                f"to {user_input.interp_method.upper()} interpolation (path_kind='idpp_fallback'). {run.message} "
                "That is a degraded route: an interpolation between the two endpoints, NOT a "
                "metadynamics path search. Install xtb to get path_kind='xtb_path'."
            )
            return fallback

        if not run.usable_as_guess:
            if run.termination_reason == "path_not_converged":
                return TsGuess_output_schema(
                    is_success=False,
                    path_kind="",
                    refinement_termination=run.refinement_termination,
                    path_termination_reason=run.termination_reason,
                    images_dir=run.run_dir,
                    diagnostics=list(run.diagnostics),
                    message=(
                        f"the xTB path refinement hit its {run.refinement_runs}-cycle ceiling "
                        "before the engine declared convergence, so no usable TS guess was "
                        "produced. A truncated path's highest frame is not a transition-state "
                        "guess (measured: it sits in the reactant's own basin and an OptTS started "
                        "from it never converges). Call again with a larger `refinement_runs` and "
                        f"rerun. {run.message} Persistent run directory (truncated path kept): {run.run_dir}"
                    ),
                )
            return TsGuess_output_schema(
                is_success=False,
                path_kind="",
                refinement_termination=run.refinement_termination,
                path_termination_reason=run.termination_reason,
                images_dir=run.run_dir,
                diagnostics=list(run.diagnostics),
                message=(
                    f"the xTB path search did not produce a usable guess (termination="
                    f"{run.termination_reason}, returncode={run.returncode}). No fallback was "
                    "substituted: a failed xTB run is reported, not silently replaced by an "
                    f"interpolation. {run.message} Persistent run directory: {run.run_dir}"
                ),
            )

        # 帧与 interpolate 同名，下游不必区分来源；能量标注单位（相对 kcal/mol）
        for frame in run.frames:
            comment = f"ts_guess xtb_path frame {frame.frame_index}"
            if frame.rel_energy_kcal is not None:
                comment += f" rel_energy_kcal={frame.rel_energy_kcal:.3f}"
            atomic_write_text(
                os.path.join(out_dir, f"img_{frame.frame_index:02d}.xyz"),
                _atoms_to_xyz_block(run.symbols, np.asarray(frame.positions, dtype=float), comment),
            )

        ts_path = os.path.join(out_dir, "ts_candidate_xtbpath.xyz")
        atomic_write_text(
            ts_path,
            _atoms_to_xyz_block(
                run.symbols, np.asarray(run.ts_candidate_positions, dtype=float),
                f"ts_guess xtb_path MTD TS candidate energy_eh={run.ts_candidate_energy_eh:.8f}",
            ),
        )

        # 距离表：与 interpolate 同一套监测对选择
        d_r = _dist_matrix(reactant.GetConformer().GetPositions())
        d_p = _dist_matrix(product.GetConformer().GetPositions())
        pairs = _select_watch_pairs(r_syms, d_r, d_p, user_input.watch_pairs, index_base=atom_index_base(user_input.engine))
        lines = [f"{'frame':>4}" + "".join(f"  {_pair_label(r_syms, pr, atom_index_base(user_input.engine)):>12}" for pr in pairs)]
        for frame in run.frames:
            d_k = _dist_matrix(np.asarray(frame.positions, dtype=float))
            lines.append(
                f"{frame.frame_index:>4}" + "".join(f"  {d_k[i, j]:>12.4f}" for i, j in pairs)
            )
        distance_table = "\n".join(lines)

        return TsGuess_output_schema(
            is_success=True,
            path_kind="xtb_path",
            refinement_termination=run.refinement_termination,
            path_termination_reason=run.termination_reason,
            diagnostics=list(run.diagnostics),
            images_dir=out_dir,
            distance_table=distance_table,
            ts_candidate_index=None,
            ts_candidate_path=ts_path,
            message=(
                f"xTB metadynamics path search finished: {len(run.frames)} path frames "
                f"(img_00..img_{len(run.frames) - 1:02d}.xyz) plus a TS CANDIDATE. "
                "The candidate is the highest point sampled along the MTD path — it is a GUESS, "
                "not a saddle point and NOT verified; run mode='verify' with a frequency job to "
                "judge it. Metadynamics is stochastic: a rerun gives a different path, so the "
                f"whole run is kept for inspection at {run.run_dir}. {run.message}"
            ),
        )

    # ---------- mode=scan_prepare ----------

    def _scan_prepare(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        """Build scan coordinates; the shared writer owns the complete native input."""
        if user_input.engine == 'xtb':
            return self._xtb_scan_prepare(user_input)
        if not user_input.method or not user_input.method.strip():
            raise ValueError(
                "scan_prepare requires an explicit method consistent with the current task's "
                "requirements, budget and available software. MethodPolicy applies only to a "
                "current Benchmark task; ordinary projects have no method/basis whitelist."
            )
        calculation = QmCalculation.model_validate({field: getattr(user_input, field) for field in QmCalculation.model_fields})
        from cloudra.tools.core.ts_inputs import ScanGuess
        ScanGuess(kind='scan', calculation=calculation, scans=user_input.scans or [],
                  freeze=user_input.freeze, mode=user_input.scan_mode,
                  force_constant=user_input.force_constant, solvation=user_input.solvation)
        if not user_input.scans:
            raise ValueError("scan_prepare requires scans: at least one scanned coordinate")
        if not user_input.output_path:
            raise ValueError("scan_prepare requires output_path (the path to write the input file)")
        mol = _source_molecule(user_input, "input")
        coordinates = native_coordinate_settings(
            mol, engine=user_input.engine, scans=user_input.scans, freeze=user_input.freeze,
            scan_mode=user_input.scan_mode, end_setting=user_input.end_setting, orca_blocks=user_input.orca_blocks,
        )
        specs = coordinates['specs']
        frozen = coordinates['frozen']
        if coordinates['start_mismatches'] and user_input.engine == 'gaussian':
            return TsGuess_output_schema(is_success=False, message=(
                'start_geometry_mismatch: ' + '; '.join(coordinates['start_mismatches'])
                + '. A Gaussian modredundant scan starts from the CURRENT geometry value and only applies '
                'the increment — generate the target start geometry first (e.g. a constrained optimization '
                'to the requested start value) instead of merely adjusting scan_start.'
            ))
        from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

        scan_labels = coordinates['scan_labels']
        native_settings = calculation.model_dump(mode='json')
        native_settings.update({field: coordinates[field] for field in ('end_setting', 'orca_blocks')})
        task_type = coordinates['task_type']
        grid = len(specs) > 1 and (user_input.engine == 'gaussian' or user_input.scan_mode == 'grid')
        run_hint = (
            f"Submit {user_input.output_path} with submit_compute_job (job_type='{user_input.engine}'); "
            + ("this is a 2D independent potential-energy grid; scan_parse does not derive a TS candidate. "
               "Inspect its native points and use a selected XYZ with guess.kind='provided' for formal refinement."
               if grid else "afterwards parse the log with ts_guess mode='scan_parse' "
               + ("engine='orca' " if user_input.engine == 'orca' else '') + "for internal-peak candidates.")
        )

        from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
        from cloudra.tools.core.calculation_intent import (
            inspect_input,
            validate_writer_request,
        )
        from cloudra.tools.core.ts_process import _stage_writer_tasks

        calculation, task_type = _stage_writer_tasks(calculation, task_type)
        # 科学状态和资源只使用共同字段，扫描不再另写电子态、资源、坐标或检查点。
        request = QmInputWriter_input_schema(
            **native_settings, **user_input.model_dump(include=set(QmInputSettings.model_fields), exclude_unset=True),
            source_type='xyz_file' if mol.HasProp('cloudra_graph_status') else 'mol_file',
            source_value=user_input.input_path or '<inline>', task_type=task_type,
            output_path=user_input.output_path,
        )
        issues = validate_writer_request(request.model_dump())
        errors = [item for item in issues if item['severity'] == 'error']
        if errors:
            return TsGuess_output_schema(is_success=False, message=str(errors))
        advice = [item for item in issues if item['severity'] == 'warning']
        if user_input.engine == 'orca' and any(
            line.split() and line.split()[0].lower() == '%geom'
            for line in (user_input.orca_blocks or '').splitlines()
        ):
            advice.append(dict(code='scan_native_geometry_block', field='orca_blocks', severity='warning',
                message='The declared native %geom block is preserved beside the generated scan coordinates; review the combined geometry settings.'))
        try:
            content = QmInputWriter.render_input(request, mol)
        except ValueError as exc:
            return TsGuess_output_schema(is_success=False, message=f'scan input refused: {exc}', warnings=advice[-100:])
        errors = QmInputWriter.validate_rendered_input(request, content, charge=total_charge(mol))
        if errors:
            return TsGuess_output_schema(is_success=False, message='scan input internal mismatch: ' + ' | '.join(errors), warnings=advice[-100:])
        actual = inspect_input(content, engine=user_input.engine)
        if actual.tasks != {'relaxed_scan'}:
            advice.append(dict(code='purpose_task_mismatch', field='keywords', severity='warning',
                message=f'The preserved native declaration requests {sorted(actual.tasks)} rather than the scan task; review its native scan options.'))
        out_dir = os.path.dirname(os.path.abspath(user_input.output_path))
        os.makedirs(out_dir, exist_ok=True)
        atomic_write_text(user_input.output_path, content)

        return TsGuess_output_schema(
            is_success=True,
            input_file_path=user_input.output_path,
            calculation=QmInputWriter._written_calculation(request),
            warnings=advice[-100:],
            run_hint=run_hint,
            message=(
                f"{user_input.engine} constrained-scan input written to {user_input.output_path} "
                f"with method={calculation.method}, basis_set={calculation.basis_set!r}, keywords={calculation.keywords!r}: "
                + "; ".join(scan_labels)
                + ("; frozen values: " + "; ".join(
                    f"{kind} {[i + atom_index_base(user_input.engine) for i in idx]}="
                    f"{value if value is not None else InternalCoordinates._coordinate_value(mol.GetConformer().GetPositions(), idx):.6f}"
                    for kind, idx, value in frozen) if frozen else "")
                + "."
            ),
        )

    def _xtb_scan_prepare(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        from pathlib import Path

        from cloudra.runtime.chem_task import ChemTask

        if not user_input.method or not user_input.method.strip():
            raise ValueError('xTB scan requires an explicitly declared method')
        if not user_input.output_path or not user_input.scans:
            raise ValueError('xTB scan requires output_path and scans')
        workspace = getattr(getattr(self, 'subagent', None), 'working_directory', None)
        if workspace:
            root = Path(workspace).resolve()
            Path(user_input.output_path).resolve().relative_to(root)
            if user_input.input_path:
                Path(user_input.input_path).resolve().relative_to(root)
        if user_input.freeze or user_input.keywords or user_input.orca_blocks or user_input.end_setting:
            raise ValueError('xTB scan rejects Gaussian/ORCA directives and frozen coordinates')
        mol = _source_molecule(user_input, "input")
        if 'multiplicity' not in user_input.model_fields_set or (
            user_input.charge is None and mol.HasProp('cloudra_graph_status')
            and mol.GetProp('cloudra_graph_status') == 'unresolved'
        ):
            raise ValueError('xTB scan requires explicit charge and multiplicity for the bound XYZ')
        symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
        positions = mol.GetConformer().GetPositions()
        coordinates = []
        for row in user_input.scans:
            coordinates.append(row.model_copy(update={
                'atoms': atom_indices(row.atoms, base=1, count=len(symbols)),
            }))
        calculation = QmCalculation.model_validate({field: getattr(user_input, field) for field in QmCalculation.model_fields})
        scan = ScanGuess(kind='scan', calculation=calculation,
            scans=coordinates, force_constant=user_input.force_constant,
            mode=user_input.scan_mode, solvation=user_input.solvation)
        xyz = '\n'.join([str(len(symbols)), 'bound xTB scan input',
            *[f'{symbol} ' + ' '.join(f'{float(value):.14f}' for value in point)
              for symbol, point in zip(symbols, positions)]]) + '\n'
        task = ChemTask(task='xtb_scan', reactant_xyz=xyz, cpus=user_input.nproc,
                        charge=total_charge(mol), multiplicity=user_input.multiplicity,
                        electronic_character=user_input.electronic_character, scan=scan)
        output = Path(user_input.output_path)
        if output.exists():
            raise ValueError(f'xTB scan manifest already exists: {output}')
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(str(output), task.model_dump_json())
        return TsGuess_output_schema(is_success=True, input_file_path=str(output),
            calculation=calculation,
            run_hint=f"Submit {output} with submit_compute_job(job_type='chem_task'); parse the finished manifest with ts_guess(mode='scan_parse', engine='xtb', log_path='{output}').",
            message='Typed xTB scan manifest written; this has not run a calculation or validated a TS.')

    def _xtb_scan_parse(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        from pathlib import Path

        from cloudra.runtime.chem_task import ChemTask, read_task_result

        if not user_input.log_path:
            raise ValueError('xTB scan parsing requires log_path pointing to the typed manifest')
        manifest = Path(user_input.log_path)
        workspace = getattr(getattr(self, 'subagent', None), 'working_directory', None)
        if workspace:
            root = Path(workspace).resolve()
            manifest.resolve().relative_to(root)
            if user_input.ts_candidate_path:
                Path(user_input.ts_candidate_path).resolve().relative_to(root)
        task = ChemTask.model_validate_json(manifest.read_text())
        if task.task != 'xtb_scan':
            raise ValueError('xTB scan parsing accepts only a native xtb_scan manifest')
        data, _ = read_task_result(str(manifest))
        result = data['result']
        points = result.get('points', [])
        profile = 'point segment electronic_hartree relative_kcal frame_path\n'
        segment_starts = {}
        for point in points:
            energy = point.get('energy_hartree')
            first = segment_starts.setdefault(point['segment'], energy)
            relative = (energy - first) * KCAL_PER_HARTREE if energy is not None and first is not None else None
            profile += f"{point['index']} {point['segment']} {energy if energy is not None else 'unresolved'} {relative if relative is not None else 'unresolved'} {point['frame_path']}\n"
        candidates = result.get('candidates', [])
        candidate = candidates[0] if len(candidates) == 1 else None
        candidate_path = result.get('candidate_path') if candidate else None
        if candidate_path and user_input.ts_candidate_path:
            atomic_write_text(user_input.ts_candidate_path, Path(candidate_path).read_text())
            candidate_path = user_input.ts_candidate_path
        complete = result.get('scan_status') == 'complete'
        verdicts = list(result.get('issues', []))
        if len(candidates) > 1:
            indexed = {point['index']: point for point in points}
            for item in candidates:
                point = indexed[item['point_index']]
                verdicts.append(f"Candidate point {point['index']}: energy={point['energy_hartree']:.12f} Hartree; XYZ={point['frame_path']}")
            verdicts.append('Multiple internal local peaks; choose one with guess.kind=provided. These candidates are not verified TSs.')
        elif complete and not candidates:
            verdicts.append('No interior electronic-energy peak; no automatic TS guess')
        barrier = None
        if complete and len(candidates) == 1 and points and len(segment_starts) == 1 and all(point.get('energy_hartree') is not None for point in points):
            maximum = max(point['energy_hartree'] for point in points)
            selected = next(point for point in points if point['index'] == candidate['point_index'])
            if selected['energy_hartree'] == maximum:
                barrier = (maximum - points[0]['energy_hartree']) * KCAL_PER_HARTREE
        return TsGuess_output_schema(is_success=complete, message=(f"Native xTB scan complete; {'choose a local-peak frame with guess.kind=provided' if len(candidates) > 1 else 'candidate still requires formal validation'}. Native log: {result['log_file']}" if complete else f"Native xTB scan incomplete; inspect recorded issues. Native log: {result['log_file']}"),
            profile_table=profile, verdicts=verdicts, scan_has_internal_peak=bool(candidates) if complete else None,
            barrier_kcal=barrier, candidate=candidate, candidate_unavailable=False,
            ts_candidate_index=candidate['point_index'] - 1 if candidate else None,
            ts_candidate_path=candidate_path or '')

    # ---------- mode=scan_parse ----------

    def _scan_parse(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        import numpy as np

        if user_input.engine is None:
            engine = detect_qm_engine(user_input.log_path or '')
            if engine not in {'gaussian', 'orca'}:
                raise ValueError('scan_parse cannot detect a supported native log engine; declare engine explicitly for a manifest or sidecar-only input')
            user_input = user_input.model_copy(update={'engine': engine})
        if user_input.engine == 'xtb':
            return self._xtb_scan_parse(user_input)
        if not user_input.log_path:
            raise ValueError("scan_parse requires log_path")
        log_exists = os.path.isfile(user_input.log_path)
        text = None
        if log_exists:
            with open(user_input.log_path, encoding="utf-8", errors="replace") as f:
                text = f.read()

        symbols: Optional[list[str]] = None
        ts_coords = None
        scan_frames = None
        notes: list[str] = []
        candidate_source = ""

        if user_input.engine == "orca" and _orca_scan_is_grid(user_input.log_path, text or ''):
            return TsGuess_output_schema(is_success=True, candidate_unavailable=True,
                message='Independent multidimensional scan grid is not a one-dimensional path; no candidate was derived.')
        if user_input.engine == "gaussian":
            if text is None:
                raise ValueError(f"Gaussian scan parsing requires the scan log file: {user_input.log_path}")
            if _gaussian_scan_is_grid(text):
                return TsGuess_output_schema(is_success=True, candidate_unavailable=True,
                    message='Independent Gaussian multidimensional grid is not a one-dimensional path; no candidate was derived.')
            energies_eh = _parse_gaussian_scan_summary(text)
            n_pts = len(energies_eh)
            e0 = energies_eh[0]
            rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
            profile = analyze_scan_profile(rel_kcal)
            ts_index = profile["ts_index"]

            # TS 初猜几何：优先 cclib scancoords（与汇总表逐点对应），回退 Standard orientation 块
            try:
                import cclib

                data = cclib.io.ccread(user_input.log_path)
                scancoords = getattr(data, "scancoords", None) if data is not None else None
                atomnos = getattr(data, "atomnos", None) if data is not None else None
                if _gaussian_scan_is_grid(text, data):
                    return TsGuess_output_schema(is_success=True, candidate_unavailable=True,
                        message='Independent Gaussian multidimensional grid is not a one-dimensional path; no candidate was derived.')
                if scancoords is not None and atomnos is not None and len(scancoords) == n_pts:
                    from cclib.parser.utils import PeriodicTable

                    pt = PeriodicTable()
                    symbols = [pt.element[int(z)] for z in atomnos]
                    scan_frames = [(symbols, np.asarray(coords, dtype=float)) for coords in scancoords]
                    ts_coords = np.asarray(scancoords[ts_index], dtype=float)
                    candidate_source = "gaussian_log:cclib_scancoords"
            except Exception as e:
                notes.append(f"cclib geometry extraction failed ({e}); falling back to Standard orientation parsing.")

            if scan_frames is None:
                blocks = gaussian_frames.std_orientation_frames(text)
                if len(blocks) == n_pts:
                    # 块数与扫描点一一对应（每点恰一块）：峰值帧几何可靠可取
                    rows = blocks[ts_index]
                    from cclib.parser.utils import PeriodicTable

                    pt = PeriodicTable()
                    symbols = [pt.element[int(z)] for z, *_ in rows]
                    scan_frames = [
                        ([pt.element[int(z)] for z, *_ in block],
                         np.asarray([[x, y, z] for _, x, y, z in block], dtype=float))
                        for block in blocks
                    ]
                    ts_coords = np.asarray([[x, y, z] for _, x, y, z in rows], dtype=float)
                    candidate_source = "gaussian_log:std_orientation"
                elif profile['peak_indices']:
                    # 块数与扫描点无法一一对应：严禁按块均分猜峰值帧、也严禁拿
                    # 末块顶替（与 ORCA _ScanStepsUngroupable 同口径，GH #G1）。
                    lines = [f"{'frame':>4}  {'rel. energy (kcal/mol)':>18}"]
                    for k, e in enumerate(rel_kcal):
                        lines.append(f"{k:>4}  {e:>18.4f}")
                    distance_table, geometry_verdicts, _ = _scan_geometry_report(
                        energies_eh, None, user_input.watch_pairs, index_base=atom_index_base(user_input.engine),
                    )
                    return TsGuess_output_schema(
                        is_success=True,
                        profile_table="\n".join(lines),
                        scan_has_internal_peak=True,
                        distance_table=distance_table,
                        verdicts=[
                            *profile["verdicts"], *notes, *geometry_verdicts,
                            f"The log has {len(blocks)} 'Standard orientation' blocks for {n_pts} "
                            "scan points, so the blocks cannot be aligned to scan points one-to-one. "
                            "The peak-frame geometry was NOT derived by equal-split block division "
                            "and the last block was NOT substituted (GH #G1).",
                            "No TS-guess geometry was written. Re-parse with cclib-accessible scan "
                            "coordinates, or extract the peak geometry from the per-point output files.",
                        ],
                        barrier_kcal=None,  # 拒发候选时不报 barrier（G4）
                        candidate=None,
                        candidate_unavailable=True,
                        message=(
                            "Scan profile parsed, but the TS-candidate geometry is unavailable: the "
                            "'Standard orientation' blocks cannot be reliably mapped to scan points, "
                            "and no equal-split or last-frame substitution was applied."
                        ),
                    )
        else:
            # ORCA relaxed scan：sidecar（relaxscanact.dat 逐帧能量 + ts_scan.NNN.xyz
            # 逐帧几何）优先——能量最高帧往往不是末帧，.out 的 rfind 末帧会选错
            # TS 候选；.out 文本仅作无 sidecar 时的回退。
            try:
                sidecar = _parse_orca_relaxed_scan_sidecar(user_input.log_path)
            except _SidecarIncomplete as exc:
                # 本次产物的 sidecar 存在但峰值帧丢失/不可读：严禁拿 .out
                # 文本的末帧块顶替——candidate=null + candidate_unavailable。
                if exc.energies:
                    energies_eh = exc.energies
                    e0 = energies_eh[0]
                    rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
                    profile = analyze_scan_profile(rel_kcal)
                    known_peaks = ', '.join(str(index + 1) for index in profile['peak_indices']) or 'none'
                    distance_table, geometry_verdicts, _ = _scan_geometry_report(
                        energies_eh, exc.frames, user_input.watch_pairs, index_base=atom_index_base(user_input.engine),
                    )
                    lines = [f"{'frame':>4}  {'rel. energy (kcal/mol)':>18}"]
                    for k, e in enumerate(rel_kcal):
                        lines.append(f"{k:>4}  {e:>18.4f}")
                    return TsGuess_output_schema(
                        is_success=True,
                        profile_table="\n".join(lines),
                        scan_has_internal_peak=bool(profile['peak_indices']),
                        distance_table=distance_table,
                        verdicts=[
                            *geometry_verdicts,
                            f"Scan sidecar is incomplete: {exc}",
                            f"Known internal candidate points (1-based): {known_peaks}; the "
                            "sidecar frame sequence is incomplete, so candidate extraction was withheld and "
                            "the last frame was NOT substituted. Re-run or recover the missing "
                            "per-frame xyz before extracting a TS guess.",
                        ],
                        barrier_kcal=None,  # 拒发候选（峰值帧不可得）时不报 barrier（G4）
                        candidate=None,
                        candidate_unavailable=True,
                        message=(
                            "Scan profile parsed, but the sidecar frame sequence is incomplete, "
                            f"so the TS candidate was withheld: {exc} The peak was not replaced "
                            "by another frame."
                        ),
                    )
                return TsGuess_output_schema(
                    is_success=True,
                    verdicts=[
                        f"Scan sidecar is incomplete: {exc}",
                        "No TS candidate could be derived; the log text was not used as a "
                        "substitute for the missing per-frame geometries.",
                    ],
                    candidate=None,
                    candidate_unavailable=True,
                    message=f"Scan sidecar is present but unusable: {exc}",
                )
            if sidecar is not None:
                energies_eh = sidecar["energies"]
                e0 = energies_eh[0]
                rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
                profile = analyze_scan_profile(rel_kcal)
                ts_index = profile["ts_index"]
                frame_symbols, ts_coords = sidecar["frames"][ts_index]
                symbols = frame_symbols
                scan_frames = sidecar["frames"]
                candidate_source = "orca_relaxed_scan_sidecar"
            elif text is not None:
                try:
                    steps = _parse_orca_scan(text)
                except _ScanStepsUngroupable as exc:
                    # 日志文本无法按扫描步分组（如缺 RELAXED SURFACE SCAN STEP 标记）：
                    # 不产候选——绝不把优化周期能量当扫描点、也绝不按块均分取几何。
                    return TsGuess_output_schema(
                        is_success=True,
                        verdicts=[
                            f"ORCA scan log text cannot be grouped into scan points: {exc}",
                            "No TS-guess geometry was derived from the log text: per-cycle single-point "
                            "energies were NOT misread as scan points and no equal-split frame heuristic "
                            "was applied. Re-run the scan or recover the relaxscanact.dat sidecar "
                            "(<job>.relaxscanact.dat + <job>.NNN.xyz) for exact per-frame energies/geometries.",
                        ],
                        candidate=None,
                        candidate_unavailable=True,
                        message=f"ORCA scan text parsing refused (candidate unavailable): {exc}",
                    )
                energies_eh = [s["energy_hartree"] for s in steps]
                step_geoms = [s["geom"] for s in steps]
                scan_frames = [
                    ([row[0] for row in geom],
                     np.asarray([[row[1], row[2], row[3]] for row in geom], dtype=float))
                    for geom in step_geoms
                ]
                e0 = energies_eh[0]
                rel_kcal = [(e - e0) * KCAL_PER_HARTREE for e in energies_eh]
                profile = analyze_scan_profile(rel_kcal)
                ts_index = profile["ts_index"]
                # 能量最高帧（TS 候选）的几何 = 该扫描步收敛结构的最后一块直角坐标
                geom = step_geoms[ts_index]
                symbols = [g[0] for g in geom]
                ts_coords = np.asarray([[g[1], g[2], g[3]] for g in geom], dtype=float)
                candidate_source = "orca_log_text"
            else:
                raise ValueError(
                    f"Cannot parse the ORCA scan: {user_input.log_path} does not exist and no "
                    "relaxscanact.dat sidecar was found next to it. ORCA relaxed scans write "
                    "<job>.relaxscanact.dat and <job>.NNN.xyz — point log_path at the job name "
                    "(e.g. .../ts_scan.out even if the .out file is absent) to use them."
                )

        # 内部峰判定：TS 候选只在存在内部能量极大（0 < i < n-1）时成立。
        # 单调（升或降）或极值落在扫描边界的剖面没有鞍点证据——端点"最高"
        # 只是扫描范围/坐标选择的假象，升/降在这里语义完全同构：都不产出
        # TS-guess，防止把解离/无垒扫描的端点帧误当 TS 初猜去提交 OptTS。
        peaks = profile['peak_indices']
        has_internal_peak = bool(peaks)
        if len(peaks) == 1:
            ts_index = peaks[0]
            if scan_frames is not None:
                symbols, ts_coords = scan_frames[ts_index]

        # 剖面文本表
        lines = [f"{'frame':>4}  {'rel. energy (kcal/mol)':>18}"]
        for k, e in enumerate(rel_kcal):
            marker = "  <- internal local-peak candidate" if k in peaks else ""
            lines.append(f"{k:>4}  {e:>18.4f}{marker}")
        profile_table = "\n".join(lines)
        distance_table, geometry_verdicts, reference_symbols = _scan_geometry_report(
            energies_eh, scan_frames, user_input.watch_pairs, index_base=atom_index_base(user_input.engine),
        )
        if len(peaks) > 1:
            verdicts = list(profile['verdicts']) + notes + geometry_verdicts
            for peak in peaks:
                if scan_frames is None or scan_frames[peak] is None:
                    continue
                peak_symbols, peak_coords = scan_frames[peak]
                if (peak_symbols != reference_symbols
                        or np.asarray(peak_coords).shape != (len(peak_symbols), 3)
                        or not np.isfinite(peak_coords).all()):
                    return TsGuess_output_schema(is_success=True, scan_has_internal_peak=True,
                        profile_table=profile_table, distance_table=distance_table,
                        verdicts=verdicts, candidate_unavailable=True,
                        message='An internal local peak has no trustworthy aligned geometry; recover the native frame before selecting a candidate.')
                if candidate_source == 'orca_relaxed_scan_sidecar':
                    path = sidecar['frame_paths'][peak]
                else:
                    path = os.path.splitext(user_input.log_path)[0] + f'_peak_{peak + 1:04d}.xyz'
                    atomic_write_text(path, _atoms_to_xyz_block(peak_symbols, peak_coords,
                        comment=f'scan point {peak + 1} candidate; not a verified TS'))
                verdicts.append(f"Candidate point {peak + 1}: energy={energies_eh[peak]:.12f} Hartree; XYZ={path}")
            return TsGuess_output_schema(is_success=True, scan_has_internal_peak=True,
                profile_table=profile_table, distance_table=distance_table, verdicts=verdicts,
                message=f'{len(peaks)} internal local-peak candidates; inspect the recorded geometries and choose one with guess.kind=provided. These are not verified transition states.')
        if has_internal_peak:
            candidate_coords = np.asarray(ts_coords, dtype=float) if ts_coords is not None else None
            if (symbols is None or reference_symbols is None or symbols != reference_symbols
                    or candidate_coords is None
                    or candidate_coords.shape != (len(symbols), 3)
                    or not np.isfinite(candidate_coords).all()):
                return TsGuess_output_schema(
                    is_success=True,
                    profile_table=profile_table,
                    scan_has_internal_peak=True,
                    distance_table=distance_table,
                    verdicts=[*profile["verdicts"], *notes, *geometry_verdicts,
                              "The internal energy peak has no trustworthy aligned geometry; "
                              "no TS candidate was written or substituted."],
                    candidate_unavailable=True,
                    message="Scan profile parsed, but the peak geometry is invalid or unavailable; "
                            "no TS candidate was written.",
                )

        # 候选来源注释只在真正发出 TS-guess（内部峰存在）时追加；无内部峰/拒发时
        # 不得声称 "TS-guess geometry is ..."（G4，避免与拒发 verdict 自相矛盾）。
        if has_internal_peak:
            if candidate_source == "orca_relaxed_scan_sidecar":
                notes.append(
                    "ORCA relaxed-scan sidecar used (relaxscanact.dat + per-frame xyz): "
                    f"TS-guess geometry is the selected internal local-peak frame {ts_index} (1-based {ts_index + 1}), not the last frame."
                )
            elif candidate_source == "orca_log_text":
                notes.append(
                    f"ORCA scan text fallback grouped {len(rel_kcal)} relaxed-scan steps by their "
                    "'RELAXED SURFACE SCAN STEP' markers and used each step's converged (last) "
                    "single-point energy, so the TS-guess geometry is the selected internal local-peak frame "
                    f"{ts_index} (1-based {ts_index + 1}), not the last frame."
                )

        verdicts = list(profile["verdicts"]) + notes + geometry_verdicts
        if not has_internal_peak:
            verdicts.append(
                "The scan has no internal local energy maximum: an endpoint maximum is NOT a TS candidate — do not submit a TS "
                "optimization from it. Inspect the actual geometries before choosing another coordinate or an explicitly concerted path. "
                "This finite scan does not establish that the target reaction is barrierless or impossible."
            )

        ts_path = ""
        ts_candidate_index = None
        if has_internal_peak:
            ts_candidate_index = ts_index
            ts_path = (
                user_input.ts_candidate_path
                or os.path.splitext(user_input.log_path)[0] + "_ts_guess.xyz"
            )
            out_dir = os.path.dirname(os.path.abspath(ts_path))
            os.makedirs(out_dir, exist_ok=True)
            atomic_write_text(ts_path, _atoms_to_xyz_block(
                symbols, ts_coords,
                comment=f"ts_guess scan_parse TS candidate frame={ts_index} from {os.path.basename(user_input.log_path)}",
            ))

        if has_internal_peak:
            message = (
                f"Scan parsing complete: {len(rel_kcal)} points; internal local-peak candidate at frame {ts_index} "
                f"(point {ts_index + 1}); XYZ={ts_path}. This constrained geometry is not a verified TS or reaction barrier. "
                "Continue with an unconstrained TS optimization, frequency analysis and IRC."
            )
        else:
            message = (
                f"Scan parsing complete: {len(rel_kcal)} points; no internal local energy maximum was found. "
                "An endpoint maximum is NOT a TS candidate; do "
                "not submit a TS optimization from it), so no TS-guess geometry was written. Choose a "
                "different/extra scan coordinate before hunting a TS."
            )
        candidate = None
        if has_internal_peak and ts_path:
            candidate = {
                "scan_index": ts_candidate_index,
                "energy": energies_eh[ts_index],
                "geometry_ref": ts_path,
                "source": candidate_source,
            }
        return TsGuess_output_schema(
            is_success=True,
            profile_table=profile_table,
            scan_has_internal_peak=has_internal_peak,
            distance_table=distance_table,
            verdicts=verdicts,
            # G4：只有存在内部峰（确实发出 TS 候选）时才填 barrier；端点极大/单调
            # 剖面（无内部峰）的 "最高点−首点" 不是能垒，置 None。
            barrier_kcal=(round(profile["barrier_kcal"], 4) if has_internal_peak and profile['ts_index'] == ts_index else None),
            ts_candidate_index=ts_candidate_index,
            ts_candidate_path=ts_path,
            candidate=candidate,
            message=message,
        )

    # ---------- mode=verify ----------

    def _verify(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        if not user_input.freq_log:
            raise ValueError("verify requires freq_log")
        if not os.path.isfile(user_input.freq_log):
            raise ValueError(f"Frequency log does not exist: {user_input.freq_log}")

        engine = detect_qm_engine(user_input.freq_log)
        if engine not in {"gaussian", "orca"}:
            raise ValueError(f"Cannot verify frequency log with unknown or unsupported engine: {engine}")
        if user_input.engine is not None and user_input.engine != engine:
            raise ValueError(
                f"Frequency log engine mismatch: requested {user_input.engine}, detected {engine}"
            )
        # Use the same detected engine for native parsing, IRC dispatch and atom indices.
        user_input = user_input.model_copy(update={"engine": engine})
        freq = _parse_freq_log(user_input.freq_log, user_input.engine)
        vibfreqs = freq["vibfreqs"]
        imag = [f for f in vibfreqs if f < 0]
        n_imag = len(imag)
        checks: list[str] = []
        references = {}
        reference_error = None
        frequency_usable = freq['normal_termination'] and freq['opt_converged'] is not False
        if frequency_usable and n_imag == 1:
            try:
                references = _reference_molecules(user_input)
            except Exception as exc:
                reference_error = str(exc)

        irc_end_a_path = ""
        irc_end_b_path = ""
        imag_mode_aligned: Optional[bool] = None
        imag_mode_alignment = ""

        def _record_mode_alignment() -> None:
            nonlocal imag_mode_aligned, imag_mode_alignment
            assessment = _assess_imag_mode_alignment(
                vibfreqs,
                freq.get("vibdisps"),
                user_input.watch_pairs,
                symbols=freq.get("symbols"),
                positions=freq.get("positions"),
                index_base=atom_index_base(user_input.engine),
                charge=total_charge(references["reactant"]) if "reactant" in references else user_input.charge or 0,
            )
            imag_mode_aligned = assessment["aligned"]
            imag_mode_alignment = assessment["message"]
            warning = (
                "[warning] Imaginary-mode alignment is advisory; strict verification uses actual IRC endpoint proof. "
                if assessment["status"] in {"missing", "undecidable", "misaligned"} else ""
            )
            checks.append(warning + assessment["message"])
            checks.extend(assessment.get("details") or [])

        if reference_error is not None:
            checks.append(f"Endpoint reference structures could not be parsed: {reference_error}")
            verdict = "inconclusive: the endpoint reference structures could not be parsed."
            status = "inconclusive"
        elif user_input.strict:
            if not frequency_usable:
                checks.append("The frequency job lacks native normal termination or reports an unconverged optimization; the first-order saddle-point premise cannot be established.")
                verdict = "inconclusive: the frequency job lacks normal termination or optimization convergence; the available material is insufficient for a strict judgement."
                status = "inconclusive"
            elif n_imag != 1:
                if n_imag == 0:
                    checks.append("A normally terminated frequency job has no imaginary frequency: the structure is a minimum, not a first-order saddle point.")
                else:
                    checks.append(
                        f"A normally terminated frequency job has {n_imag} imaginary frequencies "
                        f"({', '.join(f'{f:.1f}' for f in imag)} cm⁻¹): the structure is a higher-order saddle point."
                    )
                verdict = "fail: the strict check requires exactly one imaginary frequency."
                status = "fail"
            else:
                checks.append(f"Exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹): the first-order saddle-point premise holds.")
                _record_mode_alignment()
                status, verdict, info = self._strict_path_verdict(user_input, checks, references)
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
        else:
            if not frequency_usable:
                checks.append("The frequency job lacks native normal termination or reports an unconverged optimization; cannot judge the TS candidate from it.")
                verdict = "inconclusive: the frequency job lacks normal termination or optimization convergence."
                status = "inconclusive"
            elif n_imag == 0:
                checks.append("No imaginary frequency: the structure is a minimum, not like a first-order saddle point.")
                verdict = "unlikely: no imaginary frequency; the structure looks more like a minimum."
                status = "fail"
            elif n_imag > 1:
                checks.append(
                    f"{n_imag} imaginary frequencies ({', '.join(f'{f:.1f}' for f in imag)} cm⁻¹): "
                    "the structure looks more like a higher-order saddle point."
                )
                verdict = "unlikely: multiple imaginary frequencies; the structure looks more like a higher-order saddle point."
                status = "fail"
            else:
                checks.append(
                    f"Exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹): acceptable as a first-order saddle-point candidate, but this is not sufficient proof."
                )
                _record_mode_alignment()
                irc_ok: Optional[bool] = None
                info = self._extract_irc_endpoints(
                    user_input.irc_log, checks, engine=user_input.engine,
                    output_dir=user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify",
                    require_two_sides=False,
                )
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
                    irc_ok = self._check_irc_connectivity(
                        user_input, info["end_a"], info["end_b"], checks, references,
                    )

                if user_input.irc_log and info is None:
                    verdict = "inconclusive: IRC was provided, but comparable endpoint geometries could not be obtained."
                    status = "inconclusive"
                elif irc_ok is False:
                    verdict = "unlikely: the rough connectivity of the IRC endpoints is inconsistent with the expected structures."
                    status = "fail"
                elif irc_ok == "inconclusive":
                    verdict = (
                        "inconclusive: the IRC endpoints could not be compared with the expected "
                        "structures (atom order or element mismatch); connectivity is undecidable."
                    )
                    status = "inconclusive"
                else:
                    reason = "one imaginary frequency" + ("; rough IRC connectivity consistent" if irc_ok else "")
                    verdict = f"candidate: {reason}; advisory only for the agent's next step, not a strict proof of the TS."
                    status = "candidate"

        return TsGuess_output_schema(
            is_success=True,
            verdict=verdict,
            verification_status=status,
            n_imag=n_imag,
            imag_freqs=[round(f, 2) for f in imag],
            checks=checks,
            irc_end_a_path=irc_end_a_path,
            irc_end_b_path=irc_end_b_path,
            imag_mode_aligned=imag_mode_aligned,
            imag_mode_alignment=imag_mode_alignment,
            message=f"TS verification complete: {verdict}",
        )

    @staticmethod
    def _extract_irc_endpoints(irc_log: str | None, checks: list[str], *,
                               engine: str, output_dir: str,
                               require_two_sides: bool) -> Optional[dict]:
        """提取有坐标的 IRC 外侧帧；strict 时必须分别来自 rx<0 与 rx>0。"""
        if not irc_log:
            checks.append("No IRC log provided.")
            return None
        if not os.path.isfile(irc_log):
            raise ValueError(f"IRC log does not exist: {irc_log}")

        if engine == "orca":
            return TsGuess._extract_orca_irc_endpoints(
                irc_log, checks, output_dir=output_dir, require_two_sides=require_two_sides,
            )

        from cloudra.tools.core import gaussian_frames

        try:
            frames, meta = gaussian_frames.extract_irc(irc_log)
        except Exception as e:
            checks.append(f"IRC endpoint extraction failed: {e}")
            return None

        valid = [frame for frame in frames if frame.xyz.strip()]
        if require_two_sides:
            negative = [
                frame for frame in valid
                if frame.reaction_coordinate is not None and frame.reaction_coordinate < 0
            ]
            positive = [
                frame for frame in valid
                if frame.reaction_coordinate is not None and frame.reaction_coordinate > 0
            ]
            if not negative or not positive:
                checks.append("The IRC log does not provide valid coordinate frames on both rx<0 and rx>0 sides.")
                return None
            end_a = min(negative, key=lambda frame: frame.reaction_coordinate)
            end_b = max(positive, key=lambda frame: frame.reaction_coordinate)
        else:
            if len(valid) < 2:
                checks.append("Fewer than two path frames with coordinates in the IRC log.")
                return None
            end_a, end_b = valid[0], valid[-1]

        out_dir = output_dir
        os.makedirs(out_dir, exist_ok=True)
        path_a = os.path.join(out_dir, "irc_end_a.xyz")
        path_b = os.path.join(out_dir, "irc_end_b.xyz")
        atomic_write_text(path_a, end_a.xyz.rstrip() + "\n")
        atomic_write_text(path_b, end_b.xyz.rstrip() + "\n")
        checks.append(
            f"IRC outer frames extracted: irc_end_a.xyz (rx={end_a.reaction_coordinate}), "
            f"irc_end_b.xyz (rx={end_b.reaction_coordinate}) -> {out_dir}"
        )
        if require_two_sides and not (
            meta.get("forward_converged", False) and meta.get("backward_converged", False)
        ):
            checks.append("The IRC did not reach a minimum on at least one side; strict requires separate optimization and zero-imaginary frequency evidence for its actual outer frames.")
        return {
            "end_a": end_a,
            "end_b": end_b,
            "frames": frames,
            "meta": meta,
            "path_a": path_a,
            "path_b": path_b,
        }

    @staticmethod
    def _extract_orca_irc_endpoints(irc_log: str, checks: list[str], *,
                                    output_dir: str, require_two_sides: bool) -> Optional[dict]:
        """ORCA IRC 端点：复用 orca_frames 的 final endpoint / F-B trajectory
        读取（解析规则不在这里复制）。forward/backward 是轨迹方向标签，
        不自动映射 reactant/product。收敛与否只记录、绝不做闸门：与 Gaussian
        通道同口径，每侧取最外侧可用几何（未收敛方向的轨迹末帧同样是合法的
        部分端点），strict 通过实际外侧帧的 Opt/Freq 日志核对方向。"""
        from types import SimpleNamespace

        from cloudra.tools.core import orca_frames

        endpoints = orca_frames.extract_irc_endpoints(irc_log)
        forward, backward = endpoints["forward"], endpoints["backward"]
        for label, info in (("forward", forward), ("backward", backward)):
            converged = info.get("converged")
            if converged is False:
                checks.append(
                    f"The ORCA IRC {label} direction terminated WITHOUT converging; "
                    "the trajectory's outermost frame is used as that side's partial endpoint; "
                    "strict requires its actual endpoint Opt/Freq evidence."
                )
            elif converged:
                checks.append(
                    f"The ORCA IRC {label} direction converged; a short converged path "
                    "needs no padding to a fixed point count."
                )

        xyz_a = orca_frames.read_endpoint_geometry(forward)
        xyz_b = orca_frames.read_endpoint_geometry(backward)
        if xyz_a is None or xyz_b is None:
            checks.append(
                "ORCA IRC endpoint geometries are not available on both sides "
                "(final endpoint files or F/B trajectories are missing); one side's "
                "geometry is never reused as the other side."
            )
            return None

        end_a = SimpleNamespace(xyz=xyz_a, reaction_coordinate=None)
        end_b = SimpleNamespace(xyz=xyz_b, reaction_coordinate=None)
        out_dir = output_dir
        os.makedirs(out_dir, exist_ok=True)
        path_a = os.path.join(out_dir, "irc_end_a.xyz")
        path_b = os.path.join(out_dir, "irc_end_b.xyz")
        atomic_write_text(path_a, xyz_a.rstrip() + "\n")
        atomic_write_text(path_b, xyz_b.rstrip() + "\n")
        checks.append(
            "ORCA IRC endpoints extracted (forward/backward are trajectory directions, "
            f"NOT reactant/product assignments): irc_end_a.xyz ({forward.get('origin')}), "
            f"irc_end_b.xyz ({backward.get('origin')}) -> {out_dir}"
        )
        return {
            "end_a": end_a,
            "end_b": end_b,
            "frames": [end_a, end_b],
            "meta": {
                "forward_converged": bool(forward.get("converged")),
                "backward_converged": bool(backward.get("converged")),
            },
            "path_a": path_a,
            "path_b": path_b,
        }

    def _strict_path_verdict(self, user_input: TsGuess_input_schema,
                             checks: list[str], references) -> tuple[str, str, Optional[dict]]:
        """核对同一 TS 的 IRC 外侧帧实际优化到两侧身份正确的零虚频极小点。"""
        from cloudra.tools.core.irc_evidence import verify_short_irc_direction

        def inconclusive(reason: str, info):
            checks.append(_IRC_TRUNCATION_REMEDY)
            return "inconclusive", f"inconclusive: {reason} {_IRC_TRUNCATION_REMEDY}", info

        info = self._extract_irc_endpoints(
            user_input.irc_log, checks, engine=user_input.engine,
            output_dir=user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify",
            require_two_sides=True,
        )
        if info is None:
            return inconclusive("no usable bidirectional IRC endpoints.", None)
        if not all(role in references for role in ("reactant", "product")):
            return inconclusive("missing the expected reactant and product structures.", info)
        if not user_input.reactant_logs or not user_input.product_logs:
            return inconclusive("missing actual endpoint optimization and zero-imaginary frequency logs.", info)

        def species(role):
            from rdkit import Chem
            from rdkit.Chem import rdDetermineBonds

            molecule = Chem.Mol(references[role])
            if molecule.HasProp("cloudra_graph_status") and molecule.GetProp("cloudra_graph_status") == "unresolved":
                rdDetermineBonds.DetermineBonds(molecule, charge=total_charge(references[role]))
            molecule = Chem.RemoveHs(molecule)
            for atom in molecule.GetAtoms():
                atom.SetAtomMapNum(0)
            return Chem.MolToSmiles(molecule)

        try:
            reactant_smiles, product_smiles = species("reactant"), species("product")
        except (ValueError, RuntimeError) as exc:
            checks.append(f"Expected endpoint identity cannot be resolved; supply a complete MOL/SDF graph: {exc}")
            return inconclusive("the expected endpoint molecular identity is unresolved.", info)

        passed, details = verify_short_irc_direction(
            user_input.irc_log, [user_input.freq_log],
            user_input.product_logs, user_input.reactant_logs,
            charge=total_charge(references["reactant"]),
            reactant_smiles=reactant_smiles, product_smiles=product_smiles,
        )
        checks.extend(details)
        if passed:
            return (
                "pass",
                "pass: both actual IRC outer frames optimize to the expected zero-imaginary endpoint minima.",
                info,
            )
        checks.append(_IRC_TRUNCATION_REMEDY)
        return (
            "fail",
            "fail: the submitted logs do not prove that both actual IRC outer frames optimize "
            f"to the expected zero-imaginary endpoint minima. {_IRC_TRUNCATION_REMEDY}",
            info,
        )

    @staticmethod
    def _check_irc_connectivity(user_input: TsGuess_input_schema, end_a, end_b,
                                checks: list[str], references) -> "bool | str | None":
        """比较 IRC 两端点与预期反应物/产物的成键集合（rdDetermineBonds 主通道）。

        返回 True / False / "inconclusive" / None：
        - None：未提供预期结构，只报告成键表（不判连通性）；
        - "inconclusive"：端点或预期结构的原子序/元素不一致，连通性不可判
          （绝不静默跳过成 candidate）；
        - 键集差异按**预期结构侧**距离分级：超出 DISTANCE_CONNECTIVITY_FACTOR×共价半径和的弱接触
          （氢键/非键接触）差异只记 warning 不判负；共价差异判负。
        """
        import ase.io
        import numpy as np

        def frame_atoms(frame):
            return ase.io.read(StringIO(frame.xyz), format="xyz")

        charge = total_charge(references["reactant"]) if "reactant" in references else user_input.charge or 0

        def perceive(atoms) -> set[tuple[int, int]]:
            return set(_perceive_bonds(
                atoms.get_chemical_symbols(),
                [list(p) for p in atoms.get_positions()],
                charge,
            )[0])

        atoms_a = frame_atoms(end_a)
        atoms_b = frame_atoms(end_b)
        syms = atoms_a.get_chemical_symbols()
        if atoms_b.get_chemical_symbols() != syms:
            checks.append(
                "The two IRC endpoint frames differ in atom order or elements; "
                "connectivity is undecidable."
            )
            return "inconclusive"
        bonds_a = perceive(atoms_a)
        bonds_b = perceive(atoms_b)

        def bond_table(name, bonds):
            if bonds:
                return f"{name} bonds: " + ", ".join(_pair_label(syms, pr, atom_index_base(user_input.engine)) for pr in sorted(bonds))
            return f"{name} bonds: (none)"

        if not (user_input.reactant_path or user_input.reactant_text) and \
           not (user_input.product_path or user_input.product_text):
            checks.append(
                "No expected reactant/product provided; reporting IRC endpoint bond tables only: "
                + bond_table("Endpoint A", bonds_a) + "; " + bond_table("Endpoint B", bonds_b)
            )
            return None

        reactant, product = references["reactant"], references["product"]
        r_atoms, p_atoms = to_ase(reactant), to_ase(product)
        if r_atoms.get_chemical_symbols() != syms or p_atoms.get_chemical_symbols() != syms:
            checks.append(
                "The expected reactant/product atom order or elements differ from the IRC job; "
                "the connectivity check is undecidable."
            )
            return "inconclusive"
        def reference_bonds(mol):
            if mol.HasProp("cloudra_graph_status") and mol.GetProp("cloudra_graph_status") == "unresolved":
                return perceive(to_ase(mol))
            return {tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))) for bond in mol.GetBonds()}

        bonds_r = reference_bonds(reactant)
        bonds_p = reference_bonds(product)
        exp_pos = {"reactant": r_atoms.get_positions(), "product": p_atoms.get_positions()}

        def split_diff(end_bonds, exp_name, exp_bonds):
            """键集差异 → (共价差异, 弱接触差异)：按预期结构侧距离分级。"""
            covalent: list[tuple[int, int]] = []
            weak: list[tuple[int, int]] = []
            pos = exp_pos[exp_name]
            for pair in sorted(set(end_bonds) ^ set(exp_bonds)):
                limit = _DISTANCE_CONNECTIVITY_FACTOR * (
                    _COVALENT_RADII.get(syms[pair[0]], 1.2)
                    + _COVALENT_RADII.get(syms[pair[1]], 1.2)
                )
                d = float(np.linalg.norm(pos[pair[0]] - pos[pair[1]]))
                (weak if d > limit else covalent).append(pair)
            return covalent, weak

        # 两种端点↔预期指派，按共价差异键总数取小者（弱接触不参与指派计分）
        direct = (
            len(split_diff(bonds_a, "reactant", bonds_r)[0])
            + len(split_diff(bonds_b, "product", bonds_p)[0])
        )
        swapped = (
            len(split_diff(bonds_a, "product", bonds_p)[0])
            + len(split_diff(bonds_b, "reactant", bonds_r)[0])
        )
        if swapped < direct:
            assign = [("Endpoint A", bonds_a, "product", bonds_p), ("Endpoint B", bonds_b, "reactant", bonds_r)]
        else:
            assign = [("Endpoint A", bonds_a, "reactant", bonds_r), ("Endpoint B", bonds_b, "product", bonds_p)]

        diff_lines: list[str] = []
        warning_lines: list[str] = []
        for end_name, end_bonds, exp_name, exp_bonds in assign:
            covalent, weak = split_diff(end_bonds, exp_name, exp_bonds)
            if covalent:
                diff_lines.append(
                    f"{end_name} vs {exp_name} (covalent differences: "
                    + ", ".join(_pair_label(syms, pr, atom_index_base(user_input.engine)) for pr in covalent) + ")"
                )
            if weak:
                warning_lines.append(
                    f"{end_name} vs {exp_name} (weak-contact differences: "
                    + ", ".join(_pair_label(syms, pr, atom_index_base(user_input.engine)) for pr in weak) + ")"
                )

        if diff_lines:
            checks.append(
                "IRC endpoints' connectivity is inconsistent with the expected reactant/product "
                "(covalent bond-set differences): " + "; ".join(diff_lines)
            )
            return False
        for line in warning_lines:
            checks.append(
                "[warning] weak-contact (H-bond/non-covalent at the expected minimum) bond-set "
                "difference, not counted as failure: " + line
            )
        checks.append(
            "IRC endpoints' connectivity is consistent with the expected reactant/product: "
            + "; ".join(f"{end} ↔ {exp}" for end, _, exp, _ in assign)
        )
        return True




def is_compute_entry_call(arguments: dict[str, Any]) -> bool:
    """DAG 前置门的结构/输入准备入口；谓词不表示工具是否直接执行 QM。"""
    return (arguments or {}).get("mode") in {"interpolate", "scan_prepare"}


def derive_delivery_changes(
    *,
    current: dict[str, Any],
    role: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """DAG evidence derivation owned by this tool; kept out of DagController.

    ``ts_guess`` results are advisory by design: they may add an advisory
    source, and only a strict endpoint-direction check can set a derived flag.
    """
    advisory = list(current.get("advisory_sources") or [])
    if "ts_guess" not in advisory:
        advisory.append("ts_guess")
    changes: dict[str, Any] = {"advisory_sources": advisory}
    if (
        role == "endpoint_direction_check"
        and arguments.get("strict") is True
        and str(result.get("verdict") or "").startswith("pass")
    ):
        changes["endpoint_direction_consistent"] = True
    return changes

