#!/usr/bin/env python3
"""Extract the last CARTESIAN COORDINATES (ANGSTROEM) block from an ORCA log."""
import sys, re
def last_geom(path):
    txt = open(path, errors="ignore").read().splitlines()
    idx = [i for i, l in enumerate(txt) if "CARTESIAN COORDINATES (ANGSTROEM)" in l]
    if not idx:
        raise SystemExit(f"no coordinates in {path}")
    i = idx[-1] + 2
    atoms = []
    while i < len(txt):
        parts = txt[i].split()
        if len(parts) < 4:
            break
        atoms.append((parts[0], parts[1], parts[2], parts[3]))
        i += 1
    return atoms
if __name__ == "__main__":
    atoms = last_geom(sys.argv[1])
    print(len(atoms))
    print(sys.argv[2] if len(sys.argv) > 2 else "extracted")
    for el, x, y, z in atoms:
        print(f"{el:2s} {float(x):16.8f} {float(y):16.8f} {float(z):16.8f}")
