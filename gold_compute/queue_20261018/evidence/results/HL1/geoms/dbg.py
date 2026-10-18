
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
mol=Chem.AddHs(Chem.MolFromSmiles('C1=CC2CCC1C2')); ps=AllChem.ETKDGv3(); ps.randomSeed=20261018
AllChem.EmbedMolecule(mol,ps); AllChem.MMFFOptimizeMolecule(mol,maxIters=5000)
X=np.array(mol.GetConformer().GetPositions()); S=[a.GetSymbol() for a in mol.GetAtoms()]
for i in range(len(S)): print(i,S[i],np.round(X[i],3))
C4,C5,C6=0,1,2
n=np.cross(X[C5]-X[C4],X[C6]-X[C4]); n/=np.linalg.norm(n)
print('n=',np.round(n,3))
# heights of all atoms above alkene plane (through C4 with normal n)
for i in range(len(S)):
    h=np.dot(X[i]-X[C4],n)
    print(i,S[i],'h=',round(float(h),3),'proj dist',round(float(np.linalg.norm((X[i]-X[C4])-h*n)),3))
