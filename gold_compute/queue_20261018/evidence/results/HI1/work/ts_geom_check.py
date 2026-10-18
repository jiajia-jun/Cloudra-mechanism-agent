import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, dih
for tag,p in [('erythro TS','gold_compute/queue_20261018/results/HI1/geoms/HI1_erythro_TS_syn_opt.xyz'),
              ('threo TS','gold_compute/queue_20261018/results/HI1/geoms/HI1_threo_TS_syn_opt.xyz')]:
    at=load_xyz(p); R=[x[1] for x in at]
    d=lambda i,j,k,l: dih(R[i-1],R[j-1],R[k-1],R[l-1])
    r=lambda i,j: float(np.linalg.norm(R[i-1]-R[j-1]))
    print(tag,'natoms',len(at))
    print('   dih(C1,C2,C7,C9ipso)=%.1f  dih(H18,C2,C7,C8)=%.1f  dih(C1,C2,C7,C8)=%.1f'%(d(1,2,7,9),d(18,2,7,8),d(1,2,7,8)))
    print('   d(C2,C7)=%.3f d(C2,N3)=%.3f d(C7,H25)=%.3f d(O6,H25)=%.3f d(O6,N3)=%.3f d(C2,C1)=%.3f d(C7,C8)=%.3f d(C7,C9)=%.3f'%(
        r(2,7),r(2,3),r(7,25),r(6,25),r(6,3),r(2,1),r(7,8),r(7,9)))
