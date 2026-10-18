
import numpy as np, re, sys
p=sys.argv[1]
L=open(p).read().splitlines()
# all standard orientation blocks
blocks=[]
i=0
while i < len(L):
    if 'Standard orientation' in L[i] or 'Input orientation' in L[i]:
        j=i+5; co=[]
        while not L[j].strip().startswith('---'):
            f=L[j].split(); co.append([float(f[3]),float(f[4]),float(f[5])]); j+=1
        blocks.append((i+1, np.array(co)))
        i=j
    else: i+=1
print("orientation blocks: %d (first at L%d)"%(len(blocks), blocks[0][0]))
# energies in order
Es=[]
for i,l in enumerate(L):
    m=re.search(r'SCF Done:\s+E\(RB3LYP\)\s+=\s+(-?\d+\.\d+)', l)
    if m: Es.append((i+1,float(m.group(1))))
print("SCF Done lines: %d"%len(Es))
# path markers
marks=[(i+1,l.strip()) for i,l in enumerate(L) if 'Point Number' in l and 'Path Number' not in l]
print("path markers:", len(marks))
for k in marks[:3]+marks[-3:]: print("   L%d %s"%k)
print()
print(" idx | blockL | r(18,1) r(20,2) r(1,2) r(18,19) | E")
for n,(bl,co) in enumerate(blocks):
    r=lambda a,b: np.linalg.norm(co[a-1]-co[b-1])
    E = Es[n][1] if n < len(Es) else float('nan')
    print("  %2d | %6d | %7.3f %7.3f %7.3f %7.3f | %.9f"%(n, bl, r(18,1),r(20,2),r(1,2),r(18,19), E))
