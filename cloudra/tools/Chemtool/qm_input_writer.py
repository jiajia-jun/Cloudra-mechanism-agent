import asyncio
import math
import os
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import Field, model_validator

try:
    from rdkit import Chem
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    _RDKIT_AVAILABLE = False

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.calculation_intent import (
    inspect_input,
    intent_from_writer,
    validate_writer_request,
)
from cloudra.tools.core.molecule import read_molecule, to_xyz, total_charge
from cloudra.tools.core.qm_calculation import QmCalculation
from cloudra.tools.core.qm_keywords import gaussian_basis_keyword, orca_basis_keyword
from cloudra.tools.core.structure_builder import (
    BuildStrategy,
    PreparationRequest,
    StructureInput,
    build_artifact_dir,
    prepare_structure,
)


class StructureBuildRefused(Exception):
    """SMILES → 坐标 由共享构建器拒绝（带显式构建状态，不冒充路径/参数错误）。"""

    def __init__(self, status: str, message: str, diagnostics: list[str], artifact_path: str):
        super().__init__(message)
        self.status = status
        self.message = message
        self.diagnostics = diagnostics
        self.artifact_path = artifact_path

description = (
    "Generate a complete quantum-chemistry input file (Gaussian .gjf or ORCA .inp, selected by `engine`) "
    "from a molecular source, method, basis, and related parameters, and save it to a given path; "
    "coordinates are generated from a file or SMILES and never appear in the return value. "
    "External MLIP potentials (e.g. MACE) are supported via external_program/external_params "
    "(ORCA '! ExtOpt' + %method ProgExt block; Gaussian external=\"...\" route). "
    "Use for: preparing Gaussian/ORCA inputs (opt, freq, TS search, etc.) to submit with submit_compute_job "
    "(job_type='gaussian' or 'orca', matching `engine`). "
    "Do not use for: parsing results (use log_parser) or converting an existing structure file (use format_converter)."
)


class QmInputWriter_input_schema(QmCalculation, input_schema):
    engine: Literal["gaussian", "orca"] = Field(
        description="Target QM program. 'gaussian': write a .gjf (submit with job_type='gaussian'); "
                    "'orca': write a .inp (submit with job_type='orca'). "
                    "task_type and known basis aliases map onto each program's input syntax; "
                    "method and additional keywords must use that program's native spelling.",
    )
    source_type: Literal["smiles", "xyz_file", "mol_file"] = Field(
        description="Molecular-structure source type. "
                    "'smiles': generate 3D coordinates from a SMILES string; "
                    "'xyz_file': read coordinates from a .xyz file; "
                    "'mol_file': read coordinates from a .mol file."
    )
    source_value: str = Field(
        description="Molecular-structure source value. "
                    "When source_type='smiles', a SMILES string (e.g. 'CC(=O)O'); "
                    "when source_type='xyz_file' or 'mol_file', the file's path — "
                    "absolute as-is, or relative to the Agent working directory."
    )
    external_program: Optional[str] = Field(
        default=None,
        description="Explicit external MLIP route: declare method='ExtOpt' for ORCA or 'external' "
                    "for Gaussian, and basis_set=''. ORCA: absolute path of the "
                    "ProgExt executable — emits '! ExtOpt <tasks>' plus a %method ProgExt block, "
                    "e.g. '/opt/conda/envs/chemai/bin/mace'; the file must exist, be executable, "
                    "and live outside the working directory/data dir. Gaussian: engine value of the "
                    "external=\"...\" route keyword, e.g. 'mace' — a single [a-z0-9_.-] token, no "
                    "spaces or program arguments (they would bypass method-policy parsing)."
    )
    external_params: Optional[str] = Field(
        default=None,
        description="ORCA only, requires external_program: Ext_Params string handed to the external "
                    "program, e.g. '--model /abs/model --device cpu --dtype float64'. For Gaussian, "
                    "fold program arguments into external_program instead."
    )
    task_type: list[dict] = Field(
        default=[{"opt": None}],
        description='''List of dicts whose keys are job types and values are their parameters.
                    Keys: opt/freq/irc/single_point ('sp' accepted as the same single-point task); scan is Gaussian-only.
                    Gaussian example: [{"opt":"TS,calcfc,noeigen"},{"freq":None}];
                    the same dict works for ORCA (mapped to `! OptTS Freq` etc.).
                    ORCA scans use ts_guess mode='scan_prepare' with structured coordinates.
                    Gaussian only accepts the explicit {"scan":"rigid"} declaration (bare `scan`
                    route = RIGID scan, coordinate via end_setting) — a bare {"scan":None} is refused.'''
    )
    frequency_mode: Literal["auto", "analytic", "numeric"] = Field(
        default="auto",
        description="Frequency evaluation mode. ORCA: 'numeric' with task_type=[{'freq':None}] "
                    "emits NumFreq (required for external potentials); 'analytic'/'auto' emit Freq. "
                    "Rejected when no frequency task is requested.",
    )

    charge: int | None = Field(
        default=None,
        description="Total molecular charge. Omit for MOL/SMILES to use the structure's formal charge; "
                    "an explicit value must match that structure. XYZ contains no formal charges: "
                    "declare its total charge here, or omit for neutral."
    )
    multiplicity: int = Field(
        default=1,
        description="Spin multiplicity. Singlet=1, doublet=2, triplet=3."
    )
    electronic_character: Literal["closed_shell", "open_shell"] | None = Field(
        default=None, description="Optional explicit electronic character for SMILES seed generation; "
        "open_shell singlets skip closed-shell force fields. Does not choose a QM method or initial spin.",
    )
    mem: str = Field(
        default="4GB",
        description="TOTAL memory for the whole job, e.g. '4GB', '8GB'. Gaussian writes %mem "
                    "verbatim (a total); ORCA writes %maxcore = mem/nproc because ORCA maxcore "
                    "is a PER-CORE value. Request memory_mb equal to this total when submitting."
    )
    nproc: int = Field(
        default=4,
        ge=1,
        description="Number of CPU cores for parallel compute (Gaussian %nprocshared / ORCA %pal)."
    )
    orca_blocks: Optional[str] = Field(
        default=None,
        description="ORCA-only: raw % block lines inserted between the `!` line and the coordinate "
                    "block, e.g. '%geom MaxIter 200 end'. Scans use ts_guess mode='scan_prepare'. "
                    "Native atom indices are 0-based and refer to the exact XYZ order including explicit H. "
                    "For a SMILES source, use the generated build's "
                    "prepared_structure.json atom_identities, not SMILES heavy-atom positions. "
                    "Rejected for engine='gaussian'."
    )
    title: str = Field(
        default="Gaussian job generated by Cloudra",
        description="Job title (Gaussian title line; ORCA has no title card — emitted as a comment)."
    )
    end_setting: str = Field(
        default="",
        description="Extra settings appended at the end of the file, e.g. mixed basis or scan setup. "
                    "Example: B 1 34 S 15 0.02"
    )
    output_path: str = Field(
        description="Path of the Gaussian .gjf or ORCA .inp file (including filename): absolute as-is, "
                    "or relative to the Agent working directory."
    )
    artifact_dir: Optional[str] = Field(
        default=None,
        description="Directory for the SMILES-source build artifacts (per-component structures, "
                    "optimization trajectories, prepared_structure.json). Default: "
                    "'<output_path parent>/structure_build/<stem>/' next to the generated input file. "
                    "Relative paths resolve against the Agent working directory."
    )
    chk_name: Optional[str] = Field(
        default=None,
        description="chk filename, e.g. H2O.chk. By convention point it into the same directory "
                    "as output_path (absolute path preferred): the per-task Gaussian scratch is "
                    "deleted after the run, so a checkpoint outside the .gjf directory is lost."
    )
    rwf_name: Optional[str] = Field(
        default=None,
        description="rwf filename; Gaussian scratch file, often large."
    )
    fchk_name: Optional[str] = Field(
        default=None,
        description="fchk filename. Same placement convention as chk_name: same directory as "
                    "output_path, absolute path preferred."
    )

    @model_validator(mode='after')
    def explicit_external_route(self):
        if self.external_program:
            required = 'extopt' if self.engine == 'orca' else 'external'
            if self.method.casefold() != required or self.basis_set:
                raise ValueError(f"external_program requires method='{required}' and basis_set='' for {self.engine}")
        return self


class QmInputWriter_output_schema(output_schema):
    is_success: bool = Field(description="Whether the file was generated")
    input_path: str = Field(default="", description="Absolute path of the generated input file (.gjf or .inp, per `engine`)")
    message: str = Field(default="", description="Status or error message")
    calculation: QmCalculation | None = Field(default=None,
        description="Complete calculation settings written to the returned input, including explicit external route settings; file generation is not a scientific result.")
    interpreted_intent: dict = Field(
        default_factory=dict,
        description="CalculationIntent re-inspected from the GENERATED text (not from the "
                    "writer's own claim): tasks, frequency_mode, constraints, method signature.",
    )
    unapplied_options: list[str] = Field(
        default_factory=list,
        description="Requested options that could NOT be realized in the file. Empty on success; "
                    "a successful write never silently drops an option.",
    )
    generation_path: str = Field(
        default="",
        description="How the file was produced, e.g. 'orca:simple+orca_blocks' or 'gaussian:route'.",
    )


# Gaussian 风格 task key -> ORCA simple-input 关键字（参数太 Gaussian 化时保守降级）
_ORCA_TASK_KEYWORDS = {
    "opt": "Opt",
    "freq": "Freq",
    "irc": "IRC",
    "scan": "Opt",
}


class QmInputWriter(Tool):
    tool_id: str = 't-20'
    tool_name: str = 'qm_input_writer'
    tool_description: str = description
    input_schema: Any = QmInputWriter_input_schema
    output_schema: Any = QmInputWriter_output_schema

    def is_write(self) -> bool:
        return True

    def _validate_external_program(self, user_input: QmInputWriter_input_schema) -> Optional[str]:
        """external_program 安全校验：返回 None 放行，否则返回拒绝原因（fail-loud）。

        ORCA：ProgExt 值是可执行文件的绝对路径——必须存在、是普通文件、可执行，
        且**不在 agent 工作目录或 data_dir 内**（method_policy 只按 basename 比对
        白名单，agent 在自己工作目录放个同名恶意脚本即可过审，故路径必须在
        agent 可写范围之外）。
        Gaussian：值是 external="..." 路由关键字的引擎名——写入前用
        method_policy 的引擎值词法（valid_external_engine_value）校验，写出的 token
        必须能被策略层解析回同一个值，畸形值直接拒绝。
        """
        value = (user_input.external_program or "").strip()
        if user_input.engine == "gaussian":
            from cloudra.runtime_v2.method_policy import valid_external_engine_value

            if not valid_external_engine_value(value):
                return (
                    f"external_program {value!r} is not a valid Gaussian external engine value: "
                    "only a single [a-z0-9_.-] token is accepted (e.g. 'mace'); values with "
                    "spaces, quotes or shell characters would bypass method-policy parsing."
                )
            user_input.external_program = value
            return None

        # ORCA ProgExt 可执行文件
        path = Path(value).expanduser()
        if not path.is_absolute():
            return f"external_program {value!r} must be an absolute executable path for ORCA."
        path = path.resolve()
        if not path.exists() or not path.is_file():
            return (
                f"external_program {value!r} does not resolve to an existing regular file "
                f"(resolved: {path}). Point it at the installed MLIP executable."
            )
        if not os.access(path, os.X_OK):
            return f"external_program {value!r} is not executable (resolved: {path})."
        from cloudra.infra.config import get_config

        workdir = Path(
            getattr(self.subagent, "working_directory", None) or os.getcwd()
        ).resolve()
        data_dir = Path(get_config().data_dir).resolve()
        for root in (workdir, data_dir):
            try:
                path.relative_to(root)
            except ValueError:
                continue
            return (
                f"external_program {value!r} resolves to {path}, which is inside {root} — "
                "agent-writable locations are not trusted as external executables "
                "(method-policy matches on the basename only). Install the engine in a "
                "system location and reference that path."
            )
        user_input.external_program = str(path)
        return None

    @staticmethod
    def _coordinate_lines(mol) -> str:
        """Render coordinates only at the native input-writing boundary."""
        if not all(math.isfinite(value) for position in mol.GetConformer().GetPositions() for value in position):
            raise ValueError("Source coordinates must be finite numbers")
        return "\n".join(to_xyz(mol).splitlines()[2:])

    @staticmethod
    def _smiles_molecule(user_input: QmInputWriter_input_schema, artifact_dir: str):
        """SMILES 源：保留共享构建器返回的分子，不从导出文件重建。

        单组分量化优化可接收成功嵌入的粗种子，力场资格仍如实保留为失败态。
        其他任务与多组分继续要求共享构建器的候选资格。
        """
        source_mol = Chem.MolFromSmiles(user_input.source_value)
        if source_mol is None:
            raise ValueError(f"Invalid SMILES string: {user_input.source_value}")
        prepared = prepare_structure(PreparationRequest(
            structure=StructureInput(kind="molecule", value=source_mol),
            output_dir=artifact_dir,
            total_charge=total_charge(source_mol) if user_input.charge is None else user_input.charge,
            multiplicity=user_input.multiplicity,
            electronic_character=user_input.electronic_character,
            strategy=BuildStrategy(name="per_component", embed=True, optimize=True),
        ))
        if prepared.status == "ok" and prepared.has_coordinates:
            mol = prepared.mol
        elif (
            prepared.status in {"missing_parameters", "optimization_failed"}
            and len(prepared.components) == 1
            and prepared.components[0].embed_status == "embedded"
            and prepared.components[0].optimization_status in {"missing_parameters", "not_converged", "failed"}
            and intent_from_writer(user_input.model_dump()).tasks & {"minimum_opt", "ts_opt"}
        ):
            mol = prepared.components[0].mol
        else:
            raise StructureBuildRefused(
                prepared.status, prepared.message, list(prepared.diagnostics),
                prepared.artifact_path,
            )
        positions = mol.GetConformer().GetPositions()
        if mol.GetNumAtoms() > 1 and not positions.any():
            raise ValueError("Embedded coordinates are all-zero placeholders")
        seed_note = ""
        if prepared.status != "ok":
            seed_note = (
                f" Unoptimized seed (build status: {prepared.status}): {prepared.message} "
                f"Build artifacts: {prepared.artifact_path}"
            )
        return mol, seed_note

    @staticmethod
    def _get_molecule(user_input: QmInputWriter_input_schema, artifact_dir: str):
        """Read or build a molecule; coordinate files remain an output boundary."""
        if user_input.source_type == "smiles":
            return QmInputWriter._smiles_molecule(user_input, artifact_dir)

        fmt = "xyz" if user_input.source_type == "xyz_file" else "mol"
        try:
            mol = read_molecule(input_path=user_input.source_value, input_format=fmt, charge=user_input.charge)
        except FileNotFoundError:
            raise
        except Exception as exc:
            hint = ("If it contains an MDL MOL block, use source_type='mol_file'." if fmt == "xyz" else
                    "Provide an MDL MOL file or use source_type='xyz_file' for XYZ coordinates.")
            raise ValueError(
                f"{fmt.upper()} source could not be read: {exc}. {hint}"
            ) from exc
        return mol, ""

    @staticmethod
    def _build_link0(user_input: QmInputWriter_input_schema) -> str:
        """拼装 Link0 段。"""
        parts = []
        link0_map = {
            "chk": user_input.chk_name,
            "rwf": user_input.rwf_name,
            "fchk": user_input.fchk_name,
            "nproc": user_input.nproc,
            "mem": user_input.mem,
        }
        for key, value in link0_map.items():
            if value:
                parts.append(f"%{key}={value}")
        return "\n".join(parts)

    @staticmethod
    def _gaussian_scan_refusal(task_type: list[dict]) -> Optional[dict]:
        """Gaussian scan 语义门禁：裸 scan 是刚性扫描，ORCA 的 scan 是松弛扫描
        （Opt + %geom Scan），同一 task_type 在两引擎语义不同。只接受显式
        {'scan': 'rigid'} 声明；其余取值拒绝并给出可执行的替代声明路径。
        拒绝时返回 {"message", "unapplied_options"}，放行返回 None。
        """
        for task in task_type:
            for key, value in task.items():
                if str(key).lower() != "scan":
                    continue
                declared = str(value).strip().lower() if value is not None else ""
                if declared == "rigid":
                    continue
                return {
                    "message": (
                        "a Gaussian 'scan' task writes the bare `scan` route, which is a RIGID "
                        "potential-surface scan. RELAXED scans use structured scan_prepare coordinates. Declare the "
                        "intent explicitly: use {'scan': 'rigid'} for a Gaussian rigid scan (scan "
                        "coordinate via end_setting, e.g. 'B 1 2 S 10 0.02'); for a relaxed scan use "
                        "ts_guess mode='scan_prepare' with structured coordinates, or a Gaussian "
                        "opt=modredundant route via {'opt': 'modredundant'} + end_setting."
                    ),
                    "unapplied_options": [
                        f"scan: bare Gaussian scan is rigid (ORCA scan is relaxed); value {value!r} "
                        "is not an explicit 'rigid' declaration"
                    ],
                }
        return None

    @staticmethod
    def _build_route(user_input: QmInputWriter_input_schema) -> str:
        """拼装 Route 段。"""
        keywords = ["#p"]

        for task in user_input.task_type:
            for key, value in task.items():
                key_l = key.lower()
                if key_l == "single_point":
                    # 规范词汇映射到 Gaussian 原生 sp 关键字（validate 已放行两种拼写）
                    key_l = "sp"
                if key_l == "scan" and str(value).strip().lower() == "rigid":
                    # 显式刚性扫描声明：写裸 scan 路由（扫描坐标在 end_setting 给出），
                    # 'rigid' 是语义声明而不是 Gaussian 路由参数，不能写成 scan=rigid
                    keywords.append("scan")
                elif key_l == "freq" and user_input.frequency_mode != "auto":
                    mode = "numer" if user_input.frequency_mode == "numeric" else "analytic"
                    keywords.append(f"freq={mode}")
                elif value is None:
                    keywords.append(key_l)
                elif "," in str(value):
                    keywords.append(f"{key_l}=({value})")
                else:
                    keywords.append(f"{key_l}={value}")

        if user_input.external_program:
            # Gaussian 外部 MLIP 路由：external="engine"，无 method/basis
            keywords.append(f'external="{user_input.external_program}"')
        elif user_input.basis_set:
            keywords.append(f"{user_input.method}/{gaussian_basis_keyword(user_input.basis_set)}")
        else:
            # 半经验方法（pm6/am1/pm7 等）无基组：空 basis 不能再拼出 "pm6/" 尾斜杠。
            keywords.append(user_input.method)

        if user_input.keywords:
            keywords.append(user_input.keywords)

        return " ".join(keywords)

    # ------------------------------------------------------------------
    # ORCA 输入生成
    # ------------------------------------------------------------------

    @staticmethod
    def _orca_memory_mb(mem: str) -> float:
        """显式解析当前支持的总内存单位；非法值不能静默省略 %maxcore。"""
        text = mem.strip().lower()
        for unit, multiplier in (("gb", 1024), ("mb", 1), ("g", 1024), ("m", 1)):
            if not text.endswith(unit):
                continue
            number = text[:-len(unit)].strip()
            integer, dot, fraction = number.partition(".")
            digits = integer + fraction
            if (
                not integer or (dot and not fraction)
                or not digits.isascii() or not digits.isdecimal()
            ):
                break
            amount = float(number) * multiplier
            if math.isfinite(amount) and amount > 0:
                return amount
            break
        raise ValueError(
            f"ORCA mem {mem!r} must be a positive finite amount in MB/GB (or M/G), "
            "for example '4096MB' or '4GB'"
        )

    @staticmethod
    def _orca_resource_lines(mem: str, nproc: int) -> list[str]:
        """ORCA uses MB per process; keep the existing total-budget division."""
        mb = QmInputWriter._orca_memory_mb(mem)
        per_core = max(256, int(mb / nproc))
        return [f"%pal nprocs {nproc} end", f"%maxcore {per_core}"]

    @staticmethod
    def _orca_task_keywords(task_type: list[dict], frequency_mode: str = "auto") -> list[str]:
        """严格任务归一化：只翻译已支持的键；无法实现的选项在
        validate_writer_request 阶段已经报错，这里不会静默丢弃。"""
        keywords: list[str] = []
        for task in task_type:
            for key, value in task.items():
                key_l = key.lower()
                params = str(value).lower() if value is not None else ""
                if key_l == "opt":
                    keyword = "OptTS" if "ts" in {p.strip() for p in params.split(",")} else "Opt"
                elif key_l == "freq":
                    numeric = frequency_mode == "numeric" or params.strip() in {
                        "num", "numer", "numeric", "numfreq",
                    }
                    keyword = "NumFreq" if numeric else "Freq"
                elif key_l == "irc":
                    keyword = "IRC"
                elif key_l in ("sp", "single_point"):
                    continue  # 单点：! 行只留方法/基组
                else:
                    continue  # 前置校验已拒绝未知键，这里只是防御
                if keyword not in keywords:
                    keywords.append(keyword)
        return keywords

    @staticmethod
    def _external_method_block(user_input: QmInputWriter_input_schema) -> str:
        if not user_input.external_program:
            return ''
        block = f'%method\n  ProgExt "{user_input.external_program}"\n'
        if user_input.external_params:
            block += f'  Ext_Params "{user_input.external_params}"\n'
        return block + 'end'

    @staticmethod
    def _written_calculation(user_input: QmInputWriter_input_schema) -> QmCalculation:
        values = user_input.model_dump(include=set(QmCalculation.model_fields))
        if user_input.external_program:
            if user_input.engine == 'orca':
                values['orca_blocks'] = '\n'.join(filter(None, [
                    QmInputWriter._external_method_block(user_input), user_input.orca_blocks]))
            else:
                values['keywords'] = ' '.join(filter(None, [
                    f'external="{user_input.external_program}"', user_input.keywords]))
        return QmCalculation.model_validate(values)

    @staticmethod
    def _build_orca_input(user_input: QmInputWriter_input_schema, mol) -> str:
        """拼装 ORCA .inp：! 行 + %pal/%maxcore（+%method 外部势块）+ 坐标块。"""
        simple = QmInputWriter._orca_task_keywords(user_input.task_type, user_input.frequency_mode)
        method_block = ""
        if user_input.external_program:
            # 外部 MLIP 路由：ExtOpt 把能量/梯度交给外部程序，输入不含
            # method/basis（外部势没有基组概念），GH #16
            simple.insert(0, "ExtOpt")
            method_block = QmInputWriter._external_method_block(user_input)
        else:
            if user_input.method:
                simple.append(user_input.method)
            if user_input.basis_set:
                simple.append(orca_basis_keyword(user_input.basis_set))
        if user_input.keywords:
            simple.append(user_input.keywords)

        lines = []
        default_title = QmInputWriter_input_schema.model_fields["title"].default
        if user_input.title and user_input.title != default_title:
            lines.append(f"# {user_input.title}")
        if user_input.source_type == "smiles":
            lines.append(
                f"# expected_smiles: {user_input.source_value} "
                "(user-declared expectation; NOT an evidence-verified identity)"
            )
        lines.append("! " + " ".join(simple))
        lines.extend(QmInputWriter._orca_resource_lines(user_input.mem, user_input.nproc))
        if method_block:
            lines.append(method_block)
        if user_input.orca_blocks:
            lines.append(user_input.orca_blocks.strip())

        lines.append(f"* xyz {total_charge(mol)} {user_input.multiplicity}")
        lines.append(QmInputWriter._coordinate_lines(mol))
        lines.append("*")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _build_gjf(user_input: QmInputWriter_input_schema, mol) -> str:
        """拼装完整的 .gjf 文本。

        Gaussian 要求坐标块后有一个空行作为输入结束标记，
        因此末尾统一保留一个空行。
        """
        link0 = QmInputWriter._build_link0(user_input)
        route = QmInputWriter._build_route(user_input)
        title = user_input.title
        if user_input.source_type == "smiles":
            # provenance：声明的期望身份，不是证据验证过的身份（GH 协议：
            # 只有 evidence 绑定能证明身份，写注释不产生 verified 标签）
            title = (
                f"{title} | expected_smiles: {user_input.source_value} "
                "(unverified expectation)"
            )

        sections = [
            link0,
            route,
            "",                    # Route 后空行
            title,
            "",                    # Title 后空行
            f"{total_charge(mol)} {user_input.multiplicity}",
            QmInputWriter._coordinate_lines(mol),
            "",                    # 坐标后空行（Gaussian 输入结束标记）
        ]

        if user_input.end_setting:
            # 在结束空行之前插入自定义设置及其后的空行
            sections.insert(-1, user_input.end_setting)
            sections.insert(-1, "")

        return "\n".join(sections) + "\n"

    async def tool_call(self, user_input: QmInputWriter_input_schema, session: Session) -> QmInputWriter_output_schema:
        if not _RDKIT_AVAILABLE:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="RDKit is not installed; cannot generate the input file. "
                        "Install it with: pip install 'cloudra[chem]', then retry."
            )
        if user_input.engine == "orca":
            try:
                self._orca_memory_mb(user_input.mem)
            except ValueError as exc:
                return QmInputWriter_output_schema(
                    is_success=False,
                    message=f"qm_input_writer refused: {exc}",
                    unapplied_options=[str(exc)],
                )
        # 外部 MLIP 路由的参数校验（fail-loud，不静默吞掉配错的字段）
        if user_input.external_params and not user_input.external_program:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="external_params requires external_program: the Ext_Params string is only "
                        "meaningful together with a ProgExt executable. Set external_program, then retry.",
            )
        if user_input.external_params and user_input.engine == "gaussian":
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="external_params is ORCA-only; for the Gaussian external route the engine "
                        "value goes into external_program (e.g. external_program='mace').",
            )
        # 外部程序本身的安全校验：ORCA 可执行路径必须在 agent 可写范围之外，
        # Gaussian 引擎值必须能被 method_policy 词法解析（防白名单绕过）。
        if user_input.external_program:
            ext_error = await asyncio.to_thread(self._validate_external_program, user_input)
            if ext_error:
                return QmInputWriter_output_schema(
                    is_success=False,
                    input_path="",
                    message=f"qm_input_writer refused: {ext_error}",
                )
        # Gaussian scan 语义门禁：裸 scan 是刚性扫描，ORCA 侧是松弛扫描
        # （Opt + %geom Scan），同一 task_type 两引擎不同义且 inspect_input
        # 检不出差异——必须显式 {'scan': 'rigid'} 声明。
        if user_input.engine == "gaussian":
            scan_refusal = self._gaussian_scan_refusal(user_input.task_type)
            if scan_refusal:
                return QmInputWriter_output_schema(
                    is_success=False,
                    input_path="",
                    message=f"qm_input_writer refused: {scan_refusal['message']}",
                    unapplied_options=scan_refusal["unapplied_options"],
                )
        # Validate request semantics before SMILES embedding or coordinate
        # optimization, both of which can take minutes for an invalid job.
        conflicts = validate_writer_request(user_input.model_dump())
        if conflicts:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="qm_input_writer refused: " + " | ".join(
                    f"[{c['code']}] {c['message']}" for c in conflicts
                ),
                unapplied_options=[c["message"] for c in conflicts],
            )
        # 成功写出时在 interpreted_intent 里显式记录 scan 的刚性/松弛语义
        scan_semantics = None
        for task in user_input.task_type:
            if any(str(key).lower() == "scan" for key in task):
                scan_semantics = "rigid" if user_input.engine == "gaussian" else "relaxed"
                break
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱），绝对路径
        # 保持既有权限语义。SMILES 源不经过路径解析（绝不把 SMILES 当路径）。
        if user_input.source_type in ("xyz_file", "mol_file"):
            user_input.source_value = await asyncio.to_thread(resolve_tool_path, self, user_input.source_value)
        user_input.output_path = await asyncio.to_thread(resolve_tool_path, self, user_input.output_path)
        if user_input.artifact_dir:
            user_input.artifact_dir = await asyncio.to_thread(resolve_tool_path, self, user_input.artifact_dir)
        else:
            base = os.path.dirname(user_input.output_path)
            stem = os.path.splitext(os.path.basename(user_input.output_path))[0]
            # 与 smiles_to_mol / conformer_search 同一命名规则：<父目录>/structure_build/<stem>/
            user_input.artifact_dir = build_artifact_dir(base or ".", stem)
        try:
            # 结构构建是重活（Embed/优化），离开事件循环线程
            mol, seed_note = await asyncio.to_thread(
                self._get_molecule, user_input, user_input.artifact_dir
            )
            if user_input.engine == "orca":
                content = self._build_orca_input(user_input, mol)
                engine_label = "ORCA"
                generation_path = "orca:simple+orca_blocks"
            else:
                content = self._build_gjf(user_input, mol)
                engine_label = "Gaussian"
                generation_path = "gaussian:route"

            # 不信 writer 自述：从生成文本重新 inspect，任务集合不一致即失败。
            inspected = inspect_input(content, engine=user_input.engine)
            interpreted = inspected.model_dump(mode="json")
            if scan_semantics is not None:
                interpreted["scan_semantics"] = scan_semantics
            requested = intent_from_writer(user_input.model_dump())
            if inspected.tasks != requested.tasks:
                return QmInputWriter_output_schema(
                    is_success=False,
                    input_path="",
                    message=(
                        "qm_input_writer internal mismatch: the generated file encodes "
                        f"tasks {sorted(inspected.tasks)} but {sorted(requested.tasks)} "
                        "were requested; no file was written."
                    ),
                    interpreted_intent=interpreted,
                    unapplied_options=sorted(requested.tasks - inspected.tasks),
                )

            limitation = seed_note
            if "ts_opt" in inspected.tasks and inspected.constraints:
                limitation += (
                    " NOTE: this input keeps constraints during a TS optimization; "
                    "the result may only be claimed as a CONSTRAINED saddle point, "
                    "not a full-space transition state."
                )

            parent_dir = os.path.dirname(user_input.output_path)
            if parent_dir:
                try:
                    await asyncio.to_thread(os.makedirs, parent_dir, exist_ok=True)
                except FileExistsError:
                    # exist_ok=True 仍会在叶子已存在且不是目录时炸 Errno 17——
                    # 必须翻译成有指引的报错，不把裸 errno 抛给调用方
                    return QmInputWriter_output_schema(
                        is_success=False,
                        input_path="",
                        message=(
                            f"Cannot create the output directory {parent_dir}: a non-directory "
                            "file already exists at that path. Choose a different output_path, "
                            "or remove the conflicting file, then retry."
                        ),
                    )
            input_path = user_input.output_path

            # 同路径重复生成：内容逐字节相同 → 幂等复用；不同 → fail-loud 给指引，
            # 绝不静默覆盖一份来源不明的既有文件。
            if await asyncio.to_thread(os.path.isfile, input_path):
                existing = await asyncio.to_thread(Path(input_path).read_bytes)
                if existing == content.encode("utf-8"):
                    return QmInputWriter_output_schema(
                        is_success=True,
                        input_path=input_path,
                        message=(
                            f"{engine_label} input file already exists with identical content; "
                            f"reused it as-is.{limitation}"
                        ),
                        interpreted_intent=interpreted,
                        calculation=self._written_calculation(user_input),
                        unapplied_options=[],
                        generation_path=generation_path,
                    )
                return QmInputWriter_output_schema(
                    is_success=False,
                    input_path="",
                    message=(
                        f"Refused to overwrite {input_path}: a file already exists there with "
                        "different content. Choose a different output_path, or delete the "
                        "existing file first, then retry."
                    ),
                )

            await asyncio.to_thread(atomic_write_text, input_path, content)

            return QmInputWriter_output_schema(
                is_success=True,
                input_path=input_path,
                message=f"{engine_label} input file generated successfully.{limitation}",
                interpreted_intent=interpreted,
                calculation=self._written_calculation(user_input),
                unapplied_options=[],
                generation_path=generation_path,
            )
        except StructureBuildRefused as e:
            details = " | ".join(e.diagnostics) if e.diagnostics else e.message
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=(
                    f"qm_input_writer refused to write the file: the SMILES source could not be "
                    f"turned into a usable structure (build status: {e.status}). {e.message}"
                    + (f" Diagnostics: {details}" if details and details != e.message else "")
                    + f" Build artifacts: {e.artifact_path}"
                ),
            )
        except FileNotFoundError as e:
            missing = e.filename or user_input.source_value
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Coordinate source file not found: {missing}. "
                        "Check the path, or generate the structure first with smiles_to_mol / format_converter."
            )
        except FileExistsError as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Output path conflict: {e.filename or user_input.output_path} already exists "
                        "and cannot be created as a directory. Choose a different output_path, "
                        "or remove the conflicting file, then retry."
            )
        except ValueError as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Invalid input for qm_input_writer: {str(e)}. "
                        "Check that the SMILES is valid or that the source file matches source_type, then retry."
            )
        except Exception as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Failed to generate the {user_input.engine.upper()} input file: {str(e)}. "
                        "Verify the coordinate source and output path, then retry."
            )
