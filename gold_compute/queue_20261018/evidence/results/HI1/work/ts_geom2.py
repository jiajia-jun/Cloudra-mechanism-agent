"""Final syn-Cope TS guess builder:
 (1) rigid rotation about C2-C7 to make dih(Hbeta,C7,C2,N3)=0 (syn-periplanar H / leaving group),
 (2) MMFF94 relaxation of the whole molecule under strong constraints on the reaction coordinate
     C2-N3, C2=C7, C7-Hbeta, O...Hbeta and the torsion.
Atom order (reactant xyz order, = atom-map order for heavy atoms):
 1 C1(Me on C2), 2 C2(alpha), 3 N3, 4 C4(NMe), 5 C5(NMe), 6 O6, 7 C7(beta), 8 C8(Me on C7),
 9-14 Ph, 15-17 H@C1, 18 H@C2, 19-21 H@C4, 22-24 H@C5, 25 H(beta, migrating), 26-28 H@C8, 29-33 PhH
"""
import sys, numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdDetermineBonds
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, clean_xyz, dih

F_C2 = [1,3,4,5,6,15,16,17,18,19,20,21,22,23,24]

def rot(P,p,q,deg,atoms):
    u=P[q]-P[p]; u/=np.linalg.norm(u); th=np.radians(deg); c,s=np.cos(th),np.sin(th); Q=P.copy()
    for a in atoms:
        v=P[a]-P[p]; Q[a]=P[p]+v*c+np.cross(u,v)*s+u*np.dot(u,v)*(1-c)
    return Q

def build(xyz_in, xyz_out, mode='syn', c2n=1.95, c2c7=1.45, cxh=1.30, oh=1.40, vlim=0.02):
    at=load_xyz(xyz_in); syms=[e for e,r in at]
    P=np.array([r for e,r in at]); i=lambda k:k-1
    C2,C7,N3,O6 = i(2),i(7),i(3),i(6)
    if mode=='syn':
        mig, cmig, frag = 25, 7, F_C2
        dA, dB = (2,7), (2,3)
    else:  # regio: H on C1 (atom 16) migrates; C1=C2 forms
        mig, cmig, frag = 16, 1, [3,4,5,6,7,8,9,10,11,12,13,14,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33]
        dA, dB = (1,2), (2,3)
    m_i = i(mig)
    # (1) set dih(Hmig, Cmig, C2, N3) = 0 by rotating the C2-side fragment about C2-Cmig
    for _ in range(8):
        cur=dih(P[m_i],P[i(cmig)],P[C2],P[N3]); err=(0.0-cur+180)%360-180
        if abs(err)<0.05: break
        P=rot(P,C2,i(cmig),err,[i(a) for a in frag])
    # (2) MMFF relax with constraints
    m=Chem.MolFromXYZBlock(clean_xyz([(syms[k],P[k]) for k in range(len(syms))]))
    rdDetermineBonds.DetermineBonds(m,charge=0)
    conf=m.GetConformer(); mp=AllChem.MMFFGetMoleculeProperties(m)
    ff=AllChem.MMFFGetMoleculeForceField(m,mp)
    I=i
    ff.MMFFAddDistanceConstraint(I(dA[0]),I(dA[1]),False,c2c7,c2c7,2000.0)
    ff.MMFFAddDistanceConstraint(I(dB[0]),I(dB[1]),False,c2n,c2n,2000.0)
    ff.MMFFAddDistanceConstraint(I(cmig),I(mig),False,cxh,cxh,2000.0)
    ff.MMFFAddDistanceConstraint(I(6),I(mig),False,oh,oh,2000.0)
    ff.MMFFAddTorsionConstraint(I(mig),I(cmig),I(C2),I(N3),False,10000.0,10000.0,0.0)
    ff.Initialize()
    for _try in range(4):
        try:
            ff.Minimize(maxIts=20000,forceTol=1e-3,energyTol=1e-7); break
        except RuntimeError as e:
            print('  MMFF minimiser warning:', str(e).splitlines()[-1][:80])
    Q=conf.GetPositions()
    r=lambda a,b: float(np.linalg.norm(Q[a-1]-Q[b-1]))
    print('mode',mode,'C2-N3=%.3f C%d-C2=%.3f C%d-H%d=%.3f O6-H%d=%.3f'%(r(2,3),cmig,r(cmig,2),cmig,mig,r(cmig,mig),mig,r(6,mig)))
    print('  dih(H%d,C%d,C2,N3)=%.1f  N3-H%d=%.2f  C%d-O6=%.3f  O6-N3=%.3f'%(
        mig,cmig,dih(Q[i(mig)],Q[i(cmig)],Q[i(2)],Q[i(3)]),mig,r(3,mig),cmig,r(cmig,6),r(6,3)))
    # clash check
    bonded=set()
    for b in m.GetBonds(): bonded.add(tuple(sorted((b.GetBeginAtomIdx()+1,b.GetEndAtomIdx()+1))))
    shorts=[]
    for a in range(len(syms)):
        for b in range(a+1,len(syms)):
            dd=r(a+1,b+1)
            if dd<1.05 and (a+1,b+1) not in bonded: shorts.append((round(dd,3),a+1,b+1))
    print('  short nonbonded contacts <1.05 A:',sorted(shorts)[:6])
    out=[(syms[k],Q[k]) for k in range(len(syms))]
    open(xyz_out,'w').write(clean_xyz(out,'HI1 %s TS guess (rigid syn rotamer + MMFF constrained)'%mode))

if __name__=='__main__':
    build(sys.argv[1],sys.argv[2], sys.argv[3] if len(sys.argv)>3 else 'syn')
