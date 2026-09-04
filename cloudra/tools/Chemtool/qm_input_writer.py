import os
from typing import Any, Literal, Optional

from pydantic import Field

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    AllChem = None
    _RDKIT_AVAILABLE = False

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.calculation_intent import (
    inspect_input,
    intent_from_writer,
    validate_writer_request,
)

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


class QmInputWriter_input_schema(input_schema):
    engine: Literal["gaussian", "orca"] = Field(
        default="gaussian",
        description="Target QM program. 'gaussian': write a .gjf (submit with job_type='gaussian'); "
                    "'orca': write a .inp (submit with job_type='orca'). "
                    "method/basis/task_type map onto each program's input syntax automatically.",
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
                    "when source_type='xyz_file' or 'mol_file', the file's absolute path."
    )
    method: str = Field(
        default="b3lyp",
        description="Electronic-structure method, e.g. 'b3lyp', 'hf', 'mp2', 'wb97xd', 'pbe0' "
                    "(written as-is; ORCA expects e.g. 'wB97X-V', Gaussian 'wb97xd'). "
                    "Ignored when external_program is set (external potentials carry no method/basis)."
    )
    basis_set: str = Field(
        default="6-31g(d)",
        description="Basis set, e.g. '6-31g(d)', '6-311+g(d,p)', 'def2tzvp', 'cc-pvdz'. "
                    "Empty string selects the no-basis branch (semi-empirical / external). "
                    "Ignored when external_program is set."
    )
    external_program: Optional[str] = Field(
        default=None,
        description="External MLIP route (replaces method/basis_set). ORCA: absolute path of the "
                    "ProgExt executable — emits '! ExtOpt <tasks>' plus a %method ProgExt block, "
                    "e.g. '/opt/conda/envs/chemai/bin/mace'. Gaussian: engine value of the "
                    "external=\"...\" route keyword, e.g. 'mace' (may include program arguments)."
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
                    Gaussian example: [{"opt":"TS,calcfc,noeigen"},{"freq":None}];
                    the same dict works for ORCA (mapped to `! OptTS Freq` etc.).'''
    )
    frequency_mode: Literal["auto", "analytic", "numeric"] = Field(
        default="auto",
        description="Frequency evaluation mode. ORCA: 'numeric' with task_type=[{'freq':None}] "
                    "emits NumFreq (required for external potentials); 'analytic'/'auto' emit Freq. "
                    "Rejected when no frequency task is requested.",
    )

    charge: int = Field(
        default=0,
        description="Molecular charge."
    )
    multiplicity: int = Field(
        default=1,
        description="Spin multiplicity. Singlet=1, doublet=2, triplet=3."
    )
    mem: str = Field(
        default="4GB",
        description="TOTAL memory for the whole job, e.g. '4GB', '8GB'. Gaussian writes %mem "
                    "verbatim (a total); ORCA writes %maxcore = mem/nproc because ORCA maxcore "
                    "is a PER-CORE value. Request memory_mb equal to this total when submitting."
    )
    nproc: int = Field(
        default=4,
        description="Number of CPU cores for parallel compute (Gaussian %nprocshared / ORCA %pal)."
    )
    extra_keywords: Optional[str] = Field(
        default=None,
        description="Extra route keywords appended verbatim. Gaussian: 'scrf=(solvent=water)', "
                    "'empiricaldispersion=gd3bj'; ORCA: 'D3BJ', 'CPCM(water)' (goes onto the `!` line)."
    )
    orca_blocks: Optional[str] = Field(
        default=None,
        description="ORCA-only: raw % block lines inserted between the `!` line and the coordinate "
                    "block, e.g. '%geom MaxIter 200 end'. Ignored for engine='gaussian'."
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
    output_dir: str = Field(
        description="Absolute path of the .gjf file (including filename)."
    )
    chk_name: Optional[str] = Field(
        default=None,
        description="chk filename, e.g. H2O.chk. By convention point it into the same directory "
                    "as output_dir (absolute path preferred): the per-task Gaussian scratch is "
                    "deleted after the run, so a checkpoint outside the .gjf directory is lost."
    )
    rwf_name: Optional[str] = Field(
        default=None,
        description="rwf filename; Gaussian scratch file, often large."
    )
    fchk_name: Optional[str] = Field(
        default=None,
        description="fchk filename. Same placement convention as chk_name: same directory as "
                    "output_dir, absolute path preferred."
    )


class QmInputWriter_output_schema(output_schema):
    is_success: bool = Field(description="Whether the file was generated")
    input_path: str = Field(default="", description="Absolute path of the generated input file (.gjf or .inp, per `engine`)")
    message: str = Field(default="", description="Status or error message")
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

    @staticmethod
    def _get_coordinates(source_type: str, source_value: str) -> str:
        """根据来源类型返回 Gaussian 格式的坐标文本。"""
        if source_type == "smiles":
            mol = Chem.MolFromSmiles(source_value)
            if mol is None:
                raise ValueError(f"Could not parse a molecule from SMILES: {source_value}")
            mol = Chem.AddHs(mol)
            AllChem.EmbedMolecule(mol, randomSeed=42)
            AllChem.MMFFOptimizeMolecule(mol)
            xyz_block = Chem.MolToXYZBlock(mol)
            # XYZ 格式前两行为原子数与标题，从第三行开始为坐标
            return "\n".join(xyz_block.strip().split("\n")[2:])

        # xyz_file / mol_file 统一通过 ase 读取（惰性导入，避免拖慢工具模块加载）
        import ase.io

        atoms = ase.io.read(source_value)
        lines = []
        for symbol, position in zip(atoms.symbols, atoms.positions):
            x, y, z = position
            lines.append(f"{symbol:<4} {x:>14.8f} {y:>14.8f} {z:>14.8f}")
        return "\n".join(lines)

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
    def _build_route(user_input: QmInputWriter_input_schema) -> str:
        """拼装 Route 段。"""
        keywords = ["#p"]

        for task in user_input.task_type:
            for key, value in task.items():
                if key.lower() == "freq" and user_input.frequency_mode != "auto":
                    mode = "numer" if user_input.frequency_mode == "numeric" else "analytic"
                    keywords.append(f"freq={mode}")
                elif value is None:
                    keywords.append(key)
                elif "," in str(value):
                    keywords.append(f"{key}=({value})")
                else:
                    keywords.append(f"{key}={value}")

        if user_input.external_program:
            # Gaussian 外部 MLIP 路由：external="engine"，无 method/basis
            keywords.append(f'external="{user_input.external_program}"')
        elif user_input.basis_set:
            keywords.append(f"{user_input.method}/{user_input.basis_set}")
        else:
            # 半经验方法（pm6/am1/pm7 等）无基组：空 basis 不能再拼出 "pm6/" 尾斜杠。
            keywords.append(user_input.method)

        if user_input.extra_keywords:
            keywords.append(user_input.extra_keywords)

        return " ".join(keywords)

    # ------------------------------------------------------------------
    # ORCA 输入生成
    # ------------------------------------------------------------------

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
                elif key_l == "scan":
                    # 松弛扫描由 orca_blocks 的 %geom Scan 定义驱动，仍需 Opt 关键字
                    keyword = "Opt"
                elif key_l == "sp":
                    continue  # 单点：! 行只留方法/基组
                else:
                    continue  # 前置校验已拒绝未知键，这里只是防御
                if keyword not in keywords:
                    keywords.append(keyword)
        return keywords

    @staticmethod
    def _build_orca_input(user_input: QmInputWriter_input_schema, coords: str) -> str:
        """拼装 ORCA .inp：! 行 + %pal/%maxcore（+%method 外部势块）+ 坐标块。"""
        simple = QmInputWriter._orca_task_keywords(user_input.task_type, user_input.frequency_mode)
        method_block = ""
        if user_input.external_program:
            # 外部 MLIP 路由：ExtOpt 把能量/梯度交给外部程序，输入不含
            # method/basis（外部势没有基组概念），GH #16
            simple.insert(0, "ExtOpt")
            method_block = f'%method\n  ProgExt "{user_input.external_program}"\n'
            if user_input.external_params:
                method_block += f'  Ext_Params "{user_input.external_params}"\n'
            method_block += "end"
        else:
            if user_input.method:
                simple.append(user_input.method)
            if user_input.basis_set:
                simple.append(user_input.basis_set)
        if user_input.extra_keywords:
            simple.append(user_input.extra_keywords)

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
        lines.append(f"%pal nprocs {user_input.nproc} end")

        # %maxcore 按核均分（ORCA 语义是每核 MB）；mem 解析失败则不写
        import re as _re

        m = _re.match(r"^\s*(\d+(?:\.\d+)?)\s*([GgMm][Bb]?)\s*$", user_input.mem or "")
        if m:
            amount = float(m.group(1))
            mb = amount * 1024 if m.group(2).lower().startswith("g") else amount
            per_core = max(256, int(mb / max(1, user_input.nproc)))
            lines.append(f"%maxcore {per_core}")
        if method_block:
            lines.append(method_block)
        if user_input.orca_blocks:
            lines.append(user_input.orca_blocks.strip())

        lines.append(f"* xyz {user_input.charge} {user_input.multiplicity}")
        lines.append(coords)
        lines.append("*")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _build_gjf(user_input: QmInputWriter_input_schema, coords: str) -> str:
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
            f"{user_input.charge} {user_input.multiplicity}",
            coords,
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
                message="external_params is ORCA-only; for the Gaussian external route fold program "
                        "arguments into external_program (e.g. external_program='mace --model x.model').",
            )
        try:
            coords = self._get_coordinates(user_input.source_type, user_input.source_value)
            # 输入冲突前置校验：无法实现的选项明确报错，绝不写出看似成功
            # 的计算文件（成功时 unapplied_options 必为空）。
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
            if user_input.engine == "orca":
                content = self._build_orca_input(user_input, coords)
                engine_label = "ORCA"
                generation_path = "orca:simple+orca_blocks"
            else:
                content = self._build_gjf(user_input, coords)
                engine_label = "Gaussian"
                generation_path = "gaussian:route"

            # 不信 writer 自述：从生成文本重新 inspect，任务集合不一致即失败。
            inspected = inspect_input(content, engine=user_input.engine)
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
                    interpreted_intent=inspected.model_dump(mode="json"),
                    unapplied_options=sorted(requested.tasks - inspected.tasks),
                )

            limitation = ""
            if "ts_opt" in inspected.tasks and inspected.constraints:
                limitation = (
                    " NOTE: this input keeps constraints during a TS optimization; "
                    "the result may only be claimed as a CONSTRAINED saddle point, "
                    "not a full-space transition state."
                )

            output_dir = os.path.dirname(user_input.output_dir)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            input_path = user_input.output_dir

            atomic_write_text(input_path, content)

            return QmInputWriter_output_schema(
                is_success=True,
                input_path=input_path,
                message=f"{engine_label} input file generated successfully.{limitation}",
                interpreted_intent=inspected.model_dump(mode="json"),
                unapplied_options=[],
                generation_path=generation_path,
            )
        except FileNotFoundError as e:
            missing = e.filename or user_input.source_value
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Coordinate source file not found: {missing}. "
                        "Check the path, or generate the structure first with smiles_to_mol / format_converter."
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
                message=f"Failed to generate the Gaussian input file: {str(e)}. "
                        "Verify the coordinate source and output path, then retry."
            )


def get_class():
    return QmInputWriter
