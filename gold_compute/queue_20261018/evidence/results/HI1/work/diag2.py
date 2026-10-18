import numpy as np, sys
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, dih
for tag,p in [('A','gold_compute/queue_20261018/results/HI1/work/build_A/prepared.xyz'),
              ('B','gold_compute/queue_20261018/results/HI1/work/build_B/prepared.xyz')]:
    at=load_xyz(p); R=[x[1] for x in at]
    def d(i,j,k,l): return dih(R[i-1],R[j-1],R[k-1],R[l-1])
    print(tag)
    for x in (8,9,25):
        print('  C7-%2d : 1-2-7-x=%8.2f  3-2-7-x=%8.2f  18-2-7-x=%8.2f'%(x,d(1,2,7,x),d(3,2,7,x),d(18,2,7,x)))
    # bond angles at C7 and C2
    import numpy as np
    def ang(i,j,k):
        u=R[i-1]-R[j-1]; v=R[k-1]-R[j-1]
        return np.degrees(np.arccos(np.dot(u,v)/np.linalg.norm(u)/np.linalg.norm(v)))
    print('  angles at C7: C2-C7-C8 %.1f  C2-C7-Ph %.1f  C2-C7-H25 %.1f'%(ang(2,7,8),ang(2,7,9),ang(2,7,25)))
    print('  angles at C2: C7-C2-C1 %.1f  C7-C2-N %.1f  C7-C2-H18 %.1f'%(ang(7,2,1),ang(7,2,3),ang(7,2,18)))
