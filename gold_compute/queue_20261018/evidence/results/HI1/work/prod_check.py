import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, cip_from_atoms
at=load_xyz('gold_compute/queue_20261018/results/HI1/geoms/HI1_erythro_Pend_min.xyz')
R=[x[1] for x in at]; s=[x[0] for x in at]
print('natoms',len(at), ''.join(s))
c,smi,m=cip_from_atoms(at)
print('SMILES from 3D:',smi)
# close contacts between heavy atoms and H
r=lambda i,j: float(np.linalg.norm(R[i-1]-R[j-1]))
print('all H...heavy distances < 2.6:')
for i in range(len(at)):
    if s[i]!='H': continue
    for j in range(len(at)):
        if s[j]=='H': continue
        d=r(i+1,j+1)
        if 1.8<d<2.6:
            print('   H%d ... %s%d = %.3f'%(i+1,s[j],j+1,d))
