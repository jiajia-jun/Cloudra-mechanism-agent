
import sys, re, numpy as np
from rdkit import Chem
HBOND = {7:0, 8:1, 9:2, 10:3, 11:3, 12:4, 13:4, 14:5, 15:6, 16:6}
def parse_log(p):
    L=open(p).read().splitlines()
    E=None; Eline=None
    for i,l in enumerate(L):
        m=re.search(r'SCF Done:\s+E\(RB3LYP\)\s+=\s+(-?\d+\.\d+)', l)
        if m: E=float(m.group(1)); Eline=i+1
    idx=[i for i,l in enumerate(L) if 'Standard orientation' in l] or [i for i,l in enumerate(L) if 'Input orientation' in l]
    st=idx[-1]; j=st+5; co=[]; els=[]
    while not L[j].strip().startswith('---'):
        f=L[j].split(); co.append([float(f[3]),float(f[4]),float(f[5])]); els.append(int(f[1])); j+=1
    Z={1:'H',6:'C',7:'N',8:'O'}
    # frequencies
    fi=[i for i,l in enumerate(L) if 'Frequencies ---' in l]
    freqs=[]
    for i in fi:
        freqs += [float(x) for x in L[i].split('---')[1].split()]
    imag=[f for f in freqs if f<0]
    low=[i+1 for i,l in enumerate(L) if 'Low frequencies' in l]
    return dict(E=E,Eline=Eline,c=np.array(co),els=[Z[z] for z in els],gl=st+1,freqs=freqs,imag=imag,low=low,freqlines=[i+1 for i in fi])
def product_mol(c):
    rw=Chem.RWMol()
    els=['C']*7+['H']*10+['C','N','O','H']
    for e in els: rw.AddAtom(Chem.Atom(e))
    bl=[(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,6),(6,5),(0,17),(17,18),(18,19),(19,1),(17,20)]
    for j,i in HBOND.items(): bl.append((i,j))
    for a,b in bl: rw.AddBond(a,b, Chem.BondType.DOUBLE if (a,b)==(17,18) else Chem.BondType.SINGLE)
    m=rw.GetMol(); Chem.SanitizeMol(m)
    for i in range(21): m.GetAtomWithIdx(i).SetNoImplicit(True)
    cf=Chem.Conformer(21)
    for i in range(21): cf.SetAtomPosition(i,[float(v) for v in c[i]])
    m.AddConformer(cf); Chem.AssignStereochemistryFrom3D(m)
    return m
for p in sys.argv[1:]:
    d=parse_log(p)
    print("### "+p.split('/')[-1])
    print("   E=%.9f Ha (L%d)  nfreq=%d  nimag=%d  imag=%s  Lowfreq line %s"%(d['E'],d['Eline'],len(d['freqs']),len(d['imag']),d['imag'],d['low']))
    m=product_mol(d['c'])
    cip=[(i+1, m.GetAtomWithIdx(i).GetSymbol(), m.GetAtomWithIdx(i).GetProp("_CIPCode")) for i in range(21) if m.GetAtomWithIdx(i).HasProp("_CIPCode")]
    print("   CIP on WORK order (1-based, explicit H):", cip)
    print("   adjacency of stereocentres:", {i+1:[n.GetIdx()+1 for n in m.GetAtomWithIdx(i).GetNeighbors()] for i,_,_ in cip})
