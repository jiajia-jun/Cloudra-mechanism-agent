"""Derived quantities for every frame of the xTB MTD path (xtbpath.xyz, verbatim).

Atom indices are 0-based, matching the builder output order of this 28-atom system:
  C0  methyl carbon on ring A        ring A aromatic carbons = C1..C6
  C6  biaryl carbon (ring A side)    C7  biaryl carbon (ring B side)
  C8  ortho carbon of ring B         C9  methyl carbon on ring B
  ring B aromatic carbons = C7, C8, C10, C11, C12, C13
The biaryl axis bond is C6-C7; theta = dihedral(C1, C6, C7, C8); the two ortho
substituents are the methyls C0 and C9.

Usage: python3 path_analysis.py > path_frames.csv
"""
import math

import numpy as np

HERE = __file__.rsplit("/", 1)[0]


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


RING_A = (1, 2, 3, 4, 5, 6)
RING_B = (7, 8, 10, 11, 12, 13)
METHYL_H = {0: (14, 15, 16), 9: (21, 22, 23)}


def main():
    frames = read_frames(HERE + "/xtbpath.xyz")
    ref = frames[0][1]
    print("frame,rel_kcal_mol,theta_C1C6C7C8_deg,ringA_planarity_A,ringB_planarity_A,"
          "d_C0_C9_A,min_H_H_A,axis_C6_C7_A,rmsd_vs_frame0_A,max_atom_disp_vs_frame0_A")
    for k, (comment, at) in enumerate(frames):
        rel = float(comment.split()[1])
        theta = dihedral(at, (1, 6, 7, 8))
        m = np.linalg.norm(at[0] - at[9])
        hh = min(float(np.linalg.norm(at[i] - at[j]))
                 for i in METHYL_H[0] for j in METHYL_H[9])
        axis = float(np.linalg.norm(at[6] - at[7]))
        disp = [float(np.linalg.norm(at[i] - ref[i])) for i in range(len(at))]
        rmsd = (sum(d * d for d in disp) / len(disp)) ** 0.5
        print("%d,%.3f,%.2f,%.4f,%.4f,%.3f,%.3f,%.3f,%.3f,%.3f"
              % (k, rel, theta, planarity(at, RING_A), planarity(at, RING_B), m, hh,
                 axis, rmsd, max(disp)))


if __name__ == "__main__":
    main()
