import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz
at=load_xyz('gold_compute/queue_20261018/results/HI1/geoms/HI1_erythro_Pend_min.xyz')
R=[x[1] for x in at]; s=[x[0] for x in at]
r=lambda i,j: float(np.linalg.norm(R[i-1]-R[j-1]))
print('O6 (atom6) nearest:', sorted([(round(r(6,k+1),3), k+1, s[k]) for k in range(len(at)) if k!=5])[:5])
print('N3 (atom3) nearest:', sorted([(round(r(3,k+1),3), k+1, s[k]) for k in range(len(at)) if k!=2])[:5])
print('C2 nearest:', sorted([(round(r(2,k+1),3), k+1, s[k]) for k in range(len(at)) if k!=1])[:5])
print('C7 nearest:', sorted([(round(r(7,k+1),3), k+1, s[k]) for k in range(len(at)) if k!=6])[:5])
print('d(C2,C7)=%.3f  d(C2,C1)=%.3f  d(C7,C8)=%.3f'%(r(2,7),r(2,1),r(7,8)))
print('d(1,2)=%.3f d(2,3)=%.3f'%(r(1,2),r(2,3)))
