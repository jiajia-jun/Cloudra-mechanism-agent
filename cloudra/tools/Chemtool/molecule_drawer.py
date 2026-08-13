import os
from typing import Any, List, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_bytes, atomic_write_text

try:
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    rdMolDraw2D = None
    _RDKIT_AVAILABLE = False

description = (
    "Draw a chemical SMILES as a molecular-structure image (PNG/SVG) with RDKit, "
    "supporting size, highlights, atom indices, stereo labels, bond width, and nearly all other RDKit drawing options. "
    "Use for: showing a structure to the user or making a report figure; re-check with image_reader after drawing. "
    "Do not use for: recovering SMILES from an image (use image_to_smiles) or generating a 3D coordinate file (use smiles_to_mol)."
)

class MoleculeDrawer_input_schema(input_schema):
    smiles: str = Field(description="Molecule SMILES string")
    output_path: str = Field(description="Absolute path to save the image (.png or .svg)")

    # 基础设置
    width: int = Field(default=400, description="Image width (px)")
    height: int = Field(default=400, description="Image height (px)")
    legend: str = Field(default="", description="Caption under the molecule")

    # 高亮设置
    highlight_atoms: Optional[List[int]] = Field(default=None, description="Atom indices to highlight")
    highlight_bonds: Optional[List[int]] = Field(default=None, description="Bond indices to highlight")

    # 绘图风格 (MolDrawOptions)
    add_atom_indices: bool = Field(default=False, description="Whether to show atom index numbers")
    add_stereo_annotation: bool = Field(default=False, description="Whether to show stereo labels (R/S)")
    explicit_methyl: bool = Field(default=False, description="Whether to draw methyl groups (CH3) explicitly")
    bond_line_width: float = Field(default=2.0, description="Bond line width")
    padding: float = Field(default=0.05, description="Padding between molecule and border (0-1)")
    use_bw: bool = Field(default=False, description="Whether to use black-and-white mode")
    font_size: int = Field(default=12, description="Atom-label font size")

    # 结构处理
    kekulize: bool = Field(default=True, description="Whether to Kekulize (show alternating single/double bonds)")
    add_hs: bool = Field(default=False, description="Whether to show hydrogen atoms")

class MoleculeDrawer_output_schema(output_schema):
    is_success: bool = Field(description="Whether the image was generated")
    image_path: str = Field(description="Path of the generated image file")
    message: str = Field(default="", description="Status or error message")

class MoleculeDrawer(Tool):
    tool_id: str = 't-6'
    tool_name: str = 'molecule_drawer'
    tool_description: str = description
    input_schema: Any = MoleculeDrawer_input_schema
    output_schema: Any = MoleculeDrawer_output_schema

    def is_write(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        # 绘图并保存文件通常仅需 WRITE 权限。
        return False

    async def tool_call(self, user_input: MoleculeDrawer_input_schema, session: Session) -> MoleculeDrawer_output_schema:
        if not _RDKIT_AVAILABLE:
            return MoleculeDrawer_output_schema(
                is_success=False,
                image_path="",
                message="环境未安装 RDKit 库，无法绘制分子结构图。请执行: pip install 'cloudra[chem]'"
            )
        smiles = user_input.smiles
        path = user_input.output_path

        # 安全审批
        details = (
            f"【动作】: 绘制分子结构图\n"
            f"【SMILES】: {smiles}\n"
            f"【目标路径】: {path}\n"
            f"【参数摘要】: 尺寸={user_input.width}x{user_input.height}, "
            f"原子编号={user_input.add_atom_indices}, 手性标注={user_input.add_stereo_annotation}"
        )
        approved, denial_reason = await self.ensure_safety(session, details=details, tool_args=user_input.model_dump(mode="json"))
        if not approved:
            message = "【安全拦截】操作被拒绝。"
            if denial_reason:
                message += f"\n拒绝原因: {denial_reason}"
            return MoleculeDrawer_output_schema(is_success=False, image_path="", message=message)

        try:
            # 1. 解析分子
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return MoleculeDrawer_output_schema(is_success=False, image_path="", message=f"无效的 SMILES: {smiles}")

            # 2. 预处理
            if user_input.add_hs:
                mol = Chem.AddHs(mol)

            if user_input.kekulize:
                Chem.Kekulize(mol)

            # 3. 配置 MolDrawOptions
            ext = os.path.splitext(path)[1].lower()
            if ext == '.svg':
                drawer = rdMolDraw2D.MolDraw2DSVG(user_input.width, user_input.height)
            else:
                drawer = rdMolDraw2D.MolDraw2DCairo(user_input.width, user_input.height)

            options = drawer.drawOptions()
            options.addAtomIndices = user_input.add_atom_indices
            options.addStereoAnnotation = user_input.add_stereo_annotation
            options.explicitMethyl = user_input.explicit_methyl
            options.bondLineWidth = user_input.bond_line_width
            options.padding = user_input.padding
            options.useBWAtomPalette = user_input.use_bw
            options.minFontSize = user_input.font_size
            options.maxFontSize = user_input.font_size

            # 4. 执行绘图
            drawer.DrawMolecule(
                mol,
                legend=user_input.legend,
                highlightAtoms=user_input.highlight_atoms,
                highlightBonds=user_input.highlight_bonds
            )
            drawer.FinishDrawing()

            # 5. 保存文件
            content = drawer.GetDrawingText()
            if isinstance(content, str):
                atomic_write_text(path, content)
            else:
                atomic_write_bytes(path, content)

            return MoleculeDrawer_output_schema(is_success=True, image_path=path, message="图像生成成功。")

        except Exception as e:
            return MoleculeDrawer_output_schema(is_success=False, image_path="", message=f"绘图异常: {str(e)}")

def get_class():
    return MoleculeDrawer
