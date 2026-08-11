from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    AllChem = None
    _RDKIT_AVAILABLE = False

description = (
    "将化学 SMILES 字符串转换为 MOL（MDL MOLfile）格式：基于 RDKit，支持生成带 2D 或 3D 坐标，"
    "可选择保存到文件或直接返回 MOL 文本内容。"
    "适用：只有 SMILES 时需要生成初始三维结构，作为 gjf_writer 或 format_converter 的输入。"
    "不适用：已有结构文件的格式互换（用 format_converter）、把 SMILES 画成图片（用 molecule_drawer）。"
)


class SmilesToMol_input_schema(input_schema):
    smiles: str = Field(description="输入的化学 SMILES 字符串")
    output_path: Optional[str] = Field(
        default=None,
        description="保存 MOL 文件的路径（可选）。如果提供，会将 MOL 内容写入该文件；否则仅返回 MOL 文本。"
    )
    generate_3d: bool = Field(
        default=False,
        description="是否生成 3D 坐标。默认为 False（生成 2D 坐标）。开启后会在内存中进行分子构象搜索和力场优化，耗时稍长。"
    )
    kekulize: bool = Field(
        default=True,
        description="是否在输出中显示 Kekulé 式（单双键交替），而非芳香键。"
    )


class SmilesToMol_output_schema(output_schema):
    is_success: bool = Field(description="转换是否成功")
    mol_content: str = Field(default="", description="生成的 MOL 文件文本内容（V2000 格式）")
    file_path: str = Field(default="", description="如果写入了文件，返回文件路径；否则为空")
    message: str = Field(default="", description="状态或错误信息")


class SmilesToMol(Tool):
    tool_id: str = 't-11'
    tool_name: str = 'smiles_to_mol'
    tool_description: str = description
    input_schema: Any = SmilesToMol_input_schema
    output_schema: Any = SmilesToMol_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: SmilesToMol_input_schema, session: Session) -> SmilesToMol_output_schema:
        if not _RDKIT_AVAILABLE:
            return SmilesToMol_output_schema(
                is_success=False,
                mol_content="",
                message="环境未安装 RDKit 库。请执行: pip install 'cloudra[chem]'"
            )

        from rdkit import Chem
        from rdkit.Chem import AllChem

        smiles = user_input.smiles
        path = user_input.output_path
        generate_3d = user_input.generate_3d
        kekulize = user_input.kekulize

        try:
            # 1. 解析 SMILES
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return SmilesToMol_output_schema(
                    is_success=False,
                    mol_content="",
                    message=f"无效的 SMILES 字符串: {smiles}"
                )

            # 2. 生成坐标
            if generate_3d:
                mol = Chem.AddHs(mol)
                embed_result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
                if embed_result == -1:
                    return SmilesToMol_output_schema(
                        is_success=False,
                        mol_content="",
                        message="3D 构象生成失败（EmbedMolecule 返回 -1）。"
                    )
                AllChem.MMFFOptimizeMolecule(mol)
            else:
                Chem.rdDepictor.Compute2DCoords(mol)

            # 3. 生成 MOL 块
            mol_block = Chem.MolToMolBlock(mol, kekulize=kekulize)
            if not mol_block:
                return SmilesToMol_output_schema(
                    is_success=False,
                    mol_content="",
                    message="RDKit 未能生成 MOL 块内容。"
                )

            # 4. 可选：写入文件
            saved_path = ""
            if path:
                import os
                dir_name = os.path.dirname(path)
                if dir_name and not os.path.exists(dir_name):
                    os.makedirs(dir_name, exist_ok=True)
                atomic_write_text(path, mol_block)
                saved_path = path

            return SmilesToMol_output_schema(
                is_success=True,
                mol_content=mol_block,
                file_path=saved_path,
                message="SMILES 转换为 MOL 成功。"
            )

        except Exception as e:
            return SmilesToMol_output_schema(
                is_success=False,
                mol_content="",
                message=f"转换异常: {str(e)}"
            )


def get_class():
    return SmilesToMol
