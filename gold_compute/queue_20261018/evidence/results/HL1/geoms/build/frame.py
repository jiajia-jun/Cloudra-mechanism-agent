
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
nb = Chem.AddHs(Chem.MolFromSmiles("C1=CC2CCC1C2"))
ps = AllChem.ETKDGv3(); ps.randomSeed = 20261018
AllChem.EmbedMolecule(nb, ps); AllChem.MMFFOptimizeMolecule(nb, maxIters=5000)
X = np.array(nb.GetConformer().GetPositions())
A,B,BH1,BH2,MB = 0,1,2,5,6
u = (X[B]-X[A]); u/=np.linalg.norm(u)
P4 = np.array([X[A],X[B],X[BH1],X[BH2]]); c=P4.mean(axis=0)
_,_,Vt = np.linalg.svd(P4-c); n=Vt[2]; n/=np.linalg.norm(n)
if np.dot(X[MB]-c,n)<0: n=-n
w = n
print("plane centroid (A):", np.round(c,4))
print("u (C1->C2)      :", np.round(u,6))
print("n         (exo+)  :", np.round(n,6))
print("w = +1*n (exo)    :", np.round(w,6), "  w = -1*n (endo)")
print("sdist C10 = %+.4f  sdist ethano C7/C8 = %+.4f %+.4f" % (np.dot(X[MB]-c,n), np.dot(X[3]-c,n), np.dot(X[4]-c,n)))
print("|C1-C2| = %.4f  |C6..C9| = %.4f" % (np.linalg.norm(X[B]-X[A]), np.linalg.norm(X[BH1]-X[BH2])))
# perpendicular/tangential decomposition of C10 relative to alkene midpoint
M=(X[A]+X[B])/2
v=X[MB]-M
print("C10-mid vector:", np.round(v,4), " perp=%+.3f tang=%+.3f"%(np.dot(v,n), np.dot(v,u)))
