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
from cloudra.persistence.workspace import resolve_existing_tool_path

try:
    import pymol
    _PYMOL_MODULE_AVAILABLE = True
except Exception:
    pymol = None
    _PYMOL_MODULE_AVAILABLE = False


def pymol_available() -> bool:
    """Return True only when PyMOL can actually run (not just present on PATH)."""
    if _PYMOL_MODULE_AVAILABLE:
        return True
    binary = shutil.which("pymol")
    if not binary:
        return False
    try:
        completed = subprocess.run(
            [binary, "-cq", "-d", "quit"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False

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
    "re-check the rendered image with read afterwards. "
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


def _pml_path(path: str) -> str:
    """Format a path for PyMOL script lines (unquoted when safe; quoted otherwise)."""
    if any(ch in path for ch in (' ', '"', "'")):
        return _pml_quote(path)
    return path


def _png_base_path(output_path: str) -> str:
    """PyMOL's ``png`` command always appends ``.png`` to the basename."""
    if output_path.lower().endswith(".png"):
        return output_path[:-4]
    return output_path


def _expected_png_path(output_path: str) -> str:
    """PyMOL 实际会产出的图片路径：png 命令总是把 .png 加回 basename。

    用户给的 output_path 不带 .png 时，产物在 output_path + '.png'；
    工具的文件存在性检查与返回路径必须与产物对齐（否则误报"produced no image"）。
    """
    if output_path.lower().endswith(".png"):
        return output_path
    return output_path + ".png"


def _render_commands(structure_path: str, output_path: str, style: str,
                     width: int, height: int, dpi: int, ray: bool) -> list[str]:
    """The PyMOL command sequence shared by the module and CLI fallback paths."""
    png_target = _png_base_path(output_path)
    return [
        "reinitialize",
        f"load {_pml_path(structure_path)}, mol",
        "hide everything",
        _STYLE_COMMANDS[style],
        "bg_color white",
        f"png {_pml_path(png_target)}, width={width}, height={height}, dpi={dpi}, ray={1 if ray else 0}",
    ]


def _render_with_module(
    structure_path: str,
    output_path: str,
    style: str,
    width: int,
    height: int,
    dpi: int,
    ray: bool,
) -> None:
    """Render in-process via the pymol module (global state; reinitialize first)."""
    from pymol import cmd

    pymol.finish_launching(["pymol", "-cq"])
    cmd.reinitialize()
    cmd.load(os.path.abspath(structure_path), "mol")
    cmd.hide("everything")
    cmd.do(_STYLE_COMMANDS[style])
    cmd.bg_color("white")
    cmd.png(
        _png_base_path(os.path.abspath(output_path)),
        width=width,
        height=height,
        dpi=dpi,
        ray=1 if ray else 0,
    )


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
        try:
            structure_path = resolve_existing_tool_path(self, structure_path)
        except FileNotFoundError as exc:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message=f"Error: {exc}",
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

        binary = shutil.which("pymol")
        if binary is None and not _PYMOL_MODULE_AVAILABLE:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message="PyMOL is not available; cannot render the structure. "
                        "Install it with: pip install 'cloudra[visual]' (pymol-open-source) "
                        "or install a system PyMOL, then retry.",
            )

        # PyMOL 的 png 命令总在 basename 后补 .png：产物路径 = output_path 或其 + '.png'
        abs_output = os.path.abspath(output_path)
        image_file = _expected_png_path(abs_output)

        def render() -> None:
            os.makedirs(os.path.dirname(abs_output), exist_ok=True)
            commands = _render_commands(
                os.path.abspath(structure_path), abs_output, style,
                user_input.width, user_input.height, user_input.dpi, user_input.ray,
            )
            if binary is not None:
                _render_with_binary(binary, commands)
            else:
                _render_with_module(
                    os.path.abspath(structure_path),
                    abs_output,
                    style,
                    user_input.width,
                    user_input.height,
                    user_input.dpi,
                    user_input.ray,
                )

        try:
            await asyncio.to_thread(render)
        except Exception as e:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message=f"PyMOL rendering raised an exception: {str(e)}",
            )
        if not os.path.isfile(image_file) or os.path.getsize(image_file) == 0:
            return PymolRender_output_schema(
                is_success=False,
                image_path="",
                message=f"PyMOL finished but produced no image at {image_file}. "
                        "Check that the structure file is valid and retry.",
            )
        return PymolRender_output_schema(
            is_success=True,
            image_path=image_file,
            message=f"Image rendered: {image_file}. Inspect it with read to verify the result.",
        )


def get_class():
    return PymolRender
