
import numpy as np, sys
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, cip_from_atoms, dih

def ang_diff(t1,t2):
    d=(t1-t2+180.0)%360.0-180.0
    return d

for tag,p in [('A','gold_compute/queue_20261018/results/HI1/work/build_A/prepared.xyz'),
              ('B','gold_compute/queue_20261018/results/HI1/work/build_B/prepared.xyz')]:
    at=load_xyz(p); R=[None]+[x[1] for x in at]
    c,smi,m=cip_from_atoms(at)
    t_chain=dih(R[1],R[2],R[7],R[8])
    t_NPh =dih(R[3],R[2],R[7],R[9])
    d=ang_diff(t_NPh,t_chain)
    print(tag,'CIP',c)
    print('  dih(C1,C2,C7,C8)=%.2f  dih(N,C2,C7,C9ipso)=%.2f  Fischer-invariant diff=%.2f'%(t_chain,t_NPh,d))
    print('  => erythro if |diff| small (~0), threo if ~180')
