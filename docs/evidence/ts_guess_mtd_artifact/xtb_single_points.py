"""Single-point energies of three path frames, used as absolute-energy anchors.

Frames are taken by index from the verbatim xtbpath.xyz in this directory.

Run:  python3 xtb_single_points.py <workdir>
Writes sp_frame<NN>.out (verbatim xtb stdout+stderr) and prints the energies.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = (0, 10, 46)


def split_frames(path):
    lines = open(path).read().splitlines()
    out, i = [], 0
    while i < len(lines):
        n = int(lines[i].strip())
        out.append("\n".join(lines[i:i + 2 + n]) + "\n")
        i += 2 + n
    return out


def total_energy(text):
    for line in text.splitlines():
        if "TOTAL ENERGY" in line:
            tok = line.replace("|", " ").split()
            return float(tok[tok.index("ENERGY") + 1])
    raise RuntimeError("no TOTAL ENERGY in output")


def main():
    work = sys.argv[1]
    os.makedirs(work, exist_ok=True)
    frames = split_frames(os.path.join(HERE, "xtbpath.xyz"))
    energies = {}
    for index in FRAMES:
        name = "sp_frame%02d" % index
        open(os.path.join(work, name + ".xyz"), "w").write(frames[index])
        proc = subprocess.run(["xtb", name + ".xyz", "--sp"], cwd=work,
                              capture_output=True, text=True)
        text = proc.stdout + proc.stderr
        open(os.path.join(work, name + ".out"), "w").write(text)
        energies[index] = total_energy(text)
        print("frame %2d  E = %.12f Eh" % (index, energies[index]))
    ref = energies[0]
    for index in FRAMES:
        print("frame %2d  rel to frame 0 = %+8.3f kcal/mol"
              % (index, (energies[index] - ref) * 627.5095))


if __name__ == "__main__":
    main()
