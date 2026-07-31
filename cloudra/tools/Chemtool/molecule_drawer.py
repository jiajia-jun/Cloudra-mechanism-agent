import os
from typing import Any, List, Optional

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

try:
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    rdMolDraw2D = None
    _RDKIT_AVAILABLE = False

description = (
    "利用 RDKit 将化学 SMILES 绘制成分子结构图像（PNG/SVG），"
    "支持尺寸、高亮、原子编号、手性标注、线宽等几乎所有 RDKit 绘图参数。"
    "适用：向用户展示分子结构、生成报告插图；画完可用 image_reader 重新查看核对。"
    "不适用：从图片反推 SMILES（用 image_to_smiles）、生成三维坐标文件（用 smiles_to_mol）。"
)

class MoleculeDrawer_input_schema(input_schema):
    smiles: str = Field(description="分子的 SMILES 字符串")
    output_path: str = Field(description="保存图像的绝对路径（.png 或 .svg）")

    # 基础设置
    width: int = Field(default=400, description="图像宽度 (px)")
    height: int = Field(default=400, description="图像高度 (px)")
    legend: str = Field(default="", description="分子下方的说明文字")

    # 高亮设置
    highlight_atoms: Optional[List[int]] = Field(default=None, description="要高亮的原子索引列表")
    highlight_bonds: Optional[List[int]] = Field(default=None, description="要高亮的键索引列表")

    # 绘图风格 (MolDrawOptions)
    add_atom_indices: bool = Field(default=False, description="是否显示原子索引编号")
    add_stereo_annotation: bool = Field(default=False, description="是否显示手性标注 (R/S)")
    explicit_methyl: bool = Field(default=False, description="是否显式显示甲基 (CH3)")
    bond_line_width: float = Field(default=2.0, description="键的线宽")
    padding: float = Field(default=0.05, description="分子与边框的留白比例 (0-1)")
    use_bw: bool = Field(default=False, description="是否使用黑白模式")
    font_size: int = Field(default=12, description="原子标签字体大小")

    # 结构处理
    kekulize: bool = Field(default=True, description="是否进行 Kekulize 处理（显示单双键交替）")
    add_hs: bool = Field(default=False, description="是否显示氢原子")

class MoleculeDrawer_output_schema(output_schema):
    is_success: bool = Field(description="是否成功生成图像")
    image_path: str = Field(description="生成的图像文件路径")
    message: str = Field(default="", description="状态或错误信息")

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
            with open(path, 'wb' if ext != '.svg' else 'w') as f:
                content = drawer.GetDrawingText()
                if isinstance(content, str) and ext != '.svg':
                    f.write(content.encode())
                else:
                    f.write(content)

            return MoleculeDrawer_output_schema(is_success=True, image_path=path, message="图像生成成功。")

        except Exception as e:
            return MoleculeDrawer_output_schema(is_success=False, image_path="", message=f"绘图异常: {str(e)}")

def get_class():
    return MoleculeDrawer
