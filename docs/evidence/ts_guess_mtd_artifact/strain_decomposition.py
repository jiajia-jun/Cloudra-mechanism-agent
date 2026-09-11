"""Where does the guess frame's 44.9 kcal/mol actually live?

The SOP's "TS candidate" is xTB path frame 10.  This script takes it apart with four
well-defined constructs, all quoted against the same xTB/GFN2 minimum
(xtb_scan_block_probe.out in this directory):

  A  frame 10, single point                          -> its own energy
  B  the relaxed reactant rigidly rotated about the biaryl axis to frame 10's torsion
     (a physically sensible structure on that torsion; built here from scratch)
  C  frame 10's heavy skeleton with the hydrogens relaxed (heavy atoms frozen)
  D  free relaxation of frame 10                     -> which basin it belongs to

B separates "the torsion costs this much" from "the rest of the geometry is off";
C separates "the hydrogen positions cost this much" from "the heavy skeleton is off".

xTB 6.7.1 as built here has no working atom-freezing block ($fix and $constrain atoms:
were both probed and neither holds the heavy atoms), so C uses an MMFF94 relaxation of
the hydrogens on the frozen heavy skeleton, followed by a GFN2 single point.  The same
MMFF step is applied to B as a control, which measures the method bias of that probe.

Run:  uv run --project <repo> python strain_decomposition.py <workdir>
Writes strain_decomposition_summary.txt plus the geometries it builds.
"""
import math
import os
import subprocess
import sys

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

HERE = os.path.dirname(os.path.abspath(__file__))
K = 627.5095
MIN = -37.106620806098          # xTB minimum, verbatim in xtb_scan_block_probe.out
TORSION = (1, 6, 7, 8)          # 0-based C1-C6-C7-C8
# ring B = C7, C8, C9(methyl), C10..C13 and their hydrogens
FRAGMENT = (7, 8, 9, 10, 11, 12, 13, 21, 22, 23, 24, 25, 26, 27)
HEAVY = 14                      # first 14 atoms are the heavy skeleton
METHYL_H = {0: (14, 15, 16), 9: (21, 22, 23)}


def read_xyz(path):
    lines = open(path).read().splitlines()
    n = int(lines[0].strip())
    symbols = [row.split()[0] for row in lines[2:2 + n]]
    coords = [np.array([float(x) for x in row.split()[1:4]]) for row in lines[2:2 + n]]
    return symbols, coords


def write_xyz(path, symbols, coords, comment):
    with open(path, "w") as handle:
        handle.write("%d\n%s\n" % (len(symbols), comment))
        for symbol, point in zip(symbols, coords):
            handle.write("%-3s %18.10f %18.10f %18.10f\n" % (symbol, *point))


def split_frames(path):
    lines = open(path).read().splitlines()
    out, i = [], 0
    while i < len(lines):
        n = int(lines[i].strip())
        out.append("\n".join(lines[i:i + 2 + n]) + "\n")
        i += 2 + n
    return out


def dihedral(coords, idx=TORSION):
    p = [coords[t] for t in idx]
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


def single_point(work, xyz):
    proc = subprocess.run(["xtb", xyz, "--sp"], cwd=work, capture_output=True, text=True)
    return total_energy(proc.stdout + proc.stderr)


def relax(work, xyz, out_name):
    proc = subprocess.run(["xtb", xyz, "--opt"], cwd=work, capture_output=True, text=True)
    os.replace(os.path.join(work, "xtbopt.xyz"), os.path.join(work, out_name))
    return total_energy(proc.stdout + proc.stderr)


def rotate_fragment(coords, angle_deg):
    """Rodrigues rotation of the ring-B fragment about the C6-C7 axis."""
    out = [p.copy() for p in coords]
    a, b = coords[6], coords[7]
    axis = (b - a) / np.linalg.norm(b - a)
    ang = math.radians(angle_deg)
    for i in FRAGMENT:
        v = coords[i] - a
        out[i] = (a + v * math.cos(ang) + np.cross(axis, v) * math.sin(ang)
                  + axis * np.dot(axis, v) * (1 - math.cos(ang)))
    return out


def h_only_mmff(topology, symbols, coords, out_path):
    """Relax hydrogens with MMFF94 while every heavy atom is fixed."""
    mol = Chem.MolFromMolFile(topology, removeHs=False)
    if mol is None or mol.GetNumAtoms() != len(coords):
        raise RuntimeError("topology does not match the geometry")
    conformer = Chem.Conformer(mol.GetNumAtoms())
    for i, point in enumerate(coords):
        conformer.SetAtomPosition(i, Point3D(*[float(x) for x in point]))
    mol.RemoveAllConformers()
    mol.AddConformer(conformer, assignId=True)
    field = AllChem.MMFFGetMoleculeForceField(mol, AllChem.MMFFGetMoleculeProperties(mol))
    for i in range(HEAVY):
        field.AddFixedPoint(i)
    field.Minimize(maxIts=5000)
    final = mol.GetConformer()
    new = [np.array(final.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]
    write_xyz(out_path, symbols, new, "heavy skeleton frozen, hydrogens relaxed with MMFF94")
    return new


def main():
    work = sys.argv[1]
    os.makedirs(work, exist_ok=True)
    frames = split_frames(os.path.join(HERE, "xtbpath.xyz"))
    open(os.path.join(work, "frame00.xyz"), "w").write(frames[0])
    open(os.path.join(work, "frame10.xyz"), "w").write(frames[10])
    symbols, g10 = read_xyz(os.path.join(work, "frame10.xyz"))

    report = ["all energies relative to the xTB minimum %.12f Eh" % MIN, ""]

    # A: frame 10 as given
    e_g10 = single_point(work, "frame10.xyz")
    # D: free relaxation of frame 10 -> which basin?
    e_free = relax(work, "frame10.xyz", "relaxed_from_guess.xyz")
    _, relaxed = read_xyz(os.path.join(work, "relaxed_from_guess.xyz"))
    # B: relaxed reactant rigidly rotated to frame 10's torsion
    target = dihedral(g10)
    start = dihedral(relaxed)
    sign = None
    for candidate in (+1, -1):
        trial = rotate_fragment(relaxed, candidate * (target - start))
        if abs(dihedral(trial) - target) < 1.0:
            sign = candidate
            break
    if sign is None:
        raise RuntimeError("could not rotate the fragment onto the target torsion")
    rigid = rotate_fragment(relaxed, sign * (target - start))
    write_xyz(os.path.join(work, "rigid_reference.xyz"), symbols, rigid,
              "relaxed reactant, ring B rigidly rotated to %.2f deg" % target)
    e_rigid = single_point(work, "rigid_reference.xyz")
    # C: heavy skeleton frozen, hydrogens relaxed (MMFF, then GFN2 single point)
    h_relaxed = h_only_mmff(os.path.join(HERE, "xtbtopo.mol"), symbols, g10,
                            os.path.join(work, "h_only.xyz"))
    e_h = single_point(work, "h_only.xyz")
    # control: same MMFF probe applied to the rigid reference (method bias)
    h_only_mmff(os.path.join(HERE, "xtbtopo.mol"), symbols, rigid,
                os.path.join(work, "h_only_rigid.xyz"))
    e_h_rigid = single_point(work, "h_only_rigid.xyz")

    def rel(energy):
        return (energy - MIN) * K

    report += [
        "A  frame 10 (the SOP's TS candidate), single point        : %+8.3f kcal/mol" % rel(e_g10),
        "B  relaxed reactant rotated to the same torsion (%.2f deg): %+8.3f kcal/mol"
        % (target, rel(e_rigid)),
        "   -> cost of that torsion alone                          : %+8.3f kcal/mol"
        % (rel(e_rigid)),
        "C  frame 10 heavy skeleton + MMFF-relaxed hydrogens       : %+8.3f kcal/mol" % rel(e_h),
        "   -> strain stored in the hydrogen positions             : %+8.3f kcal/mol"
        % (rel(e_g10) - rel(e_h)),
        "   -> strain left in the heavy skeleton                   : %+8.3f kcal/mol"
        % (rel(e_h) - rel(e_rigid)),
        "D  free relaxation of frame 10                            : %+8.3f kcal/mol"
        % rel(e_free),
        "   -> torsion after free relaxation                        : %8.2f deg" % dihedral(relaxed),
        "",
        "control (method bias of the MMFF hydrogen probe):",
        "   rigid reference as built                                : %+8.3f kcal/mol" % rel(e_rigid),
        "   rigid reference + MMFF-relaxed hydrogens                : %+8.3f kcal/mol" % rel(e_h_rigid),
        "   -> probe bias                                           : %+8.3f kcal/mol"
        % (rel(e_h_rigid) - rel(e_rigid)),
        "",
        "geometric facts for the same three structures:",
    ]
    for label, coords in (("frame 10", g10), ("rigid reference", rigid),
                          ("h-only", h_relaxed)):
        hh = min(float(np.linalg.norm(coords[i] - coords[j]))
                 for i in METHYL_H[0] for j in METHYL_H[9])
        report.append("   %-16s torsion %8.2f deg   methyl C..C %.3f   min H..H %.3f"
                      % (label, dihedral(coords), float(np.linalg.norm(coords[0] - coords[9])), hh))
    report.append("   %-16s max hydrogen displacement vs frame 10: %.3f A"
                  % ("h-only", max(float(np.linalg.norm(h_relaxed[i] - g10[i]))
                                   for i in range(HEAVY, len(g10)))))
    report.append("   %-16s max heavy-atom displacement vs frame 10: %.4f A"
                  % ("h-only", max(float(np.linalg.norm(h_relaxed[i] - g10[i]))
                                  for i in range(HEAVY))))

    text = "\n".join(report) + "\n"
    open(os.path.join(work, "strain_decomposition_summary.txt"), "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
