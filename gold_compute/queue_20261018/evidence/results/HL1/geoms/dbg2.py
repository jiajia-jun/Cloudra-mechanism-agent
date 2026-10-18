
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
mol=Chem.AddHs(Chem.MolFromSmiles('C1=CC2CCC1C2')); ps=AllChem.ETKDGv3(); ps.randomSeed=20261018
AllChem.EmbedMolecule(mol,ps); AllChem.MMFFOptimizeMolecule(mol,maxIters=5000)
X=np.array(mol.GetConformer().GetPositions()); S=[a.GetSymbol() for a in mol.GetAtoms()]
C4,C5,C6,C10=0,1,2,6
u=(X[C5]-X[C4]); u/=np.linalg.norm(u)
n=np.cross(X[C5]-X[C4],X[C6]-X[C4]); n/=np.linalg.norm(n)
if np.dot(n,X[C10]-X[C4])>0: n=-n    # n -> EXO side (away from methano C10)
w=np.cross(n,u); w/=np.linalg.norm(w)
O=X[C4]
print('frame: u along C4->C5, n toward EXO, w = n x u')
for i in range(len(S)):
    d=X[i]-O; print('%2d %s  u=%6.3f n=%6.3f w=%6.3f'%(i,S[i],d@u,d@n,d@w))
