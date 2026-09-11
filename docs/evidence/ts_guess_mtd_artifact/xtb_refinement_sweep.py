"""Sweep the xTB path-refinement ceiling (``$path nrun``) on one endpoint pair.

Measures what the SOP's default used to be: the engine's *built-in* ceiling is 3 refinement runs,
and hitting a ceiling prints "terminated because max. # cycles reached" — a TRUNCATED path, not a
converged one.  Raising the ceiling lets the engine stop by its own criterion
("terminated because grad at TS <threshold").

Run:  python3 xtb_refinement_sweep.py <workdir> <reactant.xyz> <product.xyz> [cap ...]
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def summarize(log: str) -> str:
    cycles = 0
    termination = ""
    barrier = ""
    for line in log.splitlines():
        stripped = line.strip()
        if stripped.startswith("refinement cycle"):
            cycles += 1
        elif stripped.startswith("terminated because"):
            termination = stripped
        elif "forward  barrier (kcal)" in stripped:
            barrier = stripped.split(":")[-1].strip()
    return "cycles=%-4d barrier=%-9s %s" % (cycles, barrier, termination or "<no termination line>")


def main():
    work, reactant, product = sys.argv[1], sys.argv[2], sys.argv[3]
    caps = [int(x) for x in sys.argv[4:]] or [3, 10, 30, 100]
    os.makedirs(work, exist_ok=True)
    for cap in caps:
        tag = "cap%04d" % cap
        inp = os.path.join(work, tag + ".inp")
        open(inp, "w").write("$path\n   nrun=%d\n$end\n" % cap)
        log = os.path.join(work, tag + ".out")
        with open(log, "w") as handle:
            subprocess.run(
                ["xtb", reactant, "--path", product, "--input", os.path.basename(inp),
                 "--chrg", "0", "--uhf", "0"],
                cwd=work, stdout=handle, stderr=subprocess.STDOUT, check=False,
            )
        print("nrun=%-5d %s" % (cap, summarize(open(log).read())))
        for produced in ("xtbpath.xyz", "xtbpath_ts.xyz"):
            source = os.path.join(work, produced)
            if os.path.isfile(source):
                stem = "path" if produced == "xtbpath.xyz" else "ts_candidate"
                os.replace(source, os.path.join(work, "%s_%s" % (tag, stem)))


if __name__ == "__main__":
    main()
