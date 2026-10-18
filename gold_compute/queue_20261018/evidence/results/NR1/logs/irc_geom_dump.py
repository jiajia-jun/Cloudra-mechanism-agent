import re, sys, math
p = sys.argv[1]
lines = open(p).read().splitlines()
recs = []
i = 0
while i < len(lines):
    m = re.search(r'Point Number\s+(\d+) in (FORWARD|REVERSE) path direction', lines[i])
    if m:
        j = i
        while j < len(lines) and 'Input orientation' not in lines[j]:
            j += 1
        j += 5
        atoms = []
        while j < len(lines):
            parts = lines[j].split()
            if len(parts) == 6 and parts[0].isdigit() and parts[1].isdigit():
                atoms.append((int(parts[1]), float(parts[3]), float(parts[4]), float(parts[5])))
                j += 1
            else:
                break
        recs.append((m.group(2), int(m.group(1)), atoms, i+1))
        i = j
    else:
        i += 1

def dist(a, b):
    return math.dist(a[1:], b[1:])

print('total frames', len(recs))
for direction, num, atoms, ln in recs:
    if len(atoms) < 6: continue
    d = {}
    for (x, y, name) in [(1,4,'N1-H4'), (3,4,'O3-H4'), (1,5,'N1-H5'), (3,5,'O3-H5'), (2,3,'C2-O3'), (1,2,'N1-C2')]:
        d[name] = dist(atoms[x-1], atoms[y-1])
    print(direction, num, 'line', ln, ' '.join('%s=%.3f'%(k,v) for k,v in d.items()))
