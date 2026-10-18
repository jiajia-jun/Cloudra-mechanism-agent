import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, cip_from_atoms, dih
for tag,p in [('erythro(A)','gold_compute/queue_20261018/results/HI1/geoms/HI1_erythro_R_min.xyz'),
              ('threo(B)','gold_compute/queue_20261018/results/HI1/geoms/HI1_threo_R_min.xyz')]:
    at=load_xyz(p); R=[x[1] for x in at]
    c,smi,m=cip_from_atoms(at)
    def d(i,j,k,l): return dih(R[i-1],R[j-1],R[k-1],R[l-1])
    t1=d(1,2,7,8); t2=d(3,2,7,9); inv=(t2-t1+180)%360-180
    print(tag,'natoms',len(at),'CIP',c)
    print('   SMILES:',smi)
    print('   dih(C1,C2,C7,C8)=%.2f dih(N3,C2,C7,C9)=%.2f inv=%.2f'%(t1,t2,inv))
    print('   d(C2,N3)=%.3f d(C2,C7)=%.3f d(C7,H25)=%.3f d(N3,O6)=%.3f'%(np.linalg.norm(R[1]-R[2]),np.linalg.norm(R[1]-R[6]),np.linalg.norm(R[6]-R[24]),np.linalg.norm(R[2]-R[5])))
