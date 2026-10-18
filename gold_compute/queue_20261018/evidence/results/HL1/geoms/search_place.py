
import numpy as np, itertools
from rdkit import Chem
from rdkit.Chem import AllChem
mol=Chem.AddHs(Chem.MolFromSmiles('C1=CC2CCC1C2')); ps=AllChem.ETKDGv3(); ps.randomSeed=20261018
AllChem.EmbedMolecule(mol,ps); AllChem.MMFFOptimizeMolecule(mol,maxIters=5000)
X=np.array(mol.GetConformer().GetPositions()); S=[a.GetSymbol() for a in mol.GetAtoms()]
C4,C5,C6,C10=0,1,2,6
u=(X[C5]-X[C4]); u/=np.linalg.norm(u)
n=np.cross(X[C5]-X[C4],X[C6]-X[C4]); n/=np.linalg.norm(n)
if np.dot(n,X[C10]-X[C4])>0: n=-n   # n -> EXO
w=np.cross(n,u); w/=np.linalg.norm(w)
nbr=[(S[i],X[i]) for i in range(len(S))]
d_CN,d_NO,d_CH=1.161,1.207,1.061

def place(h,s,th,ph,face):
    nf=face*n
    P=X[C4]+h*nf+s*u
    d=np.cos(th)*(np.cos(ph)*u+np.sin(ph)*w)+np.sin(th)*nf
    return {'C':P,'N':P+d_CN*d,'O':P+(d_CN+d_NO)*d,'H':P-d_CH*d}

def score(fr,face):
    nf=face*n
    dc=np.linalg.norm(fr['C']-X[C4]); do=np.linalg.norm(fr['O']-X[C5])
    dmin=min(np.linalg.norm(fr[k]-X[i]) for k in fr for i in range(len(S)))
    pen=0
    if not (2.80<=dc<=3.20): pen+=10*(abs(dc-3.0))
    if not (2.80<=do<=3.20): pen+=10*(abs(do-3.0))
    if dmin<1.95: pen+=10*(1.95-dmin)
    return pen,dc,do,dmin

for face,tag in ((-1.0,'exo'),(1.0,'endo')):
    best=None
    for h in np.arange(2.85,3.31,0.05):
        for s in np.arange(-0.4,0.41,0.1):
            for th in np.arange(-30,31,10):
                for ph in np.arange(-60,61,15):
                    fr=place(h,s,np.radians(th),np.radians(ph),face)
                    p=score(fr,face)
                    if best is None or p[0]<best[0][0]-1e-9: best=(p,(h,s,th,ph))
    p,(h,s,th,ph)=best
    print(tag,'best params h=%.2f s=%.2f th=%d ph=%d'%(h,s,th,ph),'pen=%.3f dc=%.3f do=%.3f dmin=%.3f'%p)
    fr=place(h,s,np.radians(th),np.radians(ph),face)
    dmin=min(((np.linalg.norm(fr[k]-X[i]),k,i) for k in fr for i in range(len(S))))
    print('  closest:',round(float(dmin[0]),3),dmin[1],S[dmin[2]]+str(dmin[2]+1))
    np.save('/tmp/fr_%s.npy'%tag, np.array([[fr[k][0],fr[k][1],fr[k][2]] for k in ['C','N','O','H']]))
    print('  params stored', (h,s,th,ph))
