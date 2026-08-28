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
    "Convert a chemical SMILES string to MOL (MDL MOLfile) via RDKit, with 2D or 3D coordinates, "
    "optionally saving to a file or returning MOL text. "
    "Use for: generating an initial 3D structure from SMILES as input to qm_input_writer or format_converter. "
    "Do not use for: converting an existing structure file (use format_converter) or drawing SMILES as an image (use molecule_drawer)."
)


class SmilesToMol_input_schema(input_schema):
    smiles: str = Field(description="Input chemical SMILES string")
    output_path: Optional[str] = Field(
        default=None,
        description="Optional path to save the MOL file. If set, MOL content is written there; otherwise only MOL text is returned."
    )
    generate_3d: bool = Field(
        default=False,
        description="Whether to generate 3D coordinates. Default False (2D). When True, runs in-memory conformer search and force-field optimization (slower)."
    )
    kekulize: bool = Field(
        default=True,
        description="Whether to show Kekulé form (alternating single/double bonds) instead of aromatic bonds."
    )


class SmilesToMol_output_schema(output_schema):
    is_success: bool = Field(description="Whether conversion succeeded")
    mol_content: str = Field(default="", description="Generated MOL file text (V2000)")
    file_path: str = Field(default="", description="File path if written; otherwise empty")
    message: str = Field(default="", description="Status or error message")


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
                message="RDKit is not installed. Install it with: pip install 'cloudra[chem]', then retry."
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
                    message=f"Invalid SMILES string: {smiles}. Check the syntax and retry."
                )

            # 2. 生成坐标
            if generate_3d:
                mol = Chem.AddHs(mol)
                embed_result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
                if embed_result == -1:
                    return SmilesToMol_output_schema(
                        is_success=False,
                        mol_content="",
                        message="3D conformer generation failed (EmbedMolecule returned -1). "
                                "Retry, or set generate_3d=False to get a 2D structure instead."
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
                    message="RDKit did not produce MOL block content."
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
                message="SMILES converted to MOL successfully."
            )

        except Exception as e:
            return SmilesToMol_output_schema(
                is_success=False,
                mol_content="",
                message=f"Conversion raised an exception: {str(e)}. Check the SMILES and output_path, then retry."
            )


def get_class():
    return SmilesToMol
