"""Chemical utility routes: 2D molecular structure rendering via RDKit."""

from __future__ import annotations

import asyncio
import html
import re
from functools import lru_cache

from fastapi import APIRouter
from fastapi.responses import Response

from ..context import ApiContext

try:
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    rdMolDraw2D = None
    _RDKIT_AVAILABLE = False


def _fallback_svg(text: str, width: int, height: int) -> str:
    escaped = html.escape(text[:30])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="transparent"/>'
        f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        f'fill="#94a3b8" font-size="11" font-family="-apple-system, BlinkMacSystemFont, sans-serif">{escaped}</text>'
        f'</svg>'
    )


DARK_BOND_COLOR = "#cbd5e1"  # Soft slate-silver: crisp and comfortable on dark backgrounds without glare

# Precompiled regex patterns for comprehensive dark-mode conversion (catching all black/stark-white strokes and fills)
_STROKE_BLACK_PATTERN = re.compile(
    r'(stroke\s*[:=]\s*[\'"]?)(?:#000000|#000|black|rgb\(\s*0%?\s*,\s*0%?\s*,\s*0%?\s*\)|#f1f5f9)([\'\";\s}])',
    flags=re.IGNORECASE,
)
_FILL_BLACK_PATTERN = re.compile(
    r'(fill\s*[:=]\s*[\'"]?)(?:#000000|#000|black|rgb\(\s*0%?\s*,\s*0%?\s*,\s*0%?\s*\)|#f1f5f9)([\'\";\s}])',
    flags=re.IGNORECASE,
)

_DARK_MODE_STYLE_BLOCK = f"""<style>
  path[stroke="#000000"], path[stroke="#000"], path[stroke="black"], path[stroke*="rgb(0,0,0)"],
  path[stroke="#f1f5f9"], path[style*="stroke:#f1f5f9"],
  path[style*="stroke:#000000"], path[style*="stroke: #000000"], path[style*="stroke:#000"],
  path[style*="stroke:black"], path[style*="stroke:rgb(0,0,0)"], path[style*="stroke:rgb(0, 0, 0)"],
  line[stroke="#000000"], line[stroke="#000"], line[stroke="black"], line[stroke*="rgb(0,0,0)"],
  line[stroke="#f1f5f9"], line[style*="stroke:#f1f5f9"],
  line[style*="stroke:#000000"], line[style*="stroke: #000000"], line[style*="stroke:#000"],
  line[style*="stroke:black"], line[style*="stroke:rgb(0,0,0)"], line[style*="stroke:rgb(0, 0, 0)"],
  polygon[style*="stroke:#000000"], polygon[style*="stroke: #000000"],
  .bond-line, [class*="bond-"] {{
    stroke: {DARK_BOND_COLOR} !important;
  }}
  path[fill="#000000"], path[fill="#000"], path[fill="black"], path[fill*="rgb(0,0,0)"],
  path[fill="#f1f5f9"], path[style*="fill:#f1f5f9"],
  path[style*="fill:#000000"], path[style*="fill: #000000"], path[style*="fill:#000"],
  path[style*="fill:black"], path[style*="fill:rgb(0,0,0)"], path[style*="fill:rgb(0, 0, 0)"],
  polygon[style*="fill:#000000"], polygon[style*="fill: #000000"], polygon[fill="#000000"],
  polygon[fill="#000"], polygon[fill="black"], polygon[fill="#f1f5f9"] {{
    fill: {DARK_BOND_COLOR} !important;
  }}
  text[fill="#000000"], text[fill="#000"], text[fill="black"], text[fill*="rgb(0,0,0)"],
  text[fill="#f1f5f9"], text[style*="fill:#f1f5f9"],
  text[style*="fill:#000000"], text[style*="fill: #000000"], text[style*="fill:#000"],
  text[style*="fill:black"], text[style*="fill:rgb(0,0,0)"], text[style*="fill:rgb(0, 0, 0)"] {{
    fill: {DARK_BOND_COLOR} !important;
  }}
</style>"""


def _post_process_dark_svg(svg: str) -> str:
    # 1. Regex replacements
    svg = _STROKE_BLACK_PATTERN.sub(rf'\g<1>{DARK_BOND_COLOR}\2', svg)
    svg = _FILL_BLACK_PATTERN.sub(rf'\g<1>{DARK_BOND_COLOR}\2', svg)

    # 2. Exact fallback string replaces
    svg = (
        svg.replace("stroke:#000000", f"stroke:{DARK_BOND_COLOR}")
           .replace("stroke: #000000", f"stroke: {DARK_BOND_COLOR}")
           .replace("stroke:#f1f5f9", f"stroke:{DARK_BOND_COLOR}")
           .replace("stroke: #f1f5f9", f"stroke: {DARK_BOND_COLOR}")
           .replace("fill:#000000", f"fill:{DARK_BOND_COLOR}")
           .replace("fill: #000000", f"fill: {DARK_BOND_COLOR}")
           .replace("fill:#f1f5f9", f"fill:{DARK_BOND_COLOR}")
           .replace("fill: #f1f5f9", f"fill: {DARK_BOND_COLOR}")
           .replace("stroke:rgb(0%,0%,0%)", "stroke:rgb(80%,84%,88%)")
           .replace("fill:rgb(0%,0%,0%)", "fill:rgb(80%,84%,88%)")
           .replace("stroke:rgb(0,0,0)", "stroke:rgb(203,213,225)")
           .replace("fill:rgb(0,0,0)", "fill:rgb(203,213,225)")
           .replace('stroke="#000000"', f'stroke="{DARK_BOND_COLOR}"')
           .replace("stroke='#000000'", f"stroke='{DARK_BOND_COLOR}'")
           .replace('stroke="#f1f5f9"', f'stroke="{DARK_BOND_COLOR}"')
           .replace("stroke='#f1f5f9'", f"stroke='{DARK_BOND_COLOR}'")
           .replace('fill="#000000"', f'fill="{DARK_BOND_COLOR}"')
           .replace("fill='#000000'", f"fill='{DARK_BOND_COLOR}'")
           .replace('fill="#f1f5f9"', f'fill="{DARK_BOND_COLOR}"')
           .replace("fill='#f1f5f9'", f"fill='{DARK_BOND_COLOR}'")
    )

    # 3. Inject CSS style block right before </svg>
    if "</svg>" in svg:
        svg = svg.replace("</svg>", f"{_DARK_MODE_STYLE_BLOCK}</svg>")
    else:
        svg = f"{svg}{_DARK_MODE_STYLE_BLOCK}"

    return svg


@lru_cache(maxsize=1024)
def _render_smiles_to_svg(smiles: str, width: int, height: int, theme: str, version: str = "w4") -> str:
    if not _RDKIT_AVAILABLE or Chem is None or rdMolDraw2D is None:
        return _fallback_svg(smiles, width, height)

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return _fallback_svg(smiles, width, height)

        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        opts = drawer.drawOptions()
        opts.clearBackground = False  # Transparent background
        opts.padding = 0.06
        opts.bondLineWidth = 1.4  # Slender, refined chemical line width
        opts.minFontSize = 10
        opts.maxFontSize = 14

        if theme == "dark":
            # Attempt to set RDKit's internal palette using DrawColour if available
            c_soft = None
            if hasattr(rdMolDraw2D, "DrawColour"):
                try:
                    c_soft = rdMolDraw2D.DrawColour(0.80, 0.84, 0.88, 1.0)
                except Exception:
                    try:
                        c_soft = rdMolDraw2D.DrawColour(0.80, 0.84, 0.88)
                    except Exception:
                        pass

            if c_soft is None:
                c_soft = (0.80, 0.84, 0.88)

            try:
                if hasattr(opts, "updateAtomPalette"):
                    opts.updateAtomPalette({
                        0: c_soft,  # Wildcard
                        1: c_soft,  # Hydrogen
                        6: c_soft,  # Carbon
                    })
            except Exception:
                pass

            try:
                if hasattr(opts, "symbolColour"):
                    opts.symbolColour = c_soft
            except Exception:
                pass

        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()

        if theme == "dark":
            svg = _post_process_dark_svg(svg)

        return svg
    except Exception:
        return _fallback_svg(smiles, width, height)


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/chem/render-smiles")
    async def render_smiles(
        smiles: str,
        width: int = 200,
        height: int = 150,
        theme: str = "dark",
    ) -> Response:
        """Render a SMILES string to 2D SVG molecular structure diagram.

        Uses RDKit when available, cached in-memory. Returns SVG image.
        """
        w = max(40, min(width, 1000))
        h = max(30, min(height, 800))
        cleaned = smiles.strip()
        if not cleaned:
            return Response(content=_fallback_svg("(empty)", w, h), media_type="image/svg+xml")

        # RDKit 渲染是同步 CPU 工作，卸载出事件循环。
        svg = await asyncio.to_thread(_render_smiles_to_svg, cleaned, w, h, theme, "w4")
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    return router
