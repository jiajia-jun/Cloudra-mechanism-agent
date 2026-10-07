import asyncio
import os
from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.structure_builder import (
    BUILD_DIR_NAME,
    BuildStrategy,
    PreparationRequest,
    StructureInput,
    build_artifact_dir,
    prepare_structure,
)

try:
    from rdkit import Chem
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    _RDKIT_AVAILABLE = False

description = (
    "Convert a chemical SMILES string to MOL (MDL MOLfile) via RDKit, with 2D or 3D coordinates, "
    "optionally saving to a file or returning MOL text. A successful 3D build also returns "
    "xyz_path for the XYZ file produced by the same build; reuse it instead of rebuilding "
    "the same SMILES to obtain XYZ coordinates. "
    "3D structures are built by the shared structure builder: SMILES is split into its connected "
    "components, each component is embedded and force-field optimized with a recorded trajectory, "
    "and a multi-component input is NOT returned as a complex (assembly is a separate, not yet "
    "approved step) — such input fails loud so no overlapping fragment geometry reaches a QM engine. "
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
        description="Whether to generate 3D coordinates. Default False (2D). When True, the shared "
                    "structure builder embeds and force-field-optimizes the structure and records a "
                    "full optimization trajectory (slower)."
    )
    kekulize: bool = Field(
        default=True,
        description="Whether to show Kekulé form (alternating single/double bonds) instead of aromatic bonds. 2D only."
    )
    charge: int = Field(
        default=0,
        description="Total molecular charge, for the 3D builder. Must equal the SMILES' formal-charge "
                    "sum (e.g. -1 for '[F-].CCl'); a mismatch is refused rather than silently built."
    )
    multiplicity: int = Field(
        default=1,
        description="Spin multiplicity (2S+1) for the 3D builder. The RDKit force fields are "
                    "closed-shell only, so a value > 1 is refused rather than built as closed-shell."
    )
    artifact_dir: Optional[str] = Field(
        default=None,
        description="Directory for 3D build artifacts (per-component structures, optimization "
                    "trajectories, prepared_structure.json). Default: "
                    "'<output_path parent>/structure_build/<stem>/', else './structure_build/'. "
                    "Relative paths resolve against the Agent working directory."
    )


class SmilesToMol_output_schema(output_schema):
    is_success: bool = Field(description="Whether conversion succeeded")
    mol_content: str = Field(default="", description="Generated MOL file text (V2000)")
    file_path: str = Field(default="", description="File path if written; otherwise empty")
    xyz_path: str = Field(
        default="",
        description="Reusable XYZ file from the same successful 3D build; empty for 2D or failed builds.",
    )
    message: str = Field(default="", description="Status or error message")


class SmilesToMol(Tool):
    tool_id: str = 't-11'
    tool_name: str = 'smiles_to_mol'
    tool_description: str = description
    input_schema: Any = SmilesToMol_input_schema
    output_schema: Any = SmilesToMol_output_schema

    def is_write(self) -> bool:
        return True

    def _resolve_artifact_dir(self, user_input: SmilesToMol_input_schema) -> str:
        """构建产物目录：显式 artifact_dir 优先，否则用**唯一**命名规则
        ``<父目录>/structure_build/<stem>/``（与另外两个入口一致；stem 层避免同目录下的
        多个结构互相覆盖）。"""
        if user_input.artifact_dir:
            return resolve_tool_path(self, user_input.artifact_dir)
        if user_input.output_path:
            base = os.path.dirname(user_input.output_path) or "."
            stem = os.path.splitext(os.path.basename(user_input.output_path))[0]
            return build_artifact_dir(base, stem)
        return resolve_tool_path(self, f"./{BUILD_DIR_NAME}")

    def _build_3d(self, user_input: SmilesToMol_input_schema) -> SmilesToMol_output_schema:
        """3D 路径：唯一实现是 structure_builder，本工具不再自带 Embed/MMFF 快捷路径。"""
        prepared = prepare_structure(PreparationRequest(
            structure=StructureInput(kind="smiles", value=user_input.smiles),
            output_dir=self._resolve_artifact_dir(user_input),
            total_charge=user_input.charge,
            multiplicity=user_input.multiplicity,
            strategy=BuildStrategy(name="per_component", embed=True, optimize=True),
        ))
        if prepared.status != "ok" or not prepared.has_coordinates:
            details = " | ".join(prepared.diagnostics) if prepared.diagnostics else prepared.message
            return SmilesToMol_output_schema(
                is_success=False,
                mol_content="",
                message=(
                    f"3D structure could not be prepared (build status: {prepared.status}). "
                    f"{prepared.message}"
                    + (f" Diagnostics: {details}" if details and details != prepared.message else "")
                    + f" Build artifacts: {prepared.artifact_path}"
                ),
            )

        mol_path = next((p for p in prepared.candidate_paths if p.endswith(".mol")), "")
        if not mol_path:
            raise FileNotFoundError(
                "the builder reported status='ok' but produced no MOL candidate: "
                f"{prepared.candidate_paths}"
            )
        with open(mol_path, encoding="utf-8") as handle:
            mol_block = handle.read()

        saved_path = ""
        if user_input.output_path:
            dir_name = os.path.dirname(user_input.output_path)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
            atomic_write_text(user_input.output_path, mol_block)
            saved_path = user_input.output_path

        component = prepared.components[0]
        trajectory = prepared.trajectory_ids[0] if prepared.trajectory_ids else "none"
        message = (
            f"SMILES converted to MOL successfully. 3D built by the shared structure builder: "
            f"component {component.component_id}, force field {component.engine or 'n/a'}, "
            f"final energy {component.final_energy}, trajectory {trajectory} "
            f"(build artifacts: {prepared.artifact_path})."
        )
        return SmilesToMol_output_schema(
            is_success=True,
            mol_content=mol_block,
            file_path=saved_path,
            xyz_path=prepared.candidate_path(".xyz"),
            message=message,
        )

    async def tool_call(self, user_input: SmilesToMol_input_schema, session: Session) -> SmilesToMol_output_schema:
        if not _RDKIT_AVAILABLE:
            return SmilesToMol_output_schema(
                is_success=False,
                mol_content="",
                message="RDKit is not installed. Install it with: pip install 'cloudra[chem]', then retry."
            )

        from rdkit import Chem

        smiles = user_input.smiles
        path = user_input.output_path
        kekulize = user_input.kekulize

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return SmilesToMol_output_schema(
                    is_success=False,
                    mol_content="",
                    message=f"Invalid SMILES string: {smiles}. Check the syntax and retry."
                )

            if user_input.generate_3d:
                # 3D 语义统一由共享构建器承担（分片、原子身份、力场轨迹、可用性判定）。
                if path:
                    user_input.output_path = resolve_tool_path(self, path)
                # 力场优化是同步重活，卸载出事件循环。
                return await asyncio.to_thread(self._build_3d, user_input)

            Chem.rdDepictor.Compute2DCoords(mol)
            mol_block = Chem.MolToMolBlock(mol, kekulize=kekulize)
            if not mol_block:
                return SmilesToMol_output_schema(
                    is_success=False,
                    mol_content="",
                    message="RDKit did not produce MOL block content."
                )

            saved_path = ""
            if path:
                path = resolve_tool_path(self, path)
                dir_name = os.path.dirname(path)
                if dir_name and not os.path.exists(dir_name):
                    os.makedirs(dir_name, exist_ok=True)
                atomic_write_text(path, mol_block)
                saved_path = path

            return SmilesToMol_output_schema(
                is_success=True,
                mol_content=mol_block,
                file_path=saved_path,
                message="SMILES converted to MOL successfully (2D depiction; no force field was run)."
            )
        except Exception as e:
            return SmilesToMol_output_schema(
                is_success=False,
                mol_content="",
                message=f"Conversion raised an exception: {str(e)}. Check the SMILES and output_path, then retry."
            )
