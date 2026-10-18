import sys, numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdDetermineBonds
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, clean_xyz, dih
at=load_xyz(sys.argv[1]); syms=[e for e,r in at]
m=Chem.MolFromXYZBlock(clean_xyz(at)); rdDetermineBonds.DetermineBonds(m,charge=0)
conf=m.GetConformer(); pos=conf.GetPositions()
for init in (False,True):
    conf.SetPositions(pos)
    mp=AllChem.MMFFGetMoleculeProperties(m)
    ff=AllChem.MMFFGetMoleculeForceField(m,mp)
    I=lambda i:i-1
    ff.MMFFAddDistanceConstraint(I(2),I(3),False,1.95,1.95,2000.0)
    ff.MMFFAddDistanceConstraint(I(2),I(7),False,1.45,1.45,2000.0)
    ff.MMFFAddDistanceConstraint(I(7),I(25),False,1.30,1.30,2000.0)
    ff.MMFFAddDistanceConstraint(I(6),I(25),False,1.40,1.40,2000.0)
    ff.MMFFAddTorsionConstraint(I(25),I(7),I(2),I(3),False,2000.0,2000.0,0.0)
    if init: ff.Initialize()
    ff.Minimize(maxIts=20000, forceTol=1e-4, energyTol=1e-8)
    P=conf.GetPositions()
    r=lambda a,b: float(np.linalg.norm(P[a-1]-P[b-1]))
    print('init=',init,'C2-N3=%.3f C2-C7=%.3f C7-H25=%.3f O6-H25=%.3f dih=%.1f N3-H25=%.3f C7-O6=%.3f'%(
        r(2,3),r(2,7),r(7,25),r(6,25),dih(P[24],P[6],P[1],P[2]),r(3,25),r(7,6)))
