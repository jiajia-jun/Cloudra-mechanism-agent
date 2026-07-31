import os
from typing import Any, Literal

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "基于 ASE 在 mol、xyz、gjf、pdb、SDF、cif 等常见计算化学文件格式之间相互转换；"
    "坐标数据仅在文件之间流转，不会出现在返回结果中。"
    "适用：已有结构文件需要换格式（如 xyz 转 gjf、cif 转 pdb），以对接下游计算或可视化。"
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
    input_format: Literal["mol", "xyz", "gjf", "pdb", "cif", "sdf"] = Field(
        description="输入文件格式。"
    )
    output_format: Literal["mol", "xyz", "gjf", "pdb", "cif", "sdf"] = Field(
        description="目标输出格式。"
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

    async def tool_call(self, user_input: FormatConverter_input_schema, session: Session) -> FormatConverter_output_schema:
        input_path = user_input.input_path
        output_path = user_input.output_path

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
