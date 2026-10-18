import numpy as np, sys
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, dih
import geomlib
from rdkit import Chem
from rdkit.Chem import rdMolTransforms

def rot_about(atoms, i, j, deg):
    # rotate all atoms about axis i-j
    pass

for tag,p in [('A','gold_compute/queue_20261018/results/HI1/work/build_A/prepared.xyz'),
              ('B','gold_compute/queue_20261018/results/HI1/work/build_B/prepared.xyz')]:
    at=load_xyz(p); R=np.array([x[1] for x in at])
    def d(i,j,k,l): return dih(R[i-1],R[j-1],R[k-1],R[l-1])
    print(tag)
    for lbl,ii in [('chain C1-C2-C7-C8',(1,2,7,8)),('N-C2-C7-Ph',(3,2,7,9)),('H18-C2-C7-H25',(18,2,7,25))]:
        print('  ',lbl, round(d(*ii),2))
    t1=d(1,2,7,8); t2=d(3,2,7,9)
    print('   diff', round((t2-t1+180)%360-180,2))
