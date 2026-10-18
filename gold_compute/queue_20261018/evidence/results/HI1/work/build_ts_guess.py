"""Build syn-Cope TS guess by MMFF94 relaxation with reaction-coordinate constraints.
Atom order = reactant xyz order: 1 C1(Me),2 C2(alpha),3 N3,4 C4(NMe),5 C5(NMe),6 O6,7 C7(beta),8 C8(Me),
9-14 Ph, 15-17 H@C1, 18 H@C2, 19-21 H@C4, 22-24 H@C5, 25 H(beta, migrating), 26-28 H@C8, 29-33 PhH
"""
import sys, numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdDetermineBonds
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, clean_xyz, dih

def build_guess(xyz_in, xyz_out, mode='syn', c2n=1.95, c2c7=1.44, cxh=1.32, oh=1.36):
    at = load_xyz(xyz_in); syms=[e for e,r in at]
    m = Chem.MolFromXYZBlock(clean_xyz(at))
    rdDetermineBonds.DetermineBonds(m, charge=0)
    conf = m.GetConformer()
    ff = AllChem.MMFFGetMoleculeForceField(m, AllChem.MMFFGetMoleculeProperties(m))
    I = lambda i: i-1
    if mode=='syn':
        mig, cmig = 25, 7
        ff.MMFFAddDistanceConstraint(I(2), I(7), False, c2c7, c2c7, 500.0)
        ff.MMFFAddDistanceConstraint(I(2), I(3), False, c2n, c2n, 500.0)
        ff.MMFFAddDistanceConstraint(I(cmig), I(mig), False, cxh, cxh, 500.0)
        ff.MMFFAddDistanceConstraint(I(6), I(mig), False, oh, oh, 500.0)
        ff.MMFFAddTorsionConstraint(I(mig), I(cmig), I(2), I(3), False, 300.0, 300.0, 5.0)
    else:
        mig, cmig = 16, 1
        ff.MMFFAddDistanceConstraint(I(1), I(2), False, 1.40, 1.40, 500.0)
        ff.MMFFAddDistanceConstraint(I(2), I(3), False, c2n, c2n, 500.0)
        ff.MMFFAddDistanceConstraint(I(cmig), I(mig), False, cxh, cxh, 500.0)
        ff.MMFFAddDistanceConstraint(I(6), I(mig), False, oh, oh, 500.0)
        ff.MMFFAddTorsionConstraint(I(mig), I(cmig), I(2), I(3), False, 300.0, 300.0, 5.0)
    ff.Initialize()
    res = ff.Minimize(maxIts=20000, forceTol=1e-4, energyTol=1e-8)
    new = conf.GetPositions()
    out = [(syms[i], new[i]) for i in range(len(syms))]
    open(xyz_out,'w').write(clean_xyz(out, 'HI1 %s TS guess MMFF-constrained'%mode))
    def d(i,j,k,l): return dih(new[i-1],new[j-1],new[k-1],new[l-1])
    def r(i,j): return float(np.linalg.norm(new[i-1]-new[j-1]))
    print('mode',mode,'rc',res)
    print('  d(C2,N3)=%.3f d(C2,C7)=%.3f d(C%d,H%d)=%.3f d(O6,H%d)=%.3f'%(r(2,3),r(2,7),cmig,mig,r(cmig,mig),mig,r(6,mig)))
    print('  dih(H%d,C%d,C2,N3)=%.1f'%(mig,cmig,d(mig,cmig,2,3)))
    print('  ring: d(N3,C7)=%.3f d(O6,N3)=%.3f d(O6,C2)=%.3f'%(r(3,7),r(6,3),r(6,2)))
    bonded=set([(1,2),(2,3),(3,4),(3,5),(3,6),(2,7),(8,7),(9,7),(7,25),(6,25),(1,16),(2,18),(1,15),(1,17),(4,19),(4,20),(4,21),(5,22),(5,23),(5,24),(8,26),(8,27),(8,28)])
    worst=[]
    for i in range(len(out)):
        for j in range(i+1,len(out)):
            dd=r(i+1,j+1)
            if dd<1.35 and (i+1,j+1) not in bonded and (j+1,i+1) not in bonded:
                worst.append((round(dd,3),i+1,j+1))
    print('  short contacts:',sorted(worst)[:8])

if __name__=='__main__':
    build_guess(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv)>3 else 'syn')
