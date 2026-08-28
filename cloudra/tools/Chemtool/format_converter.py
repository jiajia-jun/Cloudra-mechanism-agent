import os
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

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
}


class FormatConverter_input_schema(input_schema):
    input_path: str = Field(
        description="Absolute path of the input file."
    )
    input_format: Literal["mol", "xyz", "gjf", "pdb", "cif", "sdf", "log"] = Field(
        description="Input format. log means a Gaussian or ORCA output log (.log/.out); then output must be csv."
    )
    output_format: Literal["mol", "xyz", "gjf", "inp", "pdb", "cif", "sdf", "csv"] = Field(
        description="Target output format. 'inp' is an ORCA input (coordinates only, charge 0 / "
                    "multiplicity 1 — edit method/charge with qm_input_writer instead for production). "
                    "csv is only for log→key-frame tables."
    )
    output_path: str = Field(
        description="Absolute path of the output file."
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
    def _convert_log_to_csv(user_input: "FormatConverter_input_schema") -> FormatConverter_output_schema:
        """Gaussian 日志 → 关键帧 CSV（优化轨迹/扫描/IRC 曲线）。"""
        if user_input.input_format != "log":
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="output_format='csv' is only supported for Gaussian log input (input_format='log'). "
                        "For structure files, choose a structure output_format instead."
            )
        if user_input.output_format != "csv":
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="When input_format='log', the output format must be 'csv' (key-frame table)."
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

            engine = detect_qm_engine(user_input.input_path)
            frames_mod = orca_frames if engine == "orca" else gaussian_frames
            job_types = frames_mod.detect_job_types(user_input.input_path)
            frames = frames_mod.extract_frames(user_input.input_path)
            # 按规范顺序展示（opt+ts+freq 风格，而非字母序）
            ordered = [j for j in ("opt", "ts", "freq", "scan", "irc", "sp") if j in job_types]
            if not frames:
                return FormatConverter_output_schema(
                    is_success=False,
                    output_path="",
                    message=f"No key frames could be extracted from the {engine or 'unknown'}-engine log "
                            f"(detected as {'+'.join(ordered) or 'unknown'}): {user_input.input_path}. "
                            "Check that the log contains a finished opt/scan/irc job "
                            "(ORCA IRC per-point extraction is not supported yet)."
                )
            frames_to_csv(frames, user_input.output_path)
            return FormatConverter_output_schema(
                is_success=True,
                output_path=user_input.output_path,
                message=f"Detected {engine or 'unknown'} {'+'.join(ordered)}, wrote {len(frames)} frames -> {user_input.output_path}"
            )
        except Exception as e:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"Failed to extract key frames from the log: {str(e)}. "
                        "Check that the input is a valid Gaussian log; "
                        "you can also read it directly with log_parser."
            )

    async def tool_call(self, user_input: FormatConverter_input_schema, session: Session) -> FormatConverter_output_schema:
        input_path = user_input.input_path
        output_path = user_input.output_path

        # 0. log→csv 走 Gaussian 关键帧提取，与 ASE 格式转换分流
        if user_input.input_format == "log" or user_input.output_format == "csv":
            return self._convert_log_to_csv(user_input)

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

            # 3. 读取输入文件
            atoms = ase.io.read(input_path, format=ase_input_fmt)
            if atoms is None:
                return FormatConverter_output_schema(
                    is_success=False,
                    output_path="",
                    message=f"Could not read a structure from {input_path}. "
                            f"Check that the file content matches input_format='{user_input.input_format}'."
                )

            # 4. 确保输出目录存在并写入
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            if user_input.output_format == "inp":
                # ASE 的 ORCA writer 不在 io 注册表中，走直接调用分支
                self._write_orca_inp(atoms, output_path)
            else:
                ase.io.write(output_path, atoms, format=ase_output_fmt)

            return FormatConverter_output_schema(
                is_success=True,
                output_path=output_path,
                message=f"Converted {user_input.input_format} to {user_input.output_format}: {output_path}"
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


def get_class():
    return FormatConverter
