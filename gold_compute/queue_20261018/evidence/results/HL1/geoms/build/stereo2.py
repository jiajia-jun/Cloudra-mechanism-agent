
import numpy as np, os
from rdkit import Chem
B="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/build"
HBOND = {7:0, 8:1, 9:2, 10:3, 11:3, 12:4, 13:4, 14:5, 15:6, 16:6}
for f in ["P_exo_start.xyz","P_endo_start.xyz"]:
    lines=open(os.path.join(B,f)).read().splitlines()
    els=[l.split()[0] for l in lines[2:23]]
    coords=np.array([[float(x) for x in l.split()[1:4]] for l in lines[2:23]])
    rw=Chem.RWMol()
    for e in els: rw.AddAtom(Chem.Atom(e))
    bl=[(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,6),(6,5),(0,17),(17,18),(18,19),(19,1),(17,20)]
    for j,i in HBOND.items(): bl.append((i,j))
    for a,b in bl:
        rw.AddBond(a,b, Chem.BondType.DOUBLE if (a,b)==(17,18) else Chem.BondType.SINGLE)
    m=rw.GetMol(); Chem.SanitizeMol(m)
    for i in range(m.GetNumAtoms()): m.GetAtomWithIdx(i).SetNoImplicit(True)
    conf=Chem.Conformer(21)
    for i in range(21): conf.SetAtomPosition(i,[float(v) for v in coords[i]])
    m.RemoveAllConformers(); m.AddConformer(conf)
    Chem.AssignStereochemistryFrom3D(m)
    mh=Chem.RemoveHs(m)
    print(f,"->",Chem.MolToSmiles(mh, isomericSmiles=True))
    # round trip check
    m2=Chem.MolFromSmiles(Chem.MolToSmiles(mh))
    print("   formula", Chem.rdMolDescriptors.CalcMolFormula(mh), "roundtrip", Chem.MolToSmiles(m2,isomericSmiles=True))
