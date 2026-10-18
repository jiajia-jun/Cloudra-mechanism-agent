
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
sm='C1=NOC2C3CCC(C3)C12'
m=Chem.MolFromSmiles(sm)
opts=Chem.EnumerateStereoisomers(m)
iso=list(Chem.Stereoisomers.EnumerateStereoisomers(m))
print('n stereoisomers',len(iso))
for k,mol in enumerate(iso):
    smi=Chem.MolToSmiles(mol)
    mh=Chem.AddHs(mol)
    ps=AllChem.ETKDGv3(); ps.randomSeed=7
    if AllChem.EmbedMolecule(mh,ps)!=0: print(smi,'embed fail'); continue
    AllChem.MMFFOptimizeMolecule(mh,maxIters=2000)
    X=mh.GetConformer().GetPositions(); S=[a.GetSymbol() for a in mh.GetAtoms()]
    # atom 6 in SMILES order is methano C (C3) ; find: heavy atoms order = C1,N,O,C2,C3,C,C,C,(C3),C1,C2 -> index?
    # print heavy coords mapping
    print(k,smi,'heavy:',S[:10])
    # identify methano carbon: the CH2 carbon bonded to two CH (bridgeheads)
    idx={}
    for a in mh.GetAtoms():
        if a.GetSymbol()!='H':
            idx[a.GetIdx()]=(a.GetSymbol(),[n.GetIdx() for n in a.GetNeighbors() if n.GetSymbol()!='H'])
    print('   ',idx)
