import sys
log = sys.argv[1]; target = int(sys.argv[2])
lines = open(log).read().splitlines()
best = None
i = 0
while i < target:
    if 'Input orientation' in lines[i]:
        best = i
    i += 1
j = best + 5
atoms = []
while j < len(lines):
    p = lines[j].split()
    if len(p) == 6 and p[0].isdigit() and p[1].isdigit():
        atoms.append((int(p[1]), float(p[3]), float(p[4]), float(p[5])))
        j += 1
    else:
        break
print(len(atoms))
print('geometry from log line', best+1)
for a in atoms:
    print('%-2d %.6f %.6f %.6f' % (a[0], a[1], a[2], a[3]))