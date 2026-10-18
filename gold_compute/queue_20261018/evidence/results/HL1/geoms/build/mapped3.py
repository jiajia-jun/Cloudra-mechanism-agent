
import numpy as np, os
from rdkit import Chem
B="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/build"
HBOND = {7:0, 8:1, 9:2, 10:3, 11:3, 12:4, 13:4, 14:5, 15:6, 16:6}
def mk(xyz, border, charges=()):
    lines=open(os.path.join(B,xyz)).read().splitlines()
    els=[l.split()[0] for l in lines[2:23]]
    coords=np.array([[float(x) for x in l.split()[1:4]] for l in lines[2:23]])
    rw=Chem.RWMol()
    for e in els: rw.AddAtom(Chem.Atom(e))
    BS={1:Chem.BondType.SINGLE,2:Chem.BondType.DOUBLE,3:Chem.BondType.TRIPLE}
    for (a,b),o in border.items(): rw.AddBond(a,b,BS[o])
    m=rw.GetMol()
    for i,q in charges: m.GetAtomWithIdx(i).SetFormalCharge(q)
    Chem.SanitizeMol(m)
    for i in range(m.GetNumAtoms()): m.GetAtomWithIdx(i).SetNoImplicit(True)
    c=Chem.Conformer(21)
    for i in range(21): c.SetAtomPosition(i,[float(v) for v in coords[i]])
    m.RemoveAllConformers(); m.AddConformer(c)
    Chem.AssignStereochemistryFrom3D(m)
    return m
nb={}
for a,b in [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,6),(6,5)]: nb[(a,b)]=1
for j,i in HBOND.items(): nb[(i,j)]=1
nb[(0,1)]=2
rb=dict(nb); rb[(17,18)]=3; rb[(18,19)]=1; rb[(17,20)]=1
mr = mk("RCg_exo.xyz", rb, charges=[(18,1),(19,-1)])
pb=dict(nb); pb.update({(0,17):1,(17,18):2,(18,19):1,(19,1):1,(17,20):1}); pb[(0,1)]=1
mp = mk("P_endo_start.xyz", pb)
idxmap = {0:4,1:5,2:6,3:7,4:8,5:9,6:10, 17:1,18:2,19:3}
for tag, m in [("reactant",mr),("product",mp)]:
    mh = Chem.RemoveHs(m)
    heavy_order = [a.GetIdx() for a in m.GetAtoms() if a.GetSymbol()!="H"]
    for newi, oldi in enumerate(heavy_order):
        mh.GetAtomWithIdx(newi).SetAtomMapNum(idxmap.get(oldi,0))
    print(tag, "compact-mapped:", Chem.MolToSmiles(mh, isomericSmiles=True))
    for a in mh.GetAtoms(): a.SetAtomMapNum(0)
    print(tag, "compact-plain  :", Chem.MolToSmiles(mh, isomericSmiles=True))
