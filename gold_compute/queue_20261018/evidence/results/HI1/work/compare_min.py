import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, cip_from_atoms, dih
base='gold_compute/queue_20261018/results/HI1/geoms/'
for tag,a,b in [('erythro','HI1_erythro_R_min.xyz','HI1_erythro_Rend_min.xyz'),('threo','HI1_threo_R_min.xyz','HI1_threo_Rend_min.xyz')]:
    A=load_xyz(base+a); B=load_xyz(base+b)
    RA=[x[1] for x in A]; RB=[x[1] for x in B]
    r=lambda R,i,j: float(np.linalg.norm(R[i-1]-R[j-1]))
    d=lambda R,i,j,k,l: dih(R[i-1],R[j-1],R[k-1],R[l-1])
    print('==',tag)
    for nm,R in (('seed(job %d)'%(1224 if tag=='erythro' else 1225),RA),('IRC endpoint',RB)):
        print('  ',nm,'CIP',cip_from_atoms([(A[i][0] if nm.startswith('seed') else B[i][0], R[i]) for i in range(len(R))])[0],
              'd(C2,N3)=%.3f d(C7,H25)=%.3f d(N3,O6)=%.3f'%(r(R,2,3),r(R,7,25),r(R,3,6)))
        print('      dih(H25,C7,C2,N3)=%.1f dih(C1,C2,C7,C8)=%.1f dih(O6,N3,C2,C7)=%.1f dih(N3,C2,C7,C9)=%.1f'%(
            d(R,25,7,2,3), d(R,1,2,7,8), d(R,6,3,2,7), d(R,3,2,7,9)))
    # all-atom RMSD after Kabsch
    P=np.array(RA); Q=np.array(RB)
    Pc=P-P.mean(0); Qc=Q-Q.mean(0)
    H=Pc.T@Qc; U,S,Vt=np.linalg.svd(H); dsign=np.sign(np.linalg.det(Vt.T@U.T))
    Rm=Vt.T@np.diag([1,1,dsign])@U.T
    Pr=(Rm@Pc.T).T
    dev=np.linalg.norm(Pr-Qc,axis=1)
    print('   Kabsch all-atom RMSD=%.3f max|dev|=%.3f atom=%d'%(np.sqrt((dev**2).mean()), dev.max(), int(dev.argmax())+1))
