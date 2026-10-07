import asyncio
import os
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path

description = (
    "Convert among common computational-chemistry file formats (mol, xyz, gjf, inp (ORCA), pdb, SDF, cif, etc.) via ASE; "
    "coordinates stay in files and never appear in the return value. "
    "Also extracts key frames from a Gaussian or ORCA log (input_format='log') to CSV (output_format='csv'): "
    "optimization trajectories, scan curves, and IRC path structures/energies/reaction coordinates for programmatic analysis. "
    "Use for: converting an existing structure file (e.g. xyz→gjf, xyz→inp, cif→pdb) for downstream compute or visualization; "
    "turning IRC/scan logs into CSV for pandas and similar. "
    "Do not use for: generating an initial 3D structure from SMILES (use smiles_to_mol) or writing a Gaussian/ORCA input (use qm_input_writer)."
)


# 用户可见格式名 -> ASE 内部格式名的映射
_ASE_FORMAT_MAP = {
    "pdb": "proteindatabank",
    "gjf": "gaussian-in",
    "poscar": "vasp",
    "vasp": "vasp",
}

# 能携带化学信息的格式：必须用 RDKit 读写（保留键/形式电荷/立体），
# ASE 不存键与电荷（其 mol/sdf 读写只搬坐标，会静默丢化学信息）。
_CHEMICAL_FORMATS = {"mol", "sdf"}


def _rdkit():
    try:
        from rdkit import Chem
        return Chem
    except Exception as exc:  # pragma: no cover - 由调用方转 ImportError 消息
        raise ImportError(
            f"RDKit is required for mol/sdf conversion: {exc}. "
            "Install it with: pip install 'cloudra[chem]'"
        ) from exc


def _read_rdkit_first(path: str, fmt: str):
    """RDKit 读 mol/sdf 的第一个分子。

    返回 (mol | None, n_molecules, frame_desc)。多分子 SDF 只取第一个，
    调用方负责在 message 中披露帧数（绝不静默丢其余帧）。
    """
    Chem = _rdkit()
    if fmt == "mol":
        mol = Chem.MolFromMolFile(path, removeHs=False)
        return mol, 1, "1 molecule"
    suppl = Chem.SDMolSupplier(path, removeHs=False, sanitize=True)
    mols = [m for m in suppl if m is not None]
    if not mols:
        return None, 0, "0 molecules"
    return mols[0], len(mols), f"{len(mols)} molecules"


def _rdkit_to_ase(mol):
    """RDKit mol -> ASE Atoms（坐标面；键/电荷不跨到 ASE 语义中）。"""
    import ase

    conf = mol.GetConformer()
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]
    positions = [
        (float(conf.GetAtomPosition(i).x),
         float(conf.GetAtomPosition(i).y),
         float(conf.GetAtomPosition(i).z))
        for i in range(mol.GetNumAtoms())
    ]
    return ase.Atoms(symbols=symbols, positions=positions)


def _ase_to_rdkit_atoms_only(atoms):
    """ASE Atoms -> RDKit mol（仅原子与坐标，无键）。

    输入本身是坐标面格式（xyz/gjf/pdb/cif），无键/电荷信息可保留——
    mol/sdf 输出如实反映"只有坐标"。
    """
    Chem = _rdkit()
    mol = Chem.RWMol()
    conf = Chem.Conformer(atoms.get_global_number_of_atoms())
    positions = atoms.get_positions()
    for i, symbol in enumerate(atoms.get_chemical_symbols()):
        mol.AddAtom(Chem.Atom(symbol))
        conf.SetAtomPosition(i, tuple(map(float, positions[i])))
    out = mol.GetMol()
    out.AddConformer(conf)
    return out


def _mol_total_formal_charge(mol) -> int:
    return int(sum(a.GetFormalCharge() for a in mol.GetAtoms()))


def _mol_block(mol) -> str:
    """V2000 mol block（带键/电荷/立体）。"""
    Chem = _rdkit()
    return Chem.MolToMolBlock(mol, kekulize=True)


def _sdf_record(mol) -> str:
    return _mol_block(mol).rstrip("\n") + "\n$$$$\n"


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class FormatConverter_input_schema(input_schema):
    input_path: str = Field(
        description="Path of the input file: absolute as-is, or relative to the "
                    "Agent working directory."
    )
    input_format: Literal["mol", "xyz", "gjf", "pdb", "cif", "sdf", "log", "poscar", "vasp"] = Field(
        description="Input format. log means a Gaussian or ORCA output log (.log/.out); then output must be csv or xyz."
    )
    output_format: Literal["mol", "xyz", "gjf", "inp", "pdb", "cif", "sdf", "csv", "poscar", "vasp"] = Field(
        description="Target output format. 'inp' is an ORCA input (coordinates only, charge 0 / "
                    "multiplicity 1 — edit method/charge with qm_input_writer instead for production). "
                    "When input_format='log', output can be 'csv' (key-frame table) or 'xyz' (final optimized frame)."
    )
    output_path: str = Field(
        description="Path of the output file: absolute as-is, or relative to the "
                    "Agent working directory."
    )


class FormatConverter_output_schema(output_schema):
    is_success: bool = Field(description="Whether conversion succeeded")
    output_path: str = Field(default="", description="Absolute path of the output file")
    message: str = Field(default="", description="Status or error message")


class FormatConverter(Tool):
    tool_id: str = 't-24'
    tool_name: str = 'format_converter'
    tool_description: str = description
    input_schema: Any = FormatConverter_input_schema
    output_schema: Any = FormatConverter_output_schema

    def is_write(self) -> bool:
        return True

    @staticmethod
    def _to_ase_format(fmt: str) -> str:
        """将用户格式名映射为 ASE 可识别的格式名。"""
        return _ASE_FORMAT_MAP.get(fmt, fmt)

    @staticmethod
    def _write_orca_inp(atoms, output_path: str) -> None:
        """写 ORCA 坐标骨架（ASE 的 orca writer 不在 io 注册表中，需直接调用）。

        ASE 只写几何骨架（charge 0 / mult 1，无方法行参数）；生产输入请用
        qm_input_writer(engine='orca')。
        """
        import ase.io.orca

        params = {
            "orcasimpleinput": "",
            "orcablocks": "",
            "charge": 0,
            "mult": 1,
        }
        ase.io.orca.write_orca(output_path, atoms, params)

    @staticmethod
    def _convert_log(user_input: "FormatConverter_input_schema") -> FormatConverter_output_schema:
        """Gaussian/ORCA 日志 → 关键帧 CSV 或最终几何 XYZ。"""
        if user_input.input_format != "log":
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="output_format='csv' is only supported for log input (input_format='log'). "
                        "For structure files, choose a structure output_format instead."
            )
        if user_input.output_format not in ("csv", "xyz"):
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="When input_format='log', the output format must be 'csv' (key-frame table) or 'xyz' (final optimized frame)."
            )
        if not os.path.isfile(user_input.input_path):
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"Input file does not exist: {user_input.input_path}. "
                        "Check the path, then retry."
            )
        try:
            from cloudra.tools.core import gaussian_frames, orca_frames
            from cloudra.tools.core.gaussian_frames import frames_to_csv
            from cloudra.tools.core.qm_engine import detect_qm_engine

            # 日志全文只读一次：detect_job_types/extract_frames 都吃文本变体，
            # 不再各自独立整读大日志（detect_qm_engine 只嗅探头部 16 KiB，开销可忽略）。
            with open(user_input.input_path, encoding="utf-8", errors="replace") as fh:
                log_text = fh.read()
            engine = detect_qm_engine(user_input.input_path)
            frames_mod = orca_frames if engine == "orca" else gaussian_frames
            job_types = frames_mod.detect_job_types_from_text(log_text)
            if engine == "orca":
                frames = orca_frames.extract_frames_from_text(
                    log_text, log_path=user_input.input_path,
                )
            else:
                frames = gaussian_frames.extract_frames_from_text(log_text)
            # 按规范顺序展示（opt+ts+freq 风格，而非字母序）
            ordered = [j for j in ("opt", "ts", "freq", "scan", "irc", "sp") if j in job_types]
            if not frames:
                # 空帧必须带上**具体原因**：IRC 的路径点在边文件里、NEB 的几何在逐图像边文件里，
                # 两者都是"主输出没有但作业确实产出了几何"的情形，笼统一句"没有关键帧"没有信息量
                reason = None
                if engine == "orca":
                    reason = orca_frames.frames_unavailable_reason_from_text(
                        log_text, log_path=user_input.input_path,
                    )
                explanation = f" Reason: {reason}." if reason else (
                    " Check that the log contains a finished opt/scan job."
                )
                return FormatConverter_output_schema(
                    is_success=False,
                    output_path="",
                    message=(
                        f"No key frames could be extracted from the {engine or 'unknown'}-engine log "
                        f"(detected as {'+'.join(ordered) or 'unknown'}): {user_input.input_path}."
                        f"{explanation}"
                    ),
                )
            if user_input.output_format == "csv":
                frames_to_csv(frames, user_input.output_path)
                return FormatConverter_output_schema(
                    is_success=True,
                    output_path=user_input.output_path,
                    message=(
                        f"Detected {engine or 'unknown'} {'+'.join(ordered)}, wrote {len(frames)} "
                        f"frames from {user_input.input_path} -> {user_input.output_path}"
                    )
                )
            else:
                last_frame = frames[-1]
                xyz_text = last_frame.xyz
                if not xyz_text.endswith("\n"):
                    xyz_text += "\n"
                with open(user_input.output_path, "w", encoding="utf-8") as fh:
                    fh.write(xyz_text)
                return FormatConverter_output_schema(
                    is_success=True,
                    output_path=user_input.output_path,
                    message=(
                        f"Detected {engine or 'unknown'} {'+'.join(ordered)}, extracted final frame "
                        f"(frame {last_frame.frame}) from {user_input.input_path} -> "
                        f"{user_input.output_path}. NOTE: an extracted geometry is a coordinate "
                        "artifact only — it does not imply the source job terminated normally, and "
                        "requesting a geometry never validates frequencies/TS."
                    )
                )
        except IndexError:
            # 帧解析链路任何一环对空列表的裸索引都不能漏成 "list index out of range"——
            # 统一翻成有指引的解析失败
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"No key frames could be extracted from {user_input.input_path}: the parser "
                        "hit an empty section (the file is likely truncated or not a valid "
                        "Gaussian/ORCA computation log). Check that the job wrote a complete log; "
                        "you can also inspect it directly with log_parser.",
            )
        except Exception as e:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"Failed to process log: {str(e)}. "
                        "Check that the input is a valid computational chemistry log; "
                        "you can also read it directly with log_parser."
            )

    async def tool_call(self, user_input: FormatConverter_input_schema, session: Session) -> FormatConverter_output_schema:
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱），与
        # read/write/qm_input_writer 的契约一致。
        user_input.input_path = resolve_tool_path(self, user_input.input_path)
        user_input.output_path = resolve_tool_path(self, user_input.output_path)
        input_path = user_input.input_path
        output_path = user_input.output_path

        # 0. log 输入或 csv 输出分流（大日志帧提取是同步重活，卸载出事件循环）
        if user_input.input_format == "log" or user_input.output_format == "csv":
            return await asyncio.to_thread(self._convert_log, user_input)

        # 1. 校验输入文件是否存在
        if not os.path.isfile(input_path):
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"Input file does not exist: {input_path}. "
                        "Check the path, or generate the structure first with smiles_to_mol, then retry."
            )

        # 2. 校验输入/输出格式是否相同
        if user_input.input_format == user_input.output_format:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="Input and output formats are identical; no conversion is needed."
            )

        try:
            import ase.io

            ase_input_fmt = self._to_ase_format(user_input.input_format)
            ase_output_fmt = self._to_ase_format(user_input.output_format)

            chem_input = user_input.input_format in _CHEMICAL_FORMATS
            chem_output = user_input.output_format in _CHEMICAL_FORMATS

            # 3. 读取输入
            # mol/sdf 走 RDKit（保留键/形式电荷/立体）；其余走 ASE 坐标面。
            # 多帧/多分子输入明确取第一帧并在 message 披露（不静默丢帧）。
            frame_note = ""
            if chem_input:
                mol, n_frames, desc = _read_rdkit_first(input_path, user_input.input_format)
                if mol is None:
                    return FormatConverter_output_schema(
                        is_success=False,
                        output_path="",
                        message=f"RDKit could not read a structure from {input_path} "
                                f"(input_format='{user_input.input_format}'). "
                                "Check that the file is a valid MOL/SDF with at least one molecule.",
                    )
                if n_frames > 1:
                    frame_note = (
                        f"Input {user_input.input_format} contains {n_frames} frames/molecules; "
                        "only the first one was converted."
                    )
            else:
                # 单次惰性扫描：只物化第一帧（整条轨迹物化既耗内存也只用首帧），
                # 帧数仍在同一趟扫描里数出，message 如实披露"取第一帧"。
                atoms = None
                n_frames = 0
                for frame in ase.io.iread(input_path, format=ase_input_fmt):
                    n_frames += 1
                    if atoms is None:
                        atoms = frame
                if atoms is None:
                    return FormatConverter_output_schema(
                        is_success=False,
                        output_path="",
                        message=f"Could not read a structure from {input_path}. "
                                f"Check that the file content matches input_format='{user_input.input_format}'."
                    )
                if n_frames > 1:
                    frame_note = (
                        f"Input {user_input.input_format} contains {n_frames} coordinate frames; "
                        "only the first one was converted."
                    )

            # 4. 确保输出目录存在并写入
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # 5. 按"能否携带化学信息"选择书写引擎
            if chem_output:
                # 输出 mol/sdf 必须保留化学信息：RDKit 侧须有真实分子对象
                if chem_input:
                    out_mol = mol
                    charge_note = ""
                else:
                    # 坐标面输入（xyz/pdb/cif/gjf...）本身无键/电荷/立体；
                    # 转出 mol/sdf 只有坐标，如实写入并在 message 披露。
                    out_mol = _ase_to_rdkit_atoms_only(atoms)
                    charge_note = (
                        f"Input {user_input.input_format} carries only coordinates (no bond/charge/"
                        "stereochemistry), so the MOL/SDF output contains atoms+coordinates only."
                    )
                text = _sdf_record(out_mol) if user_input.output_format == "sdf" else _mol_block(out_mol)
                _write_text(output_path, text)
            else:
                # 输出为坐标面格式：几何从 RDKit mol（若输入是化学格式）或 ASE 直出
                if chem_input:
                    atoms = _rdkit_to_ase(mol)
                    charge = _mol_total_formal_charge(mol)
                    if user_input.output_format in ("gjf", "inp") and charge != 0:
                        charge_note = (
                            f"Input carries formal charge {charge:+d}; the {user_input.output_format} "
                            "output records only coordinates (charge/multiplicity are not written here) — "
                            "re-declare the charge with qm_input_writer for production inputs."
                        )
                    else:
                        charge_note = ""
                else:
                    charge_note = ""
                if user_input.output_format == "inp":
                    self._write_orca_inp(atoms, output_path)
                else:
                    if ase_output_fmt == "vasp" and (atoms.cell is None or atoms.cell.volume == 0):
                        atoms.center(vacuum=10.0)
                    ase.io.write(output_path, atoms, format=ase_output_fmt)

            notes = " ".join(note for note in (frame_note, charge_note) if note)
            message = f"Converted {user_input.input_format} to {user_input.output_format}: {output_path}"
            if notes:
                message += f" NOTE: {notes}"
            return FormatConverter_output_schema(
                is_success=True,
                output_path=output_path,
                message=message,
            )

        except FileNotFoundError as e:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"File not found during conversion: {e.filename or input_path}. "
                        "Check the input/output paths, then retry."
            )
        except ImportError as e:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"Required conversion library is not installed: {str(e)}. "
                        "Install it with: pip install 'cloudra[chem]', then retry."
            )
        except Exception as e:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"Format conversion failed: {str(e)}. "
                        f"Check that {input_path} is a valid {user_input.input_format} file and that "
                        f"'{user_input.output_format}' is supported, then retry."
            )
