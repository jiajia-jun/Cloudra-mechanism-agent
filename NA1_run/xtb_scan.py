#!/usr/bin/env python3
"""
xtb relaxed constrained scan driver for NA1 TS2 (C-C bond formation).
Bash bypass (no xtb scheduler path / no log_parser for xtb).

Reaction coordinate: enolate C2 (atom 1) -> acetaldehyde carbonyl C6 (atom 8).
Constraint: distance C2=C6 fixed; all other DOF relaxed by xtb --opt tight.
Sequential: start each distance from the previous optimized geometry (continuity).
Record energy + key bond distances per frame. Charge -1, singlet.
"""
import os, re, subprocess, sys
import numpy as np

XTBBIN = "/Users/cloudrayyy/miniconda3/envs/chemai/bin/xtb"
WORKDIR = "/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_run"
os.chdir(WORKDIR)

ATOMS = (1, 8)          # 1-based C2 (enolate CH2), C6 (aldehyde carbonyl C)
CHRG = -1
UHF = 0

# target C2-C6 distances from pre-organized complex (2.9) toward product (~1.6)
distances = [2.90, 2.75, 2.60, 2.45, 2.30, 2.20, 2.10, 2.00, 1.90, 1.80, 1.70, 1.60]


def read_xyz(path):
    lines = open(path).read().splitlines()
    n = int(lines[0].strip())
    title = lines[1]
    atoms = [l.split()[0] for l in lines[2:2 + n]]
    coords = np.array([[float(x) for x in l.split()[1:4]] for l in lines[2:2 + n]])
    return n, atoms, coords, title


def write_xyz(path, n, atoms, coords, title="xtb frame"):
    with open(path, "w") as f:
        f.write(f"{n}\n{title}\n")
        for a, c in zip(atoms, coords):
            f.write(f"{a:2s}  {c[0]: .12f}  {c[1]: .12f}  {c[2]: .12f}\n")


def make_xcontrol(dist, path):
    with open(path, "w") as f:
        f.write("$constrain\n")
        f.write(f"    atoms: {ATOMS[0]},{ATOMS[1]}\n")
        f.write(f"    distance: {ATOMS[0]},{ATOMS[1]},{dist:.3f}\n")
        f.write("    force constant=1.0\n")
        f.write("$end\n")


def run_xtb(geom, dist):
    """Run xtb constrained opt at fixed C2-C6=dist. Return (energy, opt_ok, logpath)."""
    con = f"constr_{dist:.2f}.xcontrol"
    make_xcontrol(dist, con)
    log = f"scan_d{dist:.2f}.log"
    cmd = [XTBBIN, geom, "--opt", "tight", "--input", con,
           "--chrg", str(CHRG), "--uhf", str(UHF)]
    with open(log, "w") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    txt = open(log).read()
    en = None
    m = re.findall(r"TOTAL ENERGY\s+(-?\d+\.\d+)\s+Eh", txt)
    if m:
        en = float(m[-1])
    ok = "GEOMETRY OPTIMIZATION CONVERGED" in txt
    return en, ok, log


def key_dist(coords):
    d = lambda i, j: float(np.linalg.norm(coords[i - 1] - coords[j - 1]))
    return d(1, 8), d(1, 2), d(8, 9), d(2, 3), d(3, 9), d(3, 14)


# start from the pre-organized complex geometry
n, atoms, coords, _ = read_xyz("central_complex.xyz")
geom = "central_complex.xyz"

rows = []
for dist in distances:
    en, ok, log = run_xtb(geom, dist)
    # read the optimized geometry xtb wrote (xtbopt.xyz) for the next step
    frame = f"scanframe_{dist:.2f}.xyz"
    if os.path.exists("xtbopt.xyz"):
        n, atoms, coords, _ = read_xyz("xtbopt.xyz")
        geom = "xtbopt.xyz"
        write_xyz(frame, n, atoms, coords, f"xtb relaxed C2-C6 target {dist:.2f}")
    dcc, dC2C3, dC6O7, dC3O4, dO4O7, dO4w = key_dist(coords)
    rows.append((dist, en, ok, dcc, dC2C3, dC6O7, dC3O4, dO4O7, dO4w))
    print(f"C2-C6(target)={dist:.2f}  E={en!s:>12}  conv={ok}  "
          f"rel C-C={dcc:.3f}  C2=C3={dC2C3:.3f}  C6=O7={dC6O7:.3f}  C3-O4={dC3O4:.3f}  O4-O7={dO4O7:.3f}  O4-Ow={dO4w:.3f}")

with open("scan_profile.csv", "w") as f:
    f.write("target_C2C6,E_Eh,converged,C2C6,C2C3,C6O7,C3O4,O4O7,O4Ow\n")
    for r in rows:
        f.write(f"{r[0]:.2f},{r[1]},{r[2]},{r[3]:.3f},{r[4]:.3f},{r[5]:.3f},{r[6]:.3f},{r[7]:.3f},{r[8]:.3f}\n")

# identify the energy maximum (TS candidate) among converged frames
maxr = max((r for r in rows if r[2]), key=lambda r: r[1])
i = rows.index(maxr)
print(f"\nMAX (TS candidate): target={rows[i][0]:.2f}  E={rows[i][1]:.6f}  relC-C={rows[i][3]:.3f}")
print("\nSaving constrained-optimized frames + profile. Done.")
