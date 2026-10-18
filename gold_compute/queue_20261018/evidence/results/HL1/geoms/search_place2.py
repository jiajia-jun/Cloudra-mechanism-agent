
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
mol=Chem.AddHs(Chem.MolFromSmiles('C1=CC2CCC1C2')); ps=AllChem.ETKDGv3(); ps.randomSeed=20261018
AllChem.EmbedMolecule(mol,ps); AllChem.MMFFOptimizeMolecule(mol,maxIters=5000)
X=np.array(mol.GetConformer().GetPositions()); S=[a.GetSymbol() for a in mol.GetAtoms()]
C4,C5,C6,C10=0,1,2,6
u=(X[C5]-X[C4]); u/=np.linalg.norm(u)
n=np.cross(X[C5]-X[C4],X[C6]-X[C4]); n/=np.linalg.norm(n)
if np.dot(n,X[C10]-X[C4])>0: n=-n   # n -> EXO face (C10 is endo)
w=np.cross(n,u); w/=np.linalg.norm(w)
assert np.dot(n,X[C10]-X[C4])<0
d_CN,d_NO,d_CH=1.161,1.207,1.061
print('C10 n-coord (exo frame):',round(float(np.dot(X[C10]-X[C4],n)),3))

def place(h,s,woff,th,face):
    nf=face*n
    P=X[C4]+h*nf+s*u+woff*w
    d=np.cos(th)*u+np.sin(th)*nf
    return {'C':P,'N':P+d_CN*d,'O':P+(d_CN+d_NO)*d,'H':P-d_CH*d},nf

def score(fr):
    dc=np.linalg.norm(fr['C']-X[C4]); do=np.linalg.norm(fr['O']-X[C5])
    dmin=min(np.linalg.norm(fr[k]-X[i]) for k in fr for i in range(len(S)))
    pen=0.0
    if not (2.80<=dc<=3.20): pen+=20*(abs(dc-3.0))
    if not (2.80<=do<=3.20): pen+=20*(abs(do-3.0))
    if dmin<2.05: pen+=20*(2.05-dmin)
    pen+=3*abs(woff)   # prefer small lateral offset
    return pen,dc,do,dmin

res={}
for face,tag in ((1.0,'exo'),(-1.0,'endo')):
    best=None
    for h in np.arange(2.80,3.26,0.05):
      for s in np.arange(-0.6,0.61,0.1):
        for woff in np.arange(-1.2,1.21,0.1):
          for th in np.arange(-30,31,10):
            fr,nf=place(h,s,woff,np.radians(th),face)
            p=score(fr)
            if best is None or p[0]<best[0][0]-1e-9: best=(p,(h,s,woff,th))
    p,(h,s,woff,th)=best
    fr,nf=place(h,s,woff,np.radians(th),face)
    pairs=sorted([(round(float(np.linalg.norm(fr[k]-X[i])),3),k,S[i]+str(i+1)) for k in fr for i in range(len(S))])[:6]
    print(tag,'h=%.2f s=%.2f woff=%.2f th=%d'%(h,s,woff,th),'pen=%.3f dc=%.3f do=%.3f dmin=%.3f'%p)
    print('   closest:',pairs)
    res[tag]=(h,s,woff,th,fr)
np.save('/tmp/place.npy', np.array([1]))
import json
json.dump({t:{'h':float(v[0]),'s':float(v[1]),'woff':float(v[2]),'th':float(v[3]),
              'C':[float(x) for x in v[4]['C']],'N':[float(x) for x in v[4]['N']],
              'O':[float(x) for x in v[4]['O']],'H':[float(x) for x in v[4]['H']]} for t,v in res.items()},
          open('/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/place_params.json','w'),indent=1)
