import math, sys, re
def last_geom(path):
    lines = open(path).read().splitlines()
    idx = None
    for i, l in enumerate(lines):
        if 'Standard orientation' in l or 'Input orientation' in l: idx = i
    atoms = []
    j = idx + 5
    while j < len(lines):
        p = lines[j].split()
        if len(p) == 6 and p[0].isdigit() and p[1].isdigit():
            atoms.append((int(p[1]), float(p[3]), float(p[4]), float(p[5]))); j += 1
        else: break
    return atoms
for path in sys.argv[1:]:
    a = last_geom(path)
    print(path.split('/')[-1], 'natoms', len(a))
    if len(a) >= 18:
        print('  d(C10,C18) = %.4f' % math.dist(a[9][1:], a[17][1:]))
        print('  elem10=%d elem18=%d' % (a[9][0], a[17][0]))