"""Is the SOP's "TS candidate" a transition state, or the reactant itself?

Three measurements, all at xTB/GFN2 level on the verbatim path frames in this directory:

1. how far the guess (frame 10) is from the reactant (frame 0): torsion difference, RMSD,
   max atom displacement, heavy-atom-only displacement;
2. a free relaxation of the guess (no constraint).  A genuine TS guess stays in a saddle
   region; a strained reactant falls straight back to the reactant minimum;
3. a relaxation of the guess with *its own* torsion held fixed, which separates the
   torsional cost of that geometry from everything else.

Run:  python3 xtb_guess_basin_check.py <workdir>
Writes guess.xyz / reactant.xyz / free_relax.out / free_final.xyz / hold_relax.out /
hold_final.xyz / basin_check_summary.txt
"""
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
K = 627.5095
# xTB minimum, verbatim in xtb_scan_block_probe.out (this directory)
XTBMIN = -37.106620806098
TORSION = (1, 6, 7, 8)          # 0-based C1-C6-C7-C8
# xTB's `$constrain dihedral` target is offset by 180 deg from the ordinary dihedral
# convention in this build (see README section 5 item 3), hence 180 - (-108.03).
HOLD_TARGET = 180.0 - -108.03
METHYL_H = {0: (14, 15, 16), 9: (21, 22, 23)}


def split_frames(path):
    lines = open(path).read().splitlines()
    out, i = [], 0
    while i < len(lines):
        n = int(lines[i].strip())
        out.append("\n".join(lines[i:i + 2 + n]) + "\n")
        i += 2 + n
    return out


def read_xyz(path):
    lines = open(path).read().splitlines()
    n = int(lines[0].strip())
    symbols = [row.split()[0] for row in lines[2:2 + n]]
    coords = [np.array([float(x) for x in row.split()[1:4]]) for row in lines[2:2 + n]]
    return symbols, coords


def dihedral(at):
    p = [at[i] for i in TORSION]
    b0, b1, b2 = p[0] - p[1], p[2] - p[1], p[3] - p[2]
    n1, n2 = np.cross(b0, b1), np.cross(b1, b2)
    m = np.cross(n1, b1 / np.linalg.norm(b1))
    return math.degrees(math.atan2(float(np.dot(m, n2)), float(np.dot(n1, n2))))


def total_energy(text):
    for line in text.splitlines():
        if "TOTAL ENERGY" in line:
            tok = line.replace("|", " ").split()
            return float(tok[tok.index("ENERGY") + 1])
    raise RuntimeError("no TOTAL ENERGY in output")


def run_xtb(work, geometry, extra_input=None):
    cmd = ["xtb", geometry, "--opt"]
    if extra_input:
        cmd += ["--input", extra_input]
    proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    return proc.stdout + proc.stderr


def main():
    work = sys.argv[1]
    os.makedirs(work, exist_ok=True)
    frames = split_frames(os.path.join(HERE, "xtbpath.xyz"))
    open(os.path.join(work, "guess.xyz"), "w").write(frames[10])
    open(os.path.join(work, "reactant.xyz"), "w").write(frames[0])
    report = []

    sym_g, guess = read_xyz(os.path.join(work, "guess.xyz"))
    _, reactant = read_xyz(os.path.join(work, "reactant.xyz"))
    disp = [float(np.linalg.norm(guess[i] - reactant[i])) for i in range(len(guess))]
    heavy = [i for i, s in enumerate(sym_g) if s != "H"]
    report.append("guess (frame 10) vs reactant (frame 0):")
    report.append("  torsion C1-C6-C7-C8      : %.2f deg  vs %.2f deg  (delta %+.2f)"
                  % (dihedral(guess), dihedral(reactant), dihedral(guess) - dihedral(reactant)))
    report.append("  all-atom RMSD (no fit)   : %.3f A"
                  % (sum(d * d for d in disp) / len(disp)) ** 0.5)
    report.append("  max atom displacement    : %.3f A (atom %d, %s)"
                  % (max(disp), int(np.argmax(disp)), sym_g[int(np.argmax(disp))]))
    report.append("  heavy-atom RMSD (no fit) : %.3f A"
                  % (sum(disp[i] ** 2 for i in heavy) / len(heavy)) ** 0.5)
    report.append("  max heavy-atom displ.    : %.3f A (atom %d)"
                  % (max(disp[i] for i in heavy), max(heavy, key=lambda i: disp[i])))
    report.append("  methyl H..H (min)        : %.3f A  vs %.3f A"
                  % (min(float(np.linalg.norm(guess[i] - guess[j]))
                         for i in METHYL_H[0] for j in METHYL_H[9]),
                     min(float(np.linalg.norm(reactant[i] - reactant[j]))
                         for i in METHYL_H[0] for j in METHYL_H[9])))

    free_out = run_xtb(work, "guess.xyz")
    open(os.path.join(work, "free_relax.out"), "w").write(free_out)
    os.replace(os.path.join(work, "xtbopt.xyz"), os.path.join(work, "free_final.xyz"))

    block = "$constrain\n   dihedral: 2, 7, 8, 9, %.1f\n   force constant=5.0\n$end\n" % HOLD_TARGET
    open(os.path.join(work, "hold.inp"), "w").write(block)
    hold_out = run_xtb(work, "guess.xyz", extra_input="hold.inp")
    open(os.path.join(work, "hold_relax.out"), "w").write(hold_out)
    os.replace(os.path.join(work, "xtbopt.xyz"), os.path.join(work, "hold_final.xyz"))

    report.append("")
    report.append("free relaxation of the guess (no constraint):")
    e_free = total_energy(free_out)
    _, free_final = read_xyz(os.path.join(work, "free_final.xyz"))
    report.append("  E = %.12f Eh  (xTB minimum %+.3f kcal/mol)" % (e_free, (e_free - XTBMIN) * K))
    report.append("  lands at torsion %.2f deg, methyl H..H %.3f A"
                  % (dihedral(free_final),
                     min(float(np.linalg.norm(free_final[i] - free_final[j]))
                         for i in METHYL_H[0] for j in METHYL_H[9])))
    report.append("")
    report.append("relaxation with the guess's own torsion held (target %.1f deg):" % HOLD_TARGET)
    e_hold = total_energy(hold_out)
    _, hold_final = read_xyz(os.path.join(work, "hold_final.xyz"))
    report.append("  E = %.12f Eh  (xTB minimum %+.3f kcal/mol)" % (e_hold, (e_hold - XTBMIN) * K))
    report.append("  achieved torsion %.2f deg, methyl H..H %.3f A"
                  % (dihedral(hold_final),
                     min(float(np.linalg.norm(hold_final[i] - hold_final[j]))
                         for i in METHYL_H[0] for j in METHYL_H[9])))
    report.append("")
    report.append("the guess frame's own single point, for reference:")
    open(os.path.join(work, "guess_sp.xyz"), "w").write(frames[10])
    sp_out = subprocess.run(["xtb", "guess_sp.xyz", "--sp"], cwd=work,
                            capture_output=True, text=True)
    e_guess = total_energy(sp_out.stdout + sp_out.stderr)
    report.append("  E = %.12f Eh  (xTB minimum %+.3f kcal/mol)" % (e_guess, (e_guess - XTBMIN) * K))

    text = "\n".join(report) + "\n"
    open(os.path.join(work, "basin_check_summary.txt"), "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
