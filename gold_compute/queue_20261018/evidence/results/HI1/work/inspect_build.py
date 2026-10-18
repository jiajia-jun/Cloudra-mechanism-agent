
import sys, numpy as np
from rdkit import Chem
from rdkit.Chem import rdDetermineBonds

def load_xyz(p):
    lines=open(p).read().strip().splitlines()
    n=int(lines[0].split()[0])
    atoms=[]
    for ln in lines[2:2+n]:
        f=ln.split(); atoms.append((f[0], np.array([float(f[1]),float(f[2]),float(f[3])])))
    return atoms

def cip(p, charge=0):
    xyz=open(p).read()
    m=Chem.MolFromXYZBlock(xyz)
    rdDetermineBonds.DetermineBonds(m, charge=charge)
    Chem.AssignStereochemistryFrom3D(m, confId=0)
    Chem.AssignCIPLabels(m)
    out=[]
    for a in m.GetAtoms():
        if a.HasProp('_CIPCode'):
            out.append((a.GetIdx()+1, a.GetSymbol(), a.GetProp('_CIPCode')))
    smi=Chem.MolToSmiles(Chem.RemoveHs(m))
    return out, smi

def dih(a,b,c,d):
    b0=a-b; b1=c-b; b2=d-c
    b1n=b1/np.linalg.norm(b1)
    v=b0-np.dot(b0,b1n)*b1n; w=b2-np.dot(b2,b1n)*b1n
    x=np.dot(v,w); y=np.dot(np.cross(b1n,v),w)
    return np.degrees(np.arctan2(y,x))

def dist(a,b): return float(np.linalg.norm(a-b))

for tag,p in [('A','gold_compute/queue_20261018/results/HI1/work/build_A/prepared.xyz'),
              ('B','gold_compute/queue_20261018/results/HI1/work/build_B/prepared.xyz')]:
    at=load_xyz(p)
    print('==',tag,p,len(at))
    print('elements:', ''.join(x[0] for x in at))
    c,smi=cip(p)
    print('CIP(1-based):', c)
    print('canonical SMILES (no map):', smi)
    C=[None]+[x[1] for x in at]
    # find indices by element+connectivity: print all coordinates table for heavy atoms
    for i,(e,r) in enumerate(at,1):
        print(i,e,np.round(r,4))
