import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, cip_from_atoms
for tag,p in [('erythro P endpoint','gold_compute/queue_20261018/results/HI1/geoms/HI1_erythro_Pend_min.xyz'),
              ('threo P endpoint','gold_compute/queue_20261018/results/HI1/geoms/HI1_threo_Pend_min.xyz')]:
    at=load_xyz(p); R=[x[1] for x in at]
    c,smi,m=cip_from_atoms(at)
    r=lambda i,j: float(np.linalg.norm(R[i-1]-R[j-1]))
    print(tag,'| 3D SMILES:',smi)
    print('   d(C2,C7)=%.3f d(C2,N3)=%.3f d(O6,H25)=%.3f d(C7,H25)=%.3f'%(r(2,7),r(2,3),r(6,25),r(7,25)))
