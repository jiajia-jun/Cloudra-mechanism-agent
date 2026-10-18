import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, cip_from_atoms, dih
for tag,p in [('Z-candidate','gold_compute/queue_20261018/results/HI1/geoms/HI1_Z_2phenyl2butene_min.xyz'),
              ('E-candidate','gold_compute/queue_20261018/results/HI1/geoms/HI1_E_2phenyl2butene_min.xyz')]:
    at=load_xyz(p); c,smi,m=cip_from_atoms(at)
    print(tag,'natoms',len(at),'SMILES from 3D:',smi)
    # find the alkene bond and report the substituent dihedral
    db=[b for b in m.GetBonds() if b.GetBondType()==Chem.BondType.DOUBLE] if False else None
    for b in m.GetBonds():
        if b.GetBondType().name=='DOUBLE' and not b.GetIsAromatic():
            i,j=b.GetBeginAtomIdx(),b.GetEndAtomIdx()
            ni=[n.GetIdx() for n in m.GetAtomWithIdx(i).GetNeighbors() if n.GetIdx()!=j]
            nj=[n.GetIdx() for n in m.GetAtomWithIdx(j).GetNeighbors() if n.GetIdx()!=i]
            print('   double bond atoms',i+1,j+1,'substituents',[x+1 for x in ni],[x+1 for x in nj])
            for a in ni:
                for b2 in nj:
                    print('     dih(%d,%d,%d,%d)=%.1f'%(a+1,i+1,j+1,b2+1, dih(at[a][1],at[i][1],at[j][1],at[b2][1])))
