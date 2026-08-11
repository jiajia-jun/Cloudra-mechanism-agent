import os
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "基于 ASE 在 mol、xyz、gjf、pdb、SDF、cif 等常见计算化学文件格式之间相互转换；"
    "坐标数据仅在文件之间流转，不会出现在返回结果中。"
    "也支持 Gaussian 日志（input_format='log'）提取关键帧为 CSV（output_format='csv'）："
    "优化轨迹、扫描曲线、IRC 反应路径逐点的结构/能量/反应坐标，供程序化分析。"
    "适用：已有结构文件需要换格式（如 xyz 转 gjf、cif 转 pdb）以对接下游计算或可视化；"
    "IRC/扫描曲线分析时把日志转成 CSV 后用 pandas 等程序化读取。"
    "不适用：从 SMILES 生成初始三维结构（用 smiles_to_mol）、编写 Gaussian 计算输入（用 gjf_writer）。"
)


# 用户可见格式名 -> ASE 内部格式名的映射
_ASE_FORMAT_MAP = {
    "pdb": "proteindatabank",
    "gjf": "gaussian-in",
}


class FormatConverter_input_schema(input_schema):
    input_path: str = Field(
        description="输入文件的绝对路径。"
    )
    input_format: Literal["mol", "xyz", "gjf", "pdb", "cif", "sdf", "log"] = Field(
        description="输入文件格式。log 表示 Gaussian 输出日志（.log/.out），此时输出必须为 csv。"
    )
    output_format: Literal["mol", "xyz", "gjf", "pdb", "cif", "sdf", "csv"] = Field(
        description="目标输出格式。csv 仅用于 log→关键帧表。"
    )
    output_path: str = Field(
        description="输出文件的绝对路径。"
    )


class FormatConverter_output_schema(output_schema):
    is_success: bool = Field(description="转换是否成功")
    output_path: str = Field(default="", description="输出文件的绝对路径")
    message: str = Field(default="", description="状态或错误信息")


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
    def _convert_log_to_csv(user_input: "FormatConverter_input_schema") -> FormatConverter_output_schema:
        """Gaussian 日志 → 关键帧 CSV（优化轨迹/扫描/IRC 曲线）。"""
        if user_input.input_format != "log":
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="output_format='csv' 仅支持 Gaussian 日志输入（input_format='log'）。"
            )
        if user_input.output_format != "csv":
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="input_format='log' 时输出格式必须为 'csv'（关键帧表）。"
            )
        if not os.path.isfile(user_input.input_path):
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"输入文件不存在: {user_input.input_path}"
            )
        try:
            from cloudra.tools.core.gaussian_frames import (
                detect_job_types,
                extract_frames,
                frames_to_csv,
            )

            job_types = detect_job_types(user_input.input_path)
            frames = extract_frames(user_input.input_path)
            # 按规范顺序展示（opt+ts+freq 风格，而非字母序）
            ordered = [j for j in ("opt", "ts", "freq", "scan", "irc", "sp") if j in job_types]
            if not frames:
                return FormatConverter_output_schema(
                    is_success=False,
                    output_path="",
                    message=f"未能从日志中提取任何关键帧（识别为 {'+'.join(ordered) or '未知'}）: {user_input.input_path}"
                )
            frames_to_csv(frames, user_input.output_path)
            return FormatConverter_output_schema(
                is_success=True,
                output_path=user_input.output_path,
                message=f"识别为 {'+'.join(ordered)}，写出 {len(frames)} 帧 → {user_input.output_path}"
            )
        except Exception as e:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"日志关键帧提取失败: {str(e)}"
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
                message=f"输入文件不存在: {input_path}"
            )

        # 2. 校验输入/输出格式是否相同
        if user_input.input_format == user_input.output_format:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="输入格式与输出格式相同，无需转换。"
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
                    message=f"无法从 {input_path} 读取结构。"
                )

            # 4. 确保输出目录存在并写入
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            ase.io.write(output_path, atoms, format=ase_output_fmt)

            return FormatConverter_output_schema(
                is_success=True,
                output_path=output_path,
                message=f"成功将 {user_input.input_format} 转换为 {user_input.output_format}: {output_path}"
            )

        except Exception as e:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"格式转换失败: {str(e)}"
            )


def get_class():
    return FormatConverter
