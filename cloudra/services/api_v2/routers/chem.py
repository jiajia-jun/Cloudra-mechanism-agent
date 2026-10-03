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

    @router.get("/api/v2/chem/render-smiles", dependencies=ctx.protected)
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

    @router.get("/api/v2/chem/smiles-to-xyz", dependencies=ctx.protected)
    async def smiles_to_xyz(smiles: str) -> dict:
        """Convert a SMILES string to 3D Cartesian coordinates (XYZ block)."""
        cleaned = smiles.strip()
        if not cleaned:
            return {"success": False, "xyz": "", "num_atoms": 0, "formula": ""}

        def _generate() -> dict:
            if not _RDKIT_AVAILABLE or Chem is None:
                return {"success": False, "xyz": "", "num_atoms": 0, "formula": "", "error": "RDKit not available"}
            try:
                import numpy as np
                from rdkit.Chem import AllChem, rdMolDescriptors

                mol = Chem.MolFromSmiles(cleaned)
                if mol is None:
                    return {"success": False, "xyz": "", "num_atoms": 0, "formula": "", "error": "Invalid SMILES"}
                formula = rdMolDescriptors.CalcMolFormula(mol)
                frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
                if not frags:
                    return {"success": False, "xyz": "", "num_atoms": 0, "formula": "", "error": "No fragments found"}

                frag_data = []
                for f in frags:
                    f_h = Chem.AddHs(f)
                    res = AllChem.EmbedMolecule(f_h, randomSeed=42)
                    if res != 0:
                        res = AllChem.EmbedMolecule(f_h, useRandomCoords=True, randomSeed=42)
                    try:
                        AllChem.MMFFOptimizeMolecule(f_h)
                    except Exception:
                        try:
                            AllChem.UFFOptimizeMolecule(f_h)
                        except Exception:
                            pass

                    n = f_h.GetNumAtoms()
                    if n > 0:
                        conf = f_h.GetConformer()
                        pos = np.array([list(conf.GetAtomPosition(i)) for i in range(n)], dtype=float)
                        symbols = [f_h.GetAtomWithIdx(i).GetSymbol() for i in range(n)]
                        # Center fragment at its centroid
                        pos -= np.mean(pos, axis=0)
                    else:
                        pos = np.zeros((0, 3), dtype=float)
                        symbols = []

                    bonds = [
                        {
                            "atom1": b.GetBeginAtomIdx(),
                            "atom2": b.GetEndAtomIdx(),
                            "order": int(b.GetBondTypeAsDouble()),
                        }
                        for b in f_h.GetBonds()
                    ]
                    frag_data.append({
                        "pos": pos,
                        "symbols": symbols,
                        "bonds": bonds,
                    })

                gap = 3.2  # Angstroms separation between bounding boxes
                placed_pos = []
                all_symbols = []
                all_bonds = []
                global_atom_offset = 0

                if len(frag_data) == 1:
                    placed_pos.append(frag_data[0]["pos"])
                    all_symbols.extend(frag_data[0]["symbols"])
                    all_bonds.extend(frag_data[0]["bonds"])
                elif len(frag_data) == 2:
                    pos0 = frag_data[0]["pos"]
                    pos1 = frag_data[1]["pos"]
                    max_x0 = float(np.max(pos0[:, 0])) if len(pos0) > 0 else 0.0
                    min_x1 = float(np.min(pos1[:, 0])) if len(pos1) > 0 else 0.0

                    shifted_0 = pos0.copy()
                    shifted_0[:, 0] += -(max_x0 + gap / 2.0)

                    shifted_1 = pos1.copy()
                    shifted_1[:, 0] += -(min_x1 - gap / 2.0)

                    placed_pos.append(shifted_0)
                    placed_pos.append(shifted_1)

                    all_symbols.extend(frag_data[0]["symbols"])
                    all_symbols.extend(frag_data[1]["symbols"])

                    all_bonds.extend(frag_data[0]["bonds"])
                    for b in frag_data[1]["bonds"]:
                        all_bonds.append({
                            "atom1": b["atom1"] + len(frag_data[0]["symbols"]),
                            "atom2": b["atom2"] + len(frag_data[0]["symbols"]),
                            "order": b["order"],
                        })
                else:
                    current_x = 0.0
                    for data in frag_data:
                        pos = data["pos"]
                        if len(pos) > 0:
                            min_x = float(np.min(pos[:, 0]))
                            max_x = float(np.max(pos[:, 0]))
                            shift_x = current_x - min_x
                            current_x = shift_x + max_x + gap
                            shifted = pos.copy()
                            shifted[:, 0] += shift_x
                            placed_pos.append(shifted)
                        else:
                            placed_pos.append(pos)
                        all_symbols.extend(data["symbols"])
                        for b in data["bonds"]:
                            all_bonds.append({
                                "atom1": b["atom1"] + global_atom_offset,
                                "atom2": b["atom2"] + global_atom_offset,
                                "order": b["order"],
                            })
                        global_atom_offset += len(data["symbols"])

                if placed_pos and any(len(p) > 0 for p in placed_pos):
                    all_coords = np.vstack([p for p in placed_pos if len(p) > 0])
                    all_coords -= np.mean(all_coords, axis=0)
                else:
                    all_coords = np.zeros((0, 3), dtype=float)

                lines = [f"{len(all_symbols)}", f"{cleaned} ({len(frags)} fragments separated)"]
                for sym, coord in zip(all_symbols, all_coords):
                    lines.append(f"{sym:<2} {coord[0]:12.6f} {coord[1]:12.6f} {coord[2]:12.6f}")
                xyz_block = "\n".join(lines)

                return {
                    "success": True,
                    "xyz": xyz_block,
                    "num_atoms": len(all_symbols),
                    "formula": formula,
                    "bonds": all_bonds,
                    "num_fragments": len(frags),
                }
            except Exception as exc:
                return {"success": False, "xyz": "", "num_atoms": 0, "formula": "", "error": str(exc)}

        return await asyncio.to_thread(_generate)

    return router

