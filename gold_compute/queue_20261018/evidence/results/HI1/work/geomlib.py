
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

def clean_xyz(atoms, comment=''):
    s='%d\n%s\n'%(len(atoms),comment)
    for e,r in atoms:
        s+='%-2s %14.8f %14.8f %14.8f\n'%(e,r[0],r[1],r[2])
    return s

def cip_from_atoms(atoms, charge=0):
    m=Chem.MolFromXYZBlock(clean_xyz(atoms))
    rdDetermineBonds.DetermineBonds(m, charge=charge)
    Chem.AssignStereochemistryFrom3D(m, confId=0)
    Chem.AssignCIPLabels(m)
    out=[]
    for a in m.GetAtoms():
        if a.HasProp('_CIPCode'):
            out.append((a.GetIdx()+1, a.GetSymbol(), a.GetProp('_CIPCode')))
    return out, Chem.MolToSmiles(Chem.RemoveHs(m)), m

def dih(a,b,c,d):
    b0=a-b; b1=c-b; b2=d-c
    b1n=b1/np.linalg.norm(b1)
    v=b0-np.dot(b0,b1n)*b1n; w=b2-np.dot(b2,b1n)*b1n
    x=np.dot(v,w); y=np.dot(np.cross(b1n,v),w)
    return np.degrees(np.arctan2(y,x))

if __name__=='__main__':
    for tag,p in [('A','gold_compute/queue_20261018/results/HI1/work/build_A/prepared.xyz'),
                  ('B','gold_compute/queue_20261018/results/HI1/work/build_B/prepared.xyz')]:
        at=load_xyz(p)
        print('==',tag,len(at), ''.join(x[0] for x in at))
        c,smi,m=cip_from_atoms(at)
        print('CIP:',c)
        print('SMILES:',smi)
        for i,(e,r) in enumerate(at,1):
            print(i,e,np.round(r,4))
        # print bonds
        print('bonds:', [(b.GetBeginAtomIdx()+1,b.GetEndAtomIdx()+1,str(b.GetBondType())) for b in m.GetBonds()])
