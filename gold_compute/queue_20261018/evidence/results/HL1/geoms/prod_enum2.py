
import numpy as np, json
from rdkit import Chem
from rdkit.Chem import AllChem
sm='C1=NOC2C3CCC(C3)C12'
m=Chem.MolFromSmiles(sm)
iso=list(Chem.Stereoisomers.EnumerateStereoisomers(m))
print('n stereoisomers',len(iso))
res={}
for k,mol in enumerate(iso):
    smi=Chem.MolToSmiles(mol)
    mh=Chem.AddHs(mol)
    ps=AllChem.ETKDGv3(); ps.randomSeed=7
    if AllChem.EmbedMolecule(mh,ps)!=0: print(smi,'embed fail'); continue
    AllChem.MMFFOptimizeMolecule(mh,maxIters=2000)
    X=mh.GetConformer().GetPositions(); S=[a.GetSymbol() for a in mh.GetAtoms()]
    nb={a.GetIdx():[n.GetIdx() for n in a.GetNeighbors() if n.GetSymbol()!='H'] for a in mh.GetAtoms() if a.GetSymbol()!='H'}
    print(k,smi)
    methano=None
    for i in range(11):
        if len(nb[i])==2 and all(len(nb[j])==3 for j in nb[i]):
            methano=i
    bh=nb[methano]
    O=[i for i in range(11) if S[i]=='O'][0]; N=[i for i in range(11) if S[i]=='N'][0]
    print('   methano',methano,'bridgeheads',bh,'O',O,'N',N)
    res[smi]=dict(methano=int(methano),bh=[int(b) for b in bh],O=int(O),N=int(N),
                  xyz=[[float(v) for v in p] for p in X], syms=S)
json.dump(res, open('gold_compute/queue_20261018/results/HL1/geoms/prod_stereo.json','w'), indent=1)
print('heavy count',len([1 for s in S if s!='H']),'total',len(S))
