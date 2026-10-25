"""Chemical utility routes: 2D molecular structure rendering via RDKit."""

from __future__ import annotations

import asyncio
import html
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


def _fallback_svg(text: str, width: int, height: int, theme: str) -> str:
    escaped = html.escape(text[:30])
    color = "#94a3b8" if theme == "dark" else "#475569"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="transparent"/>'
        f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        f'fill="{color}" font-size="11" font-family="-apple-system, BlinkMacSystemFont, sans-serif">{escaped}</text>'
        f'</svg>'
    )


@lru_cache(maxsize=1024)
def _render_smiles_to_svg(smiles: str, width: int, height: int, theme: str) -> str:
    if not _RDKIT_AVAILABLE or Chem is None or rdMolDraw2D is None:
        return _fallback_svg(smiles, width, height, theme)

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return _fallback_svg(smiles, width, height, theme)

        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        opts = drawer.drawOptions()
        opts.clearBackground = False  # Transparent background
        opts.padding = 0.06
        opts.bondLineWidth = 1.4  # Slender, refined chemical line width
        opts.minFontSize = 10
        opts.maxFontSize = 14

        if theme == "dark":
            # 只调整中性原子的墨色；氮、氧等元素及相应键段保留 RDKit 配色。
            neutral = (203 / 255, 213 / 255, 225 / 255)
            opts.updateAtomPalette({0: neutral, 1: neutral, 6: neutral})
            opts.setSymbolColour(neutral)
            opts.setAnnotationColour(neutral)

        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        return _fallback_svg(smiles, width, height, theme)


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
            return Response(content=_fallback_svg("(empty)", w, h, theme), media_type="image/svg+xml")

        # RDKit 渲染是同步 CPU 工作，卸载出事件循环。
        svg = await asyncio.to_thread(_render_smiles_to_svg, cleaned, w, h, theme)
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

