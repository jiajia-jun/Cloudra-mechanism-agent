"""Re-derive every number quoted in README.md from the verbatim files in this directory.

Run:  python3 verify_claims.py
Exits non-zero on the first claim that no longer holds, so the dossier cannot silently rot.
"""
import csv
import math
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
K = 627.5095

# reference: free xTB optimization minimum, verbatim in xtb_scan_block_probe.out
FREE_MIN = -37.106620806098
# reference: B3LYP/def2-SVP minimum, verbatim in refmin_stdout.log
B3LYP_MIN = -541.189617864318

RING_A = (1, 2, 3, 4, 5, 6)
RING_B = (7, 8, 10, 11, 12, 13)
METHYL_H = {0: (14, 15, 16), 9: (21, 22, 23)}

checks = []


def check(name, got, want, tol=1e-3):
    ok = abs(got - want) <= tol
    checks.append((ok, name, got, want))
    if not ok:
        raise AssertionError("%s: got %r, want %r" % (name, got, want))


def check_true(name, value):
    checks.append((bool(value), name, value, True))
    if not value:
        raise AssertionError(name)


def read_frames(path):
    lines = open(path).read().splitlines()
    frames, i = [], 0
    while i < len(lines):
        n = int(lines[i].strip())
        frames.append((lines[i + 1],
                       [np.array([float(x) for x in row.split()[1:4]])
                        for row in lines[i + 2:i + 2 + n]]))
        i += 2 + n
    return frames


def read_xyz(path):
    lines = open(path).read().splitlines()
    n = int(lines[0].strip())
    return [np.array([float(x) for x in row.split()[1:4]]) for row in lines[2:2 + n]]


def dihedral(at, idx):
    p = [at[i] for i in idx]
    b0, b1, b2 = p[0] - p[1], p[2] - p[1], p[3] - p[2]
    n1, n2 = np.cross(b0, b1), np.cross(b1, b2)
    m = np.cross(n1, b1 / np.linalg.norm(b1))
    return math.degrees(math.atan2(float(np.dot(m, n2)), float(np.dot(n1, n2))))


def planarity(at, idx):
    pts = np.array([at[i] for i in idx])
    centre = pts.mean(axis=0)
    normal = np.linalg.svd(pts - centre)[2][2]
    return max(abs(float(np.dot(p - centre, normal))) for p in pts)


def methyl_hh(at):
    return min(float(np.linalg.norm(at[i] - at[j]))
               for i in METHYL_H[0] for j in METHYL_H[9])


def single_points(path):
    log = open(path, errors="replace").read().splitlines()
    return [float(row.split()[-1]) for row in log
            if row.strip().startswith("FINAL SINGLE POINT ENERGY")]


def main():
    frames = read_frames(os.path.join(HERE, "xtbpath.xyz"))
    check_true("xtbpath.xyz has 48 frames", len(frames) == 48)
    check("frame 0 theta", dihedral(frames[0][1], (1, 6, 7, 8)), -86.62, 0.01)
    check("frame 10 theta", dihedral(frames[10][1], (1, 6, 7, 8)), -108.03, 0.01)
    check("frame 10 relative energy (comment)", float(frames[10][0].split()[1]), 44.865, 1e-3)
    check_true("frame 0 == path_reactant.xyz (same coordinates, atol 1e-8)",
               np.allclose(np.array(frames[0][1]), np.array(read_xyz(HERE + "/path_reactant.xyz")),
                           atol=1e-8))
    check_true("frame 10 == xtbpath_ts.xyz (same coordinates, atol 1e-8)",
               np.allclose(np.array(frames[10][1]), np.array(read_xyz(HERE + "/xtbpath_ts.xyz")),
                           atol=1e-8))

    at10 = frames[10][1]
    at0 = frames[0][1]
    check("frame 10 ring A planarity", planarity(at10, RING_A), 0.0513, 5e-4)
    check("frame 10 ring B planarity", planarity(at10, RING_B), 0.0567, 5e-4)
    check("frame 0 ring B planarity", planarity(at0, RING_B), 0.0012, 5e-4)
    check("frame 10 methyl C..C", float(np.linalg.norm(at10[0] - at10[9])), 3.050, 5e-4)
    check("frame 10 methyl min H..H", methyl_hh(at10), 1.932, 5e-4)
    check("frame 0 methyl min H..H", methyl_hh(at0), 2.685, 5e-4)
    check("frame 10 axis bond", float(np.linalg.norm(at10[6] - at10[7])), 1.443, 5e-4)
    check("frame 0 axis bond", float(np.linalg.norm(at0[6] - at0[7])), 1.474, 5e-4)
    check("frame 10 max atom displacement vs frame 0",
          max(float(np.linalg.norm(at10[i] - at0[i])) for i in range(len(at0))), 1.292, 5e-4)

    # absolute single points of three path frames (section 3.2 anchors)
    def sp_energy(index):
        text = open(HERE + "/sp_frame%02d.out" % index, errors="replace").read()
        line = [row for row in text.splitlines() if "TOTAL ENERGY" in row][0]
        tok = line.replace("|", " ").split()
        return float(tok[tok.index("ENERGY") + 1])

    check("frame 0 absolute energy", sp_energy(0), -37.1025803937, 1e-9)
    check("frame 10 absolute energy", sp_energy(10), -37.0310839405, 1e-9)
    check("frame 46 absolute energy", sp_energy(46), -37.1058942701, 1e-9)
    check("frame 0 above free minimum", (sp_energy(0) - FREE_MIN) * K, 2.535, 2e-3)
    check("frame 10 (the guess) above free minimum", (sp_energy(10) - FREE_MIN) * K, 47.400, 2e-3)
    check("frame 46 above free minimum", (sp_energy(46) - FREE_MIN) * K, 0.456, 2e-3)

    # section 3.3: is the guess just a strained copy of the reactant?
    summary = open(HERE + "/basin_check_summary.txt", errors="replace").read()
    nums = {}
    for line in summary.splitlines():
        if ":" in line:
            key = line.split(":")[0].strip()
            body = line.split(":", 1)[1]
            vals = []
            for token in (body.replace("deg", " ").replace("A", " ")
                         .replace("(", " ").replace(")", " ").split()):
                try:
                    vals.append(float(token))
                except ValueError:
                    pass
            if vals:
                nums[key] = vals
    check("guess vs reactant: all-atom RMSD", nums["all-atom RMSD (no fit)"][0], 0.780, 1e-3)
    check("guess vs reactant: max atom displacement", nums["max atom displacement"][0], 1.292, 1e-3)
    check("guess vs reactant: heavy-atom RMSD", nums["heavy-atom RMSD (no fit)"][0], 0.534, 1e-3)
    check("guess vs reactant: max heavy-atom displacement", nums["max heavy-atom displ."][0], 0.900, 1e-3)
    check("guess vs reactant: torsion difference", nums["torsion C1-C6-C7-C8"][2], -21.41, 5e-3)
    check("guess methyl H..H", nums["methyl H..H (min)"][0], 1.932, 1e-3)
    check("reactant methyl H..H", nums["methyl H..H (min)"][1], 2.685, 1e-3)

    free = re.search(r"free relaxation of the guess \(no constraint\):\n"
                     r"  E = ([-0-9.]+) Eh  \(xTB minimum ([-+0-9.]+) kcal/mol\)\n"
                     r"  lands at torsion ([-0-9.]+) deg, methyl H\.\.H ([0-9.]+) A", summary)
    check_true("free relaxation of the guess is reported", free is not None)
    check("free relaxation of the guess lands on the xTB minimum",
          float(free.group(2)), 0.0, 5e-2)
    check("free relaxation of the guess lands near the reactant torsion",
          abs(abs(float(free.group(3))) - 86.62), 0.0, 3.0)

    hold = re.search(r"own torsion held \(target [-0-9.]+ deg\):\n"
                     r"  E = ([-0-9.]+) Eh  \(xTB minimum ([-+0-9.]+) kcal/mol\)\n"
                     r"  achieved torsion ([-0-9.]+) deg", summary)
    check_true("held-torsion relaxation is reported", hold is not None)
    check("holding the guess's own torsion leaves only ~1 kcal/mol of strain",
          float(hold.group(2)), 0.994, 5e-3)
    check("held torsion equals the guess's torsion", float(hold.group(3)), -107.90, 0.1)
    own = re.search(r"own single point, for reference:\n  E = [-0-9.]+ Eh  "
                    r"\(xTB minimum ([-+0-9.]+) kcal/mol", summary)
    check("the guess frame's own single point", float(own.group(1)), 47.400, 2e-3)

    # free minimum / $scan probe (section 5 item 4)
    probe = open(HERE + "/xtb_scan_block_probe.out", errors="replace").read()
    line = [row for row in probe.splitlines() if "TOTAL ENERGY" in row][0]
    tok = line.replace("|", " ").split()
    check("free minimum E from probe", float(tok[tok.index("ENERGY") + 1]), FREE_MIN, 1e-9)
    check_true("$scan block silently ignored (no scan step in probe output)",
               probe.count("scan") == 1 and "GEOMETRY OPTIMIZATION CONVERGED" in probe)

    # scan table
    rows = list(csv.DictReader(open(HERE + "/xtb_scan.csv")))
    check_true("scan has 19 points", len(rows) == 19)
    energies = {round(float(r["target_deg"])): float(r["E_Eh"]) for r in rows}
    check("scan at |theta|~110 (target 70)", (energies[70] - FREE_MIN) * K, 0.303, 2e-3)
    check("scan at |theta|~70 (target 110)", (energies[110] - FREE_MIN) * K, 0.161, 2e-3)
    check("scan planar end (target 0)", (energies[0] - FREE_MIN) * K, 18.328, 2e-3)
    check("scan planar end (target 180)", (energies[180] - FREE_MIN) * K, 14.264, 2e-3)
    check("scan maximum (target 10)", (energies[10] - FREE_MIN) * K, 23.850, 2e-3)
    check("scan maximum is at target 10 not at the guess's torsion",
          max(energies, key=lambda t: energies[t]), 10, 0.5)
    check("relaxed cost at the guess's own torsion stays < 0.5 kcal/mol",
          (energies[70] - FREE_MIN) * K, 0.303, 2e-3)

    # DFT side
    check("B3LYP min theta", dihedral(read_xyz(HERE + "/refmin_b3lyp_geometry.xyz"), (1, 6, 7, 8)),
          -87.99, 0.01)
    check("OptTS final geometry theta",
          dihedral(read_xyz(HERE + "/optts_final_geometry.xyz"), (1, 6, 7, 8)), -99.31, 0.01)
    min_sp = single_points(HERE + "/refmin_stdout.log")
    check_true("reference minimum converged",
               "OPTIMIZATION RUN DONE" in open(HERE + "/refmin_stdout.log").read()
               and "ORCA TERMINATED NORMALLY" in open(HERE + "/refmin_stdout.log").read())
    check("B3LYP minimum energy", min_sp[-1], B3LYP_MIN, 1e-9)

    opt_log = open(HERE + "/optts_stdout.log", errors="replace").read()
    opt_sp = single_points(HERE + "/optts_stdout.log")
    check_true("OptTS ran 56 geometry cycles",
               len(re.findall(r"GEOMETRY OPTIMIZATION CYCLE", opt_log)) == 56)
    check_true("OptTS never converged",
               "OPTIMIZATION RUN DONE" not in opt_log and "ORCA TERMINATED" not in opt_log)
    check("OptTS cycle 1 (guess single point) above minimum", (opt_sp[0] - B3LYP_MIN) * K, 59.86, 2e-2)
    check("OptTS last cycle above minimum", (opt_sp[-1] - B3LYP_MIN) * K, 0.644, 2e-3)
    counts = {}
    for line in opt_log.splitlines():
        m = re.search(r"Hessian has +(\d+) negative", line)
        if m:
            counts[int(m.group(1))] = counts.get(int(m.group(1)), 0) + 1
    check_true("OptTS Hessian negative-eigenvalue counts == {0:3, 1:42, 2:5, 3:4, 4:1}",
               counts == {0: 3, 1: 42, 2: 5, 3: 4, 4: 1})
    eig = [float(row.split()[row.split().index("eigenvalue") + 1])
           for row in opt_log.splitlines() if "TS mode is mode number" in row]
    check("max 'TS mode' eigenvalue is positive (noise, not a TS mode)", max(eig), 0.00038, 5e-5)

    # section 6: the refinement ceiling decides everything
    def sweep(cap):
        text = open(HERE + "/refinement_sweep/run_nrun%d.out" % cap, errors="replace").read()
        lines = text.splitlines()
        barriers = [float(row.split(":")[-1]) for row in lines if "forward  barrier (kcal)" in row]
        cycles = sum(1 for row in lines if row.strip().startswith("refinement cycle"))
        terminations = [row.strip() for row in lines
                        if row.strip().startswith("terminated because")]
        return cycles, barriers[-1], terminations[-1]

    cycles10, barrier10, term10 = sweep(10)
    cycles30, barrier30, term30 = sweep(30)
    cycles100, barrier100, term100 = sweep(100)
    check("nrun=10 last barrier", barrier10, 26.629, 1e-3)
    check("nrun=30 last barrier", barrier30, 18.290, 1e-3)
    check("nrun=10 hit the ceiling", cycles10, 10, 0)
    check("nrun=30 hit the ceiling", cycles30, 30, 0)
    check_true("nrun=10/30 were truncated, nrun=100 was not",
               "max. # cycles reached" in term10 and "max. # cycles reached" in term30
               and term100 == "terminated because grad at TS <threshold")
    check("nrun=100 converged barrier", barrier100, 18.299, 1e-3)
    check("nrun=100 converged at 31 cycles", cycles100, 31, 0)

    # the converged path's highest frame sits on the torsion maximum
    path = read_frames(HERE + "/refinement_sweep/converged_path.xyz")
    best = max(range(len(path)), key=lambda k: float(path[k][0].split()[1]))
    check("converged path frame count", len(path), 47, 0)
    check("converged path maximum frame index", best, 22, 0)
    check("torsion at the converged path maximum", dihedral(path[best][1], (1, 6, 7, 8)), -5.74, 0.01)
    check("converged path maximum relative energy (comment)",
          float(path[best][0].split()[1]), 18.299, 1e-3)
    candidate = read_xyz(HERE + "/refinement_sweep/converged_ts_candidate.xyz")
    check("converged TS candidate torsion", dihedral(candidate, (1, 6, 7, 8)), -5.74, 0.01)

    # the OptTS started from that candidate converged in 9 cycles to a first-order saddle
    opt = open(HERE + "/refinement_sweep/orca_optts_from_converged_guess.log",
               errors="replace").read()
    check_true("OptTS from the converged guess declared convergence",
               "OPTIMIZATION RUN DONE" in opt and "ORCA TERMINATED NORMALLY" in opt)
    check_true("OptTS from the converged guess ran 9 geometry cycles",
               len(re.findall(r"GEOMETRY OPTIMIZATION CYCLE", opt)) == 9)
    converged_sp = single_points(HERE + "/refinement_sweep/orca_optts_from_converged_guess.log")
    check("OptTS cycle-1 single point above the B3LYP minimum",
          (converged_sp[0] - B3LYP_MIN) * K, 20.09, 2e-2)
    check("OptTS final energy above the B3LYP minimum",
          (converged_sp[-1] - B3LYP_MIN) * K, 16.03, 2e-2)
    # the B3LYP saddle itself is the coplanar arrangement (the guess sat 5.7 deg off it)
    check("OptTS final geometry torsion (coplanar TS)",
          dihedral(read_xyz(HERE + "/refinement_sweep/orca_optts_final_geometry.xyz"),
                   (1, 6, 7, 8)), 0.03, 0.05)

    # a path that never converges, for the runner's invariant
    water = open(HERE + "/refinement_sweep/water_never_converges_1000cycles.log",
                 errors="replace").read()
    check_true("the water O-H stretch path never converges (1000 cycles, still truncated)",
               "terminated because max. # cycles reached" in water
               and "grad at TS <threshold" not in water)

    # the method-spelling side finding
    first = open(HERE + "/first_attempt_keyword_error.txt").read()
    check_true("ORCA refused the SOP's persisted method spelling",
               "def2svp" in first and "UNRECOGNIZED OR DUPLICATED KEYWORD" in first
               and "DEF2SVP" in first)

    for ok, name, got, want in checks:
        print("PASS  %-64s got=%s want=%s" % (name, got, want))
    print("\n%d/%d claims verified from the verbatim files in this directory."
          % (sum(1 for c in checks if c[0]), len(checks)))


if __name__ == "__main__":
    main()
