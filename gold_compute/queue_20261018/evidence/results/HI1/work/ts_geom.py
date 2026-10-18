"""Deterministic geometric construction of a syn-Cope elimination TS guess.
Atom order (reactant xyz order):
 1 C1(Me on C2), 2 C2(alpha, bears N-oxide), 3 N3, 4 C4(NMe), 5 C5(NMe), 6 O6(-),
 7 C7(beta, bears Ph), 8 C8(Me on C7), 9-14 Ph, 15-17 H@C1, 18 H@C2, 19-21 H@C4,
 22-24 H@C5, 25 H(beta, migrating), 26-28 H@C8, 29-33 PhH
"""
import sys, numpy as np
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, clean_xyz, dih

PH = [9,10,11,12,13,14,29,30,31,32,33]
F_C2 = [1,3,4,5,6,15,16,17,18,19,20,21,22,23,24]
F_N3 = [4,5,6,19,20,21,22,23,24]
F_C7 = [7,8,25,26,27,28]+PH

def rot(P, p, q, deg, atoms):
    u = P[q]-P[p]; u/=np.linalg.norm(u)
    th=np.radians(deg); c,s=np.cos(th),np.sin(th); Q=P.copy()
    for a in atoms:
        v=P[a]-P[p]
        Q[a]=P[p]+v*c+np.cross(u,v)*s+u*np.dot(u,v)*(1-c)
    return Q

def set_dih(P, four, target, p, q, atoms, iters=8):
    """rotate 'atoms' about axis p->q until dih(four)->target"""
    for _ in range(iters):
        cur = dih(P[four[0]],P[four[1]],P[four[2]],P[four[3]])
        err = (target-cur+180.0)%360.0-180.0
        if abs(err)<0.05: break
        P = rot(P, p, q, err, atoms)
    return P

def build(xyz_in, xyz_out, c2n=1.95, c2c7=1.45, c7h=1.30, oh=1.35, verbose=True):
    at = load_xyz(xyz_in); syms=[e for e,r in at]
    P = np.array([r for e,r in at]); i=lambda k:k-1
    C2,C7,N3,O6,H25 = i(2),i(7),i(3),i(6),i(25)
    # 1) dih(H25,C7,C2,N3) -> 0  (rotate C2-side fragment about C2->C7)
    P = set_dih(P,(H25,C7,C2,N3),0.0,C2,C7,[i(a) for a in F_C2])
    if verbose: print('1) dih(H25,C7,C2,N3)=%.2f'%dih(P[H25],P[C7],P[C2],P[N3]))
    # 2) C2-N3 -> c2n
    for _ in range(3):
        u=P[N3]-P[C2]; dd=np.linalg.norm(u); u/=dd
        sh=(c2n-dd)*u
        for a in [i(3),i(4),i(5),i(6)]+[i(k) for k in range(19,25)]: P[a]+=sh
    # 3) C2-C7 -> c2c7 (translate C7 side)
    u=P[C7]-P[C2]; dd=np.linalg.norm(u); u/=dd
    for a in [i(k) for k in F_C7]: P[a]+=(c2c7-dd)*u
    # 4) scan psi about C2->N3 to minimise d(O6,H25)
    best=None
    for psi in np.arange(0,360,1.0):
        Q=rot(P,C2,N3,psi,[i(a) for a in F_N3]); d=np.linalg.norm(Q[O6]-Q[H25])
        if best is None or d<best[1]: best=(psi,d)
    P=rot(P,C2,N3,best[0],[i(a) for a in F_N3])
    if verbose: print('4) psi=%.1f d(O6,H25)=%.3f d(C7,O6)=%.3f'%(best[0],best[1],np.linalg.norm(P[C7]-P[O6])))
    # 5) place H25 at c7h from C7, oh from O6 (sphere intersection, nearest to current)
    rC, rO = c7h, oh
    dCO = np.linalg.norm(P[O6]-P[C7]); e=(P[O6]-P[C7])/dCO
    if dCO >= rC+rO or dCO <= abs(rC-rO):
        if verbose: print('   !! no sphere intersection, d(C7,O6)=%.3f'%dCO)
    a=(rC*rC - rO*rO + dCO*dCO)/(2*dCO); h2=rC*rC-a*a
    h=np.sqrt(max(h2,0.0))
    base=P[C7]+a*e
    # pick perpendicular direction closest to current H25
    v=P[H25]-base; v=v-np.dot(v,e)*e; nv=np.linalg.norm(v)
    perp = v/nv if nv>1e-6 else np.cross(e,[1.0,0,0])/np.linalg.norm(np.cross(e,[1.0,0,0]))
    P[H25]=base+h*perp
    if verbose:
        r=lambda a_,b_: float(np.linalg.norm(P[i(a_)]-P[i(b_)]))
        print('5) C2-N3=%.3f C2-C7=%.3f C7-H25=%.3f O6-H25=%.3f C7-O6=%.3f N3-C7=%.3f O6-N3=%.3f C2-O6=%.3f'%(
            r(2,3),r(2,7),r(7,25),r(6,25),r(7,6),r(3,7),r(6,3),r(2,6)))
        print('   dih(H25,C7,C2,N3)=%.1f  dih(O6,N3,C2,C7)=%.1f  angle C7-H25-O6=%.1f  angle H25-O6-N3=%.1f'%(
            dih(P[H25],P[C7],P[C2],P[N3]), dih(P[O6],P[N3],P[C2],P[C7]),
            np.degrees(np.arccos(np.dot((P[C7]-P[H25])/np.linalg.norm(P[C7]-P[H25]),(P[O6]-P[H25])/np.linalg.norm(P[O6]-P[H25])))),
            np.degrees(np.arccos(np.dot((P[H25]-P[O6])/np.linalg.norm(P[H25]-P[O6]),(P[N3]-P[O6])/np.linalg.norm(P[N3]-P[O6]))))))
        print('   H25-C2=%.3f H25-N3=%.3f'%(r(25,2),r(25,3)))
    out=[(syms[k],P[k]) for k in range(len(syms))]
    open(xyz_out,'w').write(clean_xyz(out,'HI1 syn-Cope TS geometric guess'))
    return P

if __name__=='__main__':
    build(sys.argv[1], sys.argv[2])
