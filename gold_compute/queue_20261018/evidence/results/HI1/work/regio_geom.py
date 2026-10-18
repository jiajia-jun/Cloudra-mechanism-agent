"""Deterministic geometric regio-channel TS guess (H from the C1 methyl migrates to the N-oxide O,
C1=C2 forms, C2-N3 breaks) -- no force field, only rigid fragment motions."""
import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, clean_xyz, dih

def rot(P,p,q,deg,atoms):
    u=P[q]-P[p]; u/=np.linalg.norm(u); th=np.radians(deg); c,s=np.cos(th),np.sin(th); Q=P.copy()
    for a in atoms:
        v=P[a]-P[p]; Q[a]=P[p]+v*c+np.cross(u,v)*s+u*np.dot(u,v)*(1-c)
    return Q

def build(xyz_in, xyz_out, c2n=2.00, c1c2=1.40, c1h=1.30):
    at=load_xyz(xyz_in); syms=[e for e,r in at]
    P=np.array([r for e,r in at]); i=lambda k:k-1
    C1,C2,N3,O6,H16 = i(1),i(2),i(3),i(6),i(16)
    far = [k for k in range(33) if k+1 not in (1,2,15,16,17)]   # everything on the C2 side except C1/H's
    F_N = [i(k) for k in (4,5,6,19,20,21,22,23,24)]
    # a) syn-periplanar H16 / N3 about the C1-C2 bond
    for _ in range(10):
        cur=dih(P[H16],P[C1],P[C2],P[N3]); err=(0.0-cur+180)%360-180
        if abs(err)<0.05: break
        Q=rot(P,C2,C1,err,far)
        if abs((lambda t:(t+180)%360-180)(dih(Q[H16],Q[C1],Q[C2],Q[N3]))) > abs(err):
            Q=rot(P,C2,C1,-err,far)
        P=Q
    print('a) dih(H16,C1,C2,N3)=%.2f'%dih(P[H16],P[C1],P[C2],P[N3]))
    # b) choose O6 orientation about C2->N3 closest to H16
    best=None
    for psi in np.arange(0,360,1.0):
        Q=rot(P,C2,N3,psi,F_N); d=np.linalg.norm(Q[O6]-Q[H16])
        if best is None or d<best[1]: best=(psi,d)
    P=rot(P,C2,N3,best[0],F_N)
    print('b) psi=%.0f d(O6,H16)=%.3f'%(best[0],best[1]))
    # c) C2-N3 -> c2n
    u=P[N3]-P[C2]; dd=np.linalg.norm(u); u/=dd
    for a in [i(3)]+F_N: P[a]+=(c2n-dd)*u
    best=None
    for psi in np.arange(0,360,1.0):
        Q=rot(P,C2,N3,psi,F_N); d=np.linalg.norm(Q[O6]-Q[H16])
        if best is None or d<best[1]: best=(psi,d)
    P=rot(P,C2,N3,best[0],F_N)
    # d) C1-C2 -> c1c2 (move C1 and its two other H's)
    u=P[C1]-P[C2]; dd=np.linalg.norm(u); u/=dd
    for a in (C1,i(15),i(17)): P[a]+=(c1c2-dd)*u
    best=None
    for psi in np.arange(0,360,1.0):
        Q=rot(P,C2,N3,psi,F_N); d=np.linalg.norm(Q[O6]-Q[H16])
        if best is None or d<best[1]: best=(psi,d)
    P=rot(P,C2,N3,best[0],F_N)
    # e) put H16 at c1h from C1 toward O6
    v=P[O6]-P[C1]; v/=np.linalg.norm(v)
    P[H16]=P[C1]+c1h*v
    r=lambda a,b: float(np.linalg.norm(P[a-1]-P[b-1]))
    print('e) C2-N3=%.3f C1-C2=%.3f C1-H16=%.3f O6-H16=%.3f C1-O6=%.3f N3-H16=%.3f'%(
        r(2,3),r(1,2),r(1,16),r(6,16),r(1,6),r(3,16)))
    print('   dih(H16,C1,C2,N3)=%.1f dih(O6,N3,C2,C1)=%.1f'%(dih(P[H16],P[C1],P[C2],P[N3]),dih(P[O6],P[N3],P[C2],P[C1])))
    out=[(syms[k],P[k]) for k in range(len(syms))]
    open(xyz_out,'w').write(clean_xyz(out,'HI1 regio syn TS geometric guess'))

if __name__=='__main__':
    build(sys.argv[1], sys.argv[2])
