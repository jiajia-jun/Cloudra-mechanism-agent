"""Ray-trace the six archived NI1 geometries with a CYLview-inspired style.

Rendering is performed by PyMOL, not CYLview. Only proper rigid rotations and
translations are applied to the archived XYZ coordinates. Bond definitions
follow the previous figure: RDKit bond orders for minima, distance-based TS
single bonds, and the explicitly specified dashed reaction-center contacts.

Dependencies: PyMOL, NumPy, RDKit. Run this file with the chemistry Python, or
import render() to regenerate all six transparent PNGs and the render manifest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import time
from pathlib import Path

import numpy as np
import pymol2
from pymol.cgo import COLOR, CYLINDER, SPHERE
from rdkit import Chem
from rdkit.Chem import rdDetermineBonds

ROOT = Path(__file__).resolve().parent
SELECTED = ["RC1", "TS1", "INT1_lowest", "INT1_IRC2", "TS2", "P1_lowest"]
COLORS = {
    "C": (0.43, 0.45, 0.47),
    "H": (0.97, 0.97, 0.96),
    "N": (0.20, 0.37, 0.73),
    "O": (0.82, 0.20, 0.22),
}
RADII = {"C": 0.235, "N": 0.245, "O": 0.245, "H": 0.145}
COV = {"C": 0.76, "N": 0.71, "O": 0.66, "H": 0.31}
BOND_COLOR = (0.60, 0.61, 0.62)
CONTACT_COLOR = (0.68, 0.37, 0.22)
CHANGING = {
    "TS1": {(0, 5), (5, 9), (1, 9)},
    "TS2": {(2, 3), (1, 7), (3, 7)},
}
SETTINGS = {
    "orthoscopic": 1,
    "ray_orthoscopic": 1,
    "ray_opaque_background": 0,
    "opaque_background": 0,
    "ray_trace_mode": 1,
    "ray_trace_gain": 0.045,
    "ray_trace_slope_factor": 0.65,
    "ray_shadows": 1,
    "ray_shadow_decay_factor": 0.8,
    "ray_shadow_decay_range": 3.0,
    "ambient": 0.52,
    "direct": 0.48,
    "reflect": 0.13,
    "specular": 0.22,
    "shininess": 35,
    "antialias": 2,
    "depth_cue": 0,
    "ray_trace_fog": 0,
    "gamma": 1.0,
    "light_count": 3,
    "ambient_occlusion_mode": 0,
    "max_threads": 4,
}
SOURCES = [
    "https://github.com/schrodinger/pymol-open-source/blob/master/data/setting_help.csv",
    "https://www.cylview.org/wiki.html",
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_xyz(path):
    lines = path.read_text().splitlines()
    rows = [line.split() for line in lines[2:] if line.strip()]
    elements = [row[0] for row in rows]
    coords = np.array([[float(v) for v in row[1:4]] for row in rows])
    if len(rows) != int(lines[0]):
        raise ValueError(f"XYZ atom count differs from header: {path}")
    return elements, coords


def projection(coords, elements):
    """Use the previous figure's proper orthographic view search."""
    xyz = coords - coords.mean(axis=0)
    _, _, axes = np.linalg.svd(xyz, full_matrices=False)
    if np.linalg.det(axes) < 0:
        axes[-1] *= -1
    xyz = xyz @ axes.T
    best = None
    for tilt in [-0.65, -0.35, 0.0, 0.35, 0.65]:
        for spin in np.linspace(0, 2 * np.pi, 24, endpoint=False):
            a = np.array([[np.cos(spin), -np.sin(spin), 0], [np.sin(spin), np.cos(spin), 0], [0, 0, 1]])
            b = np.array([[1, 0, 0], [0, np.cos(tilt), -np.sin(tilt)], [0, np.sin(tilt), np.cos(tilt)]])
            view = xyz @ a.T @ b.T
            score = 0.0
            for i in range(len(view)):
                for j in range(i):
                    distance = np.linalg.norm(view[i, :2] - view[j, :2])
                    weight = 0.6 if "H" in (elements[i], elements[j]) else 1.0
                    score += weight / max(distance, 0.04) ** 3
            score += 0.3 * np.ptp(view[:, 1]) / max(np.ptp(view[:, 0]), 0.1)
            if best is None or score < best[0]:
                best = score, view
    view = best[1]
    if view[np.argmax(np.linalg.norm(view[:, :2], axis=1)), 0] < 0:
        view[:, :2] *= -1  # 180-degree rotation about z, not a reflection.
    return view


def bonds(path, elements, coords, transition):
    if not transition:
        mol = Chem.MolFromXYZBlock(path.read_text())
        rdDetermineBonds.DetermineBonds(mol, charge=0)
        return [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(b.GetBondTypeAsDouble())) for b in mol.GetBonds()]
    return [
        (j, i, 1)
        for i in range(len(elements))
        for j in range(i)
        if np.linalg.norm(coords[i] - coords[j]) < 1.23 * (COV[elements[i]] + COV[elements[j]])
    ]


def cylinder(start, end, radius, color):
    return [CYLINDER, *map(float, start), *map(float, end), radius, *color, *color]


def molecular_cgo(elements, coords, covalent_bonds, contacts):
    """Explicit primitives prevent PyMOL from inferring any extra bond."""
    result = []
    for i, j, order in covalent_bonds:
        if (min(i, j), max(i, j)) in contacts:
            continue
        start, end = coords[i], coords[j]
        if order == 2:
            direction = end - start
            offset = np.array([-direction[1], direction[0], 0.0])
            if np.linalg.norm(offset) < 1e-8:
                offset = np.cross(direction, [0.0, 1.0, 0.0])
            offset *= 0.090 / np.linalg.norm(offset)
            for sign in [-1, 1]:
                result.extend(cylinder(start + sign * offset, end + sign * offset, 0.047, BOND_COLOR))
        else:
            result.extend(cylinder(start, end, 0.066, BOND_COLOR))
    for i, j in sorted(contacts):
        start, end = coords[i], coords[j]
        direction = end - start
        length = np.linalg.norm(direction)
        visible_start = RADII[elements[i]] / length
        visible_end = 1.0 - RADII[elements[j]] / length
        visible_length = (visible_end - visible_start) * length
        count = max(3, int(np.ceil(visible_length / 0.24)))
        step = (visible_end - visible_start) / count
        for k in range(count):
            a = visible_start + (k + 0.18) * step
            b = visible_start + (k + 0.74) * step
            result.extend(cylinder(start + a * direction, start + b * direction, 0.047, CONTACT_COLOR))
    for element, coord in zip(elements, coords):
        result.extend([COLOR, *COLORS[element], SPHERE, *map(float, coord), RADII[element]])
    return result


def geometry_check(original, transformed):
    original_distances = np.linalg.norm(original[:, None] - original[None, :], axis=-1)
    transformed_distances = np.linalg.norm(transformed[:, None] - transformed[None, :], axis=-1)
    rotation, *_ = np.linalg.lstsq(original - original.mean(0), transformed - transformed.mean(0), rcond=None)
    maximum_error = float(np.max(np.abs(original_distances - transformed_distances)))
    determinant = float(np.linalg.det(rotation))
    if maximum_error > 1e-10 or abs(determinant - 1.0) > 1e-10:
        raise ValueError("Rendered view is not a proper rigid transform of the XYZ geometry")
    return {"max_pair_distance_error_angstrom": maximum_error, "rotation_determinant": determinant}


def render(output_dir, source_dir=ROOT, width=1800, height=1800):
    """Return the manifest after six PyMOL ray traces at one common Å/pixel scale."""
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = {row["id"]: row for row in csv.DictReader((source_dir / "energies.csv").open())}
    provenance = json.loads((source_dir / "provenance.json").read_text())
    expected_hashes = {row["id"]: row["geometry_sha256"] for row in provenance["species"]}
    geometries = {}
    for key in SELECTED:
        path = source_dir / rows[key]["geometry_file"]
        elements, coords = read_xyz(path)
        digest = sha256(path)
        if digest != expected_hashes[key]:
            raise ValueError(f"Source geometry differs from provenance: {path}")
        geometries[key] = {"elements": elements, "original": coords, "view": projection(coords, elements), "path": path, "sha256": digest}
    fixed = geometries["INT1_lowest"]["view"][[4, 5, 0, 1]]
    moving = geometries["INT1_IRC2"]["original"][[0, 1, 2, 3]]
    u, _, vh = np.linalg.svd((moving - moving.mean(0)).T @ (fixed - fixed.mean(0)))
    rotation = u @ np.diag([1, 1, np.linalg.det(u @ vh)]) @ vh
    geometries["INT1_IRC2"]["view"] = (geometries["INT1_IRC2"]["original"] - moving.mean(0)) @ rotation + fixed.mean(0)

    half_width, half_height = 0.0, 0.0
    for geometry in geometries.values():
        view = geometry["view"]
        center = (view.max(0) + view.min(0)) / 2
        geometry["view"] = view - center
        radii = np.array([RADII[e] for e in geometry["elements"]])
        half_width = max(half_width, float(np.max(np.abs(geometry["view"][:, 0]) + radii)))
        half_height = max(half_height, float(np.max(np.abs(geometry["view"][:, 1]) + radii)))
    half_height = max(half_height, half_width * height / width) + 0.35
    half_width = half_height * width / height
    field_of_view = 20.0
    distance = half_height / np.tan(np.radians(field_of_view / 2))
    view = (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, -distance, 0, 0, 0, distance - 7, distance + 7, field_of_view)
    manifest = {
        "renderer": "PyMOL internal ray tracer; CYLview-inspired ball-and-cylinder style, not CYLview native output",
        "documentation": SOURCES,
        "source_dir": ".",
        "image_size": [width, height],
        "background": "transparent alpha, white compositing background",
        "settings": SETTINGS,
        "sphere_radii_angstrom": RADII,
        "single_bond_radius_angstrom": 0.066,
        "double_bond_radius_angstrom": 0.047,
        "double_bond_axis_offset_angstrom": 0.090,
        "contact_radius_angstrom": 0.047,
        "common_camera": list(view),
        "common_vertical_span_angstrom": 2 * half_height,
        "common_angstrom_per_pixel": 2 * half_height / height,
        "conformer_alignment": {"I_zero_based_indices": [4, 5, 0, 1], "I_prime_zero_based_indices": [0, 1, 2, 3], "rotation_determinant": float(np.linalg.det(rotation))},
        "molecules": [],
    }
    with pymol2.PyMOL() as session:
        cmd = session.cmd
        manifest["pymol_version"] = list(cmd.get_version())
        for name, value in SETTINGS.items():
            cmd.set(name, value)
        cmd.bg_color("white")
        cmd.set("light", [-0.4, -0.4, -1.0])
        for key in SELECTED:
            started = time.monotonic()
            geometry = geometries[key]
            contacts = CHANGING.get(key, set())
            linework = bonds(geometry["path"], geometry["elements"], geometry["original"], key.startswith("TS"))
            cmd.delete("all")
            cmd.load_cgo(molecular_cgo(geometry["elements"], geometry["view"], linework, contacts), "molecule")
            cmd.set_view(view)
            cmd.ray(width, height, quiet=1)
            output = output_dir / f"{key}.png"
            cmd.png(str(output), dpi=600, ray=0, quiet=1)
            header = output.read_bytes()[:33]
            png_width, png_height = struct.unpack(">II", header[16:24])
            if header[25] != 6:
                raise ValueError(f"Expected RGBA PNG from ray tracer: {output}")
            item = {
                "id": key,
                "output": output.name,
                "output_sha256": sha256(output),
                "source_xyz": geometry["path"].name,
                "source_sha256": geometry["sha256"],
                "source_matches_provenance": True,
                "source_unchanged_after_render": sha256(geometry["path"]) == geometry["sha256"],
                "atom_count": len(geometry["elements"]),
                "element_order": geometry["elements"],
                "covalent_bonds_zero_based": [list(b) for b in linework if (min(b[0], b[1]), max(b[0], b[1])) not in contacts],
                "dashed_contacts_zero_based": [list(pair) for pair in sorted(contacts)],
                "png_width": png_width,
                "png_height": png_height,
                "png_color_type": "RGBA",
                "ray_trace_elapsed_seconds": round(time.monotonic() - started, 3),
                **geometry_check(geometry["original"], geometry["view"]),
            }
            manifest["molecules"].append(item)
            print(f"Rendered {key}: {output} ({item['ray_trace_elapsed_seconds']} s)", flush=True)
    manifest_path = output_dir / "render_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "pymol_renders")
    parser.add_argument("--width", type=int, default=1800)
    parser.add_argument("--height", type=int, default=1800)
    args = parser.parse_args()
    render(args.output_dir, args.source_dir, args.width, args.height)
