import sys
log = sys.argv[1]; target = int(sys.argv[2]); out = sys.argv[3]
lines = open(log).read().splitlines()
best = None
for i in range(target):
    if 'Input orientation' in lines[i]:
        best = i
j = best + 5
atoms = []
while j < len(lines):
    p = lines[j].split()
    if len(p) == 6 and p[0].isdigit() and p[1].isdigit():
        atoms.append((int(p[1]), float(p[3]), float(p[4]), float(p[5])))
        j += 1
    else:
        break
sym = {1:'H',6:'C',7:'N',8:'O'}
with open(out,'w') as f:
    f.write('%d\n' % len(atoms))
    f.write('scan point R(3,4)=1.2749 (peak region), extracted from log line %d\n' % (best+1))
    for a in atoms:
        f.write('%-2s %.6f %.6f %.6f\n' % (sym[a[0]], a[1], a[2], a[3]))
print('wrote', out, len(atoms))