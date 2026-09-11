"""Relaxed dihedral scan about the M1 biaryl axis, driven by repeated constrained
xTB optimizations.

This build of xTB (6.7.1) ignores a `$scan` block (probed, see README), so the scan is
driven externally: every point is a full constrained optimization started from the
previous point's optimized geometry.

Input geometry: xtbpath.xyz frame 0 (the MTD run's reactant minimum, verbatim copy in
this directory).  Dihedral atoms are 1-based (2,7,8,9) = C1-C6-C7-C8, i.e. the
ortho-carbon / biaryl-carbon / biaryl-carbon / ortho-carbon torsion.

Usage:  python3 xtb_scan_driver.py <workdir>
Writes: xtb_scan.csv, xtb_scan_transcript.txt, scan_points/point_XXX.xyz
"""
import math
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DIH_ATOMS = (2, 7, 8, 9)          # 1-based, C1-C6-C7-C8
TARGETS = list(range(0, 181, 10))
FORCE_CONSTANT = 5.0


def read_xyz(path):
    lines = open(path).read().splitlines()
    n = int(lines[0].strip())
    return [np.array([float(x) for x in row.split()[1:4]]) for row in lines[2:2 + n]]


def first_frame(path):
    lines = open(path).read().splitlines()
    n = int(lines[0].strip())
    return "\n".join(lines[:2 + n]) + "\n"


def dihedral(at, idx):
    first, second, third, fourth = (t - 1 for t in idx)
    p = [at[t] for t in (first, second, third, fourth)]
    b0, b1, b2 = p[0] - p[1], p[2] - p[1], p[3] - p[2]
    n1, n2 = np.cross(b0, b1), np.cross(b1, b2)
    m = np.cross(n1, b1 / np.linalg.norm(b1))
    return math.degrees(math.atan2(float(np.dot(m, n2)), float(np.dot(n1, n2))))


def total_energy(out):
    for line in out.splitlines():
        if "TOTAL ENERGY" in line:
            parts = line.replace("|", " ").split()
            return float(parts[parts.index("ENERGY") + 1])
    return None


def main():
    work = sys.argv[1]
    os.makedirs(work, exist_ok=True)
    os.makedirs(os.path.join(work, "scan_points"), exist_ok=True)
    os.chdir(work)
    open("start.xyz", "w").write(first_frame(os.path.join(HERE, "xtbpath.xyz")))

    geometry = "current.xyz"
    shutil.copy("start.xyz", geometry)
    rows, transcript = [], []
    for target in TARGETS:
        block = "$constrain\n   dihedral: %d, %d, %d, %d, %.1f\n   force constant=%.1f\n$end\n" % (
            DIH_ATOMS + (target, FORCE_CONSTANT))
        open("constraint.inp", "w").write(block)
        proc = subprocess.run(["xtb", geometry, "--input", "constraint.inp", "--opt"],
                              capture_output=True, text=True)
        out = proc.stdout + proc.stderr
        energy = total_energy(out)
        converged = "GEOMETRY OPTIMIZATION CONVERGED" in out
        assert converged and energy is not None, "scan point %s failed" % target
        atoms = read_xyz("xtbopt.xyz")
        achieved = dihedral(atoms, DIH_ATOMS)
        rows.append((target, achieved, energy, converged))
        transcript.append("### target %.1f deg   (constraint block)\n%s" % (target, block))
        transcript.append("  achieved dihedral = %.2f deg   E = %.12f Eh   converged=%s\n"
                          % (achieved, energy, converged))
        for line in out.splitlines():
            if "GEOMETRY OPTIMIZATION CONVERGED" in line or "TOTAL ENERGY" in line:
                transcript.append("  | " + line.strip() + "\n")
        shutil.copy("xtbopt.xyz", os.path.join("scan_points", "point_%03d.xyz" % target))
        shutil.copy("xtbopt.xyz", geometry)

    with open("xtb_scan.csv", "w") as f:
        f.write("target_deg,achieved_dihedral_deg,E_Eh,rel_kcal_mol,converged\n")
        for target, achieved, energy, converged in rows:
            ref = rows[0][2]
            f.write("%.1f,%.2f,%.12f,%.3f,%s\n"
                    % (target, achieved, energy, (energy - ref) * 627.5095, converged))
    open("xtb_scan_transcript.txt", "w").write("".join(transcript))
    print(open("xtb_scan.csv").read())


if __name__ == "__main__":
    main()
