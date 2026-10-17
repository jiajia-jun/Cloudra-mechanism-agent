#!/usr/bin/env python3
"""IA5 geometry diagnostics for cyclobutene ring opening.

Atom order used throughout (cyclobutene ordering, 1-based):
 1 C1(=C2)  2 C2  3 C3(CH2)  4 C4(CH2)
 5 H(C1)    6 H(C2)   7 H(C3a) 8 H(C3b)   9 H(C4a) 10 H(C4b)

Descriptors:
 r34            C3-C4 distance (the breaking sigma bond)
 tauA/tauAp     dihedral H7-C3-C2-C1 / H8-C3-C2-C1 (twist of the C3 CH2 about C3-C2)
 tauB/tauBp     dihedral H9-C4-C1-C2 / H10-C4-C1-C2 (twist of the C4 CH2 about C4-C1)
 omega3/omega4  angle between the CH2 plane normal and the ring reference normal
                (measures the p-orbital rotation at each terminus)
"""
import sys, math

def read_xyz(path):
    with open(path) as fh:
        lines = fh.read().splitlines()
    n = int(lines[0].split()[0])
    atoms = []
    for ln in lines[2:2+n]:
        p = ln.split()
        atoms.append((p[0], [float(p[1]), float(p[2]), float(p[3])]))
    return atoms

def sub(a, b): return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]
def cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def norm(a):
    n = math.sqrt(dot(a, a))
    return [x/n for x in a]
def dist(a, b): return math.sqrt(dot(sub(a, b), sub(a, b)))

def dihedral(p0, p1, p2, p3):
    b0 = sub(p0, p1); b1 = sub(p2, p1); b2 = sub(p3, p2)
    b1n = norm(b1)
    v = [b0[i] - dot(b0, b1n)*b1n[i] for i in range(3)]
    wv = [b2[i] - dot(b2, b1n)*b1n[i] for i in range(3)]
    return math.degrees(math.atan2(dot(cross(b1n, v), wv), dot(v, wv)))

def angle(a, b, c):
    v1 = sub(a, b); v2 = sub(c, b)
    return math.degrees(math.acos(max(-1, min(1, dot(v1, v2)/(math.sqrt(dot(v1,v1))*math.sqrt(dot(v2,v2)))))))

def report(path):
    at = read_xyz(path)
    x = [a[1] for a in at]
    C1, C2, C3, C4 = x[0], x[1], x[2], x[3]
    H7, H8, H9, H10 = x[6], x[7], x[8], x[9]
    out = []
    out.append(f"file: {path}")
    out.append(f"  r(C1=C2) = {dist(C1,C2):.3f}  r(C2-C3) = {dist(C2,C3):.3f}  r(C3-C4) = {dist(C3,C4):.3f}  r(C4-C1) = {dist(C4,C1):.3f}")
    out.append(f"  angle C1-C2-C3 = {angle(C1,C2,C3):.2f}  C2-C3-C4 = {angle(C2,C3,C4):.2f}  C3-C4-C1 = {angle(C3,C4,C1):.2f}")
    out.append(f"  tauA  [H7-C3-C2-C1]  = {dihedral(H7,C3,C2,C1):8.2f}")
    out.append(f"  tauAp [H8-C3-C2-C1]  = {dihedral(H8,C3,C2,C1):8.2f}")
    out.append(f"  tauB  [H9-C4-C1-C2]  = {dihedral(H9,C4,C1,C2):8.2f}")
    out.append(f"  tauBp [H10-C4-C1-C2] = {dihedral(H10,C4,C1,C2):8.2f}")
    # p-orbital (CH2 plane normal) rotation, referenced to ring-plane normal
    nring = norm(cross(sub(C2,C1), sub(C4,C1)))
    n3 = norm(cross(sub(H7,C3), sub(H8,C3)))
    n4 = norm(cross(sub(H9,C4), sub(H10,C4)))
    def tilt(n):
        c = max(-1.0, min(1.0, dot(n, nring)))
        return math.degrees(math.acos(c))
    out.append(f"  omega3 (CH2(C3) plane vs ring plane) = {tilt(n3):7.2f}   omega4 = {tilt(n4):7.2f}")
    out.append(f"  ring-plane normal n = [{nring[0]:+.3f} {nring[1]:+.3f} {nring[2]:+.3f}]")
    return "\n".join(out)

if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(report(p))
        print()
