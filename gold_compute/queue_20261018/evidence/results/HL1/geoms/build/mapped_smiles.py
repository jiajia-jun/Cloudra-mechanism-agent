
import numpy as np, os
from rdkit import Chem
B="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/build"
HBOND = {7:0, 8:1, 9:2, 10:3, 11:3, 12:4, 13:4, 14:5, 15:6, 16:6}
MAP_R = {0:4,1:5,2:6,3:7,4:8,5:9,6:10,17:1,18:2,19:3}   # 0-based work idx -> map
MAP_P = {0:4,1:5,2:6,3:7,4:8,5:9,6:10,17:1,18:2,19:3}
def mk(xyz, bonds, double=()):
    lines=open(os.path.join(B,xyz)).read().splitlines()
    els=[l.split()[0] for l in lines[2:23]]
    coords=np.array([[float(x) for x in l.split()[1:4]] for l in lines[2:23]])
    rw=Chem.RWMol()
    for e in els: rw.AddAtom(Chem.Atom(e))
    for a,b in bonds:
        rw.AddBond(a,b, Chem.BondType.DOUBLE if (a,b) in double else Chem.BondType.SINGLE)
    m=rw.GetMol(); Chem.SanitizeMol(m)
    for i in range(m.GetNumAtoms()): m.GetAtomWithIdx(i).SetNoImplicit(True)
    c=Chem.Conformer(21)
    for i in range(21): c.SetAtomPosition(i,[float(v) for v in coords[i]])
    m.RemoveAllConformers(); m.AddConformer(c)
    Chem.AssignStereochemistryFrom3D(m)
    return m

nb=[(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,6),(6,5)]
for j,i in HBOND.items(): nb.append((i,j))
PB = nb+[(0,17),(17,18),(18,19),(19,1),(17,20)]
# reactant
mr = mk("RCg_exo.xyz", nb+[(17,18),(18,19),(19,20)], double=())
print("reactant plain :", Chem.MolToSmiles(Chem.RemoveHs(mr), isomericSmiles=True))
# product
mp = mk("P_exo_start.xyz", PB, double=((17,18),))
print("product plain  :", Chem.MolToSmiles(Chem.RemoveHs(mp), isomericSmiles=True))

def mapped(m, MP):
    for a in m.GetAtoms():
        if a.GetIdx() in MP: a.SetAtomMapNum(MP[a.GetIdx()])
    return Chem.MolToSmiles(m, isomericSmiles=True, canonical=True)

print("reactant mapped:", mapped(mr, MAP_R))
print("product  mapped:", mapped(mp, MAP_P))
