import numpy as np, sys
from rdkit import Chem
from rdkit.Chem import AllChem
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import dih

def build(smi):
    m=Chem.AddHs(Chem.MolFromSmiles(smi))
    ps=AllChem.ETKDGv3(); ps.randomSeed=0xf00d
    AllChem.EmbedMolecule(m,ps); AllChem.MMFFOptimizeMolecule(m, maxIters=5000)
    return m, m.GetConformer().GetPositions()

def idx(m,n):
    for a in m.GetAtoms():
        if a.GetAtomMapNum()==n: return a.GetIdx()
    raise KeyError(n)

def inv(smi, chain, subs):
    m,c=build(smi)
    a,b,cc,d=[idx(m,k) for k in chain]
    xb,xc=[idx(m,k) for k in subs]
    t1=dih(c[a],c[b],c[cc],c[d]); t2=dih(c[xb],c[b],c[cc],c[xc])
    return (t2-t1+180.0)%360.0-180.0, t1, t2

cases=[
 ('L-Thr(2S,3R) THREO','[CH3:8][C@H:6]([OH:7])[C@@H:4]([NH2:5])[C:1](=[O:2])[OH:3]',(1,4,6,8),(5,7)),
 ('L-allo-Thr(2S,3S) ERYTHRO','[CH3:8][C@H:6]([OH:7])[C@H:4]([NH2:5])[C:1](=[O:2])[OH:3]',(1,4,6,8),(5,7)),
]
for name,smi,ch,su in cases:
    m,_=build(smi)
    print(name,'CIP:',[(a.GetIdx(),a.GetProp('_CIPCode')) for a in m.GetAtoms() if a.HasProp('_CIPCode')])
    print('   invariant',inv(smi,ch,su))
