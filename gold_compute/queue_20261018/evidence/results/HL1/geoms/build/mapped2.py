
import numpy as np, os
from rdkit import Chem
B="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/build"
HBOND = {7:0, 8:1, 9:2, 10:3, 11:3, 12:4, 13:4, 14:5, 15:6, 16:6}
MAP = {0:4,1:5,2:6,3:7,4:8,5:9,6:10,17:1,18:2,19:3}
def mk(xyz, bonds, double, charges=()):
    lines=open(os.path.join(B,xyz)).read().splitlines()
    els=[l.split()[0] for l in lines[2:23]]
    coords=np.array([[float(x) for x in l.split()[1:4]] for l in lines[2:23]])
    rw=Chem.RWMol()
    for e in els: rw.AddAtom(Chem.Atom(e))
    for a,b in bonds:
        bt = Chem.BondType.TRIPLE if (a,b)==(17,18) and len(bonds)==20 else (Chem.BondType.DOUBLE if (a,b) in double else Chem.BondType.SINGLE)
        rw.AddBond(a,b, bt)
    m=rw.GetMol()
    for i,q in charges: m.GetAtomWithIdx(i).SetFormalCharge(q)
    Chem.SanitizeMol(m)
    for i in range(m.GetNumAtoms()): m.GetAtomWithIdx(i).SetNoImplicit(True)
    c=Chem.Conformer(21)
    for i in range(21): c.SetAtomPosition(i,[float(v) for v in coords[i]])
    m.RemoveAllConformers(); m.AddConformer(c)
    Chem.AssignStereochemistryFrom3D(m)
    return m
nb=[(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,6),(6,5)]
for j,i in HBOND.items(): nb.append((i,j))
mr = mk("RCg_exo.xyz", nb+[(17,18),(18,19),(17,20)], double=((0,1),(17,18)), charges=[(18,1),(19,-1)])
PB = nb+[(0,17),(17,18),(18,19),(19,1),(17,20)]
mp = mk("P_exo_start.xyz", PB, double=((17,18),))
for tag, m in [("reactant",mr),("product",mp)]:
    mh = Chem.RemoveHs(m)
    for a in mh.GetAtoms():
        pass
    # map on heavy atoms: need mapping from mh atoms back - RemoveHs keeps indices of heavy atoms in order
    # heavy atoms are indices 0..6 and 17,18,19 in m
    idxmap = {0:4,1:5,2:6,3:7,4:8,5:9,6:10, 17:1,18:2,19:3}
    heavy_order = [a.GetIdx() for a in m.GetAtoms() if a.GetSymbol()!="H"]
    for newi, oldi in enumerate(heavy_order):
        mh.GetAtomWithIdx(newi).SetAtomMapNum(idxmap.get(oldi,0))
    print(tag, "compact-mapped:", Chem.MolToSmiles(mh, isomericSmiles=True))
    for a in mh.GetAtoms(): a.SetAtomMapNum(0)
    print(tag, "compact-plain  :", Chem.MolToSmiles(mh, isomericSmiles=True))
