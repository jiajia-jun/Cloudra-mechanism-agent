
import sys, re, numpy as np
from rdkit import Chem
HBOND = {7:0, 8:1, 9:2, 10:3, 11:3, 12:4, 13:4, 14:5, 15:6, 16:6}
def parse_log(p):
    L=open(p).read().splitlines()
    E=None; Eline=None
    for i,l in enumerate(L):
        m=re.search(r'SCF Done:\s+E\(RB3LYP\)\s+=\s+(-?\d+\.\d+)', l)
        if m: E=float(m.group(1)); Eline=i+1
    # last geometry: 'Standard orientation' blocks or 'Input orientation'
    idx=[i for i,l in enumerate(L) if 'Standard orientation' in l]
    if not idx:
        idx=[i for i,l in enumerate(L) if 'Input orientation' in l]
    st=idx[-1]; gline=st+1
    j=st+5
    co=[]; els=[]
    while not L[j].strip().startswith('---'):
        f=L[j].split()
        co.append([float(f[3]),float(f[4]),float(f[5])])
        els.append(int(f[1]))
        j+=1
    Z={1:'H',6:'C',7:'N',8:'O'}
    return E,Eline,np.array(co),[Z[z] for z in els],gline
def dih(p0,p1,p2,p3):
    b0=p0-p1; b1=p2-p1; b2=p3-p2; b1n=b1/np.linalg.norm(b1)
    v=b0-np.dot(b0,b1n)*b1n; w=b2-np.dot(b2,b1n)*b1n
    return np.degrees(np.arctan2(np.dot(np.cross(b1n,v),w), np.dot(v,w)))
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
    E,Eline,c,els,gline = parse_log(p)
    print("### %s"%p.split('/')[-1])
    print("  E = %.9f Ha (log line %d) ; last-orientation block starts line %d"%(E,Eline,gline-4))
    print("  element order:", "".join(e[0] for e in els)[:21])
    P4=np.array([c[0],c[1],c[2],c[5]]); cc=P4.mean(axis=0)
    _,_,Vt=np.linalg.svd(P4-cc); nn=Vt[2]; nn/=np.linalg.norm(nn)
    if np.dot(c[6]-cc,nn)<0: nn=-nn
    print("  sdist C10(atom7)=%+.4f  C18=%+.4f  O20=%+.4f"%(np.dot(c[6]-cc,nn),np.dot(c[17]-cc,nn),np.dot(c[19]-cc,nn)))
    print("  d(C7bridge, newC-C bond C18) = %.4f ; d(C7, O20) = %.4f"%(np.linalg.norm(c[6]-c[17]), np.linalg.norm(c[6]-c[19])))
    print("  d(C10, C18) = %.4f ; d(C10,O20)=%.4f ; d(C10,C1)=%.4f"%(np.linalg.norm(c[6]-c[17]),np.linalg.norm(c[6]-c[19]),np.linalg.norm(c[6]-c[0])))
    print("  dih(C18,1,3,7)=%+.2f  dih(O20,2,6,7)=%+.2f  dih(H21,18,19,20)=%+.2f"%(dih(c[17],c[0],c[2],c[6]), dih(c[19],c[1],c[5],c[6]), dih(c[20],c[17],c[18],c[19])))
    print("  new bonds: d(1-18)=%.4f d(2-20)=%.4f d(1-2)=%.4f d(18-19)=%.4f d(19-20)=%.4f"%(
        np.linalg.norm(c[0]-c[17]),np.linalg.norm(c[1]-c[19]),np.linalg.norm(c[0]-c[1]),np.linalg.norm(c[17]-c[18]),np.linalg.norm(c[18]-c[19])))
    m=product_mol(c); mh=Chem.RemoveHs(m)
    print("  isomeric SMILES:", Chem.MolToSmiles(mh, isomericSmiles=True))
    print("  stereocentres (CIP):", [(i+1, mh.GetAtomWithIdx(i).GetSymbol(), mh.GetAtomWithIdx(i).GetProp("_CIPCode")) for i in range(mh.GetNumAtoms()) if mh.GetAtomWithIdx(i).HasProp("_CIPCode")])
