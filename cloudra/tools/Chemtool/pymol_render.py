import asyncio
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

try:
    import pymol
    _PYMOL_MODULE_AVAILABLE = True
except Exception:
    pymol = None
    _PYMOL_MODULE_AVAILABLE = False

_SUPPORTED_FORMATS = {".pdb", ".mol", ".sdf", ".mol2", ".xyz", ".cif"}
_STYLE_COMMANDS = {
    "sticks": "show sticks",
    "spheres": "show spheres",
    "cartoon": "show cartoon",
    "surface": "show surface",
    "line": "show lines",
}

description = (
    "Render a 3D molecular structure file (PDB/MOL/SDF/MOL2/XYZ/CIF) to a publication-style PNG "
    "with PyMOL (headless), supporting style presets, size, DPI, and ray tracing. "
    "Use for: showing a 3D structure to the user or making a report figure; "
    "re-check the rendered image with image_reader afterwards. "
    "Do not use for: 2D structure diagrams (use molecule_drawer) or generating 3D coordinates (use smiles_to_mol)."
)


class PymolRender_input_schema(input_schema):
    structure_path: str = Field(description="Absolute path of the structure file (.pdb/.mol/.sdf/.mol2/.xyz/.cif)")
    style: str = Field(default="sticks", description="Style preset: sticks, spheres, cartoon, surface, or line")
    width: int = Field(default=800, description="Image width (px)")
    height: int = Field(default=600, description="Image height (px)")
    dpi: int = Field(default=300, description="Image resolution (DPI)")
    ray: bool = Field(default=True, description="Whether to ray-trace the image (slower, higher quality)")
    output_path: Optional[str] = Field(
        default=None,
        description="Absolute path of the output PNG; defaults to .cloudra/visual/ under the workspace with a timestamped name",
    )


class PymolRender_output_schema(output_schema):
    is_success: bool = Field(description="Whether the image was rendered")
    image_path: str = Field(description="Absolute path of the rendered PNG")
    message: str = Field(default="", description="Status or error message")


def _pml_quote(path: str) -> str:
    """Quote a path for a .pml script line (double-quoted, backslashes escaped)."""
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render_commands(structure_path: str, output_path: str, style: str,
                     width: int, height: int, dpi: int, ray: bool) -> list[str]:
    """The PyMOL command sequence shared by the module and CLI fallback paths."""
    return [
        "reinitialize",
        f"load {_pml_quote(structure_path)}, mol",
        "hide everything",
        _STYLE_COMMANDS[style],
        "bg_color white",
        f"png {_pml_quote(output_path)}, width={width}, height={height}, dpi={dpi}, ray={1 if ray else 0}",
    ]


def _render_with_module(commands: list[str]) -> None:
    """Render in-process via the pymol module (global state; reinitialize first)."""
    from pymol import cmd

    pymol.finish_launching(["pymol", "-cq"])
    for command in commands:
        cmd.do(command)


def _render_with_binary(binary: str, commands: list[str]) -> None:
    """Render via a system pymol binary running a temporary .pml script."""
    script = "\n".join([*commands, "quit"]) + "\n"
    fd, script_path = tempfile.mkstemp(prefix="cloudra-pymol-", suffix=".pml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(script)
        completed = subprocess.run(
            [binary, "-cq", script_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"pymol exited with code {completed.returncode}: {completed.stderr[-500:]}")
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


class PymolRender(Tool):
    tool_id: str = 't-52'
    tool_name: str = 'pymol_render'
    tool_description: str = description
    input_schema: Any = PymolRender_input_schema
    output_schema: Any = PymolRender_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: PymolRender_input_schema, session: Session) -> PymolRender_output_schema:
        structure_path = user_input.structure_path
        ext = os.path.splitext(structure_path)[1].lower()
        if ext not in _SUPPORTED_FORMATS:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message=f"Error: unsupported structure format {ext or '(none)'}. "
                        f"Supported: {', '.join(sorted(_SUPPORTED_FORMATS))}.",
            )
        if not os.path.isfile(structure_path):
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message=f"Error: structure file does not exist at path {structure_path}",
            )
        style = (user_input.style or "sticks").lower()
        if style not in _STYLE_COMMANDS:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message=f"Error: unknown style {user_input.style!r}. Choose one of: {', '.join(sorted(_STYLE_COMMANDS))}.",
            )

        if user_input.output_path:
            output_path = user_input.output_path
        else:
            root = getattr(self.subagent, "working_directory", None) or os.getcwd()
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            output_path = os.path.join(root, ".cloudra", "visual", f"pymol-{stamp}.png")

        binary = None if _PYMOL_MODULE_AVAILABLE else shutil.which("pymol")
        if not _PYMOL_MODULE_AVAILABLE and binary is None:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message="PyMOL is not available; cannot render the structure. "
                        "Install it with: pip install 'cloudra[visual]' (pymol-open-source) "
                        "or install a system PyMOL, then retry.",
            )

        def render() -> None:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            commands = _render_commands(
                os.path.abspath(structure_path), os.path.abspath(output_path), style,
                user_input.width, user_input.height, user_input.dpi, user_input.ray,
            )
            if _PYMOL_MODULE_AVAILABLE:
                _render_with_module(commands)
            else:
                _render_with_binary(binary, commands)

        try:
            await asyncio.to_thread(render)
        except Exception as e:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message=f"PyMOL rendering raised an exception: {str(e)}",
            )
        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message=f"PyMOL finished but produced no image at {output_path}. "
                        "Check that the structure file is valid and retry.",
            )
        return PymolRender_output_schema(
            is_success=True,
            image_path=output_path,
            message=f"Image rendered: {output_path}. Inspect it with image_reader to verify the result.",
        )


def get_class():
    return PymolRender
