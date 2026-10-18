
import numpy as np, json
from rdkit import Chem
from rdkit.Chem import AllChem
mol=Chem.AddHs(Chem.MolFromSmiles('C1=CC2CCC1C2')); ps=AllChem.ETKDGv3(); ps.randomSeed=20261018
AllChem.EmbedMolecule(mol,ps); AllChem.MMFFOptimizeMolecule(mol,maxIters=5000)
X=np.array(mol.GetConformer().GetPositions()); S=[a.GetSymbol() for a in mol.GetAtoms()]
C4,C5,C6,C10=0,1,2,6
u=(X[C5]-X[C4]); u/=np.linalg.norm(u)
n=np.cross(X[C5]-X[C4],X[C6]-X[C4]); n/=np.linalg.norm(n)
if np.dot(n,X[C10]-X[C4])>0: n=-n
w=np.cross(n,u); w/=np.linalg.norm(w)
P=json.load(open('gold_compute/queue_20261018/results/HL1/geoms/place_params.json'))
for tag in ('exo','endo'):
    fr={k:np.array(P[tag][k]) for k in ('C','N','O','H')}
    atoms=[(S[i],X[i]) for i in range(len(S))]+[('C',fr['C']),('N',fr['N']),('O',fr['O']),('H',fr['H'])]
    out='gold_compute/queue_20261018/results/HL1/geoms/RC_%s.xyz'%tag
    face='exo (anti to methano C10)' if tag=='exo' else 'endo (syn to methano C10)'
    with open(out,'w') as f:
        f.write('%d\nHL1 RC_%s | %s | SMILES: C#[N+][O-].C1=CC2CCC1C2 | atoms 1-17 norbornene (map C4=1,C5=2,C6=3,C7=4,C8=5,C9=6,C10=7), 18=C1(dip) 19=N2 20=O3 21=H\n'%(len(atoms),tag,face))
        for sy,p in atoms: f.write('%-3s %14.8f %14.8f %14.8f\n'%(sy,p[0],p[1],p[2]))
    d1=np.linalg.norm(fr['C']-X[C4]); d2=np.linalg.norm(fr['O']-X[C5])
    print(tag,'written',out,' d(C4-Cdip)=%.3f d(C5-Odip)=%.3f'%(d1,d2))
