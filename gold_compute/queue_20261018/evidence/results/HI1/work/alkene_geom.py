import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, dih
for tag,p in [('erythro','gold_compute/queue_20261018/results/HI1/geoms/erythro_TS_guess_v4.xyz'),
              ('threo','gold_compute/queue_20261018/results/HI1/geoms/threo_TS_guess_v4.xyz')]:
    at=load_xyz(p); R=[x[1] for x in at]
    def d(i,j,k,l): return dih(R[i-1],R[j-1],R[k-1],R[l-1])
    print(tag,'dih(C1,C2,C7,Cipso)=%.1f  dih(H18,C2,C7,C8)=%.1f  dih(H18,C2,C7,Cipso)=%.1f  dih(C1,C2,C7,C8)=%.1f'%(
        d(1,2,7,9), d(18,2,7,8), d(18,2,7,9), d(1,2,7,8)))
