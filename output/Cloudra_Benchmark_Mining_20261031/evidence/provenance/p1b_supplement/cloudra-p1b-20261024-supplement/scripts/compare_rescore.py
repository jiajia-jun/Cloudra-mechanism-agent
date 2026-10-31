#!/usr/bin/env python3
import csv, statistics, collections

rows = list(csv.DictReader(open("/home/ly/cloudra-p1b-rescore/results.csv")))
ARMS = ("guided", "record", "standard", "brief-errors")
TIER = {"E1": "easy", "NB1": "normal", "HA1": "hard", "IA1": "impossible"}

def f(x):
    return float(x) if x not in (None, "", "None") else None

print(f"rows: {len(rows)}")
print()
print("=== per arm: old -> new mean final ===")
print(f"{'arm':13s} {'n':>3s} {'old_mean':>9s} {'new_mean':>9s} {'delta':>7s} {'old_min':>8s} {'new_min':>8s}")
for arm in ARMS:
    a = [r for r in rows if r["arm"] == arm]
    old = [f(r["old_final"]) for r in a if f(r["old_final"]) is not None]
    new = [f(r["new_final"]) for r in a if f(r["new_final"]) is not None]
    if not a:
        continue
    print(f"{arm:13s} {len(a):3d} {statistics.mean(old):9.3f} {statistics.mean(new):9.3f} "
          f"{statistics.mean(new)-statistics.mean(old):+7.3f} {min(old):+8.3f} {min(new):+8.3f}")

print()
print("=== by tier: old -> new mean final ===")
print(f"{'arm':13s} {'easy':>18s} {'normal':>18s} {'hard':>18s} {'impossible':>18s}")
for arm in ARMS:
    cells = []
    for tier in ("easy", "normal", "hard", "impossible"):
        a = [r for r in rows if r["arm"] == arm and TIER.get(r["task"]) == tier]
        if not a:
            cells.append("-")
            continue
        old = statistics.mean(f(r["old_final"]) for r in a)
        new = statistics.mean(f(r["new_final"]) for r in a if f(r["new_final"]) is not None)
        cells.append(f"{old:+.2f}->{new:+.2f} ({len(a)})")
    print(f"{arm:13s} " + " ".join(f"{c:>18s}" for c in cells))

print()
print("=== runs that changed by more than 0.05 ===")
for r in sorted(rows, key=lambda r: (f(r["new_final"]) or 0) - (f(r["old_final"]) or 0)):
    old, new = f(r["old_final"]), f(r["new_final"])
    if old is None or new is None:
        print("  ERROR", r["arm"], r["round"], r["task"], r["note"][:80])
        continue
    if abs(new - old) > 0.05:
        print(f"  {r['arm']:13s} {r['round']} {r['task']:4s} {old:+.3f} -> {new:+.3f}")
